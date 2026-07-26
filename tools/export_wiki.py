# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""im-human -> im-human-public GitHub Wiki: doc-only export with Gollum-style links.

Stdlib-only (argparse, re, shutil, pathlib, urllib.parse) CLI used by
`.github/workflows/publish-public.yml` on every push to `main`. Unlike
`export_public_snapshot.py` (which mirrors the WHOLE tracked source tree
byte-for-byte), this script exports only the documentation/wiki subset —
the `01 - Human Profiles/` .. `09 - Templates/` folders plus the root docs
(`HOME.md`, `MILESTONES.md`, `README.md`, `log.md`), `.neo4j/README.md`, and
`src/README.md` — and REWRITES every standard Markdown link
(`[text](relative/path.md)`, added for the main-repo GitHub rendering fix)
back into Gollum's native `[[Page]]` / `[[Page|text]]` wikilink syntax,
since the GitHub Wiki's Gollum engine renders `[[...]]` directly.

Link rewriting rules:
  - A Markdown link whose target resolves to one of the exported doc files
    becomes `[[PageName]]` (or `[[PageName|display text]]` if the display
    text differs from the page name). Page names are the file's stem,
    disambiguated by qualified relative path on basename collisions (e.g.
    three `README.md` files -> `README`, `.neo4j/README`, `src/README`).
  - A Markdown link whose target is a directory (a category-folder link)
    becomes an absolute link to that folder's GitHub tree view in
    `im-human-public`, since a wiki page has no folder-listing equivalent.
  - A Markdown link whose target is any other real file (Python source,
    LICENSE.txt, etc. — not part of the doc export) becomes an absolute
    link to that file's GitHub blob view in `im-human-public`, since the
    wiki repo does not contain source code.
  - External links (http/https/mailto) and in-page anchors are left as-is.
  - Image embeds (`![alt](path)`) are left as-is; referenced local assets
    (`Assets/`) are copied alongside the exported docs so relative paths
    keep resolving.
  - `[[mortality:...]]` cross-vault KB citations and `09 - Templates/`
    `{{...}}`/`[[...]]` placeholders were never converted to Markdown links
    in the source, so this script's link-rewriting regex (which only
    matches standard `[text](url)` syntax) does not touch them — they pass
    through unchanged, which is correct for both.

Usage:
    python tools/export_wiki.py --source <source-repo-dir> --dest <wiki-checkout-dir>
"""

from __future__ import annotations

import argparse
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote

DOC_DIRS = [
    "01 - Human Profiles", "02 - Biomarkers", "03 - Substances",
    "04 - Interactions", "05 - Simulation", "06 - Engine",
    "07 - Analysis", "08 - Index", "09 - Templates",
]
ROOT_DOCS = ["HOME.md", "MILESTONES.md", "README.md", "log.md"]
EXTRA_DOCS = [".neo4j/README.md", "src/README.md"]
ASSETS_DIR = "Assets"

PUBLIC_REPO = "SimuOstasis/im-human-public"
GITHUB_BLOB_BASE = f"https://github.com/{PUBLIC_REPO}/blob/master/"
GITHUB_TREE_BASE = f"https://github.com/{PUBLIC_REPO}/tree/master/"

# One level of balanced parens is valid, unescaped, in a CommonMark link
# destination (e.g. "25(OH)D.md") — match that instead of stopping at the
# first ")".
_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")


def discover_doc_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for d in DOC_DIRS:
        files.extend(sorted((source / d).rglob("*.md")))
    for name in ROOT_DOCS:
        files.append(source / name)
    for rel in EXTRA_DOCS:
        files.append(source / rel)
    return [f.resolve() for f in files]


def build_wiki_names(doc_files: list[Path], source: Path) -> dict[Path, str]:
    """Map each doc file to its Gollum page name (file stem, disambiguated by
    qualified relative path — without extension — on basename collisions;
    the file with the shortest relative path keeps the bare stem)."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in doc_files:
        groups[f.stem].append(f)

    wiki_name: dict[Path, str] = {}
    for stem, group in groups.items():
        if len(group) == 1:
            wiki_name[group[0]] = stem
            continue
        group_sorted = sorted(group, key=lambda p: len(str(p.relative_to(source))))
        wiki_name[group_sorted[0]] = stem
        for f in group_sorted[1:]:
            rel = f.relative_to(source).with_suffix("")
            wiki_name[f] = str(rel).replace("\\", "/")
    return wiki_name


def _github_url(base: str, rel_to_source: Path) -> str:
    return base + quote(str(rel_to_source).replace("\\", "/"))


def rewrite_links(text: str, current_file: Path, source: Path,
                   doc_path_set: set[Path], wiki_name: dict[Path, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        bang, display, target = m.group(1), m.group(2), m.group(3)
        if bang:
            return m.group(0)  # image embed — asset copied alongside, path untouched
        if target.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        if target.startswith("#"):
            return m.group(0)

        try:
            abs_target = (current_file.parent / unquote(target)).resolve()
        except (OSError, ValueError):
            return m.group(0)

        if abs_target.is_dir():
            try:
                rel = abs_target.relative_to(source)
            except ValueError:
                return m.group(0)
            return f"[{display}]({_github_url(GITHUB_TREE_BASE, rel)})"

        if abs_target in doc_path_set:
            page = wiki_name[abs_target]
            return f"[[{page}]]" if display == page else f"[[{page}|{display}]]"

        if abs_target.exists():
            try:
                rel = abs_target.relative_to(source)
            except ValueError:
                return m.group(0)
            return f"[{display}]({_github_url(GITHUB_BLOB_BASE, rel)})"

        return m.group(0)  # unresolvable — leave unchanged rather than guess

    return _LINK_RE.sub(repl, text)


def export(source: Path, dest: Path) -> int:
    doc_files = discover_doc_files(source)
    doc_path_set = set(doc_files)
    wiki_name = build_wiki_names(doc_files, source)

    dest.mkdir(parents=True, exist_ok=True)

    for f in doc_files:
        if not f.is_file():
            raise SystemExit(f"Expected doc file missing: {f}")
        rel = f.relative_to(source)
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = f.read_text(encoding="utf-8")
        out_path.write_text(
            rewrite_links(text, f, source, doc_path_set, wiki_name),
            encoding="utf-8",
        )

    assets_src = source / ASSETS_DIR
    if assets_src.is_dir():
        shutil.copytree(assets_src, dest / ASSETS_DIR, dirs_exist_ok=True)

    return len(doc_files)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export im-human's documentation/wiki pages into a GitHub Wiki "
            "checkout, rewriting Markdown links back to Gollum [[wikilinks]]."
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
