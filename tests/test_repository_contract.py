from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_POLICY = (
    ROOT
    / "skills"
    / "instruction-learning-loop"
    / "references"
    / "installed-skill-reconciliation.md"
)

GENERAL_ROUTING_MATRIX = {
    "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
    "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
    "luna_scanner": ("gpt-5.6-luna", "medium"),
    "luna_fast_worker": ("gpt-5.6-luna", "xhigh"),
    "luna_worker": ("gpt-5.6-luna", "max"),
    "sol_fast_worker": ("gpt-5.6-sol", "low"),
    "astra_worker": ("gpt-6-astra", "medium"),
    "astra_low_worker": ("gpt-6-astra", "low"),
    "astra_advisor": ("gpt-6-astra", "high"),
}
RETIRED_PROFILE_MARKERS = (
    "terra",
    "spark_coordinator",
    "luna_coordinator",
    "terra_worker",
    "terra_coordinator",
    "sol_coordinator",
    "luna_orchestrator",
)

PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----",
    re.IGNORECASE,
)
URL_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:https?|ssh)://[^/\s:@]+:(?!\{)[^/\s@]+@",
    re.IGNORECASE,
)
ASSIGNED_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"client[_ -]?secret|password|passwd)\b\s*[:=]\s*"
    r"['\"](?!<[^>]+>|REDACTED|REPLACE(?:_ME)?|EXAMPLE)[^'\"]{12,}['\"]",
    re.IGNORECASE,
)
BEARER_TOKEN_PATTERN = re.compile(
    r"\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{20,}\b",
    re.IGNORECASE,
)
TOKEN_PREFIX_PATTERN = re.compile(
    r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9]{20,})\b"
)


def _actual_user_profile_pattern() -> re.Pattern[str]:
    """Match this machine's user profile, without banning synthetic fixtures."""

    user_name = re.escape(Path.home().name)
    return re.compile(
        r"(?i)(?:[A-Za-z]:[\\/]+Users[\\/]"
        + user_name
        + r"(?:[\\/]|$)|(?:^|[\s\"'(])/(?:Users|home)/"
        + user_name
        + r"(?:/|$))"
    )


ACTUAL_USER_PROFILE_PATTERN = _actual_user_profile_pattern()


class RepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "config.toml").open("rb") as stream:
            cls.config = tomllib.load(stream)

    @staticmethod
    def _registered_profiles(config: dict) -> set[str]:
        return {
            name
            for name, value in config["agents"].items()
            if isinstance(value, dict) and "config_file" in value
        }

    def _load_profile(self, name: str) -> dict:
        relative_path = self.config["agents"][name]["config_file"]
        path = ROOT / relative_path
        with path.open("rb") as stream:
            return tomllib.load(stream)

    @staticmethod
    def _relative(path: Path) -> str:
        return path.relative_to(ROOT).as_posix()

    @classmethod
    def _text_files(cls):
        """Yield every UTF-8 text file, including patch/diff artifacts."""

        excluded_dirs = {
            ".git",
            ".superpowers",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        }
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in excluded_dirs for part in path.parts):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\0" in raw:
                continue
            try:
                yield path, raw.decode("utf-8").lower()
            except UnicodeDecodeError:
                continue

    def test_config_registers_the_current_astra_matrix(self) -> None:
        agents = self.config["agents"]
        self.assertEqual(
            (self.config["model"], self.config["model_reasoning_effort"]),
            ("gpt-5.6-luna", "xhigh"),
        )
        self.assertEqual(agents["max_depth"], 2)
        self.assertEqual(agents["max_concurrent_threads_per_session"], 6)
        self.assertIs(agents["enabled"], True)
        self.assertEqual(
            (
                agents["default_subagent_model"],
                agents["default_subagent_reasoning_effort"],
            ),
            ("gpt-6-astra", "medium"),
        )
        self.assertEqual(
            self.config["features"]["multi_agent_v2"],
            {
                "enabled": True,
                "min_wait_timeout_ms": 1500000,
                "default_wait_timeout_ms": 1500000,
                "max_wait_timeout_ms": 1500000,
            },
        )

        registered = self._registered_profiles(self.config)
        self.assertEqual(
            registered,
            set(GENERAL_ROUTING_MATRIX),
        )
        self.assertEqual(len(registered), 9)
        self.assertTrue(self.config["features"]["multi_agent"])

        profile_files = {path.stem for path in (ROOT / "agents").glob("*.toml")}
        self.assertEqual(profile_files, registered)
        self.assertFalse(any("terra" in name or "coordinator" in name for name in registered))

        for name in registered:
            with self.subTest(agent=name):
                config_file = Path(agents[name]["config_file"])
                self.assertFalse(config_file.is_absolute())
                self.assertEqual(config_file.parts[0], "agents")
                self.assertTrue((ROOT / config_file).is_file())

        for name, wanted in {
            **GENERAL_ROUTING_MATRIX,
        }.items():
            with self.subTest(agent=name):
                profile = self._load_profile(name)
                self.assertEqual(
                    (profile["model"], profile["model_reasoning_effort"]),
                    wanted,
                )
                self.assertEqual(profile["name"], name)

    def test_registered_profiles_preserve_bounded_depth_and_leaf_boundaries(self) -> None:
        registered = self._registered_profiles(self.config)
        self.assertEqual(len(registered), 9)

        for name in registered:
            with self.subTest(agent=name):
                profile = self._load_profile(name)
                instructions = profile["developer_instructions"].lower()
                description = profile["description"].lower()
                for stale in ("terminal leaf", "terminal worker", "terminal writer", "read-only leaf"):
                    self.assertNotIn(stale, description)
                self.assertRegex(instructions, r"depth[- ]1")
                self.assertRegex(instructions, r"depth[- ]2")
                self.assertRegex(instructions, r"do not[^.\n]*spawn")
                self.assertIn("do not fork", instructions)
                self.assertIn("fresh self-contained packet", instructions)
                self.assertIn("cache window", instructions)
                self.assertIs(profile["agents"]["enabled"], True)
                self.assertNotIn("act as a terminal", instructions)
                self.assertIn("30-minute cache window", instructions)

                if profile["sandbox_mode"] == "workspace-write":
                    for phrase in ("do not commit", "push", "publish", "deploy"):
                        self.assertIn(phrase, instructions)
                    self.assertIn("external", instructions)

    def test_runtime_assets_do_not_reference_retired_profile_families(self) -> None:
        paths = [
            ROOT / "config.toml",
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            RECONCILIATION_POLICY,
        ]
        paths.extend((ROOT / "agents").glob("*.toml"))
        paths.extend((ROOT / "skills" / "delivery-orchestration").rglob("*.md"))
        paths.extend((ROOT / "skills" / "instruction-learning-loop").rglob("*.md"))
        paths.extend((ROOT / "skills" / "adversarial-code-review").glob("SKILL.md"))

        for path in paths:
            text = path.read_text(encoding="utf-8").lower()
            for marker in RETIRED_PROFILE_MARKERS:
                with self.subTest(path=self._relative(path), marker=marker):
                    self.assertNotIn(marker, text)

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

    def test_hooks_are_portable_and_register_the_plan_goal_event(self) -> None:
        hooks_path = ROOT / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertIn("UserPromptSubmit", hooks)
        self.assertEqual(
            set(hooks),
            {"UserPromptSubmit"},
        )

        self.assertEqual(len(hooks["UserPromptSubmit"]), 1)
        self.assertEqual(len(hooks["UserPromptSubmit"][0]["hooks"]), 1)
        self.assertIn(
            "plan_gap_goal_hook.py",
            hooks["UserPromptSubmit"][0]["hooks"][0]["command"],
        )

        serialized = json.dumps(hooks).lower()
        self.assertNotIn("c:\\\\users\\", serialized)
        self.assertNotIn("m." + "pincoski", serialized)
        self.assertIn("os.environ.get('codex_home')", serialized)
        self.assertIn("os.path.expanduser('~/.codex')", serialized)
        self.assertNotIn("%userprofile%", serialized)
        for event in hooks.values():
            for group in event:
                for entry in group["hooks"]:
                    self.assertRegex(entry["command"], r'^python3 -B -c ".+"$')
                    self.assertRegex(entry["commandWindows"], r'^python -B -c ".+"$')

    def test_review_policy_is_risk_triggered(self) -> None:
        root_facing = (
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "skills" / "delivery-orchestration" / "SKILL.md",
            ROOT / "skills" / "adversarial-code-review" / "SKILL.md",
        )
        combined = " ".join(path.read_text(encoding="utf-8").lower() for path in root_facing)
        normalized = " ".join(combined.split())
        for phrase in (
            "luna xhigh root",
            "independent review",
            "security",
            "authentication",
            "credentials",
            "privacy",
            "repeated failed verification",
            "optional review failure",
            "required consequential review",
        ):
            self.assertIn(phrase, normalized)
        self.assertNotIn("for every material delivery", normalized)

    def test_error_learning_contract_preserves_user_confirmation_authority(self) -> None:
        agents = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").lower().split())
        skill = " ".join(
            (ROOT / "skills" / "instruction-learning-loop" / "SKILL.md")
            .read_text(encoding="utf-8")
            .lower()
            .split()
        )

        for phrase in (
            "instruction learning is discretionary",
            "established, recurring instruction defect",
            "narrowest authorized source",
            "fixed bug does not require an instruction edit",
            "change memory only when explicitly requested",
        ):
            self.assertIn(phrase, agents)

        for phrase in (
            "do not create a persistent confirmation lifecycle",
            "do not claim user-observed resolution without user-observed evidence",
        ):
            self.assertIn(phrase, skill)

        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        registered_hooks = json.dumps(hooks).lower()
        self.assertNotIn("instruction_learning_hook.py", registered_hooks)
        self.assertFalse(
            (ROOT / "skills" / "instruction-learning-loop" / "scripts" / "instruction_learning_hook.py").exists()
        )
        self.assertTrue(
            (ROOT / "skills" / "instruction-learning-loop" / "scripts" / "audit_instruction_system.py").is_file()
        )

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
            "/session_index.jsonl",
            "/transcription-history.jsonl",
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
            with self.subTest(runtime_path=self._relative(path)):
                self.assertFalse(path.exists())

        source_paths = (
            ROOT / "hooks.json",
            ROOT / "hooks" / "plan_gap_goal_hook.py",
            ROOT / "config.toml",
            RECONCILIATION_POLICY,
            ROOT / "tests" / "test_hooks_config.py",
            ROOT / "tests" / "test_repository_contract.py",
        )
        for path in source_paths:
            with self.subTest(path=self._relative(path)):
                self.assertFalse(any(path.match(pattern.lstrip("/")) for pattern in expected_patterns))

        actual_runtime_names = {
            "models_cache.json",
            "history.jsonl",
            "session_index.jsonl",
            "transcription-history.jsonl",
            "state.sqlite",
            "state.sqlite-shm",
            "state.sqlite-wal",
        }
        for path in ROOT.rglob("*"):
            if not path.exists() or not path.is_file():
                continue
            relative_parts = {part.lower() for part in path.relative_to(ROOT).parts}
            with self.subTest(runtime_path=self._relative(path)):
                self.assertFalse(relative_parts & actual_runtime_names)

    def test_reusable_text_allows_contextual_vendor_names_but_blocks_private_material(self) -> None:
        self.assertTrue(RECONCILIATION_POLICY.is_file())
        policy_text = RECONCILIATION_POLICY.read_text(encoding="utf-8").lower()
        self.assertIn("vendor", policy_text)
        self.assertIn("superpowers methodology", policy_text)
        self.assertIn("## application toolkits", policy_text)

        for path, text in self._text_files():
            relative = self._relative(path)
            with self.subTest(path=relative, check="user profile"):
                self.assertIsNone(ACTUAL_USER_PROFILE_PATTERN.search(text))

            # Vendor and product names are legitimate in reconciliation
            # guidance, integrations, and other contextual documentation.
            # Portability is enforced at the machine/private boundary below
            # instead of by a brittle project-name blacklist.
            for pattern in (
                PRIVATE_KEY_PATTERN,
                URL_CREDENTIAL_PATTERN,
                ASSIGNED_CREDENTIAL_PATTERN,
                BEARER_TOKEN_PATTERN,
                TOKEN_PREFIX_PATTERN,
            ):
                with self.subTest(path=relative, check=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_reusable_assets_have_no_device_workspace_or_tenant_binding(self) -> None:
        # Cover documentation and optional patches as well as installed assets.
        # Synthetic code-test fixtures remain outside this publication contract.
        extensions = {".md", ".toml", ".json", ".yaml", ".yml", ".patch"}
        concrete_drive_path = re.compile(r"\b[a-z]:[\\/]+(?![\\/<{])", re.I)
        tenant_url = re.compile(r"https?://[a-z0-9-]+\.(?:atlassian\.net|ghe\.com)\b", re.I)
        for path, text in self._text_files():
            if path.suffix.lower() not in extensions:
                continue
            with self.subTest(path=self._relative(path)):
                self.assertIsNone(concrete_drive_path.search(text))
                self.assertIsNone(tenant_url.search(text))
        self.assertNotIn("projects", self.config)


if __name__ == "__main__":
    unittest.main()
