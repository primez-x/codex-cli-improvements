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
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from review_contracts import (  # noqa: E402
    BundleStore,
    SnapshotLimits,
    build_bundle,
    build_git_snapshot,
    delivery_address_sha256,
    MANDATORY_REVIEW_LENSES,
    validate_disposition_ledger,
    validate_finding_evidence,
    validate_git_object_id,
    validate_lens_coverage,
    validate_review_output,
    validate_review_receipt,
)
from packet_integrity import canonical_bytes, compute_packet_sha256, compute_raw_sha256  # noqa: E402
from verification_evidence import build_verification_evidence, load_production_manifest  # noqa: E402


REVIEWER_TYPE = "sol_reviewer"
REVIEWER_MODEL = "gpt-5.6-sol"
REVIEWER_EFFORT = "max"
DELIVERY_ADDRESSING = "composite-v1"
BLOCKED_MARKER = "[adversarial-review-blocked]"
MUTATION_COMMAND = re.compile(
    r"(?:"
    r"\b(?:apply_patch|cp|mv|rm|del|mkdir|rmdir|touch|tee|truncate)\b|"
    r"\b(?:set|add)-content\b|\bout-file\b|\b(?:new|remove|move|copy|rename)-item\b|"
    r"\bsed\s+-i\b|\bgit\s+(?:add|am|apply|checkout|cherry-pick|clean|commit|merge|mv|rebase|reset|restore|rm|switch)\b|"
    r"\b(?:npm|pnpm|yarn)\s+(?:install|add|remove|run\s+(?:build|generate))\b|"
    r"\b(?:dotnet|msbuild|cargo|go)\s+(?:build|publish|install|generate)\b|"
    r"\[system\.io\.file\]::(?:write|append|create)|"
    r"(?:^|\s)(?:>>?|2>>?)\s*[^&|]"
    r")",
    re.IGNORECASE,
)
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


def default_root() -> Path:
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    return Path(os.environ.get("CODEX_ADVERSARIAL_STATE") or home / "hooks" / "state" / "adversarial-review")


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


def is_mutation(payload: Mapping[str, Any]) -> bool:
    name = str(payload.get("tool_name", "")).casefold()
    if name in DIRECT_MUTATION_TOOLS:
        return True
    if name not in SHELL_TOOLS:
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return False
    command = next((tool_input.get(key) for key in ("command", "cmd", "script") if isinstance(tool_input.get(key), str)), "")
    return bool(MUTATION_COMMAND.search(str(command)))


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
    if not is_mutation(payload):
        return response("PreToolUse", "Read-only tool path observed; no mutation epoch is reserved.")
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
    if not is_mutation(payload):
        return response("PostToolUse", "Read-only tool path did not change the mutation epoch.")
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
            validate_finding_evidence(
                output["findings"],
                store=BundleStore(root / "bundles"),
                active_bundle_sha256=state["bundle_sha256"],
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
    ledger = validate_disposition_ledger(state["ledger"], output["findings"], generation=state["generation"])
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
    if receipt != _make_receipt(state, receipt["disposition_sha256"]):
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


def cli(args: argparse.Namespace, root: Path, profile_path: Path) -> int:
    if args.action == "health":
        profile_sha = profile_digest(profile_path)
        print(json.dumps({"ok": True, "profile_sha256": profile_sha, "state_addressing": "session/task/delivery/generation"}, sort_keys=True))
        return 0
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
            ledger = json.loads(Path(args.file).read_text(encoding="utf-8"))
            ledger = validate_disposition_ledger(ledger, state["review_output"]["findings"], generation=state["generation"])
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
            item.add_argument("--file", required=True)
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
