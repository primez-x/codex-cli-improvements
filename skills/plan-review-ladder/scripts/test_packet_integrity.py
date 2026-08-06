from __future__ import annotations

import copy
import unittest

from packet_integrity import (
    build_packet_envelope,
    canonical_bytes,
    compute_packet_sha256,
    compute_raw_sha256,
    verify_packet_envelope,
)

DEFAULT_STATUS_CHECK_MINUTES = 15
DEFAULT_UNRESPONSIVE_GRACE_MINUTES = 3


class PacketIntegrityTests(unittest.TestCase):
    def test_compute_raw_sha256_hashes_exact_bytes(self) -> None:
        self.assertEqual(
            compute_raw_sha256(b"\x00review\xff"),
            "9747cddf1054f045ffe4018535821a320986f45d596249eefc49eaca327d0ff3",
        )

    def setUp(self) -> None:
        self.payload = {
            "packet_id": "packet-001",
            "request": {"goal": "review", "constraints": ["read-only"]},
            "evidence": {"files": ["SKILL.md"], "head": "abc123"},
            "candidate": {"route": "Standard", "steps": ["inspect"]},
            "reviewer_lens": "luna-contract-completeness",
            "reviewer_profile": "luna_scanner",
            "status_check_minutes": 10,
            "unresponsive_grace_minutes": 2,
        }

    def test_canonical_bytes_sort_nested_keys_without_insignificant_whitespace(self) -> None:
        value = {"z": {"b": 2, "a": "é"}, "a": [3, {"d": 4, "c": 1}]}
        self.assertEqual(
            canonical_bytes(value),
            '{"a":[3,{"c":1,"d":4}],"z":{"a":"é","b":2}}'.encode("utf-8"),
        )

    def test_build_freezes_payload_and_declares_lowercase_digest(self) -> None:
        envelope = build_packet_envelope(self.payload)
        self.assertEqual(envelope["packet_sha256"], compute_packet_sha256(self.payload))
        self.assertEqual(envelope["packet_sha256"], envelope["packet_sha256"].lower())
        self.assertEqual(envelope["packet_payload"]["status_check_minutes"], 10)
        with self.assertRaises(TypeError):
            envelope["packet_sha256"] = "0" * 64
        with self.assertRaises(TypeError):
            envelope["packet_payload"]["packet_id"] = "changed"

    def test_frozen_dict_blocks_in_place_union_without_mutation(self) -> None:
        envelope = build_packet_envelope(self.payload)
        payload = envelope["packet_payload"]
        before = dict(payload)
        with self.assertRaises(TypeError):
            payload |= {"unexpected": True}
        self.assertEqual(dict(payload), before)
        self.assertNotIn("unexpected", payload)

    def test_defaults_are_frozen_when_budget_values_are_omitted_at_build(self) -> None:
        payload = copy.deepcopy(self.payload)
        del payload["status_check_minutes"]
        del payload["unresponsive_grace_minutes"]
        envelope = build_packet_envelope(payload)
        self.assertIn("status_check_minutes", envelope["packet_payload"])
        self.assertIn("unresponsive_grace_minutes", envelope["packet_payload"])
        self.assertEqual(
            envelope["packet_payload"]["status_check_minutes"], DEFAULT_STATUS_CHECK_MINUTES
        )
        self.assertEqual(
            envelope["packet_payload"]["unresponsive_grace_minutes"], DEFAULT_UNRESPONSIVE_GRACE_MINUTES
        )

    def test_mutation_after_hash_is_rejected(self) -> None:
        envelope = build_packet_envelope(self.payload)
        tampered = dict(envelope)
        tampered_payload = copy.deepcopy(dict(envelope["packet_payload"]))
        tampered_payload["request"]["goal"] = "mutated"
        tampered["packet_payload"] = tampered_payload
        with self.assertRaises(ValueError):
            verify_packet_envelope(tampered)

    def test_malformed_or_unobserved_digest_is_rejected(self) -> None:
        envelope = build_packet_envelope(self.payload)
        malformed = {"packet_payload": dict(envelope["packet_payload"]), "packet_sha256": "bad"}
        with self.assertRaises(ValueError):
            verify_packet_envelope(malformed)
        with self.assertRaises(ValueError):
            verify_packet_envelope(
                envelope, observed_packet_sha256="0" * 64
            )
        self.assertEqual(
            verify_packet_envelope(
                envelope, observed_packet_sha256=envelope["packet_sha256"]
            ),
            envelope["packet_sha256"],
        )

    def test_missing_or_invalid_budgets_are_rejected_before_dispatch(self) -> None:
        for field in ("status_check_minutes", "unresponsive_grace_minutes"):
            payload = copy.deepcopy(self.payload)
            del payload[field]
            envelope = {
                "packet_payload": payload,
                "packet_sha256": compute_packet_sha256(payload),
            }
            with self.assertRaises(ValueError):
                verify_packet_envelope(envelope)
        for field, value in (
            ("status_check_minutes", 0),
            ("status_check_minutes", 46),
            ("unresponsive_grace_minutes", 0),
            ("unresponsive_grace_minutes", 6),
            ("status_check_minutes", True),
        ):
            payload = copy.deepcopy(self.payload)
            payload[field] = value
            with self.assertRaises(ValueError):
                build_packet_envelope(payload)

    def test_all_supported_profiles_are_terminal(self) -> None:
        supported_profiles = {
            "spark_scanner",
            "luna_scanner",
            "sol_advisor",
        }
        for profile in supported_profiles:
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            self.assertIsNotNone(build_packet_envelope(payload))
        for profile in (
            "spark_worker",
            "luna_worker",
            "sol_worker",
            "terra_worker",
            "terra_coordinator",
            "luna_coordinator",
            "sol_coordinator",
            "spark_coordinator",
            "sol_reviewer",
            "unknown_profile",
        ):
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            with self.assertRaises(ValueError):
                build_packet_envelope(payload)

    def test_supported_profile_defaults_select_new_status_budgets(self) -> None:
        for profile in (
            "spark_scanner",
            "luna_scanner",
            "sol_advisor",
        ):
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            payload.pop("status_check_minutes")
            payload.pop("unresponsive_grace_minutes")
            envelope = build_packet_envelope(payload)
            self.assertIn("status_check_minutes", envelope["packet_payload"])
            self.assertIn("unresponsive_grace_minutes", envelope["packet_payload"])
            self.assertEqual(envelope["packet_payload"]["status_check_minutes"], DEFAULT_STATUS_CHECK_MINUTES)
            self.assertEqual(envelope["packet_payload"]["unresponsive_grace_minutes"], DEFAULT_UNRESPONSIVE_GRACE_MINUTES)

    def test_retired_budget_fields_are_rejected_explicitly(self) -> None:
        for field in ("deadline_minutes", "grace_minutes", "descendant_budget"):
            payload = copy.deepcopy(self.payload)
            payload[field] = 1
            with self.assertRaises(ValueError):
                build_packet_envelope(payload)


if __name__ == "__main__":
    unittest.main()
