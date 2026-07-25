# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""im-human -> im-human-public: filtered, delete-then-copy mirror export (D-06..D-09).

Stdlib-only (argparse, subprocess, pathlib, shutil, fnmatch) CLI used by
`.github/workflows/publish-public.yml` on every push to `main`. Enumerates the
SOURCE repo's tracked file set via `git ls-files` (never a recursive filesystem
walk, so gitignored secrets such as `.neo4j/.env`, `log_internal.md`, and
`venv/` cannot leak by construction), excludes `.planning/`, `CLAUDE.md`,
`AGENTS.md`, and any `*_internal*` path (the exclusion set proven in
09.1-06-SUMMARY.md, D-09), then reconciles DEST's working tree to exactly that
inclusion set: deletes every file under DEST except `.git/` and files that are
still in the inclusion set, then copies each included file over. This is a
mirror/sync, not an additive copy, so files renamed/removed upstream do not
linger as orphans in the public repo (RESEARCH.md Anti-Pattern 3 / T-14-04-Io).

This script never touches git history: it does not run `git init`,
`git subtree`, or `git-filter-repo`. DEST's `.git/` (and thus its accumulating
commit history) is owned entirely by the caller (the workflow's `actions/checkout`
step) — this script only rewrites DEST's working-tree files.

Usage:
    python tools/export_public_snapshot.py --source <source-repo-dir> --dest <dest-checkout-dir>
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

# Exclusion set inherited unchanged from 09.1-06-SUMMARY.md (D-09).
_EXCLUDED_EXACT_BASENAMES = {"CLAUDE.md", "AGENTS.md"}
_EXCLUDED_PREFIX = ".planning/"
_EXCLUDED_GLOB = "*_internal*"


def is_excluded(rel_posix_path: str) -> bool:
    """True if `rel_posix_path` (forward-slash-separated, repo-relative) must
    never cross into the public export."""
    basename = rel_posix_path.rsplit("/", 1)[-1]
    if basename in _EXCLUDED_EXACT_BASENAMES:
        return True
    if rel_posix_path.startswith(_EXCLUDED_PREFIX):
        return True
    if fnmatch.fnmatch(basename, _EXCLUDED_GLOB):
        return True
    if fnmatch.fnmatch(rel_posix_path, _EXCLUDED_GLOB):
        return True
    return False


def enumerate_tracked_files(source: Path) -> list[str]:
    """Enumerate SOURCE's tracked file set via `git ls-files` — the sole
    trusted enumeration source (never a filesystem walk, per T-14-04-I)."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(source),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def gather_existing_dest_files(dest: Path) -> list[str]:
    """List all files currently under DEST, excluding `.git/`, as
    forward-slash-separated paths relative to DEST."""
    files: list[str] = []
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(dest)
        if rel.parts and rel.parts[0] == ".git":
            continue
        files.append(rel.as_posix())
    return files


def prune_empty_dirs(dest: Path) -> None:
    """Remove now-empty directories left behind by deletions, skipping `.git/`."""
    for path in sorted(dest.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_dir():
            continue
        if path.name == ".git" and path.parent == dest:
            continue
        if ".git" in path.relative_to(dest).parts:
            continue
        try:
            path.rmdir()
        except OSError:
            pass  # not empty — leave it


def mirror(source: Path, dest: Path) -> dict[str, int]:
    all_tracked = enumerate_tracked_files(source)
    included = [p for p in all_tracked if not is_excluded(p)]
    excluded = [p for p in all_tracked if is_excluded(p)]
    included_set = set(included)

    dest.mkdir(parents=True, exist_ok=True)

    # 1. Delete every existing dest file NOT in the current inclusion set
    #    (mirror/sync, not additive copy — closes the stale-orphan gap).
    existing = gather_existing_dest_files(dest)
    deleted = 0
    for rel in existing:
        if rel not in included_set:
            (dest / rel).unlink()
            deleted += 1
    prune_empty_dirs(dest)

    # 2. Copy every included file from source to dest, creating parent dirs.
    #    Reject symlinks outright (WR-05 fix): shutil.copy2 follows symlinks
    #    by default and copies the *dereferenced* target's contents, so a
    #    tracked symlink whose own path passes is_excluded() cleanly could
    #    still smuggle an excluded file's contents (e.g. log_internal.md,
    #    .neo4j/.env) into the public mirror — is_excluded() never inspects
    #    the link target. No symlink is tracked in this repo today, so
    #    failing closed here costs nothing and closes the bypass by
    #    construction rather than trying to validate targets case-by-case.
    written = 0
    for rel in included:
        src_file = source / rel
        if src_file.is_symlink():
            raise SystemExit(
                f"Refusing to mirror symlink '{rel}': shutil.copy2 would "
                "follow it and copy its dereferenced target's contents, "
                "bypassing path-based exclusion. Untrack or replace with a "
                "regular file."
            )
        dest_file = dest / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        written += 1

    return {
        "enumerated": len(all_tracked),
        "included": len(included),
        "excluded": len(excluded),
        "written": written,
        "deleted": deleted,
    }


def assert_no_leak(dest: Path) -> None:
    """Defense-in-depth: re-scan DEST's final file set and refuse to exit
    cleanly if any excluded pattern leaked through (T-14-04-I)."""
    leaked = [rel for rel in gather_existing_dest_files(dest) if is_excluded(rel)]
    if leaked:
        print(
            "LEAK DETECTED — excluded paths present in dest after mirror:",
            file=sys.stderr,
        )
        for rel in leaked:
            print(f"  {rel}", file=sys.stderr)
        raise SystemExit(1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mirror a filtered snapshot of a git-tracked source repo into a "
            "destination checkout, excluding .planning/, CLAUDE.md, AGENTS.md, "
            "and any *_internal* path (D-06..D-09)."
        )
    )
    parser.add_argument(
        "--source", required=True, type=Path,
        help="Path to the source repo checkout (must be a git repository)",
    )
    parser.add_argument(
        "--dest", required=True, type=Path,
        help="Path to the destination checkout to mirror the filtered snapshot into",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    source = args.source.resolve()
    dest = args.dest.resolve()

    counts = mirror(source, dest)
    assert_no_leak(dest)

    print(
        "[export] enumerated={enumerated} included={included} excluded={excluded} "
        "written={written} deleted={deleted}".format(**counts)
    )


if __name__ == "__main__":
    main()
