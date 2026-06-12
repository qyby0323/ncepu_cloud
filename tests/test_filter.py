from pathlib import Path

from ncepu_cloud_client.sync.filter import SyncIgnore


def test_default_filter_ignores_temp_and_cache_dirs():
    ignore = SyncIgnore()
    root = Path("project")
    assert ignore.should_ignore(root / "a.tmp", root)
    assert ignore.should_ignore(root / "node_modules" / "pkg" / "index.js", root)
    assert ignore.should_ignore(root / ".git" / "config", root)
    assert not ignore.should_ignore(root / "src" / "main.py", root)


def test_syncignore_file_supports_comments_and_globs(tmp_path):
    rules = tmp_path / ".syncignore"
    rules.write_text("# comment\nbuild/\n*.bak\n\n", encoding="utf-8")
    ignore = SyncIgnore.from_file(rules)
    assert ignore.should_ignore(tmp_path / "build" / "x.txt", tmp_path)
    assert ignore.should_ignore(tmp_path / "note.bak", tmp_path)
    assert not ignore.should_ignore(tmp_path / "note.md", tmp_path)


def test_syncignore_merges_extra_rules(tmp_path):
    ignore = SyncIgnore.from_file(tmp_path / ".syncignore", extra_rules=["cache/", "*.secret"])
    assert ignore.should_ignore(tmp_path / "cache" / "data.bin", tmp_path)
    assert ignore.should_ignore(tmp_path / "token.secret", tmp_path)
    assert not ignore.should_ignore(tmp_path / "token.txt", tmp_path)
