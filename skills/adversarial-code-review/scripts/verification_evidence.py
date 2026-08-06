"""Strict verification-evidence and production-manifest contracts."""
from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from review_contracts import canonical_bytes, compute_raw_sha256  # noqa: E402


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
GLOB_TOKENS = set("*?[]{}")
CREDENTIAL_TOKENS = (".env", "credential", "id_rsa", "private-key", "secret", "token")
MAX_COMMANDS = 128
MAX_OBSERVATIONS = 64
MAX_ARTIFACTS = 384
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
OBSERVATION_PROVENANCE = {
    "handler_contract_smoke": "synthetic",
    "subagent_provenance": "live",
    "mutation_observation": "live",
    "hook_trust": "live",
    "runtime_restart": "live",
}


def _strict(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)}")
    return value


def _text(value: Any, label: str, *, maximum: int = 16_384) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be non-empty text no longer than {maximum} characters")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _text(value, label, maximum=64)
    if not IDENTIFIER.fullmatch(text):
        raise ValueError(f"{label} is not a safe identifier")
    return text


def _relative(value: Any, label: str, *, allow_dot: bool = False) -> str:
    text = _text(value, label, maximum=4096).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or ".." in path.parts
        or (not allow_dot and text in {"", "."})
        or any(token in text for token in GLOB_TOKENS)
        or any(part in {"", "."} for part in path.parts if part != ".")
    ):
        raise ValueError(f"{label} must be a safe relative path without traversal or globs")
    return path.as_posix()


def _nonnegative(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _is_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _check_deadline(deadline: float | None, clock: Callable[[], float]) -> None:
    if deadline is None:
        return
    observed = clock()
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed):
        raise ValueError("verification clock is invalid")
    if observed >= deadline:
        raise ValueError("snapshot limit exceeded")


def _bounded_read(
    path: Path,
    expected_size: int,
    *,
    deadline: float | None,
    clock: Callable[[], float],
) -> bytes:
    _check_deadline(deadline, clock)
    chunks: list[bytes] = []
    observed = 0
    with path.open("rb") as stream:
        while observed <= expected_size:
            _check_deadline(deadline, clock)
            chunk = stream.read(min(READ_CHUNK_BYTES, expected_size - observed + 1))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
    _check_deadline(deadline, clock)
    if observed != expected_size:
        raise ValueError(f"{path.name or 'manifest'} changed while it was being read")
    return b"".join(chunks)


def _read_artifact(
    root: Path,
    value: Any,
    label: str,
    bundle_path: str,
    *,
    budget: list[int],
    deadline: float | None,
    clock: Callable[[], float],
) -> tuple[dict[str, Any], bytes]:
    item = _strict(value, {"path", "sha256", "size_bytes"}, label)
    relative = _relative(item["path"], f"{label}.path")
    if any(any(token in part.casefold() for token in CREDENTIAL_TOKENS) for part in PurePosixPath(relative).parts):
        raise ValueError(f"{label} credential-like path is rejected")
    expected_sha = item["sha256"]
    if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
        raise ValueError(f"{label}.sha256 must be a lowercase SHA-256 digest")
    expected_size = _nonnegative(item["size_bytes"], f"{label}.size_bytes")
    if expected_size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} exceeds the per-artifact size limit")
    lexical = root.joinpath(*PurePosixPath(relative).parts)
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor /= part
        if _is_reparse(cursor):
            raise ValueError(f"{label} must not traverse a symlink or reparse point")
    resolved_root = root.resolve(strict=True)
    resolved = lexical.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise ValueError(f"{label} escapes the verification manifest directory")
    before = resolved.stat()
    if not resolved.is_file() or before.st_size != expected_size:
        raise ValueError(f"{label} size does not match its declared artifact")
    if budget[0] >= MAX_ARTIFACTS or budget[1] + expected_size > MAX_TOTAL_BYTES:
        raise ValueError("verification evidence exceeds artifact count or total-byte limits")
    data = _bounded_read(resolved, expected_size, deadline=deadline, clock=clock)
    after = resolved.stat()
    if len(data) != expected_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"{label} changed while it was being read")
    if compute_raw_sha256(data) != expected_sha:
        raise ValueError(f"{label} digest does not match its declared artifact")
    budget[0] += 1
    budget[1] += expected_size
    return {"path": bundle_path, "sha256": expected_sha, "size_bytes": expected_size}, data


def build_verification_evidence(
    path: str | os.PathLike[str],
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Validate VerificationEvidenceV1 inputs and return content-addressed bundle files."""
    lexical_manifest = Path(path).expanduser()
    if not lexical_manifest.is_absolute():
        lexical_manifest = Path.cwd() / lexical_manifest
    if _is_reparse(lexical_manifest):
        raise ValueError("verification manifest must not be a symlink or reparse point")
    manifest_path = lexical_manifest.resolve(strict=True)
    if not manifest_path.is_file():
        raise ValueError("verification manifest must be a regular non-symlink file")
    manifest_size = manifest_path.stat().st_size
    if manifest_size > MAX_MANIFEST_BYTES:
        raise ValueError("verification manifest exceeds its size limit")
    try:
        manifest_bytes = _bounded_read(manifest_path, manifest_size, deadline=deadline, clock=clock)
        source = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("verification manifest is not valid UTF-8 JSON") from exc
    source = _strict(source, {"schema_version", "platform", "commands", "observations"}, "verification evidence")
    if type(source["schema_version"]) is not int or source["schema_version"] != 1:
        raise ValueError("unsupported verification evidence version")

    platform = _strict(source["platform"], {"system", "release", "machine", "python"}, "platform")
    normalized_platform = {
        field: _text(platform[field], f"platform.{field}", maximum=1024)
        for field in ("system", "release", "machine", "python")
    }
    commands = source["commands"]
    observations = source["observations"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise ValueError("verification evidence requires between 1 and 128 commands")
    if not isinstance(observations, list) or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise ValueError("verification evidence requires between 1 and 64 observations")

    root = manifest_path.parent
    budget = [0, 0]
    bundle_files: dict[str, bytes] = {}
    normalized_commands: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(commands):
        item = _strict(
            raw,
            {"id", "command", "cwd", "exit_code", "test_counts", "stdout", "stderr"},
            f"commands[{index}]",
        )
        identifier = _identifier(item["id"], f"commands[{index}].id")
        if identifier in seen_ids:
            raise ValueError(f"duplicate verification identifier: {identifier}")
        seen_ids.add(identifier)
        command = _text(item["command"], f"commands[{index}].command")
        cwd = _relative(item["cwd"], f"commands[{index}].cwd", allow_dot=True)
        exit_code = item["exit_code"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ValueError(f"commands[{index}].exit_code must be an integer")
        counts = _strict(
            item["test_counts"],
            {"passed", "failed", "errors", "skipped"},
            f"commands[{index}].test_counts",
        )
        normalized_counts = {
            name: _nonnegative(counts[name], f"commands[{index}].test_counts.{name}")
            for name in ("passed", "failed", "errors", "skipped")
        }
        if exit_code != 0 or normalized_counts["failed"] or normalized_counts["errors"]:
            raise ValueError(f"commands[{index}] is not successful verification evidence")
        stdout_path = f"verification/artifacts/{identifier}.stdout"
        stderr_path = f"verification/artifacts/{identifier}.stderr"
        stdout, stdout_bytes = _read_artifact(
            root, item["stdout"], f"commands[{index}].stdout", stdout_path,
            budget=budget, deadline=deadline, clock=clock,
        )
        stderr, stderr_bytes = _read_artifact(
            root, item["stderr"], f"commands[{index}].stderr", stderr_path,
            budget=budget, deadline=deadline, clock=clock,
        )
        bundle_files[stdout_path] = stdout_bytes
        bundle_files[stderr_path] = stderr_bytes
        normalized_commands.append(
            {
                "id": identifier,
                "command": command,
                "cwd": cwd,
                "exit_code": exit_code,
                "test_counts": normalized_counts,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    normalized_observations: list[dict[str, Any]] = []
    saw_synthetic = False
    saw_live = False
    seen_subjects: set[str] = set()
    for index, raw in enumerate(observations):
        item = _strict(raw, {"id", "subject", "provenance", "status", "detail", "artifact"}, f"observations[{index}]")
        identifier = _identifier(item["id"], f"observations[{index}].id")
        if identifier in seen_ids:
            raise ValueError(f"duplicate verification identifier: {identifier}")
        seen_ids.add(identifier)
        subject = item["subject"]
        if subject not in OBSERVATION_PROVENANCE:
            raise ValueError(f"observations[{index}].subject is unsupported")
        if subject in seen_subjects:
            raise ValueError(f"duplicate verification observation subject: {subject}")
        seen_subjects.add(subject)
        provenance = item["provenance"]
        if provenance != OBSERVATION_PROVENANCE[subject]:
            raise ValueError(f"observations[{index}] has invalid synthetic/live provenance")
        status = item["status"]
        if status not in {"passed", "failed", "unavailable", "not_run"}:
            raise ValueError(f"observations[{index}].status is unsupported")
        detail = _text(item["detail"], f"observations[{index}].detail", maximum=4096)
        artifact = item["artifact"]
        if status in {"passed", "failed"}:
            if artifact is None:
                raise ValueError(f"observations[{index}] {status} status requires a raw artifact")
            bundle_path = f"verification/artifacts/{identifier}.evidence"
            normalized_artifact, artifact_bytes = _read_artifact(
                root,
                artifact,
                f"observations[{index}].artifact",
                bundle_path,
                budget=budget,
                deadline=deadline,
                clock=clock,
            )
            bundle_files[bundle_path] = artifact_bytes
        else:
            if artifact is not None:
                raise ValueError(f"observations[{index}] {status} status cannot claim an artifact")
            normalized_artifact = None
        saw_synthetic = saw_synthetic or provenance == "synthetic"
        saw_live = saw_live or provenance == "live"
        normalized_observations.append(
            {
                "id": identifier,
                "subject": subject,
                "provenance": provenance,
                "status": status,
                "detail": detail,
                "artifact": normalized_artifact,
            }
        )
    if not saw_synthetic or not saw_live:
        raise ValueError("verification evidence must explicitly distinguish synthetic and live observations")
    missing_subjects = set(OBSERVATION_PROVENANCE) - seen_subjects
    if missing_subjects:
        raise ValueError(f"missing required observation subjects: {sorted(missing_subjects)}")

    record = {
        "schema_version": 1,
        "platform": normalized_platform,
        "commands": normalized_commands,
        "observations": normalized_observations,
    }
    record_bytes = canonical_bytes(record)
    return {
        "record": record,
        "record_bytes": record_bytes,
        "sha256": compute_raw_sha256(record_bytes),
        "bundle_files": bundle_files,
    }


def load_production_manifest(
    path: str | os.PathLike[str],
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    return_bytes: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], bytes]:
    """Load strict ProductionManifestV1 and verify its derived review set."""
    manifest_path = Path(path)
    try:
        if not manifest_path.is_absolute():
            manifest_path = Path.cwd() / manifest_path
        if _is_reparse(manifest_path):
            raise ValueError("production manifest must not be a symlink or reparse point")
        manifest_path = manifest_path.resolve(strict=True)
        if not manifest_path.is_file():
            raise ValueError("production manifest must be a regular non-symlink file")
        manifest_size = manifest_path.stat().st_size
        if manifest_size > MAX_MANIFEST_BYTES:
            raise ValueError("production manifest exceeds its size limit")
        manifest_bytes = _bounded_read(
            manifest_path,
            manifest_size,
            deadline=deadline,
            clock=clock,
        )
        value = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("production manifest is not valid UTF-8 JSON") from exc
    value = _strict(value, {"schema_version", "copy_paths", "semantic_inputs", "review_paths"}, "production manifest")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported production manifest version")
    copy_paths = value["copy_paths"]
    semantic_inputs = value["semantic_inputs"]
    review_paths = value["review_paths"]
    if not isinstance(copy_paths, list) or not copy_paths:
        raise ValueError("production manifest copy_paths must be a non-empty list")
    if not isinstance(semantic_inputs, list) or not semantic_inputs:
        raise ValueError("production manifest semantic_inputs must be a non-empty list")
    if not isinstance(review_paths, list) or not review_paths:
        raise ValueError("production manifest review_paths must be a non-empty list")
    normalized_copy = [_relative(item, f"copy_paths[{index}]") for index, item in enumerate(copy_paths)]
    if len(normalized_copy) != len(set(normalized_copy)):
        raise ValueError("production manifest has duplicate copy paths")
    normalized_semantic: list[dict[str, str]] = []
    for index, raw in enumerate(semantic_inputs):
        item = _strict(raw, {"path", "role"}, f"semantic_inputs[{index}]")
        normalized_semantic.append(
            {
                "path": _relative(item["path"], f"semantic_inputs[{index}].path"),
                "role": _identifier(item["role"], f"semantic_inputs[{index}].role"),
            }
        )
    semantic_paths = [item["path"] for item in normalized_semantic]
    if len(semantic_paths) != len(set(semantic_paths)):
        raise ValueError("production manifest has duplicate semantic input paths")
    normalized_review = [_relative(item, f"review_paths[{index}]") for index, item in enumerate(review_paths)]
    if len(normalized_review) != len(set(normalized_review)):
        raise ValueError("production manifest has duplicate review paths")
    expected_review = list(dict.fromkeys([*normalized_copy, *semantic_paths]))
    if normalized_review != expected_review:
        raise ValueError("production manifest review_paths must be the ordered union of copy and semantic inputs")
    normalized = {
        "schema_version": 1,
        "copy_paths": normalized_copy,
        "semantic_inputs": normalized_semantic,
        "review_paths": normalized_review,
    }
    if return_bytes:
        return normalized, manifest_bytes
    return normalized
