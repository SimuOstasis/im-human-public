# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""im-human doc pages: Obsidian [[wikilinks]] -> relative Markdown links, in place.

Stdlib-only (argparse, re, pathlib, urllib.parse) CLI used by
`.github/workflows/publish-public.yml`'s `publish` job, run against the
ephemeral CI checkout of `im-human` (never the developer's working copy)
BEFORE `export_public_snapshot.py` mirrors it into `im-human-public`.
GitHub's regular file/Code view does not render Obsidian `[[...]]` syntax —
this rewrites every wikilink into the equivalent relative Markdown link so
the public repo's Code tab renders correctly, while the source vault keeps
storing links in native Obsidian form (CLAUDE.md, "Ссылки" convention).

Rewrite rules (mirror image of `export_wiki.py`'s Gollum-facing rewrite):
  - `[[Page]]` / `[[Page|text]]` / `[[Page\\|text]]` (table-cell-escaped
    pipe) where `Page` resolves to one of the exported doc files becomes
    `[text](relative/encoded/path.md)` (or `[Page](...)` if no display
    text was given).
  - `[[folder/path/]]` / `[[folder/path/\\|text]]` (a category-folder
    link) becomes a relative link to that folder.
  - `[[name.py|relative/path.py]]` (or any other real repo file, e.g.
    `LICENSE.txt`) becomes a relative Markdown link to that file.
  - `[[mortality:...]]` cross-vault KB citations and `09 - Templates/`
    `{{...}}` placeholders are left untouched — this script only matches
    genuine `[[...]]` wikilink syntax, and a mortality: target never
    resolves to a real file, so it naturally falls through unresolved
    and is left as-is (matching the info-only intent of that notation).
  - Anything already a standard `[text](url)` link, or `![...]` image
    embed, is left untouched.

Usage:
    python tools/convert_links_for_code.py --source <repo-checkout-dir>
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from export_public_snapshot import is_excluded

DOC_DIRS = [
    "01 - Human Profiles", "02 - Biomarkers", "03 - Substances",
    "04 - Interactions", "05 - Simulation", "06 - Engine",
    "07 - Analysis", "08 - Index", "09 - Templates",
]
# Folders that are valid [[folder/]] link targets but contain no doc pages
# of their own (nothing to scan for cross-links) — "00 - Inbox/" is empty
# except a .gitkeep placeholder.
EXTRA_FOLDER_DIRS = ["00 - Inbox"]
ROOT_DOCS = ["HOME.md", "MILESTONES.md", "README.md", "log.md"]
EXTRA_DOCS = [".neo4j/README.md", "src/README.md"]

# `[[target]]` or `[[target\|display]]` / `[[target|display]]`. The
# backslash before `|` is CLAUDE.md's table-cell escaping convention — it
# only matters for source rendering, not for parsing intent here, so it is
# accepted and stripped uniformly.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\\?\|([^\[\]]+?))?\]\]")


def discover_doc_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for d in DOC_DIRS:
        files.extend(sorted((source / d).rglob("*.md")))
    for name in ROOT_DOCS:
        files.append(source / name)
    for rel in EXTRA_DOCS:
        files.append(source / rel)
    return [f.resolve() for f in files]


def build_basename_map(doc_files: list[Path], source: Path) -> dict[str, Path]:
    """Map each doc file's Gollum-style page name (bare stem, or a
    collision-qualified relative path — see export_wiki.py) back to its
    real path, so `[[PageName]]` resolves the same way in both directions."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in doc_files:
        groups[f.stem].append(f)

    basename_map: dict[str, Path] = {}
    for stem, group in groups.items():
        if len(group) == 1:
            basename_map[stem] = group[0]
            continue
        group_sorted = sorted(group, key=lambda p: len(str(p.relative_to(source))))
        basename_map[stem] = group_sorted[0]
        for f in group_sorted[1:]:
            rel = f.relative_to(source).with_suffix("")
            basename_map[str(rel).replace("\\", "/")] = f
    return basename_map


def build_folder_map(source: Path) -> dict[str, Path]:
    folder_map: dict[str, Path] = {}
    for d in DOC_DIRS + EXTRA_FOLDER_DIRS:
        folder_map[d + "/"] = source / d
        for sub in (source / d).iterdir():
            if sub.is_dir():
                folder_map[f"{d}/{sub.name}/"] = sub
    return folder_map


def build_repo_file_index(source: Path) -> dict[str, Path]:
    """Basename -> path for every git-tracked file, mirroring how Obsidian
    resolves a bare `[[filename.ext]]` wikilink by unique name anywhere in
    the vault (used as the fallback for non-doc targets like `.py` source
    files or `LICENSE.txt`, which the doc/folder maps do not cover)."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=str(source), capture_output=True, text=True, check=True,
    )
    index: dict[str, Path] = {}
    for rel in result.stdout.splitlines():
        if not rel.strip():
            continue
        name = rel.rsplit("/", 1)[-1]
        index.setdefault(name, source / rel)
    return index


def _encode_rel(rel: str) -> str:
    return "/".join(quote(part, safe="().,'") for part in rel.split("/"))


def rewrite_file(f: Path, source: Path, basename_map: dict[str, Path],
                  folder_map: dict[str, Path], repo_file_index: dict[str, Path]) -> str:
    text = f.read_text(encoding="utf-8")
    out_lines = []
    for line in text.split("\n"):
        def repl(m: re.Match[str]) -> str:
            target, display = m.group(1), m.group(2)
            if target.startswith("mortality:"):
                return m.group(0)
            if "{{" in target or "}}" in target:
                return m.group(0)

            if target.endswith("/"):
                if target not in folder_map:
                    return m.group(0)
                dest = folder_map[target]
                rel = _rel(dest, f.parent)
                if not rel.endswith("/"):
                    rel += "/"
                disp = display if display else dest.name
                return f"[{disp}]({_encode_rel(rel)})"

            key = target.rstrip("/").split("/")[-1]
            disp = display if display else key

            candidate = basename_map.get(target) or basename_map.get(key)
            if candidate is not None:
                rel = _rel(candidate, f.parent)
                return f"[{disp}]({_encode_rel(rel)})"

            # Fallback: any other git-tracked file (source code, LICENSE.txt, ...).
            candidate = repo_file_index.get(key)
            if candidate is None:
                return m.group(0)  # unresolved (e.g. mistyped) — leave visible, not silently guessed

            rel_to_source = candidate.relative_to(source).as_posix()
            if is_excluded(rel_to_source):
                # Target never reaches the public mirror (e.g. CLAUDE.md) —
                # a link to it would 404 there; fall back to plain text.
                return disp
            rel = _rel(candidate, f.parent)
            return f"[{disp}]({_encode_rel(rel)})"

        out_lines.append(_WIKILINK_RE.sub(repl, line))
    return "\n".join(out_lines)


def _rel(target: Path, from_dir: Path) -> str:
    import os
    return os.path.relpath(target, from_dir).replace("\\", "/")


def convert(source: Path) -> int:
    doc_files = discover_doc_files(source)
    basename_map = build_basename_map(doc_files, source)
    folder_map = build_folder_map(source)
    repo_file_index = build_repo_file_index(source)

    changed = 0
    for f in doc_files:
        original = f.read_text(encoding="utf-8")
        rewritten = rewrite_file(f, source, basename_map, folder_map, repo_file_index)
        if rewritten != original:
            f.write_text(rewritten, encoding="utf-8")
            changed += 1
    return changed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite Obsidian [[wikilinks]] in im-human's doc pages into "
            "relative Markdown links, in place, for GitHub Code rendering."
        )
    )
    parser.add_argument(
        "--source", required=True, type=Path,
        help="Path to the im-human repo checkout to rewrite in place",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    changed = convert(args.source.resolve())
    print(f"[convert-links-for-code] files_rewritten={changed}")


if __name__ == "__main__":
    main()
