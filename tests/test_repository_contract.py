from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]

GENERAL_ROUTING_MATRIX = {
    "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
    "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
    "luna_scanner": ("gpt-5.6-luna", "medium"),
    "luna_worker": ("gpt-5.6-luna", "max"),
    "sol_worker": ("gpt-5.6-sol", "xhigh"),
    "sol_advisor": ("gpt-5.6-sol", "max"),
}
REVIEWER_PROFILE_NAME = "sol_reviewer"
REVIEWER_PROFILE = ("gpt-5.6-sol", "max")


class RepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "config.toml").open("rb") as stream:
            cls.config = tomllib.load(stream)

    def test_config_registers_only_the_supported_routing_matrix(self) -> None:
        agents = self.config["agents"]
        self.assertNotIn(REVIEWER_PROFILE_NAME, GENERAL_ROUTING_MATRIX)

        self.assertEqual(
            (self.config["model"], self.config["model_reasoning_effort"]),
            ("gpt-5.6-sol", "low"),
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
        self.assertEqual(
            registered,
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )
        self.assertEqual(
            agents[REVIEWER_PROFILE_NAME]["description"],
            "On-demand read-only Sol reviewer for root-prepared consequential delivery evidence packets.",
        )
        self.assertTrue(registered)

        profile_files = {
            path.stem for path in (ROOT / "agents").glob("*.toml")
        }
        self.assertEqual(
            profile_files,
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )
        self.assertFalse(
            any("terra" in name or "coordinator" in name for name in profile_files)
        )

        for name, wanted in GENERAL_ROUTING_MATRIX.items():
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
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )
        self.assertFalse(any(name.endswith("_coordinator") for name in registered))

        for name in GENERAL_ROUTING_MATRIX:
            with self.subTest(agent=name):
                instructions = (
                    ROOT / self.config["agents"][name]["config_file"]
                ).read_text(encoding="utf-8").lower()
                self.assertRegex(instructions, r"do not[^.\n]*spawn")

    def test_on_demand_reviewer_profile_is_read_only_and_evidence_bound(self) -> None:
        agents = self.config["agents"]
        self.assertIn(REVIEWER_PROFILE_NAME, agents)
        reviewer_path = ROOT / agents[REVIEWER_PROFILE_NAME]["config_file"]
        self.assertTrue(reviewer_path.is_file())
        with reviewer_path.open("rb") as stream:
            reviewer = tomllib.load(stream)

        self.assertEqual(reviewer["name"], REVIEWER_PROFILE_NAME)
        self.assertEqual(
            (reviewer["model"], reviewer["model_reasoning_effort"]),
            REVIEWER_PROFILE,
        )
        self.assertEqual(reviewer["sandbox_mode"], "read-only")
        instructions = reviewer["developer_instructions"].lower()
        for phrase in (
            "operate only at depth 1",
            "do not spawn",
            "do not emit a receipt",
            "root-prepared evidence packet",
            "evidence anchors",
            "verdict",
        ):
            self.assertIn(phrase, instructions)
        self.assertRegex(instructions, r"do not[^.\n]*(?:edit|mutate)")

    def test_runtime_assets_do_not_reference_retired_profiles(self) -> None:
        retired = (
            "spark_" + "coordinator",
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

    def test_readme_explains_routing_methodology_and_rejected_alternatives(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        normalized = " ".join(readme.split())

        for heading in (
            "## routing decision method",
            "## why terra is not configured",
            "## why the other model efforts are not configured",
            "## when to revisit the matrix",
        ):
            self.assertIn(heading, readme)

        for phrase in (
            "hard gates",
            "pareto",
            "role-specific weights",
            "distinct routing region",
            "benchmark snapshot",
            "provisional estimates",
            "not universal pricing",
            "121,600",
            "258,400",
            "terra low",
            "terra medium",
            "terra high",
            "terra xhigh",
            "terra max",
            "luna medium scanner",
            "sol low root",
            "root-owned synthesis",
            "direct root path",
            "luna medium",
            "luna xhigh",
            "sol low",
            "sol high",
            "sol ultra",
            "$0.0151",
            "$0.0289",
            "$0.1598",
            "$0.0431",
            "$0.3041",
            "$0.0658",
            "$0.4300",
            "$0.7328",
            "$1.1671",
            "38.5%",
            "40.2%",
            "measured operating default",
            "zero additional critical/high misses",
        ):
            self.assertIn(phrase, normalized)

    def test_registered_skills_exist_and_use_relative_paths(self) -> None:
        skill_paths = [
            entry["path"] for entry in self.config.get("skills", {}).get("config", [])
        ]
        self.assertEqual(len(skill_paths), 4)
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
        self.assertEqual(
            set(hooks),
            {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"},
        )

        learning_script = "instruction_learning_hook.py"
        for event in ("PreToolUse", "PostToolUse"):
            with self.subTest(event=event):
                self.assertEqual(len(hooks[event]), 1)
                self.assertEqual(
                    hooks[event][0]["matcher"],
                    r"^(Bash|apply_patch|mcp__.*)$",
                )
                self.assertEqual(len(hooks[event][0]["hooks"]), 1)
                self.assertIn(
                    learning_script,
                    hooks[event][0]["hooks"][0]["command"],
                )

        serialized = json.dumps(hooks).lower()
        self.assertNotIn("adversarial-code-review", serialized)
        self.assertNotIn("lifecycle_gate.py", serialized)
        self.assertNotIn("c:\\\\users\\\\", serialized)
        self.assertNotIn("m." + "pincoski", serialized)
        self.assertIn("os.environ.get('codex_home')", serialized)
        self.assertIn("os.path.expanduser('~/.codex')", serialized)
        self.assertNotIn("%userprofile%", serialized)
        for event in hooks.values():
            for group in event:
                for entry in group["hooks"]:
                    self.assertRegex(entry["command"], r'^python3 -B -c ".+"$')
                    self.assertRegex(entry["commandWindows"], r'^python -B -c ".+"$')

    def test_review_policy_is_risk_triggered_and_low_risk_work_is_not_blocked(self) -> None:
        root_facing = (
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "skills" / "adversarial-code-review" / "references" / "managed-agents-instruction.md",
            ROOT / "skills" / "delivery-orchestration" / "SKILL.md",
        )
        combined = " ".join(path.read_text(encoding="utf-8").lower() for path in root_facing)
        normalized = " ".join(combined.split())
        for phrase in (
            "root-routed independent review",
            "security, authentication, credentials",
            "reversible startup-setting changes",
            "`agents.md` wording",
            "optional review infrastructure fails",
            "only a required high-risk review failure blocks delivery",
        ):
            self.assertIn(phrase, normalized)
        for path in root_facing:
            policy = " ".join(path.read_text(encoding="utf-8").lower().split())
            with self.subTest(path=path):
                for phrase in ("privacy", "public-contract", "repeated failed verification"):
                    self.assertIn(phrase, policy)
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
            "root cause is established",
            "fix is freshly verified",
            "agent verification remains provisional",
            "explicitly confirms the issue is resolved in later testing",
            "later user report supersedes",
        ):
            self.assertIn(phrase, agents)

        for phrase in (
            "candidate resolution",
            "does not by itself require an instruction change",
            "awaiting user confirmation",
            "never expires",
            "supersedes",
            "exactly one active instruction-learning handler",
            "`/hooks`",
            "fresh session",
        ):
            self.assertIn(phrase, skill)

    def test_plan_review_docs_exclude_the_on_demand_delivery_reviewer(self) -> None:
        for path in (
            ROOT / "skills" / "plan-review-ladder" / "SKILL.md",
            ROOT / "skills" / "plan-review-ladder" / "references" / "review-lenses.md",
        ):
            text = " ".join(path.read_text(encoding="utf-8").lower().split())
            with self.subTest(path=path):
                self.assertIn("on-demand `sol_reviewer` delivery-review identity", text)
                self.assertNotIn("gate-only", text)

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

    def test_digest_bound_evaluation_fixtures_are_checked_out_with_lf_endings(self) -> None:
        fixture_root = (
            ROOT
            / "skills"
            / "adversarial-code-review"
            / "references"
            / "evaluation-inputs"
        )
        fixtures = sorted(
            fixture_root.glob("*.txt")
        )
        relative = [path.relative_to(ROOT).as_posix() for path in fixtures]

        result = subprocess.run(
            ["git", "check-attr", "eol", "--", *relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(relative)
        self.assertEqual(
            result.stdout.splitlines(),
            [f"{path}: eol: lf" for path in relative],
        )

    def test_reusable_text_excludes_local_and_project_material(self) -> None:
        forbidden_patterns = (
            re.escape("m." + "pincoski"),
            re.escape("c:" + "\\users\\"),
            r"\b" + "crea" + "tio" + r"\b",
            r"\b" + "bank" + r"\.ai\b",
            r"\b" + "one" + "drive" + r"\b",
        )
        excluded_dirs = {".git", ".superpowers", "__pycache__", ".pytest_cache", ".mypy_cache"}
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
