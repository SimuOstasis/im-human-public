#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

r"""
im-human · Neo4j wiki ingest pipeline.

Reads pages from vault sections, creates :Page nodes with metadata,
:LINKS_TO edges from [[wikilinks]], :Chunk nodes with embeddings,
and :Tag nodes with :HAS_TAG edges.

Embedding model: paraphrase-multilingual-MiniLM-L12-v2 (384d) — same as Mortality.

Usage (PowerShell):
    cd W:\Obsidian\human\.neo4j
    .\venv\Scripts\python.exe ingest_wiki.py [--dry-run] [--clear]
    .\venv\Scripts\python.exe ingest_wiki.py --section biomarkers
    .\venv\Scripts\python.exe ingest_wiki.py --changed-only

Flags:
    --dry-run       Parse files and show stats, no DB writes
    --clear         Delete all Page/Chunk/Tag nodes before loading
    --limit N       Process only first N pages (debug)
    --section SLUG  Ingest only this section (e.g. "biomarkers", "substances")
    --changed-only  Skip pages whose file_hash matches the stored hash
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Generator

import yaml

from _utils import load_dotenv, require_env

load_dotenv()

VAULT_ROOT = Path(__file__).parent.parent

SECTIONS: dict[str, str] = {
    "00 - Inbox":            "inbox",
    "01 - Human Profiles":   "profiles",
    "02 - Biomarkers":       "biomarkers",
    "03 - Substances":       "substances",
    "04 - Interactions":     "interactions",
    "05 - Simulation":       "simulation",
    "06 - Engine":           "engine",
    "07 - Analysis":         "analysis",
    "08 - Index":            "index",
    "09 - Templates":        "templates",
}

SKIP_FILES = {"log.md", "HOME.md", "CLAUDE.md", "MILESTONES.md"}

EMBED_MODEL   = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM     = 384
CHUNK_SIZE    = 400
CHUNK_OVERLAP = 80
INDEX_NAME    = "human_wiki_chunks"


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iter_pages(section_filter: str | None = None) -> Generator[tuple[Path, str, str], None, None]:
    """Yield (path, section_slug, page_slug) for all markdown files."""
    for folder_name, section_slug in SECTIONS.items():
        if section_filter and section_slug != section_filter:
            continue
        folder = VAULT_ROOT / folder_name
        if not folder.exists():
            continue
        for md_file in sorted(folder.rglob("*.md")):
            if md_file.name in SKIP_FILES:
                continue
            rel = md_file.relative_to(folder)
            parts = list(rel.with_suffix("").parts)
            slug_parts = [slugify(p) for p in parts]
            page_slug = f"{section_slug}/{'/'.join(slug_parts)}"
            yield md_file, section_slug, page_slug


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_text = content[3:end].strip()
            body = content[end + 3:].strip()
            try:
                return yaml.safe_load(fm_text) or {}, body
            except yaml.YAMLError:
                return {}, content
    return {}, content


def extract_wikilinks(text: str) -> list[str]:
    raw = re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]", text)
    result = []
    for link in raw:
        link = link.strip()
        if link and not link.startswith("http"):
            result.append(link)
    return result


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print(f"[INFO] Loading embedding model {EMBED_MODEL}...")
            _model = SentenceTransformer(EMBED_MODEL, model_kwargs={"low_cpu_mem_usage": True})
            print("[INFO] Model loaded.")
        except ImportError:
            print("[ERROR] sentence-transformers not installed. Run: pip install sentence-transformers")
            sys.exit(1)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    model = get_model()
    return model.encode(texts, show_progress_bar=False).tolist()


# ---------------------------------------------------------------------------
# Neo4j writes
# ---------------------------------------------------------------------------

def upsert_page(session, slug: str, title: str, section: str,
                file_hash: str, frontmatter: dict, wikilinks: list[str]) -> None:
    session.run("""
        MERGE (p:Page {slug: $slug})
        SET p.title = $title,
            p.section = $section,
            p.file_hash = $file_hash,
            p.code = $code,
            p.category = $category,
            p.status = $status,
            p.updated_at = datetime()
    """, slug=slug, title=title, section=section, file_hash=file_hash,
         code=frontmatter.get("code", ""),
         category=frontmatter.get("category", ""),
         status=frontmatter.get("status", ""))

    for tag in frontmatter.get("tags", []):
        if tag:
            session.run("""
                MERGE (t:Tag {name: $name})
                WITH t
                MATCH (p:Page {slug: $slug})
                MERGE (p)-[:HAS_TAG]->(t)
            """, name=str(tag), slug=slug)


def upsert_chunks(session, slug: str, body: str) -> None:
    texts = chunk_text(body)
    embeddings = embed(texts) if texts else []
    with session.begin_transaction() as tx:
        tx.run("MATCH (c:Chunk)-[:PART_OF]->(p:Page {slug: $slug}) DETACH DELETE c", slug=slug)
        for i, (text, emb) in enumerate(zip(texts, embeddings)):
            chunk_id = f"{slug}::chunk::{i}"
            tx.run("""
                MERGE (c:Chunk {id: $id})
                SET c.text = $text, c.embedding = $embedding, c.chunk_index = $idx
                WITH c
                MATCH (p:Page {slug: $slug})
                MERGE (c)-[:PART_OF]->(p)
            """, id=chunk_id, text=text, embedding=emb, idx=i, slug=slug)
        tx.commit()


def wikilink_to_slug(link: str) -> str:
    """Convert an Obsidian wikilink path to a graph slug preserving section hierarchy.

    '02 - Biomarkers/01 - Lipids/LDL Cholesterol' -> 'biomarkers/lipids/ldl-cholesterol'
    'LDL Cholesterol' -> 'ldl-cholesterol'
    """
    parts = [p.strip() for p in link.strip().split("/")]
    if len(parts) == 1:
        return slugify(link)
    first = parts[0]
    for folder, section_slug in SECTIONS.items():
        if first == folder or first.lower() in folder.lower():
            slug_parts = [slugify(p) for p in parts[1:]]
            return "/".join([section_slug] + slug_parts)
    return slugify(link.replace("/", "-"))


def create_links(session, slug: str, wikilinks: list[str]) -> None:
    session.run("MATCH (p:Page {slug: $slug})-[r:LINKS_TO]->() DELETE r", slug=slug)
    for link in set(wikilinks):
        target_slug = wikilink_to_slug(link)
        session.run("""
            MATCH (src:Page {slug: $src})
            MERGE (tgt:Page {slug: $tgt})
            ON CREATE SET tgt.title = $tgt_title, tgt.section = 'unknown'
            MERGE (src)-[:LINKS_TO]->(tgt)
        """, src=slug, tgt=target_slug, tgt_title=link)


def clear_wiki(session) -> None:
    print("[WARN] Clearing all Page/Chunk/Tag nodes...")
    session.run("MATCH (c:Chunk) DETACH DELETE c")
    session.run("MATCH (p:Page) DETACH DELETE p")
    session.run("MATCH (t:Tag) DETACH DELETE t")
    print("[OK] Wiki nodes cleared.")


def get_stored_hashes(session) -> dict[str, str]:
    result = session.run("MATCH (p:Page) WHERE p.file_hash IS NOT NULL RETURN p.slug, p.file_hash")
    return {row["p.slug"]: row["p.file_hash"] for row in result}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="im-human wiki ingest")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--section", default=None)
    parser.add_argument("--changed-only", action="store_true")
    args = parser.parse_args()

    pages = list(iter_pages(args.section))
    if args.limit:
        pages = pages[:args.limit]

    print(f"[INFO] Found {len(pages)} pages to process (section={args.section or 'all'})")

    if args.dry_run:
        for path, section, slug in pages:
            print(f"  {slug}")
        print("[DRY-RUN] No writes.")
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] neo4j not installed")
        sys.exit(1)

    uri      = require_env("NEO4J_URI")
    user     = require_env("NEO4J_USER")
    password = require_env("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE", "Human")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    processed = skipped = errors = 0

    try:
        with driver.session(database=database) as session:
            if args.clear:
                clear_wiki(session)

            stored_hashes = get_stored_hashes(session) if args.changed_only else {}

            for path, section, slug in pages:
                try:
                    fhash = file_hash(path)
                    if args.changed_only and stored_hashes.get(slug) == fhash:
                        skipped += 1
                        continue

                    content = path.read_text(encoding="utf-8")
                    fm, body = parse_frontmatter(content)
                    title = fm.get("title") or path.stem
                    wikilinks = extract_wikilinks(body)

                    upsert_page(session, slug, title, section, fhash, fm, wikilinks)
                    upsert_chunks(session, slug, body)
                    create_links(session, slug, wikilinks)

                    print(f"  [OK] {slug}")
                    processed += 1
                except Exception as e:
                    print(f"  [ERR] {slug}: {e}")
                    errors += 1

    finally:
        driver.close()

    print(f"\n[DONE] Processed: {processed}, Skipped: {skipped}, Errors: {errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
