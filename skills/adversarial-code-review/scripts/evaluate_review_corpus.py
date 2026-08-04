"""Score external strict review outputs against authenticated immutable cases.

This deterministic regression harness is not proof of model quality. It stores
no review-comment bodies; the trusted identity file contains only primary-source
identities and digests established when the fixture is refreshed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from review_contracts import (  # noqa: E402
    BundleStore,
    MANDATORY_REVIEW_LENSES,
    build_local_git_resolver,
    canonical_bytes,
    compute_packet_sha256,
    delivery_address_sha256,
    validate_evidence_selector,
    validate_lens_coverage,
    validate_disposition_ledger,
    validate_review_output,
    validate_review_receipt,
)


HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SUPPORTED_CATEGORIES = {
    "artifact_identity",
    "author_verification",
    "concurrency_ownership",
    "indirect_consumers",
    "input_command_boundaries",
    "lifecycle_cleanup",
    "memory_resource_safety",
    "overlap_attribution",
    "performance_hot_paths",
    "repository_contracts",
}

EXPORT_FIELDS = {
    "schema_version", "authority", "session_id", "turn_id", "task_id",
    "delivery_id", "generation", "state_relative_path", "state_sha256",
    "bundle_sha256", "bundle_manifest_sha256", "profile_sha256",
    "output_sha256", "review_output", "receipt",
}
STATE_FIELDS = {
    "schema_version", "session_id", "turn_id", "delivery_id", "classification",
    "exempt_reason", "status", "task_id", "paths_sha256", "generation",
    "mutation_epoch", "seen_tool_use_ids", "inflight_tool_use_ids",
    "snapshot_sha256", "bundle_sha256", "lens_sha256", "packet_sha256",
    "frozen_epoch", "workspace_sha256", "profile_sha256", "attempt_id",
    "reviewer_agent", "consumed_attempt_ids", "review_output", "output_sha256",
    "pending_disposition_sha256", "dispositions", "ledger", "receipt",
    "blocked_evidence_sha256", "blocked_origin", "stale_reason",
}
CONTRACT_FIELDS = {
    "schema_version", "delivery_id", "task_id", "generation", "mutation_epoch",
    "attempt_id", "paths_sha256", "snapshot_sha256", "profile_sha256",
    "lens_sha256", "mandatory_lenses", "verification_sha256",
    "production_manifest_sha256",
}
PACKET_FIELDS = {
    "schema_version", "contract_sha256", "snapshot_sha256", "generation",
    "mutation_epoch", "attempt_id", "evidence", "lens_sha256",
    "mandatory_lenses", "verification_sha256", "production_manifest_sha256",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def strict(record: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping) or set(record) != fields:
        fail(f"{label} fields are not exact")
    return dict(record)


def safe_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str):
        fail("fixture path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts:
        fail("fixture path is unsafe")
    return path


def load_git_identities(path: Path) -> dict[str, dict[str, Any]]:
    root = strict(
        json.loads(path.read_text(encoding="utf-8")),
        {"schema_version", "authority", "identities"},
        "Git identity authority",
    )
    if root["schema_version"] != 1 or root["authority"] != "github-primary-evidence-pins-v1":
        fail("Git identity authority is unsupported")
    if not isinstance(root["identities"], list):
        fail("Git identities must be a list")
    result: dict[str, dict[str, Any]] = {}
    fields = {
        "case_id", "kind", "repository", "commit", "path", "source_blob_sha1",
        "source_sha256", "review_comment_url", "review_comment_sha256",
    }
    for raw in root["identities"]:
        identity = strict(raw, fields, "Git identity")
        case_id = identity["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in result:
            fail("Git identity case ID is missing or duplicated")
        if identity["kind"] != "git_review":
            fail("Git identity kind is invalid")
        if HEX40.fullmatch(str(identity["commit"])) is None or HEX40.fullmatch(str(identity["source_blob_sha1"])) is None:
            fail("Git commit or blob identity is malformed")
        if HEX64.fullmatch(str(identity["source_sha256"])) is None or HEX64.fullmatch(str(identity["review_comment_sha256"])) is None:
            fail("Git identity digest is malformed")
        result[case_id] = identity
    return result


def validate_input(record: Any, corpus_dir: Path, case_id: str, identities: Mapping[str, Mapping[str, Any]]) -> bool:
    if not isinstance(record, Mapping):
        fail("input must be a record")
    kind = record.get("kind")
    if kind == "git_review":
        value = strict(
            record,
            {
                "kind", "repository", "commit", "path", "source_blob_sha1",
                "source_sha256", "review_comment_url", "review_comment_sha256",
            },
            "Git review input",
        )
        parsed_repository = urlsplit(str(value["repository"]))
        parsed_comment = urlsplit(str(value["review_comment_url"]))
        if parsed_repository.scheme != "https" or parsed_repository.netloc != "github.com" or not parsed_repository.path.strip("/"):
            fail("Git review repository is not authoritative")
        if parsed_comment.scheme != "https" or parsed_comment.netloc != "github.com" or "issuecomment-" not in parsed_comment.fragment:
            fail("review comment URL is not immutable")
        if HEX40.fullmatch(str(value["commit"])) is None or HEX40.fullmatch(str(value["source_blob_sha1"])) is None:
            fail("Git review commit/blob identity is malformed")
        if HEX64.fullmatch(str(value["source_sha256"])) is None or HEX64.fullmatch(str(value["review_comment_sha256"])) is None:
            fail("Git review identity digest is malformed")
        safe_relative(value["path"])
        expected = identities.get(case_id)
        if expected != {"case_id": case_id, **value}:
            fail(f"Git review identity authentication failed: {case_id}")
        return True
    if kind == "local_fixture":
        value = strict(record, {"kind", "path", "sha256", "version"}, "local fixture input")
        if value["version"] != 1 or HEX64.fullmatch(str(value["sha256"])) is None:
            fail("local fixture version or digest is invalid")
        relative = safe_relative(value["path"])
        target = corpus_dir.joinpath(*relative.parts).resolve(strict=True)
        root = corpus_dir.resolve(strict=True)
        if root not in target.parents or sha(target.read_bytes()) != value["sha256"]:
            fail("local fixture digest mismatch")
        return False
    fail("unsupported immutable input kind")


def validate_ground_truth(record: Any) -> dict[str, Any]:
    value = strict(
        record,
        {"allow_findings", "required_categories", "expectations"},
        "ground truth",
    )
    if not isinstance(value["allow_findings"], bool):
        fail("ground-truth allow_findings must be boolean")
    required = value["required_categories"]
    expectations = value["expectations"]
    if not isinstance(required, list) or not isinstance(expectations, list):
        fail("ground-truth category and expectation lists are required")
    if len(required) != len(set(required)) or not all(
        isinstance(category, str) and category in SUPPORTED_CATEGORIES for category in required
    ):
        fail("ground-truth required categories are duplicated or unsupported")
    normalized: list[dict[str, Any]] = []
    selectors: set[bytes] = set()
    for raw in expectations:
        expectation = strict(
            raw,
            {
                "category", "evidence_selector", "claim_concepts",
                "correction_concepts", "verification_concepts",
            },
            "ground-truth defect expectation",
        )
        if expectation["category"] not in required:
            fail("ground-truth expectation category is not required")
        selector = validate_evidence_selector(expectation["evidence_selector"])
        selector_identity = canonical_bytes(selector)
        if selector_identity in selectors:
            fail("ground-truth evidence selectors must be distinct within a case")
        selectors.add(selector_identity)
        for field in ("claim_concepts", "correction_concepts", "verification_concepts"):
            groups = expectation[field]
            if not isinstance(groups, list) or len(groups) < 2:
                fail(f"ground-truth {field} requires at least two defect concept groups")
            for group in groups:
                if (
                    not isinstance(group, list)
                    or not group
                    or not all(isinstance(term, str) and len(term.strip()) >= 2 for term in group)
                ):
                    fail(f"ground-truth {field} concept group is malformed")
        normalized.append({**expectation, "evidence_selector": selector})
    categories = [expectation["category"] for expectation in normalized]
    if len(categories) != len(set(categories)) or set(categories) != set(required):
        fail("ground-truth requires exactly one defect expectation per category")
    if not value["allow_findings"] and (required or normalized):
        fail("control case cannot require findings")
    if value["allow_findings"] and not normalized:
        fail("finding case requires grounded defect expectations")
    return {**value, "expectations": normalized}


def input_manifest_sha(cases: list[Mapping[str, Any]]) -> str:
    manifest = [{"id": case["id"], "kind": case["kind"], "input": case["input"]} for case in cases]
    return sha(canonical_bytes(manifest))


def _placeholder(value: str) -> bool:
    return len(set(value)) == 1


def _text_digest(value: str) -> str:
    return sha(value.encode("utf-8"))


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail(f"{label} must be a non-negative integer")
    return value


def _filesystem_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    absolute = os.path.abspath(value)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def _path_under(root: Path, relative_value: Any, label: str) -> Path:
    relative = safe_relative(relative_value)
    try:
        resolved_root = _filesystem_path(root).resolve(strict=True)
        lexical = resolved_root
        for part in relative.parts:
            lexical = lexical / part
            is_junction = getattr(lexical, "is_junction", None)
            if lexical.is_symlink() or bool(is_junction and is_junction()):
                fail(f"{label} contains a symlink or reparse point")
        target = lexical.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} is missing") from exc
    if resolved_root not in target.parents:
        fail(f"{label} escapes the lifecycle state root")
    return target


def _read_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing or malformed") from exc


def _validate_profile(profile_path: Path, reviewer: Mapping[str, Any]) -> bytes:
    try:
        profile_raw = profile_path.read_bytes()
        profile = tomllib.loads(profile_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("reviewer profile is missing or malformed") from exc
    expected = {
        "agent_type": "sol_reviewer",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "max",
        "profile_sha256": sha(profile_raw),
    }
    if reviewer != expected:
        fail("reviewer provenance is not the exact sol_reviewer/Sol/max profile")
    if (
        profile.get("name") != "sol_reviewer"
        or profile.get("model") != "gpt-5.6-sol"
        or profile.get("model_reasoning_effort") != "max"
        or profile.get("sandbox_mode") != "read-only"
    ):
        fail("reviewer profile does not declare the read-only sol_reviewer/Sol/max contract")
    return profile_raw


def _validate_bundle(
    state_root: Path,
    export: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bytes]]:
    bundle_sha = export["bundle_sha256"]
    bundle_relative = PurePosixPath("bundles") / str(bundle_sha)
    bundle_dir = _path_under(state_root, bundle_relative.as_posix(), "lifecycle bundle")
    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        fail("lifecycle bundle must be a real directory")
    manifest_path = _path_under(state_root, (bundle_relative / "manifest.json").as_posix(), "bundle manifest")
    manifest_raw, manifest_value = _read_json(manifest_path, "bundle manifest")
    if not isinstance(manifest_value, Mapping):
        fail("bundle manifest must be an object")
    manifest = dict(manifest_value)
    if compute_packet_sha256(manifest) != bundle_sha:
        fail("bundle manifest does not bind the lifecycle bundle")
    if sha(manifest_raw) != export["bundle_manifest_sha256"]:
        fail("bundle manifest export digest mismatch")

    actual: set[str] = set()
    for path in bundle_dir.rglob("*"):
        if path.is_symlink():
            fail("bundle contains a symlink")
        if path.is_file():
            relative = path.relative_to(bundle_dir).as_posix()
            if relative != "manifest.json":
                actual.add(relative)
    if actual != set(manifest):
        fail("bundle file set differs from its manifest")

    content: dict[str, bytes] = {}
    for name, expected_sha in manifest.items():
        relative = safe_relative(name)
        if HEX64.fullmatch(str(expected_sha)) is None:
            fail("bundle manifest content digest is malformed")
        target = _path_under(
            state_root,
            (bundle_relative / relative).as_posix(),
            "bundle content",
        )
        if target.is_symlink() or not target.is_file():
            fail("bundle content must be a regular file")
        data = target.read_bytes()
        if sha(data) != expected_sha:
            fail("bundle content digest mismatch")
        content[name] = data

    required = {
        "snapshot.json",
        "review-contract.json",
        "review-packet.json",
        "review-lenses.md",
        "verification-evidence.json",
    }
    if not required.issubset(content):
        fail("bundle omits required frozen review artifacts")
    try:
        snapshot = json.loads(content["snapshot.json"])
        contract = strict(json.loads(content["review-contract.json"]), CONTRACT_FIELDS, "frozen review contract")
        packet = strict(json.loads(content["review-packet.json"]), PACKET_FIELDS, "frozen review packet")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("bundle structured artifacts are malformed") from exc
    if not isinstance(snapshot, Mapping):
        fail("frozen snapshot is malformed")
    snapshot = dict(snapshot)
    snapshot_identity = snapshot.get("snapshot_sha256")
    snapshot_payload = dict(snapshot)
    snapshot_payload.pop("snapshot_sha256", None)
    if compute_packet_sha256(snapshot_payload) != snapshot_identity:
        fail("frozen snapshot digest does not bind its content")
    if snapshot_identity != state["snapshot_sha256"]:
        fail("frozen snapshot does not bind lifecycle state")
    if sha(canonical_bytes(contract)) != packet["contract_sha256"]:
        fail("review packet does not bind the frozen contract")
    if compute_packet_sha256(packet) != state["packet_sha256"]:
        fail("review packet does not bind lifecycle state")
    lens_sha = sha(content["review-lenses.md"])
    if lens_sha != state["lens_sha256"] or packet["lens_sha256"] != lens_sha or contract["lens_sha256"] != lens_sha:
        fail("review lenses do not bind the packet, contract, and lifecycle state")
    if packet["mandatory_lenses"] != list(MANDATORY_REVIEW_LENSES) or contract["mandatory_lenses"] != list(MANDATORY_REVIEW_LENSES):
        fail("frozen bundle does not require the canonical review lenses")
    verification_sha = sha(content["verification-evidence.json"])
    if (
        contract["verification_sha256"] != verification_sha
        or packet["verification_sha256"] != verification_sha
    ):
        fail("frozen verification evidence does not bind the packet and contract")
    production_sha = contract["production_manifest_sha256"]
    if production_sha != packet["production_manifest_sha256"]:
        fail("production manifest identity differs between packet and contract")
    if production_sha is None:
        if "production-manifest.json" in content:
            fail("unbound production manifest is present in the frozen bundle")
    elif (
        HEX64.fullmatch(str(production_sha)) is None
        or "production-manifest.json" not in content
        or sha(content["production-manifest.json"]) != production_sha
    ):
        fail("frozen production manifest does not bind the packet and contract")
    contract_expected = {
        "delivery_id": state["delivery_id"],
        "task_id": state["task_id"],
        "generation": state["generation"],
        "mutation_epoch": state["frozen_epoch"],
        "attempt_id": state["attempt_id"],
        "paths_sha256": state["paths_sha256"],
        "snapshot_sha256": state["snapshot_sha256"],
        "profile_sha256": state["profile_sha256"],
    }
    if contract["schema_version"] != 1 or any(contract[field] != expected for field, expected in contract_expected.items()):
        fail("frozen review contract does not bind lifecycle state")
    if (
        packet["schema_version"] != 1
        or packet["snapshot_sha256"] != state["snapshot_sha256"]
        or packet["generation"] != state["generation"]
        or packet["mutation_epoch"] != state["frozen_epoch"]
        or packet["attempt_id"] != state["attempt_id"]
    ):
        fail("frozen review packet identity differs from lifecycle state")
    if not isinstance(packet["evidence"], list):
        fail("frozen review packet evidence is malformed")
    packet_internal = {"snapshot.json", "review-contract.json", "review-packet.json", "review-lenses.md"}
    expected_evidence = {
        name: digest_value for name, digest_value in manifest.items() if name not in packet_internal
    }
    observed_evidence: dict[str, str] = {}
    for raw in packet["evidence"]:
        item = strict(raw, {"path", "sha256"}, "frozen packet evidence")
        safe_relative(item["path"])
        if item["path"] in observed_evidence or HEX64.fullmatch(str(item["sha256"])) is None:
            fail("frozen packet evidence identity is malformed")
        observed_evidence[item["path"]] = item["sha256"]
    if observed_evidence != expected_evidence:
        fail("frozen packet evidence does not bind bundle evidence bytes")
    return snapshot, contract, packet, content


def validate_lifecycle_export(
    record: Any,
    state_root: Path | None,
    reviewer: Mapping[str, Any],
    reviewer_profile: Path,
) -> dict[str, Any]:
    """Revalidate an export against persisted lifecycle authority and frozen bytes."""
    export = strict(record, EXPORT_FIELDS, "lifecycle export")
    if export["schema_version"] != 1 or export["authority"] != "lifecycle_gate_export_v1":
        fail("lifecycle export authority is unsupported")
    if state_root is None:
        fail("lifecycle export replay requires --lifecycle-state-root")
    for field in ("session_id", "turn_id", "task_id", "delivery_id"):
        if not isinstance(export[field], str) or not export[field]:
            fail(f"lifecycle export {field} is missing")
    generation = _integer(export["generation"], "lifecycle export generation")
    for field in ("state_sha256", "bundle_sha256", "bundle_manifest_sha256", "profile_sha256", "output_sha256"):
        if HEX64.fullmatch(str(export[field])) is None:
            fail(f"lifecycle export {field} is malformed")

    composite_state_relative = (
        PurePosixPath("deliveries")
        / delivery_address_sha256(export["session_id"], export["task_id"], export["delivery_id"])
        / f"generation-{generation}.json"
    ).as_posix()
    legacy_state_relative = (
        PurePosixPath("deliveries")
        / _text_digest(export["session_id"])
        / _text_digest(export["task_id"])
        / _text_digest(export["delivery_id"])
        / f"generation-{generation}.json"
    ).as_posix()
    accepted_state_addresses = {composite_state_relative, legacy_state_relative}
    exported_state_relative = export["state_relative_path"]
    if exported_state_relative not in accepted_state_addresses:
        fail("lifecycle export state address is not canonical")
    state_path = _path_under(state_root, exported_state_relative, "lifecycle delivery state")
    state_raw, state_value = _read_json(state_path, "lifecycle delivery state")
    state = strict(state_value, STATE_FIELDS, "lifecycle delivery state")
    if sha(state_raw) != export["state_sha256"]:
        fail("lifecycle export state digest mismatch")

    active_relative = (
        PurePosixPath("active")
        / _text_digest(export["session_id"])
        / f"{_text_digest(export['turn_id'])}.json"
    ).as_posix()
    _, pointer_value = _read_json(_path_under(state_root, active_relative, "active delivery pointer"), "active delivery pointer")
    pointer = strict(pointer_value, {"schema_version", "state", "delivery_sha256", "generation"}, "active delivery pointer")
    if (
        pointer["schema_version"] != 1
        or pointer["state"] not in accepted_state_addresses
        or pointer["delivery_sha256"] != _text_digest(export["delivery_id"])
        or pointer["generation"] != generation
    ):
        fail("active delivery pointer does not bind the exported lifecycle state")
    if pointer["state"] != exported_state_relative:
        pointer_raw, pointer_state_value = _read_json(
            _path_under(state_root, pointer["state"], "active lifecycle delivery state"),
            "active lifecycle delivery state",
        )
        if pointer_raw != state_raw or pointer_state_value != state_value:
            fail("migrated active delivery state differs from the lifecycle export")

    identities = {
        "session_id": export["session_id"],
        "turn_id": export["turn_id"],
        "task_id": export["task_id"],
        "delivery_id": export["delivery_id"],
        "generation": generation,
        "bundle_sha256": export["bundle_sha256"],
        "profile_sha256": export["profile_sha256"],
        "output_sha256": export["output_sha256"],
    }
    if state["schema_version"] != 1 or any(state[field] != expected for field, expected in identities.items()):
        fail("lifecycle export does not match persisted gate state")
    if (
        state["classification"] != "material"
        or state["status"] not in {"receipted", "completed"}
        or state["mutation_epoch"] != state["frozen_epoch"]
        or state["inflight_tool_use_ids"]
    ):
        fail("lifecycle state is not a fresh receipted delivery")
    if sha(_validate_profile(reviewer_profile, reviewer)) != export["profile_sha256"]:
        fail("lifecycle export profile digest differs from the exact reviewer profile")

    output = validate_review_output(export["review_output"])
    validate_lens_coverage(output["coverage"], MANDATORY_REVIEW_LENSES)
    output_sha = sha(canonical_bytes(output))
    if output != state["review_output"] or output_sha != export["output_sha256"]:
        fail("lifecycle export output differs from persisted reviewer output")
    for field in ("attempt_id", "packet_sha256", "bundle_sha256", "snapshot_sha256"):
        if output[field] != state[field]:
            fail(f"lifecycle review output {field} does not bind persisted state")
    if any(_placeholder(output[field]) for field in ("packet_sha256", "bundle_sha256", "snapshot_sha256")):
        fail("lifecycle export contains placeholder review identities")
    if any(token in output["attempt_id"].casefold() for token in ("baseline", "curated", "fixture", "placeholder")):
        fail("lifecycle export contains a placeholder attempt identity")

    snapshot, _, _, bundle_content = _validate_bundle(state_root, export, state)
    git_resolver = None
    if snapshot.get("kind") == "git":
        repository_root = snapshot.get("repo")
        if not isinstance(repository_root, str) or not repository_root:
            fail("frozen Git repository root is unavailable")
        git_resolver = build_local_git_resolver(Path(repository_root))
    store = BundleStore(_filesystem_path(state_root) / "bundles")

    receipt = validate_review_receipt(export["receipt"])
    if receipt != state["receipt"]:
        fail("lifecycle export receipt differs from persisted gate state")
    if state["ledger"] is None:
        if state["status"] != "receipted" or state["dispositions"] is not None:
            fail("undisposed reviewer output is not in the receipted lifecycle state")
        pending = {
            "schema_version": 1,
            "generation": generation,
            "status": "pending",
            "finding_ids": [finding["id"] for finding in output["findings"]],
        }
        disposition_sha = sha(canonical_bytes(pending))
        if state["pending_disposition_sha256"] != disposition_sha:
            fail("pending disposition digest does not bind reviewer findings")
    else:
        ledger = validate_disposition_ledger(
            state["ledger"],
            output["findings"],
            generation=generation,
            store=store,
            active_bundle_sha256=export["bundle_sha256"],
            git_resolver=git_resolver,
        )
        disposition_sha = sha(canonical_bytes(ledger))
        if state["dispositions"] != disposition_sha:
            fail("persisted disposition ledger digest mismatch")
    expected_receipt = {
        "schema_version": 1,
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "delivery_id": state["delivery_id"],
        "generation": generation,
        "reviewer_agent": state["reviewer_agent"],
        "reviewer_type": "sol_reviewer",
        "reviewer_model": "gpt-5.6-sol",
        "config_sha256": state["profile_sha256"],
        "attempt_id": state["attempt_id"],
        "packet_sha256": state["packet_sha256"],
        "bundle_sha256": state["bundle_sha256"],
        "snapshot_sha256": state["snapshot_sha256"],
        "output_sha256": state["output_sha256"],
        "disposition_sha256": disposition_sha,
        "mutation_epoch": state["frozen_epoch"],
    }
    if receipt != expected_receipt:
        fail("lifecycle receipt does not bind the persisted profile, output, bundle, disposition, and epoch")
    return {
        "output": output,
        "receipt": receipt,
        "bundle_sha256": export["bundle_sha256"],
        "snapshot": snapshot,
        "bundle_content": bundle_content,
    }


def lifecycle_bundle_anchors_input(snapshot: Mapping[str, Any], case_input: Mapping[str, Any]) -> bool:
    files = snapshot.get("files")
    if not isinstance(files, list):
        return False
    expected_path = case_input.get("path")
    item = next(
        (
            candidate
            for candidate in files
            if isinstance(candidate, Mapping) and candidate.get("path") == expected_path
        ),
        None,
    )
    if item is None:
        return False
    if case_input.get("kind") == "git_review":
        head = item.get("head")
        return (
            snapshot.get("kind") == "git"
            and snapshot.get("head") == case_input.get("commit")
            and isinstance(head, Mapping)
            and head.get("present") is True
            and head.get("sha256") == case_input.get("source_sha256")
        )
    if case_input.get("kind") == "local_fixture":
        worktree = item.get("worktree")
        return (
            isinstance(worktree, Mapping)
            and worktree.get("present") is True
            and worktree.get("sha256") == case_input.get("sha256")
        )
    return False


def lifecycle_bundle_case_bytes(
    snapshot: Mapping[str, Any],
    bundle_content: Mapping[str, bytes],
    case_input: Mapping[str, Any],
) -> bytes | None:
    if not lifecycle_bundle_anchors_input(snapshot, case_input):
        return None
    path = str(case_input.get("path", ""))
    source = "head" if case_input.get("kind") == "git_review" else "worktree"
    data = bundle_content.get(f"evidence/{source}/{path}")
    expected_sha = case_input.get("source_sha256") if source == "head" else case_input.get("sha256")
    return data if isinstance(data, bytes) and sha(data) == expected_sha else None


def load_results(
    record: Any,
    corpus_id: str,
    cases: list[Mapping[str, Any]],
    reviewer_profile: Path | None,
    lifecycle_state_root: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], str, bool]:
    if not isinstance(record, Mapping):
        fail("candidate results must be a record")
    kind = record.get("results_kind")
    common = {"schema_version", "results_kind", "corpus_id", "corpus_sha256", "replay_id", "cases"}
    if kind == "curated_evaluator_self_test":
        root = strict(record, common, "curated evaluator self-test")
        item_fields = {"id", "input_sha256", "output"}
        provenance_verified = False
    elif kind == "sol_reviewer_replay":
        root = strict(record, common | {"reviewer"}, "Sol reviewer replay")
        reviewer = strict(
            root["reviewer"],
            {"agent_type", "model", "reasoning_effort", "profile_sha256"},
            "reviewer provenance",
        )
        if reviewer_profile is None:
            fail("provenance-bound replay requires --reviewer-profile")
        _validate_profile(reviewer_profile, reviewer)
        item_fields = {"id", "input_sha256", "case_sha256", "lifecycle_export"}
        provenance_verified = True
    else:
        fail("candidate results kind is unsupported")
    if root["schema_version"] != 1 or root["corpus_id"] != corpus_id or not isinstance(root["replay_id"], str) or not root["replay_id"]:
        fail("candidate-results identity is invalid")
    if root["corpus_sha256"] != input_manifest_sha(cases):
        fail("candidate-results corpus identity mismatch")
    if not isinstance(root["cases"], list):
        fail("candidate results cases must be a list")
    results: dict[str, dict[str, Any]] = {}
    cases_by_id = {case["id"]: case for case in cases}
    seen_lifecycle_receipts: set[tuple[Any, ...]] = set()
    for raw in root["cases"]:
        item = strict(
            raw,
            item_fields,
            "lifecycle export candidate result" if provenance_verified else "candidate result",
        )
        case_id = item["id"]
        if not isinstance(case_id, str) or not case_id or case_id in results:
            fail("candidate result ID is missing or duplicated")
        if HEX64.fullmatch(str(item["input_sha256"])) is None:
            fail("candidate result input digest is malformed")
        if provenance_verified:
            if HEX64.fullmatch(str(item["case_sha256"])) is None:
                fail("provenance-bound case_sha256 is malformed")
            validated = validate_lifecycle_export(
                item["lifecycle_export"], lifecycle_state_root, reviewer, reviewer_profile
            )
            case = cases_by_id.get(case_id)
            if case is None or not lifecycle_bundle_anchors_input(validated["snapshot"], case["input"]):
                fail(f"lifecycle frozen bundle does not contain the immutable case artifact: {case_id}")
            case_source = lifecycle_bundle_case_bytes(
                validated["snapshot"], validated["bundle_content"], case["input"]
            )
            if case_source is None:
                fail(f"lifecycle frozen bundle case bytes are missing: {case_id}")
            receipt = validated["receipt"]
            receipt_identity = (
                receipt["session_id"], receipt["task_id"], receipt["delivery_id"],
                receipt["generation"], receipt["attempt_id"], receipt["output_sha256"],
            )
            if receipt_identity in seen_lifecycle_receipts:
                fail("lifecycle receipt was replayed for more than one evaluation case")
            seen_lifecycle_receipts.add(receipt_identity)
            validated.pop("bundle_content")
            item = {**item, **validated, "case_source": case_source}
        results[case_id] = item
    if set(results) != {case["id"] for case in cases}:
        fail("candidate results do not exactly cover corpus cases")
    return results, str(kind), provenance_verified


def _matches_concepts(text: Any, groups: list[list[str]]) -> bool:
    value = str(text).casefold()
    return all(
        any(re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", value) for term in group)
        for group in groups
    )


def selector_present(selector: Mapping[str, Any], source: bytes) -> bool:
    if selector.get("kind") == "symbol":
        return str(selector.get("value", "")).encode("utf-8") in source
    if selector.get("kind") == "line_range":
        line_count = len(source.splitlines())
        return 1 <= int(selector.get("start", 0)) <= int(selector.get("end", 0)) <= line_count
    return False


def case_evidence_selector(evidence: Any, case_input: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(evidence, list):
        return None
    selectors: list[dict[str, Any]] = []
    if case_input.get("kind") == "git_review":
        for item in evidence:
            if (
                isinstance(item, Mapping)
                and item.get("kind") == "git_commit"
                and item.get("repository") == case_input.get("repository")
                and item.get("commit") == case_input.get("commit")
                and item.get("path") == case_input.get("path")
                and item.get("sha256") == case_input.get("source_sha256")
                and "selector" in item
            ):
                selectors.append(validate_evidence_selector(item["selector"]))
    elif case_input.get("kind") == "local_fixture":
        expected_sha = case_input.get("sha256")
        expected_suffix = "/" + str(case_input.get("path", ""))
        for item in evidence:
            if (
                isinstance(item, Mapping)
                and item.get("kind") == "bundle"
                and item.get("sha256") == expected_sha
                and isinstance(item.get("uri"), str)
                and item["uri"].endswith(expected_suffix)
                and "selector" in item
            ):
                selectors.append(validate_evidence_selector(item["selector"]))
    return selectors[0] if len(selectors) == 1 else None


def matching_expectations(
    finding: Mapping[str, Any],
    case_input: Mapping[str, Any],
    expectations: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    selector = case_evidence_selector(finding["evidence"], case_input)
    if selector is None:
        return []
    selector_identity = canonical_bytes(selector)
    return [
        expectation
        for expectation in expectations
        if canonical_bytes(expectation["evidence_selector"]) == selector_identity
        and _matches_concepts(finding["claim"], expectation["claim_concepts"])
        and _matches_concepts(finding["correction"], expectation["correction_concepts"])
        and _matches_concepts(finding["verification"], expectation["verification_concepts"])
    ]


def evaluate(
    corpus: dict[str, Any],
    corpus_path: Path,
    results_record: dict[str, Any],
    identities: Mapping[str, Mapping[str, Any]],
    reviewer_profile: Path | None = None,
    lifecycle_state_root: Path | None = None,
    claim_empirical_quality: bool = False,
) -> dict[str, Any]:
    root = strict(corpus, {"schema_version", "corpus_id", "lens_sha256", "cases"}, "evaluation corpus")
    if root["schema_version"] != 1 or not isinstance(root["corpus_id"], str) or not root["corpus_id"]:
        fail("evaluation corpus identity is invalid")
    lens_path = corpus_path.parent / "review-lenses.md"
    if HEX64.fullmatch(str(root["lens_sha256"])) is None or sha(lens_path.read_bytes()) != root["lens_sha256"]:
        fail("review lens digest mismatch")
    if not isinstance(root["cases"], list) or not root["cases"]:
        fail("evaluation cases are required")
    cases = [strict(case, {"ground_truth", "id", "input", "kind"}, "evaluation case") for case in root["cases"]]
    results, results_kind, provenance_verified = load_results(
        results_record, root["corpus_id"], cases, reviewer_profile, lifecycle_state_root
    )

    required_categories = found_categories = controls = controls_with_findings = 0
    expected_findings = quality_findings = authenticated_git_reviews = corrected_non_cpp_controls = 0
    kinds: set[str] = set()
    case_ids: set[str] = set()
    failures: list[str] = []
    missing_categories: dict[str, list[str]] = {}
    allowed_kinds = {"windhawk_cpp", "corrected_control", "non_cpp", "corrected_non_cpp_control"}
    for case in cases:
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            fail("evaluation case ID is missing or duplicated")
        case_ids.add(case_id)
        if case["kind"] not in allowed_kinds:
            fail(f"unsupported case kind: {case['kind']}")
        kinds.add(case["kind"])
        authenticated_git_reviews += int(validate_input(case["input"], corpus_path.parent, case_id, identities))
        if case["kind"] == "corrected_non_cpp_control":
            corrected_non_cpp_controls += 1
            if case["input"].get("kind") != "local_fixture":
                fail("corrected non-C++ control must be an immutable local fixture")
        truth = validate_ground_truth(case["ground_truth"])
        replay = results[case_id]
        case_source: bytes | None = replay.get("case_source")
        if case_source is None and case["input"].get("kind") == "local_fixture":
            relative = safe_relative(case["input"]["path"])
            case_source = corpus_path.parent.joinpath(*relative.parts).read_bytes()
        if replay["input_sha256"] != sha(canonical_bytes(case["input"])):
            fail(f"candidate result input identity mismatch: {case_id}")
        if provenance_verified:
            expected_case_sha = sha(canonical_bytes({"id": case_id, "kind": case["kind"], "input": case["input"]}))
            if replay["case_sha256"] != expected_case_sha:
                fail(f"provenance-bound immutable case identity mismatch: {case_id}")
        output = validate_review_output(replay["output"])
        validate_lens_coverage(output["coverage"], MANDATORY_REVIEW_LENSES)
        if output["verdict"] == "blocked":
            failures.append(f"{case_id}: candidate replay is blocked")
        findings = output["findings"]
        if not truth["allow_findings"]:
            controls += 1
            if findings:
                controls_with_findings += 1
                failures.append(f"{case_id}: prohibited finding on control")
            if output["verdict"] != "pass":
                failures.append(f"{case_id}: control verdict must pass")
            continue
        if output["verdict"] != "fail":
            failures.append(f"{case_id}: finding case verdict must fail")
        required = list(truth["required_categories"])
        expectations = list(truth["expectations"])
        required_categories += len(required)
        expected_findings += len(required)
        covered: set[str] = set()
        unmatched_ids: list[str] = []
        for finding in findings:
            selector = case_evidence_selector(finding["evidence"], case["input"])
            if selector is not None and case_source is not None and not selector_present(selector, case_source):
                failures.append(
                    f"{case_id}: finding {finding['id']} selector is not present in the immutable case artifact bytes"
                )
                unmatched_ids.append(finding["id"])
                continue
            matched = matching_expectations(finding, case["input"], expectations)
            if len(matched) > 1:
                failures.append(
                    f"{case_id}: ambiguous multi-category finding {finding['id']} cannot receive one-to-one credit"
                )
                unmatched_ids.append(finding["id"])
                continue
            if not matched:
                failures.append(
                    f"{case_id}: finding {finding['id']} lacks a distinct immutable case artifact selector or the required defect concept, correction, and verification semantics"
                )
                unmatched_ids.append(finding["id"])
                continue
            category = matched[0]["category"]
            if category in covered:
                failures.append(f"{case_id}: duplicate finding for category {category} violates one-to-one scoring")
                unmatched_ids.append(finding["id"])
                continue
            covered.add(category)
            quality_findings += int(
                len(finding["correction"].strip()) >= 20
                and len(finding["verification"].strip()) >= 20
            )
        found_categories += len(covered)
        missing = sorted(set(required) - covered)
        if missing:
            missing_categories[case_id] = missing
            failures.append(f"{case_id}: missing required categories {', '.join(missing)}")
        if unmatched_ids:
            failures.append(f"{case_id}: unmatched candidate findings {unmatched_ids}")

    if not {"windhawk_cpp", "corrected_control", "non_cpp", "corrected_non_cpp_control"}.issubset(kinds):
        failures.append("corpus lacks required language/control kinds")
    if corrected_non_cpp_controls < 1:
        failures.append("corpus lacks an immutable corrected non-C++ control")
    if authenticated_git_reviews != len(identities):
        failures.append("not all trusted Git identities were exercised exactly once")
    recall = found_categories / required_categories if required_categories else 1.0
    false_positive_rate = controls_with_findings / controls if controls else 1.0
    finding_quality_rate = quality_findings / expected_findings if expected_findings else 1.0
    if recall != 1.0:
        failures.append("required category recall is below 1.0")
    if false_positive_rate != 0.0:
        failures.append("control false-positive rate exceeds 0.0")
    if finding_quality_rate != 1.0:
        failures.append("finding evidence/correction/verification quality is below 1.0")
    if claim_empirical_quality and not provenance_verified:
        failures.append("empirical reviewer-quality claim requires provenance-bound sol_reviewer replay results")
    empirical_quality_claim_eligible = provenance_verified and not failures
    return {
        "ok": not failures,
        "case_count": len(cases),
        "kinds": sorted(kinds),
        "authenticated_git_reviews": authenticated_git_reviews,
        "corrected_non_cpp_controls": corrected_non_cpp_controls,
        "results_kind": results_kind,
        "provenance_verified": provenance_verified,
        "empirical_quality_claim_eligible": empirical_quality_claim_eligible,
        "required_category_recall": recall,
        "missing_categories": missing_categories,
        "control_false_positive_rate": false_positive_rate,
        "finding_quality_rate": finding_quality_rate,
        "failures": failures,
        "note": (
            "Curated evaluator self-test only; it validates scoring mechanics and is not empirical reviewer-quality evidence."
            if not provenance_verified
            else "Provenance-bound Sol/max replay; metrics remain empirical regression evidence, not proof of complete defect detection."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True, help="separate model-replay ReviewOutputV1 results")
    parser.add_argument("--git-identities", type=Path, required=True, help="trusted primary-source identity pins")
    parser.add_argument("--reviewer-profile", type=Path, help="exact sol_reviewer profile used by a provenance replay")
    parser.add_argument("--lifecycle-state-root", type=Path, help="persisted lifecycle authority referenced by a replay export")
    parser.add_argument("--claim-empirical-quality", action="store_true", help="fail unless results have exact Sol/max provenance")
    args = parser.parse_args()
    try:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        results = json.loads(args.results.read_text(encoding="utf-8"))
        identities = load_git_identities(args.git_identities)
        report = evaluate(
            corpus,
            args.corpus.resolve(strict=True),
            results,
            identities,
            args.reviewer_profile.resolve(strict=True) if args.reviewer_profile else None,
            _filesystem_path(args.lifecycle_state_root).resolve(strict=True)
            if args.lifecycle_state_root
            else None,
            claim_empirical_quality=args.claim_empirical_quality,
        )
        print(json.dumps(report, sort_keys=True))
        return 0 if report["ok"] else 2
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
