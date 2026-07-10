# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Idempotent Apache-2.0 copyright/license header inserter.

One tool, six modes, all safe to re-run (skip-if-marker-present):

    --python         Prepend a 4-line comment header to src/**/*.py and
                      .neo4j/*.py (after any shebang line).
    --wiki           Insert license/copyright/contact frontmatter keys into
                      the 53 wiki .md pages (10 SECTIONS folders, excluding
                      09 - Templates/ and the 4 root SKIP_FILES).
    --templates      Same frontmatter-key insertion as --wiki, scoped to the
                      3 files under "09 - Templates/" (placeholder-safe: text
                      insertion only, never parses/re-serializes YAML).
    --json-sidecars  Create adjacent <name>.json.license SPDX sidecar files
                      for the 6 tracked JSON data files. Never opens the JSON
                      itself.
    --root-docs      Insert a "## License" H2 block into README.md, HOME.md,
                      MILESTONES.md, log.md (after the first H1 heading).
    --dry-run        Report what WOULD change; write nothing.

Design note: frontmatter/header insertion is done via TEXT-LINE insertion,
never via yaml.safe_load/yaml.safe_dump round-trip. Verified empirically
(Phase 09.1 planning) that yaml.safe_load fails on 4 of 53 wiki files
(3 templates using "{{PLACEHOLDER}}" flow-token syntax, and
"02 - Biomarkers/02 - Glucose/HbA1c.md" via "units: %", a YAML reserved
indicator) and that yaml.safe_dump would reformat existing flow-lists
(tags: [a, b] -> block list) on the other 49, producing noisy diffs. `yaml`
is imported read-only, wrapped in try/except, purely to help detect an
already-present `license` key during idempotency checks — never to
re-serialize a frontmatter block.

Usage (PowerShell, from vault root):
    venv\\Scripts\\python.exe tools/add_license_headers.py --python --dry-run
    venv\\Scripts\\python.exe tools/add_license_headers.py --python
    venv\\Scripts\\python.exe tools/add_license_headers.py --wiki --templates --dry-run
    venv\\Scripts\\python.exe tools/add_license_headers.py --json-sidecars --root-docs
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml  # noqa: F401  (read-only idempotency-detection aid; never used to dump)
except ImportError:  # pragma: no cover - yaml is an existing project dependency
    yaml = None

# CRITICAL: this script lives in tools/, one level below vault root.
# ingest_wiki.py uses:            Path(__file__).parent.parent        (.neo4j/ -> vault)
# generate_biomarker_pages.py uses: Path(__file__).parent.parent.parent (scripts->src->vault)
# add_license_headers.py uses:    Path(__file__).parent.parent        (tools/ -> vault)
VAULT_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Fixed constants (verbatim, per 09.1-01-PLAN.md <artifacts_produced>)
# ---------------------------------------------------------------------------

COPYRIGHT_LINE = "Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>"
COPYRIGHT_LINE_SHORT = "Copyright © 2026 Vladimir Bazhin"
CONTACT_EMAIL = "info@simuostasis.com"

PY_HEADER = (
    f"# {COPYRIGHT_LINE}\n"
    "#\n"
    "# Licensed under the Apache License, Version 2.0.\n"
    "# http://www.apache.org/licenses/LICENSE-2.0\n"
)

FRONTMATTER_LICENSE_LINES = (
    "license: Apache-2.0\n"
    f'copyright: "{COPYRIGHT_LINE_SHORT}"\n'
    f"contact: {CONTACT_EMAIL}\n"
)

SIDECAR_BODY = (
    f"# SPDX-FileCopyrightText: 2026 Vladimir Bazhin <{CONTACT_EMAIL}>\n"
    "#\n"
    "# SPDX-License-Identifier: Apache-2.0\n"
)

ROOT_DOC_LICENSE_BLOCK = (
    "\n## License\n\n"
    "This work is licensed under the Apache License, Version 2.0. "
    "See [LICENSE.txt](LICENSE.txt) for the full text.\n\n"
    f"{COPYRIGHT_LINE_SHORT}. Contact: {CONTACT_EMAIL}\n"
)

# Same 10 SECTIONS folders .neo4j/ingest_wiki.py walks (Donor 3, 09.1-PATTERNS.md).
SECTIONS: dict[str, str] = {
    "00 - Inbox": "inbox",
    "01 - Human Profiles": "profiles",
    "02 - Biomarkers": "biomarkers",
    "03 - Substances": "substances",
    "04 - Interactions": "interactions",
    "05 - Simulation": "simulation",
    "06 - Engine": "engine",
    "07 - Analysis": "analysis",
    "08 - Index": "index",
    "09 - Templates": "templates",
}

TEMPLATES_FOLDER = "09 - Templates"

# Root public docs (D-02) — same set as ingest_wiki.py's SKIP_FILES, they are
# NOT wiki pages (never chunked/embedded) and get a body-level "## License"
# block instead of frontmatter keys.
ROOT_DOCS = ["README.md", "HOME.md", "MILESTONES.md", "log.md"]

JSON_SIDECAR_TARGETS = [
    VAULT_ROOT / "src" / "data" / "substances.json",
    VAULT_ROOT / "src" / "data" / "interactions.json",
    VAULT_ROOT / "src" / "data" / "biomarkers.json",
    VAULT_ROOT / "src" / "data" / "reference_ranges.json",
    VAULT_ROOT / "src" / "data" / "presets.json",
    VAULT_ROOT / ".planning" / "config.json",
]


# ---------------------------------------------------------------------------
# --python mode
# ---------------------------------------------------------------------------

def _excluded_py_path(path: Path) -> bool:
    """True if path is under a venv/ or __pycache__/ segment."""
    return any(part in ("venv", "__pycache__") for part in path.parts)


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    src_dir = VAULT_ROOT / "src"
    if src_dir.exists():
        files.extend(
            p for p in sorted(src_dir.rglob("*.py")) if not _excluded_py_path(p)
        )
    neo4j_dir = VAULT_ROOT / ".neo4j"
    if neo4j_dir.exists():
        files.extend(
            p for p in sorted(neo4j_dir.glob("*.py")) if not _excluded_py_path(p)
        )
    return files


def add_python_header(path: Path, dry_run: bool) -> str:
    """Insert PY_HEADER after any shebang line. Returns 'modified' or 'skipped'."""
    text = path.read_text(encoding="utf-8")
    if "Copyright ©" in text or "SPDX-License-Identifier" in text:
        return "skipped"

    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        # shebang stays on line 1 — header inserted after it (Pitfall 3)
        new_text = lines[0] + PY_HEADER + "\n" + "".join(lines[1:])
    else:
        new_text = PY_HEADER + "\n" + text

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return "modified"


def run_python_mode(dry_run: bool) -> None:
    files = iter_python_files()
    modified = skipped = 0
    for path in files:
        result = add_python_header(path, dry_run)
        rel = path.relative_to(VAULT_ROOT)
        if result == "modified":
            modified += 1
            verb = "WOULD MODIFY" if dry_run else "modified"
            print(f"[python] {verb}: {rel}")
        else:
            skipped += 1
    print(f"[python] total={len(files)} modified={modified} skipped={skipped}")


# ---------------------------------------------------------------------------
# --wiki / --templates modes (shared text-insertion logic)
# ---------------------------------------------------------------------------

def _frontmatter_has_license(path: Path, text: str) -> bool:
    """Idempotency check: scan the raw frontmatter region for a `license:` key.

    Uses a raw-text region scan (not a full yaml.safe_load) so it works even
    on files whose frontmatter is not valid YAML (e.g. "{{PLACEHOLDER}}"
    flow-tokens in the 3 templates, or "units: %" in HbA1c.md).
    """
    if not text.startswith("---"):
        return False
    end = text.find("---", 3)
    if end == -1:
        return False
    fm_region = text[3:end]
    return any(
        line.strip().startswith("license:") for line in fm_region.splitlines()
    )


def add_wiki_license_fields(path: Path, dry_run: bool) -> str:
    """Insert the 3 license frontmatter lines as literal text after the
    opening '---' delimiter. Never parses/re-serializes YAML. Returns
    'modified' or 'skipped'."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return "skipped"  # no frontmatter block — nothing to insert into
    if _frontmatter_has_license(path, text):
        return "skipped"

    # Insert immediately after the opening "---\n" line.
    newline_idx = text.find("\n")
    if newline_idx == -1:
        return "skipped"
    insert_at = newline_idx + 1
    new_text = text[:insert_at] + FRONTMATTER_LICENSE_LINES + text[insert_at:]

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return "modified"


def iter_wiki_files(include_templates: bool) -> list[Path]:
    files: list[Path] = []
    for folder_name in SECTIONS:
        if folder_name == TEMPLATES_FOLDER and not include_templates:
            continue
        if folder_name != TEMPLATES_FOLDER and include_templates:
            continue
        folder = VAULT_ROOT / folder_name
        if not folder.exists():
            continue
        for md_file in sorted(folder.rglob("*.md")):
            files.append(md_file)
    return files


def _run_frontmatter_mode(mode_name: str, files: list[Path], dry_run: bool) -> None:
    modified = skipped = 0
    for path in files:
        result = add_wiki_license_fields(path, dry_run)
        rel = path.relative_to(VAULT_ROOT)
        if result == "modified":
            modified += 1
            verb = "WOULD MODIFY" if dry_run else "modified"
            print(f"[{mode_name}] {verb}: {rel}")
        else:
            skipped += 1
    print(f"[{mode_name}] total={len(files)} modified={modified} skipped={skipped}")


def run_wiki_mode(dry_run: bool) -> None:
    _run_frontmatter_mode("wiki", iter_wiki_files(include_templates=False), dry_run)


def run_templates_mode(dry_run: bool) -> None:
    _run_frontmatter_mode(
        "templates", iter_wiki_files(include_templates=True), dry_run
    )


# ---------------------------------------------------------------------------
# --json-sidecars mode
# ---------------------------------------------------------------------------

def run_json_sidecars_mode(dry_run: bool) -> None:
    modified = skipped = 0
    for json_path in JSON_SIDECAR_TARGETS:
        sidecar_path = json_path.with_name(json_path.name + ".license")
        rel = sidecar_path.relative_to(VAULT_ROOT)
        if sidecar_path.exists():
            skipped += 1
            continue
        modified += 1
        verb = "WOULD CREATE" if dry_run else "created"
        print(f"[json-sidecars] {verb}: {rel}")
        if not dry_run:
            sidecar_path.write_text(SIDECAR_BODY, encoding="utf-8")
    print(
        f"[json-sidecars] total={len(JSON_SIDECAR_TARGETS)} "
        f"modified={modified} skipped={skipped}"
    )


# ---------------------------------------------------------------------------
# --root-docs mode
# ---------------------------------------------------------------------------

def add_root_doc_license_block(path: Path, dry_run: bool) -> str:
    text = path.read_text(encoding="utf-8")
    if "## License" in text:
        return "skipped"

    lines = text.splitlines(keepends=True)
    insert_idx = None
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_idx = i + 1
            break

    if insert_idx is None:
        # No H1 heading found — prepend the block at the very top instead.
        new_text = ROOT_DOC_LICENSE_BLOCK.lstrip("\n") + "\n" + text
    else:
        new_text = (
            "".join(lines[:insert_idx])
            + ROOT_DOC_LICENSE_BLOCK
            + "".join(lines[insert_idx:])
        )

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return "modified"


def run_root_docs_mode(dry_run: bool) -> None:
    modified = skipped = 0
    for name in ROOT_DOCS:
        path = VAULT_ROOT / name
        if not path.exists():
            print(f"[root-docs] MISSING (skipped): {name}")
            skipped += 1
            continue
        result = add_root_doc_license_block(path, dry_run)
        if result == "modified":
            modified += 1
            verb = "WOULD MODIFY" if dry_run else "modified"
            print(f"[root-docs] {verb}: {name}")
        else:
            skipped += 1
    print(f"[root-docs] total={len(ROOT_DOCS)} modified={modified} skipped={skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotent Apache-2.0 copyright/license header inserter "
            "for im-human (Phase 09.1)."
        )
    )
    parser.add_argument(
        "--python", action="store_true",
        help="Insert the 4-line header into src/**/*.py and .neo4j/*.py",
    )
    parser.add_argument(
        "--wiki", action="store_true",
        help="Insert license/copyright/contact frontmatter keys into wiki pages",
    )
    parser.add_argument(
        "--templates", action="store_true",
        help="Same as --wiki, scoped to 09 - Templates/ (placeholder-safe)",
    )
    parser.add_argument(
        "--json-sidecars", action="store_true",
        help="Create <name>.json.license SPDX sidecar files",
    )
    parser.add_argument(
        "--root-docs", action="store_true",
        help="Insert '## License' block into README.md/HOME.md/MILESTONES.md/log.md",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what WOULD change; write nothing",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    any_mode = any(
        [args.python, args.wiki, args.templates, args.json_sidecars, args.root_docs]
    )
    if not any_mode:
        parser.error(
            "at least one mode is required: --python, --wiki, --templates, "
            "--json-sidecars, --root-docs"
        )

    if args.dry_run:
        print("=== DRY RUN — no files will be written ===")

    if args.python:
        run_python_mode(args.dry_run)
    if args.wiki:
        run_wiki_mode(args.dry_run)
    if args.templates:
        run_templates_mode(args.dry_run)
    if args.json_sidecars:
        run_json_sidecars_mode(args.dry_run)
    if args.root_docs:
        run_root_docs_mode(args.dry_run)


if __name__ == "__main__":
    main()
