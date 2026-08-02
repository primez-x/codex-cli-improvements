from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "config.toml").open("rb") as stream:
            cls.config = tomllib.load(stream)

    def test_config_registers_only_the_supported_routing_matrix(self) -> None:
        agents = self.config["agents"]
        expected = {
            "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
            "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
            "luna_scanner": ("gpt-5.6-luna", "high"),
            "luna_worker": ("gpt-5.6-luna", "max"),
            "sol_worker": ("gpt-5.6-sol", "xhigh"),
            "sol_advisor": ("gpt-5.6-sol", "max"),
        }

        self.assertEqual(
            (self.config["model"], self.config["model_reasoning_effort"]),
            ("gpt-5.6-sol", "medium"),
        )
        self.assertEqual(agents["max_depth"], 1)
        self.assertEqual(agents["max_concurrent_threads_per_session"], 4)
        self.assertEqual(
            (
                agents["default_subagent_model"],
                agents["default_subagent_reasoning_effort"],
            ),
            ("gpt-5.6-luna", "max"),
        )

        registered = {
            name
            for name, value in agents.items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(registered, set(expected))
        self.assertTrue(registered)

        profile_files = {
            path.stem for path in (ROOT / "agents").glob("*.toml")
        }
        self.assertEqual(profile_files, set(expected))
        self.assertFalse(
            any("terra" in name or "coordinator" in name for name in profile_files)
        )

        for name, wanted in expected.items():
            with self.subTest(agent=name):
                path = ROOT / agents[name]["config_file"]
                self.assertTrue(path.is_file())
                with path.open("rb") as stream:
                    profile = tomllib.load(stream)
                self.assertEqual(
                    (profile["model"], profile["model_reasoning_effort"]),
                    wanted,
                )

    def test_registered_profiles_are_terminal_and_root_coordinates_directly(self) -> None:
        registered = {
            name
            for name, value in self.config["agents"].items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(
            registered,
            {
                "spark_scanner",
                "spark_worker",
                "luna_scanner",
                "luna_worker",
                "sol_worker",
                "sol_advisor",
            },
        )
        self.assertFalse(any(name.endswith("_coordinator") for name in registered))

        for name in registered:
            with self.subTest(agent=name):
                instructions = (
                    ROOT / self.config["agents"][name]["config_file"]
                ).read_text(encoding="utf-8").lower()
                self.assertRegex(instructions, r"do not[^.\n]*spawn")

    def test_runtime_assets_do_not_reference_retired_profiles(self) -> None:
        retired = (
            "luna_" + "coordinator",
            "terra_" + "worker",
            "terra_" + "coordinator",
            "sol_" + "coordinator",
        )
        paths = [ROOT / "config.toml", ROOT / "AGENTS.md", ROOT / "README.md"]
        paths.extend((ROOT / "agents").glob("*.toml"))
        paths.extend((ROOT / "skills" / "delivery-orchestration").rglob("*.md"))
        paths.extend((ROOT / "skills" / "plan-review-ladder").rglob("*.md"))
        paths.append(
            ROOT / "skills" / "plan-review-ladder" / "scripts" / "packet_integrity.py"
        )
        for path in paths:
            text = path.read_text(encoding="utf-8").lower()
            for profile in retired:
                with self.subTest(path=path.relative_to(ROOT), profile=profile):
                    self.assertNotIn(profile, text)

    def test_registered_skills_exist_and_use_relative_paths(self) -> None:
        skill_paths = [
            entry["path"] for entry in self.config.get("skills", {}).get("config", [])
        ]
        self.assertEqual(len(skill_paths), 3)
        for configured in skill_paths:
            with self.subTest(path=configured):
                path = Path(configured)
                self.assertFalse(path.is_absolute())
                self.assertTrue((ROOT / path).is_file())

    def test_hooks_are_portable(self) -> None:
        hooks_path = ROOT / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("Stop", hooks)

        serialized = json.dumps(hooks).lower()
        self.assertNotIn("c:\\\\users\\\\", serialized)
        self.assertNotIn("m." + "pincoski", serialized)
        self.assertIn("os.environ.get('codex_home')", serialized)
        self.assertIn("os.path.expanduser('~/.codex')", serialized)
        self.assertNotIn("%userprofile%", serialized)
        for event in hooks.values():
            for group in event:
                for entry in group["hooks"]:
                    self.assertRegex(entry["command"], r'^python3 -c ".+"$')
                    self.assertRegex(entry["commandWindows"], r'^python -c ".+"$')

    def test_runtime_state_is_ignored_at_repository_boundaries(self) -> None:
        patterns = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        expected_patterns = {
            "/hooks/state/",
            "/hooks/*.log",
            "/tmp/",
            "/models_cache.json",
            "/sessions/",
            "/history.jsonl",
            "/logs/",
            "/sqlite/",
            "/*.sqlite",
            "/*.sqlite-shm",
            "/*.sqlite-wal",
        }
        self.assertTrue(expected_patterns.issubset(patterns))
        self.assertTrue(all(pattern.startswith("/") for pattern in expected_patterns))

        runtime_paths = (
            ROOT / "hooks" / "state",
            ROOT / "hooks" / "plan_gap_goal_hook.log",
            ROOT / "tmp",
            ROOT / "models_cache.json",
            ROOT / "sessions",
            ROOT / "history.jsonl",
            ROOT / "session_index.jsonl",
            ROOT / "transcription-history.jsonl",
            ROOT / "logs",
            ROOT / "sqlite",
            ROOT / "state.sqlite",
            ROOT / "state.sqlite-shm",
            ROOT / "state.sqlite-wal",
        )
        for path in runtime_paths:
            with self.subTest(runtime_path=path.relative_to(ROOT)):
                self.assertFalse(path.exists())

        source_paths = (
            ROOT / "hooks.json",
            ROOT / "hooks" / "plan_gap_goal_hook.py",
            ROOT / "config.toml",
            ROOT / "tests" / "test_hooks_config.py",
            ROOT / "tests" / "test_repository_contract.py",
        )
        for path in source_paths:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(any(path.match(pattern.lstrip("/")) for pattern in expected_patterns))

    def test_reusable_text_excludes_local_and_project_material(self) -> None:
        forbidden_patterns = (
            re.escape("m." + "pincoski"),
            re.escape("c:" + "\\users\\"),
            r"\b" + "crea" + "tio" + r"\b",
            r"\b" + "bank" + r"\.ai\b",
            r"\b" + "one" + "drive" + r"\b",
        )
        excluded_dirs = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
        text_suffixes = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}

        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in excluded_dirs for part in path.parts):
                continue
            if path.suffix.lower() not in text_suffixes:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for pattern in forbidden_patterns:
                with self.subTest(path=path.relative_to(ROOT), pattern=pattern):
                    self.assertIsNone(re.search(pattern, text))


if __name__ == "__main__":
    unittest.main()
