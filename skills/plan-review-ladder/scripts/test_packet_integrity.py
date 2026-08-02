from __future__ import annotations

import copy
import unittest

from packet_integrity import (
    DEFAULT_DEADLINE_MINUTES,
    DEFAULT_GRACE_MINUTES,
    build_packet_envelope,
    canonical_bytes,
    compute_packet_sha256,
    verify_packet_envelope,
    compute_raw_sha256,
)


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
            "candidate": {"route": "Full", "steps": ["inspect"]},
            "reviewer_lens": "sol-adversarial-risk",
            "reviewer_profile": "sol_coordinator",
            "deadline_minutes": 10,
            "grace_minutes": 2,
            "descendant_budget": 1,
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
        self.assertEqual(envelope["packet_payload"]["deadline_minutes"], 10)
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
        del payload["deadline_minutes"]
        del payload["grace_minutes"]
        envelope = build_packet_envelope(payload)
        self.assertEqual(
            envelope["packet_payload"]["deadline_minutes"], DEFAULT_DEADLINE_MINUTES
        )
        self.assertEqual(
            envelope["packet_payload"]["grace_minutes"], DEFAULT_GRACE_MINUTES
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
        for field in ("deadline_minutes", "grace_minutes", "descendant_budget"):
            payload = copy.deepcopy(self.payload)
            del payload[field]
            envelope = {
                "packet_payload": payload,
                "packet_sha256": compute_packet_sha256(payload),
            }
            with self.assertRaises(ValueError):
                verify_packet_envelope(envelope)
        for field, value in (
            ("deadline_minutes", 0),
            ("deadline_minutes", 46),
            ("grace_minutes", 0),
            ("grace_minutes", 6),
            ("descendant_budget", -1),
            ("descendant_budget", 3),
            ("deadline_minutes", True),
        ):
            payload = copy.deepcopy(self.payload)
            payload[field] = value
            with self.assertRaises(ValueError):
                build_packet_envelope(payload)

    def test_profile_compatible_descendant_budgets_are_enforced(self) -> None:
        valid_budgets = {
            "spark_scanner": 0,
            "luna_scanner": 0,
            "sol_advisor": 0,
            "luna_coordinator": 1,
            "terra_coordinator": 1,
            "sol_coordinator": 2,
        }
        for profile, budget in valid_budgets.items():
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            payload["descendant_budget"] = budget
            self.assertIsNotNone(build_packet_envelope(payload))
        for profile, budget in (
            ("spark_scanner", 1),
            ("luna_scanner", 1),
            ("sol_advisor", 1),
            ("luna_coordinator", 0),
            ("terra_coordinator", 0),
            ("luna_coordinator", 2),
            ("terra_coordinator", 2),
            ("sol_coordinator", 0),
            ("sol_coordinator", 3),
            ("spark_worker", 0),
            ("unknown_profile", 0),
        ):
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            payload["descendant_budget"] = budget
            with self.assertRaises(ValueError):
                build_packet_envelope(payload)

    def test_profile_defaults_select_the_required_descendant_budget(self) -> None:
        for profile, expected in (
            ("spark_scanner", 0),
            ("luna_coordinator", 1),
            ("sol_coordinator", 1),
        ):
            payload = copy.deepcopy(self.payload)
            payload["reviewer_profile"] = profile
            payload.pop("descendant_budget")
            envelope = build_packet_envelope(payload)
            self.assertEqual(envelope["packet_payload"]["descendant_budget"], expected)


if __name__ == "__main__":
    unittest.main()
