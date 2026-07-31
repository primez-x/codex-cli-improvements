#!/usr/bin/env python3

"""Command-hook handler for durable instruction-system prompts."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


STATE_SENTINEL = "[instruction-learning-hook]"
STATE_DIR_NAME = "hooks/state/instruction-learning"
LOG_PATH_NAME = "hooks/instruction_learning_hook.log"
MAX_LOG_BYTES = 64 * 1024
MAX_LOG_LINES = 400
STATE_TTL_SECONDS = 6 * 60 * 60
ADDITIONAL_CONTEXT_PREFIX = (
    "Review this as a possible durable instruction-system improvement. "
    "Use $instruction-learning-loop to classify it; do not infer write authority. "
    "Include a standalone disposition line: "
    "`Instruction learning:` ..."
)


def get_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_unix() -> float:
    return time.time()


def sanitize_token(value: Optional[str], fallback: str = "unknown") -> str:
    value = value or fallback
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", str(value))
    sanitized = re.sub(r"_{2,}", "_", sanitized).strip("._-")
    return (sanitized or fallback)[:96]


def extract_first(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key in payload and payload[key]:
            return str(payload[key])
    return None


def event_name(payload: Dict[str, Any]) -> str:
    for key in ("hook_event_name", "event", "type", "hook"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def prompt_text(payload: Dict[str, Any]) -> str:
    for key in ("prompt", "input", "message", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = prompt_text(value)
            if nested:
                return nested
    return ""


def has_sentinel(text: str) -> bool:
    return STATE_SENTINEL.lower() in (text or "").lower()


def is_durable_correction_prompt(text: str) -> bool:
    low = (text or "").lower()
    if not low.strip() or has_sentinel(low):
        return False

    explicit_targets = [
        "agents.md",
        "agent.md",
        "skill.md",
        "skills/",
        ".codex/skills",
        "developer instructions",
        "instruction system",
        "instruction-system",
        "hooks.json",
        "command hook",
        "lifecycle hook",
        "hook script",
        "self improvement",
        "self-improvement",
    ]
    verbs = [
        "update",
        "improve",
        "consolidate",
        "slim",
        "simplify",
        "fix",
        "tighten",
        "refactor",
        "revise",
        "adjust",
        "edit",
        "change",
        "correct",
        "harden",
    ]
    recurrence_phrases = [
        "you keep",
        "agent keeps",
        "agents keep",
        "model keeps",
        "same mistake",
        "every time you",
        "again you",
        "have to babysit",
        "manual cracking the whip",
    ]
    failure_signals = [
        "wrong",
        "incorrect",
        "broken",
        "fails",
        "failure",
        "bug",
        "buggy",
        "missing",
        "drift",
        "inconsistent",
        "no autonomy",
        "zero autonomy",
    ]

    has_target = any(token in low for token in explicit_targets)
    has_verb = any(f" {v} " in f" {low} " for v in verbs)
    if has_target and has_verb:
        return True

    has_recurrence = any(phrase in low for phrase in recurrence_phrases)
    has_failure = any(signal in low for signal in failure_signals)
    return has_recurrence and has_failure


def is_safe_path(path: Path) -> bool:
    try:
        cursor = path
        while cursor and cursor.parent != cursor:
            if cursor.exists() and cursor.is_symlink():
                return False
            cursor = cursor.parent
        return True
    except Exception:
        return False


def state_filename(session_id: Optional[str], turn_id: Optional[str], codex_home: Optional[Path] = None) -> Path:
    home = codex_home or get_codex_home()
    key = f"{sanitize_token(session_id, 'session')}_{sanitize_token(turn_id, 'turn')}"
    return home / STATE_DIR_NAME / f"{key}.json"


def state_base(home: Optional[Path] = None) -> Path:
    return (home or get_codex_home()) / STATE_DIR_NAME


def state_path_for_session_turn(home: Path, session_id: str, turn_id: str) -> Path:
    return state_filename(session_id, turn_id, home)


def parse_created_at(path: Path) -> Optional[float]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("created_at")
        if not isinstance(raw, str):
            return None
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        return None


def cleanup_stale_state_files(home: Path) -> None:
    base = state_base(home)
    if not base.exists() or not is_safe_path(base):
        return

    cutoff = now_unix() - STATE_TTL_SECONDS
    for path in base.glob("*.json"):
        created = parse_created_at(path)
        if created is None or created < cutoff:
            try:
                path.unlink()
            except Exception:
                pass


def read_state(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_state_atomic(path: Path, payload: Dict[str, Any]) -> bool:
    if not is_safe_path(path):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()
        return True
    except Exception:
        return False


def delete_state(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def find_stale_or_exact_state(home: Path, session_id: str, turn_id: Optional[str]) -> Optional[Path]:
    cleanup_stale_state_files(home)
    if not is_safe_path(state_base(home)):
        return None

    base = state_base(home)
    if not base.exists():
        return None

    if turn_id:
        exact = state_path_for_session_turn(home, session_id, turn_id)
        if exact.exists():
            return exact
        return None

    prefix = f"{sanitize_token(session_id)}_"
    matches = []
    for path in base.glob("*.json"):
        if path.name.startswith(prefix):
            state = read_state(path)
            if not state:
                continue
            created = parse_created_at(path)
            if created is None:
                continue
            if created >= (now_unix() - STATE_TTL_SECONDS):
                matches.append(path)
    if len(matches) != 1:
        return None
    return matches[0]


def state_payload(event: str, payload: Dict[str, Any], turn_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "event": event,
        "session_id": extract_first(payload, ["session_id", "sessionId", "session"]),
        "turn_id": turn_id or extract_first(payload, ["turn_id", "turnId", "turn"]),
        "created_at": now_ts(),
        "hook_event": extract_first(payload, ["hook_event_name", "event", "type"]),
        "created_unix": now_unix(),
        "stop_hook_active": bool(payload.get("stop_hook_active")),
    }


def log_path(home: Optional[Path] = None) -> Path:
    return (home or get_codex_home()) / LOG_PATH_NAME


def rotate_log_if_needed(path: Path) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= MAX_LOG_BYTES:
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    lines = lines[-MAX_LOG_LINES:]
    while len(lines) > 1 and len(("\n".join(lines) + "\n").encode("utf-8")) > MAX_LOG_BYTES:
        lines.pop(0)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def log_entry(event: str, payload: Dict[str, Any], result: Dict[str, Any], codex_home: Optional[Path] = None) -> None:
    path = log_path(codex_home)
    if not is_safe_path(path):
        return
    data = {
        "timestamp": now_ts(),
        "event": event,
        "session_id": extract_first(payload, ["session_id", "sessionId", "session"]),
        "turn_id": extract_first(payload, ["turn_id", "turnId", "turn"]),
        "result": result,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        rotate_log_if_needed(path)
    except Exception:
        return


def build_context() -> str:
    return (
        f"{ADDITIONAL_CONTEXT_PREFIX}\n"
        "Use the exact standalone line format:\n"
        "Instruction learning: <scope, evidence, rationale, next step>"
    )


def userprompt_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = prompt_text(payload)
    if not is_durable_correction_prompt(prompt):
        return {}

    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    turn = extract_first(payload, ["turn_id", "turnId", "turn"]) or now_ts().replace(":", "-")
    home = get_codex_home()
    path = state_filename(session, turn, home)
    state = state_payload("UserPromptSubmit", payload, turn_id=turn)
    if not write_state_atomic(path, state):
        return {}
    log_entry("UserPromptSubmit", payload, {"state": path.name, "status": "stored"}, home)

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": build_context(),
        }
    }


def last_assistant_message(payload: Dict[str, Any]) -> str:
    direct = extract_first(payload, ["last_assistant_message", "assistant_message", "lastAssistantMessage"])
    if direct:
        return direct
    messages = payload.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict):
                role = str(item.get("role", "")).lower()
                content = item.get("content", "")
                if role == "assistant" and isinstance(content, str):
                    return content
    return ""


def has_disposition_marker(text: str) -> bool:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return any(
        re.fullmatch(r"instruction learning:\s*\S.*", line, re.IGNORECASE)
        for line in lines
    )


def stop_hook(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("stop_hook_active"):
        return {}

    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    turn = extract_first(payload, ["turn_id", "turnId", "turn"])
    home = get_codex_home()
    state_path = find_stale_or_exact_state(home, session, turn)
    if state_path is None:
        return {}

    delete_state(state_path)
    marker_present = has_disposition_marker(last_assistant_message(payload))
    if marker_present:
        log_entry("Stop", payload, {"state": state_path.name, "decision": "allow"}, home)
        return {}

    log_entry(
        "Stop",
        payload,
        {"state": state_path.name, "decision": "block"},
        home,
    )
    return {
        "decision": "block",
        "reason": "[instruction-learning-hook] Include the required final marker before stop proceeds.",
    }


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    evt = event_name(payload).strip().lower()
    if evt == "userpromptsubmit":
        return userprompt_submit(payload)
    if evt == "stop":
        return stop_hook(payload)
    return {}


def main() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return handle(payload)
    except Exception:
        return {}


if __name__ == "__main__":
    output = main()
    if output:
        print(json.dumps(output))
    else:
        print("{}")
