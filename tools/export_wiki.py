# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""im-human -> im-human-public GitHub Wiki: doc-only export, Gollum-native.

Stdlib-only (argparse, re, shutil, pathlib, urllib.parse) CLI used by
`.github/workflows/publish-public.yml` on every push to `main`. Exports the
doc/wiki subset (01-09 folders, HOME/MILESTONES/README/log, .neo4j/README,
src/README) into a GitHub Wiki checkout. Unlike `convert_links_for_code.py`
(which rewrites the same source's `[[wikilinks]]` into relative Markdown for
GitHub's regular Code view), this script leaves genuine page-to-page
`[[Page]]` / `[[Page\\|text]]` wikilinks UNCHANGED — the Wiki's Gollum
engine renders Obsidian's native syntax directly, table-cell pipe-escaping
and all (CLAUDE.md's "Ссылки в ячейках таблиц" convention already produces
exactly what Gollum needs).

Only three link shapes get rewritten, because their targets have no
equivalent inside the wiki checkout itself:
  - `[[folder/path/]]` / `[[folder/path/\\|text]]` (a category-folder link)
    becomes plain text (the display text, or the folder name) — a wiki has
    no folder-listing page to link to.
  - `[[name.py|relative/path.py]]` (or any other real repo file that is not
    part of the doc export, e.g. `LICENSE.txt`) becomes an absolute link to
    that file's GitHub blob view in `im-human-public`, since the wiki
    checkout contains no source code.
  - `[[mortality:...]]` cross-vault KB citations and `09 - Templates/`
    `{{...}}` placeholders are left untouched by construction — this
    script's rewrite only matches `[[...]]` whose target is a folder or a
    resolvable non-doc file; neither ever matches those two.

Usage:
    python tools/export_wiki.py --source <source-repo-dir> --dest <wiki-checkout-dir>
"""

from __future__ import annotations

import argparse
import re
import shutil
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
EXTRA_FOLDER_DIRS = ["00 - Inbox"]
ROOT_DOCS = ["HOME.md", "MILESTONES.md", "README.md", "log.md"]
EXTRA_DOCS = [".neo4j/README.md", "src/README.md"]
ASSETS_DIR = "Assets"

PUBLIC_REPO = "SimuOstasis/im-human-public"
GITHUB_BLOB_BASE = f"https://github.com/{PUBLIC_REPO}/blob/master/"

# `[[target]]` or `[[target\|display]]` / `[[target|display]]`.
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


def build_folder_map(source: Path) -> dict[str, Path]:
    folder_map: dict[str, Path] = {}
    for d in DOC_DIRS + EXTRA_FOLDER_DIRS:
        folder_map[d + "/"] = source / d
        for sub in (source / d).iterdir():
            if sub.is_dir():
                folder_map[f"{d}/{sub.name}/"] = sub
    return folder_map


def build_repo_file_index(source: Path) -> dict[str, Path]:
    """Basename -> path for every git-tracked file (mirrors Obsidian's
    resolve-by-unique-name behavior), used to recognize non-doc targets
    like `.py` source files or `LICENSE.txt`."""
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


def _github_blob_url(rel_to_source: str) -> str:
    return GITHUB_BLOB_BASE + quote(rel_to_source)


def build_doc_target_names(doc_path_set: set[Path], source: Path) -> tuple[set[str], set[str]]:
    """Every string form a `[[...]]` target could legitimately use to refer
    to one of the exported doc pages: bare stems (`LDL Cholesterol`) and
    qualified relative paths with or without the `.md` extension (
    `.neo4j/README`, `src/README.md`)."""
    stems = {p.stem for p in doc_path_set}
    qualified = set()
    for p in doc_path_set:
        rel = p.relative_to(source).as_posix()
        qualified.add(rel)
        qualified.add(rel[:-3] if rel.endswith(".md") else rel)
    return stems, qualified


def rewrite_file(f: Path, source: Path, doc_stems: set[str], doc_qualified: set[str],
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
                return display if display else folder_map[target].name

            key = target.rstrip("/").split("/")[-1]

            # A real doc page (bare name or qualified path) — Gollum
            # resolves [[Page]] natively; leave completely untouched.
            if target in doc_qualified or key in doc_stems:
                return m.group(0)

            disp = display if display else key
            candidate = repo_file_index.get(key)
            if candidate is None:
                return m.group(0)  # unresolved — leave visible, not silently guessed
            rel_to_source = candidate.relative_to(source).as_posix()
            if is_excluded(rel_to_source):
                return disp  # excluded from the public repo too — plain text
            return f"[{disp}]({_github_blob_url(rel_to_source)})"

        out_lines.append(_WIKILINK_RE.sub(repl, line))
    return "\n".join(out_lines)


def export(source: Path, dest: Path) -> int:
    doc_files = discover_doc_files(source)
    doc_path_set = set(doc_files)
    doc_stems, doc_qualified = build_doc_target_names(doc_path_set, source)
    folder_map = build_folder_map(source)
    repo_file_index = build_repo_file_index(source)

    dest.mkdir(parents=True, exist_ok=True)

    for f in doc_files:
        if not f.is_file():
            raise SystemExit(f"Expected doc file missing: {f}")
        rel = f.relative_to(source)
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rewritten = rewrite_file(f, source, doc_stems, doc_qualified, folder_map, repo_file_index)
        out_path.write_text(rewritten, encoding="utf-8")

    assets_src = source / ASSETS_DIR
    if assets_src.is_dir():
        shutil.copytree(assets_src, dest / ASSETS_DIR, dirs_exist_ok=True)

    return len(doc_files)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export im-human's documentation/wiki pages into a GitHub Wiki "
            "checkout. Native [[wikilinks]] are left as-is for Gollum; "
            "folder links become plain text and non-doc file links become "
            "absolute GitHub blob URLs into im-human-public."
        )
    )
    parser.add_argument(
        "--source", required=True, type=Path,
        help="Path to the im-human source repo checkout",
    )
    parser.add_argument(
        "--dest", required=True, type=Path,
        help="Path to the im-human-public.wiki checkout to write pages into",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    count = export(args.source.resolve(), args.dest.resolve())
    print(f"[export-wiki] pages_exported={count}")


if __name__ == "__main__":
    main()
