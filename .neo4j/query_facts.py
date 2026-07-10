#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Biomarker fact lookup via semantic search.

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe query_facts.py "HOMA-IR"
    .\\venv\\Scripts\\python.exe query_facts.py "LDL Cholesterol" --top 3
    .\\venv\\Scripts\\python.exe query_facts.py "воспаление" --top 5 --no-expand
"""

import argparse
import io
import os
import sys
from pathlib import Path


def _configure_stdout() -> None:
    """Reconfigure stdout to UTF-8 on Windows (cp1251 default breaks Cyrillic + Unicode)."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _load_dotenv() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
_configure_stdout()

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME  = "human_wiki_chunks"
SECTION     = "biomarkers"          # hard-coded filter — differs from query_wiki.py
PAGE_EXPAND_THRESHOLD = 0.65        # min score to trigger full-page fact dump
# Oversampling: vector index returns $k globally before WHERE section filter;
# multiplying ensures we get top_k biomarker results even when other sections dominate.
QUERY_MULTIPLIER = 5

_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBED_MODEL, model_kwargs={"low_cpu_mem_usage": True})
        except ImportError:
            print("[ERROR] pip install sentence-transformers")
            sys.exit(1)
    return _model


def embed_query(text: str) -> list[float]:
    return get_model().encode([text])[0].tolist()


def search_biomarker(session, query_vec: list[float], top_k: int) -> list[dict]:
    """Search biomarker chunks via vector similarity, filtered to section='biomarkers'."""
    cypher = f"""
    CALL db.index.vector.queryNodes('{INDEX_NAME}', $k_expanded, $embedding)
    YIELD node AS c, score
    MATCH (c)-[:PART_OF]->(p:Page)
    WHERE p.section = '{SECTION}'
    RETURN p.slug AS slug, p.title AS title, p.code AS code,
           p.category AS category, c.text AS excerpt, score
    ORDER BY score DESC
    LIMIT $k
    """
    result = session.run(cypher, embedding=query_vec, k=top_k, k_expanded=top_k * QUERY_MULTIPLIER)
    return [dict(row) for row in result]


def fetch_page_facts(session, slug: str) -> list[dict]:
    """Fetch all chunks of a specific page ordered by chunk_index.
    Used to surface formula and reference ranges that may score low in ANN search.
    """
    cypher = """
    MATCH (c:Chunk)-[:PART_OF]->(p:Page {slug: $slug})
    RETURN c.text AS text, c.chunk_index AS idx
    ORDER BY c.chunk_index
    """
    result = session.run(cypher, slug=slug)
    return [dict(row) for row in result]


def _best_page_per_slug(results: list[dict]) -> list[dict]:
    """De-duplicate results to one row per slug (highest score wins)."""
    seen: dict[str, dict] = {}
    for r in results:
        slug = r["slug"]
        if slug not in seen or r["score"] > seen[slug]["score"]:
            seen[slug] = r
    # Return in original score order
    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="im-human biomarker fact lookup")
    parser.add_argument("query", help="Biomarker name or concept")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--no-expand", action="store_true",
                        help="Show matching chunks only; skip full-page expansion")
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        sys.exit(1)

    query_vec = embed_query(args.query)

    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")
    missing = [k for k, v in [("NEO4J_URI", neo4j_uri), ("NEO4J_USER", neo4j_user),
                               ("NEO4J_PASSWORD", neo4j_password)] if not v]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}. Create .neo4j/.env with these keys.")
        sys.exit(1)

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as session:
            results = search_biomarker(session, query_vec, args.top)

            if not results:
                print("[INFO] No results. Run ingest_wiki.py --section biomarkers first.")
                return

            print(f"[QUERY] '{args.query}' (top={args.top})\n")

            for i, r in enumerate(results, 1):
                print(f"\n{'='*60}")
                print(f"  {i}. {r['title']}  [code: {r['code'] or '—'}]")
                print(f"     category: {r['category'] or '—'}  score={r['score']:.3f}")
                excerpt = r["excerpt"] or ""
                print(f"\n{excerpt}\n")

            # Full-page expansion: for each unique page scoring above threshold,
            # fetch all chunks to surface formula + reference ranges (SC-1).
            # This compensates for ANN search not always ranking formula/range
            # chunks near the top when searching by biomarker name.
            if not args.no_expand:
                pages = _best_page_per_slug(results)
                pages = [p for p in pages if p["score"] >= PAGE_EXPAND_THRESHOLD]
                if pages:
                    print(f"\n{'#'*60}")
                    print(f"# FULL PAGE FACTS ({len(pages)} page(s) above score {PAGE_EXPAND_THRESHOLD})")
                    print(f"{'#'*60}")
                    for page in pages:
                        page_chunks = fetch_page_facts(session, page["slug"])
                        if not page_chunks:
                            continue
                        print(f"\n{'='*60}")
                        print(f"  {page['title']}  [code: {page['code'] or '—'}]"
                              f"  category: {page['category'] or '—'}  ({len(page_chunks)} chunks)")
                        print(f"{'='*60}\n")
                        for chunk in page_chunks:
                            text = chunk["text"] or ""
                            print(text)
                            print()
    finally:
        driver.close()


if __name__ == "__main__":
    main()
