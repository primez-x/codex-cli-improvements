from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]

GENERAL_ROUTING_MATRIX = {
    "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
    "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
    "luna_scanner": ("gpt-5.6-luna", "low"),
    "luna_worker": ("gpt-5.6-luna", "medium"),
    "luna_orchestrator": ("gpt-5.6-luna", "max"),
    "sol_worker": ("gpt-5.6-sol", "high"),
    "sol_advisor": ("gpt-5.6-sol", "high"),
}
REVIEWER_PROFILE_NAME = "sol_reviewer"
REVIEWER_PROFILE = ("gpt-5.6-sol", "max")


class RepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "config.toml").open("rb") as stream:
            cls.config = tomllib.load(stream)

    def test_config_registers_the_normalized_role_graph(self) -> None:
        agents = self.config["agents"]
        self.assertNotIn(REVIEWER_PROFILE_NAME, GENERAL_ROUTING_MATRIX)

        self.assertEqual(
            (self.config["model"], self.config["model_reasoning_effort"]),
            ("gpt-5.6-luna", "max"),
        )
        self.assertEqual(agents["max_depth"], 3)
        self.assertEqual(agents["max_concurrent_threads_per_session"], 64)
        self.assertEqual(
            (
                agents["default_subagent_model"],
                agents["default_subagent_reasoning_effort"],
            ),
            ("gpt-5.6-luna", "medium"),
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

    def test_only_scanners_are_legal_at_depth_three(self) -> None:
        registered = {
            name
            for name, value in self.config["agents"].items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(
            registered,
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )
        depth_three = set()
        for name in registered:
            instructions = (
                ROOT / self.config["agents"][name]["config_file"]
            ).read_text(encoding="utf-8").lower()
            if "terminal leaf at depth 1 through depth 3" in instructions:
                depth_three.add(name)

        self.assertEqual(depth_three, {"spark_scanner", "luna_scanner"})

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

    def test_readme_distinguishes_full_kit_deployment_from_reviewer_add_on(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").lower().split())
        for phrase in (
            "adversarial-review add-on",
            "does not install the normalized hierarchy",
            "full normalized kit",
            "existing codex home",
            "merge the `## delegation` section from `agents.md`",
            "preserving unrelated local instructions",
            "exact set of eight source profiles",
            "remove or archive every other agent toml",
            "corresponding retired role registrations",
            "repeat the controlled deployment",
        ):
            self.assertIn(phrase, readme)

    def test_documented_full_kit_projection_is_exact_and_idempotent(self) -> None:
        source_agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        source_config = copy.deepcopy(self.config)
        source_profiles = {
            path.name: path.read_bytes() for path in (ROOT / "agents").glob("*.toml")
        }
        self.assertEqual(len(source_profiles), 8)

        previous_agents = re.sub(
            r"(?ms)^## Delegation\n.*?(?=^##\s|\Z)",
            "## Delegation\n\nUse the retired coordinator hierarchy.\n\n",
            source_agents,
            count=1,
        )
        previous_agents += """
## Local Only

Keep this machine-only instruction.
Preserve this unrelated local instruction.
"""
        previous_config = {
            "model": "retired-root",
            "model_reasoning_effort": "low",
            "mcp_servers": {"local": {"url": "http://127.0.0.1:9999"}},
            "features": {"multi_agent": False, "other_local_feature": True},
            "agents": {
                "max_depth": 2,
                "local_runtime_setting": "preserve-me",
                "terra_worker": {"config_file": "./agents/terra_worker.toml"},
            },
            "skills": {"config": [{"path": "./skills/retired/SKILL.md"}]},
        }

        def markdown_section(text: str, heading: str) -> str:
            match = re.search(
                rf"(?ms)^{re.escape(heading)}\n.*?(?=^##\s|\Z)", text
            )
            self.assertIsNotNone(match)
            return match.group(0).rstrip() + "\n"

        def merge_delegation(target: str) -> str:
            wanted = markdown_section(source_agents, "## Delegation")
            current = re.search(r"(?ms)^## Delegation\n.*?(?=^##\s|\Z)", target)
            self.assertIsNotNone(current)
            return target[: current.start()] + wanted + "\n" + target[current.end() :]

        def project_config(target: dict[str, object]) -> dict[str, object]:
            projected = copy.deepcopy(target)
            for key in ("model", "model_reasoning_effort"):
                projected[key] = copy.deepcopy(source_config[key])

            target_agents = projected.setdefault("agents", {})
            self.assertIsInstance(target_agents, dict)
            for key in tuple(target_agents):
                value = target_agents[key]
                if isinstance(value, dict) and "config_file" in value:
                    del target_agents[key]
            for key, value in source_config["agents"].items():
                target_agents[key] = copy.deepcopy(value)

            target_features = projected.setdefault("features", {})
            self.assertIsInstance(target_features, dict)
            target_features["multi_agent"] = source_config["features"]["multi_agent"]

            target_skills = projected.setdefault("skills", {})
            self.assertIsInstance(target_skills, dict)
            target_skills["config"] = copy.deepcopy(source_config["skills"]["config"])
            return projected

        with tempfile.TemporaryDirectory() as temporary:
            target_home = Path(temporary) / ".codex"
            target_agents_dir = target_home / "agents"
            archive_dir = Path(temporary) / "retired-agent-profiles"
            target_home.mkdir()
            target_agents_dir.mkdir()
            archive_dir.mkdir()
            (target_agents_dir / "terra_worker.toml").write_text(
                'name = "terra_worker"\n', encoding="utf-8"
            )
            (target_agents_dir / "local-notes.txt").write_text(
                "preserve", encoding="utf-8"
            )

            def reconcile_profiles() -> None:
                for path in target_agents_dir.glob("*.toml"):
                    if path.name not in source_profiles:
                        path.replace(archive_dir / path.name)
                for name, content in source_profiles.items():
                    (target_agents_dir / name).write_bytes(content)

            merged_agents = merge_delegation(previous_agents)
            projected_config = project_config(previous_config)
            reconcile_profiles()

            target_config_text = (ROOT / "config.toml").read_text(encoding="utf-8")
            target_config_text = target_config_text.replace(
                "[agents]\n",
                '[agents]\nlocal_runtime_setting = "preserve-me"\n',
                1,
            ).replace(
                "[features]\n",
                "[features]\nother_local_feature = true\n",
                1,
            )
            target_config_text += (
                "\n[mcp_servers.local]\nurl = \"http://127.0.0.1:9999\"\n"
            )
            (target_home / "AGENTS.md").write_text(merged_agents, encoding="utf-8")
            (target_home / "config.toml").write_text(
                target_config_text, encoding="utf-8"
            )
            for skill_name in (
                "delivery-orchestration",
                "plan-review-ladder",
                "instruction-learning-loop",
                "adversarial-code-review",
            ):
                shutil.copytree(
                    ROOT / "skills" / skill_name,
                    target_home / "skills" / skill_name,
                )
            shutil.copytree(ROOT / "hooks", target_home / "hooks")
            shutil.copy2(ROOT / "hooks.json", target_home / "hooks.json")

            first_agents = merged_agents
            first_config = copy.deepcopy(projected_config)
            first_profiles = {
                path.name: path.read_bytes()
                for path in target_agents_dir.glob("*.toml")
            }

            merged_agents = merge_delegation(merged_agents)
            projected_config = project_config(projected_config)
            reconcile_profiles()
            (target_home / "AGENTS.md").write_text(merged_agents, encoding="utf-8")

            installed_environment = os.environ.copy()
            installed_environment.update(
                {
                    "CODEX_HOME": str(target_home),
                    "CODEX_ROUTING_HOME": str(target_home),
                }
            )
            installed_checks = (
                target_home
                / "skills"
                / "delivery-orchestration"
                / "scripts"
                / "test_routing_policy.py",
                target_home
                / "skills"
                / "plan-review-ladder"
                / "scripts"
                / "test_plan_routing.py",
                target_home
                / "skills"
                / "plan-review-ladder"
                / "scripts"
                / "test_packet_integrity.py",
                target_home
                / "skills"
                / "instruction-learning-loop"
                / "scripts"
                / "test_instruction_learning.py",
                target_home
                / "skills"
                / "instruction-learning-loop"
                / "scripts"
                / "test_global_autonomy_contract.py",
                target_home
                / "skills"
                / "adversarial-code-review"
                / "scripts"
                / "test_install_review_gate.py",
            )
            for check in installed_checks:
                result = subprocess.run(
                    [sys.executable, "-B", str(check)],
                    cwd=target_home,
                    env=installed_environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
                with self.subTest(installed_check=check.relative_to(target_home)):
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
                    )

            lifecycle = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(
                        target_home
                        / "skills"
                        / "adversarial-code-review"
                        / "scripts"
                        / "lifecycle_gate.py"
                    ),
                    "health",
                ],
                cwd=target_home,
                env=installed_environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            self.assertEqual(
                lifecycle.returncode,
                0,
                f"stdout:\n{lifecycle.stdout}\nstderr:\n{lifecycle.stderr}",
            )

            self.assertEqual(merged_agents, first_agents)
            self.assertEqual(projected_config, first_config)
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in target_agents_dir.glob("*.toml")
                },
                first_profiles,
            )
            self.assertEqual(first_profiles, source_profiles)
            self.assertTrue((archive_dir / "terra_worker.toml").is_file())
            self.assertEqual(
                (target_agents_dir / "local-notes.txt").read_text(encoding="utf-8"),
                "preserve",
            )
            self.assertIn("Keep this machine-only instruction.", merged_agents)
            self.assertIn("Preserve this unrelated local instruction.", merged_agents)
            self.assertNotIn("retired coordinator hierarchy", merged_agents)
            self.assertEqual(
                projected_config["mcp_servers"], previous_config["mcp_servers"]
            )
            self.assertTrue(projected_config["features"]["other_local_feature"])
            self.assertEqual(
                projected_config["agents"]["local_runtime_setting"], "preserve-me"
            )
            self.assertNotIn("terra_worker", projected_config["agents"])

    def test_adversarial_contracts_are_self_contained(self) -> None:
        contract = (
            ROOT / "skills" / "adversarial-code-review" / "references" / "contracts.md"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("review_contracts.py", contract)
        self.assertNotIn("plan-review-ladder/scripts/packet_integrity.py", contract)

        for name in ("review_contracts.py", "lifecycle_gate.py", "verification_evidence.py"):
            source = (
                ROOT / "skills" / "adversarial-code-review" / "scripts" / name
            ).read_text(encoding="utf-8").lower()
            with self.subTest(script=name):
                self.assertNotIn("plan-review-ladder", source)

    def test_hooks_are_portable(self) -> None:
        hooks_path = ROOT / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("Stop", hooks)
        self.assertEqual(set(hooks), {"UserPromptSubmit", "Stop"})

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


    def test_repository_contract_roster_examples_and_topology_link(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for label in (
            "D0 · Luna/max · Root · Delivery integration",
            "D1 · Luna/medium · Worker · Component style reviewer",
            "D1 · Spark/xhigh · Scanner · Locate styling contracts",
            "D2 · Luna/low · Scanner · Trace inherited theme rules",
        ):
            self.assertIn(label, readme)
        self.assertRegex(readme, r"delegation-topology\.md")
        self.assertNotIn("Luna worker · Luna/medium", readme)

    def test_owned_contract_tests_are_utf8_and_free_of_mojibake(self) -> None:
        paths = (
            ROOT / "skills" / "delivery-orchestration" / "scripts" / "test_routing_policy.py",
            ROOT / "tests" / "test_repository_contract.py",
        )
        for path in paths:
            raw = path.read_bytes()
            text = raw.decode("utf-8").replace("\r\n", "\n")
            self.assertNotIn(chr(0xC2), text)
            with tempfile.TemporaryDirectory() as temporary:
                roundtrip = Path(temporary) / path.name
                roundtrip.write_text(text, encoding="utf-8")
                self.assertEqual(roundtrip.read_text(encoding="utf-8"), text)

if __name__ == "__main__":
    unittest.main()
