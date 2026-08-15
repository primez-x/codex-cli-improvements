"""Transactional installer for the managed Codex orchestration package.

The explicit handler-contract smoke exercises legacy lifecycle scripts. It is
optional and cannot prove that a running Codex process loaded or trusted hooks.
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verification_evidence import load_production_manifest  # noqa: E402


MANAGED_EVENTS = (
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)
RUNTIME_NAMES = {
    ".git",
    ".superpowers",
    "cache",
    "hooks/state",
    "logs",
    "memories",
    "sessions",
    "state",
    "tmp",
}
CREDENTIAL_TOKENS = (".env", "credential", "id_rsa", "private-key", "secret", "token")
INSTALLABLE_VALIDATORS = {
    "skills/delivery-orchestration/scripts/test_routing_policy.py",
    "skills/instruction-learning-loop/scripts/test_global_autonomy_contract.py",
    "skills/instruction-learning-loop/scripts/test_instruction_learning.py",
    "skills/plan-review-ladder/scripts/test_packet_integrity.py",
    "skills/plan-review-ladder/scripts/test_plan_routing.py",
}
BEGIN = "<!-- BEGIN MANAGED ADVERSARIAL DELIVERY GATE -->"
END = "<!-- END MANAGED ADVERSARIAL DELIVERY GATE -->"
TRANSACTION_ID = re.compile(r"[0-9a-f]{32}\Z")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LIFECYCLE_GATE_PATH = "skills/adversarial-code-review/scripts/lifecycle_gate.py"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MANAGED_SKILL_PATH = "./skills/adversarial-code-review/SKILL.md"
SEMANTIC_DESTINATIONS = frozenset({"AGENTS.md", "config.toml", "hooks.json"})
_TABLE_PROBE = "__codex_installer_table_probe_7f44b7a5__"
_IDENTITY_UNSET = object()


# This strict manifest is the sole production-input authority for both install
# and immutable review. Tests and runtime state cannot enter by recursion.
PRODUCTION_MANIFEST_PATH = HERE.parent / "references" / "production-manifest.json"
PRODUCTION_MANIFEST = load_production_manifest(PRODUCTION_MANIFEST_PATH)
COPY_MANIFEST = tuple(PRODUCTION_MANIFEST["copy_paths"])
PRODUCTION_REVIEW_PATHS = tuple(PRODUCTION_MANIFEST["review_paths"])
SEMANTIC_SOURCE_INPUTS = tuple(
    (item["path"], item["role"]) for item in PRODUCTION_MANIFEST["semantic_inputs"]
)
if SEMANTIC_SOURCE_INPUTS != (
    ("config.toml", "codex_config_source"),
    ("hooks.json", "hook_config_source"),
    ("AGENTS.md", "global_agents_source"),
):
    raise ValueError("production manifest does not match installer semantic source inputs")
MANAGED_ROOTS = {
    "skills/adversarial-code-review": {
        path for path in COPY_MANIFEST if path.startswith("skills/adversarial-code-review/")
    },
}
STALE_MANAGED_FILES = {
    "skills/adversarial-code-review/references/evaluation-candidate-results.json",
    "skills/adversarial-code-review/scripts/packet_integrity.py",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def die(message: str) -> None:
    raise ValueError(message)


def _lexical_absolute(value: str | os.PathLike[str], label: str) -> Path:
    raw = Path(value).expanduser()
    if ".." in raw.parts:
        die(f"{label} must not contain traversal")
    path = raw if raw.is_absolute() else Path.cwd() / raw
    path = Path(os.path.abspath(path))
    if path.parent == path:
        die(f"{label} must not be a filesystem root")
    return path


def _filesystem_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    absolute = os.path.abspath(value)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _metadata_is_reparse(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_attribute)


def _is_reparse(path: Path) -> bool:
    metadata = _lstat(path)
    if metadata is None:
        return False
    if _metadata_is_reparse(metadata):
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _reject_reparse_chain(path: Path, label: str) -> None:
    chain = [path, *path.parents]
    for candidate in reversed(chain):
        if _is_reparse(candidate):
            die(f"{label} has a symlink or reparse-point ancestor: {candidate}")


def _leaf_identity(metadata: os.stat_result) -> dict[str, int]:
    return {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
        "mode": int(metadata.st_mode),
        "file_attributes": int(getattr(metadata, "st_file_attributes", 0)),
    }


def _reject_managed_leaf_reparse(home: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    target = home.joinpath(*safe.parts)
    _reject_reparse_chain(target.parent, f"path {relative}")
    if _is_reparse(target):
        die(f"managed destination leaf is a symlink or reparse point: {relative}")
    return _contained(home, relative)


def _reject_managed_leaf_reparses(home: Path, relatives: Iterable[str]) -> None:
    for relative in sorted(set(relatives)):
        _reject_managed_leaf_reparse(home, relative)


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts or not path.parts:
        die(f"unsafe manifest path: {value}")
    if any(part in {"", "."} for part in path.parts):
        die(f"unsafe manifest path: {value}")
    return path


def _contained(root: Path, relative: str, *, existing: bool = False) -> Path:
    safe = _safe_relative(relative)
    target = root.joinpath(*safe.parts)
    _reject_reparse_chain(target if existing else target.parent, f"path {relative}")
    resolved_root = root.resolve(strict=True)
    resolved = target.resolve(strict=existing)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        die(f"path escapes root: {relative}")
    return target


def roots(args: argparse.Namespace) -> tuple[Path, Path]:
    source_lexical = _lexical_absolute(args.source_root, "source-root")
    home_value = args.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
    home_lexical = _lexical_absolute(home_value, "codex-home")
    _reject_reparse_chain(source_lexical, "source-root")
    _reject_reparse_chain(home_lexical, "codex-home")
    if not source_lexical.is_dir() or not home_lexical.is_dir():
        die("source-root and codex-home must already exist as directories")
    source = source_lexical.resolve(strict=True)
    home = home_lexical.resolve(strict=True)
    if source == home or source in home.parents or home in source.parents:
        die("source-root and codex-home must be distinct non-overlapping directories")
    if not (source / "skills" / "adversarial-code-review" / "SKILL.md").is_file():
        die("source root lacks adversarial-code-review skill")
    return source, home


def _is_runtime_path(relative: PurePosixPath) -> bool:
    folded = [part.casefold() for part in relative.parts]
    if _is_generated_cache_path(relative):
        return False  # Generated locally and explicitly omitted, never copied.
    joined = "/".join(folded)
    return any(name == joined or name in folded for name in RUNTIME_NAMES)


def _is_generated_cache_path(relative: str | PurePosixPath) -> bool:
    path = PurePosixPath(relative)
    folded = [part.casefold() for part in path.parts]
    return "__pycache__" in folded or path.name.casefold().endswith((".pyc", ".pyo"))


def validate_source(source: Path) -> None:
    source_manifest = load_production_manifest(
        _contained(
            source,
            "skills/adversarial-code-review/references/production-manifest.json",
            existing=True,
        )
    )
    if source_manifest != PRODUCTION_MANIFEST:
        die("source production manifest differs from the executing installer authority")
    expected = set(COPY_MANIFEST)
    for relative in sorted(expected):
        path = _contained(source, relative, existing=True)
        if not path.is_file():
            die(f"required production source is missing: {relative}")
        lowered = path.name.casefold()
        if any(token in lowered for token in CREDENTIAL_TOKENS):
            die(f"credential-like source rejected: {relative}")
        if (
            path.name.startswith("test_")
            and relative not in INSTALLABLE_VALIDATORS
        ) or _is_runtime_path(PurePosixPath(relative)):
            die(f"non-production source rejected: {relative}")

    # Runtime and credential material inside a managed skill is a boundary
    # error even when the explicit manifest would otherwise omit it.
    for managed_root in MANAGED_ROOTS:
        root = _contained(source, managed_root, existing=True)
        for candidate in root.rglob("*"):
            if "__pycache__" in candidate.parts:
                continue
            relative = PurePosixPath(candidate.relative_to(source).as_posix())
            if _is_reparse(candidate):
                die(f"symlink source rejected: {relative.as_posix()}")
            if _is_runtime_path(relative):
                die(f"runtime/scratch source rejected: {relative.as_posix()}")
            if candidate.is_file() and any(token in candidate.name.casefold() for token in CREDENTIAL_TOKENS):
                die(f"credential-like source rejected: {relative.as_posix()}")

    # Parse all authoritative source formats before producing a preview.
    source_config(source)
    managed_hook_contracts(source)


def source_files(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for relative in COPY_MANIFEST:
        path = _contained(source, relative, existing=True)
        files[relative] = path.read_bytes()
    return files


def source_config(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        value = tomllib.loads((source / "config.toml").read_text(encoding="utf-8"))
        agent = value["agents"]["sol_reviewer"]
        skills = value["skills"]["config"]
    except (KeyError, OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise ValueError("unsupported source config format") from exc
    desired = [entry for entry in skills if entry.get("path") == "./skills/adversarial-code-review/SKILL.md"]
    if len(desired) != 1 or desired[0] != {
        "path": "./skills/adversarial-code-review/SKILL.md",
        "enabled": True,
    }:
        die("source config has no exact adversarial skill registration")
    if agent != {
        "description": "On-demand read-only Sol reviewer for root-prepared consequential delivery evidence packets.",
        "config_file": "./agents/sol_reviewer.toml",
    }:
        die("source config has no exact sol_reviewer registration")
    return dict(agent), dict(desired[0])


def _table_header_identity(header: str) -> tuple[tuple[str, ...], bool]:
    """Return a parsed TOML table path without trusting raw header spelling."""
    try:
        parsed = tomllib.loads(f"{header}\n{_TABLE_PROBE} = true\n")
    except tomllib.TOMLDecodeError as exc:
        raise ValueError("unsupported TOML table header") from exc
    found: list[tuple[str, ...]] = []

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            if value.get(_TABLE_PROBE) is True:
                found.append(path)
            for key, child in value.items():
                if key == _TABLE_PROBE:
                    continue
                if isinstance(child, list):
                    for item in child:
                        visit(item, (*path, str(key)))
                else:
                    visit(child, (*path, str(key)))

    visit(parsed, ())
    if len(found) != 1:
        die("unsupported TOML table header")
    return found[0], header.startswith("[[")


def _header_at_line_start(line: str) -> str | None:
    """Recognize one complete table header, excluding comments and value arrays."""
    body = line.rstrip("\r\n")
    start = 0
    while start < len(body) and body[start] in " \t":
        start += 1
    if start >= len(body) or body[start] != "[":
        return None
    array = body.startswith("[[", start)
    index = start + (2 if array else 1)
    quote: str | None = None
    escaped = False
    end: int | None = None
    while index < len(body):
        character = body[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
            index += 1
            continue
        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
            index += 1
            continue
        if array and body.startswith("]]", index):
            end = index + 2
            break
        if not array and character == "]":
            end = index + 1
            break
        index += 1
    if end is None or quote is not None:
        return None
    remainder = body[end:].lstrip(" \t")
    if remainder and not remainder.startswith("#"):
        return None
    header = body[start:end]
    try:
        _table_header_identity(header)
    except ValueError:
        return None
    return header


def _scan_toml_line(
    line: str,
    multiline: str | None,
    square_depth: int,
    curly_depth: int,
) -> tuple[str | None, int, int]:
    """Track TOML string and collection context across physical lines."""
    index = 0
    while index < len(line):
        if multiline is not None:
            delimiter = '"' if multiline == "basic" else "'"
            if multiline == "basic" and line[index] == "\\":
                index += 2
                continue
            if line[index] == delimiter:
                run_end = index
                while run_end < len(line) and line[run_end] == delimiter:
                    run_end += 1
                if run_end - index >= 3:
                    multiline = None
                    index = run_end
                    continue
                index = run_end
                continue
            index += 1
            continue

        character = line[index]
        if character == "#":
            break
        if line.startswith('\"\"\"', index):
            multiline = "basic"
            index += 3
            continue
        if line.startswith("'''", index):
            multiline = "literal"
            index += 3
            continue
        if character == '"':
            index += 1
            while index < len(line):
                if line[index] == "\\":
                    index += 2
                elif line[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
            continue
        if character == "'":
            closing = line.find("'", index + 1)
            index = len(line) if closing < 0 else closing + 1
            continue
        if character == "[":
            square_depth += 1
        elif character == "]":
            square_depth = max(0, square_depth - 1)
        elif character == "{":
            curly_depth += 1
        elif character == "}":
            curly_depth = max(0, curly_depth - 1)
        index += 1
    return multiline, square_depth, curly_depth


def _table_segments(text: str) -> tuple[str, list[tuple[str, str]]]:
    matches: list[tuple[int, str]] = []
    offset = 0
    multiline: str | None = None
    square_depth = 0
    curly_depth = 0
    for line in text.splitlines(keepends=True):
        if multiline is None and square_depth == 0 and curly_depth == 0:
            header = _header_at_line_start(line)
            if header is not None:
                matches.append((offset, header))
        multiline, square_depth, curly_depth = _scan_toml_line(
            line,
            multiline,
            square_depth,
            curly_depth,
        )
        offset += len(line)
    if not matches:
        return text, []
    prefix = text[:matches[0][0]]
    segments: list[tuple[str, str]] = []
    for index, (start, header) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        segments.append((header, text[start:end]))
    return prefix, segments


def _managed_config_segments(
    text: str,
    parsed: Mapping[str, Any],
) -> tuple[str, list[tuple[str, str, bool]]]:
    """Bind real lexical AoT spans to their parsed ordinal and path owner."""
    prefix, segments = _table_segments(text)
    skills = parsed.get("skills")
    configured_skills = skills.get("config", []) if isinstance(skills, Mapping) else []
    if not isinstance(configured_skills, list):
        configured_skills = []
    skill_ordinal = 0
    classified: list[tuple[str, str, bool]] = []
    for header, segment in segments:
        identity = _table_header_identity(header)
        managed = identity == (("agents", "sol_reviewer"), False)
        if identity == (("skills", "config"), True):
            if skill_ordinal >= len(configured_skills):
                die("TOML array-table spans disagree with parsed skills.config")
            entry = configured_skills[skill_ordinal]
            managed = isinstance(entry, Mapping) and entry.get("path") == MANAGED_SKILL_PATH
            skill_ordinal += 1
        classified.append((header, segment, managed))
    if skill_ordinal != len(configured_skills):
        die("TOML array-table spans disagree with parsed skills.config")
    return prefix, classified


def _source_config_segments(source: Path) -> tuple[str, str]:
    text = (source / "config.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    _, segments = _managed_config_segments(text, parsed)
    agent = [
        segment
        for header, segment, managed in segments
        if managed and _table_header_identity(header) == (("agents", "sol_reviewer"), False)
    ]
    skill = [
        segment
        for header, segment, managed in segments
        if managed and _table_header_identity(header) == (("skills", "config"), True)
    ]
    if len(agent) != 1 or len(skill) != 1:
        die("source config managed segments are ambiguous")
    return agent[0].strip(), skill[0].strip()


def _config_managed_exact(value: Mapping[str, Any], source: Path) -> bool:
    agent, skill = source_config(source)
    actual_agent = value.get("agents", {}).get("sol_reviewer")
    actual_skills = [
        entry
        for entry in value.get("skills", {}).get("config", [])
        if isinstance(entry, Mapping) and entry.get("path") == skill["path"]
    ]
    return actual_agent == agent and actual_skills == [skill]


def _unmanaged_config(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(dict(value))
    agents = projected.get("agents")
    if isinstance(agents, dict):
        agents.pop("sol_reviewer", None)
        if not agents:
            projected.pop("agents", None)
    skills = projected.get("skills")
    if isinstance(skills, dict):
        entries = skills.get("config")
        if isinstance(entries, list):
            skills["config"] = [
                entry
                for entry in entries
                if not (isinstance(entry, Mapping) and entry.get("path") == MANAGED_SKILL_PATH)
            ]
            if not skills["config"]:
                skills.pop("config", None)
        if not skills:
            projected.pop("skills", None)
    return projected


def config_text(existing: bytes, source: Path) -> bytes:
    text = existing.decode("utf-8") if existing else ""
    try:
        parsed = tomllib.loads(text) if text.strip() else {}
    except tomllib.TOMLDecodeError as exc:
        raise ValueError("unsupported destination config format") from exc
    if _config_managed_exact(parsed, source):
        return existing
    prefix, segments = _managed_config_segments(text, parsed)
    kept = [segment for _, segment, managed in segments if not managed]
    newline = "\r\n" if b"\r\n" in existing else "\n"
    agent_segment, skill_segment = _source_config_segments(source)
    retained = prefix + "".join(kept)
    if not retained:
        separator = ""
    elif retained.endswith(("\r\n\r\n", "\n\n")):
        separator = ""
    elif retained.endswith(("\r", "\n")):
        separator = newline
    else:
        separator = newline + newline
    managed = (newline + newline).join(
        segment.replace("\r\n", "\n").replace("\n", newline)
        for segment in (agent_segment, skill_segment)
    )
    encoded = (retained + separator + managed.rstrip("\r\n") + newline).encode("utf-8")
    try:
        candidate = tomllib.loads(encoded.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError("managed config merge produced invalid TOML") from exc
    if not _config_managed_exact(candidate, source):
        die("managed config merge failed semantic equality")
    if _unmanaged_config(candidate) != _unmanaged_config(parsed):
        die("managed config merge changed unmanaged values")
    return encoded


_MANAGED_HOOK_PARTS = {
    "plan-gap": ("hooks", "plan_gap_goal_hook.py"),
    "instruction-learning": (
        "skills",
        "instruction-learning-loop",
        "scripts",
        "instruction_learning_hook.py",
    ),
    "adversarial-lifecycle": (
        "skills",
        "adversarial-code-review",
        "scripts",
        "lifecycle_gate.py",
    ),
}


def _managed_dispatcher_commands() -> dict[str, str]:
    commands: dict[str, str] = {}
    prefix = (
        "import os, runpy; runpy.run_path(os.path.join("
        "os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex'), "
    )
    suffix = "), run_name='__main__')"
    for kind, parts in _MANAGED_HOOK_PARTS.items():
        body = prefix + ", ".join(repr(part) for part in parts) + suffix
        for executable in ("python", "python3"):
            for bytecode_flag in ("", "-B "):
                commands[f'{executable} {bytecode_flag}-c "{body}"'] = kind
    return commands


_MANAGED_DISPATCHER_COMMANDS = _managed_dispatcher_commands()


def _managed_hook_kind(value: Any) -> str | None:
    """Classify only exact supported dispatchers with agreeing platform fields."""
    if not isinstance(value, Mapping) or value.get("type") != "command":
        return None
    kinds: list[str] = []
    for field in ("command", "commandWindows"):
        if field not in value:
            continue
        command = value[field]
        if not isinstance(command, str):
            return None
        kind = _MANAGED_DISPATCHER_COMMANDS.get(command)
        if kind is None:
            return None
        kinds.append(kind)
    if not kinds or any(kind != kinds[0] for kind in kinds[1:]):
        return None
    return kinds[0]


def _contains_gate(value: Any) -> bool:
    """Compatibility helper for legacy tests and lifecycle-only classification."""
    if isinstance(value, Mapping) and _managed_hook_kind(value) == "adversarial-lifecycle":
        return True
    if isinstance(value, Mapping):
        return any(_contains_gate(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_gate(item) for item in value)
    return False


def managed_hook_contracts(source: Path) -> dict[str, dict[str, Any]]:
    try:
        value = json.loads((source / "hooks.json").read_text(encoding="utf-8"))
        hooks = value["hooks"]
    except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("unsupported source hooks format") from exc
    if not isinstance(hooks, dict):
        die("unsupported source hooks format")
    result: dict[str, dict[str, Any]] = {}
    for event in MANAGED_EVENTS:
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            die(f"source hooks event is malformed: {event}")
        matched = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("hooks"), list)
            and any(_managed_hook_kind(handler) is not None for handler in entry["hooks"])
        ]
        if len(matched) > 1:
            die(f"source hooks event has ambiguous managed registrations: {event}")
        if not matched:
            continue
        contract = json.loads(json.dumps(matched[0]))
        handlers = contract.get("hooks")
        if not isinstance(handlers, list):
            die(f"source review-gate hook group is malformed: {event}")
        managed_handlers = [handler for handler in handlers if _managed_hook_kind(handler) is not None]
        if not managed_handlers:
            die(f"source managed hook group is empty: {event}")
        kinds = [_managed_hook_kind(handler) for handler in managed_handlers]
        if len(kinds) != len(set(kinds)):
            die(f"source managed hook kind is duplicated: {event}")
        contract["hooks"] = managed_handlers
        result[event] = contract
    return result


def _remove_managed_handlers(entry: Any) -> Any | None:
    """Remove only managed handlers, preserving unrelated handlers in a shared group."""
    if not isinstance(entry, dict):
        return entry
    handlers = entry.get("hooks")
    if not isinstance(handlers, list):
        return None if _contains_gate(entry) else entry
    remaining = [handler for handler in handlers if _managed_hook_kind(handler) is None]
    if len(remaining) == len(handlers):
        return entry
    if not remaining:
        return None
    preserved = json.loads(json.dumps(entry))
    preserved["hooks"] = remaining
    return preserved


def _remove_gate_handlers(entry: Any) -> Any | None:
    """Remove only retired lifecycle handlers for legacy migration callers."""
    if not isinstance(entry, dict):
        return entry
    handlers = entry.get("hooks")
    if not isinstance(handlers, list):
        return None if _contains_gate(entry) else entry
    remaining = [
        handler
        for handler in handlers
        if _managed_hook_kind(handler) != "adversarial-lifecycle"
    ]
    if len(remaining) == len(handlers):
        return entry
    if not remaining:
        return None
    preserved = json.loads(json.dumps(entry))
    preserved["hooks"] = remaining
    return preserved


def _merge_managed_hook_entries(
    current: list[Any],
    contract: Mapping[str, Any] | None,
) -> list[Any]:
    expected: dict[str, dict[str, Any]] = {}
    expected_order: list[str] = []
    if contract is not None:
        handlers = contract.get("hooks")
        if not isinstance(handlers, list):
            die("source managed hook contract is malformed")
        for handler in handlers:
            kind = _managed_hook_kind(handler)
            if kind is None or kind == "adversarial-lifecycle" or not isinstance(handler, dict):
                die("source managed hook contract contains an unsupported dispatcher")
            expected[kind] = handler
            expected_order.append(kind)

    installed: set[str] = set()
    updated: list[Any] = []
    for entry in current:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            updated.append(entry)
            continue
        changed = False
        handlers: list[Any] = []
        for handler in entry["hooks"]:
            kind = _managed_hook_kind(handler)
            if kind == "adversarial-lifecycle":
                changed = True
                continue
            if kind in expected:
                changed = True
                if kind not in installed:
                    handlers.append(copy.deepcopy(expected[kind]))
                    installed.add(kind)
                continue
            handlers.append(handler)
        if not changed:
            updated.append(entry)
        elif handlers:
            preserved = copy.deepcopy(entry)
            preserved["hooks"] = handlers
            updated.append(preserved)

    missing = [kind for kind in expected_order if kind not in installed]
    if missing:
        appended = copy.deepcopy(dict(contract or {}))
        appended["hooks"] = [copy.deepcopy(expected[kind]) for kind in missing]
        updated.append(appended)
    return updated


def hooks_text(existing: bytes, source: Path) -> bytes:
    try:
        value = json.loads(existing.decode("utf-8")) if existing else {"hooks": {}}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("unsupported destination hooks format") from exc
    if not isinstance(value, dict) or not isinstance(value.get("hooks", {}), dict):
        die("unsupported destination hooks format")
    target = value.setdefault("hooks", {})
    contracts = managed_hook_contracts(source)
    for event in MANAGED_EVENTS:
        current = target.get(event, [])
        if not isinstance(current, list):
            die(f"unsupported destination hook event format: {event}")
        contract = contracts.get(event)
        updated = _merge_managed_hook_entries(current, contract)
        if updated:
            target[event] = updated
        else:
            target.pop(event, None)
    newline = "\r\n" if b"\r\n" in existing else "\n"
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").replace("\n", newline).encode("utf-8")


def _managed_instruction(source: Path) -> str:
    return (
        source
        / "skills"
        / "adversarial-code-review"
        / "references"
        / "managed-agents-instruction.md"
    ).read_text(encoding="utf-8").strip()


def _source_agents(source: Path) -> bytes:
    return _contained(source, "AGENTS.md", existing=True).read_bytes()


def agents_text(existing: bytes, source: Path, *, replace_global_agents: bool = False) -> bytes:
    canonical = _source_agents(source)
    if existing == canonical or replace_global_agents:
        return canonical
    content = _managed_instruction(source)
    text = existing.decode("utf-8") if existing else ""
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        die("destination AGENTS managed block is malformed")
    newline = "\r\n" if b"\r\n" in existing else "\n"
    block = f"{BEGIN}\n{content}\n{END}".replace("\n", newline)
    if BEGIN in text:
        before, rest = text.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        result = before.rstrip("\r\n") + newline + newline + block + after
    else:
        result = text.rstrip("\r\n") + (newline + newline if text else "") + block + newline
    return result.encode("utf-8")


def _semantic_snapshots(
    home: Path,
) -> dict[str, tuple[bytes | None, dict[str, int] | None]]:
    return {
        relative: _regular_leaf_snapshot(home, relative)
        for relative in sorted(SEMANTIC_DESTINATIONS)
    }


def _semantic_plan(
    source: Path,
    snapshots: Mapping[str, tuple[bytes | None, dict[str, int] | None]],
    *,
    replace_global_agents: bool = False,
) -> dict[str, bytes]:
    existing = {
        relative: snapshot[0] or b""
        for relative, snapshot in snapshots.items()
    }
    return {
        "config.toml": config_text(existing["config.toml"], source),
        "hooks.json": hooks_text(existing["hooks.json"], source),
        "AGENTS.md": agents_text(
            existing["AGENTS.md"],
            source,
            replace_global_agents=replace_global_agents,
        ),
    }


def _managed_extras(home: Path) -> set[str]:
    extras: set[str] = set()
    for root_relative, allowed in MANAGED_ROOTS.items():
        root = home / root_relative
        if not root.exists():
            continue
        _reject_reparse_chain(root, f"managed destination {root_relative}")
        for item in root.rglob("*"):
            if _is_reparse(item):
                relative = item.relative_to(home).as_posix()
                die(f"managed destination has a symlink or reparse point: {relative}")
            if not item.is_file():
                continue
            relative = item.relative_to(home).as_posix()
            if relative in allowed:
                continue
            name = item.name.casefold()
            if _is_generated_cache_path(relative):
                continue
            if relative in STALE_MANAGED_FILES or name.startswith("test_"):
                extras.add(relative)
            else:
                die(f"unowned file exists inside managed destination: {relative}")
    return extras


def planned(
    source: Path,
    home: Path,
    *,
    replace_global_agents: bool = False,
) -> tuple[
    dict[str, bytes],
    dict[str, bytes],
    set[str],
    dict[str, tuple[bytes | None, dict[str, int] | None]],
]:
    managed_paths = set(COPY_MANIFEST) | set(SEMANTIC_DESTINATIONS) | set(STALE_MANAGED_FILES)
    _reject_managed_leaf_reparses(home, managed_paths)
    copied = source_files(source)
    snapshots = _semantic_snapshots(home)
    semantic = _semantic_plan(
        source,
        snapshots,
        replace_global_agents=replace_global_agents,
    )
    deletions = _managed_extras(home) | {path for path in STALE_MANAGED_FILES if (home / path).is_file()}
    _reject_managed_leaf_reparses(home, deletions)
    return copied, semantic, deletions, snapshots


def _preview_from_plan(
    source: Path,
    home: Path,
    copied: Mapping[str, bytes],
    semantic: Mapping[str, bytes],
    deletions: set[str],
    snapshots: Mapping[str, tuple[bytes | None, dict[str, int] | None]],
    *,
    replace_global_agents: bool = False,
) -> dict[str, Any]:
    changed_copy = sorted(
        path for path, data in copied.items() if not (home / path).is_file() or (home / path).read_bytes() != data
    )
    changed_semantic = sorted(
        path for path, data in semantic.items() if not (home / path).is_file() or (home / path).read_bytes() != data
    )
    source_agents = _source_agents(source)
    previous_agents = snapshots["AGENTS.md"][0]
    agents_mode = "exact_source" if semantic["AGENTS.md"] == source_agents else "preserved_block"
    return {
        "copy": changed_copy,
        "semantic": changed_semantic,
        "semantic_changes": {
            "config": ["agents.sol_reviewer", "skills.config:adversarial-code-review"],
            "hooks": list(MANAGED_EVENTS),
            "instructions": ["AGENTS.md"] if replace_global_agents else [BEGIN, END],
        },
        "global_agents": {
            "mode": agents_mode,
            "previous_sha256": sha(previous_agents) if previous_agents is not None else None,
            "source_sha256": sha(source_agents),
        },
        "delete": sorted(deletions),
        "unchanged": not changed_copy and not changed_semantic and not deletions,
    }


def preview(
    source: Path,
    home: Path,
    *,
    replace_global_agents: bool = False,
) -> dict[str, Any]:
    copied, semantic, deletions, snapshots = planned(
        source,
        home,
        replace_global_agents=replace_global_agents,
    )
    return _preview_from_plan(
        source,
        home,
        copied,
        semantic,
        deletions,
        snapshots,
        replace_global_agents=replace_global_agents,
    )


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o700)
    except OSError as exc:
        raise ValueError(f"could not make private staging directory: {path}") from exc


def _current_windows_sid() -> str:
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        text=True,
        capture_output=True,
        check=False,
    )
    if identity.returncode != 0:
        die("could not resolve the invoking Windows account SID")
    try:
        sid = next(csv.reader([identity.stdout.strip()]))[1]
    except (IndexError, StopIteration) as exc:
        raise ValueError("could not parse the invoking Windows account SID") from exc
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        die("invoking Windows account SID is malformed")
    return sid


def _harden_private_tree(path: Path) -> None:
    """Fail closed unless every transaction object has a private ACL/mode."""
    if os.name == "nt":
        sid = _current_windows_sid()
        hardened = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)(F)",
                "*S-1-5-18:(OI)(CI)(F)",
                "*S-1-5-32-544:(OI)(CI)(F)",
                "*S-1-3-4:(OI)(CI)(F)",
                "/T",
                "/C",
                "/Q",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if hardened.returncode != 0:
            die(f"could not establish private recursive Windows ACL: {hardened.stderr.strip()}")
        effective = subprocess.run(
            [
                "icacls",
                str(path),
                "/grant",
                f"*{sid}:(F)",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
                "*S-1-3-4:(F)",
                "/T",
                "/C",
                "/Q",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if effective.returncode != 0:
            die(f"could not establish effective recursive Windows ACL: {effective.stderr.strip()}")
        with tempfile.TemporaryDirectory() as temporary:
            acl_path = Path(temporary) / "transaction.acl"
            saved = subprocess.run(
                ["icacls", str(path), "/save", str(acl_path), "/T", "/C", "/Q"],
                text=True,
                capture_output=True,
                check=False,
            )
            if saved.returncode != 0:
                die(f"could not verify private recursive Windows ACL: {saved.stderr.strip()}")
            sddl = acl_path.read_text(encoding="utf-16-le")
        acl_lines = [line for line in sddl.splitlines() if line.startswith("D:")]
        expected_objects = sum(1 for _ in path.rglob("*")) + 1
        if len(acl_lines) != expected_objects:
            die("private Windows ACL verification did not cover every transaction object")
        for acl in acl_lines:
            if any(principal in acl for principal in (";;;BU)", ";;;WD)", ";;;AU)")):
                die("private Windows ACL retains an unrelated account")
            if sid not in acl or ";;;SY)" not in acl or ";;;BA)" not in acl:
                die("private Windows ACL lacks required invoking-account or recovery access")
    else:
        for directory, _, names in os.walk(path):
            os.chmod(directory, 0o700)
            for name in names:
                os.chmod(Path(directory) / name, 0o600)


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".review-install-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


@contextmanager
def _install_lock(home: Path):
    state = home / ".adversarial-review-install"
    state.mkdir(exist_ok=True)
    _reject_reparse_chain(state, "installer state")
    handle_path = state / "install.lock"
    with handle_path.open("a+b") as handle:
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
                    die("installer lock timeout")
                time.sleep(0.01)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _transaction_root(home: Path, transaction: str) -> Path:
    if TRANSACTION_ID.fullmatch(transaction) is None:
        die("transaction id must be exactly 32 lowercase hexadecimal characters")
    return _contained(home, f".adversarial-review-install/{transaction}")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing or malformed") from exc
    if not isinstance(value, dict):
        die(f"{label} is malformed")
    return value


def _regular_leaf_snapshot(home: Path, relative: str) -> tuple[bytes | None, dict[str, int] | None]:
    """Read one regular managed leaf while authenticating its non-following identity."""
    target = _reject_managed_leaf_reparse(home, relative)
    before = _lstat(target)
    if before is None:
        return None, None
    if not stat.S_ISREG(before.st_mode):
        die(f"managed target is not a regular file: {relative}")
    identity = _leaf_identity(before)
    data = target.read_bytes()
    after = _lstat(target)
    if after is None or _metadata_is_reparse(after) or _leaf_identity(after) != identity:
        die(f"managed target identity changed while reading: {relative}")
    return data, identity


def _valid_leaf_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"device", "inode", "mode", "file_attributes"}
        and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in value.values())
    )


def _require_prepared_leaf(
    home: Path,
    manifest: Mapping[str, Any],
    relative: str,
) -> None:
    data, identity = _regular_leaf_snapshot(home, relative)
    record = manifest["paths"][relative]
    if record["present"] is False:
        if data is not None:
            die(f"managed target appeared after transaction preparation: {relative}")
        return
    if manifest["schema_version"] >= 2 and identity != record["identity"]:
        die(f"managed target identity changed after transaction preparation: {relative}")
    if data is None or len(data) != record["size"] or sha(data) != record["sha256"]:
        die(f"managed target content changed after transaction preparation: {relative}")


def _prepare_transaction(
    home: Path,
    transaction: str,
    writes: Mapping[str, bytes],
    deletions: set[str],
    *,
    expected_preimages: Mapping[
        str,
        tuple[bytes | None, dict[str, int] | None],
    ] | None = None,
) -> Path:
    root = _transaction_root(home, transaction)
    tracked = sorted(set(writes) | deletions)
    _reject_managed_leaf_reparses(home, tracked)
    expected = expected_preimages or {}
    preimages: dict[str, tuple[bytes | None, dict[str, int] | None]] = {}
    for relative in tracked:
        snapshot = _regular_leaf_snapshot(home, relative)
        if relative in expected and snapshot != expected[relative]:
            die(f"managed target changed after planning: {relative}")
        preimages[relative] = snapshot
    predecessor = _active_completed_head(home)
    _private_directory(root)
    _harden_private_tree(root)
    _private_directory(root / "backup")
    _private_directory(root / "staging")
    path_records: dict[str, Any] = {}
    for relative in tracked:
        data, identity = preimages[relative]
        if data is not None:
            backup = _contained(root / "backup", relative)
            _atomic_write(backup, data)
            path_records[relative] = {
                "present": True,
                "sha256": sha(data),
                "size": len(data),
                "identity": identity,
            }
        else:
            path_records[relative] = {
                "present": False,
                "sha256": None,
                "size": 0,
                "identity": None,
            }
    staged_hashes: dict[str, str] = {}
    for relative, data in writes.items():
        stage = _contained(root / "staging", relative)
        _atomic_write(stage, data)
        if stage.read_bytes() != data:
            die(f"staged equality failed: {relative}")
        staged_hashes[relative] = sha(data)
    manifest = {
        "schema_version": 2,
        "home_sha256": sha(str(home.resolve()).encode("utf-8")),
        "predecessor_transaction_id": predecessor,
        "paths": path_records,
        "writes": dict(sorted(staged_hashes.items())),
        "deletions": sorted(deletions),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write(root / "manifest.json", manifest_bytes)
    journal = {
        "schema_version": 2,
        "transaction_id": transaction,
        "manifest_sha256": sha(manifest_bytes),
        "status": "prepared",
        "next_path": None,
        "applied": [],
        "postimage_identities": {},
    }
    _atomic_json(root / "journal.json", journal)
    _harden_private_tree(root)
    return root


def _validated_transaction(
    home: Path,
    transaction: str,
    *,
    allow_generated_cache_drift: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = _transaction_root(home, transaction)
    _reject_reparse_chain(root, "transaction")
    journal = _read_json(root / "journal.json", "transaction journal")
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = _read_json(manifest_path, "transaction manifest")
    journal_version = journal.get("schema_version")
    expected_journal_fields = {
        "schema_version",
        "transaction_id",
        "manifest_sha256",
        "status",
        "next_path",
        "applied",
    }
    if journal_version == 2:
        expected_journal_fields.add("postimage_identities")
    if journal_version not in {1, 2} or set(journal) != expected_journal_fields:
        die("transaction journal fields are not exact")
    if journal["transaction_id"] != transaction or journal["manifest_sha256"] != sha(manifest_bytes):
        die("transaction journal identity mismatch")
    if (
        set(manifest) != {"schema_version", "home_sha256", "predecessor_transaction_id", "paths", "writes", "deletions"}
        or manifest.get("schema_version") not in {1, 2}
        or manifest["schema_version"] != journal_version
    ):
        die("transaction manifest fields are not exact")
    if manifest["home_sha256"] != sha(str(home.resolve()).encode("utf-8")):
        die("transaction belongs to another Codex home")
    predecessor = manifest["predecessor_transaction_id"]
    if predecessor is not None and (not isinstance(predecessor, str) or TRANSACTION_ID.fullmatch(predecessor) is None or predecessor == transaction):
        die("transaction predecessor identity is invalid")
    if not isinstance(manifest["paths"], dict) or not isinstance(manifest["writes"], dict) or not isinstance(manifest["deletions"], list):
        die("transaction manifest collections are malformed")
    if journal["status"] not in {"prepared", "applying", "validating", "completed", "rolling_back", "rolled_back"}:
        die("transaction journal status is invalid")
    if not isinstance(journal["applied"], list) or len(journal["applied"]) != len(set(journal["applied"])):
        die("transaction journal applied paths are malformed")
    if any(path not in manifest["paths"] for path in journal["applied"]):
        die("transaction journal applied path is untracked")
    if journal["next_path"] is not None and journal["next_path"] not in manifest["paths"]:
        die("transaction journal next path is untracked")
    if len(manifest["deletions"]) != len(set(manifest["deletions"])):
        die("transaction manifest has duplicate deletions")
    if set(manifest["paths"]) != set(manifest["writes"]) | set(manifest["deletions"]):
        die("transaction manifest path sets disagree")
    postimage_identities = journal.get("postimage_identities", {})
    if journal_version == 2:
        if not isinstance(postimage_identities, dict) or not set(postimage_identities).issubset(journal["applied"]):
            die("transaction postimage identities disagree with applied paths")
        if journal["status"] in {"prepared", "applying", "validating", "completed"} and set(
            postimage_identities
        ) != set(journal["applied"]):
            die("transaction postimage identities are incomplete")
        for relative, identity in postimage_identities.items():
            if (
                relative not in manifest["paths"]
                or (relative in manifest["writes"] and not _valid_leaf_identity(identity))
                or (relative in manifest["deletions"] and identity is not None)
            ):
                die("transaction postimage identity is malformed")
    for relative, record in manifest["paths"].items():
        _safe_relative(relative)
        expected_record_fields = {"present", "sha256", "size"}
        if manifest["schema_version"] == 2:
            expected_record_fields.add("identity")
        if not isinstance(record, dict) or set(record) != expected_record_fields:
            die("transaction backup record is malformed")
        if record["present"] is True:
            if manifest["schema_version"] == 2 and not _valid_leaf_identity(record["identity"]):
                die("transaction backup identity is malformed")
            generated_deletion = (
                allow_generated_cache_drift
                and relative in manifest["deletions"]
                and _is_generated_cache_path(relative)
            )
            backup = _contained(root / "backup", relative, existing=not generated_deletion)
            data = backup.read_bytes() if backup.is_file() else None
            if data is None or record["sha256"] != sha(data) or record["size"] != len(data):
                if generated_deletion:
                    continue
                die(f"backup authentication failed: {relative}")
        else:
            expected_absent = {"present": False, "sha256": None, "size": 0}
            if manifest["schema_version"] == 2:
                expected_absent["identity"] = None
            if record != expected_absent:
                die("absent backup record is malformed")
    for relative, expected in manifest["writes"].items():
        _safe_relative(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            die("staged hash is malformed")
        stage = _contained(root / "staging", relative, existing=True)
        if sha(stage.read_bytes()) != expected:
            die(f"staged payload authentication failed: {relative}")
    ordered_paths = sorted(manifest["paths"])
    applied = journal["applied"]
    next_path = journal["next_path"]
    if applied != ordered_paths[:len(applied)]:
        die("transaction journal applied paths are not an ordered prefix")
    if journal["status"] == "prepared" and (applied or next_path is not None):
        die("prepared transaction journal has apply progress")
    if journal["status"] == "applying" and next_path is not None:
        if len(applied) >= len(ordered_paths) or next_path != ordered_paths[len(applied)]:
            die("applying transaction next path does not follow applied progress")
    if journal["status"] in {"validating", "completed"} and (
        applied != ordered_paths or next_path is not None
    ):
        die(f"{journal['status']} transaction journal is incomplete")
    if journal["status"] == "rolling_back" and next_path is not None and (
        not applied or next_path != applied[-1]
    ):
        die("rollback transaction next path does not match remaining progress")
    if journal["status"] == "rolled_back" and (applied or next_path is not None):
        die("rolled-back transaction journal retains progress")
    return root, manifest, journal


def _active_completed_head(home: Path) -> str | None:
    """Return the single active completed lineage head, failing on forks."""
    state = home / ".adversarial-review-install"
    if not state.exists():
        return None
    completed: dict[str, dict[str, Any]] = {}
    for candidate in state.iterdir():
        if not candidate.is_dir() or TRANSACTION_ID.fullmatch(candidate.name) is None:
            continue
        journal = candidate / "journal.json"
        manifest = candidate / "manifest.json"
        if not journal.is_file() or not manifest.is_file():
            continue
        _, record, status = _validated_transaction(
            home,
            candidate.name,
            allow_generated_cache_drift=True,
        )
        if status["status"] == "completed":
            completed[candidate.name] = record
    if not completed:
        return None
    referenced = {
        record["predecessor_transaction_id"]
        for record in completed.values()
        if record["predecessor_transaction_id"] in completed
    }
    heads = set(completed) - referenced
    if len(heads) != 1:
        die("completed transaction lineage is ambiguous")
    head = next(iter(heads))
    seen: set[str] = set()
    cursor: str | None = head
    while cursor is not None:
        if cursor in seen:
            die("completed transaction lineage contains a cycle")
        seen.add(cursor)
        record = completed.get(cursor)
        cursor = record["predecessor_transaction_id"] if record else None
    return head


def _journal_postimage_identity(journal: Mapping[str, Any], relative: str) -> Any:
    identities = journal.get("postimage_identities")
    if isinstance(identities, Mapping) and relative in identities:
        return identities[relative]
    return _IDENTITY_UNSET


def _require_current_postimage(
    home: Path,
    transaction: str,
    manifest: Mapping[str, Any],
    journal: Mapping[str, Any],
) -> None:
    head = _active_completed_head(home)
    if head != transaction:
        die("rollback refused: a later completed install supersedes this transaction")
    drift: list[str] = []
    for relative in sorted(manifest["paths"]):
        data, current_identity = _regular_leaf_snapshot(home, relative)
        expected_identity = _journal_postimage_identity(journal, relative)
        if relative in manifest["writes"]:
            if data is None or sha(data) != manifest["writes"][relative] or (
                expected_identity is not _IDENTITY_UNSET
                and current_identity != expected_identity
            ):
                drift.append(relative)
        elif data is not None:
            drift.append(relative)
    if drift:
        die(f"rollback refused: live postimage drift at {', '.join(drift)}")


def _live_image_matches(
    home: Path,
    manifest: Mapping[str, Any],
    relative: str,
    *,
    postimage_identity: Any = _IDENTITY_UNSET,
) -> tuple[bool, bool]:
    """Return whether a live path equals the authenticated preimage/postimage."""
    data, current_identity = _regular_leaf_snapshot(home, relative)
    present = data is not None
    digest = sha(data) if data is not None else None
    size = len(data) if data is not None else 0
    record = manifest["paths"][relative]
    preimage = (
        present and record["present"] is True
        and digest == record["sha256"] and size == record["size"]
    ) or (not present and record["present"] is False)
    postimage = (
        present and relative in manifest["writes"]
        and digest == manifest["writes"][relative]
    ) or (not present and relative in manifest["deletions"])
    if postimage and postimage_identity is not _IDENTITY_UNSET:
        postimage = current_identity == postimage_identity
    return preimage, postimage


def _rollback_candidates(manifest: Mapping[str, Any], journal: Mapping[str, Any]) -> list[str]:
    if journal["status"] == "completed":
        return sorted(manifest["paths"])
    candidates = list(journal["applied"])
    next_path = journal["next_path"]
    if journal["status"] != "rolling_back" and next_path is not None:
        candidates.append(next_path)
    return candidates


def _preflight_incomplete_rollback(
    home: Path,
    manifest: Mapping[str, Any],
    journal: Mapping[str, Any],
    candidates: list[str],
) -> None:
    """Reject every non-authenticated live state before changing journal or files."""
    candidate_set = set(candidates)
    drift: list[str] = []
    for relative in sorted(manifest["paths"]):
        preimage, postimage = _live_image_matches(
            home,
            manifest,
            relative,
            postimage_identity=_journal_postimage_identity(journal, relative),
        )
        if relative in candidate_set:
            if not (preimage or postimage):
                drift.append(relative)
        elif not preimage:
            drift.append(relative)
    if drift:
        die(f"rollback refused: live transaction drift at {', '.join(drift)}")


def _restore_preimage(
    home: Path,
    root: Path,
    manifest: Mapping[str, Any],
    journal: Mapping[str, Any],
    relative: str,
) -> None:
    """Restore one candidate only while it remains an authenticated postimage."""
    preimage, postimage = _live_image_matches(
        home,
        manifest,
        relative,
        postimage_identity=_journal_postimage_identity(journal, relative),
    )
    if preimage:
        return
    if not postimage:
        die(f"rollback refused: live transaction drift at {relative}")
    target = _reject_managed_leaf_reparse(home, relative)
    record = manifest["paths"][relative]
    if record["present"]:
        _atomic_write(target, _contained(root / "backup", relative, existing=True).read_bytes())
    else:
        if not target.is_file() or _is_reparse(target):
            die(f"rollback target is not a regular file: {relative}")
        target.unlink()
    restored, _ = _live_image_matches(home, manifest, relative)
    if not restored:
        die(f"rollback preimage verification failed: {relative}")


def _composite_lifecycle_state_exists(home: Path) -> bool:
    roots = [home / "hooks" / "state" / "adversarial-review"]
    override = os.environ.get("CODEX_ADVERSARIAL_STATE")
    if override:
        roots.append(_lexical_absolute(override, "adversarial lifecycle state"))
    seen: set[Path] = set()
    for root in roots:
        absolute = _filesystem_path(Path(os.path.abspath(root)))
        if absolute in seen:
            continue
        seen.add(absolute)
        deliveries = absolute / "deliveries"
        if not deliveries.exists():
            continue
        _reject_reparse_chain(deliveries, "adversarial lifecycle state")
        for address in deliveries.iterdir():
            if _is_reparse(address):
                die(f"adversarial lifecycle state has a symlink or reparse point: {address}")
            if not address.is_dir() or HEX_SHA256.fullmatch(address.name) is None:
                continue
            for generation in address.iterdir():
                if _is_reparse(generation):
                    die(f"adversarial lifecycle state has a symlink or reparse point: {generation}")
                if generation.is_file() and re.fullmatch(r"generation-[0-9]+\.json", generation.name):
                    return True
    return False


def _rollback_preimage_supports_composite_state(
    transaction_root: Path,
    manifest: Mapping[str, Any],
) -> bool:
    record = manifest["paths"].get(LIFECYCLE_GATE_PATH)
    if record is None:
        return True
    if record["present"] is not True:
        return False
    backup = _contained(
        transaction_root / "backup",
        LIFECYCLE_GATE_PATH,
        existing=True,
    ).read_bytes()
    try:
        tree = ast.parse(backup.decode("utf-8"), filename=LIFECYCLE_GATE_PATH)
    except (SyntaxError, UnicodeDecodeError):
        return False
    declarations = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "DELIVERY_ADDRESSING"
    ]
    return (
        len(declarations) == 1
        and isinstance(declarations[0].value, ast.Constant)
        and declarations[0].value.value == "composite-v1"
    )


def _refuse_incompatible_lifecycle_rollback(
    home: Path,
    transaction_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    if (
        not _rollback_preimage_supports_composite_state(transaction_root, manifest)
        and _composite_lifecycle_state_exists(home)
    ):
        die(
            "rollback refused: composite lifecycle state exists but the authenticated "
            "preimage lifecycle gate cannot address it"
        )


def _rollback_transaction(home: Path, transaction: str, *, acquire: bool) -> None:
    context = _install_lock(home) if acquire else nullcontext()
    with context:
        root, manifest, journal = _validated_transaction(home, transaction)
        if journal["status"] == "rolled_back":
            return
        if journal["status"] == "completed":
            # Explicit historical rollback is allowed only for the active head
            # and only while every live target still equals its postimage.
            _require_current_postimage(home, transaction, manifest, journal)
        _refuse_incompatible_lifecycle_rollback(home, root, manifest)
        candidates = _rollback_candidates(manifest, journal)
        # Authenticate every live path before changing either the journal or a
        # target. Untouched paths must still be preimages; candidates may be a
        # preimage (before replace or already rolled back) or a postimage.
        _preflight_incomplete_rollback(home, manifest, journal, candidates)
        if journal["status"] != "rolling_back":
            journal.update({"status": "rolling_back", "applied": candidates, "next_path": None})
            _atomic_json(root / "journal.json", journal)
        while journal["applied"]:
            relative = journal["applied"][-1]
            if journal["next_path"] != relative:
                journal["next_path"] = relative
                _atomic_json(root / "journal.json", journal)
            _restore_preimage(home, root, manifest, journal, relative)
            journal["applied"].pop()
            if journal["schema_version"] >= 2:
                journal["postimage_identities"].pop(relative, None)
            journal["next_path"] = None
            _atomic_json(root / "journal.json", journal)
        # Catch drift in both originally untouched and already-restored paths
        # before declaring the rollback complete.
        _preflight_incomplete_rollback(home, manifest, journal, [])
        journal.update({"status": "rolled_back", "next_path": None, "applied": []})
        _atomic_json(root / "journal.json", journal)


def rollback(home: Path, transaction: str) -> None:
    _rollback_transaction(home, transaction, acquire=True)


def _recover_incomplete(home: Path) -> list[str]:
    state = home / ".adversarial-review-install"
    if not state.exists():
        return []
    recovered: list[str] = []
    for candidate in state.iterdir():
        if not candidate.is_dir() or TRANSACTION_ID.fullmatch(candidate.name) is None:
            continue
        journal_path = candidate / "journal.json"
        if not journal_path.is_file():
            continue
        journal = _read_json(journal_path, "transaction journal")
        if journal.get("status") in {"prepared", "applying", "validating", "rolling_back"}:
            _rollback_transaction(home, candidate.name, acquire=False)
            recovered.append(candidate.name)
    return recovered


def _incomplete_transactions(home: Path) -> list[str]:
    state = home / ".adversarial-review-install"
    if not state.exists():
        return []
    _reject_reparse_chain(state, "installer state")
    pending: list[str] = []
    for candidate in state.iterdir():
        if not candidate.is_dir() or TRANSACTION_ID.fullmatch(candidate.name) is None:
            continue
        journal_path = candidate / "journal.json"
        if not journal_path.is_file():
            pending.append(candidate.name)
            continue
        try:
            journal = _read_json(journal_path, "transaction journal")
        except ValueError:
            pending.append(candidate.name)
            continue
        if journal.get("status") in {"prepared", "applying", "validating", "rolling_back"}:
            pending.append(candidate.name)
    return sorted(pending)


def _validate_skill(skill: Path, expected_name: str) -> None:
    skill_file = skill / "SKILL.md"
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"skill validator cannot read {skill_file}") from exc
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        die(f"skill validator rejected frontmatter: {skill}")
    fields: dict[str, str] = {}
    lines = match.group(1).splitlines()
    for line in lines:
        if not line.strip() or line[0].isspace():
            continue
        if ":" not in line:
            die(f"skill validator rejected frontmatter: {skill}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"} or fields["name"] != expected_name:
        die(f"skill validator rejected metadata: {skill}")
    if not fields["description"] and not any(line.startswith((" ", "\t")) and line.strip() for line in lines):
        die(f"skill validator rejected empty description: {skill}")
    for destination in LINK.findall(text):
        if "://" in destination or destination.startswith("#"):
            continue
        relative = destination.split("#", 1)[0]
        if relative and not _contained(skill, relative, existing=True).exists():
            die(f"skill validator found a broken local link: {destination}")


def _profile_exact(home: Path) -> None:
    try:
        profile = tomllib.loads((home / "agents" / "sol_reviewer.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("installed sol_reviewer profile is invalid") from exc
    required = {
        "name": "sol_reviewer",
        "model": "gpt-5.6-sol",
        "model_reasoning_effort": "max",
        "sandbox_mode": "read-only",
    }
    if any(profile.get(key) != value for key, value in required.items()):
        die("installed sol_reviewer profile identity is wrong")
    instructions = str(profile.get("developer_instructions", "")).casefold()
    for phrase in (
        "depth 1",
        "do not spawn",
        "root-prepared evidence packet",
        "evidence anchors",
        "verdict",
        "review-lenses.md",
        "every mandatory lens",
        "strict `reviewoutputv1` json",
        "do not emit a receipt",
    ):
        if phrase not in instructions:
            die(f"installed sol_reviewer purpose is incomplete: {phrase}")


def _agents_state(home: Path, source: Path) -> str:
    try:
        data = (home / "AGENTS.md").read_bytes()
        if data == _source_agents(source):
            return "exact_source"
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return "invalid"
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return "invalid"
    actual = text.split(BEGIN, 1)[1].split(END, 1)[0].strip().replace("\r\n", "\n")
    if actual == _managed_instruction(source).replace("\r\n", "\n"):
        return "preserved_block"
    return "invalid"


def _managed_block_exact(home: Path, source: Path) -> bool:
    return _agents_state(home, source) != "invalid"


def _hooks_exact(home: Path, source: Path) -> bool:
    try:
        value = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
        hooks = value["hooks"]
    except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return False
    expected = managed_hook_contracts(source)
    for event in MANAGED_EVENTS:
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            return False
        contract = expected.get(event)
        expected_handlers: dict[str, Any] = {}
        if contract is not None:
            for handler in contract["hooks"]:
                kind = _managed_hook_kind(handler)
                if kind is None or kind in expected_handlers:
                    return False
                expected_handlers[kind] = handler
        actual_handlers: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("hooks"), list):
                continue
            for handler in entry["hooks"]:
                kind = _managed_hook_kind(handler)
                if kind is None:
                    continue
                if (
                    kind == "adversarial-lifecycle"
                    or kind not in expected_handlers
                    or kind in actual_handlers
                    or handler != expected_handlers[kind]
                ):
                    return False
                actual_handlers[kind] = handler
        if set(actual_handlers) != set(expected_handlers):
            return False
    return True


def _run_gate(
    gate: Path,
    payload: Mapping[str, Any],
    environment: Mapping[str, str],
) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-B", str(gate)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=dict(environment),
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        die(f"handler fixture process failed: {payload.get('hook_event_name')}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        die("handler fixture returned a non-object")
    return value


def _run_lifecycle_cli(
    gate: Path,
    state: Path,
    profile: Path,
    arguments: Iterable[str],
    environment: Mapping[str, str],
) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(gate),
            "--state-root",
            str(state),
            "--profile-path",
            str(profile),
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=dict(environment),
        timeout=30,
    )
    if result.returncode != 0:
        die(f"lifecycle fixture command failed: {' '.join(arguments)}: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        die("lifecycle fixture returned a non-object")
    return value


def smoke(source: Path, home: Path) -> dict[str, Any]:
    """Exercise real installed lifecycle state, not Codex hook loading/trust."""
    gate = home / "skills" / "adversarial-code-review" / "scripts" / "lifecycle_gate.py"
    profile = home / "agents" / "sol_reviewer.toml"
    if not gate.is_file() or not profile.is_file():
        die("install the gate before handler-contract smoke")
    session = "handler-contract-session"
    turn = "handler-contract-turn"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        state = root / "state"
        workspace = root / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=workspace, check=True)
        tracked = workspace / "tracked.txt"
        tracked.write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True)
        environment = {
            **os.environ,
            "CODEX_ADVERSARIAL_STATE": str(state),
            "CODEX_HOME": str(home),
        }
        common = {
            "session_id": session,
            "turn_id": turn,
            "cwd": str(workspace),
        }
        prompt = _run_gate(
            gate,
            {**common, "hook_event_name": "UserPromptSubmit", "prompt": "Implement this material change."},
            environment,
        )
        pending_state = _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["status", "--session-id", session, "--turn-id", turn],
            environment,
        )
        _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["classify", "--session-id", session, "--turn-id", turn, "--classification", "material", "--task-id", "handler-contract", "--paths", "tracked.txt"],
            environment,
        )
        mutation = {
            **common,
            "tool_name": "apply_patch",
            "tool_use_id": "fixture-mutation-1",
            "tool_input": {"patch": "fixture"},
        }
        pre = _run_gate(gate, {**mutation, "hook_event_name": "PreToolUse"}, environment)
        pre_state = _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["status", "--session-id", session, "--turn-id", turn],
            environment,
        )
        tracked.write_text("after\n", encoding="utf-8")
        post = _run_gate(gate, {**mutation, "hook_event_name": "PostToolUse"}, environment)
        post_state = _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["status", "--session-id", session, "--turn-id", turn],
            environment,
        )
        duplicate_post = _run_gate(gate, {**mutation, "hook_event_name": "PostToolUse"}, environment)
        duplicate_post_state = _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["status", "--session-id", session, "--turn-id", turn],
            environment,
        )
        verification_root = root / "verification"
        verification_root.mkdir()
        health_command = [
            sys.executable,
            "-B",
            str(gate),
            "--state-root",
            str(state),
            "--profile-path",
            str(profile),
            "health",
        ]
        health_result = subprocess.run(
            health_command,
            cwd=workspace,
            capture_output=True,
            check=False,
            env=environment,
            timeout=30,
        )
        if health_result.returncode != 0:
            die(f"handler-contract health verification failed: {health_result.stderr.decode(errors='replace')}")
        health_stdout = bytes(health_result.stdout)
        health_stderr = bytes(health_result.stderr)
        synthetic_bytes = json.dumps(
            {
                "prompt": prompt,
                "pre": pre,
                "post": post,
                "duplicate_post": duplicate_post,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        (verification_root / "health.stdout").write_bytes(health_stdout)
        (verification_root / "health.stderr").write_bytes(health_stderr)
        (verification_root / "synthetic-handler.json").write_bytes(synthetic_bytes)
        verification_manifest = verification_root / "verification.json"
        verification_manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "platform": {
                        "system": sys.platform,
                        "release": os.name,
                        "machine": os.environ.get("PROCESSOR_ARCHITECTURE", "unknown"),
                        "python": sys.version,
                    },
                    "commands": [
                        {
                            "id": "lifecycle-health",
                            "command": subprocess.list2cmdline(health_command),
                            "cwd": ".",
                            "exit_code": health_result.returncode,
                            "test_counts": {"passed": 0, "failed": 0, "errors": 0, "skipped": 0},
                            "stdout": {
                                "path": "health.stdout",
                                "sha256": sha(health_stdout),
                                "size_bytes": len(health_stdout),
                            },
                            "stderr": {
                                "path": "health.stderr",
                                "sha256": sha(health_stderr),
                                "size_bytes": len(health_stderr),
                            },
                        }
                    ],
                    "observations": [
                        {
                            "id": "synthetic-handler",
                            "subject": "handler_contract_smoke",
                            "provenance": "synthetic",
                            "status": "passed",
                            "detail": "Direct lifecycle handler calls exercised configured event contracts.",
                            "artifact": {
                                "path": "synthetic-handler.json",
                                "sha256": sha(synthetic_bytes),
                                "size_bytes": len(synthetic_bytes),
                            },
                        },
                        {
                            "id": "live-reviewer",
                            "subject": "subagent_provenance",
                            "provenance": "live",
                            "status": "unavailable",
                            "detail": "Installer smoke cannot prove a running Codex process dispatched the installed profile.",
                            "artifact": None,
                        },
                        {
                            "id": "live-mutation",
                            "subject": "mutation_observation",
                            "provenance": "live",
                            "status": "unavailable",
                            "detail": "Installer smoke invokes handlers directly and cannot prove managed runtime observation.",
                            "artifact": None,
                        },
                        {
                            "id": "live-trust",
                            "subject": "hook_trust",
                            "provenance": "live",
                            "status": "not_run",
                            "detail": "Hook trust approval requires an interactive restarted Codex process.",
                            "artifact": None,
                        },
                        {
                            "id": "live-restart",
                            "subject": "runtime_restart",
                            "provenance": "live",
                            "status": "not_run",
                            "detail": "Installer smoke does not restart the active Codex process.",
                            "artifact": None,
                        },
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        frozen = _run_lifecycle_cli(
            gate,
            state,
            profile,
            [
                "freeze",
                "--session-id",
                session,
                "--turn-id",
                turn,
                "--cwd",
                str(workspace),
                "--paths",
                "tracked.txt",
                "--verification-manifest",
                str(verification_manifest),
            ],
            environment,
        )
        coverage = [
            f"{lens}: reviewed - handler-contract fixture"
            for lens in frozen.get("mandatory_lenses", (
                "artifact_identity", "lifecycle_cleanup", "concurrency_ownership",
                "input_command_boundaries", "memory_resource_safety", "performance_hot_paths",
                "repository_contracts", "indirect_consumers", "overlap_attribution", "author_verification",
            ))
        ]
        output = {
            "schema_version": 1,
            "attempt_id": frozen["attempt_id"],
            "packet_sha256": frozen["packet_sha256"],
            "bundle_sha256": frozen["bundle_sha256"],
            "snapshot_sha256": frozen["snapshot_sha256"],
            "verdict": "pass",
            "coverage": coverage,
            "residual_risks": [],
            "findings": [],
        }
        wrong_start = _run_gate(
            gate,
            {**common, "hook_event_name": "SubagentStart", "agent_type": "copied_profile", "model": "gpt-5.6-sol", "agent_id": "wrong-agent"},
            environment,
        )
        copied_stop = _run_gate(
            gate,
            {**common, "hook_event_name": "SubagentStop", "agent_type": "sol_reviewer", "model": "gpt-5.6-sol", "agent_id": "copied-agent", "last_assistant_message": json.dumps(output)},
            environment,
        )
        correct_start = _run_gate(
            gate,
            {**common, "hook_event_name": "SubagentStart", "agent_type": "sol_reviewer", "model": "gpt-5.6-sol", "agent_id": "reviewer-agent"},
            environment,
        )
        correct_stop = _run_gate(
            gate,
            {**common, "hook_event_name": "SubagentStop", "agent_type": "sol_reviewer", "model": "gpt-5.6-sol", "agent_id": "reviewer-agent", "last_assistant_message": json.dumps(output)},
            environment,
        )
        replay_stop = _run_gate(
            gate,
            {**common, "hook_event_name": "SubagentStop", "agent_type": "sol_reviewer", "model": "gpt-5.6-sol", "agent_id": "reviewer-agent", "last_assistant_message": json.dumps(output)},
            environment,
        )
        ledger = json.dumps(
            {"schema_version": 1, "generation": 0, "dispositions": []},
            sort_keys=True,
            separators=(",", ":"),
        )
        _run_lifecycle_cli(
            gate,
            state,
            profile,
            ["disposition", "--session-id", session, "--turn-id", turn, "--json", ledger],
            environment,
        )
        final_stop = _run_gate(
            gate,
            {**common, "hook_event_name": "Stop", "last_assistant_message": "Delivery complete."},
            environment,
        )
    results = {
        "prompt_pending_classification": (
            prompt.get("decision") != "block"
            and pending_state.get("classification") == "pending"
            and pending_state.get("status") == "pending_classification"
            and pending_state.get("mutation_epoch") == 0
            and pending_state.get("inflight_tool_use_ids") == []
            and pending_state.get("seen_tool_use_ids") == []
        ),
        "managed_mutation_reserved": (
            pre.get("decision") != "block"
            and pre_state.get("status") == "armed"
            and pre_state.get("mutation_epoch") == 0
            and pre_state.get("inflight_tool_use_ids") == ["fixture-mutation-1"]
            and pre_state.get("seen_tool_use_ids") == []
        ),
        "managed_mutation_recorded_once": (
            post.get("decision") != "block"
            and duplicate_post.get("decision") != "block"
            and post_state.get("mutation_epoch") == 1
            and post_state.get("inflight_tool_use_ids") == []
            and post_state.get("seen_tool_use_ids") == ["fixture-mutation-1"]
            and duplicate_post_state.get("mutation_epoch") == 1
            and duplicate_post_state.get("inflight_tool_use_ids") == []
            and duplicate_post_state.get("seen_tool_use_ids") == ["fixture-mutation-1"]
        ),
        "wrong_profile_rejected": wrong_start.get("decision") == "block",
        "copied_output_rejected": copied_stop.get("decision") == "block",
        "replayed_output_rejected": replay_stop.get("decision") == "block",
        "correct_profile_provenance": correct_start.get("decision") != "block" and correct_stop.get("decision") != "block",
        "final_stop_accepted": final_stop.get("decision") != "block",
    }
    return {
        "ok": all(results.values()),
        "events": list(MANAGED_EVENTS),
        **results,
        "fixture_observations": {
            "prompt_blocked": prompt.get("decision") == "block",
            "pre_blocked": pre.get("decision") == "block",
            "post_blocked": post.get("decision") == "block",
            "mutation_epoch_before": pre_state.get("mutation_epoch"),
            "mutation_epoch_after": duplicate_post_state.get("mutation_epoch"),
            "inflight_after_pre": pre_state.get("inflight_tool_use_ids"),
            "inflight_after_post": duplicate_post_state.get("inflight_tool_use_ids"),
        },
        "note": "Handler-contract smoke only; it does not prove a running Codex app loaded or trusted hooks.",
    }


def verify(
    source: Path,
    home: Path,
    *,
    replace_global_agents: bool = False,
    ignore_transactions: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    failures: list[str] = []
    _reject_managed_leaf_reparses(
        home,
        set(COPY_MANIFEST) | set(SEMANTIC_DESTINATIONS) | set(STALE_MANAGED_FILES),
    )
    failures.extend(
        f"recovery-journal:{transaction}"
        for transaction in _incomplete_transactions(home)
        if transaction not in ignore_transactions
    )
    copied = source_files(source)
    for relative, data in copied.items():
        target = home / relative
        if not target.is_file() or sha(target.read_bytes()) != sha(data):
            failures.append(f"raw:{relative}")
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
        if not _config_managed_exact(config, source):
            failures.append("semantic:config.toml")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        failures.append("parse:config.toml")
    if not _hooks_exact(home, source):
        failures.append("semantic:hooks.json")
    agents_state = _agents_state(home, source)
    if agents_state == "invalid" or (replace_global_agents and agents_state != "exact_source"):
        failures.append("semantic:AGENTS.md")
    try:
        _profile_exact(home)
        _validate_skill(home / "skills" / "adversarial-code-review", "adversarial-code-review")
        _validate_skill(home / "skills" / "delivery-orchestration", "delivery-orchestration")
        _validate_skill(home / "skills" / "instruction-learning-loop", "instruction-learning-loop")
        _validate_skill(home / "skills" / "plan-review-ladder", "plan-review-ladder")
    except ValueError as exc:
        failures.append(f"validator:{exc}")
    try:
        extras = _managed_extras(home)
        if extras:
            failures.extend(f"runtime-exclusion:{path}" for path in sorted(extras))
    except ValueError as exc:
        failures.append(f"runtime-exclusion:{exc}")
    wrong_packet = home / "skills" / "adversarial-code-review" / "scripts" / "packet_integrity.py"
    if wrong_packet.exists():
        failures.append("canonical-packet-helper:duplicate")
    return {"ok": not failures, "failures": failures, "handler_contract_smoke": None}


def install(
    source: Path,
    home: Path,
    *,
    replace_global_agents: bool = False,
) -> dict[str, Any]:
    # Refuse unsafe topology before even creating the installer lock/state.
    _reject_managed_leaf_reparses(
        home,
        set(COPY_MANIFEST) | set(SEMANTIC_DESTINATIONS) | set(STALE_MANAGED_FILES),
    )
    _managed_extras(home)
    with _install_lock(home):
        recovered = _recover_incomplete(home)
        copied, semantic, deletions, semantic_preimages = planned(
            source,
            home,
            replace_global_agents=replace_global_agents,
        )
        outcome = _preview_from_plan(
            source,
            home,
            copied,
            semantic,
            deletions,
            semantic_preimages,
            replace_global_agents=replace_global_agents,
        )
        if outcome["unchanged"]:
            verification = verify(
                source,
                home,
                replace_global_agents=replace_global_agents,
            )
            if not verification["ok"]:
                die("idempotent installation failed verification")
            return {"idempotent": True, "installed_files": sorted(COPY_MANIFEST), "recovered": recovered, **outcome}
        writes = {**copied, **semantic}
        transaction = uuid.uuid4().hex
        root = _transaction_root(home, transaction)
        try:
            root = _prepare_transaction(
                home,
                transaction,
                writes,
                deletions,
                expected_preimages=semantic_preimages,
            )
            _, manifest, journal = _validated_transaction(home, transaction)
        except Exception:
            if root.exists():
                shutil.rmtree(root)
            raise
        failure = os.environ.get("CODEX_ADVERSARIAL_INSTALL_FAIL_STEP", "")
        try:
            # Authenticate the whole preimage immediately before the apply
            # phase, then authenticate each leaf again at its write boundary.
            for relative in sorted(manifest["paths"]):
                _require_prepared_leaf(home, manifest, relative)
            for index, relative in enumerate(sorted(manifest["paths"]), start=1):
                journal.update({"status": "applying", "next_path": relative})
                _atomic_json(root / "journal.json", journal)
                _require_prepared_leaf(home, manifest, relative)
                target = _reject_managed_leaf_reparse(home, relative)
                installed_identity: dict[str, int] | None = None
                if relative in manifest["writes"]:
                    staged = _contained(root / "staging", relative, existing=True).read_bytes()
                    _atomic_write(target, staged)
                    installed_data, installed_identity = _regular_leaf_snapshot(home, relative)
                    if installed_data is None or sha(installed_data) != manifest["writes"][relative]:
                        die(f"managed postimage verification failed: {relative}")
                elif _lstat(target) is not None:
                    target.unlink()
                    if _lstat(target) is not None:
                        die(f"managed deletion verification failed: {relative}")
                    installed_identity = None
                journal["applied"].append(relative)
                if journal["schema_version"] >= 2:
                    journal["postimage_identities"][relative] = installed_identity
                journal["next_path"] = None
                _atomic_json(root / "journal.json", journal)
                if failure == f"replace:{index}":
                    raise RuntimeError("injected replacement failure")
            journal["status"] = "validating"
            _atomic_json(root / "journal.json", journal)
            if failure == "validators":
                raise RuntimeError("injected validator failure")
            verification = verify(
                source,
                home,
                replace_global_agents=replace_global_agents,
                ignore_transactions=frozenset({transaction}),
            )
            if not verification["ok"]:
                die(f"post-install verification failed: {verification['failures']}")
            journal.update({"status": "completed", "next_path": None})
            _atomic_json(root / "journal.json", journal)
        except Exception:
            _rollback_transaction(home, transaction, acquire=False)
            raise
        return {
            "transaction_id": transaction,
            "idempotent": False,
            "installed_files": sorted(COPY_MANIFEST),
            "handler_contract_smoke": None,
            "recovered": recovered,
            **outcome,
            "next": "Restart Codex and open a new task to reload the root model, profiles, skills, and remaining user-level hooks. Review and approve changed handlers in /hooks. No adversarial lifecycle hooks are registered.",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preview", "install", "verify", "smoke", "rollback"))
    parser.add_argument("--source-root")
    parser.add_argument("--codex-home")
    parser.add_argument("--transaction-id")
    parser.add_argument("--replace-global-agents", action="store_true")
    args = parser.parse_args()
    try:
        if args.replace_global_agents and args.action not in {"preview", "install", "verify"}:
            die("--replace-global-agents is valid only for preview, install, or verify")
        if args.action == "rollback":
            if not args.codex_home or not args.transaction_id:
                die("rollback requires --codex-home and --transaction-id")
            home_lexical = _lexical_absolute(args.codex_home, "codex-home")
            _reject_reparse_chain(home_lexical, "codex-home")
            if not home_lexical.is_dir():
                die("codex-home must exist")
            rollback(home_lexical.resolve(strict=True), args.transaction_id)
            result: dict[str, Any] = {"ok": True, "rolled_back": args.transaction_id}
        else:
            if not args.source_root:
                die("--source-root is required")
            source, home = roots(args)
            validate_source(source)
            if args.action == "preview":
                result = preview(
                    source,
                    home,
                    replace_global_agents=args.replace_global_agents,
                )
            elif args.action == "install":
                result = install(
                    source,
                    home,
                    replace_global_agents=args.replace_global_agents,
                )
            elif args.action == "verify":
                result = verify(
                    source,
                    home,
                    replace_global_agents=args.replace_global_agents,
                )
            else:
                result = smoke(source, home)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok", True) else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
