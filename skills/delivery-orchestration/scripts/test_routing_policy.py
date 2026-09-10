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
    "astra_advisor": ("gpt-6-astra", "high"),
}
MATRIX = {**GENERAL_ROUTING_MATRIX, "astra_reviewer": ("gpt-6-astra", "high")}
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
        self.assertEqual((self.config["model"], self.config["model_reasoning_effort"]), ("gpt-6-astra", "low"))
        self.assertEqual((self.agents["default_subagent_model"], self.agents["default_subagent_reasoning_effort"]), ("gpt-5.6-luna", "max"))
        self.assertEqual(self.agents["max_depth"], 1)
        self.assertEqual(self.agents["max_concurrent_threads_per_session"], 6)

    def test_registered_profiles_and_actual_bindings(self):
        registered = {k for k, v in self.agents.items() if isinstance(v, dict) and "config_file" in v}
        self.assertEqual(registered, set(MATRIX))
        self.assertEqual({p.stem for p in (CODEX_HOME / "agents").glob("*.toml")}, set(MATRIX))
        for name, binding in MATRIX.items():
            with self.subTest(profile=name):
                profile = self.profiles[name]
                self.assertEqual(profile["name"], name)
                self.assertEqual((profile["model"], profile["model_reasoning_effort"]), binding)

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

    def test_terminal_leaf_and_read_only_roles(self):
        for name, profile in self.profiles.items():
            with self.subTest(profile=name):
                instruction = profile["developer_instructions"].lower()
                self.assertTrue(bool(re.search(r"do not[^.\n]*spawn", instruction)), f"{name}: missing no-spawn rule")
                expected = "read-only" if name.endswith(("scanner", "advisor", "reviewer")) else "workspace-write"
                self.assertEqual(profile["sandbox_mode"], expected)

    def test_writers_have_ownership_and_external_action_limits(self):
        for name, profile in self.profiles.items():
            if profile["sandbox_mode"] == "workspace-write":
                self.require_rules(profile["developer_instructions"].lower(),
                    ("ownership", "do not commit", "push", "deploy", "external systems"), name)

    def test_advisor_and_reviewer_can_return_engineering_verdict(self):
        for name in ("astra_advisor", "astra_reviewer"):
            instruction = self.profiles[name]["developer_instructions"].lower()
            self.require_rules(instruction, ("verdict", "evidence", "risk"), name)
        advisor = self.profiles["astra_advisor"]["developer_instructions"].lower()
        self.require_rules(advisor, ("early checkpoint", "final-plan checkpoint", "final-delivery checkpoint", "root"), "advisor checkpoints")
        self.assertFalse("do not disposition findings or conclusions" in advisor, "advisor must be able to give an engineering verdict")

    def test_advisor_final_checkpoint_covers_integrated_delivery(self):
        advisor = self.profiles["astra_advisor"]["developer_instructions"].lower()
        self.require_rules(advisor, (
            "integrated deliverable", "interfaces", "maintainability",
            "verification evidence", "remaining risks", "approve, revise, or blocked",
            "unverified areas", "root owns acceptance or rejection",
        ), "advisor final checkpoint")

    def test_delegation_is_active_and_progress_aware(self):
        self.require_rules(self.skill + self.global_rules,
            ("decomposition", "new evidence", "bottleneck", "before integration",
             "independent", "handoff", "root rework", "productive long-running",
             "one live writer", "reuse"), "delegation")
        for stale in ("four or more substantive stages", "after two repetitions", "sol low root"):
            self.assertFalse(stale in self.skill + self.topology, f"retired routing rule: {stale}")

    def test_cost_routes_and_capability_boundaries(self):
        self.require_rules(self.skill + self.topology,
            ("luna_fast_worker", "sol_fast_worker", "low-ambiguity",
             "focused verification", "critical path", "user-provided",
             "do not require a failed", "capability",
             "root-selected capability candidate"), "cost routing")
        self.require_rules(self.global_rules,
            ("root review does not justify", "primary", "substantive"), "capability floor")

    def test_user_benchmark_table_is_explicitly_qualified(self):
        self.require_rules(self.topology, (
            "starting estimates rather than verified universal metrics",
            "comparable quality outside",
            "| luna xhigh | 35 | $0.085 | 3.6 min |",
            "| luna max | 38 | $0.18 | 6.3 min |",
            "| sol low | 34 | $0.26 | 1.2 min |",
            "| astra low | 46 | $0.82 | 1.5 min |",
            "| astra high | 51 | $1.72 | 4.0 min |",
            "| sol high (comparison only) | 42 | $0.81 | 3.8 min |",
        ), "user benchmark table")

    def test_spark_packets_are_bounded(self):
        self.require_rules(self.topology, ("self-contained", "bounded", "anchor", "current model catalog"), "Spark")
        self.assertTrue(bool(re.search(r'fork_turns\s*=\s*["\x27]none', self.topology)), "Spark requires a fresh packet")
        self.assertFalse(bool(re.search(r"\b(?:128k|272k)\b", self.topology)), "context limits must not be frozen in routing prose")

    def test_final_approval_and_required_risk_review(self):
        self.require_rules(self.global_rules + self.topology,
            ("every final deliverable", "engineering review and approval",
             "astra root", "astra high", "integrated outcome", "privacy",
             "data integrity", "concurrency", "public-contract", "required",
             "optional", "file count", "stage count"), "senior sign-off")

    def test_git_and_scope_guards(self):
        self.require_rules(self.skill + self.global_rules,
            ("explicit user or repository branch policy", "never force-push",
             "ahead-of-upstream", "explicit paths or hunks", "remote-ref verification",
             "task commit must be an ancestor", "no push", "keep local",
             "pull requests, merges, releases, and deployments remain separately authorized"),
            "Git completion")

if __name__ == "__main__":
    unittest.main()
