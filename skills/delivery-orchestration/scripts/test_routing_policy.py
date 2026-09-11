"""Focused installed routing contracts; never print private instruction contents."""
from __future__ import annotations

import os
from pathlib import Path
import re
import tomllib
import unittest

CODEX_HOME = Path(os.environ.get("CODEX_ROUTING_HOME", Path.home() / ".codex")).resolve()
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
MATRIX = GENERAL_ROUTING_MATRIX
ROOT_SERVERS = {"clio", "creatio", "chrome-devtools", "node_repl"}

def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))

class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read_toml(CODEX_HOME / "config.toml")
        cls.agents = cls.config["agents"]
        cls.profiles = {
            name: read_toml((CODEX_HOME / cls.agents[name]["config_file"]).resolve())
            for name in MATRIX
        }
        cls.skill = (CODEX_HOME / "skills/delivery-orchestration/SKILL.md").read_text(encoding="utf-8").lower()
        cls.topology = (CODEX_HOME / "skills/delivery-orchestration/references/delegation-topology.md").read_text(encoding="utf-8").lower()
        cls.global_rules = (CODEX_HOME / "AGENTS.md").read_text(encoding="utf-8").lower()

    def require_rules(self, text, rules, scope):
        flat = " ".join(text.split())
        # Report rule names, never source text: AGENTS.md may contain private data.
        for rule in rules:
            with self.subTest(scope=scope, rule=rule):
                self.assertTrue(rule in flat, f"{scope}: required rule absent: {rule}")

    def test_root_and_default_delegation(self):
        self.assertEqual((self.config["model"], self.config["model_reasoning_effort"]), ("gpt-5.6-luna", "xhigh"))
        self.assertEqual((self.agents["default_subagent_model"], self.agents["default_subagent_reasoning_effort"]), ("gpt-6-astra", "medium"))
        self.assertEqual(self.agents["max_depth"], 2)
        self.assertEqual(self.agents["max_concurrent_threads_per_session"], 6)
        self.assertIs(self.agents["enabled"], True)
        self.assertEqual(
            self.config["features"]["multi_agent_v2"],
            {
                "enabled": True,
                "min_wait_timeout_ms": 1500000,
                "default_wait_timeout_ms": 1500000,
                "max_wait_timeout_ms": 1500000,
            },
        )

    def test_registered_profiles_and_actual_bindings(self):
        registered = {k for k, v in self.agents.items() if isinstance(v, dict) and "config_file" in v}
        self.assertEqual(registered, set(MATRIX))
        self.assertEqual({p.stem for p in (CODEX_HOME / "agents").glob("*.toml")}, set(MATRIX))
        for name, binding in MATRIX.items():
            with self.subTest(profile=name):
                profile = self.profiles[name]
                self.assertEqual(profile["name"], name)
                self.assertEqual((profile["model"], profile["model_reasoning_effort"]), binding)
                config_description = self.agents[name]["description"].lower()
                for stale in ("terminal leaf", "terminal worker", "terminal writer", "read-only leaf"):
                    self.assertNotIn(stale, config_description)
                description = profile["description"].lower()
                for stale in ("terminal leaf", "terminal worker", "terminal writer", "read-only leaf"):
                    self.assertNotIn(stale, description)

    def test_all_profiles_preserve_root_mcp_ownership(self):
        # A portable kit does not configure the user's root MCP connections.
        root_servers = self.config.get("mcp_servers", {})
        for name in ROOT_SERVERS & root_servers.keys():
            self.assertNotEqual(root_servers[name].get("enabled"), False)
        for name, profile in self.profiles.items():
            with self.subTest(profile=name):
                self.assertEqual(set(profile["mcp_servers"]), ROOT_SERVERS)
                for server in profile["mcp_servers"].values():
                    self.assertIs(server["enabled"], False)
                    self.assertEqual(server["command"], "__codex_disabled_mcp_transport_never_run__")
                    self.assertEqual(server["args"], [])

    def test_depth_eligibility_and_terminal_roles(self):
        root_critics = {"astra_advisor"}
        for name, profile in self.profiles.items():
            with self.subTest(profile=name):
                instruction = profile["developer_instructions"].lower()
                flat = " ".join(instruction.split())
                expected = "read-only" if name.endswith(("scanner", "advisor")) else "workspace-write"
                self.assertEqual(profile["sandbox_mode"], expected)
                self.assertIs(profile["agents"]["enabled"], True)

                if name in root_critics:
                    self.require_rules(
                        flat,
                        ("assigned depth", "depth-1", "depth-2", "terminal", "do not fork", "do not spawn", "fresh self-contained packet", "cache window", "root"),
                        name,
                    )
                else:
                    self.require_rules(
                        flat,
                        ("assigned depth", "depth-1", "depth-2", "terminal", "do not fork", "do not spawn", "fresh self-contained packet", "cache window"),
                        name,
                    )

                self.assertIn("30-minute cache window", flat)
                self.assertNotIn("may subdivide", flat)
                self.assertNotIn("subdelegate", flat)
                self.assertNotIn("act as a terminal", flat)

    def test_writers_have_ownership_and_external_action_limits(self):
        for name, profile in self.profiles.items():
            if profile["sandbox_mode"] == "workspace-write":
                self.require_rules(profile["developer_instructions"].lower(),
                    ("ownership", "do not commit", "push", "deploy", "external systems"), name)

    def test_advisor_can_criticize_approach_or_integrated_delivery(self):
        advisor = self.profiles["astra_advisor"]["developer_instructions"].lower()
        self.require_rules(
            advisor,
            ("approach", "integrated delivery", "verdict", "evidence", "risk", "root"),
            "astra advisor",
        )
        self.assertFalse(
            "do not disposition findings or conclusions" in advisor,
            "advisor must be able to give an engineering verdict",
        )

    def test_advisor_delivery_critique_covers_integrated_evidence(self):
        advisor = self.profiles["astra_advisor"]["developer_instructions"].lower()
        self.require_rules(
            advisor,
            ("integrated deliverable", "interfaces", "maintainability", "verification", "remaining risks"),
            "astra advisor delivery critique",
        )

    def test_delegation_is_active_and_progress_aware(self):
        combined = self.skill + self.topology + self.global_rules
        self.assertIn("terminal subagent", combined, "delegation topology: terminal rule absent")
        self.assertIn("fresh self-contained packet", combined, "delegation topology: fresh context rule absent")
        self.assertIn("do not fork", combined, "delegation topology: no-fork rule absent")
        self.assertIn("30-minute cache window", combined, "delegation topology: continuation window absent")
        self.assertRegex(combined, r"depth[- ]?2", "delegation topology: depth-2 rule absent")
        self.assertIn("may spawn", combined, "delegation topology: child fan-out rule absent")
        self.assertRegex(combined, r"depth(?:s|\s+)?1", "delegation topology: depth rule absent")
        self.assertRegex(combined, r"six[- ](?:thread|concurrent)", "delegation topology: concurrency rule absent")
        self.assertIn("root owns", combined, "delegation topology: root ownership rule absent")

    def test_cost_routes_and_capability_boundaries(self):
        self.require_rules(
            self.skill + self.topology,
            ("luna_worker", "astra_worker", "astra_low_worker", "sol_fast_worker", "capability"),
            "cost routing",
        )
        self.require_rules(
            self.global_rules,
            ("luna root review is sufficient", "astra medium", "primary capable code"),
            "capability floor",
        )

    def test_spark_packets_are_bounded(self):
        self.require_rules(self.topology, ("self-contained", "bounded", "fork_turns"), "Spark")
        self.assertTrue(bool(re.search(r'fork_turns\s*=\s*["\x27]none', self.topology)), "Spark requires a fresh packet")
        self.assertFalse(bool(re.search(r"\b(?:128k|272k)\b", self.topology)), "context limits must not be frozen in routing prose")

    def test_final_approval_and_required_risk_review(self):
        self.require_rules(
            self.global_rules + self.topology,
            ("reviews and approves every integrated outcome", "luna xhigh root", "astra high", "privacy",
             "data integrity", "required", "optional"),
            "senior sign-off",
        )

    def test_git_and_scope_guards(self):
        self.require_rules(
            self.skill + self.global_rules,
            ("commit", "push", "remote-ref verification", "deployments", "explicit authorization"),
            "Git completion",
        )

if __name__ == "__main__":
    unittest.main()
