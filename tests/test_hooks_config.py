from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOKS_PATH = Path(__file__).resolve().parents[1] / "hooks.json"


def _dispatcher_code(*relative_parts: str) -> str:
    path_expression = ", ".join(repr(part) for part in relative_parts)
    return (
        "import os, runpy; "
        "runpy.run_path(os.path.join(os.environ.get('CODEX_HOME') or "
        "os.path.expanduser('~/.codex'), "
        f"{path_expression}), run_name='__main__')"
    )


PLAN_GAP_CODE = _dispatcher_code("hooks", "plan_gap_goal_hook.py")
PLAN_GAP_POSIX = f'python3 -B -c "{PLAN_GAP_CODE}"'
PLAN_GAP_WINDOWS = f'python -B -c "{PLAN_GAP_CODE}"'


def _skill_loop_code(verb: str) -> str:
    return (
        "import os, runpy, sys; "
        f"sys.argv = ['skill_loop.py', 'hook', '{verb}', '--platform', 'codex']; "
        "runpy.run_path(os.path.expanduser('~/.skill-loop/skill_loop.py'), run_name='__main__')"
    )


SKILL_LOOP_VERBS = {
    "UserPromptSubmit": "user-prompt-submit",
    "SessionStart": "session-start",
    "PreCompact": "pre-compact",
    "SessionEnd": "session-end",
}


class HooksConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))

    def test_registers_plan_gap_and_skill_loop_events(self) -> None:
        hooks = self.config["hooks"]
        self.assertEqual(set(hooks), set(SKILL_LOOP_VERBS))

        for event, verb in SKILL_LOOP_VERBS.items():
            with self.subTest(event=event):
                commands = [
                    (entry["command"], entry["commandWindows"])
                    for group in hooks[event]
                    for entry in group["hooks"]
                ]
                code = _skill_loop_code(verb)
                expected = [(f'python3 -B -c "{code}"', f'python -B -c "{code}"')]
                if event == "UserPromptSubmit":
                    expected.insert(0, (PLAN_GAP_POSIX, PLAN_GAP_WINDOWS))
                self.assertEqual(commands, expected)

    def test_skill_loop_dispatcher_runs_engine_from_home_with_hook_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            engine = home / ".skill-loop" / "skill_loop.py"
            engine.parent.mkdir(parents=True)
            engine.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(home)
            environment["HOME"] = str(home)
            for verb in SKILL_LOOP_VERBS.values():
                with self.subTest(verb=verb):
                    result = subprocess.run(
                        [sys.executable, "-B", "-c", _skill_loop_code(verb)],
                        capture_output=True,
                        env=environment,
                        check=False,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), f"hook {verb} --platform codex")

    def test_commands_use_expected_windows_and_posix_home_relative_paths(self) -> None:
        commands = [
            entry
            for event in self.config["hooks"].values()
            for group in event
            for entry in group["hooks"]
        ]
        command_pairs = [(entry["command"], entry["commandWindows"]) for entry in commands]
        self.assertIn((PLAN_GAP_POSIX, PLAN_GAP_WINDOWS), command_pairs)

        for entry in commands:
            for command in (entry["command"], entry["commandWindows"]):
                self.assertIsNone(re.search(r"(?i)[A-Z]:[\\/]", command))
                self.assertNotRegex(command, r"(?i)(?:^|[\\/])users(?:[\\/]|$)")
                self.assertNotIn("codex-cli-improvements", command)
                self.assertNotIn("trust", command.lower())
                self.assertNotIn("hash", command.lower())

    def test_dispatchers_run_fake_hooks_from_custom_and_default_homes(self) -> None:
        commands = [
            (PLAN_GAP_POSIX, ("hooks", "plan_gap_goal_hook.py")),
            (PLAN_GAP_WINDOWS, ("hooks", "plan_gap_goal_hook.py")),
        ]
        payload = b'{"hook_event_name":"UserPromptSubmit"}\n'

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            custom_home = root / "custom-home"
            default_home = root / "default-home"
            for command, relative_parts in commands:
                with self.subTest(command=command):
                    for configured_home, expected_home in (
                        (custom_home, custom_home),
                        (None, default_home / ".codex"),
                    ):
                        with self.subTest(configured_home=configured_home):
                            script_path = expected_home.joinpath(*relative_parts)
                            marker_path = root / (
                                "marker-"
                                + str(len(list(root.glob("marker-*"))))
                                + ".bin"
                            )
                            script_path.parent.mkdir(parents=True, exist_ok=True)
                            script_path.write_text(
                                "import sys\n"
                                "from pathlib import Path\n"
                                f"data = sys.stdin.buffer.read()\nPath({str(marker_path)!r}).write_bytes(data)\n"
                                "sys.stdout.buffer.write(data)\n",
                                encoding="utf-8",
                            )

                            environment = os.environ.copy()
                            environment["USERPROFILE"] = str(default_home)
                            environment["HOME"] = str(default_home)
                            if configured_home is None:
                                environment.pop("CODEX_HOME", None)
                            else:
                                environment["CODEX_HOME"] = str(configured_home)

                            embedded_code = command.split(' -B -c "', 1)[1][:-1]
                            result = subprocess.run(
                                [sys.executable, "-B", "-c", embedded_code],
                                input=payload,
                                capture_output=True,
                                env=environment,
                                check=False,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr.decode())
                            self.assertEqual(result.stdout, payload)
                            self.assertEqual(marker_path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
