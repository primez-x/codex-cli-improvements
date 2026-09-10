"""Pure, optional identity helpers for direct depth-1 delegation metadata."""

import re
import unicodedata

ROSTER_STATUSES = frozenset(("active", "completed", "failed", "terminated"))


def normalize_task_slug(purpose: str) -> str:
    normalized = unicodedata.normalize("NFKD", purpose).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    if not normalized:
        raise ValueError("purpose must contain an alphanumeric character")
    return normalized


def task_name(profile: str, purpose: str, depth: int = 1) -> str:
    if depth != 1:
        raise ValueError("identity metadata is limited to direct depth-1 leaves")
    profile_slug = normalize_task_slug(profile)
    return f"d1_{profile_slug}_{normalize_task_slug(purpose)}"


def display_label(profile: str, model_family: str, effort: str, role: str, purpose: str) -> str:
    return f"D1 · {model_family}/{effort} · {role} · {purpose.strip()}"


def roster_delta(canonical_task_path: str, name: str, label: str, status: str) -> dict[str, str]:
    if status not in ROSTER_STATUSES:
        raise ValueError(f"unsupported roster status: {status}")
    return {
        "canonical_task_path": canonical_task_path,
        "task_name": name,
        "display_label": label,
        "status": status,
    }
