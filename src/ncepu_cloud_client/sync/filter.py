from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_RULES = [
    "*.tmp",
    "*.temp",
    "~$*",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".git/",
    ".svn/",
    ".hg/",
    "__pycache__/",
    "node_modules/",
    ".venv/",
    "venv/",
    "*.pyc",
    "*.log",
]


class SyncIgnore:
    """Gitignore-like filter for sync tasks."""

    def __init__(self, rules: list[str] | None = None):
        self.rules = self._normalize_rules(rules or DEFAULT_RULES)

    @classmethod
    def from_file(cls, path: Path, extra_rules: list[str] | None = None) -> "SyncIgnore":
        rules = list(DEFAULT_RULES)
        if path.exists():
            rules.extend(path.read_text(encoding="utf-8").splitlines())
        if extra_rules:
            rules.extend(extra_rules)
        return cls(rules)

    def should_ignore(self, path: Path | str, root: Path | None = None) -> bool:
        candidate = Path(path)
        rel = candidate
        if root is not None:
            try:
                rel = candidate.relative_to(root)
            except ValueError:
                rel = candidate
        rel_text = rel.as_posix()
        name = candidate.name
        parts = set(rel.parts)
        for rule in self.rules:
            if rule.endswith("/"):
                dirname = rule.rstrip("/")
                if dirname in parts or rel_text.startswith(dirname + "/"):
                    return True
                continue
            if fnmatch.fnmatch(name, rule) or fnmatch.fnmatch(rel_text, rule):
                return True
        return False

    @staticmethod
    def _normalize_rules(rules: list[str]) -> list[str]:
        normalized: list[str] = []
        for rule in rules:
            clean = rule.strip()
            if not clean or clean.startswith("#"):
                continue
            normalized.append(clean.replace("\\", "/"))
        return normalized

