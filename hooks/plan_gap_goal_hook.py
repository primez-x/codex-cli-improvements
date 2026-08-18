#!/usr/bin/env python3
"""Set a plan-implementation gap-analysis goal when a plan is accepted."""

from __future__ import annotations

import glob
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


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
CLIENT_NAME = "plan_gap_goal_hook"
LOG_NAME = "plan_gap_goal_hook.log"
ACTIVE_GOAL_STATUSES = {"active", "paused", "blocked", "usageLimited", "budgetLimited"}

OBJECTIVE = """Implement the accepted plan fully. Treat the accepted plan as the contract for the work.

Treat internal review findings as implementation inputs, not a new approval gate. Incorporate valid in-scope findings, revise and resubmit internally when required, and continue without renewed user approval. Reject or defer findings that require new scope or authority; ask only when that expansion is necessary.

After the implementation appears complete, do not stop. Conduct a plan implementation gap analysis before giving the final answer:
- Recover the original plan and turn it into a checklist of concrete commitments.
- Compare each commitment against the actual diff, relevant code paths, tests, docs, config, and generated artifacts.
- Fix any clear, in-scope missing, partial, contradicted, or buggy implementation pieces.
- Run focused verification after the fixes.
- Only finish after reporting the plan recovered, gap checklist, fixes applied, verification, and remaining risk.

Before marking the goal complete, satisfy all delivery gates applicable under the active repository and project instructions; source changes, a commit, Git push, or artifact upload do not substitute for required build, install or deployment, read-back, or runtime verification. If a required gate remains pending or fails, keep the goal unfinished and use `blocked` only under the goal-status rules. User-excluded or non-applicable gates do not block completion of the authorized scope, but report them and do not claim full delivery or live verification.

Completion means both the implementation and the gap analysis loop are complete, with every applicable delivery gate evidenced."""


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


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def log(message: str, **extra: object) -> None:
    try:
        path = codex_home() / "hooks" / LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": message,
            **extra,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def find_codex() -> str | None:
    candidates: list[str] = []
    env_path = os.environ.get("CODEX_CLI_PATH")
    if env_path:
        candidates.append(env_path)

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.extend(
                sorted(
                    glob.glob(str(Path(local) / "OpenAI" / "Codex" / "bin" / "*" / "codex.exe")),
                    key=lambda p: os.path.getmtime(p),
                    reverse=True,
                )
            )

    which = shutil.which("codex")
    if which:
        candidates.append(which)

    if os.name != "nt":
        candidates.extend(
            [
                str(Path.home() / ".local" / "bin" / "codex"),
                "/usr/local/bin/codex",
                "/usr/bin/codex",
            ]
        )

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if Path(candidate).exists():
            return candidate
    return None


def reader(stream, out: queue.Queue[dict]) -> None:
    for line in iter(stream.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            out.put(json.loads(line))
        except Exception:
            log("ignored non-json app-server line", line=line[:500])


def send(proc: subprocess.Popen, message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    proc.stdin.flush()


def wait_for_response(out: queue.Queue[dict], request_id: int, timeout_s: float) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            msg = out.get(timeout=max(0.1, min(0.5, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if msg.get("id") == request_id:
            return msg
    return None


def set_goal(thread_id: str) -> None:
    codex = find_codex()
    if not codex:
        log("codex executable not found", thread_id=thread_id)
        return

    proc = subprocess.Popen(
        [codex, "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out: queue.Queue[dict] = queue.Queue()
    thread = threading.Thread(target=reader, args=(proc.stdout, out), daemon=True)
    thread.start()

    try:
        send(
            proc,
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": CLIENT_NAME,
                        "title": "Plan Gap Goal Hook",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            },
        )
        send(proc, {"method": "initialized", "params": {}})
        send(proc, {"method": "thread/goal/get", "id": 1, "params": {"threadId": thread_id}})

        current = wait_for_response(out, 1, 6.0)
        if not current:
            log("timed out reading current goal", thread_id=thread_id)
            return
        if current.get("error"):
            log("goal get failed", thread_id=thread_id, error=current.get("error"))
            return

        goal = ((current.get("result") or {}).get("goal"))
        if goal and goal.get("status") in ACTIVE_GOAL_STATUSES:
            log("skipped because goal already active", thread_id=thread_id, status=goal.get("status"))
            return

        send(
            proc,
            {
                "method": "thread/goal/set",
                "id": 2,
                "params": {
                    "threadId": thread_id,
                    "objective": OBJECTIVE,
                    "status": "active",
                },
            },
        )
        result = wait_for_response(out, 2, 6.0)
        if not result:
            log("timed out setting goal", thread_id=thread_id)
        elif result.get("error"):
            log("goal set failed", thread_id=thread_id, error=result.get("error"))
        else:
            log("goal set", thread_id=thread_id)
    except Exception as exc:
        log("hook failed", thread_id=thread_id, error=repr(exc))
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        log("invalid hook input", error=repr(exc))
        return 0

    prompt = str(payload.get("prompt") or "")
    if not is_plan_implementation_prompt(prompt):
        return 0

    thread_id = str(payload.get("session_id") or "")
    if not thread_id:
        log("missing session_id for trigger")
        return 0

    set_goal(thread_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
