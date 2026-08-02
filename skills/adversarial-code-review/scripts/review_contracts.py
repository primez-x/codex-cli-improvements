"""Strict, persisted V1 contracts for immutable adversarial-review evidence."""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

_PACKET = Path(__file__).resolve().parents[2] / "plan-review-ladder" / "scripts"
sys.path.insert(0, str(_PACKET))
from packet_integrity import canonical_bytes, compute_packet_sha256, compute_raw_sha256  # noqa: E402

_HEX = set("0123456789abcdef")
_BLOCKING = {"critical", "high"}
_AUTHORITY_KIND = re.compile(r"[a-z][a-z0-9._-]{1,63}\Z")
_OPAQUE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}\Z")
_SYMBOL_SELECTOR = re.compile(r"[A-Za-z_~][A-Za-z0-9_:.<>~$-]{0,255}\Z")
_MUTABLE_VERSIONS = {"branch", "current", "dev", "develop", "head", "latest", "main", "master", "stable", "trunk"}
_SECRET_QUERY_KEY = re.compile(
    r"(?:^|[-_.])(?:access[-_]?token|api[-_]?key|auth(?:orization)?|credential|key|password|secret|sig(?:nature)?|token)(?:$|[-_.])",
    re.IGNORECASE,
)
MANDATORY_REVIEW_LENSES = (
    "artifact_identity",
    "lifecycle_cleanup",
    "concurrency_ownership",
    "input_command_boundaries",
    "memory_resource_safety",
    "performance_hot_paths",
    "repository_contracts",
    "indirect_consumers",
    "overlap_attribution",
    "author_verification",
)


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{field} must be a nonempty string")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int): raise ValueError(f"{field} must be an integer")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value): raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def validate_git_object_id(value: Any, field: str = "Git object id") -> str:
    object_id = _nonempty(value, field)
    if len(object_id) not in {40, 64} or any(character not in _HEX for character in object_id):
        raise ValueError(f"{field} must be a full lowercase Git object id")
    return object_id


def _record(record: Mapping[str, Any], fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(record, Mapping) or set(record) != fields: raise ValueError(f"{name} fields are not exact")
    value = dict(record)
    if value["schema_version"] != 1 or isinstance(value["schema_version"], bool): raise ValueError(f"{name} supports schema_version 1 only")
    return value


def _absolute_uri(value: Any, field: str, *, schemes: set[str]) -> str:
    uri = _nonempty(value, field)
    if any(ord(character) < 0x20 for character in uri):
        raise ValueError(f"{field} contains a control character")
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
        parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is malformed") from exc
    if parsed.scheme.lower() not in schemes or not parsed.netloc or hostname is None or parsed.fragment:
        raise ValueError(f"{field} must be an absolute authoritative URI")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not contain user information")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if (
            _SECRET_QUERY_KEY.search(key)
            or lowered.startswith(("x-amz-", "x-goog-", "x-ms-"))
            or lowered in {"sas", "sharedaccesssignature"}
        ):
            raise ValueError(f"{field} must not contain credential or signed query parameters")
    return uri


def _authority(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "source"}:
        raise ValueError("authority must contain exactly kind and source")
    authority = dict(value)
    kind = _nonempty(authority["kind"], "authority kind")
    if _AUTHORITY_KIND.fullmatch(kind) is None:
        raise ValueError("authority kind is invalid")
    _absolute_uri(
        authority["source"],
        "authority source",
        schemes={"az", "gs", "https", "oci", "s3", "ssh"},
    )
    return authority


def _bundle_uri(value: Any) -> str:
    uri = _nonempty(value, "bundle uri")
    if not uri.startswith("bundle://"):
        raise ValueError("bundle evidence requires a bundle URI")
    parts = uri[len("bundle://"):].split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError("invalid bundle URI")
    _sha(parts[0], "bundle uri digest")
    _safe_relative(parts[1])
    return uri


def _bundle_uri_parts(value: Any) -> tuple[str, str]:
    uri = _bundle_uri(value)
    digest, path = uri[len("bundle://"):].split("/", 1)
    return digest, _safe_relative(path).as_posix()


def validate_evidence_selector(record: Any) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError("evidence selector must be a strict record")
    selector = dict(record)
    kind = selector.get("kind")
    if kind == "symbol":
        if set(selector) != {"kind", "value"}:
            raise ValueError("symbol selector fields are not exact")
        value = _nonempty(selector["value"], "symbol selector")
        if _SYMBOL_SELECTOR.fullmatch(value) is None:
            raise ValueError("symbol selector is malformed")
    elif kind == "line_range":
        if set(selector) != {"kind", "start", "end"}:
            raise ValueError("line-range selector fields are not exact")
        start = selector["start"]
        end = selector["end"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
        ):
            raise ValueError("line-range selector is malformed")
    else:
        raise ValueError("evidence selector kind is unsupported")
    return selector


def validate_external_evidence(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list): raise ValueError("external evidence must be a list")
    valid: list[dict[str, Any]] = []
    for item in items:
        try:
            if not isinstance(item, Mapping):
                raise ValueError("external evidence must be a strict record")
            value = dict(item)
            kind = value.get("kind")
            if kind == "bundle":
                if set(value) not in ({"kind", "uri", "sha256"}, {"kind", "uri", "sha256", "selector"}):
                    raise ValueError("bundle evidence fields are not exact")
                _bundle_uri(value["uri"])
                _sha(value["sha256"], "bundle evidence sha256")
                if "selector" in value:
                    validate_evidence_selector(value["selector"])
            elif kind == "git_commit":
                if set(value) not in (
                    {"kind", "repository", "commit", "path"},
                    {"kind", "repository", "commit", "path", "selector"},
                ):
                    raise ValueError("Git evidence fields are not exact")
                repository = _absolute_uri(
                    value["repository"],
                    "Git repository authority",
                    schemes={"git", "https", "ssh"},
                )
                if urlsplit(repository).path in {"", "/"}:
                    raise ValueError("Git repository authority requires a repository path")
                validate_git_object_id(value["commit"], "Git evidence commit")
                _safe_relative(value["path"])
                if "selector" in value:
                    validate_evidence_selector(value["selector"])
            elif kind == "digest":
                if set(value) != {"kind", "uri", "authority", "sha256"}:
                    raise ValueError("digest evidence fields are not exact")
                _absolute_uri(
                    value["uri"],
                    "digest reference URI",
                    schemes={"az", "gs", "https", "oci", "s3"},
                )
                _authority(value["authority"])
                _sha(value["sha256"], "digest evidence sha256")
            elif kind == "opaque_version":
                if set(value) != {"kind", "uri", "authority", "version", "immutable"}:
                    raise ValueError("opaque evidence fields are not exact")
                _absolute_uri(
                    value["uri"],
                    "opaque reference URI",
                    schemes={"az", "gs", "https", "oci", "s3"},
                )
                _authority(value["authority"])
                version = _nonempty(value["version"], "opaque version")
                if (
                    value["immutable"] is not True
                    or _OPAQUE_VERSION.fullmatch(version) is None
                    or version.casefold() in _MUTABLE_VERSIONS
                ):
                    raise ValueError("opaque version is not explicitly immutable")
            else:
                raise ValueError("external evidence kind is unsupported")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid external evidence: {exc}") from exc
        valid.append(value)
    return valid


def _validate_selector_content(
    selector: Mapping[str, Any],
    content: bytes,
    *,
    max_line_span: int,
) -> None:
    value = validate_evidence_selector(selector)
    if value["kind"] == "symbol":
        symbol = re.escape(value["value"].encode("utf-8"))
        if re.search(rb"(?<![A-Za-z0-9_$])" + symbol + rb"(?![A-Za-z0-9_$])", content) is None:
            raise ValueError("evidence symbol selector is absent from immutable content")
        return
    start = value["start"]
    end = value["end"]
    if end - start + 1 > max_line_span:
        raise ValueError("evidence line-range selector exceeds the bounded span")
    if end > len(content.splitlines()):
        raise ValueError("evidence line-range selector is absent from immutable content")


def validate_finding_evidence(
    findings: Any,
    *,
    store: "BundleStore",
    active_bundle_sha256: str,
    git_resolver: Callable[[str, str, str], bytes] | None = None,
    max_line_span: int = 200,
) -> list[dict[str, Any]]:
    """Bind every finding selector to exact bytes in the active bundle or pinned Git."""
    active = _sha(active_bundle_sha256, "active bundle sha256")
    if (
        isinstance(max_line_span, bool)
        or not isinstance(max_line_span, int)
        or max_line_span < 1
    ):
        raise ValueError("max_line_span must be a positive integer")
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    manifest = store.manifest(active)
    validated: list[dict[str, Any]] = []
    for item in findings:
        if not isinstance(item, Mapping) or not isinstance(item.get("evidence"), list) or not item["evidence"]:
            raise ValueError("every finding requires immutable evidence")
        for raw_evidence in item["evidence"]:
            if not isinstance(raw_evidence, Mapping):
                raise ValueError("finding evidence must be a strict record")
            evidence = dict(raw_evidence)
            if evidence.get("kind") == "bundle":
                if set(evidence) != {"kind", "uri", "sha256", "selector"}:
                    raise ValueError("finding bundle evidence fields are not exact")
                digest, path = _bundle_uri_parts(evidence["uri"])
                if digest != active:
                    raise ValueError("finding evidence does not reference the active bundle")
                raw_sha = _sha(evidence["sha256"], "finding bundle evidence sha256")
                if manifest.get(path) != raw_sha:
                    raise ValueError("finding evidence path or raw digest does not match the active manifest")
                content = store.read(active, path)
            elif evidence.get("kind") == "git_commit":
                if set(evidence) != {
                    "kind", "repository", "commit", "path", "sha256", "selector",
                }:
                    raise ValueError("finding Git evidence fields are not exact")
                validate_external_evidence([
                    {key: value for key, value in evidence.items() if key != "sha256"}
                ])
                raw_sha = _sha(evidence["sha256"], "finding Git evidence sha256")
                if git_resolver is None:
                    raise ValueError("pinned Git finding evidence has no immutable resolver")
                content = git_resolver(
                    evidence["repository"], evidence["commit"], evidence["path"]
                )
                if not isinstance(content, bytes):
                    raise ValueError("pinned Git resolver must return bytes")
                if compute_raw_sha256(content) != raw_sha:
                    raise ValueError("pinned Git evidence raw digest mismatch")
            else:
                raise ValueError("finding evidence must be active-bundle or pinned-Git content")
            _validate_selector_content(
                evidence["selector"], content, max_line_span=max_line_span
            )
        validated.append(dict(item))
    return validated


def validate_review_output(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schema_version", "attempt_id", "packet_sha256", "bundle_sha256", "snapshot_sha256", "verdict", "coverage", "residual_risks", "findings"}
    value = _record(record, fields, "ReviewOutputV1")
    _nonempty(value["attempt_id"], "attempt_id")
    if value["verdict"] not in {"pass", "fail", "blocked"}: raise ValueError("invalid verdict")
    for field in ("packet_sha256", "bundle_sha256", "snapshot_sha256"): _sha(value[field], field)
    if not all(isinstance(value[x], list) for x in ("coverage", "residual_risks", "findings")): raise ValueError("review output lists are required")
    if not all(isinstance(x, str) and x for x in value["coverage"] + value["residual_risks"]): raise ValueError("coverage and risks must be strings")
    ids = set(); finding_fields = {"id", "severity", "claim", "evidence", "correction", "verification"}
    for item in value["findings"]:
        if not isinstance(item, Mapping) or set(item) != finding_fields: raise ValueError("finding schema is not exact")
        finding = dict(item); identifier = _nonempty(finding["id"], "finding id")
        if identifier in ids or finding["severity"] not in {"critical", "high", "medium", "low", "info"}: raise ValueError("invalid stable finding")
        ids.add(identifier)
        for field in ("claim", "correction", "verification"): _nonempty(finding[field], field)
        validate_external_evidence(finding["evidence"])
    return value


def validate_lens_coverage(
    coverage: Any,
    required: tuple[str, ...] = MANDATORY_REVIEW_LENSES,
) -> list[str]:
    """Require an explicit reviewed or evidence-backed N/A line per lens."""
    if not isinstance(coverage, list):
        raise ValueError("lens coverage must be a list")
    observed: dict[str, str] = {}
    for item in coverage:
        if not isinstance(item, str) or ":" not in item:
            continue
        lens, disposition = (part.strip() for part in item.split(":", 1))
        if lens not in required:
            continue
        if lens in observed:
            raise ValueError(f"duplicate mandatory lens coverage: {lens}")
        lowered = disposition.casefold()
        if lowered.startswith("reviewed - "):
            if not disposition[len("reviewed - "):].strip():
                raise ValueError(f"reviewed lens lacks evidence: {lens}")
        elif lowered.startswith("not_applicable - "):
            if not disposition[len("not_applicable - "):].strip():
                raise ValueError(f"not-applicable lens lacks evidence: {lens}")
        else:
            raise ValueError(f"invalid mandatory lens disposition: {lens}")
        observed[lens] = disposition
    missing = [lens for lens in required if lens not in observed]
    if missing:
        raise ValueError(f"mandatory lens coverage is missing: {', '.join(missing)}")
    return list(coverage)


@dataclass(frozen=True)
class SnapshotLimits:
    max_files: int = 100
    max_bytes: int = 10_000_000
    max_seconds: float = 5.0


class _SnapshotDeadline:
    def __init__(
        self,
        seconds: float,
        *,
        expires_at: float | None,
        clock: Callable[[], float],
        runner: Callable[..., subprocess.CompletedProcess[Any]],
    ) -> None:
        self._clock = clock
        self._runner = runner
        started = clock()
        if isinstance(started, bool) or not isinstance(started, (int, float)) or not math.isfinite(started):
            raise ValueError("snapshot clock is invalid")
        if expires_at is None:
            self._expires_at = started + seconds
        else:
            if (
                isinstance(expires_at, bool)
                or not isinstance(expires_at, (int, float))
                or not math.isfinite(expires_at)
                or expires_at <= started
            ):
                raise ValueError("snapshot limit exceeded")
            self._expires_at = float(expires_at)

    def remaining(self) -> float:
        remaining = self._expires_at - self._clock()
        if not math.isfinite(remaining) or remaining <= 0:
            raise ValueError("snapshot limit exceeded")
        return remaining

    def run_git(self, root: Path, *args: str) -> subprocess.CompletedProcess[Any]:
        try:
            result = self._runner(
                ["git", *args],
                cwd=root,
                capture_output=True,
                check=False,
                timeout=self.remaining(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("snapshot limit exceeded") from exc
        except OSError as exc:
            raise ValueError(f"Git command failed: {exc}") from exc
        self.remaining()
        if not hasattr(result, "returncode") or not hasattr(result, "stdout"):
            raise ValueError("Git runner returned an invalid result")
        return result

    def hash_regular_file(
        self,
        path: Path,
        *,
        expected_identity: tuple[int, int, int, int, int],
        expected_size: int,
    ) -> str:
        self.remaining()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ValueError("could not open declared path") from exc
        try:
            opened = _file_identity(os.fstat(descriptor))
            if opened != expected_identity:
                raise ValueError("declared path changed while snapshotting")
            digest = hashlib.sha256()
            observed = 0
            while True:
                self.remaining()
                chunk = os.read(descriptor, min(1024 * 1024, expected_size - observed + 1))
                if not chunk:
                    break
                observed += len(chunk)
                if observed > expected_size:
                    raise ValueError("declared path changed while snapshotting")
                digest.update(chunk)
            closed_identity = _file_identity(os.fstat(descriptor))
        except OSError as exc:
            raise ValueError("could not read declared path") from exc
        finally:
            os.close(descriptor)
        try:
            current_identity = _file_identity(path.stat(follow_symlinks=False))
        except OSError as exc:
            raise ValueError("declared path changed while snapshotting") from exc
        if (
            observed != expected_size
            or closed_identity != expected_identity
            or current_identity != expected_identity
        ):
            raise ValueError("declared path changed while snapshotting")
        self.remaining()
        return digest.hexdigest()

    def hash_git_blob(
        self,
        root: Path,
        object_id: str,
        *,
        expected_size: int,
    ) -> str:
        self.remaining()
        with tempfile.TemporaryFile() as spool:
            try:
                result = self._runner(
                    ["git", "cat-file", "blob", object_id],
                    cwd=root,
                    stdout=spool,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=self.remaining(),
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError("snapshot limit exceeded") from exc
            except OSError as exc:
                raise ValueError("could not read immutable Git blob") from exc
            self.remaining()
            if not hasattr(result, "returncode") or result.returncode != 0:
                raise ValueError("could not read immutable Git blob")
            if spool.tell() != expected_size:
                raise ValueError("immutable Git blob size changed while snapshotting")
            spool.seek(0)
            digest = hashlib.sha256()
            observed = 0
            while True:
                self.remaining()
                chunk = spool.read(1024 * 1024)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > expected_size:
                    raise ValueError("immutable Git blob size changed while snapshotting")
                digest.update(chunk)
        if observed != expected_size:
            raise ValueError("immutable Git blob size changed while snapshotting")
        return digest.hexdigest()


def _stdout_bytes(result: subprocess.CompletedProcess[Any]) -> bytes:
    if isinstance(result.stdout, bytes):
        return result.stdout
    if isinstance(result.stdout, str):
        return result.stdout.encode("utf-8")
    return b""


def _git_required(deadline: _SnapshotDeadline, root: Path, args: list[str], error: str) -> bytes:
    result = deadline.run_git(root, *args)
    if result.returncode != 0:
        raise ValueError(error)
    return _stdout_bytes(result)


def _git_text(deadline: _SnapshotDeadline, root: Path, args: list[str], error: str) -> str:
    return _git_required(deadline, root, args, error).decode("utf-8", errors="replace")


def _source_entry(digest: str | None, mode: str | None) -> dict[str, Any]:
    return {
        "present": digest is not None,
        "sha256": digest,
        "mode": mode,
    }


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


@dataclass(frozen=True)
class _SourcePlan:
    present: bool
    mode: str | None
    size: int
    kind: str
    value: str | Path | None
    identity: tuple[int, int, int, int, int] | None = None


_ABSENT_SOURCE = _SourcePlan(False, None, 0, "absent", None)


def _git_blob_size(
    deadline: _SnapshotDeadline,
    root: Path,
    object_id: str,
    relative: PurePosixPath,
) -> int:
    raw = _git_required(
        deadline,
        root,
        ["cat-file", "-s", object_id],
        f"could not size Git blob for {relative.as_posix()}",
    ).strip()
    try:
        size = int(raw.decode("ascii", errors="strict"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"malformed Git blob size for {relative.as_posix()}") from exc
    if size < 0:
        raise ValueError(f"malformed Git blob size for {relative.as_posix()}")
    return size


def _tree_source_plan(
    deadline: _SnapshotDeadline,
    root: Path,
    revision: str,
    relative: PurePosixPath,
) -> _SourcePlan:
    listing = _git_required(
        deadline,
        root,
        ["ls-tree", "-z", revision, "--", relative.as_posix()],
        f"could not inspect Git tree source for {relative.as_posix()}",
    )
    rows = [row for row in listing.split(b"\0") if row]
    if not rows:
        return _ABSENT_SOURCE
    if len(rows) != 1 or b"\t" not in rows[0]:
        raise ValueError(f"ambiguous Git tree source for {relative.as_posix()}")
    metadata, _ = rows[0].split(b"\t", 1)
    parts = metadata.split()
    if len(parts) != 3:
        raise ValueError(f"malformed Git tree source for {relative.as_posix()}")
    mode, object_type, object_id = (part.decode("ascii", errors="strict") for part in parts)
    if object_type != "blob" or mode not in {"100644", "100755"}:
        raise ValueError(f"declared Git path is not a regular file: {relative.as_posix()}")
    size = _git_blob_size(deadline, root, object_id, relative)
    return _SourcePlan(True, mode, size, "git", object_id)


def _index_source_plan(
    deadline: _SnapshotDeadline,
    root: Path,
    relative: PurePosixPath,
) -> _SourcePlan:
    listing = _git_required(
        deadline,
        root,
        ["ls-files", "--stage", "-z", "--", relative.as_posix()],
        f"could not inspect Git index source for {relative.as_posix()}",
    )
    rows = [row for row in listing.split(b"\0") if row]
    if not rows:
        return _ABSENT_SOURCE
    if len(rows) != 1 or b"\t" not in rows[0]:
        raise ValueError(f"ambiguous Git index source for {relative.as_posix()}")
    metadata, _ = rows[0].split(b"\t", 1)
    parts = metadata.split()
    if len(parts) != 3:
        raise ValueError(f"malformed Git index source for {relative.as_posix()}")
    mode, object_id, stage = (part.decode("ascii", errors="strict") for part in parts)
    if stage != "0" or mode not in {"100644", "100755"}:
        raise ValueError(f"declared Git index path is unmerged or not a regular file: {relative.as_posix()}")
    size = _git_blob_size(deadline, root, object_id, relative)
    return _SourcePlan(True, mode, size, "git", object_id)


def _worktree_source_plan(
    candidate: Path,
    fallback_mode: str | None,
) -> _SourcePlan:
    if not candidate.exists():
        return _ABSENT_SOURCE
    try:
        metadata = candidate.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValueError("could not inspect declared path") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("declared path is not a regular file")
    if os.name == "nt" and fallback_mode in {"100644", "100755"}:
        mode = fallback_mode
    else:
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
    return _SourcePlan(
        True,
        mode,
        metadata.st_size,
        "worktree",
        candidate,
        _file_identity(metadata),
    )


def _materialize_source(
    deadline: _SnapshotDeadline,
    root: Path,
    plan: _SourcePlan,
) -> dict[str, Any]:
    if not plan.present:
        return _source_entry(None, None)
    if plan.kind == "git":
        digest = deadline.hash_git_blob(root, str(plan.value), expected_size=plan.size)
    elif plan.kind == "worktree" and isinstance(plan.value, Path) and plan.identity is not None:
        digest = deadline.hash_regular_file(
            plan.value,
            expected_identity=plan.identity,
            expected_size=plan.size,
        )
    else:
        raise ValueError("invalid snapshot source plan")
    return _source_entry(digest, plan.mode)


def _sources_differ(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return any(left[field] != right[field] for field in ("present", "sha256", "mode"))


def _derive_git_state(
    base: Mapping[str, Any],
    head: Mapping[str, Any],
    index: Mapping[str, Any],
    worktree: Mapping[str, Any],
) -> dict[str, Any]:
    if not head["present"] and index["present"]:
        staged = "added"
    elif head["present"] and not index["present"]:
        staged = "deleted"
    elif head["present"] and index["present"] and _sources_differ(head, index):
        staged = "modified"
    else:
        staged = "none"

    untracked = not head["present"] and not index["present"] and worktree["present"]
    if index["present"] and not worktree["present"]:
        unstaged = "deleted"
    elif index["present"] and worktree["present"] and _sources_differ(index, worktree):
        unstaged = "modified"
    elif not index["present"] and worktree["present"] and not untracked:
        unstaged = "added"
    else:
        unstaged = "none"

    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "deleted": not worktree["present"] and any(
            source["present"] for source in (base, head, index)
        ),
    }


def _safe_relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or any(token in name for token in ("*", "?", "[", "]")): raise ValueError("path must be explicit")
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts: raise ValueError("path must be bundle-relative")
    return path


def build_git_snapshot(
    root: Path,
    paths: list[str],
    *,
    limits: SnapshotLimits,
    base: str | None = None,
    absolute_deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> dict[str, Any]:
    if (
        isinstance(limits.max_files, bool)
        or not isinstance(limits.max_files, int)
        or isinstance(limits.max_bytes, bool)
        or not isinstance(limits.max_bytes, int)
        or isinstance(limits.max_seconds, bool)
        or not isinstance(limits.max_seconds, (int, float))
        or limits.max_files < 1
        or limits.max_bytes < 1
        or not math.isfinite(limits.max_seconds)
        or limits.max_seconds <= 0
    ):
        raise ValueError("invalid snapshot limits")
    root = Path(root).resolve()
    deadline = _SnapshotDeadline(
        limits.max_seconds,
        expires_at=absolute_deadline,
        clock=clock,
        runner=runner or subprocess.run,
    )
    if not paths or len(paths) > limits.max_files or len(paths) != len(set(paths)): raise ValueError("task paths must be unique and bounded")
    forbidden = {".env", "userprofile.json", "settings.ini", "windhawk.ini", ".git"}
    declared: list[tuple[PurePosixPath, Path]] = []
    for name in paths:
        relative = _safe_relative(name)
        if any(part.lower() in forbidden for part in relative.parts): raise ValueError("credential or runtime-state path rejected")
        candidate = root.joinpath(*relative.parts)
        if candidate.is_symlink() or (
            candidate.exists()
            and (not candidate.is_file() or root not in candidate.resolve().parents)
        ):
            raise ValueError("escaping task path")
        declared.append((relative, candidate))

    git_probe = deadline.run_git(root, "rev-parse", "--is-inside-work-tree")
    is_git = git_probe.returncode == 0 and _stdout_bytes(git_probe).strip() == b"true"
    if is_git:
        head = _git_text(
            deadline,
            root,
            ["rev-parse", "--verify", "--end-of-options", "HEAD^{commit}"],
            "HEAD must resolve to a Git commit",
        ).strip()
        validate_git_object_id(head, "HEAD")
        if base is None:
            raise ValueError("base must be a validated git commit")
        validated_base = _git_text(
            deadline,
            root,
            ["rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"],
            "base must be a validated git commit",
        ).strip()
        validate_git_object_id(validated_base, "base")
        repo = _git_text(
            deadline,
            root,
            ["rev-parse", "--show-toplevel"],
            "could not resolve Git repository identity",
        ).strip()
    else:
        if base is not None:
            raise ValueError("base is only valid for a Git snapshot")
        head = ""
        validated_base = ""
        repo = ""

    planned: list[tuple[PurePosixPath, _SourcePlan, _SourcePlan, _SourcePlan, _SourcePlan]] = []
    total = 0
    for relative, candidate in declared:
        if not candidate.exists() and not is_git:
            raise ValueError("missing task path")
        if is_git:
            base_plan = _tree_source_plan(deadline, root, validated_base, relative)
            head_plan = _tree_source_plan(deadline, root, head, relative)
            index_plan = _index_source_plan(deadline, root, relative)
        else:
            base_plan = head_plan = index_plan = _ABSENT_SOURCE
        fallback_mode = index_plan.mode or head_plan.mode or base_plan.mode
        worktree_plan = _worktree_source_plan(candidate, fallback_mode)
        sources = (base_plan, head_plan, index_plan, worktree_plan)
        if not any(source.present for source in sources):
            raise ValueError("missing declared path")
        total += sum(source.size for source in sources)
        if total > limits.max_bytes:
            raise ValueError("snapshot limit exceeded")
        deadline.remaining()
        planned.append((relative, *sources))

    files: list[dict[str, Any]] = []
    for relative, base_plan, head_plan, index_plan, worktree_plan in planned:
        base_record = _materialize_source(deadline, root, base_plan)
        head_record = _materialize_source(deadline, root, head_plan)
        index_record = _materialize_source(deadline, root, index_plan)
        worktree_record = _materialize_source(deadline, root, worktree_plan)
        state = (
            _derive_git_state(base_record, head_record, index_record, worktree_record)
            if is_git
            else {"staged": "not_applicable", "unstaged": "not_applicable", "untracked": False, "deleted": False}
        )
        files.append(
            {
                "path": relative.as_posix(),
                "base": base_record,
                "head": head_record,
                "index": index_record,
                "worktree": worktree_record,
                "state": state,
            }
        )

    if not is_git:
        manifests = {"content": files}
    else:
        pathspecs = [relative.as_posix() for relative, _ in declared]
        manifests = {
            "head": _git_text(deadline, root, ["ls-tree", "-r", "--full-tree", head, "--", *pathspecs], "could not build HEAD manifest"),
            "index": _git_text(deadline, root, ["ls-files", "--stage", "--", *pathspecs], "could not build index manifest"),
            "worktree": _git_text(deadline, root, ["status", "--porcelain=v1", "--untracked-files=all", "--", *pathspecs], "could not build worktree manifest"),
            "deleted": _git_text(deadline, root, ["diff", "--name-status", "--diff-filter=D", head, "--", *pathspecs], "could not build deletion manifest"),
        }
    snapshot = {"kind": "git" if is_git else "content-manifest", "repo": repo, "base": validated_base, "head": head, "files": files, "manifests": manifests}
    snapshot["snapshot_sha256"] = compute_packet_sha256(snapshot)
    return snapshot


class BundleStore:
    def __init__(self, root: Path) -> None: self.root = Path(root)

    def manifest(self, digest: str) -> dict[str, str]:
        _sha(digest, "bundle_sha256")
        directory = self.root / digest
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("bundle manifest is missing or malformed") from exc
        if (
            not isinstance(manifest, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in manifest.items())
            or compute_packet_sha256(manifest) != digest
        ):
            raise ValueError("bundle manifest digest mismatch")
        actual = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and path.relative_to(directory).as_posix() != "manifest.json"
        }
        if actual != set(manifest):
            raise ValueError("bundle file set does not match manifest")
        return manifest

    def read(self, digest: str, name: str) -> bytes:
        _sha(digest, "bundle_sha256"); relative = _safe_relative(name); directory = self.root / digest
        manifest = self.manifest(digest)
        expected = manifest.get(relative.as_posix())
        if not isinstance(expected, str): raise ValueError("bundle path is absent")
        target = directory.joinpath(*relative.parts).resolve()
        if directory.resolve() not in target.parents: raise ValueError("bundle read escapes")
        data = target.read_bytes()
        if compute_raw_sha256(data) != expected: raise ValueError("immutable bundle content digest mismatch")
        return data


def build_bundle(store: BundleStore, content: Mapping[str, bytes]) -> dict[str, str]:
    if not isinstance(content, Mapping) or not content: raise ValueError("bundle must contain bytes")
    manifest = {}; normalized: list[tuple[PurePosixPath, bytes]] = []
    for name, data in content.items():
        path = _safe_relative(name)
        if path.as_posix() == "manifest.json":
            raise ValueError("root manifest.json is reserved for bundle integrity")
        if not isinstance(data, bytes) or path.as_posix() in manifest: raise ValueError("bundle content is invalid")
        manifest[path.as_posix()] = compute_raw_sha256(data); normalized.append((path, data))
    digest = compute_packet_sha256(manifest); final = store.root / digest
    if final.exists(): raise FileExistsError("immutable bundle already exists")
    store.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=store.root, prefix=".bundle-") as temporary:
        staged = Path(temporary)
        for path, data in normalized:
            target = staged.joinpath(*path.parts); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data); os.chmod(target, 0o444)
        (staged / "manifest.json").write_bytes(canonical_bytes(manifest)); os.chmod(staged / "manifest.json", 0o444)
        os.replace(staged, final)
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        hardened = subprocess.run(
            [
                "icacls", str(final),
                "/inheritance:r",
                "/grant:r",
                f"{user}:(RX)",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
                "*S-1-3-4:(F)",
                "/T", "/C", "/Q",
            ],
            capture_output=True,
            check=False,
        ) if user else None
        if hardened is None or hardened.returncode != 0:
            raise RuntimeError("could not finalize private Windows bundle ACL")
    else:
        for directory, _, names in os.walk(final):
            os.chmod(directory, 0o555)
            for name in names: os.chmod(Path(directory) / name, 0o444)
    return {"bundle_sha256": digest, "bundle_path": f"bundle://{digest}/"}


def validate_disposition_ledger(record: Mapping[str, Any], findings: list[Mapping[str, Any]], *, generation: int) -> dict[str, Any]:
    value = _record(record, {"schema_version", "generation", "dispositions"}, "DispositionLedgerV1"); _integer(value["generation"], "generation")
    if value["generation"] != generation or not isinstance(value["dispositions"], list): raise ValueError("invalid ledger")
    finding_map = {item.get("id"): item for item in findings}; seen = set()
    for entry in value["dispositions"]:
        if not isinstance(entry, Mapping) or entry.get("finding_id") not in finding_map or entry["finding_id"] in seen: raise ValueError("every finding needs one disposition")
        seen.add(entry["finding_id"]); decision = entry.get("decision"); severity = finding_map[entry["finding_id"]].get("severity")
        if decision not in {"accepted", "rejected", "deferred"}: raise ValueError("invalid decision")
        allowed = {"accepted": {"finding_id", "decision", "new_generation"}, "rejected": {"finding_id", "decision", "primary_counterevidence"} if severity in _BLOCKING else {"finding_id", "decision"}, "deferred": {"finding_id", "decision", "owner", "follow_up"}}[decision]
        if set(entry) != allowed: raise ValueError("disposition schema is not exact")
        if decision == "accepted" and entry.get("new_generation") != generation + 1: raise ValueError("acceptance requires new generation")
        if decision == "rejected" and severity in _BLOCKING:
            counterevidence = entry.get("primary_counterevidence")
            if not isinstance(counterevidence, list) or not counterevidence:
                raise ValueError("blocking rejection needs primary immutable counterevidence")
            validate_external_evidence(counterevidence)
        if decision == "deferred" and (severity in _BLOCKING or not entry.get("owner") or not entry.get("follow_up")): raise ValueError("deferral is invalid")
    if seen != set(finding_map): raise ValueError("every finding needs a disposition")
    return value


def validate_review_receipt(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schema_version", "session_id", "task_id", "delivery_id", "generation", "reviewer_agent", "reviewer_type", "reviewer_model", "config_sha256", "attempt_id", "packet_sha256", "bundle_sha256", "snapshot_sha256", "output_sha256", "disposition_sha256", "mutation_epoch"}; value = _record(record, fields, "ReviewReceiptV1")
    for key in {"session_id", "task_id", "delivery_id", "reviewer_agent", "reviewer_type", "reviewer_model", "attempt_id"}: _nonempty(value[key], key)
    for key in {"generation", "mutation_epoch"}:
        if _integer(value[key], key) < 0: raise ValueError("negative receipt integer")
    for key in {"config_sha256", "packet_sha256", "bundle_sha256", "snapshot_sha256", "output_sha256", "disposition_sha256"}: _sha(value[key], key)
    return value


@contextmanager
def _state_lock(path: Path, timeout: float = 5.0):
    lock_path = path.with_suffix(path.suffix + ".lock"); lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0); handle.write(b"0"); handle.flush(); handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline: raise TimeoutError("gate lock timeout")
                time.sleep(0.02)
        try: yield
        finally:
            if os.name == "nt": msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class GateState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None; self.status = "pending_classification"; self.epoch = 0; self.revision = 0; self._fingerprint: str | None = None
        if self.path and self.path.exists(): self._load()

    def _load(self) -> None:
        try: state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise ValueError("corrupt GateStateV1") from exc
        fields = {"schema_version", "status", "epoch", "revision", "fingerprint"}
        if not isinstance(state, dict) or set(state) != fields or state["schema_version"] != 1 or state["status"] not in {"pending_classification", "armed", "reviewing", "receipted", "completed", "stale", "blocked"} or any(isinstance(state[key], bool) or not isinstance(state[key], int) or state[key] < 0 for key in ("epoch", "revision")) or (state["fingerprint"] is not None and not isinstance(state["fingerprint"], str)):
            raise ValueError("invalid GateStateV1")
        self.status = state["status"]; self.epoch = state["epoch"]; self.revision = state["revision"]; self._fingerprint = state["fingerprint"]

    def _save(self) -> None:
        if not self.path: return
        self.path.parent.mkdir(parents=True, exist_ok=True); fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".gate-", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as handle: json.dump({"schema_version": 1, "status": self.status, "epoch": self.epoch, "revision": self.revision, "fingerprint": self._fingerprint}, handle, sort_keys=True); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def transition(self, target: str, *, expected: str) -> None:
        if self.path:
            with _state_lock(self.path): self._transition_locked(target, expected)
            return
        self._transition_locked(target, expected)

    def _transition_locked(self, target: str, expected: str) -> None:
        if self.path and self.path.exists(): self._load()
        allowed = {"pending_classification": {"armed", "blocked"}, "armed": {"reviewing", "blocked"}, "reviewing": {"receipted", "stale", "blocked"}, "receipted": {"completed", "stale", "blocked"}}
        if expected != self.status: raise ValueError("compare-and-swap transition failed")
        if target == self.status: return
        if target not in allowed.get(self.status, set()): raise ValueError("compare-and-swap transition failed")
        self.status = target; self.revision += 1; self._save()

    def bundle_created(self, fingerprint: str = "A") -> None:
        if self.path:
            with _state_lock(self.path):
                if self.path.exists(): self._load()
                self._fingerprint = fingerprint; self.revision += 1; self._save()
        else: self._fingerprint = fingerprint; self.revision += 1; self._save()
    def mutation(self, fingerprint: str) -> None:
        if self.path:
            with _state_lock(self.path):
                if self.path.exists(): self._load()
                self._mutate_locked(fingerprint)
            return
        self._mutate_locked(fingerprint)

    def _mutate_locked(self, fingerprint: str) -> None:
        if self._fingerprint is None: return
        self.epoch += 1; self.revision += 1
        if fingerprint == self._fingerprint: self.status = "stale"
        self._save()
