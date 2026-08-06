"""Canonical, immutable review-packet envelopes and stage-liveness validation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


DEFAULT_STATUS_CHECK_MINUTES = 15
DEFAULT_UNRESPONSIVE_GRACE_MINUTES = 3
MIN_STATUS_CHECK_MINUTES = 1
MAX_STATUS_CHECK_MINUTES = 45
MIN_UNRESPONSIVE_GRACE_MINUTES = 1
MAX_UNRESPONSIVE_GRACE_MINUTES = 5
TERMINAL_PROFILES = frozenset({"spark_scanner", "luna_scanner", "sol_advisor"})
# The adversarial gate's sol_reviewer identity is not a plan-review route.
REJECTED_PROFILES = frozenset({"sol_reviewer"})
ALLOWED_PROFILES = TERMINAL_PROFILES

_MISSING = object()
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED_PAYLOAD_FIELDS = (
    "packet_id",
    "request",
    "evidence",
    "candidate",
    "reviewer_lens",
    "reviewer_profile",
    "status_check_minutes",
    "unresponsive_grace_minutes",
)
_RETIRED_PAYLOAD_FIELDS = frozenset({"deadline_minutes", "grace_minutes", "descendant_budget"})
_ALLOWED_PAYLOAD_FIELDS = frozenset(_REQUIRED_PAYLOAD_FIELDS)


class _FrozenDict(dict[str, Any]):
    """A JSON-compatible recursively immutable dictionary."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen packet payload is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        return {
            copy.deepcopy(key, memo): copy.deepcopy(value, memo)
            for key, value in self.items()
        }


class _FrozenList(list[Any]):
    """A JSON-compatible recursively immutable list."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen packet payload is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(item, memo) for item in self]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = _FrozenDict()
        for key, item in value.items():
            dict.__setitem__(frozen, key, _freeze(item))
        return frozen
    if isinstance(value, list):
        frozen = _FrozenList()
        list.extend(frozen, (_freeze(item) for item in value))
        return frozen
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _validate_integer(name: str, value: Any, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")
    if not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")
    return value


def validate_liveness(
    status_check_minutes: Any = _MISSING,
    unresponsive_grace_minutes: Any = _MISSING,
    *,
    reviewer_profile: Any = _MISSING,
    use_defaults: bool = True,
) -> dict[str, int]:
    """Validate finite liveness intervals against the dispatcher's profile."""

    if reviewer_profile is _MISSING:
        raise ValueError("reviewer_profile is required before dispatch")
    if isinstance(reviewer_profile, str) and reviewer_profile in REJECTED_PROFILES:
        raise ValueError(f"{reviewer_profile} is not a plan-review routing profile")
    if not isinstance(reviewer_profile, str) or reviewer_profile not in ALLOWED_PROFILES:
        raise ValueError(f"reviewer_profile is not an allowed planning profile: {reviewer_profile!r}")
    if status_check_minutes is _MISSING:
        if not use_defaults:
            raise ValueError("status_check_minutes is required before dispatch")
        status_check_minutes = DEFAULT_STATUS_CHECK_MINUTES
    if unresponsive_grace_minutes is _MISSING:
        if not use_defaults:
            raise ValueError("unresponsive_grace_minutes is required before dispatch")
        unresponsive_grace_minutes = DEFAULT_UNRESPONSIVE_GRACE_MINUTES
    intervals = {
        "status_check_minutes": _validate_integer(
            "status_check_minutes",
            status_check_minutes,
            MIN_STATUS_CHECK_MINUTES,
            MAX_STATUS_CHECK_MINUTES,
        ),
        "unresponsive_grace_minutes": _validate_integer(
            "unresponsive_grace_minutes",
            unresponsive_grace_minutes,
            MIN_UNRESPONSIVE_GRACE_MINUTES,
            MAX_UNRESPONSIVE_GRACE_MINUTES,
        ),
    }
    return intervals


def canonical_bytes(value: Any) -> bytes:
    """Serialize JSON using the packet's canonical UTF-8 representation."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value cannot be represented as canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def compute_packet_sha256(packet_payload: Mapping[str, Any]) -> str:
    """Return the lowercase SHA-256 digest of canonical packet payload bytes."""

    return hashlib.sha256(canonical_bytes(packet_payload)).hexdigest()


def compute_raw_sha256(value: bytes) -> str:
    """Return the lowercase SHA-256 of exact, uncanonicalized byte content."""
    if not isinstance(value, bytes):
        raise ValueError("raw SHA-256 input must be bytes")
    return hashlib.sha256(value).hexdigest()


def _validate_payload(packet_payload: Mapping[str, Any], *, apply_defaults: bool) -> dict[str, Any]:
    if not isinstance(packet_payload, Mapping):
        raise ValueError("packet_payload must be a mapping")
    payload = copy.deepcopy(dict(packet_payload))
    retired = set(payload).intersection(_RETIRED_PAYLOAD_FIELDS)
    if retired:
        raise ValueError(f"retired packet fields are rejected: {', '.join(sorted(retired))}")
    if "packet_sha256" in payload:
        raise ValueError("packet_sha256 belongs to the envelope, not packet_payload")
    unknown = set(payload).difference(_ALLOWED_PAYLOAD_FIELDS)
    if unknown:
        raise ValueError(f"packet_payload contains unknown fields: {', '.join(sorted(unknown))}")
    for field in _REQUIRED_PAYLOAD_FIELDS[:5]:
        if field not in payload:
            raise ValueError(f"packet_payload is missing {field}")
    if not isinstance(payload["packet_id"], str) or not payload["packet_id"].strip():
        raise ValueError("packet_id must be a nonempty string")
    if not isinstance(payload["reviewer_lens"], str) or not payload["reviewer_lens"].strip():
        raise ValueError("reviewer_lens must be a nonempty string")
    if "reviewer_profile" not in payload:
        raise ValueError("packet_payload is missing reviewer_profile")
    payload.update(
        validate_liveness(
            payload.get("status_check_minutes", _MISSING),
            payload.get("unresponsive_grace_minutes", _MISSING),
            reviewer_profile=payload["reviewer_profile"],
            use_defaults=apply_defaults,
        )
    )
    canonical_bytes(payload)
    return payload


def build_packet_envelope(packet_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build a recursively immutable envelope with a frozen declared digest."""

    payload = _validate_payload(packet_payload, apply_defaults=True)
    frozen_payload = _freeze(payload)
    digest = compute_packet_sha256(frozen_payload)
    return MappingProxyType(
        {"packet_payload": frozen_payload, "packet_sha256": digest}
    )


def _validate_digest(name: str, digest: Any) -> str:
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 digest")
    return digest


def verify_packet_envelope(
    envelope: Mapping[str, Any], *, observed_packet_sha256: str | None = None
) -> str:
    """Recompute and verify the frozen, declared, and optional observed digest."""

    if not isinstance(envelope, Mapping):
        raise ValueError("envelope must be a mapping")
    if set(envelope) != {"packet_payload", "packet_sha256"}:
        raise ValueError("envelope must contain only packet_payload and packet_sha256")
    payload = _validate_payload(envelope["packet_payload"], apply_defaults=False)
    declared = _validate_digest("packet_sha256", envelope["packet_sha256"])
    observed = compute_packet_sha256(payload)
    if observed != declared:
        raise ValueError("packet payload does not match declared packet_sha256")
    if observed_packet_sha256 is not None:
        _validate_digest("observed_packet_sha256", observed_packet_sha256)
        if observed_packet_sha256 != observed:
            raise ValueError("reviewer observed_packet_sha256 does not match frozen packet")
    return observed


def verify_reviewer_output(
    envelope: Mapping[str, Any], reviewer_output: Mapping[str, Any]
) -> str:
    """Verify a reviewer response's independently recomputed packet digest."""

    if not isinstance(reviewer_output, Mapping):
        raise ValueError("reviewer output must be a mapping")
    if "observed_packet_sha256" not in reviewer_output:
        raise ValueError("reviewer output must include observed_packet_sha256")
    return verify_packet_envelope(
        envelope, observed_packet_sha256=reviewer_output["observed_packet_sha256"]
    )


# Explicit aliases keep the contract discoverable to callers using either verb.
hash_packet_payload = compute_packet_sha256
verify_packet = verify_packet_envelope
