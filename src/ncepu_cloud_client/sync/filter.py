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
    """同步任务使用的类 gitignore 过滤器。

    过滤器用于排除临时文件、版本控制目录、虚拟环境和缓存文件。
    这些文件频繁变化且通常没有同步价值，如果不排除，会放大同步队列压力并产生噪声。
    """

    def __init__(self, rules: list[str] | None = None):
        self.rules = self._normalize_rules(rules or DEFAULT_RULES)

    @classmethod
    def from_file(cls, path: Path, extra_rules: list[str] | None = None) -> "SyncIgnore":
        # 规则是叠加关系：内置规则过滤常见干扰文件，
        # .syncignore 处理单个同步目录策略，设置页规则作为全局补充。
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
                # 规则匹配优先使用相对于同步根目录的路径，
                # 这样用户可以写出 node_modules/、build/*.tmp 这类目录内规则。
                rel = candidate.relative_to(root)
            except ValueError:
                # 如果传入路径不在同步根目录下，就退回完整路径进行保守匹配。
                rel = candidate
        rel_text = rel.as_posix()
        name = candidate.name
        parts = set(rel.parts)
        for rule in self.rules:
            if rule.endswith("/"):
                # 目录规则既匹配目录自身，也匹配目录下所有内容，行为接近 gitignore。
                dirname = rule.rstrip("/")
                if dirname in parts or rel_text.startswith(dirname + "/"):
                    return True
                continue
            if fnmatch.fnmatch(name, rule) or fnmatch.fnmatch(rel_text, rule):
                # 同时匹配文件名和相对路径：*.tmp 适合文件名，
                # docs/*.log 这类规则则需要完整相对路径。
                return True
        return False

    @staticmethod
    def _normalize_rules(rules: list[str]) -> list[str]:
        normalized: list[str] = []
        for rule in rules:
            clean = rule.strip()
            if not clean or clean.startswith("#"):
                continue
            # Windows 使用反斜杠，gitignore 风格更接近正斜杠；
            # 统一为 / 后，规则在不同平台上表现更一致。
            normalized.append(clean.replace("\\", "/"))
        return normalized
