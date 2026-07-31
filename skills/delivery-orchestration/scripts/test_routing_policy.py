from __future__ import annotations

import os
from pathlib import Path
import tomllib
import unittest


CODEX_HOME = Path(
    os.environ.get("CODEX_ROUTING_HOME", Path.home() / ".codex")
).resolve()


def load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = CODEX_HOME / "config.toml"
        cls.config = load_toml(cls.config_path)
        cls.agents = cls.config["agents"]

    def load_agent(self, name: str) -> dict:
        relative_path = self.agents[name]["config_file"]
        return load_toml((self.config_path.parent / relative_path).resolve())

    def test_root_and_untyped_subagent_defaults(self) -> None:
        self.assertEqual(self.config["model"], "gpt-5.6-sol")
        self.assertEqual(self.config["model_reasoning_effort"], "medium")
        self.assertEqual(
            self.agents["default_subagent_model"], "gpt-5.6-luna"
        )
        self.assertEqual(
            self.agents["default_subagent_reasoning_effort"], "high"
        )
        self.assertEqual(self.agents["max_depth"], 3)
        self.assertEqual(
            self.agents["max_concurrent_threads_per_session"], 8
        )

    def test_registered_model_effort_contract(self) -> None:
        expected = {
            "spark_scanner": ("gpt-5.3-codex-spark", "high"),
            "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
            "luna_scanner": ("gpt-5.6-luna", "medium"),
            "luna_worker": ("gpt-5.6-luna", "high"),
            "luna_coordinator": ("gpt-5.6-luna", "high"),
            "terra_worker": ("gpt-5.6-terra", "medium"),
            "terra_coordinator": ("gpt-5.6-terra", "medium"),
            "sol_worker": ("gpt-5.6-sol", "xhigh"),
            "sol_advisor": ("gpt-5.6-sol", "max"),
            "sol_coordinator": ("gpt-5.6-sol", "max"),
        }

        registered = {
            name
            for name, value in self.agents.items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(registered, set(expected))
        self.assertNotIn("spark_coordinator", registered)
        self.assertFalse((CODEX_HOME / "agents" / "spark_coordinator.toml").exists())

        for name, (model, effort) in expected.items():
            with self.subTest(agent=name):
                agent = self.load_agent(name)
                self.assertEqual(agent["model"], model)
                self.assertEqual(agent["model_reasoning_effort"], effort)

    def test_terminal_leaf_depth_contract(self) -> None:
        for name in (
            "spark_scanner",
            "spark_worker",
            "luna_scanner",
            "luna_worker",
        ):
            with self.subTest(agent=name):
                instructions = self.load_agent(name)["developer_instructions"].lower()
                self.assertIn("depths 1, 2, or 3", instructions)
                self.assertRegex(instructions, r"do not[^.\n]*spawn")

    def test_depth_two_coordinators_can_use_terminal_spark_or_luna(self) -> None:
        terminal_profiles = (
            "spark_scanner",
            "spark_worker",
            "luna_scanner",
            "luna_worker",
        )
        for name in (
            "luna_coordinator",
            "terra_coordinator",
        ):
            with self.subTest(agent=name):
                instructions = self.load_agent(name)["developer_instructions"]
                self.assertIn("At depth 2", instructions)
                for profile in terminal_profiles:
                    self.assertIn(profile, instructions)
                self.assertNotIn("spark_coordinator", instructions)

    def test_sol_coordinator_uses_only_non_sol_children(self) -> None:
        instructions = self.load_agent("sol_coordinator")["developer_instructions"]
        self.assertNotIn("spark_coordinator", instructions)
        self.assertIn("Never spawn Sol", instructions)

    def test_delivery_skill_declares_the_routing_invariants(self) -> None:
        skill = (
            CODEX_HOME / "skills" / "delivery-orchestration" / "SKILL.md"
        ).read_text(encoding="utf-8").lower()
        topology = (
            CODEX_HOME
            / "skills"
            / "delivery-orchestration"
            / "references"
            / "delegation-topology.md"
        ).read_text(encoding="utf-8").lower()
        flat_skill = " ".join(skill.split())

        for phrase in (
            "sol medium root",
            "spark fast path",
            "luna is the default",
            "escalate the model",
        ):
            self.assertIn(phrase, flat_skill)

        for phrase in (
            "use `spark_scanner` at high effort or `spark_worker` at xhigh effort",
            "use `luna_scanner` at medium effort and `luna_worker` or "
            "`luna_coordinator` at high effort",
        ):
            self.assertIn(phrase, flat_skill)

        for row in (
            "| spark scanner | high |",
            "| spark worker | xhigh |",
            "| luna scanner | medium |",
            "| luna worker | high |",
            "| luna coordinator | high |",
            "| terra worker | medium |",
            "| terra coordinator | medium |",
            "| sol advisor | max |",
            "| sol worker | xhigh |",
            "| sol coordinator | max |",
        ):
            self.assertIn(row, topology)

        self.assertIn("depth 3", topology)
        for stale_row in (
            "| spark scanner | low |",
            "| spark worker | medium |",
            "| luna scanner | low |",
            "| luna worker | medium |",
            "| luna coordinator | medium |",
        ):
            self.assertNotIn(stale_row, topology)


if __name__ == "__main__":
    unittest.main()
