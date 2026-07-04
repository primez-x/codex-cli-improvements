#!/usr/bin/env python3
"""Set a plan-implementation gap-analysis goal when a plan is accepted."""

from __future__ import annotations

import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


TRIGGER_PROMPTS = {
    "Implement the plan.",
    "Yes, implement this plan",
}
CLIENT_NAME = "plan_gap_goal_hook"
LOG_NAME = "plan_gap_goal_hook.log"
ACTIVE_GOAL_STATUSES = {"active", "paused", "blocked", "usageLimited", "budgetLimited"}

OBJECTIVE = """Implement the accepted plan fully. Treat the accepted plan as the contract for the work.

After the implementation appears complete, do not stop. Conduct a plan implementation gap analysis before giving the final answer:
- Recover the original plan and turn it into a checklist of concrete commitments.
- Compare each commitment against the actual diff, relevant code paths, tests, docs, config, and generated artifacts.
- Fix any clear, in-scope missing, partial, contradicted, or buggy implementation pieces.
- Run focused verification after the fixes.
- Only finish after reporting the plan recovered, gap checklist, fixes applied, verification, and remaining risk.

Completion means both the implementation and the gap analysis loop are complete."""


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
    if prompt.strip() not in TRIGGER_PROMPTS:
        return 0

    thread_id = str(payload.get("session_id") or "")
    if not thread_id:
        log("missing session_id for trigger")
        return 0

    set_goal(thread_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
