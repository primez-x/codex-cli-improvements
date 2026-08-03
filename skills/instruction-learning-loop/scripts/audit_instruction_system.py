#!/usr/bin/env python3

"""Read-only instruction-system audit utility."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
KNOWN_LINK_PREFIXES = ("http://", "https://", "mailto:", "tel:", "www.")
SKIP_DIRS = {
    ".angular",
    ".cache",
    ".git",
    ".local-archives",
    ".local-source",
    ".nx",
    ".tmp",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
}

AGENTS_BUDGET_LINES = 120
SKILL_BUDGET_LINES = 200
DUPLICATE_MIN_WORDS = 12


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def in_subtree(root: Path, target: Path) -> bool:
    try:
        root_r = root.resolve().parts
        target_r = target.resolve().parts
        return len(target_r) >= len(root_r) and target_r[: len(root_r)] == root_r
    except Exception:
        return False


def line_stats(text: str) -> Tuple[int, int, int]:
    lines = text.splitlines()
    words = len(re.findall(r"\S+", text))
    return len(lines), words, len(text.encode("utf-8"))


def discover_files(project_root: Path, name: str) -> List[Path]:
    matches = []
    if not project_root.exists():
        return matches
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [directory for directory in dirs if directory.lower() not in SKIP_DIRS]
        if name in files:
            matches.append(Path(root) / name)
    return sorted(matches)


def discover_project_agents(project_root: Path) -> Dict[str, Path]:
    agents = {}
    for p in discover_files(project_root, "AGENTS.md"):
        agents[str(p.relative_to(project_root))] = p
    return agents


def discover_project_skills(project_root: Path) -> Dict[str, Path]:
    skills = {}
    for p in discover_files(project_root / ".agents", "SKILL.md"):
        if p.parent.name == ".system":
            continue
        skills[str(p.parent.relative_to(project_root))] = p.parent
    return skills


def discover_codebase_skills(codex_home: Path) -> Dict[str, Path]:
    skills = {}
    root = codex_home / "skills"
    if not root.exists():
        return skills
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name == "references" or child.name == ".system":
            continue
        md = child / "SKILL.md"
        if md.exists():
            skills[child.name] = child
    return skills


def sparse_tracked_target(source: Path, target: Path) -> bool:
    for candidate in source.parents:
        if not (candidate / ".git").exists():
            continue
        if not in_subtree(candidate, target):
            return False
        relative = target.resolve().relative_to(candidate.resolve()).as_posix()
        result = subprocess.run(
            ["git", "-C", str(candidate), "ls-files", "-v", "--", relative],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.startswith("S ")
    return False


def markdown_links(path: Path, text: str, owning_root: Path) -> Tuple[List[str], List[str]]:
    base = path.parent
    invalid = []
    sparse = []
    for href in LINK_RE.findall(text):
        target = href.strip().split(" ", 1)[0].strip("<>").strip()
        if not target or target.startswith("#") or target.startswith(KNOWN_LINK_PREFIXES):
            continue
        if "://" in target:
            continue
        path_target = target.split("#", 1)[0].split("?", 1)[0]
        if not path_target:
            continue
        if Path(path_target).is_absolute():
            continue
        target_path = (base / path_target).resolve()
        if not target_path.exists():
            if sparse_tracked_target(path, target_path):
                sparse.append(target)
            else:
                invalid.append(target)
            continue
        if not in_subtree(owning_root, target_path):
            invalid.append(target)
            continue
    return sorted(set(invalid)), sorted(set(sparse))


def extract_blocks(text: str) -> List[str]:
    blocks = []
    raw: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            if raw:
                block = " ".join(" ".join(raw).split()).strip().lower()
                raw = []
                if len(block.split()) >= DUPLICATE_MIN_WORDS and len(block) >= 40:
                    blocks.append(block)
            continue
        raw.append(line.strip())
    if raw:
        block = " ".join(" ".join(raw).split()).strip().lower()
        if len(block.split()) >= DUPLICATE_MIN_WORDS and len(block) >= 40:
            blocks.append(block)
    return blocks


@dataclass
class AuditContext:
    quick_validate_script: Path | None
    strict: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: List[dict] = field(default_factory=list)

    def add_metric(self, kind: str, path: Path, text: str) -> None:
        lines, words, bytes_len = line_stats(text)
        self.metrics.append({"kind": kind, "path": str(path), "lines": lines, "words": words, "bytes": bytes_len})
        if kind == "AGENTS" and lines > AGENTS_BUDGET_LINES:
            msg = f"{path}: AGENTS file is {lines} lines (budget {AGENTS_BUDGET_LINES})"
            if self.strict:
                self.errors.append(msg)
            else:
                self.warnings.append(msg)
        if kind == "SKILL" and lines > SKILL_BUDGET_LINES:
            msg = f"{path}: SKILL.md is {lines} lines (budget {SKILL_BUDGET_LINES})"
            if self.strict:
                self.errors.append(msg)
            else:
                self.warnings.append(msg)


def run_quick_validate(skill_dir: Path, context: AuditContext) -> None:
    if not context.quick_validate_script or not context.quick_validate_script.exists():
        context.errors.append(
            f"{skill_dir}: quick_validate.py missing and required for SKILL validation."
        )
        return
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(context.quick_validate_script), str(skill_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        context.errors.append(f"{skill_dir}: quick_validate.py failed: {result.stdout.strip() or result.stderr.strip()}")


def validate_duplicate_blocks(contents: Dict[Path, str], context: AuditContext) -> None:
    seen: Dict[str, List[Path]] = {}
    for path, text in contents.items():
        for block in extract_blocks(text):
            seen.setdefault(block, []).append(path)
    grouped: Dict[Tuple[str, ...], List[str]] = {}
    for block, files in seen.items():
        unique_files = tuple(str(path) for path in sorted(set(files)))
        if len(unique_files) > 1:
            grouped.setdefault(unique_files, []).append(block)
    for files, blocks in sorted(grouped.items()):
        samples = " | ".join(block[:100] for block in sorted(blocks)[:3])
        context.warnings.append(
            f"{len(blocks)} duplicate nontrivial block(s) require canonical-ownership review. "
            f"Files={', '.join(files)}; samples={samples}"
        )


def safe_read(path: Path, context: AuditContext) -> str | None:
    try:
        return read_text(path)
    except OSError as e:
        context.errors.append(f"{path}: failed to read: {e}")
        return None


def build_report(codex_home: Path, project_root: Path | None, strict: bool) -> AuditContext:
    quick_validate = codex_home / "skills/.system/skill-creator/scripts/quick_validate.py"
    context = AuditContext(
        quick_validate_script=quick_validate,
        strict=strict,
    )

    instructions: Dict[str, Path] = {}
    global_agents = codex_home / "AGENTS.md"
    if global_agents.exists():
        instructions["global_AGENTS"] = global_agents

    code_skills = discover_codebase_skills(codex_home)
    project_skills: Dict[str, Path] = {}
    instructions.update({f"skill:{name}": path / "SKILL.md" for name, path in code_skills.items()})

    if project_root:
        project_agents = discover_project_agents(project_root)
        instructions.update({f"project:{name}": path for name, path in project_agents.items()})
        project_skills = discover_project_skills(project_root)
        instructions.update({f"project_skill:{name}": path / "SKILL.md" for name, path in project_skills.items()})

    skill_roots = list(code_skills.values()) + list(project_skills.values())
    for skill_root in skill_roots:
        for reference in sorted(skill_root.rglob("*.md")):
            if reference.name == "SKILL.md" or not reference.is_file():
                continue
            instructions[f"reference:{reference}"] = reference

    if any(str(path).endswith("SKILL.md") for path in instructions.values()) and not quick_validate.exists():
        context.errors.append("quick_validate.py not found for discovered SKILL.md files.")

    contents: Dict[Path, str] = {}
    for label, path in sorted(instructions.items(), key=lambda kv: kv[0]):
        text = safe_read(path, context)
        if text is None:
            continue
        contents[path] = text
        skill_owner = next((root for root in skill_roots if in_subtree(root, path)), None)
        if skill_owner:
            owning_root = skill_owner
        elif path.name == "AGENTS.md" and project_root and in_subtree(project_root, path):
            owning_root = project_root
        elif path.name == "AGENTS.md":
            owning_root = path.parent
        else:
            owning_root = path.parent

        kind = "SKILL" if path.name == "SKILL.md" else "AGENTS" if path.name == "AGENTS.md" else "REFERENCE"
        context.add_metric(kind, path, text)

        if path.name == "SKILL.md":
            run_quick_validate(path.parent, context)
        if path.suffix.lower() == ".md":
            broken_links, sparse_links = markdown_links(path, text, owning_root)
            for link in broken_links:
                context.errors.append(f"{path}: broken/displaced relative markdown link -> {link}")
            for link in sparse_links:
                context.warnings.append(
                    f"{path}: relative link is tracked but not materialized by sparse checkout -> {link}"
                )

    validate_duplicate_blocks(contents, context)
    return context


def print_report(context: AuditContext, json_output: bool = False) -> int:
    payload = {"errors": context.errors, "warnings": context.warnings, "metrics": context.metrics}
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for line in context.metrics:
            print(f"{line['kind']} {line['path']}: {line['lines']} lines, {line['words']} words, {line['bytes']} bytes")
        if context.warnings:
            print("\nWarnings:")
            for warning in context.warnings:
                print(f"- {warning}")
        if context.errors:
            print("\nErrors:")
            for error in context.errors:
                print(f"- {error}")
    return 1 if context.errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit instruction files for AGENTS/skills")
    parser.add_argument("--project-root", default=None, help="Optional project root to include project instructions")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--strict-budgets", action="store_true", help="Promote budget overruns to errors")
    return parser

def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    project_root = Path(args.project_root).resolve() if args.project_root else None
    context = build_report(codex_home, project_root, args.strict_budgets)
    return print_report(context, json_output=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
