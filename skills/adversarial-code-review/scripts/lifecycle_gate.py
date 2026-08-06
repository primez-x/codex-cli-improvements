"""Portable, fail-closed lifecycle gate for immutable review deliveries."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from review_contracts import (  # noqa: E402
    BundleStore,
    SnapshotLimits,
    build_local_git_resolver,
    build_bundle,
    build_git_snapshot,
    canonical_bytes,
    compute_packet_sha256,
    compute_raw_sha256,
    delivery_address_sha256,
    MANDATORY_REVIEW_LENSES,
    validate_disposition_ledger,
    validate_finding_evidence,
    validate_git_object_id,
    validate_lens_coverage,
    validate_review_output,
    validate_review_receipt,
)
from verification_evidence import build_verification_evidence, load_production_manifest  # noqa: E402


REVIEWER_TYPE = "sol_reviewer"
REVIEWER_MODEL = "gpt-5.6-sol"
REVIEWER_EFFORT = "max"
DELIVERY_ADDRESSING = "composite-v1"
BLOCKED_MARKER = "[adversarial-review-blocked]"
MAX_DISPOSITION_BYTES = 1_048_576
MAX_SHELL_COMMAND_CHARS = 262_144
LIKELY_MUTATION = re.compile(
    r"\b(?:implement|fix|build|add|change|update|create|remove|refactor|remed(?:y|iate)|apply|ship)\b",
    re.IGNORECASE,
)
EXPLICIT_EXEMPTION = re.compile(
    r"\b(?:plan\s+only|review\s+only|read[ -]?only|"
    r"(?:no|without)\s+(?:code\s+)?changes?|do\s+not\s+(?:change|edit|modify))\b",
    re.IGNORECASE,
)
FOLLOW_ON_MUTATION = re.compile(
    r"\b(?:then|but|next|afterwards?)\s+(?:please\s+)?"
    r"(?:implement|fix|build|add|change|update|create|remove|refactor|remed(?:y|iate)|apply|ship)\b",
    re.IGNORECASE,
)
DIRECT_MUTATION_TOOLS = {
    "apply_patch",
    "functions.apply_patch",
    "edit",
    "write",
    "mcp__filesystem__create_directory",
    "mcp__filesystem__edit_file",
    "mcp__filesystem__move_file",
    "mcp__filesystem__write_file",
}
SHELL_TOOLS = {
    "bash",
    "exec_command",
    "functions.exec_command",
    "functions.shell_command",
    "powershell",
    "shell_command",
}
SUCCESS_WORDS = re.compile(r"\b(?:complete|completed|delivered|done|fixed|pass(?:ed)?|success(?:ful|fully)?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ShellToken:
    kind: str
    value: str
    quoted: bool = False
    dynamic: bool = False
    substitutions_active: bool = True


_SHELL_SEPARATORS = {";", "&&", "||", "|", "|&", "\n", "(", ")", "{", "}"}
_SHELL_OPERATORS = (
    "&>>",
    "2>>",
    "1>>",
    "*>>",
    "<<<",
    ">>",
    "2>",
    "1>",
    "*>",
    "&>",
    "<<",
    "&&",
    "||",
    "|&",
    ";",
    "|",
    "&",
    ">",
    "<",
    "(",
    ")",
    "{",
    "}",
)
_DIRECT_COMMAND_MUTATIONS = {
    "add-content",
    "apply_patch",
    "copy-item",
    "cp",
    "cpi",
    "del",
    "erase",
    "install",
    "md",
    "mkdir",
    "move",
    "move-item",
    "mv",
    "new-item",
    "ni",
    "out-file",
    "rd",
    "remove-item",
    "rename",
    "rename-item",
    "ren",
    "ri",
    "rmdir",
    "rm",
    "set-content",
    "touch",
    "truncate",
}
_POWERSHELL_MUTATION_ALIASES = {"ac", "mi", "rni", "sc"}
_LIFECYCLE_ROOT_ENVIRONMENT = {"CODEX_ADVERSARIAL_STATE", "CODEX_HOME"}
_PYTHON_WRITER_SCRIPTS = {
    "evaluate_review_corpus.py",
    "install_review_gate.py",
}
_PYTHON_WRITER_MODULES = {
    "build",
    "compileall",
    "ensurepip",
    "pip",
    "py_compile",
    "venv",
    "wheel",
    "zipapp",
}
_UNITTEST_FLAGS = {
    "-b",
    "--buffer",
    "-c",
    "--catch",
    "-f",
    "--failfast",
    "--locals",
    "-q",
    "--quiet",
    "-v",
    "--verbose",
}
_UNITTEST_VALUE_OPTIONS = {
    "-k",
    "--durations",
}
_UNITTEST_DISCOVERY_VALUE_OPTIONS = {
    "-s",
    "--start-directory",
    "-p",
    "--pattern",
    "-t",
    "--top-level-directory",
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _filesystem_path(path: Path) -> Path:
    """Return a Windows extended-length path without changing logical addresses."""

    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    absolute = os.path.abspath(value)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def _environment_get(environment: Mapping[str, str], name: str) -> str | None:
    if os.name != "nt":
        return environment.get(name)
    expected = name.casefold()
    return next(
        (value for key, value in environment.items() if key.casefold() == expected),
        None,
    )


def default_root(environment: Mapping[str, str] | None = None) -> Path:
    effective = os.environ if environment is None else environment
    home = Path(_environment_get(effective, "CODEX_HOME") or Path.home() / ".codex")
    return Path(
        _environment_get(effective, "CODEX_ADVERSARIAL_STATE")
        or home / "hooks" / "state" / "adversarial-review"
    )


def default_profile() -> Path:
    return HERE.parents[2] / "agents" / "sol_reviewer.toml"


def state_path(root: Path, session_id: str, turn_id: str) -> Path:
    """Return the digest-only active pointer path for a session turn."""
    return root / "active" / digest(session_id) / f"{digest(turn_id)}.json"


def session_state_path(root: Path, session_id: str) -> Path:
    """Return the session continuity pointer used across Codex turn IDs."""
    return root / "active" / digest(session_id) / "session.json"


def pending_path(root: Path, session_id: str, turn_id: str) -> Path:
    return root / "pending" / digest(session_id) / f"{digest(turn_id)}.json"


def delivery_path(root: Path, state: Mapping[str, Any]) -> Path:
    return (
        root
        / "deliveries"
        / delivery_address_sha256(state["session_id"], state["task_id"], state["delivery_id"])
        / f"generation-{int(state['generation'])}.json"
    )


def legacy_delivery_path(root: Path, state: Mapping[str, Any]) -> Path:
    """Return the exact V1 address used before composite delivery digests."""

    return (
        root
        / "deliveries"
        / digest(str(state["session_id"]))
        / digest(str(state["task_id"]))
        / digest(str(state["delivery_id"]))
        / f"generation-{int(state['generation'])}.json"
    )


def session_lock(root: Path, session_id: str, turn_id: str) -> Path:
    # All turns in a session share delivery continuity and therefore one lock.
    # Keep turn_id in the signature so hook/CLI call sites remain explicit.
    del turn_id
    return root / "locks" / f"{digest(session_id)}.state"


@contextmanager
def lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        deadline = time.monotonic() + 10
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    handle.write(b"0")
                    handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("gate lock timeout")
                time.sleep(0.01)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load(path: Path) -> dict[str, Any] | None:
    physical = _filesystem_path(path)
    if not physical.exists():
        return None
    value = json.loads(physical.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("gate state must be an object")
    return value


def save(path: Path, value: Mapping[str, Any]) -> None:
    physical = _filesystem_path(path)
    physical.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(physical.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(dir=physical.parent, prefix=".gate-", text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, physical)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _relative_state(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()


def _pointer(root: Path, state: Mapping[str, Any], target: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": _relative_state(root, target),
        "delivery_sha256": digest(str(state["delivery_id"])),
        "generation": state["generation"],
    }


def save_active(root: Path, state: dict[str, Any]) -> None:
    target = delivery_path(root, state) if state.get("task_id") else pending_path(root, state["session_id"], state["turn_id"])
    save(target, state)
    pointer = _pointer(root, state, target)
    save(state_path(root, state["session_id"], state["turn_id"]), pointer)
    if state["classification"] in {"pending", "material"}:
        save(session_state_path(root, state["session_id"]), pointer)


def _rollover_path(root: Path, state: Mapping[str, Any], next_generation: int) -> Path:
    return (
        root
        / "transactions"
        / digest(str(state["session_id"]))
        / digest(str(state["delivery_id"]))
        / f"generation-{int(state['generation'])}-to-{next_generation}.json"
    )


def _fault(point: str) -> None:
    """Deterministic test-only crash injection; absent in normal operation."""
    if os.environ.get("CODEX_ACR_FAULT_INJECT") == point:
        raise RuntimeError(f"injected lifecycle fault: {point}")


def _recover_rollovers(root: Path, session_id: str) -> None:
    directory = root / "transactions" / digest(session_id)
    if not directory.exists():
        return
    for path in sorted(directory.rglob("generation-*-to-*.json")):
        journal = load(path)
        if journal is None:
            continue
        fields = {"schema_version", "phase", "session_id", "delivery_id", "from_generation", "to_generation", "previous", "next"}
        if set(journal) != fields or journal["schema_version"] != 1 or journal["phase"] not in {"prepared", "completed"}:
            raise ValueError("accepted-generation rollover journal is malformed")
        if journal["session_id"] != session_id:
            raise ValueError("accepted-generation rollover session mismatch")
        previous = journal["previous"]
        following = journal["next"]
        if not isinstance(previous, dict) or not isinstance(following, dict):
            raise ValueError("accepted-generation rollover states are malformed")
        if (
            previous.get("session_id") != session_id
            or following.get("session_id") != session_id
            or previous.get("delivery_id") != journal["delivery_id"]
            or following.get("delivery_id") != journal["delivery_id"]
            or previous.get("generation") != journal["from_generation"]
            or following.get("generation") != journal["to_generation"]
            or journal["to_generation"] != journal["from_generation"] + 1
            or following.get("classification") != "material"
        ):
            raise ValueError("accepted-generation rollover identity is invalid")
        if journal["phase"] == "prepared":
            save(delivery_path(root, previous), previous)
            save(delivery_path(root, following), following)
            save_active(root, following)
            save(path, {**journal, "phase": "completed"})


def _load_pointer(root: Path, pointer_path: Path, session_id: str) -> dict[str, Any] | None:
    pointer = load(pointer_path)
    if pointer is None:
        return None
    if set(pointer) != {"schema_version", "state", "delivery_sha256", "generation"} or pointer["schema_version"] != 1:
        raise ValueError("active delivery pointer is malformed")
    relative = PurePosixPath(str(pointer["state"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("active delivery pointer escapes state root")
    target = _filesystem_path(root.joinpath(*relative.parts)).resolve()
    resolved_root = _filesystem_path(root).resolve()
    if resolved_root not in target.parents:
        raise ValueError("active delivery pointer escapes state root")
    state = load(target)
    if state is None:
        raise ValueError("active delivery state is missing")
    if state.get("session_id") != session_id:
        raise ValueError("active delivery identity mismatch")
    if pointer["delivery_sha256"] != digest(str(state.get("delivery_id"))) or pointer["generation"] != state.get("generation"):
        raise ValueError("active delivery address mismatch")
    expected = delivery_path(root, state) if state.get("task_id") else pending_path(root, session_id, str(state.get("turn_id")))
    if target == _filesystem_path(expected).resolve():
        return state
    if state.get("task_id") and target == _filesystem_path(legacy_delivery_path(root, state)).resolve():
        _migrate_legacy_delivery(root, state, pointer_path)
        return state
    raise ValueError("state is not addressed by delivery generation")


def _migrate_legacy_delivery(
    root: Path,
    state: dict[str, Any],
    loaded_pointer_path: Path,
) -> None:
    """Copy legacy state and repoint only matching pointers under the caller lock."""

    legacy = legacy_delivery_path(root, state)
    current = delivery_path(root, state)
    existing = load(current)
    if existing is not None and existing != state:
        raise ValueError("legacy migration conflicts with composite delivery state")
    save(current, state)
    old_pointer = _pointer(root, state, legacy)
    new_pointer = _pointer(root, state, current)
    candidates = {
        loaded_pointer_path,
        state_path(root, str(state["session_id"]), str(state["turn_id"])),
        session_state_path(root, str(state["session_id"])),
    }
    for candidate in candidates:
        if load(candidate) == old_pointer:
            save(candidate, new_pointer)


def load_active(root: Path, session_id: str, turn_id: str) -> dict[str, Any] | None:
    _recover_rollovers(root, session_id)
    exact = _load_pointer(root, state_path(root, session_id, turn_id), session_id)
    if exact is not None:
        return exact
    return _load_pointer(root, session_state_path(root, session_id), session_id)


def response(event: str, text: str, *, block: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text}
    }
    if block:
        result.update({"decision": "block", "reason": text})
    return result


def new_state(
    payload: Mapping[str, Any],
    classification: str,
    exempt_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "session_id": payload["session_id"],
        "turn_id": payload["turn_id"],
        "delivery_id": uuid.uuid4().hex,
        "classification": classification,
        "exempt_reason": exempt_reason if classification == "exempt" else None,
        "status": "pending_classification" if classification == "pending" else "exempt",
        "task_id": None,
        "paths_sha256": None,
        "generation": 0,
        "mutation_epoch": 0,
        "seen_tool_use_ids": [],
        "inflight_tool_use_ids": [],
        "snapshot_sha256": None,
        "bundle_sha256": None,
        "lens_sha256": None,
        "packet_sha256": None,
        "frozen_epoch": None,
        "workspace_sha256": None,
        "profile_sha256": None,
        "attempt_id": None,
        "reviewer_agent": None,
        "consumed_attempt_ids": [],
        "review_output": None,
        "output_sha256": None,
        "pending_disposition_sha256": None,
        "dispositions": None,
        "ledger": None,
        "receipt": None,
        "blocked_evidence_sha256": None,
        "blocked_origin": None,
        "stale_reason": None,
    }


def profile_digest(profile_path: Path) -> str:
    try:
        raw = profile_path.read_bytes()
        profile = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("installed sol_reviewer profile is missing or invalid") from exc
    required = {
        "name": REVIEWER_TYPE,
        "model": REVIEWER_MODEL,
        "model_reasoning_effort": REVIEWER_EFFORT,
        "sandbox_mode": "read-only",
    }
    if any(profile.get(field) != expected for field, expected in required.items()):
        raise ValueError("installed sol_reviewer profile does not match the required reviewer")
    instructions = str(profile.get("developer_instructions", "")).lower()
    for phrase in ("depth 1", "do not spawn", "do not", "strict `reviewoutputv1` json"):
        if phrase not in instructions:
            raise ValueError("installed sol_reviewer profile contract is incomplete")
    return compute_raw_sha256(raw)


def classify_prompt(text: str) -> tuple[str, str | None]:
    mutation_matches = list(LIKELY_MUTATION.finditer(text))
    if not mutation_matches:
        return "exempt", "automatic: no mutation request detected"

    exemption = EXPLICIT_EXEMPTION.search(text)
    if exemption:
        mutation_precedes_exemption = any(match.start() < exemption.start() for match in mutation_matches)
        follow_on_mutation = FOLLOW_ON_MUTATION.search(text, exemption.end())
        if not mutation_precedes_exemption and not follow_on_mutation:
            return "exempt", "automatic: explicit read-only or plan-only prompt"

    return "pending", None


def prompt(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    text = str(payload.get("prompt", ""))
    classification, exempt_reason = classify_prompt(text)
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        state = load_active(root, payload["session_id"], payload["turn_id"])
        unresolved = bool(
            state
            and state["classification"] in {"pending", "material"}
            and state["status"] != "completed"
            and not (state["status"] == "blocked" and state["blocked_origin"] == "operator-abandon")
        )
        if not unresolved:
            state = new_state(payload, classification, exempt_reason)
            save_active(root, state)
        elif state["turn_id"] != payload["turn_id"]:
            return response(
                "UserPromptSubmit",
                f"Prior material delivery_id={state['delivery_id']} remains unresolved across turns; its gate cannot be exempted.",
            )
    if state["classification"] == "exempt":
        return response("UserPromptSubmit", "Adversarial review gate exempt: recorded read-only or plan-only reason.")
    return response(
        "UserPromptSubmit",
        f"Adversarial gate pending delivery_id={state['delivery_id']}. Run lifecycle_gate.py classify with task and owned paths, then freeze.",
    )


def _shell_operator(text: str, index: int) -> str | None:
    return next((item for item in _SHELL_OPERATORS if text.startswith(item, index)), None)


def _dynamic_shell_value(value: str, *, dialect: str | None = None) -> bool:
    return bool(
        re.search(r"\$\(|\$\{|(?<!\\)\$[A-Za-z_]|%[^%\r\n]+%", value)
        or (dialect == "cmd" and re.search(r"![^!\r\n]+!", value))
    )


def _read_shell_word(text: str, index: int, *, dialect: str) -> tuple[ShellToken, int]:
    value: list[str] = []
    quoted = False
    substitutions_active = False
    while index < len(text):
        character = text[index]
        if character.isspace() or _shell_operator(text, index):
            break
        if character in {"'", '"'}:
            quoted = True
            quote = character
            if quote == '"':
                substitutions_active = True
            index += 1
            closed = False
            while index < len(text):
                character = text[index]
                if character == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        value.append(quote)
                        index += 2
                        continue
                    index += 1
                    closed = True
                    break
                if quote == '"' and character == "`" and dialect in {
                    "bash",
                    "dash",
                    "ksh",
                    "powershell",
                    "pwsh",
                    "sh",
                    "zsh",
                }:
                    raise ValueError("unsupported dialect-sensitive backtick escaping or substitution")
                if (
                    quote == '"'
                    and character == "\\"
                    and index + 1 < len(text)
                    and text[index + 1] in {'"', "\\", "$", "`"}
                ):
                    if dialect in {"bash", "dash", "ksh", "sh", "zsh"}:
                        raise ValueError("unsupported POSIX backslash escaping")
                value.append(character)
                index += 1
            if not closed:
                raise ValueError("unterminated shell quote")
            continue
        if character == "`" and dialect in {
            "bash",
            "dash",
            "ksh",
            "powershell",
            "pwsh",
            "sh",
            "zsh",
        }:
            raise ValueError("unsupported dialect-sensitive backtick escaping or substitution")
        if character == "\\" and dialect in {"bash", "dash", "ksh", "sh", "zsh"}:
            raise ValueError("unsupported POSIX backslash escaping")
        if character == "^" and dialect == "cmd":
            raise ValueError("unsupported cmd caret escaping")
        substitutions_active = True
        value.append(character)
        index += 1
    rendered = "".join(value)
    if not rendered and not quoted:
        raise ValueError("empty shell token")
    return ShellToken(
        "word",
        rendered,
        quoted=quoted,
        dynamic=substitutions_active and _dynamic_shell_value(rendered, dialect=dialect),
        substitutions_active=substitutions_active,
    ), index


def _read_powershell_here_string(text: str, index: int) -> tuple[ShellToken, int] | None:
    marker = next((item for item in ("@'", '@"') if text.startswith(item, index)), None)
    if marker is None:
        return None
    content_start = index + len(marker)
    if text.startswith("\r\n", content_start):
        content_start += 2
    elif text.startswith("\n", content_start):
        content_start += 1
    else:
        return None
    terminator = "'@" if marker == "@'" else '"@'
    match = re.search(rf"(?m)^{re.escape(terminator)}(?=\r?$)", text[content_start:])
    if match is None:
        raise ValueError("unterminated PowerShell here-string")
    body_start = content_start
    body_end = content_start + match.start()
    end = content_start + match.end()
    substitutions_active = marker == '@"'
    body = text[body_start:body_end]
    return (
        ShellToken(
            "word",
            body,
            quoted=True,
            dynamic=substitutions_active and _dynamic_shell_value(body),
            substitutions_active=substitutions_active,
        ),
        end,
    )


def _skip_heredoc_bodies(text: str, index: int, delimiters: list[str]) -> int:
    for delimiter in delimiters:
        found = False
        while index <= len(text):
            end = text.find("\n", index)
            if end < 0:
                end = len(text)
            line = text[index:end].rstrip("\r")
            index = end + (end < len(text))
            if line == delimiter:
                found = True
                break
        if not found:
            raise ValueError("unterminated shell here-document")
    return index


def _shell_tokens(text: str, *, dialect: str) -> list[ShellToken]:
    tokens: list[ShellToken] = []
    heredoc_delimiters: list[str] = []
    expect_heredoc_delimiter = False
    index = 0
    while index < len(text):
        character = text[index]
        if character in " \t\r":
            index += 1
            continue
        if character == "\n":
            tokens.append(ShellToken("operator", "\n"))
            index += 1
            if heredoc_delimiters:
                index = _skip_heredoc_bodies(text, index, heredoc_delimiters)
                heredoc_delimiters.clear()
            continue
        if character == "#":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        here_string = _read_powershell_here_string(text, index)
        if here_string is not None:
            token, index = here_string
            tokens.append(token)
            continue
        operator = _shell_operator(text, index)
        if operator is not None:
            kind = "redirection" if "<" in operator or ">" in operator else "operator"
            tokens.append(ShellToken(kind, operator))
            expect_heredoc_delimiter = operator == "<<"
            index += len(operator)
            continue
        token, index = _read_shell_word(text, index, dialect=dialect)
        tokens.append(token)
        if expect_heredoc_delimiter:
            if token.dynamic or not token.value:
                raise ValueError("dynamic shell here-document delimiter")
            heredoc_delimiters.append(token.value)
            expect_heredoc_delimiter = False
    if expect_heredoc_delimiter or heredoc_delimiters:
        raise ValueError("unterminated shell here-document")
    return tokens


def _command_name(value: str) -> str:
    name = re.split(r"[\\/]", value)[-1].casefold()
    for suffix in (".exe", ".com", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _leading_environment_assignments(
    tokens: list[ShellToken],
) -> tuple[list[ShellToken], dict[str, str], list[str], tuple[str, str] | None]:
    effective = dict(os.environ)
    assigned: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        match = re.fullmatch(
            r"(?i)(?:\$env:)?([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)",
            token.value,
            re.DOTALL,
        )
        if match is None:
            break
        name, operator, value = match.groups()
        windows_names = os.name == "nt"
        normalized = name.upper() if windows_names else name
        if token.dynamic or "\0" in value:
            return (
                tokens[index + 1 :],
                effective,
                assigned,
                ("ambiguous", f"environment assignment {normalized} is dynamic or malformed"),
            )
        if operator == "+=":
            value = (_environment_get(effective, name) or "") + value
        for existing in tuple(effective):
            if (
                existing.casefold() == name.casefold()
                if windows_names
                else existing == name
            ):
                del effective[existing]
        effective[normalized] = value
        assigned.append(normalized)
        index += 1
    return tokens[index:], effective, assigned, None


def _classify_git(_arguments: list[ShellToken]) -> tuple[str, str]:
    return "mutation", "Git may mutate state or execute configured helpers"


def _next_non_option(values: list[str], start: int = 0) -> str | None:
    index = start
    while index < len(values):
        value = values[index]
        if value in {"-c", "-C", "--git-dir", "--work-tree", "--config-env"}:
            index += 2
            continue
        if value.startswith("-"):
            index += 1
            continue
        return value.casefold()
    return None


def _path_is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _parse_lifecycle_options(
    action: str,
    arguments: list[str],
) -> bool:
    specs: dict[str, tuple[set[str], set[str], dict[str, int]]] = {
        "classify": (
            {"--session-id", "--turn-id", "--classification"},
            {"--session-id", "--turn-id", "--classification", "--task-id", "--reason"},
            {"--paths": 0},
        ),
        "freeze": (
            {"--session-id", "--turn-id", "--cwd", "--verification-manifest"},
            {
                "--session-id",
                "--turn-id",
                "--cwd",
                "--verification-manifest",
                "--production-manifest",
                "--max-freeze-seconds",
            },
            {"--paths": 1},
        ),
        "disposition": (
            {"--session-id", "--turn-id"},
            {"--session-id", "--turn-id", "--file", "--json"},
            {"--stdin": 0},
        ),
        "status": ({"--session-id", "--turn-id"}, {"--session-id", "--turn-id"}, {}),
        "block": (
            {"--session-id", "--turn-id", "--evidence"},
            {"--session-id", "--turn-id", "--evidence"},
            {},
        ),
        "reconcile": (
            {"--session-id", "--turn-id", "--tool-use-id", "--evidence"},
            {"--session-id", "--turn-id", "--tool-use-id", "--evidence"},
            {},
        ),
        "abort": (
            {"--session-id", "--turn-id", "--scope", "--evidence"},
            {"--session-id", "--turn-id", "--scope", "--attempt-id", "--evidence"},
            {},
        ),
        "export-replay": (
            {"--session-id", "--turn-id"},
            {"--session-id", "--turn-id"},
            {},
        ),
        "health": (set(), set(), {}),
    }
    if action not in specs:
        return False
    required, valued, list_options = specs[action]
    seen: set[str] = set()
    parsed: dict[str, list[str]] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option in seen:
            return False
        if option in valued:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                return False
            seen.add(option)
            parsed[option] = [arguments[index + 1]]
            index += 2
            continue
        if option in list_options:
            minimum = list_options[option]
            index += 1
            start = index
            while index < len(arguments) and not arguments[index].startswith("--"):
                index += 1
            if index - start < minimum:
                return False
            seen.add(option)
            parsed[option] = arguments[start:index]
            continue
        return False
    if not required.issubset(seen):
        return False
    if action == "disposition":
        sources = seen & {"--file", "--json", "--stdin"}
        if len(sources) != 1:
            return False
    if action == "classify" and parsed["--classification"][0] not in {"exempt", "material"}:
        return False
    if action == "abort" and parsed["--scope"][0] not in {"reviewer", "delivery"}:
        return False
    return True


def _exact_lifecycle_cli(
    values: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[bool, str | None, bool]:
    """Return exact-script match, authenticated action, and state-root-in-cwd."""

    if not values:
        return False, None, False
    script = Path(values[0])
    if not script.is_absolute():
        script = cwd / script
    try:
        if os.path.normcase(str(script.resolve())) != os.path.normcase(str(Path(__file__).resolve())):
            return False, None, False
    except OSError:
        return False, None, False
    arguments = values[1:]
    index = 0
    state_root: Path | None = None
    seen_globals: set[str] = set()
    while index < len(arguments) and arguments[index] in {"--state-root", "--profile-path"}:
        option = arguments[index]
        if option in seen_globals or index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
            return True, None, False
        seen_globals.add(option)
        if option == "--state-root":
            state_root = Path(arguments[index + 1])
        index += 2
    if index >= len(arguments):
        return True, None, False
    action = arguments[index]
    if not _parse_lifecycle_options(action, arguments[index + 1 :]):
        return True, None, False
    effective_root = state_root or default_root(environment)
    if not effective_root.is_absolute():
        effective_root = cwd / effective_root
    return True, action, _path_is_within(effective_root, cwd)


def _shell_substitutions(value: str) -> list[str]:
    substitutions: list[str] = []
    search = 0
    while True:
        start = value.find("$(", search)
        if start < 0:
            return substitutions
        depth = 1
        index = start + 2
        while index < len(value) and depth:
            if value.startswith("$(", index):
                depth += 1
                index += 2
                continue
            if value[index] == ")":
                depth -= 1
                if depth == 0:
                    substitutions.append(value[start + 2 : index])
                    search = index + 1
                    break
            index += 1
        if depth:
            raise ValueError("unterminated shell command substitution")


def _classify_lifecycle_values(
    values: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str] | None:
    exact_script, action, writes_inside_cwd = _exact_lifecycle_cli(
        values,
        cwd=cwd,
        environment=environment,
    )
    if action is not None:
        if action in {"classify", "freeze", "disposition", "block", "reconcile", "abort"}:
            if writes_inside_cwd:
                return "mutation", "lifecycle state root is inside the task workspace"
            return "state_control", f"authenticated lifecycle {action} state-control"
        return "read_only", f"authenticated lifecycle {action} read-only action"
    if exact_script:
        return "ambiguous", "lifecycle CLI action grammar is not authenticated"
    if values and _command_name(values[0]) == "lifecycle_gate.py":
        return "ambiguous", "lifecycle CLI script identity is not authenticated"
    return None


def _authenticated_unittest(arguments: list[str], cwd: Path) -> bool:
    if (cwd / "unittest.py").exists() or (cwd / "unittest" / "__init__.py").exists():
        return False
    discovery = False
    saw_target = False
    index = 0
    while index < len(arguments):
        value = arguments[index]
        lowered = value.casefold()
        if lowered in _UNITTEST_FLAGS:
            index += 1
            continue
        value_options = set(_UNITTEST_VALUE_OPTIONS)
        if discovery:
            value_options.update(_UNITTEST_DISCOVERY_VALUE_OPTIONS)
        if lowered in value_options:
            if index + 1 >= len(arguments):
                return False
            option_value = arguments[index + 1]
            if not option_value or option_value.startswith("-") or _dynamic_shell_value(option_value):
                return False
            index += 2
            continue
        if lowered == "discover" and not discovery and not saw_target:
            discovery = True
            index += 1
            continue
        if value.startswith("-") or discovery or _dynamic_shell_value(value):
            return False
        normalized = value.replace("\\", "/")
        if (
            normalized.startswith("/")
            or re.match(r"^[A-Za-z]:/", normalized)
            or ".." in normalized.split("/")
            or not (
                normalized == "tests"
                or normalized.startswith(("tests/", "tests.", "test_"))
            )
        ):
            return False
        saw_target = True
        index += 1
    return True


def _resolved_python_script(value: str, cwd: Path) -> Path | None:
    if not value or value == "-" or _dynamic_shell_value(value):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = cwd / path
    try:
        return path.resolve()
    except OSError:
        return None


def _classify_python_module(
    module: str,
    arguments: list[str],
    *,
    cwd: Path,
) -> tuple[str, str]:
    normalized = module.casefold()
    if not module or _dynamic_shell_value(module):
        return "ambiguous", "Python module position is dynamic or missing"
    if normalized == "unittest":
        if _authenticated_unittest(arguments, cwd):
            return "mutation", "authenticated unittest execution may write project fixtures"
        return "ambiguous", "Python unittest invocation grammar is not authenticated"
    if normalized in _PYTHON_WRITER_MODULES:
        return "mutation", f"recognized Python writer module {normalized}"
    return "ambiguous", f"Python module {module} has unknown file effects"


def _classify_python_script(
    arguments: list[str],
    *,
    cwd: Path,
) -> tuple[str, str]:
    if not arguments:
        return "ambiguous", "interactive Python execution has unknown file effects"
    lifecycle = _classify_lifecycle_values(arguments, cwd=cwd)
    if lifecycle is not None:
        return lifecycle
    script = arguments[0]
    if script == "-" or _dynamic_shell_value(script):
        return "ambiguous", "Python stdin or dynamic script execution has unknown file effects"
    name = _command_name(script)
    if name in _PYTHON_WRITER_SCRIPTS:
        return "mutation", f"recognized Python writer script {name}"
    resolved = _resolved_python_script(script, cwd)
    routing_test = (
        HERE.parent.parent
        / "delivery-orchestration"
        / "scripts"
        / "test_routing_policy.py"
    ).resolve()
    if resolved == routing_test and len(arguments) == 1:
        return "read_only", "authenticated read-only routing-policy verifier"
    return "ambiguous", f"Python script {script} has unknown file effects"


def _classify_shell_segment(
    segment: list[ShellToken],
    *,
    dialect: str,
    cwd: Path,
    depth: int,
) -> tuple[str, str]:
    word_tokens: list[ShellToken] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        if token.kind == "word":
            substitutions: list[str] = []
            if token.substitutions_active:
                try:
                    substitutions = _shell_substitutions(token.value)
                except ValueError as exc:
                    return "ambiguous", str(exc)
            for substitution in substitutions:
                nested = _classify_shell_command(
                    substitution,
                    dialect=dialect,
                    cwd=cwd,
                    depth=depth + 1,
                )
                if nested[0] in {"mutation", "ambiguous"}:
                    return nested
            word_tokens.append(token)
            index += 1
            continue
        if token.kind != "redirection":
            if token.value == "&":
                word_tokens.append(token)
            index += 1
            continue
        output = ">" in token.value
        index += 1
        if index >= len(segment):
            return "ambiguous", "redirection target is missing"
        target = segment[index]
        if target.value == "&" and index + 1 < len(segment) and segment[index + 1].value.isdigit():
            index += 2
            continue
        if target.kind != "word":
            return "ambiguous", "redirection target is dynamic or malformed"
        if output:
            sink = target.value.casefold()
            if sink in {"$null", "nul", "nul:", "&1", "&2", "/dev/null", "/dev/stdout", "/dev/stderr"}:
                index += 1
                continue
            if target.dynamic:
                return "ambiguous", "output redirection target is dynamic"
            if sink:
                return "mutation", "shell output redirection writes bytes"
        index += 1

    command_tokens, effective_environment, assigned, assignment_failure = (
        _leading_environment_assignments(word_tokens)
    )
    if assignment_failure is not None:
        return assignment_failure
    assigned_set = set(assigned)
    lifecycle_assignment = assigned_set & _LIFECYCLE_ROOT_ENVIRONMENT
    if lifecycle_assignment and assigned_set <= _LIFECYCLE_ROOT_ENVIRONMENT:
        effective_root = default_root(effective_environment)
        if not effective_root.is_absolute():
            effective_root = cwd / effective_root
        if _path_is_within(effective_root, cwd):
            return "mutation", "lifecycle environment redirects state writes into the task workspace"
        return "ambiguous", "lifecycle state-root environment assignment is not authenticated"
    if assigned:
        return "ambiguous", "leading environment assignments are not authenticated read-only grammar"

    while command_tokens and command_tokens[0].value.casefold() in {"&", "command", "builtin", "call"}:
        command_tokens.pop(0)
    if not command_tokens:
        return "read_only", "shell segment has no executable command"
    if command_tokens[0].dynamic:
        return "ambiguous", "shell executable position is dynamic"

    values = [token.value for token in command_tokens]
    command = _command_name(values[0])
    arguments = values[1:]
    direct_lifecycle = _classify_lifecycle_values(
        values,
        cwd=cwd,
        environment=effective_environment,
    )
    if direct_lifecycle is not None:
        return direct_lifecycle
    if command in {"rem", "::"}:
        return "read_only", "shell comment command is inert"
    if command in {
        "alias",
        "env",
        "export",
        "function",
        "new-alias",
        "set",
        "set-alias",
        "setenv",
    } and arguments:
        return "ambiguous", f"shell definition command {command} may alter later command resolution"
    if command in _DIRECT_COMMAND_MUTATIONS or (
        dialect == "powershell" and command in _POWERSHELL_MUTATION_ALIASES
    ):
        return "mutation", f"recognized mutation command {command}"
    if command in {"tee", "tee-object"}:
        lowered = [value.casefold() for value in arguments]
        if command == "tee-object":
            file_argument = any(
                value in {"-filepath", "-literalpath"}
                or value.startswith(("-filepath:", "-literalpath:"))
                for value in lowered
            )
            if not file_argument and "-variable" not in lowered:
                file_argument = any(not value.startswith("-") for value in arguments)
        else:
            file_argument = any(not value.startswith("-") for value in arguments)
        return (
            ("mutation", "tee command has a file target")
            if file_argument
            else ("read_only", "tee command has no file target")
        )
    if command == "git":
        return _classify_git(command_tokens[1:])
    if command == "sed" and any(
        value == "--in-place" or re.fullmatch(r"-[A-Za-z]*i[A-Za-z]*(?:=.*)?", value)
        for value in arguments
    ):
        return "mutation", "sed in-place mode writes files"
    if command in {"npm", "pnpm", "yarn"}:
        action = _next_non_option(arguments)
        if action in {"install", "add", "remove"}:
            return "mutation", f"recognized package mutation {action}"
        if action == "run" and any(value.casefold() in {"build", "generate"} for value in arguments):
            return "mutation", "package build or generation writes output"
    if command in {"dotnet", "msbuild", "cargo", "go"} and _next_non_option(arguments) in {
        "build",
        "publish",
        "install",
        "generate",
    }:
        return "mutation", f"recognized build mutation {command}"
    if re.fullmatch(r"\[(?:system\.)?io\.file\]::(?:write\w*|append\w*|create\w*|openwrite)", command):
        return "mutation", "System.IO.File command writes files"

    if command in {"bash", "sh", "zsh", "dash", "ksh"}:
        flags = {"-c", "--command"}
    elif command in {"powershell", "pwsh"}:
        flags = {"-c", "-command", "--command"}
    elif command == "cmd":
        flags = {"/c", "/k"}
    else:
        flags = set()
    if flags:
        nested_index = next(
            (
                i
                for i, value in enumerate(arguments)
                if value.casefold() in flags
                or (
                    command in {"bash", "sh", "zsh", "dash", "ksh"}
                    and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", value)
                )
            ),
            None,
        )
        if nested_index is None or nested_index + 1 >= len(arguments):
            return "ambiguous", f"nested {command} invocation has no literal command argument"
        nested = arguments[nested_index + 1]
        if _dynamic_shell_value(nested):
            return "ambiguous", f"nested {command} command argument is dynamic"
        return _classify_shell_command(
            nested,
            dialect=command,
            cwd=cwd,
            depth=depth + 1,
        )
    if command in {"eval", "iex", "invoke-expression"}:
        if not arguments or any(_dynamic_shell_value(value) for value in arguments):
            return "ambiguous", f"dynamic {command} invocation cannot be resolved"
        return _classify_shell_command(
            " ".join(arguments),
            dialect=dialect,
            cwd=cwd,
            depth=depth + 1,
        )

    python_command = command == "py" or command.startswith("python")
    if python_command:
        if len(arguments) == 1 and arguments[0] in {"-h", "--help", "-V", "-VV", "--version"}:
            return "read_only", "authenticated Python interpreter information command"
        script_index = 0
        while script_index < len(arguments) and arguments[script_index].startswith("-"):
            option = arguments[script_index]
            if option == "-c":
                return "ambiguous", "inline Python execution has unknown file effects"
            if option == "-m":
                if script_index + 1 >= len(arguments):
                    return "ambiguous", "Python module position is missing"
                return _classify_python_module(
                    arguments[script_index + 1],
                    arguments[script_index + 2 :],
                    cwd=cwd,
                )
            if option in {"-W", "-X"}:
                if script_index + 1 >= len(arguments):
                    return "ambiguous", f"Python option {option} is missing its value"
                script_index += 2
                continue
            if option == "--":
                script_index += 1
                break
            if not re.fullmatch(
                r"(?:-[bBdEhiIOPqRsSuvVx]|-OO?|-[23](?:\.\d+)?)",
                option,
            ):
                return "ambiguous", f"Python option {option} is not authenticated"
            script_index += 1
        return _classify_python_script(arguments[script_index:], cwd=cwd)
    if command in {"start-process", "start"} or command.endswith((".ps1", ".sh", ".bat", ".cmd")):
        return "ambiguous", "indirect executable invocation cannot be resolved"
    return "read_only", "command and arguments have no recognized delivery mutation"


def _classify_shell_command(
    command: str,
    *,
    dialect: str,
    cwd: Path,
    depth: int = 0,
) -> tuple[str, str]:
    if depth > 4:
        return "ambiguous", "nested shell depth exceeds the classifier bound"
    if len(command) > MAX_SHELL_COMMAND_CHARS:
        return "ambiguous", "shell command exceeds the classifier bound"
    try:
        tokens = _shell_tokens(command, dialect=dialect)
    except ValueError as exc:
        return "ambiguous", str(exc)
    segments: list[list[ShellToken]] = [[]]
    for token_index, token in enumerate(tokens):
        if token.kind == "operator" and token.value in _SHELL_SEPARATORS:
            segments.append([])
        elif token.kind == "operator" and token.value == "&":
            previous = tokens[token_index - 1] if token_index else None
            following = tokens[token_index + 1] if token_index + 1 < len(tokens) else None
            stream_duplication = bool(
                previous
                and previous.kind == "redirection"
                and following
                and following.kind == "word"
                and following.value.isdigit()
            )
            if stream_duplication:
                segments[-1].append(token)
            elif segments[-1]:
                segments.append([])
            else:
                segments[-1].append(token)
        else:
            segments[-1].append(token)
    strongest = ("read_only", "shell command has no recognized delivery mutation")
    for segment in segments:
        if not segment:
            continue
        result = _classify_shell_segment(
            segment,
            dialect=dialect,
            cwd=cwd,
            depth=depth,
        )
        if result[0] == "mutation":
            return result
        if result[0] == "ambiguous":
            strongest = result
        elif result[0] == "state_control" and strongest[0] == "read_only":
            strongest = result
    return strongest


def classify_tool_mutation(payload: Mapping[str, Any]) -> tuple[str, str]:
    name = str(payload.get("tool_name", "")).casefold()
    if name in DIRECT_MUTATION_TOOLS:
        return "mutation", f"direct mutation tool {name}"
    if name not in SHELL_TOOLS:
        return "read_only", "tool is outside the supported mutation set"
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return "ambiguous", "shell tool input is missing"
    commands = [
        tool_input.get(key)
        for key in ("command", "cmd", "script")
        if key in tool_input
    ]
    if len(commands) != 1 or not isinstance(commands[0], str):
        return "ambiguous", "shell command input is missing or not uniquely structured"
    command = commands[0]
    if not command.strip():
        return "read_only", "empty shell command is inert"
    cwd_value = payload.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()
    dialect = (
        "powershell"
        if name in {"powershell", "shell_command", "functions.shell_command"}
        else name
    )
    return _classify_shell_command(command, dialect=dialect, cwd=cwd)


def is_mutation(payload: Mapping[str, Any]) -> bool:
    return classify_tool_mutation(payload)[0] == "mutation"


def _pending_for_mutation(payload: Mapping[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    if state is None or state["status"] == "completed" or (
        state["status"] == "blocked" and state["blocked_origin"] == "operator-abandon"
    ):
        return new_state(payload, "pending")
    if state["classification"] != "material":
        state.update(
            {
                "classification": "pending",
                "status": "pending_classification",
                "exempt_reason": None,
                "task_id": None,
                "paths_sha256": None,
            }
        )
    return state


def pre_tool(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    mutation_kind, mutation_detail = classify_tool_mutation(payload)
    if mutation_kind == "read_only":
        return response("PreToolUse", "Read-only tool path observed; no mutation epoch is reserved.")
    if mutation_kind == "state_control":
        return response(
            "PreToolUse",
            f"Lifecycle state-control observed; no delivery mutation epoch is reserved: {mutation_detail}.",
        )
    if mutation_kind == "ambiguous":
        return response(
            "PreToolUse",
            f"Ambiguous shell command is blocked before execution: {mutation_detail}.",
            block=True,
        )
    tool_id = payload.get("tool_use_id")
    if not isinstance(tool_id, str) or not tool_id:
        return response("PreToolUse", "Mutation-capable tool lacks a stable tool_use_id; gate fails closed.", block=True)
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        state = load_active(root, payload["session_id"], payload["turn_id"])
        state = _pending_for_mutation(payload, state)
        if state["status"] == "blocked":
            return response("PreToolUse", "Blocked material delivery must be explicitly abandoned before further mutation.", block=True)
        if state["classification"] != "material" or not state["task_id"] or not state["paths_sha256"]:
            save_active(root, state)
            return response(
                "PreToolUse",
                "Known mutation is blocked until the delivery is classified material with task_id and exact owned paths.",
                block=True,
            )
        if tool_id not in state["seen_tool_use_ids"] and tool_id not in state["inflight_tool_use_ids"]:
            state["inflight_tool_use_ids"] = state["inflight_tool_use_ids"] + [tool_id]
            save_active(root, state)
    return response("PreToolUse", "Supported local mutation reserved; coverage is not universal.")


def post_tool(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    mutation_kind, mutation_detail = classify_tool_mutation(payload)
    if mutation_kind == "read_only":
        return response("PostToolUse", "Read-only tool path did not change the mutation epoch.")
    if mutation_kind == "state_control":
        return response(
            "PostToolUse",
            f"Lifecycle state-control did not change the delivery mutation epoch: {mutation_detail}.",
        )
    if mutation_kind == "ambiguous":
        with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
            state = load_active(root, payload["session_id"], payload["turn_id"])
            state = _pending_for_mutation(payload, state)
            if state["classification"] == "material" and state.get("bundle_sha256"):
                state["status"] = "stale"
                state["stale_reason"] = f"ambiguous shell outcome: {mutation_detail}"
                state["receipt"] = None
            save_active(root, state)
        return response(
            "PostToolUse",
            "Ambiguous shell outcome is blocked without recording a successful mutation; "
            f"fresh verification is required: {mutation_detail}.",
            block=True,
        )
    tool_id = payload.get("tool_use_id")
    if not isinstance(tool_id, str) or not tool_id:
        return response("PostToolUse", "Mutation-capable tool lacks a stable tool_use_id; gate fails closed.", block=True)
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        state = load_active(root, payload["session_id"], payload["turn_id"])
        state = _pending_for_mutation(payload, state)
        if state["status"] == "blocked":
            if tool_id not in state["seen_tool_use_ids"]:
                state["seen_tool_use_ids"] = state["seen_tool_use_ids"] + [tool_id]
                state["mutation_epoch"] += 1
                save_active(root, state)
            return response("PostToolUse", "Mutation occurred after a blocked delivery; explicit abandon is required.", block=True)
        if state["classification"] != "material" or not state["task_id"] or not state["paths_sha256"]:
            if tool_id not in state["seen_tool_use_ids"]:
                state["seen_tool_use_ids"] = state["seen_tool_use_ids"] + [tool_id]
                state["mutation_epoch"] += 1
            save_active(root, state)
            return response(
                "PostToolUse",
                "Mutation bypassed material classification; delivery is pending and completion is blocked.",
                block=True,
            )
        if state["classification"] == "material":
            changed = False
            had_lease = tool_id in state["inflight_tool_use_ids"]
            unseen = tool_id not in state["seen_tool_use_ids"]
            if tool_id not in state["seen_tool_use_ids"]:
                state["seen_tool_use_ids"] = state["seen_tool_use_ids"] + [tool_id]
                state["mutation_epoch"] += 1
                changed = True
                if state["bundle_sha256"]:
                    state["status"] = "stale"
                    state["stale_reason"] = "managed mutation after freeze"
                    state["receipt"] = None
            if tool_id in state["inflight_tool_use_ids"]:
                state["inflight_tool_use_ids"] = [item for item in state["inflight_tool_use_ids"] if item != tool_id]
                changed = True
            if changed:
                save_active(root, state)
            if unseen and not had_lease:
                return response(
                    "PostToolUse",
                    "Mutation bypassed its PreToolUse lease; epoch was recorded and completion is blocked pending review.",
                    block=True,
                )
    return response("PostToolUse", "Supported local mutation recorded; coverage is not universal.")


def _require_reviewer_payload(payload: Mapping[str, Any]) -> str:
    agent_id = payload.get("agent_id")
    if payload.get("agent_type") != REVIEWER_TYPE or payload.get("model") != REVIEWER_MODEL:
        raise ValueError("reviewer type or model mismatch")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("reviewer agent_id is required")
    return agent_id


def subagent_start(payload: dict[str, Any], root: Path, profile_path: Path) -> dict[str, Any]:
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        try:
            state = load_active(root, payload["session_id"], payload["turn_id"])
            if not state or state["status"] != "reviewing" or not state["bundle_sha256"]:
                raise ValueError("no armed frozen delivery exists; no receipt will be accepted")
            agent_id = _require_reviewer_payload(payload)
            if profile_digest(profile_path) != state["profile_sha256"]:
                raise ValueError("reviewer profile digest changed after freeze")
            if state["reviewer_agent"] not in (None, agent_id):
                raise ValueError("review attempt is already bound to another agent")
            state["reviewer_agent"] = agent_id
            save_active(root, state)
            contract = {
                "schema_version": 1,
                "agent_id": agent_id,
                "agent_type": REVIEWER_TYPE,
                "model": REVIEWER_MODEL,
                "attempt_id": state["attempt_id"],
                "generation": state["generation"],
                "mutation_epoch": state["frozen_epoch"],
                "packet_sha256": state["packet_sha256"],
                "bundle_sha256": state["bundle_sha256"],
                "lens_sha256": state["lens_sha256"],
                "mandatory_lenses": list(MANDATORY_REVIEW_LENSES),
                "snapshot_sha256": state["snapshot_sha256"],
                "profile_sha256": state["profile_sha256"],
            }
            bundle = (root / "bundles" / state["bundle_sha256"]).resolve()
            return response(
                "SubagentStart",
                f"Review only immutable bundle {bundle} (bundle://{state['bundle_sha256']}/). Exact ReviewContractV1: {canonical_bytes(contract).decode('utf-8')}",
            )
        except (KeyError, TypeError, ValueError) as exc:
            return response("SubagentStart", f"Reviewer start rejected: {exc}", block=True)


def _pending_disposition_digest(state: Mapping[str, Any], output: Mapping[str, Any]) -> str:
    pending = {
        "schema_version": 1,
        "generation": state["generation"],
        "status": "pending",
        "finding_ids": [finding["id"] for finding in output["findings"]],
    }
    return compute_raw_sha256(canonical_bytes(pending))


def _make_receipt(state: Mapping[str, Any], disposition_sha256: str) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "delivery_id": state["delivery_id"],
        "generation": state["generation"],
        "reviewer_agent": state["reviewer_agent"],
        "reviewer_type": REVIEWER_TYPE,
        "reviewer_model": REVIEWER_MODEL,
        "config_sha256": state["profile_sha256"],
        "attempt_id": state["attempt_id"],
        "packet_sha256": state["packet_sha256"],
        "bundle_sha256": state["bundle_sha256"],
        "snapshot_sha256": state["snapshot_sha256"],
        "output_sha256": state["output_sha256"],
        "disposition_sha256": disposition_sha256,
        "mutation_epoch": state["frozen_epoch"],
    }
    return validate_review_receipt(receipt)


def _blocked_output_has_evidence(output: Mapping[str, Any]) -> bool:
    return bool(output.get("residual_risks")) or any(finding.get("evidence") for finding in output.get("findings", []))


def _immutable_evidence_context(
    state: Mapping[str, Any],
    root: Path,
) -> tuple[BundleStore, Any]:
    bundle_sha256 = state.get("bundle_sha256")
    if not isinstance(bundle_sha256, str):
        raise ValueError("active review bundle is unavailable for immutable evidence resolution")
    store = BundleStore(root / "bundles")
    try:
        snapshot = json.loads(store.read(bundle_sha256, "snapshot.json"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("frozen snapshot is malformed") from exc
    if not isinstance(snapshot, Mapping):
        raise ValueError("frozen snapshot is malformed")
    git_resolver = None
    if snapshot.get("kind") == "git":
        repository_root = snapshot.get("repo")
        if not isinstance(repository_root, str) or not repository_root:
            raise ValueError("frozen Git repository root is unavailable")
        git_resolver = build_local_git_resolver(Path(repository_root))
    return store, git_resolver


def _validate_disposition_state(
    state: Mapping[str, Any],
    root: Path,
    output: Mapping[str, Any],
) -> dict[str, Any]:
    store, git_resolver = _immutable_evidence_context(state, root)
    return validate_disposition_ledger(
        state["ledger"],
        output["findings"],
        generation=state["generation"],
        store=store,
        active_bundle_sha256=state["bundle_sha256"],
        git_resolver=git_resolver,
    )


def subagent_stop(payload: dict[str, Any], root: Path, profile_path: Path) -> dict[str, Any]:
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        try:
            state = load_active(root, payload["session_id"], payload["turn_id"])
            if not state or state["status"] != "reviewing":
                raise ValueError("no current review attempt")
            agent_id = _require_reviewer_payload(payload)
            if state["reviewer_agent"] != agent_id:
                raise ValueError("reviewer agent does not own this attempt")
            if profile_digest(profile_path) != state["profile_sha256"]:
                raise ValueError("reviewer profile digest changed after freeze")
            if state["mutation_epoch"] != state["frozen_epoch"] or state["inflight_tool_use_ids"]:
                raise ValueError("review snapshot is stale or a mutation remains in flight")
            output = validate_review_output(json.loads(payload.get("last_assistant_message") or ""))
            validate_lens_coverage(output["coverage"])
            store, git_resolver = _immutable_evidence_context(state, root)
            validate_finding_evidence(
                output["findings"],
                store=store,
                active_bundle_sha256=state["bundle_sha256"],
                git_resolver=git_resolver,
            )
            if output["attempt_id"] != state["attempt_id"] or output["attempt_id"] in state["consumed_attempt_ids"]:
                raise ValueError("review attempt is stale or replayed")
            for field in ("packet_sha256", "bundle_sha256", "snapshot_sha256"):
                if output[field] != state[field]:
                    raise ValueError(f"review {field} identity mismatch")
            if state["review_output"] is not None:
                raise ValueError("review output replay")
            if output["verdict"] == "blocked" and not _blocked_output_has_evidence(output):
                raise ValueError("blocked reviewer verdict requires persisted evidence")
            state["review_output"] = output
            state["output_sha256"] = compute_raw_sha256(canonical_bytes(output))
            state["pending_disposition_sha256"] = _pending_disposition_digest(state, output)
            state["receipt"] = _make_receipt(state, state["pending_disposition_sha256"])
            if output["verdict"] == "blocked":
                state["status"] = "blocked"
                state["blocked_origin"] = "reviewer"
                state["blocked_evidence_sha256"] = state["output_sha256"]
                save_active(root, state)
                return response(
                    "SubagentStop",
                    f"Reviewer blocked with persisted evidence. Only {BLOCKED_MARKER} Incomplete: ... may exit.",
                    block=True,
                )
            state["status"] = "receipted"
            save_active(root, state)
            return response("SubagentStop", "Review output accepted and a local pending-disposition receipt was created.")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return response("SubagentStop", f"Review output rejected: {exc}", block=True)


def _evidence_remaining(deadline: float, clock: Any) -> float:
    observed = clock()
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed):
        raise ValueError("review bundle evidence clock is invalid")
    remaining = deadline - observed
    if remaining <= 0:
        raise ValueError("review bundle evidence deadline exceeded")
    return remaining


def _bounded_git_blob(
    workspace: Path,
    specifier: str,
    *,
    max_bytes: int,
    deadline: float,
    clock: Any = time.monotonic,
) -> bytes:
    remaining = _evidence_remaining(deadline, clock)
    try:
        sized = subprocess.run(
            ["git", "cat-file", "-s", specifier],
            cwd=workspace,
            capture_output=True,
            check=False,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("review bundle evidence deadline exceeded") from exc
    if sized.returncode != 0:
        raise ValueError(f"Git object size failed: {specifier}")
    try:
        size = int(sized.stdout.decode("ascii", errors="strict").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Git object size is malformed: {specifier}") from exc
    if size < 0 or size > max_bytes:
        raise ValueError("review bundle evidence exceeds the remaining byte limit")
    remaining = _evidence_remaining(deadline, clock)
    try:
        result = subprocess.run(
            ["git", "show", specifier],
            cwd=workspace,
            capture_output=True,
            check=False,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("review bundle evidence deadline exceeded") from exc
    if result.returncode != 0:
        raise ValueError(f"Git object read failed: {specifier}")
    if len(result.stdout) != size or len(result.stdout) > max_bytes:
        raise ValueError("Git evidence size changed while freezing")
    return result.stdout


def _bounded_regular_file(
    candidate: Path,
    root: Path,
    *,
    max_bytes: int,
    deadline: float,
    clock: Any = time.monotonic,
) -> bytes:
    _evidence_remaining(deadline, clock)
    if candidate.is_symlink() or root not in candidate.resolve().parents:
        raise ValueError("worktree evidence path escaped while freezing")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    _evidence_remaining(deadline, clock)
    descriptor = os.open(candidate, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 0 or metadata.st_size > max_bytes:
            raise ValueError("worktree evidence exceeds the remaining byte limit")
        chunks: list[bytes] = []
        observed = 0
        while True:
            _evidence_remaining(deadline, clock)
            chunk = os.read(descriptor, min(1024 * 1024, metadata.st_size - observed + 1))
            _evidence_remaining(deadline, clock)
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > metadata.st_size or observed > max_bytes:
                raise ValueError("worktree evidence grew while freezing")
        if observed != metadata.st_size:
            raise ValueError("worktree evidence changed size while freezing")
        _evidence_remaining(deadline, clock)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _snapshot_source_bytes(
    workspace: Path,
    snapshot: Mapping[str, Any],
    source: str,
    path: str,
    *,
    max_bytes: int,
    deadline: float,
    clock: Any = time.monotonic,
) -> bytes:
    if source == "worktree":
        return _bounded_regular_file(
            workspace / Path(*PurePosixPath(path).parts),
            workspace,
            max_bytes=max_bytes,
            deadline=deadline,
            clock=clock,
        )
    if source == "index":
        return _bounded_git_blob(workspace, f":{path}", max_bytes=max_bytes, deadline=deadline, clock=clock)
    revision = str(snapshot[source])
    return _bounded_git_blob(
        workspace, f"{revision}:{path}", max_bytes=max_bytes, deadline=deadline, clock=clock
    )


def _bundle_evidence(
    workspace: Path,
    snapshot: Mapping[str, Any],
    *,
    deadline: float,
    clock: Any = time.monotonic,
) -> dict[str, bytes]:
    content: dict[str, bytes] = {}
    remaining_bytes = 10_000_000
    for item in snapshot["files"]:
        path = item["path"]
        for source in ("base", "head", "index", "worktree"):
            _evidence_remaining(deadline, clock)
            record = item[source]
            if not record["present"]:
                continue
            data = _snapshot_source_bytes(
                workspace,
                snapshot,
                source,
                path,
                max_bytes=remaining_bytes,
                deadline=deadline,
                clock=clock,
            )
            if compute_raw_sha256(data) != record["sha256"]:
                raise ValueError(f"{source} evidence changed while freezing {path}")
            content[f"evidence/{source}/{path}"] = data
            remaining_bytes -= len(data)
    return content


def _build_current_snapshot(state: Mapping[str, Any], root: Path, cwd: Path) -> dict[str, Any]:
    if digest(str(cwd.resolve())) != state["workspace_sha256"]:
        raise ValueError("Stop cwd does not match the frozen workspace")
    frozen = json.loads(BundleStore(root / "bundles").read(state["bundle_sha256"], "snapshot.json"))
    paths = [item["path"] for item in frozen["files"]]
    base = frozen["base"] if frozen["kind"] == "git" else None
    current = build_git_snapshot(cwd, paths, limits=SnapshotLimits(max_seconds=30.0), base=base)
    if current["snapshot_sha256"] != state["snapshot_sha256"]:
        raise ValueError("current task-owned snapshot differs from the reviewed snapshot")
    return current


def _verify_final_state(state: Mapping[str, Any], root: Path, cwd: Path, profile_path: Path) -> None:
    if state["mutation_epoch"] != state["frozen_epoch"] or state["inflight_tool_use_ids"]:
        raise ValueError("review mutation epoch is stale or a mutation is in flight")
    if profile_digest(profile_path) != state["profile_sha256"]:
        raise ValueError("reviewer profile digest changed after freeze")
    output = validate_review_output(state["review_output"])
    validate_lens_coverage(output["coverage"])
    if output["attempt_id"] != state["attempt_id"] or output["attempt_id"] in state["consumed_attempt_ids"]:
        raise ValueError("review attempt is stale or replayed")
    for field in ("packet_sha256", "bundle_sha256", "snapshot_sha256"):
        if output[field] != state[field]:
            raise ValueError(f"review output {field} mismatch")
    output_sha = compute_raw_sha256(canonical_bytes(output))
    if output_sha != state["output_sha256"]:
        raise ValueError("review output digest mismatch")
    ledger = _validate_disposition_state(state, root, output)
    disposition_sha = compute_raw_sha256(canonical_bytes(ledger))
    if disposition_sha != state["dispositions"]:
        raise ValueError("disposition digest mismatch")
    expected = _make_receipt({**state, "output_sha256": output_sha}, disposition_sha)
    actual = validate_review_receipt(state["receipt"])
    if actual != expected:
        raise ValueError("review receipt does not match current output, disposition, provenance, or epoch")
    _build_current_snapshot(state, root, cwd)


def _blocker_final_is_qualified(message: str) -> bool:
    lowered = message.casefold()
    return BLOCKED_MARKER in lowered and "incomplete" in lowered and SUCCESS_WORDS.search(message) is None


def stop(payload: dict[str, Any], root: Path, profile_path: Path) -> dict[str, Any]:
    with lock(session_lock(root, payload["session_id"], payload["turn_id"])):
        state = load_active(root, payload["session_id"], payload["turn_id"])
        if state is None:
            return response("Stop", "No persisted classification exists; gate fails closed.", block=True)
        if state["classification"] == "exempt":
            if not state["exempt_reason"]:
                return response("Stop", "Exemption lacks a recorded reason.", block=True)
            return response("Stop", "Adversarial review gate exempt with a recorded reason.")
        if state["status"] == "blocked":
            message = str(payload.get("last_assistant_message", ""))
            if not state["blocked_evidence_sha256"] or not _blocker_final_is_qualified(message):
                return response(
                    "Stop",
                    f"Blocked delivery may exit only as {BLOCKED_MARKER} Incomplete: ... and never as success.",
                    block=True,
                )
            return response("Stop", "Blocker-qualified incomplete exit allowed; delivery is not completed.")
        if state["status"] not in {"receipted", "completed"}:
            return response("Stop", "Delivery gate is incomplete or stale; refreeze and rereview before completion.", block=True)
        try:
            _verify_final_state(state, root, Path(str(payload["cwd"])), profile_path)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            detail = str(exc)
            if any(token in detail for token in ("snapshot", "mutation epoch", "mutation is in flight")):
                state["status"] = "stale"
                state["stale_reason"] = detail
                state["receipt"] = None
                save_active(root, state)
            return response("Stop", f"Delivery gate validation failed: {exc}", block=True)
        state["status"] = "completed"
        save_active(root, state)
        return response("Stop", "Delivery gate complete.")


def _git_head(
    workspace: Path,
    *,
    deadline: float,
    clock: Any = time.monotonic,
    runner: Any = subprocess.run,
) -> str | None:
    def run(*arguments: str) -> Any:
        remaining = _evidence_remaining(deadline, clock)
        try:
            result = runner(
                ["git", *arguments],
                cwd=workspace,
                capture_output=True,
                check=False,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("review bundle evidence deadline exceeded") from exc
        _evidence_remaining(deadline, clock)
        if not hasattr(result, "returncode") or not hasattr(result, "stdout"):
            raise ValueError("Git HEAD probe returned an invalid result")
        return result

    probe = run("rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != b"true":
        return None
    resolved = run("rev-parse", "--verify", "--end-of-options", "HEAD^{commit}")
    if resolved.returncode != 0:
        raise ValueError("Git HEAD resolution failed")
    try:
        head = resolved.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Git HEAD resolution is malformed") from exc
    try:
        validate_git_object_id(head, "Git HEAD resolution")
    except ValueError as exc:
        raise ValueError("Git HEAD resolution is malformed")
    return head


def _freeze(state: dict[str, Any], args: argparse.Namespace, root: Path, profile_path: Path) -> dict[str, Any]:
    if state["classification"] != "material" or state["status"] not in {"armed", "stale"}:
        raise ValueError("only armed or stale material delivery can freeze")
    if state["inflight_tool_use_ids"]:
        raise ValueError("cannot freeze while a managed mutation is in flight; reconcile the exact lease first")
    if digest("\n".join(sorted(args.paths))) != state["paths_sha256"]:
        raise ValueError("freeze paths differ from the classified owned paths")
    workspace = Path(args.cwd).resolve()
    profile_sha = profile_digest(profile_path)
    max_freeze_seconds = args.max_freeze_seconds
    if (
        isinstance(max_freeze_seconds, bool)
        or not isinstance(max_freeze_seconds, (int, float))
        or not math.isfinite(max_freeze_seconds)
        or not 1.0 <= max_freeze_seconds <= 300.0
    ):
        raise ValueError("max freeze seconds must be between 1 and 300")
    freeze_deadline = time.monotonic() + max_freeze_seconds
    verification = build_verification_evidence(
        args.verification_manifest,
        deadline=freeze_deadline,
    )
    review_paths = list(dict.fromkeys(args.paths))
    production_bytes: bytes | None = None
    production_sha: str | None = None
    if args.production_manifest:
        production_input = Path(args.production_manifest).expanduser()
        if not production_input.is_absolute():
            production_input = Path.cwd() / production_input
        if production_input.is_symlink():
            raise ValueError("production manifest must be a regular non-symlink file")
        production_path = production_input.resolve(strict=True)
        if not production_path.is_file():
            raise ValueError("production manifest must be a regular non-symlink file")
        if production_path != workspace and workspace not in production_path.parents:
            raise ValueError("production manifest must be inside the frozen workspace")
        production, production_bytes = load_production_manifest(
            production_path,
            deadline=freeze_deadline,
            clock=time.monotonic,
            return_bytes=True,
        )
        review_paths = list(dict.fromkeys([*review_paths, *production["review_paths"]]))
        production_sha = compute_raw_sha256(production_bytes)
    else:
        production_sha = None
    head = _git_head(workspace, deadline=freeze_deadline)
    _evidence_remaining(freeze_deadline, time.monotonic)
    snapshot = build_git_snapshot(
        workspace,
        review_paths,
        limits=SnapshotLimits(max_seconds=args.max_freeze_seconds),
        base=head,
        absolute_deadline=freeze_deadline,
    )
    attempt_id = uuid.uuid4().hex
    contract = {
        "schema_version": 1,
        "delivery_id": state["delivery_id"],
        "task_id": state["task_id"],
        "generation": state["generation"],
        "mutation_epoch": state["mutation_epoch"],
        "attempt_id": attempt_id,
        "paths_sha256": state["paths_sha256"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "profile_sha256": profile_sha,
        "verification_sha256": verification["sha256"],
        "production_manifest_sha256": production_sha,
    }
    lens_bytes = (HERE.parent / "references" / "review-lenses.md").read_bytes()
    lens_sha = compute_raw_sha256(lens_bytes)
    contract["lens_sha256"] = lens_sha
    contract["mandatory_lenses"] = list(MANDATORY_REVIEW_LENSES)
    if freeze_deadline <= time.monotonic():
        raise ValueError("snapshot limit exceeded")
    evidence = _bundle_evidence(workspace, snapshot, deadline=freeze_deadline)
    verification_files = {
        **verification["bundle_files"],
        "verification-evidence.json": verification["record_bytes"],
    }
    if production_bytes is not None:
        verification_files["production-manifest.json"] = production_bytes
    contract_bytes = canonical_bytes(contract)
    packet = {
        "schema_version": 1,
        "contract_sha256": compute_raw_sha256(contract_bytes),
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "generation": state["generation"],
        "mutation_epoch": state["mutation_epoch"],
        "attempt_id": attempt_id,
        "evidence": [
            {"path": name, "sha256": compute_raw_sha256(data)}
            for name, data in sorted({**evidence, **verification_files}.items())
        ],
        "lens_sha256": lens_sha,
        "mandatory_lenses": list(MANDATORY_REVIEW_LENSES),
        "verification_sha256": verification["sha256"],
        "production_manifest_sha256": production_sha,
    }
    packet_sha = compute_packet_sha256(packet)
    bundle = build_bundle(
        BundleStore(root / "bundles"),
        {
            **evidence,
            **verification_files,
            "snapshot.json": canonical_bytes(snapshot),
            "review-contract.json": contract_bytes,
            "review-packet.json": canonical_bytes(packet),
            "review-lenses.md": lens_bytes,
        },
    )
    state.update(
        {
            "status": "reviewing",
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "bundle_sha256": bundle["bundle_sha256"],
            "lens_sha256": lens_sha,
            "packet_sha256": packet_sha,
            "frozen_epoch": state["mutation_epoch"],
            "workspace_sha256": digest(str(workspace)),
            "profile_sha256": profile_sha,
            "attempt_id": attempt_id,
            "reviewer_agent": None,
            "review_output": None,
            "output_sha256": None,
            "pending_disposition_sha256": None,
            "dispositions": None,
            "ledger": None,
            "receipt": None,
            "blocked_evidence_sha256": None,
            "blocked_origin": None,
            "stale_reason": None,
        }
    )
    save_active(root, state)
    return state


def _accepted_generation(state: dict[str, Any], ledger: dict[str, Any], root: Path) -> dict[str, Any]:
    old = dict(state)
    old["ledger"] = ledger
    old["dispositions"] = compute_raw_sha256(canonical_bytes(ledger))
    old["receipt"] = None
    old["status"] = "stale"
    old["stale_reason"] = "accepted disposition requires a new generation"
    consumed = old["consumed_attempt_ids"] + [old["attempt_id"]]
    following = {
        **old,
        "generation": old["generation"] + 1,
        "consumed_attempt_ids": consumed,
        "snapshot_sha256": None,
        "bundle_sha256": None,
        "lens_sha256": None,
        "packet_sha256": None,
        "frozen_epoch": None,
        "workspace_sha256": None,
        "profile_sha256": None,
        "attempt_id": None,
        "reviewer_agent": None,
        "review_output": None,
        "output_sha256": None,
        "pending_disposition_sha256": None,
        "dispositions": None,
        "ledger": None,
        "receipt": None,
        "blocked_evidence_sha256": None,
        "blocked_origin": None,
    }
    journal_path = _rollover_path(root, old, int(following["generation"]))
    journal = {
        "schema_version": 1,
        "phase": "prepared",
        "session_id": old["session_id"],
        "delivery_id": old["delivery_id"],
        "from_generation": old["generation"],
        "to_generation": following["generation"],
        "previous": old,
        "next": following,
    }
    save(journal_path, journal)
    _fault("rollover_after_prepare")
    save(delivery_path(root, old), old)
    _fault("rollover_after_old")
    save(delivery_path(root, following), following)
    _fault("rollover_after_new")
    save_active(root, following)
    _fault("rollover_after_pointer")
    save(journal_path, {**journal, "phase": "completed"})
    return following


def _validated_bundle_manifest(root: Path, bundle_sha256: str) -> str:
    directory = root / "bundles" / bundle_sha256
    manifest_path = directory / "manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or compute_packet_sha256(manifest) != bundle_sha256:
        raise ValueError("frozen bundle manifest identity mismatch")
    actual = set()
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if relative != "manifest.json":
            actual.add(relative)
    if actual != set(manifest):
        raise ValueError("frozen bundle file set mismatch")
    store = BundleStore(root / "bundles")
    for name in manifest:
        store.read(bundle_sha256, name)
    return compute_raw_sha256(raw)


def export_replay(state: Mapping[str, Any], root: Path, profile_path: Path) -> dict[str, Any]:
    """Export validated gate authority without mutating lifecycle state."""
    if state.get("status") not in {"receipted", "completed"}:
        raise ValueError("only a receipted or completed review can be exported")
    if state.get("mutation_epoch") != state.get("frozen_epoch") or state.get("inflight_tool_use_ids"):
        raise ValueError("stale or in-flight review cannot be exported")
    profile_sha = profile_digest(profile_path)
    if profile_sha != state.get("profile_sha256"):
        raise ValueError("reviewer profile digest changed after freeze")
    output = validate_review_output(state.get("review_output"))
    validate_lens_coverage(output["coverage"])
    output_sha = compute_raw_sha256(canonical_bytes(output))
    if output_sha != state.get("output_sha256"):
        raise ValueError("review output digest mismatch")
    for field in ("attempt_id", "packet_sha256", "bundle_sha256", "snapshot_sha256"):
        if output[field] != state.get(field):
            raise ValueError(f"review output {field} mismatch")
    receipt = validate_review_receipt(state.get("receipt"))
    if state.get("ledger") is None:
        if state.get("dispositions") is not None:
            raise ValueError("pending review has an unexpected disposition digest")
        disposition_sha = state.get("pending_disposition_sha256")
    else:
        ledger = _validate_disposition_state(state, root, output)
        disposition_sha = compute_raw_sha256(canonical_bytes(ledger))
        if disposition_sha != state.get("dispositions"):
            raise ValueError("persisted disposition ledger digest mismatch")
    if receipt.get("disposition_sha256") != disposition_sha:
        raise ValueError("review receipt disposition digest mismatch")
    if receipt != _make_receipt(state, disposition_sha):
        raise ValueError("review receipt does not bind persisted lifecycle state")

    store = BundleStore(root / "bundles")
    snapshot = json.loads(store.read(state["bundle_sha256"], "snapshot.json"))
    contract = json.loads(store.read(state["bundle_sha256"], "review-contract.json"))
    packet = json.loads(store.read(state["bundle_sha256"], "review-packet.json"))
    lens = store.read(state["bundle_sha256"], "review-lenses.md")
    if snapshot.get("snapshot_sha256") != state["snapshot_sha256"]:
        raise ValueError("frozen snapshot identity mismatch")
    if (
        contract.get("attempt_id") != state["attempt_id"]
        or contract.get("snapshot_sha256") != state["snapshot_sha256"]
        or contract.get("profile_sha256") != profile_sha
        or contract.get("generation") != state["generation"]
        or contract.get("mutation_epoch") != state["frozen_epoch"]
    ):
        raise ValueError("frozen review contract identity mismatch")
    if compute_packet_sha256(packet) != state["packet_sha256"]:
        raise ValueError("frozen review packet identity mismatch")
    if packet.get("lens_sha256") != compute_raw_sha256(lens) or packet.get("snapshot_sha256") != state["snapshot_sha256"]:
        raise ValueError("frozen packet content mismatch")
    manifest_sha = _validated_bundle_manifest(root, state["bundle_sha256"])
    persisted = delivery_path(root, state)
    state_raw = _filesystem_path(persisted).read_bytes()
    if json.loads(state_raw) != state:
        raise ValueError("persisted lifecycle state differs from active state")
    return {
        "schema_version": 1,
        "authority": "lifecycle_gate_export_v1",
        "session_id": state["session_id"],
        "turn_id": state["turn_id"],
        "task_id": state["task_id"],
        "delivery_id": state["delivery_id"],
        "generation": state["generation"],
        "state_relative_path": _relative_state(root, persisted),
        "state_sha256": compute_raw_sha256(state_raw),
        "bundle_sha256": state["bundle_sha256"],
        "bundle_manifest_sha256": manifest_sha,
        "profile_sha256": profile_sha,
        "output_sha256": output_sha,
        "review_output": output,
        "receipt": receipt,
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value is not allowed: {value}")


def _parse_disposition_bytes(raw: bytes, source: str) -> Mapping[str, Any]:
    if len(raw) > MAX_DISPOSITION_BYTES:
        raise ValueError(
            f"DispositionLedgerV1 {source} exceeds the maximum of {MAX_DISPOSITION_BYTES} bytes"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"DispositionLedgerV1 {source} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"DispositionLedgerV1 {source} is malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError("DispositionLedgerV1 must be a JSON object")
    return value


def _read_disposition_file(path: Path) -> bytes:
    resolved = _filesystem_path(path)
    with open(resolved, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("DispositionLedgerV1 --file must identify a regular file")
        if before.st_size > MAX_DISPOSITION_BYTES:
            raise ValueError(
                f"DispositionLedgerV1 file exceeds the maximum of {MAX_DISPOSITION_BYTES} bytes"
            )
        raw = handle.read(MAX_DISPOSITION_BYTES + 1)
        after = os.fstat(handle.fileno())
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in identity):
        raise ValueError("DispositionLedgerV1 file changed while it was read")
    return raw


def _load_disposition_input(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.file is not None:
        return _parse_disposition_bytes(_read_disposition_file(args.file), "file")
    if args.json is not None:
        return _parse_disposition_bytes(args.json.encode("utf-8"), "inline JSON")
    if args.stdin:
        return _parse_disposition_bytes(
            sys.stdin.buffer.read(MAX_DISPOSITION_BYTES + 1),
            "stdin",
        )
    raise ValueError("DispositionLedgerV1 input source is required")


def cli(args: argparse.Namespace, root: Path, profile_path: Path) -> int:
    if args.action == "health":
        profile_sha = profile_digest(profile_path)
        print(json.dumps({"ok": True, "profile_sha256": profile_sha, "state_addressing": "session/task/delivery/generation"}, sort_keys=True))
        return 0
    disposition_input = _load_disposition_input(args) if args.action == "disposition" else None
    with lock(session_lock(root, args.session_id, args.turn_id)):
        state = load_active(root, args.session_id, args.turn_id)
        if args.action == "classify":
            if state is None:
                state = new_state({"session_id": args.session_id, "turn_id": args.turn_id}, "pending")
            if state["classification"] == "material" and state["status"] != "pending_classification":
                if args.classification != "material" or state["task_id"] != args.task_id or state["paths_sha256"] != digest("\n".join(sorted(args.paths))):
                    raise ValueError("material classification is immutable")
            elif args.classification == "exempt":
                if not args.reason or not args.reason.strip():
                    raise ValueError("exempt classification requires a recorded reason")
                state.update({"classification": "exempt", "status": "exempt", "exempt_reason": args.reason.strip()})
            else:
                if not args.task_id or not args.paths:
                    raise ValueError("material classification requires task_id and owned paths")
                state.update(
                    {
                        "classification": "material",
                        "status": "armed",
                        "task_id": args.task_id,
                        "paths_sha256": digest("\n".join(sorted(args.paths))),
                        "exempt_reason": None,
                    }
                )
            save_active(root, state)
        elif args.action == "freeze":
            if state is None:
                raise ValueError("delivery not found")
            state = _freeze(state, args, root, profile_path)
        elif args.action == "disposition":
            if not state or state["status"] != "receipted" or not state["review_output"] or not state["receipt"]:
                raise ValueError("current review output and local receipt are required")
            ledger = disposition_input
            store, git_resolver = _immutable_evidence_context(state, root)
            ledger = validate_disposition_ledger(
                ledger,
                state["review_output"]["findings"],
                generation=state["generation"],
                store=store,
                active_bundle_sha256=state["bundle_sha256"],
                git_resolver=git_resolver,
            )
            if any(item["decision"] == "accepted" for item in ledger["dispositions"]):
                state = _accepted_generation(state, ledger, root)
            else:
                state["ledger"] = ledger
                state["dispositions"] = compute_raw_sha256(canonical_bytes(ledger))
                state["receipt"] = _make_receipt(state, state["dispositions"])
                save_active(root, state)
        elif args.action == "block":
            if not state or not args.evidence or not args.evidence.strip():
                raise ValueError("explicit blocked evidence required")
            state["status"] = "blocked"
            state["blocked_origin"] = "operator"
            state["blocked_evidence_sha256"] = digest(args.evidence.strip())
            state["receipt"] = None
            save_active(root, state)
        elif args.action == "reconcile":
            if not state or state["classification"] != "material":
                raise ValueError("material delivery is required to reconcile a mutation lease")
            if not args.evidence or not args.evidence.strip():
                raise ValueError("confirmed failed-tool evidence is required")
            if args.tool_use_id not in state["inflight_tool_use_ids"]:
                raise ValueError("the exact mutation lease is not in flight")
            state["inflight_tool_use_ids"] = [item for item in state["inflight_tool_use_ids"] if item != args.tool_use_id]
            if args.tool_use_id not in state["seen_tool_use_ids"]:
                state["seen_tool_use_ids"] = state["seen_tool_use_ids"] + [args.tool_use_id]
            state["mutation_epoch"] += 1
            if state["bundle_sha256"]:
                state["status"] = "stale"
                state["stale_reason"] = f"failed mutation reconciled with evidence sha256={digest(args.evidence.strip())}"
                state["receipt"] = None
            save_active(root, state)
        elif args.action == "abort":
            if not state or state["classification"] not in {"pending", "material"}:
                raise ValueError("an unresolved delivery is required for abort")
            if not args.evidence or not args.evidence.strip():
                raise ValueError("abort evidence is required")
            if args.scope == "reviewer":
                if state["classification"] != "material" or not state["attempt_id"] or args.attempt_id != state["attempt_id"]:
                    raise ValueError("the exact active reviewer attempt is required")
                if state["attempt_id"] in state["consumed_attempt_ids"]:
                    raise ValueError("reviewer attempt was already consumed")
                state["consumed_attempt_ids"] = state["consumed_attempt_ids"] + [state["attempt_id"]]
                state["mutation_epoch"] += 1
                state["status"] = "stale"
                state["stale_reason"] = f"reviewer aborted with evidence sha256={digest(args.evidence.strip())}"
                state["reviewer_agent"] = None
                state["review_output"] = None
                state["output_sha256"] = None
                state["pending_disposition_sha256"] = None
                state["dispositions"] = None
                state["ledger"] = None
                state["receipt"] = None
            else:
                if state["attempt_id"] and state["attempt_id"] not in state["consumed_attempt_ids"]:
                    state["consumed_attempt_ids"] = state["consumed_attempt_ids"] + [state["attempt_id"]]
                state["mutation_epoch"] += 1
                state["status"] = "blocked"
                state["blocked_origin"] = "operator-abandon"
                state["blocked_evidence_sha256"] = digest(args.evidence.strip())
                state["stale_reason"] = "authorized delivery abandon"
                state["receipt"] = None
            save_active(root, state)
        elif args.action == "export-replay":
            if not state:
                raise ValueError("delivery not found")
            print(json.dumps(export_replay(state, root, profile_path), sort_keys=True, separators=(",", ":")))
            return 0
        elif args.action != "status":
            raise ValueError("unsupported lifecycle action")
        if not state:
            raise ValueError("delivery not found")
        print(json.dumps(state, sort_keys=True, separators=(",", ":")))
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=default_root())
    parser.add_argument("--profile-path", type=Path, default=default_profile())
    subparsers = parser.add_subparsers(dest="action")
    for action in ("classify", "freeze", "disposition", "status", "block", "reconcile", "abort", "export-replay"):
        item = subparsers.add_parser(action)
        item.add_argument("--session-id", required=True)
        item.add_argument("--turn-id", required=True)
        if action == "classify":
            item.add_argument("--classification", choices=("exempt", "material"), required=True)
            item.add_argument("--task-id")
            item.add_argument("--paths", nargs="*", default=[])
            item.add_argument("--reason")
        if action == "freeze":
            item.add_argument("--cwd", required=True)
            item.add_argument("--paths", nargs="+", required=True)
            item.add_argument("--verification-manifest", required=True)
            item.add_argument("--production-manifest")
            item.add_argument("--max-freeze-seconds", type=float, default=180.0)
        if action == "disposition":
            source = item.add_mutually_exclusive_group(required=True)
            source.add_argument("--file", type=Path)
            source.add_argument("--json")
            source.add_argument("--stdin", action="store_true")
        if action == "block":
            item.add_argument("--evidence", required=True)
        if action == "reconcile":
            item.add_argument("--tool-use-id", required=True)
            item.add_argument("--evidence", required=True)
        if action == "abort":
            item.add_argument("--scope", choices=("reviewer", "delivery"), required=True)
            item.add_argument("--attempt-id")
            item.add_argument("--evidence", required=True)
    subparsers.add_parser("health")
    args = parser.parse_args()
    state_root = _filesystem_path(args.state_root)
    if args.action:
        try:
            return cli(args, state_root, args.profile_path)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": "lifecycle gate operational failure", "detail": str(exc)}), file=sys.stderr)
            return 2
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return 2
    event = payload.get("hook_event_name")
    handlers = {
        "UserPromptSubmit": lambda: prompt(payload, state_root),
        "PreToolUse": lambda: pre_tool(payload, state_root),
        "PostToolUse": lambda: post_tool(payload, state_root),
        "SubagentStart": lambda: subagent_start(payload, state_root, args.profile_path),
        "SubagentStop": lambda: subagent_stop(payload, state_root, args.profile_path),
        "Stop": lambda: stop(payload, state_root, args.profile_path),
    }
    if event in handlers:
        try:
            print(json.dumps(handlers[event](), separators=(",", ":")))
        except Exception as exc:
            print(json.dumps(response(str(event), f"Lifecycle gate operational failure: {exc}", block=True), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
