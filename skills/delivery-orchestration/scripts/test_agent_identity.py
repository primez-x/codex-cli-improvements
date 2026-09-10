import unittest

from agent_identity import display_label, normalize_task_slug, roster_delta, task_name


class AgentIdentityTests(unittest.TestCase):
    def test_slug_is_deterministic_and_unicode_safe(self):
        self.assertEqual(normalize_task_slug("  Café / API review! "), "cafe_api_review")

    def test_empty_purpose_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_task_slug("---")

    def test_task_name_is_direct_depth_one(self):
        self.assertEqual(task_name("luna_worker", "Review CSS"), "d1_luna_worker_review_css")
        with self.assertRaises(ValueError):
            task_name("luna_worker", "Review CSS", depth=2)

    def test_roster_delta_is_optional_metadata_shape(self):
        label = display_label("luna_worker", "Luna", "max", "Worker", "Review CSS")
        delta = roster_delta("root/luna_worker/review", "d1_luna_worker_review_css", label, "active")
        self.assertEqual(list(delta), ["canonical_task_path", "task_name", "display_label", "status"])
        with self.assertRaises(ValueError):
            roster_delta("p", "n", "l", "running")


if __name__ == "__main__":
    unittest.main()
