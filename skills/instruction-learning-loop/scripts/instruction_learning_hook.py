#!/usr/bin/env python3

"""Command-hook handler for durable instruction-system prompts."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import secrets
import stat
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
ERROR_LEARNING_DIR_NAME = "hooks/state/instruction-learning/error-learning"
ERROR_LEARNING_KEY_NAME = "error-learning.key"
ERROR_LEARNING_INTEGRITY_NAME = "error-learning.key.sha256"
ERROR_RECOVERY_KEY_NAME = "error-learning.recovery.key"
ERROR_RECOVERY_INTEGRITY_NAME = "error-learning.recovery.key.sha256"
ERROR_EVENT_DIR_NAME = "events"
ERROR_ATTEMPT_DIR_NAME = "attempts"
ERROR_COMPLETION_DIR_NAME = "completions"
ERROR_FAILURE_DIR_NAME = "failures"
ERROR_KEYLESS_DIR_NAME = "keyless"
ERROR_GLOBAL_FAILURE_NAME = "keyless-user-report.pending"
ERROR_KEY_BYTES = 32
ERROR_KEY_READ_RETRIES = 100
ERROR_KEY_READ_RETRY_SECONDS = 0.01
ERROR_ATTEMPT_TTL_SECONDS = 24 * 60 * 60
OPAQUE_ID_RE = re.compile(r"^[0-9a-f]{64}$")
LEADING_DIAGNOSTIC_RE = re.compile(
    r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:check|verify|determine|confirm|see|find\s+out)\s+(?:if|whether)\b"
)
ERROR_EVENT_FIELDS = {
    "user_report": {"kind", "session_hash", "generation", "event_id", "created_unix_ns"},
    "confirmation": {
        "kind", "session_hash", "generation", "baseline", "project_root",
        "event_id", "created_unix_ns",
    },
    "completed": {"kind", "session_hash", "generation", "event_id", "created_unix_ns"},
    "candidate_resolution": {
        "kind", "session_hash", "turn_hash", "attempt_hash",
        "prior_attempt_hashes", "candidate_hash", "event_id", "created_unix_ns",
    },
    "technical_verification": {
        "kind", "session_hash", "generation", "turn_hash", "attempt_hash",
        "event_id", "created_unix_ns",
    },
}
PROVISIONAL_CONFIRMATION_STATEMENT = (
    "Technical verification passed, but real-world resolution and instruction "
    "learning are awaiting your confirmation."
)
ACTION_CONTEXT = (
    "This prompt contains behavioral guidance or an instruction-system correction. "
    "Use $instruction-learning-loop to form the smallest durable proposal and send it to an independent "
    "sol_advisor. If approved, implement it in the applicable user-owned AGENTS.md, skill, hook, agent "
    "direction, or config surface and verify it before finishing. If rejected, revise or replace the proposal "
    "from the advisor's rationale and resubmit it until a valid narrow change is approved. Treat valid in-scope "
    "review findings as implementation inputs, continue without renewed user approval, and reject or defer "
    "findings that require new scope or authority. "
    "A proposal alone is not completion."
)
READ_ONLY_CONTEXT = (
    "This prompt may contain behavioral guidance or an instruction-system correction, but the user explicitly "
    "made the task read-only. Use $instruction-learning-loop only to classify and report the possible durable "
    "improvement. Do not mutate instruction files or other user state."
)
ONE_OFF_PHRASES = ("for this task only", "this time only", "just this once", "one-off")
PLAN_DIRECTIVE_RE = re.compile(
    r"^(?:yes\s*,?\s+)?(?:please\s+)?implement\s+(?:the|this)\s+plan\s*"
    r"(?:(?P<terminal>[.!])|(?P<colon>:)(?:\s*(?P<body>.*))?)?$",
    re.IGNORECASE,
)
IMMEDIATE_REVERSAL_PREFIX_RE = re.compile(
    r"^(?:(?P<cancellation>(?:(?:actually|wait)\s*(?:[,;:]|-{1,2}|\N{EM DASH})?\s*)?(?:"
    r"never\s+mind\b|"
    r"cancel\s+(?:this\s+)?(?:request|task|plan|work)\b|"
    r"(?:do\s+not|don't|never)\s+implement\s+(?:this\s+plan|the\s+plan|it)\b"
    r"))|(?P<restriction>"
    r"keep\s+this(?:\s+(?:task|request|turn|work))?\s+read[- ]only\b|"
    r"(?:review|proposal)\s+only\b|"
    r"(?:do\s+not|don't|never)\s+(?:edit|change|modify)\s+(?:any\s+)?files\b|"
    r"no\s+(?:code|file|instruction)\s+(?:changes|edits)\b"
    r"))(?=\s*(?:$|[.,;:!?—–-]|\b(?:because|until|unless|while|before|after|for\s+now|pending)\b))",
    re.IGNORECASE,
)
DIRECTED_ACTION_RE = re.compile(
    r"(?:(?P<action_boundary>^|[;:]\s*)|(?P<countermand_then>\bthen\s+))"
    r"(?P<countermand_contrast>(?:(?:but|instead)\s+)?)(?:please\s+)?"
    r"(?P<action>implement|execute|proceed|continue|"
    r"resume|update|edit|change|modify|fix|correct|revise|adjust|create|add|remove|"
    r"write|patch|apply|document|run|validate|test|build|install)\b",
    re.IGNORECASE,
)
SEQUENCED_ACTION_RE = re.compile(
    r"\b(?:until\s+(?:after\s+)?|unless\s+|while\s+|before\s+|after\s+)"
    r"(?:please\s+)?(?:(?:you\s+)(?P<finite_action>implement|execute|proceed|continue|resume|"
    r"update|edit|change|modify|fix|correct|revise|adjust|create|add|remove|write|"
    r"patch|apply|document|run|validate|test|build|install)|(?P<gerund_action>implementing|"
    r"executing|proceeding|continuing|resuming|updating|editing|changing|modifying|"
    r"fixing|correcting|revising|adjusting|creating|adding|removing|writing|"
    r"patching|applying|documenting|running|validating|testing|building|installing))\b",
    re.IGNORECASE,
)
ACTION_CLAUSE_BOUNDARY_RE = re.compile(r";|\.(?=\s+\S|$)|[!?](?=\s+\S|$)")
ACTION_CLAUSE_AUXILIARY_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|has|have|had)\b",
    re.IGNORECASE,
)
ACTION_CLAUSE_SUBORDINATE_RE = re.compile(
    r"\s+(?:as|which|who|that|until|unless|when|while|after|before|because)\s+",
    re.IGNORECASE,
)
ACTION_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/\\?=-]*")
ACTION_RESOURCE_TOKEN_RE = re.compile(
    r"^(?:[A-Za-z]:[/\\]|https?://|.*\.[A-Za-z0-9]{1,12}(?:[?=].*)?)",
    re.IGNORECASE,
)
AMBIGUOUS_ACTION_FORMS = {
    "build", "building", "install", "installing", "patch", "patching",
    "run", "running", "test", "testing", "update", "updating",
}
NO_OBJECT_ACTION_FORMS = {"continue", "continuing", "proceed", "proceeding", "resume", "resuming"}
SINGLE_TOKEN_STATE_FORMS = {
    "blocked", "broke", "broken", "crashed", "crashes", "failed", "fails",
    "failing", "finishes", "green", "hangs", "hung", "incomplete", "pending",
    "red", "stalled", "succeeds",
}
AMBIGUOUS_PRESENT_STATE_FORMS = {
    "abort", "aborts", "complete", "completes", "crash", "crashes", "error",
    "errors", "fail", "fails", "finish", "finishes", "hang", "hangs", "pass",
    "passes", "stall", "stalls", "succeed", "succeeds",
}
IRREGULAR_STATE_FORMS = {"blocked", "broke", "broken", "down", "hung", "incomplete", "pending", "red", "green"}
ELLIPTICAL_MODIFIER_FORMS = {
    "accepted", "approved", "assigned", "described", "discussed", "documented",
    "expected", "generated", "identified", "listed", "mentioned", "noted",
    "planned", "proposed", "provided", "reported", "requested", "required",
    "selected", "specified",
}
QUALIFYING_SUFFIX_RE = re.compile(
    r"^(?:because|until|unless|while|before|after|for\s+now|pending)\b",
    re.IGNORECASE,
)
ACTION_AWARE_QUALIFYING_SUFFIX_RE = re.compile(
    r"^(?:until|unless|while|before|after)\b",
    re.IGNORECASE,
)
NO_CODE_CHANGES_PREFIX_RE = re.compile(
    r"^no\s+code\s+(?:changes|edits)\b",
    re.IGNORECASE,
)
INSTRUCTION_ACTION_RE = re.compile(
    r"\b(?:update|improve|fix|tighten|revise|adjust|edit|change|modify|correct|harden|"
    r"consolidate|simplify|refactor)\s+"
    r"(?:the\s+)?(?:global\s+|local\s+|project\s+|nested\s+)?"
    r"(?:agents?\.md|skills?\b|hooks?\b|config(?:\.toml)?\b|agent direction\b|"
    r"instruction(?: system|-system|s)?\b)",
    re.IGNORECASE,
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


def action_match_is_unambiguous(
    text: str,
    match: re.Match[str],
    *,
    allow_subordinate: bool = False,
    require_explicit_countermand: bool = False,
) -> bool:
    tail = text[match.end():]
    boundary = ACTION_CLAUSE_BOUNDARY_RE.search(tail)
    clause = tail[:boundary.start()] if boundary else tail
    subordinate = ACTION_CLAUSE_SUBORDINATE_RE.search(clause)
    explicit_countermand = any(
        name in match.re.groupindex and bool(match.group(name))
        for name in ("countermand_then", "countermand_contrast")
    )
    if require_explicit_countermand and not explicit_countermand:
        return False
    if subordinate and not (allow_subordinate or explicit_countermand):
        return False
    main_clause = clause[:subordinate.start()] if subordinate else clause
    action = next(
        (match.group(name) for name in ("action", "finite_action", "gerund_action")
         if name in match.re.groupindex and match.group(name)),
        "",
    ).lower()
    if ACTION_CLAUSE_AUXILIARY_RE.search(main_clause):
        return False
    tokens = [token.lower() for token in ACTION_TOKEN_RE.findall(main_clause)]
    has_determiner = bool(tokens and tokens[0] in {
        "a", "an", "the", "this", "that", "these", "those", "my", "your", "our", "its",
    })
    if has_determiner:
        tokens = tokens[1:]
    if not tokens:
        return action in NO_OBJECT_ACTION_FORMS
    if len(tokens) == 1:
        return not (
            action in AMBIGUOUS_ACTION_FORMS
            and tokens[0] in SINGLE_TOKEN_STATE_FORMS
        )
    if (
        action in AMBIGUOUS_ACTION_FORMS
        and not has_determiner
        and ACTION_RESOURCE_TOKEN_RE.match(tokens[0]) is None
    ):
        return False
    predicate = tokens[-1]
    if predicate.endswith("ly") and len(tokens) > 2:
        predicate = tokens[-2]
    if predicate in ELLIPTICAL_MODIFIER_FORMS:
        return True
    if len(tokens) >= 2 and tokens[-2:] == ["timed", "out"]:
        return False
    if predicate in IRREGULAR_STATE_FORMS or predicate.endswith("ed"):
        return False
    if action in AMBIGUOUS_ACTION_FORMS and predicate in AMBIGUOUS_PRESENT_STATE_FORMS:
        return False
    return True


def has_unambiguous_action(
    text: str,
    pattern: re.Pattern[str],
    *,
    allow_subordinate: bool = False,
    require_explicit_countermand: bool = False,
) -> bool:
    return any(
        action_match_is_unambiguous(
            text,
            match,
            allow_subordinate=allow_subordinate,
            require_explicit_countermand=require_explicit_countermand,
        )
        for match in pattern.finditer(text)
    )


def is_immediate_whole_task_reversal(text: str) -> bool:
    body = (text or "").strip()
    match = IMMEDIATE_REVERSAL_PREFIX_RE.match(body)
    if match is None:
        return False
    raw_remainder = body[match.end():].strip()
    if not raw_remainder or re.fullmatch(r"[.!?]+", raw_remainder):
        return True
    separator_match = re.match(r"^(?P<separator>--|[,;:!?—–-])", raw_remainder)
    separator = separator_match.group("separator") if separator_match else ""
    remainder = re.sub(r"^[\s,;:!?—–-]+", "", raw_remainder).strip()
    if not remainder:
        return True
    if is_immediate_whole_task_reversal(remainder):
        return True
    if QUALIFYING_SUFFIX_RE.match(remainder):
        sequence_match = SEQUENCED_ACTION_RE.match(remainder)
        return (
            ACTION_AWARE_QUALIFYING_SUFFIX_RE.match(remainder) is None
            or sequence_match is None
            or not action_match_is_unambiguous(
                remainder,
                sequence_match,
                allow_subordinate=True,
            )
        )
    is_restriction = match.group("restriction") is not None
    countermand_separators = {",", ":", "!", "?", "-", "--", "–", "—"}
    allow_subordinate = is_restriction and separator not in countermand_separators
    require_explicit_countermand = is_restriction and separator in countermand_separators
    return not (
        has_unambiguous_action(
            remainder,
            DIRECTED_ACTION_RE,
            allow_subordinate=allow_subordinate,
            require_explicit_countermand=require_explicit_countermand,
        )
        or has_unambiguous_action(
            remainder,
            SEQUENCED_ACTION_RE,
            allow_subordinate=allow_subordinate,
            require_explicit_countermand=require_explicit_countermand,
        )
    )


def is_plan_implementation_prompt(text: str) -> bool:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    match = PLAN_DIRECTIVE_RE.fullmatch(lines[0])
    if match is None:
        return False
    inline_body = (match.group("body") or "").strip()
    body_lines = ([inline_body] if inline_body else []) + lines[1:]
    if match.group("colon") and not body_lines:
        return False
    return not body_lines or not is_immediate_whole_task_reversal(body_lines[0])


def is_durable_correction_prompt(text: str) -> bool:
    low = (text or "").lower()
    if not low.strip() or has_sentinel(low) or any(phrase in low for phrase in ONE_OFF_PHRASES):
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
        "modify",
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
    has_verb = re.search(rf"\b(?:{'|'.join(map(re.escape, verbs))})\b", low) is not None
    if has_target and has_verb:
        return True

    redirect_patterns = [
        r"\bstop\s+(?:asking|handing|making|telling|requiring)\b",
        r"\b(?:do not|don't|never)\s+(?:ask|hand|make|tell|require)\b",
        r"\bdo (?:it|that|the .*?) yourself\b",
    ]
    if any(re.search(pattern, low) for pattern in redirect_patterns):
        return True

    has_recurrence = any(phrase in low for phrase in recurrence_phrases)
    has_failure = any(signal in low for signal in failure_signals)
    return has_recurrence and has_failure


def explicitly_read_only(text: str) -> bool:
    low = (text or "").lower()
    if is_plan_implementation_prompt(text):
        return False
    if re.search(
        r"(?:\bkeep\s+this(?:\s+(?:task|request|turn|work))?\s+read[- ]only\b|"
        r"\bthis\s+(?:task|request|turn|work)\s+(?:is\s+)?read[- ]only\b)"
        r"(?=\s*(?:$|[.,;:!?]))",
        low,
    ):
        return True
    starts = [0] + [match.end() for match in re.finditer(r"[.!?]\s+", low)]
    for start in starts:
        candidate = low[start:].lstrip()
        if not is_immediate_whole_task_reversal(candidate):
            continue
        if (
            NO_CODE_CHANGES_PREFIX_RE.match(candidate)
            and has_explicit_instruction_action(text)
        ):
            continue
        return True
    if re.search(
        r"\b(?:do not|don't|never)\s+(?:change|edit|update|modify)\s+"
        r"(?:the\s+)?(?:agents?\.md|skills?\b|hooks?\b|config(?:\.toml)?\b|instructions?\b)",
        low,
    ) and not has_explicit_instruction_action(text):
        return True
    if re.search(
        r"\bno\s+(?:changes|edits)\s+(?:to|in)\s+"
        r"(?:the\s+)?(?:agents?\.md|skills?\b|hooks?\b|config(?:\.toml)?\b|instructions?\b)",
        low,
    ) and not has_explicit_instruction_action(text):
        return True
    if re.fullmatch(r"\s*(?:please\s+)?(?:make\s+)?no\s+(?:changes|edits)[.!]?\s*", low):
        return True
    return False


def has_explicit_instruction_action(text: str) -> bool:
    low = (text or "").lower()
    for match in INSTRUCTION_ACTION_RE.finditer(low):
        prefix = low[max(0, match.start() - 20):match.start()]
        if re.search(r"(?:\bdo\s+not|\bdon't|\bnever)\s+$", prefix):
            continue
        return True
    return False


def requires_instruction_change(text: str) -> bool:
    if not is_durable_correction_prompt(text) or explicitly_read_only(text):
        return False
    if has_explicit_instruction_action(text):
        return True
    review_intent = re.match(
        r"\s*(?:(?:please|kindly)\s+|(?:can|could|would|will)\s+you\s+)*"
        r"(?:review|explain|classify|assess|analy[sz]e|summarize|inspect)\b",
        text or "",
        re.IGNORECASE,
    )
    return review_intent is None


def instruction_files(home: Path, project_root: Optional[Path] = None) -> Iterable[Path]:
    seen = set()

    def is_test_or_evaluation_artifact(path: Path, classification_root: Path) -> bool:
        try:
            relative = path.relative_to(classification_root)
        except ValueError:
            relative = Path(path.name)
        parts = {part.lower() for part in relative.parts[:-1]}
        if parts.intersection(
            {"test", "tests", "fixture", "fixtures", "testdata", "test-data", "evaluation-inputs"}
        ):
            return True
        name = path.name.lower()
        stem = path.stem.lower()
        return (
            name == "conftest.py"
            or stem.startswith(("test_", "test-", "evaluation_", "evaluation-"))
            or stem.endswith(("_test", "-test"))
            or "self_test" in stem
            or "self-test" in stem
        )

    def emit(path: Path, classification_root: Path) -> Iterable[Path]:
        if is_test_or_evaluation_artifact(path, classification_root):
            return
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            return
        key = os.path.normcase(str(resolved))
        if resolved.is_file() and key not in seen and is_safe_path(resolved):
            seen.add(key)
            yield resolved

    direct = (home / "AGENTS.md", home / "config.toml", home / "hooks.json")
    for path in direct:
        yield from emit(path, home)
    roots = (home / "agents", home / "skills")
    allowed_names = {"AGENTS.md", "SKILL.md"}
    allowed_suffixes = {".py", ".toml", ".yaml", ".yml", ".json"}
    for root in roots:
        if not root.is_dir() or not is_safe_path(root):
            continue
        for path in root.rglob("*"):
            if path.is_file() and (path.name in allowed_names or path.suffix.lower() in allowed_suffixes):
                yield from emit(path, home)

    if project_root is None or not project_root.is_dir() or not is_safe_path(project_root):
        return
    cursor = project_root
    while True:
        yield from emit(cursor / "AGENTS.md", project_root)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for path in project_root.rglob("AGENTS.md"):
        yield from emit(path, project_root)
    project_skills = project_root / ".agents" / "skills"
    if project_skills.is_dir() and is_safe_path(project_skills):
        for path in project_skills.rglob("SKILL.md"):
            yield from emit(path, project_root)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def instruction_snapshot(home: Path, project_root: Optional[Path] = None) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for path in instruction_files(home, project_root):
        try:
            key = os.path.normcase(str(path.resolve(strict=True)))
            snapshot[key] = file_sha256(path)
        except (OSError, RuntimeError):
            continue
    return snapshot


def is_safe_path(path: Path) -> bool:
    try:
        cursor = path
        while cursor and cursor.parent != cursor:
            if cursor.is_symlink():
                return False
            if cursor.exists():
                is_junction = getattr(cursor, "is_junction", None)
                if callable(is_junction) and is_junction():
                    return False
                metadata = os.lstat(cursor)
                attributes = getattr(metadata, "st_file_attributes", 0)
                reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                if attributes & reparse_flag:
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


def error_learning_base(home: Optional[Path] = None) -> Path:
    return (home or get_codex_home()) / ERROR_LEARNING_DIR_NAME


def error_learning_key_path(home: Optional[Path] = None) -> Path:
    return error_learning_base(home) / ERROR_LEARNING_KEY_NAME


def error_learning_integrity_path(home: Optional[Path] = None) -> Path:
    return error_learning_base(home) / ERROR_LEARNING_INTEGRITY_NAME


def error_learning_recovery_key_path(home: Optional[Path] = None) -> Path:
    return error_learning_base(home) / ERROR_RECOVERY_KEY_NAME


def error_learning_recovery_integrity_path(home: Optional[Path] = None) -> Path:
    return error_learning_base(home) / ERROR_RECOVERY_INTEGRITY_NAME


def _dynamic_state_exists(home: Path) -> bool:
    base = error_learning_base(home)
    if not base.is_dir():
        return False
    if not is_safe_path(base):
        return True
    ignored = {
        ERROR_LEARNING_KEY_NAME,
        ERROR_LEARNING_INTEGRITY_NAME,
        ERROR_RECOVERY_KEY_NAME,
        ERROR_RECOVERY_INTEGRITY_NAME,
    }
    return any(path.name not in ignored for path in base.iterdir())


def _keyed_dynamic_state_exists(home: Path) -> bool:
    """Return whether state tied to an existing HMAC key is persisted."""
    base = error_learning_base(home)
    if not base.is_dir():
        return False
    if not is_safe_path(base):
        return True
    ignored = {
        ERROR_LEARNING_KEY_NAME,
        ERROR_LEARNING_INTEGRITY_NAME,
        ERROR_RECOVERY_KEY_NAME,
        ERROR_RECOVERY_INTEGRITY_NAME,
    }
    for path in base.iterdir():
        if path.name in ignored:
            continue
        if not is_safe_path(path):
            return True
        if path.name == ERROR_FAILURE_DIR_NAME and path.is_dir():
            try:
                entries = list(path.iterdir())
            except OSError:
                return True
            ignored_failures = {ERROR_GLOBAL_FAILURE_NAME, ERROR_KEYLESS_DIR_NAME}
            if not entries or all(entry.name in ignored_failures for entry in entries):
                continue
        return True
    return False


def _write_integrity_file(path: Path, key: bytes) -> bool:
    digest = hashlib.sha256(key).hexdigest()
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(digest)
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except FileExistsError:
        try:
            return path.read_text(encoding="ascii").strip() == digest
        except OSError:
            return False
    except Exception:
        return False


def _write_key_integrity(home: Path, key: bytes) -> bool:
    return _write_integrity_file(error_learning_integrity_path(home), key)


def error_learning_key(home: Optional[Path] = None) -> Optional[bytes]:
    """Return the local HMAC key, creating it atomically without overwriting malformed state."""
    path = error_learning_key_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() and _keyed_dynamic_state_exists(home):
            return None
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError:
            for _ in range(ERROR_KEY_READ_RETRIES):
                try:
                    raw = path.read_bytes()
                except OSError:
                    raw = b""
                if len(raw) == ERROR_KEY_BYTES:
                    integrity = error_learning_integrity_path(home)
                    if integrity.exists():
                        try:
                            if integrity.read_text(encoding="ascii").strip() != hashlib.sha256(raw).hexdigest():
                                return None
                        except OSError:
                            return None
                    elif _keyed_dynamic_state_exists(home):
                        return None
                    elif not _write_key_integrity(home, raw):
                        return None
                    return raw
                # A concurrent creator may have opened but not flushed yet. A
                # persistently malformed key is never overwritten or replaced.
                time.sleep(ERROR_KEY_READ_RETRY_SECONDS)
            return None
        key = secrets.token_bytes(ERROR_KEY_BYTES)
        with os.fdopen(fd, "wb") as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        if not _write_key_integrity(home, key):
            return None
        return key
    except Exception:
        return None


def _keyless_root(home: Path) -> Path:
    return error_learning_base(home) / ERROR_FAILURE_DIR_NAME / ERROR_KEYLESS_DIR_NAME


def _keyless_state_exists(home: Path) -> bool:
    root = _keyless_root(home)
    if not root.exists():
        return False
    if not root.is_dir() or not is_safe_path(root):
        return True
    try:
        return any(root.iterdir())
    except OSError:
        return True


def error_learning_recovery_key(home: Optional[Path] = None) -> Optional[bytes]:
    """Return the independent key used only to identify keyless user reports."""
    home = home or get_codex_home()
    path = error_learning_recovery_key_path(home)
    integrity = error_learning_recovery_integrity_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() and _keyless_state_exists(home):
            return None
        try:
            fd = os.open(
                str(path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            for _ in range(ERROR_KEY_READ_RETRIES):
                try:
                    raw = path.read_bytes()
                except OSError:
                    raw = b""
                if len(raw) == ERROR_KEY_BYTES:
                    if integrity.exists():
                        try:
                            if integrity.read_text(encoding="ascii").strip() != hashlib.sha256(raw).hexdigest():
                                return None
                        except OSError:
                            return None
                    elif _keyless_state_exists(home):
                        return None
                    elif not _write_integrity_file(integrity, raw):
                        return None
                    return raw
                time.sleep(ERROR_KEY_READ_RETRY_SECONDS)
            return None
        key = secrets.token_bytes(ERROR_KEY_BYTES)
        with os.fdopen(fd, "wb") as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        if not _write_integrity_file(integrity, key):
            return None
        return key
    except Exception:
        return None


def opaque_identity(value: Any, key: Optional[bytes]) -> Optional[str]:
    if key is None:
        return None
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def _error_dir(home: Path, name: str) -> Path:
    return error_learning_base(home) / name


def _error_event_dir(home: Path, session_hash: str) -> Path:
    return _error_dir(home, ERROR_EVENT_DIR_NAME) / session_hash


def _authority_failure_path(home: Path, session_hash: str) -> Path:
    return _error_dir(home, ERROR_FAILURE_DIR_NAME) / session_hash


def _global_authority_failure_path(home: Path) -> Path:
    return _error_dir(home, ERROR_FAILURE_DIR_NAME) / ERROR_GLOBAL_FAILURE_NAME


def _mark_global_authority_failure(home: Path) -> bool:
    path = _global_authority_failure_path(home)
    if not is_safe_path(path):
        return False
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def _global_authority_failed(home: Path) -> bool:
    path = _global_authority_failure_path(home)
    return path.exists() or not is_safe_path(path)


def _keyless_report_paths(
    home: Path,
    session: str,
    prompt: str,
    key: bytes,
) -> tuple[Path, Path]:
    session_hash = opaque_identity({"scope": "keyless-session", "session": session}, key)
    report_hash = opaque_identity(
        {"scope": "keyless-report", "session": session, "prompt": prompt},
        key,
    )
    if not session_hash or not report_hash:
        raise ValueError("keyless report identity unavailable")
    session_dir = _keyless_root(home) / session_hash
    return session_dir, session_dir / report_hash


def _mark_keyless_report(home: Path, session: str, prompt: str) -> bool:
    if not session or session == "unknown":
        _mark_global_authority_failure(home)
        return False
    key = error_learning_recovery_key(home)
    if key is None:
        _mark_global_authority_failure(home)
        return False
    try:
        session_dir, report_dir = _keyless_report_paths(home, session, prompt, key)
        if not is_safe_path(report_dir):
            _mark_global_authority_failure(home)
            return False
        session_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(exist_ok=True)
        return True
    except Exception:
        _mark_global_authority_failure(home)
        return False


def _clear_keyless_reports_for_session(home: Path, session: str) -> None:
    if not session or session == "unknown":
        return
    key = error_learning_recovery_key(home)
    if key is None:
        return
    try:
        root = _keyless_root(home)
        if not root.is_dir() or not is_safe_path(root):
            return
        session_hash = opaque_identity({"scope": "keyless-session", "session": session}, key)
        if not session_hash:
            return
        session_dir = root / session_hash
        if not session_dir.is_dir() or not is_safe_path(session_dir):
            return
        reports = list(session_dir.iterdir())
        if not reports or any(
            not report.is_dir()
            or not _is_opaque_id(report.name)
            or not is_safe_path(report)
            or any(report.iterdir())
            for report in reports
        ):
            return
        for report in reports:
            if not report.is_dir() or not is_safe_path(report) or any(report.iterdir()):
                return
            report.rmdir()
        if not session_dir.is_dir() or not is_safe_path(session_dir) or any(session_dir.iterdir()):
            return
        session_dir.rmdir()
        if root.is_dir() and is_safe_path(root) and not any(root.iterdir()):
            root.rmdir()
        failure_root = root.parent
        if failure_root.is_dir() and is_safe_path(failure_root) and not any(failure_root.iterdir()):
            failure_root.rmdir()
    except OSError:
        return


def _keyless_authority_status(home: Path, session: str) -> str:
    """Return clear, pending, or invalid for keyless reports in this session."""
    if _global_authority_failed(home):
        return "invalid"
    root = _keyless_root(home)
    if not root.exists():
        return "clear"
    if not root.is_dir() or not is_safe_path(root):
        return "invalid"
    try:
        sessions = list(root.iterdir())
    except OSError:
        return "invalid"
    if any(not entry.is_dir() or not _is_opaque_id(entry.name) for entry in sessions):
        return "invalid"
    key = error_learning_recovery_key(home)
    if key is None:
        return "invalid"
    session_hash = opaque_identity({"scope": "keyless-session", "session": session}, key)
    if not session_hash:
        return "invalid"
    session_dir = root / session_hash
    if not session_dir.exists():
        return "clear"
    if not session_dir.is_dir() or not is_safe_path(session_dir):
        return "invalid"
    try:
        reports = list(session_dir.iterdir())
    except OSError:
        return "invalid"
    if not reports or any(not entry.is_dir() or not _is_opaque_id(entry.name) for entry in reports):
        return "invalid"
    return "pending"


def _mark_authority_failure(
    home: Path,
    session_hash: str,
    event_id: Optional[str] = None,
) -> Optional[Path]:
    """Create a content-free, directory-backed transition intent.

    This deliberately does not share the event writer: if the exclusive JSON
    write fails, the intent directory remains and makes later Stop evaluation
    fail closed. Each deterministic event owns its own directory so concurrent
    transitions cannot clear one another's failure state.
    """
    directory = _authority_failure_path(home, session_hash)
    if not is_safe_path(directory):
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if event_id is None:
            return directory
        pending = directory / event_id
        pending.mkdir(exist_ok=True)
        return pending
    except Exception:
        return None


def _clear_authority_failure(pending: Optional[Path]) -> None:
    if pending is None:
        return
    try:
        pending.rmdir()
        pending.parent.rmdir()
    except OSError:
        # Another failed/in-flight transition, or an I/O failure, keeps the
        # session fail-closed.
        return


def _authority_pending_ids(
    home: Path,
    session_hash: Optional[str],
) -> Optional[set[str]]:
    if not session_hash:
        return set()
    path = _authority_failure_path(home, session_hash)
    if not path.exists():
        return set() if is_safe_path(path) else None
    if not path.is_dir() or not is_safe_path(path):
        return None
    try:
        entries = list(path.iterdir())
    except OSError:
        return None
    if not entries or any(not entry.is_dir() or not _is_opaque_id(entry.name) for entry in entries):
        return None
    return {entry.name for entry in entries}


def _authority_failed(home: Path, session_hash: Optional[str]) -> bool:
    pending = _authority_pending_ids(home, session_hash)
    return pending is None or bool(pending)


def _tool_state_dir(
    home: Path,
    name: str,
    session_hash: str,
    turn_hash: str,
) -> Path:
    return _error_dir(home, name) / session_hash / turn_hash


def _write_json_exclusive(path: Path, payload: Dict[str, Any]) -> bool:
    if not is_safe_path(path):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                str(path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            return False
        return True
    except Exception:
        return False


def _append_error_event(
    home: Path,
    event: Dict[str, Any],
    *,
    event_id: Optional[str] = None,
) -> Optional[str]:
    key = error_learning_key(home)
    if key is None:
        return None
    event_id = event_id or opaque_identity(
        f"{time.time_ns()}:{secrets.token_hex(12)}",
        key,
    )
    if not isinstance(event_id, str) or not OPAQUE_ID_RE.fullmatch(event_id):
        return None
    event = dict(event)
    session_hash = event.get("session_hash")
    if not isinstance(session_hash, str) or not OPAQUE_ID_RE.fullmatch(session_hash):
        return None
    event["event_id"] = event_id
    event["created_unix_ns"] = time.time_ns()
    if not _valid_error_event(
        event,
        event_id=event_id,
        session_hash=session_hash,
    ):
        return None
    path = _error_event_dir(home, session_hash) / f"{event_id}.json"
    pending = None
    if event.get("kind") in {"user_report", "confirmation", "completed"}:
        pending = _mark_authority_failure(home, session_hash, event_id)
        if pending is None:
            return None
    expected = {key: value for key, value in event.items() if key != "created_unix_ns"}

    def existing_matches() -> bool:
        existing = read_state(path)
        return bool(
            isinstance(existing, dict)
            and _valid_error_event(existing, event_id=event_id, session_hash=session_hash)
            and all(existing.get(key) == value for key, value in expected.items())
        )

    if path.exists():
        if existing_matches():
            _clear_authority_failure(pending)
            return event_id
        return None
    if not _write_json_exclusive(path, event):
        # A concurrent identical transition may have won O_EXCL between the
        # existence check and our write. Treat only an exact valid record as
        # the same idempotent transition.
        if path.exists() and existing_matches():
            _clear_authority_failure(pending)
            return event_id
        return None
    _clear_authority_failure(pending)
    return event_id


def _is_opaque_id(value: Any) -> bool:
    return isinstance(value, str) and bool(OPAQUE_ID_RE.fullmatch(value))


def _valid_error_event(
    event: Dict[str, Any],
    *,
    event_id: str,
    session_hash: str,
) -> bool:
    kind = event.get("kind")
    expected_fields = ERROR_EVENT_FIELDS.get(kind)
    if expected_fields is None or set(event) != expected_fields:
        return False
    created = event.get("created_unix_ns")
    if (
        event.get("event_id") != event_id
        or event.get("session_hash") != session_hash
        or not _is_opaque_id(event_id)
        or not isinstance(created, int)
        or isinstance(created, bool)
        or created < 0
    ):
        return False
    for field in ("generation", "turn_hash", "attempt_hash", "candidate_hash"):
        if field in event and not _is_opaque_id(event[field]):
            return False
    if kind == "candidate_resolution":
        prior = event.get("prior_attempt_hashes")
        if (
            event.get("candidate_hash") != event_id
            or not isinstance(prior, list)
            or not prior
            or prior != sorted(set(prior))
            or any(not _is_opaque_id(item) for item in prior)
        ):
            return False
    if kind == "confirmation":
        baseline = event.get("baseline")
        project_root = event.get("project_root")
        if (
            not isinstance(baseline, dict)
            or any(
                not isinstance(path, str) or not _is_opaque_id(digest)
                for path, digest in baseline.items()
            )
            or (project_root is not None and not isinstance(project_root, str))
        ):
            return False
    return True


def _error_events(
    home: Path,
    session_hash: Optional[str] = None,
) -> Optional[list[Dict[str, Any]]]:
    if session_hash is None:
        root = _error_dir(home, ERROR_EVENT_DIR_NAME)
        if not root.is_dir() or not is_safe_path(root):
            return []
        combined: list[Dict[str, Any]] = []
        for directory in root.iterdir():
            if not directory.is_dir() or not _is_opaque_id(directory.name):
                continue
            events = _error_events(home, directory.name)
            if events is not None:
                combined.extend(events)
        return sorted(
            combined,
            key=lambda item: (item["created_unix_ns"], item["event_id"]),
        )
    if not _is_opaque_id(session_hash):
        return None
    directory = _error_event_dir(home, session_hash)
    events: list[Dict[str, Any]] = []
    if not directory.exists():
        return events
    if not directory.is_dir() or not is_safe_path(directory):
        return None
    for path in directory.glob("*.json"):
        event = read_state(path)
        if not isinstance(event, dict) or not _valid_error_event(
            event,
            event_id=path.stem,
            session_hash=session_hash,
        ):
            return None
        events.append(event)
    return sorted(
        events,
        key=lambda item: (item["created_unix_ns"], item["event_id"]),
    )


def _error_fold(home: Path, session_hash: str) -> Dict[str, Any]:
    current: Dict[str, Any] = {}
    events = _error_events(home, session_hash)
    if events is None:
        return {"status": "invalid"}
    for event in events:
        kind = event.get("kind")
        if kind == "user_report":
            current = {"generation": event.get("generation"), "status": "awaiting"}
        elif kind == "confirmation" and event.get("generation") == current.get("generation"):
            current.update({"status": "confirmed", "baseline": event.get("baseline", {}), "project_root": event.get("project_root")})
        elif kind == "completed" and event.get("generation") == current.get("generation"):
            current["status"] = "completed"
    return current


def _error_context(
    text: str,
    event_name: str = "UserPromptSubmit",
) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }


def _error_diagnostic() -> Dict[str, Any]:
    return {
        "systemMessage": (
            "[instruction-learning-hook] Dynamic error learning is unavailable "
            "because local identity or authority persistence could not be verified. "
            "Do not claim resolution or finalize instruction learning."
        )
    }


def _wholly_quoted(text: str) -> bool:
    stripped = (text or "").strip()
    return len(stripped) >= 2 and any(
        stripped.startswith(left) and stripped.endswith(right)
        for left, right in (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"))
    )


def _hypothetical_or_example(text: str) -> bool:
    lowered = " ".join((text or "").strip().lower().split())
    historical_when = bool(
        lowered.startswith("when ")
        and re.search(
            r"\b(?:tested|ran|got|saw|hit|encountered|received|failed|crashed|"
            r"hung|timed\s+out|finished)\b",
            lowered.split(",", 1)[0],
        )
    )
    if historical_when:
        return False
    # A leading conditional/example frame is not converted into a live report,
    # even when it contains a first-person clause later in the sentence.
    if re.match(
        r"^(?:if|when|suppose|supposing|hypothetically|imagine|for\s+example|do\s+not\s+treat)\b",
        lowered,
    ):
        return True
    if LEADING_DIAGNOSTIC_RE.match(lowered):
        return True
    observed_first_person = bool(
        re.search(
            r"\b(?:i|we)\s+(?:got|get|have|see|saw|hit|encountered|received|"
            r"am\s+getting|keep\s+getting)\b",
            lowered,
        )
    )
    if observed_first_person:
        return False
    return bool(
        re.match(
            r"^(?:add|create|update|change|make|ensure|teach|configure)\b.*\b"
            r"(?:if|when)\b",
            lowered,
        )
    )


def _without_quoted_spans(text: str) -> str:
    return re.sub(
        r'"[^"\r\n]*"|“[^”\r\n]*”|‘[^’\r\n]*’|'
        r"(?<![\w])'(?:[^'\r\n]|(?<=\w)'(?=\w))*'(?![\w])|`[^`\r\n]*`",
        " ",
        text or "",
    )


def _without_leading_diagnostic_clause(text: str) -> str:
    match = LEADING_DIAGNOSTIC_RE.match(text)
    if not match:
        return text
    trailing = text[match.end():]
    boundary = re.search(
        r"[?!.;:](?:\s+|$)|\s+[—–-]\s+|"
        r",\s+(?:because|but|although|however,?|while|and)\s+",
        trailing,
    )
    return "" if boundary is None else trailing[boundary.end():].strip()


def _has_new_error_signal(text: str) -> bool:
    if not text or has_sentinel(text) or _wholly_quoted(text):
        return False
    unquoted = " ".join(_without_quoted_spans(text).strip().lower().split())
    unquoted = _without_leading_diagnostic_clause(unquoted)
    if not unquoted or _hypothetical_or_example(unquoted):
        return False
    return bool(re.search(
        r"\b(?:(?:i|we)\s+(?:(?:still|now)\s+)?(?:got|get|have|see|saw|hit|"
        r"encountered|received|(?:am|are)\s+(?:(?:still|now)\s+)?(?:getting|seeing)|"
        r"keep\s+getting)|"
        r"i['’]m\s+(?:(?:still|now)\s+)?(?:getting|seeing)|"
        r"we['’]re\s+(?:(?:still|now)\s+)?(?:getting|seeing))\s+(?:an?\s+|the\s+)?"
        r"(?:(?:same|another|new)\s+)?(?:(?:build|compile|compilation)\s+)?"
        r"(?:error|exception|failure|crash|timeout|roadblock|regression)\b|"
        r"\b(?:it|this|that)\s+(?:is\s+)?(?:still\s+)?(?:fails?|failed|failing|broken|"
        r"crashes?|crashed|crashing|hangs?|hung|time(?:d|s)?\s+out|didn['’]?t\s+work|"
        r"doesn['’]?t\s+work|isn['’]?t\s+fixed|will\s+not\s+compile|"
        r"won['’]?t\s+compile|cannot\s+compile|can['’]?t\s+compile)\b|"
        r"\b(?:the\s+)?(?:build|compile|compilation|tests?|command|app|application|"
        r"deployment|request|process)\s+(?:is\s+)?(?:(?:still|now)\s+)?(?:fails?|failed|"
        r"failing|broken|not\s+working|crashes?|crashed|crashing|hangs?|hung|"
        r"time(?:d|s)?\s+out|will\s+not\s+(?:build|compile|complete)|"
        r"won['’]?t\s+(?:build|compile|complete)|cannot\s+(?:build|compile|complete)|"
        r"can['’]?t\s+(?:build|compile|complete))\b|"
        r"\b(?:build|compile|command)\s+(?:returned|produced)\s+(?:an?\s+)?error\b|"
        r"\b(?:same|another|new)\s+(?:error|exception|failure|crash|regression)\b|"
        r"\b(?:the\s+)?(?:(?:build|compile|compilation)\s+)?"
        r"(?:error|exception|failure|timeout)\s+(?:is\s+)?(?:(?:still|now)\s+)?"
        r"(?:occurred|occurring|happened|happening|returned|present|persist(?:s|ing)?|"
        r"persisted(?![^.!?;\r\n]*(?:until|before)\s+(?:(?:this|the)\s+fix|"
        r"you\s+fixed\s+it)))\b|"
        r"\b(?:the\s+)?(?:(?:build|compile|compilation)\s+)?"
        r"(?:error|exception|failure|timeout)\s+persisted\b[^.!?;\r\n]*?"
        r"\b(?:and|but)\s+(?:it\s+)?is\s+(?:still|now)\s+(?:failing|broken|"
        r"not\s+working|present|occurring|happening|persisting|not\s+fixed|unresolved)\b|"
        r"\b(?:not\s+fixed|fix\s+didn['’]?t\s+work|there(?:'s|’s|\s+is)\s+a\s+"
        r"regression)\b|^(?:(?:compile|compilation|build)\s+)?error\s*[:\-]",
        unquoted,
    ))


def is_user_error_report(text: str) -> bool:
    return _has_new_error_signal(text)


def is_user_confirmation(text: str) -> bool:
    lowered = " ".join((text or "").strip().lower().split())
    if not lowered or has_sentinel(lowered):
        return False
    if (
        _wholly_quoted(text)
        or _hypothetical_or_example(text)
        or _has_new_error_signal(text)
    ):
        return False
    if re.search(
        r"\b(still|but|however|except|not|same|fails?|failing|broken|once|"
        r"sometimes|intermittent)\b",
        lowered,
    ):
        return False
    if re.fullmatch(
        r"(?:yes,?\s+)?that\s+fixed\s+it\s*[,;:]\s+(?:please\s+)?"
        r"(?:update|improve|fix|change|harden|revise)\b.+[.!]?",
        lowered,
    ):
        return True
    return bool(re.fullmatch(
        r"(?:yes,?\s+)?(?:that\s+fixed\s+it|it\s+works(?:\s+now)?|"
        r"it(?:'s|’s|\s+is)\s+fixed\s+now|issue\s+is\s+resolved|"
        r"confirmed\s+resolved|i\s+tested\s+it\s+and\s+it\s+works(?:\s+now)?)"
        r"(?:[.!]|,\s*(?:thanks|thank\s+you)[.!]?)?",
        lowered,
    ))


def _tool_input(payload: Dict[str, Any]) -> Any:
    return payload.get("tool_input", payload.get("input", {}))


def _tool_is_error(response: Any) -> bool:
    if isinstance(response, dict):
        if response.get("is_error") is True or response.get("isError") is True or response.get("success") is False:
            return True
        if isinstance(response.get("exit_code"), int) and response.get("exit_code") != 0:
            return True
    return bool(isinstance(response, str) and re.search(r"\b(?:error|exception|failed|failure)\b", response, re.I))


def _tool_event(payload: Dict[str, Any], key: bytes) -> Dict[str, Any]:
    home = get_codex_home()
    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    turn = extract_first(payload, ["turn_id", "turnId", "turn"]) or "unknown"
    tool_id = extract_first(payload, ["tool_use_id", "toolUseId", "tool_id", "toolId"])
    if not tool_id:
        return {}
    tool_name = str(payload.get("tool_name", ""))
    session_hash = opaque_identity(session, key)
    turn_hash = opaque_identity({"session": session, "turn": turn}, key)
    tool_hash = opaque_identity(
        {"session": session, "tool_use_id": tool_id},
        key,
    )
    tool_name_hash = opaque_identity(
        {"session": session, "tool_name": tool_name},
        key,
    )
    input_hash = opaque_identity(
        {
            "session": session,
            "tool_name": tool_name,
            "tool_input": _tool_input(payload),
        },
        key,
    )
    if not all((session_hash, turn_hash, tool_hash, tool_name_hash, input_hash)):
        return {}
    return {
        "home": home,
        "key": key,
        "session_hash": session_hash,
        "turn_hash": turn_hash,
        "tool_hash": tool_hash,
        "tool_name_hash": tool_name_hash,
        "input_hash": input_hash,
    }


def _tool_state_path(info: Dict[str, Any], name: str) -> Path:
    return (
        _tool_state_dir(
            info["home"],
            name,
            info["session_hash"],
            info["turn_hash"],
        )
        / f"{info['tool_hash']}.json"
    )


def pre_tool_use(payload: Dict[str, Any]) -> Dict[str, Any]:
    home = get_codex_home()
    key = error_learning_key(home)
    if key is None:
        return _error_diagnostic()
    info = _tool_event(payload, key)
    if not info:
        return {}
    session_state = _error_fold(info["home"], info["session_hash"])
    if session_state.get("status") == "invalid":
        return _error_diagnostic()
    attempt = {
        key: info[key]
        for key in (
            "session_hash",
            "turn_hash",
            "tool_hash",
            "tool_name_hash",
            "input_hash",
        )
    }
    attempt.update(
        {
            "captured_generation": (
                session_state.get("generation")
                if session_state.get("status") == "awaiting"
                else None
            ),
            "created_unix_ns": time.time_ns(),
        }
    )
    _write_json_exclusive(
        _tool_state_path(info, ERROR_ATTEMPT_DIR_NAME),
        attempt,
    )
    return {}


def _attempts(
    home: Path,
    session_hash: str,
    turn_hash: str,
) -> list[Dict[str, Any]]:
    directory = _tool_state_dir(
        home,
        ERROR_ATTEMPT_DIR_NAME,
        session_hash,
        turn_hash,
    )
    if not directory.is_dir():
        return []
    cutoff = time.time_ns() - (ERROR_ATTEMPT_TTL_SECONDS * 1_000_000_000)
    attempts = []
    for path in directory.glob("*.json"):
        item = read_state(path)
        if not isinstance(item, dict):
            continue
        created = item.get("created_unix_ns")
        if not isinstance(created, int) or created < cutoff:
            try:
                path.unlink()
            except OSError:
                pass
            completion = (
                _tool_state_dir(
                    home,
                    ERROR_COMPLETION_DIR_NAME,
                    session_hash,
                    turn_hash,
                )
                / path.name
            )
            try:
                completion.unlink()
            except OSError:
                pass
            continue
        effective = dict(item)
        effective["status"] = "inflight"
        completion_path = (
            _tool_state_dir(
                home,
                ERROR_COMPLETION_DIR_NAME,
                session_hash,
                turn_hash,
            )
            / path.name
        )
        completion = read_state(completion_path)
        identity_fields = (
            "session_hash",
            "turn_hash",
            "tool_hash",
            "tool_name_hash",
            "input_hash",
        )
        if (
            isinstance(completion, dict)
            and completion.get("status") in ("error", "success")
            and isinstance(completion.get("created_unix_ns"), int)
            and not isinstance(completion.get("created_unix_ns"), bool)
            and all(completion.get(field) == item.get(field) for field in identity_fields)
        ):
            effective["status"] = completion["status"]
        attempts.append(effective)
    return attempts


def post_tool_use(payload: Dict[str, Any]) -> Dict[str, Any]:
    home = get_codex_home()
    key = error_learning_key(home)
    if key is None:
        return _error_diagnostic()
    info = _tool_event(payload, key)
    if not info:
        return {}
    path = _tool_state_path(info, ERROR_ATTEMPT_DIR_NAME)
    attempt = read_state(path)
    identity_fields = (
        "session_hash",
        "turn_hash",
        "tool_hash",
        "tool_name_hash",
        "input_hash",
    )
    if (
        not isinstance(attempt, dict)
        or any(attempt.get(field) != info[field] for field in identity_fields)
    ):
        return {}
    error = _tool_is_error(payload.get("tool_response", payload.get("response")))
    completion = {
        field: info[field]
        for field in identity_fields
    }
    completion.update(
        {
            "status": "error" if error else "success",
            "created_unix_ns": time.time_ns(),
        }
    )
    if not _write_json_exclusive(
        _tool_state_path(info, ERROR_COMPLETION_DIR_NAME),
        completion,
    ):
        return {}
    if error:
        return {}
    prior = [
        candidate
        for candidate in _attempts(
            info["home"],
            info["session_hash"],
            info["turn_hash"],
        )
        if candidate.get("session_hash") == info["session_hash"]
        and candidate.get("turn_hash") == info["turn_hash"]
        and candidate.get("tool_name_hash") == info["tool_name_hash"]
        and candidate.get("input_hash") == info["input_hash"]
        and candidate.get("status") in ("error", "inflight")
        and candidate.get("tool_hash") != info["tool_hash"]
    ]
    context = ""
    if prior:
        prior_hashes = sorted(
            {
                str(candidate["tool_hash"])
                for candidate in prior
                if candidate.get("tool_hash")
            }
        )
        candidate_hash = opaque_identity(
            {
                "session_hash": info["session_hash"],
                "turn_hash": info["turn_hash"],
                "resolved_attempt_hash": info["tool_hash"],
                "prior_attempt_hashes": prior_hashes,
            },
            info["key"],
        )
        recorded = candidate_hash and _append_error_event(
            info["home"],
            {
                "kind": "candidate_resolution",
                "session_hash": info["session_hash"],
                "turn_hash": info["turn_hash"],
                "attempt_hash": info["tool_hash"],
                "prior_attempt_hashes": prior_hashes,
                "candidate_hash": candidate_hash,
            },
            event_id=candidate_hash,
        )
        if recorded:
            context = (
                "The exact retry succeeded after a prior failed or unresolved "
                "attempt. This is candidate evidence only; classify expected "
                "probe/TDD/one-off versus unexpected durable failure, establish "
                "root cause, and freshly verify before learning."
            )
    captured = attempt.get("captured_generation")
    folded = _error_fold(info["home"], info["session_hash"])
    if captured and folded.get("status") == "awaiting" and folded.get("generation") == captured:
        verification_hash = opaque_identity(
            {
                "kind": "technical_verification",
                "generation": captured,
                "turn_hash": info["turn_hash"],
                "attempt_hash": info["tool_hash"],
            },
            info["key"],
        )
        if verification_hash:
            _append_error_event(
                info["home"],
                {
                    "kind": "technical_verification",
                    "session_hash": info["session_hash"],
                    "generation": captured,
                    "turn_hash": info["turn_hash"],
                    "attempt_hash": info["tool_hash"],
                },
                event_id=verification_hash,
            )
    return _error_context(context, "PostToolUse") if context else {}


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


def state_payload(event: str, payload: Dict[str, Any], turn_id: Optional[str] = None,
                  requires_change: bool = False, baseline: Optional[Dict[str, str]] = None,
                  project_root: Optional[Path] = None) -> Dict[str, Any]:
    return {
        "event": event,
        "session_id": extract_first(payload, ["session_id", "sessionId", "session"]),
        "turn_id": turn_id or extract_first(payload, ["turn_id", "turnId", "turn"]),
        "created_at": now_ts(),
        "hook_event": extract_first(payload, ["hook_event_name", "event", "type"]),
        "created_unix": now_unix(),
        "stop_hook_active": bool(payload.get("stop_hook_active")),
        "requires_change": requires_change,
        "instruction_baseline": baseline or {},
        "project_root": str(project_root) if project_root else None,
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


def build_context(requires_change: bool = True) -> str:
    return ACTION_CONTEXT if requires_change else READ_ONLY_CONTEXT


def _store_durable_prompt(payload: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    turn = extract_first(payload, ["turn_id", "turnId", "turn"]) or now_ts().replace(":", "-")
    home = get_codex_home()
    cwd = extract_first(payload, ["cwd", "working_directory", "workdir"])
    project_root = Path(cwd).resolve() if cwd else None
    if project_root is not None and (not project_root.is_dir() or not is_safe_path(project_root)):
        project_root = None
    path = state_filename(session, turn, home)
    needs_change = requires_instruction_change(prompt)
    state = state_payload(
        "UserPromptSubmit", payload, turn_id=turn,
        requires_change=needs_change,
        baseline=instruction_snapshot(home, project_root) if needs_change else {},
        project_root=project_root,
    )
    if not write_state_atomic(path, state):
        return {}
    log_entry("UserPromptSubmit", payload, {"state": path.name, "status": "stored"}, home)

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": build_context(needs_change),
        }
    }


def userprompt_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = prompt_text(payload)
    home = get_codex_home()
    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    key = error_learning_key(home)
    if key is None and is_user_error_report(prompt):
        _mark_keyless_report(home, session, prompt)
        result = _error_context(
            "The user reported an error, but the dynamic authority state is "
            "unavailable. Follow the global user-report fallback: remediate now, "
            "treat agent checks as provisional, and do not finalize resolution or "
            "instruction learning without explicit later user confirmation."
        )
        result.update(_error_diagnostic())
        return result
    session_hash = opaque_identity(session, key)
    folded = _error_fold(home, session_hash) if session_hash else {}
    if folded.get("status") == "invalid":
        result = _error_context(
            "Dynamic user-error authority state is invalid. Do not claim resolution "
            "or finalize instruction learning until the local state is repaired and "
            "the user's authority can be evaluated safely."
        )
        result.update(_error_diagnostic())
        return result
    if folded.get("status") == "awaiting" and is_user_error_report(prompt):
        turn = extract_first(payload, ["turn_id", "turnId", "turn"]) or "unknown"
        generation = opaque_identity({"session": session, "turn": turn, "prompt": prompt}, key)
        event_id = opaque_identity({"kind": "user_report", "generation": generation}, key)
        if not generation or not event_id:
            _mark_authority_failure(home, session_hash)
            return _error_diagnostic()
        if not _append_error_event(home, {"kind": "user_report", "session_hash": session_hash, "generation": generation}, event_id=event_id):
            return _error_diagnostic()
        _clear_keyless_reports_for_session(home, session)
        return _error_context("You reported a post-work error. Diagnose and remediate it now, but do not claim real-world resolution or finalize instruction learning until you receive explicit confirmation from the user after their testing. Any later user report supersedes this cycle.")
    if is_user_error_report(prompt):
        turn = extract_first(payload, ["turn_id", "turnId", "turn"]) or "unknown"
        generation = opaque_identity({"session": session, "turn": turn, "prompt": prompt}, key)
        event_id = opaque_identity({"kind": "user_report", "generation": generation}, key)
        if not generation or not event_id:
            _mark_authority_failure(home, session_hash)
            return _error_diagnostic()
        if not _append_error_event(home, {"kind": "user_report", "session_hash": session_hash, "generation": generation}, event_id=event_id):
            return _error_diagnostic()
        _clear_keyless_reports_for_session(home, session)
        return _error_context("You reported an error after prior work. Diagnose the root cause and remediate it now. Technical checks remain provisional: do not claim real-world resolution or finalize instruction learning until the user explicitly confirms their testing and confirmation is recorded; a later report supersedes this cycle.")
    if folded.get("status") == "awaiting" and is_user_confirmation(prompt):
        project_root = extract_first(payload, ["cwd", "working_directory", "workdir"])
        root = Path(project_root).resolve() if project_root else None
        baseline = instruction_snapshot(home, root) if root and root.is_dir() else instruction_snapshot(home)
        generation = folded.get("generation")
        event_id = opaque_identity({"kind": "confirmation", "generation": generation, "baseline": baseline}, key)
        if not event_id:
            _mark_authority_failure(home, session_hash)
            return _error_diagnostic()
        if not _append_error_event(home, {"kind": "confirmation", "session_hash": session_hash, "generation": generation, "baseline": baseline, "project_root": str(root) if root else None}, event_id=event_id):
            return _error_diagnostic()
        if is_durable_correction_prompt(prompt):
            return _store_durable_prompt(payload, prompt)
        return _error_context(
            "The user explicitly confirmed resolution. Use "
            "$instruction-learning-loop to apply the smallest durable instruction "
            "improvement, then verify a real instruction-file change before completing."
        )
    if folded.get("status") == "awaiting" and is_durable_correction_prompt(prompt):
        return _error_context("A user-reported error is still awaiting explicit positive confirmation after user testing. Remediate and verify technically, but do not finalize real-world resolution or instruction learning yet.")
    if is_durable_correction_prompt(prompt):
        return _store_durable_prompt(payload, prompt)
    return {}


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


def _has_unqualified_resolution_claim(text: str) -> bool:
    scrubbed = " ".join((text or "").lower().split())
    negative_patterns = (
        r"\b(?:not|isn['’]?t|is\s+not|hasn['’]?t\s+been|has\s+not\s+been)\s+"
        r"(?:yet\s+)?(?:fixed|resolved|complete|completed|done)\b",
        r"\b(?:cannot|can['’]?t|do\s+not)\s+claim\b.{0,48}\b"
        r"(?:fixed|resolved|complete|completed|done)\b",
    )
    for pattern in negative_patterns:
        scrubbed = re.sub(pattern, "", scrubbed)
    return bool(
        re.search(
            r"\b(?:fixed|resolved|solved|works\s+now|working\s+now|"
            r"issue\s+is\s+gone|no\s+longer\s+(?:fails?|failing|reproduces?)|"
            r"healthy|behav(?:es|ing)\s+correctly|tests?\s+(?:all\s+)?pass(?:ed|ing)?|"
            r"build\s+is\s+green|complete|completed|done|all\s+checks\s+pass|"
            r"successfully\s+fixed)\b",
            scrubbed,
        )
    )


def _safe_awaiting_user_status(text: str) -> bool:
    lowered = " ".join((text or "").lower().split())
    canonical = " ".join(PROVISIONAL_CONFIRMATION_STATEMENT.lower().split())
    has_canonical = canonical in lowered
    claim_surface = lowered.replace(canonical, " ")
    if not lowered or _has_unqualified_resolution_claim(claim_surface):
        return False
    if has_canonical:
        # The canonical disclaimer is valid only when no contradictory
        # unresolved status is asserted outside that complete clause.
        return not bool(re.search(
            r"\b(?:unresolved|still\s+failing|blocked|unable\s+to\s+verify|cannot\s+verify|"
            r"can['’]?t\s+verify|not\s+(?:yet\s+)?fixed|fix\s+is\s+pending)\b",
            claim_surface,
        ))
    unresolved = bool(
        re.search(
            r"\b(?:not\s+(?:yet\s+)?(?:fixed|resolved)|unresolved|still\s+failing|"
            r"blocked|unable\s+to\s+verify|cannot\s+verify|can['’]?t\s+verify|"
                r"verification\s+is\s+pending|fix\s+is\s+pending|"
                r"cannot\s+claim|can['’]?t\s+claim)\b",
            lowered,
        )
    )
    return unresolved


def stop_hook(payload: Dict[str, Any]) -> Dict[str, Any]:
    session = extract_first(payload, ["session_id", "sessionId", "session"]) or "unknown"
    turn = extract_first(payload, ["turn_id", "turnId", "turn"])
    home = get_codex_home()
    keyless_status = _keyless_authority_status(home, session)
    if keyless_status != "clear":
        return {
            "decision": "block",
            "reason": "[instruction-learning-hook] This session has an unrecorded user error, or its keyless authority state is invalid; completion remains fail-closed until the local key is repaired and the same report is recorded successfully.",
        }
    key = error_learning_key(home)
    if key is None and _dynamic_state_exists(home):
        return {
            "decision": "block",
            "reason": "[instruction-learning-hook] Dynamic authority state exists but its local identity key is missing or corrupt; completion is fail-closed.",
        }
    session_hash = opaque_identity(session, key)
    error_state = _error_fold(home, session_hash) if session_hash else {}
    pending_ids = _authority_pending_ids(home, session_hash)
    if pending_ids is None:
        return {
            "decision": "block",
            "reason": "[instruction-learning-hook] Dynamic authority persistence failed; completion is fail-closed until the authority event can be written and verified.",
        }
    if pending_ids:
        retry_completion_id = None
        if error_state.get("status") in {"confirmed", "completed"}:
            retry_completion_id = opaque_identity(
                {"kind": "completed", "generation": error_state.get("generation")},
                key,
            )
        if not retry_completion_id or pending_ids != {retry_completion_id}:
            return {
                "decision": "block",
                "reason": "[instruction-learning-hook] Dynamic authority persistence failed; completion is fail-closed until the authority event can be written and verified.",
            }
        if error_state.get("status") == "completed":
            _clear_authority_failure(
                _authority_failure_path(home, session_hash) / retry_completion_id
            )
            if _authority_failed(home, session_hash):
                return {
                    "decision": "block",
                    "reason": "[instruction-learning-hook] Completed authority state is valid, but its pending marker could not be cleared safely.",
                }
    assistant = last_assistant_message(payload)
    if error_state.get("status") == "invalid":
        return {
            "decision": "block",
            "reason": (
                "[instruction-learning-hook] Dynamic user-error authority state is "
                "invalid; completion cannot be evaluated safely. Repair or quarantine "
                "the malformed local state before claiming resolution."
            ),
        }
    if error_state.get("status") == "awaiting":
        if not _safe_awaiting_user_status(assistant):
            return {
                "decision": "block",
                "reason": (
                    "[instruction-learning-hook] A user-reported error is awaiting "
                    "explicit confirmation. State truthful unresolved/blocker status "
                    "or say: Technical verification passed, but real-world resolution "
                    "and instruction learning are awaiting your confirmation. Do not "
                    "claim fixed or resolved."
                ),
            }
        return {}
    if error_state.get("status") == "confirmed":
        baseline = error_state.get("baseline")
        raw_project_root = error_state.get("project_root")
        project_root = Path(raw_project_root) if isinstance(raw_project_root, str) and raw_project_root else None
        changed = isinstance(baseline, dict) and instruction_snapshot(home, project_root) != baseline
        if not changed:
            if payload.get("stop_hook_active"):
                return {}
            return {"decision": "block", "reason": "[instruction-learning-hook] User confirmed resolution, but no fresh durable instruction change has been verified."}
        generation = error_state.get("generation")
        completion_id = opaque_identity({"kind": "completed", "generation": generation}, key)
        if not completion_id:
            _mark_authority_failure(home, session_hash)
            return {"decision": "block", "reason": "[instruction-learning-hook] Completion persistence failed; resolution remains unfinalized."}
        if not _append_error_event(home, {"kind": "completed", "session_hash": session_hash, "generation": generation}, event_id=completion_id):
            return {"decision": "block", "reason": "[instruction-learning-hook] Completion persistence failed; resolution remains unfinalized."}
        if payload.get("stop_hook_active"):
            return {}

    # Preserve the legacy correction gate's recursive-stop pass-through. User-error
    # awaiting state was handled above and is intentionally stricter.
    if payload.get("stop_hook_active"):
        return {}

    state_path = find_stale_or_exact_state(home, session, turn)
    if state_path is None:
        return {}

    state = read_state(state_path) or {}
    requires_change = bool(state.get("requires_change"))
    baseline = state.get("instruction_baseline")
    raw_project_root = state.get("project_root")
    project_root = Path(raw_project_root) if isinstance(raw_project_root, str) and raw_project_root else None
    changed = not requires_change or (
        isinstance(baseline, dict) and instruction_snapshot(home, project_root) != baseline
    )
    if changed:
        delete_state(state_path)
        log_entry(
            "Stop", payload,
            {"state": state_path.name, "decision": "allow", "instruction_changed": requires_change}, home,
        )
        return {}

    log_entry(
        "Stop",
        payload,
        {"state": state_path.name, "decision": "block", "instruction_changed": False},
        home,
    )
    return {
        "decision": "block",
        "reason": "[instruction-learning-hook] This actionable correction has not changed an instruction file. Obtain independent advisor review, fold valid in-scope findings into the proposal, revise and resubmit internally, then implement and verify the approved durable change without renewed user approval; a proposal or claimed rejection alone is not completion.",
    }


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    evt = event_name(payload).strip().lower()
    if evt == "userpromptsubmit":
        return userprompt_submit(payload)
    if evt == "pretooluse":
        return pre_tool_use(payload)
    if evt == "posttooluse":
        return post_tool_use(payload)
    if evt == "stop":
        return stop_hook(payload)
    return {}


def main() -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return handle(payload)
    except Exception:
        if event_name(payload).strip().lower() == "stop":
            return {
                "decision": "block",
                "reason": (
                    "[instruction-learning-hook] Stop-time instruction-learning "
                    "authority evaluation failed; completion cannot be accepted safely."
                ),
            }
        return {}


if __name__ == "__main__":
    output = main()
    if output:
        print(json.dumps(output))
    else:
        print("{}")
