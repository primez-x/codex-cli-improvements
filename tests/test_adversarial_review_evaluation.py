"""Behavioral tests for authenticated corpus and external replay scoring."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from tests import test_adversarial_review_hooks as hook_helpers


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "adversarial-code-review"
CORPUS = SKILL / "references" / "evaluation-corpus.json"
RESULTS = SKILL / "references" / "evaluation-self-test-results.json"
IDENTITIES = SKILL / "references" / "evaluation-git-identities.json"
EVALUATOR = SKILL / "scripts" / "evaluate_review_corpus.py"
PROFILE = ROOT / "agents" / "sol_reviewer.toml"
CORRECTED_PYTHON = SKILL / "references" / "evaluation-inputs" / "python-shell-boundary-corrected.py.txt"
sys.path.insert(0, str(EVALUATOR.parent))
import evaluate_review_corpus as evaluation_module  # noqa: E402
import review_contracts  # noqa: E402


def remove_hardened_tree(path: Path) -> None:
    """Restore the test account's delete rights before removing immutable evidence."""
    physical = hook_helpers.lifecycle_gate._filesystem_path(path)
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            text=True,
            capture_output=True,
            check=False,
        )
        if identity.returncode != 0:
            raise AssertionError(identity.stderr)
        sid = next(csv.reader([identity.stdout.strip()]))[1]
        restored = subprocess.run(
            [
                "icacls",
                str(physical),
                "/grant:r",
                f"*{sid}:(OI)(CI)(F)",
                "/T",
                "/C",
                "/Q",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if restored.returncode != 0:
            raise AssertionError(restored.stderr)
    for directory, _, names in os.walk(physical):
        os.chmod(directory, 0o700)
        for name in names:
            os.chmod(Path(directory) / name, 0o600)
    shutil.rmtree(physical)


class EvaluationTests(unittest.TestCase):
    def invoke(
        self,
        corpus: Path,
        results: Path | None = RESULTS,
        identities: Path = IDENTITIES,
        *,
        claim_quality: bool = False,
        reviewer_profile: bool = False,
        lifecycle_state_root: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-B", str(EVALUATOR), "--corpus", str(corpus)]
        if results is not None:
            command.extend(("--results", str(results)))
        command.extend(("--git-identities", str(identities)))
        if reviewer_profile:
            command.extend(("--reviewer-profile", str(PROFILE)))
        if lifecycle_state_root is not None:
            command.extend(("--lifecycle-state-root", str(lifecycle_state_root)))
        if claim_quality:
            command.append("--claim-empirical-quality")
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def mutated(self, corpus_value: dict[str, object], results_value: dict[str, object], mutate) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus_path = root / "corpus.json"
            results_path = root / "results.json"
            changed_corpus = copy.deepcopy(corpus_value)
            changed_results = copy.deepcopy(results_value)
            mutate(changed_corpus, changed_results)
            manifest = [
                {"id": case["id"], "kind": case["kind"], "input": case["input"]}
                for case in changed_corpus["cases"]
            ]
            changed_results["corpus_sha256"] = hashlib.sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            corpus_path.write_text(json.dumps(changed_corpus), encoding="utf-8")
            results_path.write_text(json.dumps(changed_results), encoding="utf-8")
            shutil.copy2(SKILL / "references" / "review-lenses.md", root / "review-lenses.md")
            shutil.copytree(SKILL / "references" / "evaluation-inputs", root / "evaluation-inputs")
            return self.invoke(corpus_path, results_path)

    def test_curated_self_test_is_strict_authenticated_and_cover_corrected_non_cpp(self) -> None:
        """Re-embedding hand-authored candidates or omitting identity checks must fail."""
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        self.assertTrue(all("candidate_output" not in case for case in corpus["cases"]))
        self.assertTrue(any(case["kind"] == "corrected_non_cpp_control" for case in corpus["cases"]))

        result = self.invoke(CORPUS)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["results_kind"], "curated_evaluator_self_test")
        self.assertFalse(report["provenance_verified"])
        self.assertFalse(report["empirical_quality_claim_eligible"])
        self.assertEqual(report["required_category_recall"], 1.0)
        self.assertEqual(report["control_false_positive_rate"], 0.0)
        self.assertEqual(report["finding_quality_rate"], 1.0)
        self.assertGreaterEqual(report["authenticated_git_reviews"], 6)
        self.assertGreaterEqual(report["corrected_non_cpp_controls"], 1)
        self.assertIn("corrected_non_cpp_control", report["kinds"])
        self.assertIn("non_cpp", report["kinds"])
        self.assertIn("windhawk_cpp", report["kinds"])
        self.assertIn("empirical", report["note"].lower())
        self.assertIn("self-test", report["note"].lower())

    def test_results_are_required_as_a_separate_model_replay(self) -> None:
        result = self.invoke(CORPUS, results=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("results", (result.stdout + result.stderr).lower())

    def test_ground_truth_is_strict_id_free_and_one_to_one(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        ground_truth = next(
            case["ground_truth"]
            for case in corpus["cases"]
            if len(case["ground_truth"]["expectations"]) >= 2
        )

        with self.assertRaisesRegex(ValueError, "fields are not exact"):
            evaluation_module.validate_ground_truth({
                **ground_truth,
                "required_finding_ids": ["fixture-label-must-not-leak"],
            })

        duplicate_selector = copy.deepcopy(ground_truth)
        duplicate_selector["expectations"][1]["evidence_selector"] = copy.deepcopy(
            duplicate_selector["expectations"][0]["evidence_selector"]
        )
        with self.assertRaisesRegex(ValueError, "selectors must be distinct"):
            evaluation_module.validate_ground_truth(duplicate_selector)

        shallow_semantics = copy.deepcopy(ground_truth)
        shallow_semantics["expectations"][0]["claim_concepts"] = [["generic"]]
        with self.assertRaisesRegex(ValueError, "at least two defect concept groups"):
            evaluation_module.validate_ground_truth(shallow_semantics)

    def test_curated_self_test_cannot_claim_empirical_reviewer_quality(self) -> None:
        result = self.invoke(CORPUS, claim_quality=True)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report["empirical_quality_claim_eligible"])
        self.assertIn("provenance", " ".join(report["failures"]).lower())

    def test_missing_known_finding_fails_recall(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["ground_truth"]["required_categories"])
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            replay["output"]["findings"] = []

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(json.loads(result.stdout)["required_category_recall"], 1.0)

    def test_semantic_match_accepts_genuine_output_with_a_different_stable_id(self) -> None:
        """Ground truth labels must not require the model to invent fixture IDs."""
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["ground_truth"]["required_categories"])
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            replay["output"]["findings"][0]["id"] = "MODEL-FINDING-1"

        result = self.mutated(corpus, results, mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["required_category_recall"], 1.0)

    def test_category_recall_is_independent_and_aggregates_across_findings(self) -> None:
        """Four genuine category hits out of seven must score exactly 4/7."""
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if len(case["ground_truth"]["required_categories"]) == 7)
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            keep = {"concurrency_ownership", "lifecycle_cleanup", "performance_hot_paths", "repository_contracts"}
            selected = [
                copy.deepcopy(finding)
                for expectation, finding in zip(case["ground_truth"]["expectations"], replay["output"]["findings"])
                if expectation["category"] in keep
            ]
            for index, finding in enumerate(selected, 1):
                finding["id"] = f"MODEL-{index}"
            replay["output"]["findings"] = selected
            results_value["cases"] = [replay]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertAlmostEqual(report["required_category_recall"], 4 / 7)
        self.assertEqual(
            report["missing_categories"],
            {
                next(case["id"] for case in corpus["cases"] if len(case["ground_truth"]["required_categories"]) == 7): [
                    "author_verification",
                    "indirect_consumers",
                    "overlap_attribution",
                ]
            },
        )

    def test_keyword_salad_cannot_credit_unrelated_categories_or_quality(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if len(case["ground_truth"]["required_categories"]) == 7)
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            evidence = replay["output"]["findings"][0]["evidence"]
            salad = "thread race teardown cleanup caller consumer overlap attribution performance hot repository contract test verify command shell memory resource"
            replay["output"]["findings"] = [{
                "id": "GENERIC-SALAD",
                "severity": "high",
                "claim": salad,
                "evidence": evidence,
                "correction": f"Generic correction {salad}",
                "verification": f"Generic verification {salad}",
            }]
            results_value["cases"] = [replay]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["required_category_recall"], 0.0)
        self.assertEqual(report["finding_quality_rate"], 0.0)
        self.assertIn("defect concept", " ".join(report["failures"]).lower())

        def mutate_single_category(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if len(case["ground_truth"]["required_categories"]) == 1)
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            evidence = replay["output"]["findings"][0]["evidence"]
            salad = "artifact identity test verify thread race consumer downstream input command lifecycle cleanup memory resource overlap attribution performance hot path repository contract"
            replay["output"]["findings"] = [{
                "id": "SINGLE-CATEGORY-SALAD",
                "severity": "high",
                "claim": salad,
                "evidence": evidence,
                "correction": f"Generic correction {salad}",
                "verification": f"Generic verification {salad}",
            }]
            results_value["cases"] = [replay]

        single = self.mutated(corpus, results, mutate_single_category)
        self.assertNotEqual(single.returncode, 0)
        single_report = json.loads(single.stdout)
        self.assertEqual(single_report["required_category_recall"], 0.0)
        self.assertEqual(single_report["finding_quality_rate"], 0.0)
        self.assertIn("defect concept", " ".join(single_report["failures"]).lower())

    def test_one_vacuous_keyword_finding_per_category_gets_no_credit(self) -> None:
        """Splitting boilerplate must not evade the multi-category salad check."""
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
        boilerplate_tokens = {
            "artifact_identity": "artifact",
            "author_verification": "evidence",
            "concurrency_ownership": "race",
            "indirect_consumers": "consumer",
            "input_command_boundaries": "command",
            "lifecycle_cleanup": "cleanup",
            "memory_resource_safety": "memory",
            "overlap_attribution": "overlap",
            "performance_hot_paths": "performance",
            "repository_contracts": "policy",
        }

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if len(case["ground_truth"]["required_categories"]) == 7)
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            evidence = replay["output"]["findings"][0]["evidence"]
            replay["output"]["findings"] = [
                {
                    "id": f"BOILERPLATE-{index}",
                    "severity": "high",
                    "claim": f"The {boilerplate_tokens[category]} defect remains in the implementation.",
                    "evidence": evidence,
                    "correction": f"Resolve the {boilerplate_tokens[category]} defect with a concrete change.",
                    "verification": f"Exercise the {boilerplate_tokens[category]} defect path after the change.",
                }
                for index, category in enumerate(case["ground_truth"]["required_categories"])
            ]
            results_value["cases"] = [replay]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["required_category_recall"], 0.0)
        self.assertEqual(report["finding_quality_rate"], 0.0)
        self.assertIn("defect concept", " ".join(report["failures"]).lower())

    def test_immutable_evidence_accepts_only_strict_code_selectors(self) -> None:
        evidence = [{
            "kind": "bundle",
            "uri": f"bundle://{'a' * 64}/src/example.py",
            "sha256": "b" * 64,
            "selector": {"kind": "symbol", "value": "Example::run"},
        }]
        self.assertEqual(review_contracts.validate_external_evidence(evidence), evidence)
        for selector in (
            {"kind": "symbol", "value": ""},
            {"kind": "line_range", "start": 9, "end": 4},
            {"kind": "symbol", "value": "Example::run", "extra": True},
        ):
            invalid = copy.deepcopy(evidence)
            invalid[0]["selector"] = selector
            with self.assertRaises(ValueError):
                review_contracts.validate_external_evidence(invalid)

    def test_bundle_failures_leave_no_digest_path_and_allow_clean_retry(self) -> None:
        content = {"nested/evidence.txt": b"sensitive evidence\n"}
        digest = review_contracts.compute_packet_sha256({
            name: hashlib.sha256(data).hexdigest()
            for name, data in content.items()
        })
        failure_points = (
            "_prepare_staging_root",
            "_finalize_staging_permissions",
            "_verify_staged_bundle",
        )
        if os.name == "nt":
            failure_points += ("_current_windows_user_sid",)
        for failure_point in failure_points:
            with self.subTest(failure_point=failure_point), tempfile.TemporaryDirectory() as temporary:
                store = review_contracts.BundleStore(Path(temporary) / "bundles")
                store.root.mkdir()
                sentinel = store.root / "unrelated.txt"
                sentinel.write_bytes(b"preserve me")
                final = store.root / digest

                def fail_before_publication(*_args, **_kwargs):
                    self.assertFalse(final.exists())
                    if failure_point == "_prepare_staging_root":
                        self.assertEqual(list(Path(_args[0]).iterdir()), [])
                    elif failure_point in {"_finalize_staging_permissions", "_verify_staged_bundle"}:
                        self.assertTrue(any(Path(_args[0]).iterdir()))
                    raise RuntimeError(f"{failure_point} failed")

                try:
                    with mock.patch.object(
                        review_contracts,
                        failure_point,
                        create=True,
                        side_effect=fail_before_publication,
                    ):
                        with self.assertRaisesRegex(RuntimeError, "failed"):
                            review_contracts.build_bundle(store, content)
                    self.assertFalse(final.exists())
                    self.assertEqual(
                        {path.name for path in store.root.iterdir()},
                        {sentinel.name},
                    )

                    retry = review_contracts.build_bundle(store, content)
                    self.assertEqual(retry["bundle_sha256"], digest)
                    self.assertEqual(store.read(digest, "nested/evidence.txt"), content["nested/evidence.txt"])
                finally:
                    if final.exists():
                        remove_hardened_tree(final)

    def test_bundle_publication_failure_preserves_only_unrelated_store_entries(self) -> None:
        content = {"review.json": b"{}\n"}
        digest = review_contracts.compute_packet_sha256({
            "review.json": hashlib.sha256(content["review.json"]).hexdigest(),
        })
        with tempfile.TemporaryDirectory() as temporary:
            store = review_contracts.BundleStore(Path(temporary) / "bundles")
            store.root.mkdir()
            sentinel = store.root / "unrelated.txt"
            sentinel.write_bytes(b"preserve me")
            final = store.root / digest

            def fail_publication(staged, destination):
                self.assertEqual(Path(destination), final)
                self.assertFalse(final.exists())
                review_contracts._verify_bundle_permissions(Path(staged))
                raise OSError("publication failed")

            try:
                with mock.patch.object(
                    review_contracts.os,
                    "replace",
                    side_effect=fail_publication,
                ):
                    with self.assertRaisesRegex(OSError, "publication failed"):
                        review_contracts.build_bundle(store, content)
                self.assertFalse(final.exists())
                self.assertEqual(
                    {path.name for path in store.root.iterdir()},
                    {sentinel.name},
                )

                retry = review_contracts.build_bundle(store, content)
                self.assertEqual(retry["bundle_sha256"], digest)
            finally:
                if final.exists():
                    remove_hardened_tree(final)

    def test_bundle_permissions_are_verified_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = review_contracts.BundleStore(Path(temporary) / "bundles")
            bundle = review_contracts.build_bundle(
                store,
                {"nested/deep/evidence.txt": b"private\n"},
            )
            final = store.root / bundle["bundle_sha256"]
            leaf = final / "nested" / "deep" / "evidence.txt"
            try:
                review_contracts._verify_bundle_permissions(final)
                if os.name == "nt":
                    inherited = subprocess.run(
                        ["icacls", str(leaf), "/grant", "*S-1-5-11:(R)", "/Q"],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(inherited.returncode, 0, inherited.stderr)
                else:
                    leaf.chmod(0o644)
                with self.assertRaisesRegex(RuntimeError, "permission|ACL"):
                    review_contracts._verify_bundle_permissions(final)
            finally:
                if final.exists():
                    remove_hardened_tree(final)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell module resolution only")
    def test_bundle_acl_verifier_ignores_inherited_powershell_core_module_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shadow = root / "modules" / "Microsoft.PowerShell.Security"
            shadow.mkdir(parents=True)
            (shadow / "Microsoft.PowerShell.Security.psd1").write_text(
                "@{ RootModule = 'Microsoft.PowerShell.Security.psm1'; "
                "ModuleVersion = '99.0.0'; GUID = '11111111-1111-1111-1111-111111111111'; "
                "FunctionsToExport = @('Get-Acl') }\n",
                encoding="utf-8",
            )
            (shadow / "Microsoft.PowerShell.Security.psm1").write_text(
                "throw 'incompatible PowerShell Core security module'\n",
                encoding="utf-8",
            )
            store = review_contracts.BundleStore(root / "bundles")
            original_module_path = os.environ.get("PSModulePath", "")
            polluted_module_path = os.pathsep.join(
                part for part in (str(root / "modules"), original_module_path) if part
            )
            final: Path | None = None
            try:
                with mock.patch.dict(os.environ, {"PSModulePath": polluted_module_path}):
                    try:
                        bundle = review_contracts.build_bundle(
                            store,
                            {"evidence.txt": b"private\n"},
                        )
                    except RuntimeError as exc:
                        self.fail(f"ACL verification inherited PSModulePath: {exc}")
                final = store.root / bundle["bundle_sha256"]
                self.assertEqual(store.read(bundle["bundle_sha256"], "evidence.txt"), b"private\n")
            finally:
                if final is not None and final.exists():
                    remove_hardened_tree(final)

    def test_review_output_uses_one_exact_pinned_git_finding_shape(self) -> None:
        generic_reference = {
            "kind": "git_commit",
            "repository": "https://example.com/acme/review-fixture.git",
            "commit": "a" * 40,
            "path": "src/review.py",
        }
        self.assertEqual(
            review_contracts.validate_external_evidence([generic_reference]),
            [generic_reference],
        )
        evidence = {
            **generic_reference,
            "sha256": "b" * 64,
            "selector": {"kind": "line_range", "start": 1, "end": 1},
        }
        output = {
            "schema_version": 1,
            "attempt_id": "attempt-1",
            "packet_sha256": "c" * 64,
            "bundle_sha256": "d" * 64,
            "snapshot_sha256": "e" * 64,
            "verdict": "fail",
            "coverage": [],
            "residual_risks": [],
            "findings": [{
                "id": "ACR-TEST",
                "severity": "high",
                "claim": "Pinned Git evidence must bind exact bytes.",
                "evidence": [evidence],
                "correction": "Use the exact finding evidence contract.",
                "verification": "Resolve and hash the pinned blob.",
            }],
        }
        self.assertEqual(review_contracts.validate_review_output(output), output)

        invalid_evidence = {
            "missing digest": {key: value for key, value in evidence.items() if key != "sha256"},
            "malformed digest": {**evidence, "sha256": "B" * 64},
            "malformed authority": {**evidence, "repository": "https://example.com/"},
            "credential authority": {**evidence, "repository": "https://user@example.com/acme/review.git"},
            "abbreviated commit": {**evidence, "commit": "a" * 12},
            "unsafe path": {**evidence, "path": "../review.py"},
            "missing selector": {key: value for key, value in evidence.items() if key != "selector"},
            "malformed selector": {**evidence, "selector": {"kind": "line_range", "start": 2, "end": 1}},
        }
        for label, invalid in invalid_evidence.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(output)
                changed["findings"][0]["evidence"] = [invalid]
                with self.assertRaises(ValueError):
                    review_contracts.validate_review_output(changed)

    def test_pinned_git_finding_shape_resolves_exact_authority_commit_path_digest_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repo"
            repository.mkdir()
            remote = "https://example.com/acme/review-fixture.git"
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repository, check=True)
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repository, check=True)
            subprocess.run(["git", "remote", "add", "origin", remote], cwd=repository, check=True)
            source = b"exact_evidence_symbol\n"
            (repository / "evidence.py").write_bytes(source)
            subprocess.run(["git", "add", "evidence.py"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repository, check=True)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            store = review_contracts.BundleStore(root / "bundles")
            bundle = review_contracts.build_bundle(store, {"anchor.txt": b"anchor\n"})
            final = store.root / bundle["bundle_sha256"]
            evidence = {
                "kind": "git_commit",
                "repository": remote,
                "commit": commit,
                "path": "evidence.py",
                "sha256": hashlib.sha256(source).hexdigest(),
                "selector": {"kind": "symbol", "value": "exact_evidence_symbol"},
            }
            finding = {"id": "PINNED-GIT", "evidence": [evidence]}
            resolver = review_contracts.build_local_git_resolver(repository)
            try:
                self.assertEqual(
                    review_contracts.validate_finding_evidence(
                        [finding],
                        store=store,
                        active_bundle_sha256=bundle["bundle_sha256"],
                        git_resolver=resolver,
                    ),
                    [finding],
                )
                invalid_evidence = {
                    "authority": {**evidence, "repository": "https://example.com/acme/other.git"},
                    "commit": {**evidence, "commit": "f" * 40},
                    "path": {**evidence, "path": "missing.py"},
                    "digest": {**evidence, "sha256": "0" * 64},
                    "selector": {**evidence, "selector": {"kind": "symbol", "value": "missing_symbol"}},
                }
                for label, invalid in invalid_evidence.items():
                    with self.subTest(label=label), self.assertRaises(ValueError):
                        review_contracts.validate_finding_evidence(
                            [{"id": "PINNED-GIT", "evidence": [invalid]}],
                            store=store,
                            active_bundle_sha256=bundle["bundle_sha256"],
                            git_resolver=resolver,
                        )
            finally:
                if final.exists():
                    remove_hardened_tree(final)

    def test_pinned_git_resolver_rejects_non_regular_tree_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()
            remote = "https://example.com/acme/tree-entry-fixture.git"
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repository, check=True)
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repository, check=True)
            subprocess.run(["git", "remote", "add", "origin", remote], cwd=repository, check=True)
            source = b"print('regular blob')\n"
            (repository / "target.py").write_bytes(source)
            (repository / "nested").mkdir()
            (repository / "nested" / "code.py").write_bytes(b"nested_code = True\n")
            subprocess.run(["git", "add", "target.py", "nested/code.py"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repository, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            link_blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                cwd=repository,
                input=b"target.py",
                capture_output=True,
                check=True,
            ).stdout.decode("ascii").strip()
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"120000,{link_blob},link.py"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"160000,{base},dependency"],
                cwd=repository,
                check=True,
            )
            subprocess.run(["git", "update-index", "--chmod=+x", "target.py"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "tree entry modes"], cwd=repository, check=True)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            resolver = review_contracts.build_local_git_resolver(repository)

            self.assertEqual(resolver(remote, commit, "target.py"), source)
            self.assertEqual(
                resolver(remote, commit, "nested/code.py"),
                b"nested_code = True\n",
            )
            for path in ("link.py", "dependency", "nested"):
                with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError,
                    "regular Git blob",
                ):
                    resolver(remote, commit, path)

    def test_evaluator_replay_binds_git_finding_to_case_source_digest(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
        cases_by_id = {case["id"]: case for case in corpus["cases"]}
        git_results = [
            case for case in results["cases"]
            if cases_by_id[case["id"]]["input"]["kind"] == "git_review"
            and case["output"]["findings"]
        ]
        self.assertTrue(git_results)
        for case in git_results:
            expected = cases_by_id[case["id"]]["input"]["source_sha256"]
            for finding in case["output"]["findings"]:
                for evidence in finding["evidence"]:
                    if evidence["kind"] == "git_commit":
                        self.assertEqual(evidence["sha256"], expected)

        def remove_digest(_corpus, changed_results):
            case = next(
                item for item in changed_results["cases"]
                if cases_by_id[item["id"]]["input"]["kind"] == "git_review"
                and item["output"]["findings"]
            )
            del case["output"]["findings"][0]["evidence"][0]["sha256"]

        missing = self.mutated(corpus, results, remove_digest)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("evidence", (missing.stdout + missing.stderr).casefold())

        def replace_digest(_corpus, changed_results):
            case = next(
                item for item in changed_results["cases"]
                if cases_by_id[item["id"]]["input"]["kind"] == "git_review"
                and item["output"]["findings"]
            )
            case["output"]["findings"][0]["evidence"][0]["sha256"] = "0" * 64

        wrong = self.mutated(corpus, results, replace_digest)
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("immutable case artifact", (wrong.stdout + wrong.stderr).casefold())

    def test_category_finding_requires_immutable_case_artifact_evidence(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["input"]["kind"] == "local_fixture" and case["ground_truth"]["required_categories"])
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            replay["output"]["findings"][0]["evidence"][0]["sha256"] = "f" * 64
            results_value["cases"] = [replay]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["required_category_recall"], 0.0)
        self.assertIn("case artifact", " ".join(report["failures"]).lower())

    def test_selector_must_exist_in_the_frozen_case_bytes(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["input"]["kind"] == "local_fixture" and case["ground_truth"]["expectations"])
            corpus_value["cases"] = [case]
            replay = next(item for item in results_value["cases"] if item["id"] == case["id"])
            missing = {"kind": "symbol", "value": "DefinitelyMissingSymbol"}
            case["ground_truth"]["expectations"][0]["evidence_selector"] = missing
            replay["output"]["findings"][0]["evidence"][0]["selector"] = missing
            results_value["cases"] = [replay]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["required_category_recall"], 0.0)
        self.assertIn("not present", " ".join(report["failures"]).lower())

    def test_invented_control_finding_fails_false_positive_gate(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def mutate(corpus_value, results_value):
            control = next(case for case in corpus_value["cases"] if "control" in case["kind"])
            source = next(item for item in results_value["cases"] if item["output"]["findings"])
            replay = next(item for item in results_value["cases"] if item["id"] == control["id"])
            replay["output"]["verdict"] = "fail"
            replay["output"]["findings"] = [copy.deepcopy(source["output"]["findings"][0])]

        result = self.mutated(corpus, results, mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertGreater(json.loads(result.stdout)["control_false_positive_rate"], 0.0)

    def test_invalid_evidence_and_missing_mandatory_lens_fail(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def invalid_evidence(corpus_value, results_value):
            case = next(item for item in results_value["cases"] if item["output"]["findings"])
            case["output"]["findings"][0]["evidence"] = ["mutable string"]

        self.assertNotEqual(self.mutated(corpus, results, invalid_evidence).returncode, 0)

        def missing_lens(corpus_value, results_value):
            results_value["cases"][0]["output"]["coverage"].pop()

        result = self.mutated(corpus, results, missing_lens)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lens", (result.stdout + result.stderr).lower())

    def test_immutable_local_fixture_and_git_comment_digests_are_authenticated(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))

        def local_digest(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["input"]["kind"] == "local_fixture")
            case["input"]["sha256"] = "0" * 64

        local = self.mutated(corpus, results, local_digest)
        self.assertNotEqual(local.returncode, 0)
        self.assertIn("digest", (local.stdout + local.stderr).lower())

        def comment_digest(corpus_value, results_value):
            case = next(case for case in corpus_value["cases"] if case["input"]["kind"] == "git_review")
            case["input"]["review_comment_sha256"] = "0" * 64

        comment = self.mutated(corpus, results, comment_digest)
        self.assertNotEqual(comment.returncode, 0)
        self.assertIn("identity", (comment.stdout + comment.stderr).lower())

    def test_corrected_python_control_preserves_revision_behavior_and_metacharacters_are_inert(self) -> None:
        namespace = runpy.run_path(str(CORRECTED_PYTHON))
        inspect_revision = namespace["inspect_revision"]
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
            (repo / "file.txt").write_text("content\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True
            ).stdout.strip()
            self.assertEqual(inspect_revision("HEAD", repo).strip(), head)
            marker = repo / "owned.txt"
            with self.assertRaises(ValueError):
                inspect_revision("HEAD;echo-owned>owned.txt", repo)
            self.assertFalse(marker.exists())

    def test_provenance_replay_rejects_wrong_profile_and_standalone_receipts(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        self_test = json.loads(RESULTS.read_text(encoding="utf-8"))

        def replay_record(agent_type: str, *, nonplaceholder: bool = False) -> dict[str, object]:
            cases_by_id = {case["id"]: case for case in corpus["cases"]}
            cases = []
            for item in self_test["cases"]:
                case = cases_by_id[item["id"]]
                output = copy.deepcopy(item["output"])
                if nonplaceholder:
                    output["attempt_id"] = f"replay-{hashlib.sha256(item['id'].encode()).hexdigest()[:16]}"
                    for field in ("packet_sha256", "bundle_sha256", "snapshot_sha256"):
                        output[field] = hashlib.sha256(f"{item['id']}:{field}".encode()).hexdigest()
                output_sha256 = hashlib.sha256(
                    json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                profile_sha256 = hashlib.sha256(PROFILE.read_bytes()).hexdigest()
                cases.append(
                    {
                        "id": item["id"],
                        "input_sha256": item["input_sha256"],
                        "case_sha256": hashlib.sha256(
                            json.dumps(
                                {"id": case["id"], "kind": case["kind"], "input": case["input"]},
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "bundle_sha256": output["bundle_sha256"],
                        "output_sha256": output_sha256,
                        "receipt": {
                            "schema_version": 1,
                            "session_id": "test-session",
                            "task_id": item["id"],
                            "delivery_id": f"delivery-{item['id']}",
                            "generation": 0,
                            "reviewer_agent": "test-reviewer-agent",
                            "reviewer_type": "sol_reviewer",
                            "reviewer_model": "gpt-5.6-sol",
                            "config_sha256": profile_sha256,
                            "attempt_id": output["attempt_id"],
                            "packet_sha256": output["packet_sha256"],
                            "bundle_sha256": output["bundle_sha256"],
                            "snapshot_sha256": output["snapshot_sha256"],
                            "output_sha256": output_sha256,
                            "disposition_sha256": hashlib.sha256(item["id"].encode()).hexdigest(),
                            "mutation_epoch": 0,
                        },
                        "output": output,
                    }
                )
            return {
                "schema_version": 1,
                "results_kind": "sol_reviewer_replay",
                "corpus_id": self_test["corpus_id"],
                "corpus_sha256": self_test["corpus_sha256"],
                "replay_id": "test-only-schema-replay",
                "reviewer": {
                    "agent_type": agent_type,
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "max",
                    "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
                },
                "cases": cases,
            }

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.json"
            wrong = replay_record("luna_worker")
            path.write_text(json.dumps(wrong), encoding="utf-8")
            result = self.invoke(CORPUS, path, reviewer_profile=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reviewer", (result.stdout + result.stderr).lower())

            placeholder = replay_record("sol_reviewer")
            path.write_text(json.dumps(placeholder), encoding="utf-8")
            result = self.invoke(CORPUS, path, reviewer_profile=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lifecycle export", (result.stdout + result.stderr).lower())

            modified = replay_record("sol_reviewer", nonplaceholder=True)
            modified["cases"][0]["output"]["coverage"][0] += " changed after capture"
            path.write_text(json.dumps(modified), encoding="utf-8")
            result = self.invoke(CORPUS, path, reviewer_profile=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lifecycle export", (result.stdout + result.stderr).lower())

            standalone = replay_record("sol_reviewer", nonplaceholder=True)
            path.write_text(json.dumps(standalone), encoding="utf-8")
            result = self.invoke(CORPUS, path, reviewer_profile=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lifecycle export", (result.stdout + result.stderr).lower())

    def test_real_lifecycle_export_is_accepted_as_replay_authority(self) -> None:
        helper = hook_helpers.LifecycleGateTests(methodName="run")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = helper.make_fixture(temporary)
            long_state_top: Path | None = None
            if os.name == "nt":
                long_state_top = root / ("state-a-" + "a" * 110) / ("state-b-" + "b" * 110)
                state_root = long_state_top / "state"
                hook_helpers.lifecycle_gate._filesystem_path(state_root).mkdir(parents=True)
                self.assertGreater(len(str(state_root)), 260)
            if os.name == "nt":
                cli_result = self.invoke(CORPUS, lifecycle_state_root=state_root)
                if cli_result.returncode != 0:
                    shutil.rmtree(hook_helpers.lifecycle_gate._filesystem_path(long_state_top))
                self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
            helper.empty_receipt(root, state_root, profile, workspace)
            exported = hook_helpers.run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
            )
            case_input = {
                "kind": "local_fixture",
                "path": "owned.txt",
                "sha256": hashlib.sha256((workspace / "owned.txt").read_bytes()).hexdigest(),
                "version": 1,
            }
            cases = [{"id": "real-gate-case", "kind": "corrected_non_cpp_control", "input": case_input}]
            case_sha = hashlib.sha256(
                json.dumps(cases[0], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            replay = {
                "schema_version": 1,
                "results_kind": "sol_reviewer_replay",
                "corpus_id": "real-gate-export-test",
                "corpus_sha256": evaluation_module.input_manifest_sha(cases),
                "replay_id": "real-gate-export-test-v1",
                "reviewer": {
                    "agent_type": "sol_reviewer",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "max",
                    "profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest(),
                },
                "cases": [{
                    "id": "real-gate-case",
                    "input_sha256": hashlib.sha256(
                        json.dumps(case_input, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "case_sha256": case_sha,
                    "lifecycle_export": exported,
                }],
            }
            loaded, kind, provenance = evaluation_module.load_results(
                replay,
                "real-gate-export-test",
                cases,
                profile,
                state_root,
            )
            self.assertEqual(kind, "sol_reviewer_replay")
            self.assertTrue(provenance)
            self.assertEqual(loaded["real-gate-case"]["output"], exported["review_output"])

            current_state = state_root.joinpath(*PurePosixPath(exported["state_relative_path"]).parts)
            legacy_relative = (
                PurePosixPath("deliveries")
                / hashlib.sha256(exported["session_id"].encode()).hexdigest()
                / hashlib.sha256(exported["task_id"].encode()).hexdigest()
                / hashlib.sha256(exported["delivery_id"].encode()).hexdigest()
                / f"generation-{exported['generation']}.json"
            )
            legacy_state = state_root.joinpath(*legacy_relative.parts)
            hook_helpers.lifecycle_gate.save(
                legacy_state,
                json.loads(
                    hook_helpers.lifecycle_gate._filesystem_path(current_state).read_text(
                        encoding="utf-8"
                    )
                ),
            )
            pointer_path = (
                state_root
                / "active"
                / hashlib.sha256(exported["session_id"].encode()).hexdigest()
                / f"{hashlib.sha256(exported['turn_id'].encode()).hexdigest()}.json"
            )
            pointer_physical = hook_helpers.lifecycle_gate._filesystem_path(pointer_path)
            pointer = json.loads(pointer_physical.read_text(encoding="utf-8"))
            pointer["state"] = legacy_relative.as_posix()
            pointer_physical.write_text(json.dumps(pointer), encoding="utf-8")
            legacy_replay = copy.deepcopy(replay)
            legacy_replay["cases"][0]["lifecycle_export"]["state_relative_path"] = legacy_relative.as_posix()

            legacy_loaded, legacy_kind, legacy_provenance = evaluation_module.load_results(
                legacy_replay,
                "real-gate-export-test",
                cases,
                profile,
                state_root,
            )
            self.assertEqual(legacy_kind, "sol_reviewer_replay")
            self.assertTrue(legacy_provenance)
            self.assertEqual(legacy_loaded["real-gate-case"]["output"], exported["review_output"])

            pointer["state"] = exported["state_relative_path"]
            pointer_physical.write_text(json.dumps(pointer), encoding="utf-8")
            migrated_loaded, _, migrated_provenance = evaluation_module.load_results(
                legacy_replay,
                "real-gate-export-test",
                cases,
                profile,
                state_root,
            )
            self.assertTrue(migrated_provenance)
            self.assertEqual(migrated_loaded["real-gate-case"]["output"], exported["review_output"])

            tampered_output = copy.deepcopy(replay)
            tampered_output["cases"][0]["lifecycle_export"]["review_output"]["coverage"][0] += " tampered"
            with self.assertRaisesRegex(ValueError, "output"):
                evaluation_module.load_results(
                    tampered_output,
                    "real-gate-export-test",
                    cases,
                    profile,
                    state_root,
                )

            tampered_state = copy.deepcopy(replay)
            tampered_state["cases"][0]["lifecycle_export"]["state_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "state digest"):
                evaluation_module.load_results(
                    tampered_state,
                    "real-gate-export-test",
                    cases,
                    profile,
                    state_root,
                )
            cleanup_root = long_state_top or state_root / "deliveries"
            remove_hardened_tree(cleanup_root)

    def test_evaluator_replay_revalidates_persisted_blocking_counterevidence(self) -> None:
        helper = hook_helpers.LifecycleGateTests(methodName="run")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = helper.make_fixture(temporary)
            try:
                _, evidence = helper.blocking_review(state_root, profile, workspace)
                ledger = helper.rejection_ledger(evidence)
                state = helper.disposition(root, state_root, profile, ledger)
                exported = hook_helpers.run_cli(
                    self,
                    state_root,
                    profile,
                    "export-replay",
                    "--session-id",
                    "session",
                    "--turn-id",
                    "turn",
                )

                case_input = {
                    "kind": "local_fixture",
                    "path": "owned.txt",
                    "sha256": hashlib.sha256((workspace / "owned.txt").read_bytes()).hexdigest(),
                    "version": 1,
                }
                cases = [{"id": "counterevidence-case", "kind": "corrected_non_cpp_control", "input": case_input}]
                replay = {
                    "schema_version": 1,
                    "results_kind": "sol_reviewer_replay",
                    "corpus_id": "counterevidence-replay-test",
                    "corpus_sha256": evaluation_module.input_manifest_sha(cases),
                    "replay_id": "counterevidence-replay-test-v1",
                    "reviewer": {
                        "agent_type": "sol_reviewer",
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "max",
                        "profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest(),
                    },
                    "cases": [{
                        "id": "counterevidence-case",
                        "input_sha256": hashlib.sha256(
                            json.dumps(case_input, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                        "case_sha256": hashlib.sha256(
                            json.dumps(cases[0], sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                        "lifecycle_export": exported,
                    }],
                }

                tampered_ledger = copy.deepcopy(ledger)
                tampered_ledger["dispositions"][0]["primary_counterevidence"] = [{
                    "kind": "digest",
                    "uri": "https://example.com/source.txt",
                    "authority": {"kind": "archive", "source": "https://example.com/archive"},
                    "sha256": "d" * 64,
                }]
                disposition_sha = hashlib.sha256(
                    hook_helpers.lifecycle_gate.canonical_bytes(tampered_ledger)
                ).hexdigest()
                state["ledger"] = tampered_ledger
                state["dispositions"] = disposition_sha
                state["receipt"]["disposition_sha256"] = disposition_sha
                hook_helpers.lifecycle_gate.save_active(state_root, state)
                state_path = state_root.joinpath(
                    *PurePosixPath(exported["state_relative_path"]).parts
                )
                state_raw = hook_helpers.lifecycle_gate._filesystem_path(state_path).read_bytes()
                exported["state_sha256"] = hashlib.sha256(state_raw).hexdigest()
                exported["receipt"] = copy.deepcopy(state["receipt"])

                with self.assertRaisesRegex(ValueError, "counterevidence"):
                    evaluation_module.load_results(
                        replay,
                        "counterevidence-replay-test",
                        cases,
                        profile,
                        state_root,
                    )
            finally:
                if hook_helpers.lifecycle_gate._filesystem_path(state_root).exists():
                    remove_hardened_tree(state_root)


if __name__ == "__main__":
    unittest.main()
