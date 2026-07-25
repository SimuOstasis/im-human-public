# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Regression gate for Phase 14's public-snapshot exporter (WR-04, closes the
gap CR-01 found: no test exercised `is_excluded()`, `mirror()`, or
`assert_no_leak()` before this).

Placed under `src/tests/` (not `tools/`) so it is picked up by the existing
`pytest src/tests/ -v` CI invocation (see `.github/workflows/ci.yml` and
`README.md`'s test command), rather than a sibling location that would never
actually run in CI.

Loads `tools/export_public_snapshot.py` via importlib (the file is not part of
a package) — same pattern as `test_mortality_slug.py::_load_ingest_cross_links`
for `.neo4j/ingest_cross_links.py`.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

# Root of the vault (2 levels up: tests -> src -> vault root)
_PROJECT_ROOT = Path(__file__).parents[2]


def _load_export_public_snapshot():
    module_path = _PROJECT_ROOT / "tools" / "export_public_snapshot.py"
    spec = importlib.util.spec_from_file_location("export_public_snapshot", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_track_all(root: Path) -> None:
    """Init a git repo at `root` and stage every file so `git ls-files`
    (what the module's `enumerate_tracked_files` shells out to) sees them.
    No commit needed — `git ls-files` reads the index, not HEAD."""
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)


# ── is_excluded() ────────────────────────────────────────────────────────────


def test_is_excluded_root_level_claude_and_agents_md():
    m = _load_export_public_snapshot()
    assert m.is_excluded("CLAUDE.md") is True
    assert m.is_excluded("AGENTS.md") is True


def test_is_excluded_nested_claude_and_agents_md():
    """CR-01 regression: nested occurrences must be excluded too, not just root."""
    m = _load_export_public_snapshot()
    assert m.is_excluded("nested/dir/CLAUDE.md") is True
    assert m.is_excluded(".claude/AGENTS.md") is True
    assert m.is_excluded(".claude/skills/foo/AGENTS.md") is True


def test_is_excluded_planning_prefix():
    m = _load_export_public_snapshot()
    assert m.is_excluded(".planning/x/y.md") is True
    assert m.is_excluded(".planning/STATE.md") is True


def test_is_excluded_internal_glob():
    m = _load_export_public_snapshot()
    assert m.is_excluded("foo_internal_bar.md") is True
    assert m.is_excluded("log_internal.md") is True
    assert m.is_excluded("some/dir/log_internal.md") is True


def test_is_excluded_ordinary_files_not_excluded():
    m = _load_export_public_snapshot()
    assert m.is_excluded("README.md") is False
    assert m.is_excluded("src/tests/test_simulation.py") is False
    assert m.is_excluded("tools/export_public_snapshot.py") is False


# ── mirror() ─────────────────────────────────────────────────────────────────


def test_mirror_includes_ordinary_and_excludes_planning_claude_agents(tmp_path):
    m = _load_export_public_snapshot()
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()

    (source / "README.md").write_text("hello", encoding="utf-8")
    (source / "CLAUDE.md").write_text("secret rules", encoding="utf-8")
    (source / "nested").mkdir()
    (source / "nested" / "AGENTS.md").write_text("secret rules 2", encoding="utf-8")
    (source / ".planning").mkdir()
    (source / ".planning" / "STATE.md").write_text("planning", encoding="utf-8")
    (source / "log_internal.md").write_text("internal log", encoding="utf-8")
    _git_track_all(source)

    counts = m.mirror(source, dest)

    assert (dest / "README.md").exists()
    assert not (dest / "CLAUDE.md").exists()
    assert not (dest / "nested" / "AGENTS.md").exists()
    assert not (dest / ".planning" / "STATE.md").exists()
    assert not (dest / "log_internal.md").exists()
    assert counts["included"] == 1
    assert counts["excluded"] == 4


def test_mirror_deletes_stale_dest_orphans(tmp_path):
    """mirror() is a sync, not an additive copy — stale dest files must go."""
    m = _load_export_public_snapshot()
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()

    (source / "keep.md").write_text("keep", encoding="utf-8")
    _git_track_all(source)

    # Orphan file that no longer exists in source's tracked set.
    (dest / "stale.md").write_text("stale", encoding="utf-8")

    counts = m.mirror(source, dest)

    assert (dest / "keep.md").exists()
    assert not (dest / "stale.md").exists()
    assert counts["deleted"] == 1


def test_mirror_rejects_tracked_symlinks(tmp_path, monkeypatch):
    """WR-05 regression: shutil.copy2 follows symlinks by default and would
    copy the dereferenced target's contents, bypassing path-based exclusion.
    Real symlinks can't be reliably created in this Windows CI environment
    without elevated privileges, so simulate one via monkeypatched
    Path.is_symlink() instead — this exercises the same code path mirror()
    actually checks."""
    m = _load_export_public_snapshot()
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()

    (source / "linkish.txt").write_text("payload", encoding="utf-8")
    _git_track_all(source)

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if self.name == "linkish.txt":
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(SystemExit):
        m.mirror(source, dest)


# ── assert_no_leak() ─────────────────────────────────────────────────────────


def test_assert_no_leak_raises_when_excluded_path_present(tmp_path):
    m = _load_export_public_snapshot()
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "CLAUDE.md").write_text("leaked", encoding="utf-8")

    with pytest.raises(SystemExit):
        m.assert_no_leak(dest)


def test_assert_no_leak_passes_when_clean(tmp_path):
    m = _load_export_public_snapshot()
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "README.md").write_text("hello", encoding="utf-8")

    m.assert_no_leak(dest)  # must not raise
