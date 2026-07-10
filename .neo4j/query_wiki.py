#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

r"""
im-human · Semantic + graph query for the Human wiki.

Usage:
    .\venv\Scripts\python.exe query_wiki.py "HOMA-IR инсулинорезистентность"
    .\venv\Scripts\python.exe query_wiki.py "рапамицин mTOR" --top 8
    .\venv\Scripts\python.exe query_wiki.py "воспаление" --section biomarkers
    .\venv\Scripts\python.exe query_wiki.py "omega-3" --tags supplement
"""

import argparse
import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

EMBED_MODEL     = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME      = "human_wiki_chunks"
ALLOWED_INDEXES = {"human_wiki_chunks"}
MAX_HOPS        = 4

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


def vector_search(session, query_vec: list[float], top_k: int,
                  section: str | None, tags: list[str],
                  index_name: str = INDEX_NAME) -> list[dict]:
    if index_name not in ALLOWED_INDEXES:
        raise ValueError(f"Unknown index: {index_name!r}")
    where_clauses = []
    params: dict = {"embedding": query_vec, "k": top_k}

    if section:
        where_clauses.append("p.section = $section")
        params["section"] = section
    if tags:
        where_clauses.append("ANY(tag IN $tags WHERE (p)-[:HAS_TAG]->(:Tag {name: tag}))")
        params["tags"] = tags

    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cypher = f"""
    CALL db.index.vector.queryNodes('{index_name}', $k, $embedding)
    YIELD node AS c, score
    MATCH (c)-[:PART_OF]->(p:Page)
    {where_str}
    RETURN p.slug AS slug, p.title AS title, p.section AS section,
           c.text AS excerpt, score
    ORDER BY score DESC
    LIMIT $k
    """
    result = session.run(cypher, **params)
    return [dict(row) for row in result]


def graph_expand(session, slug: str, hops: int) -> list[dict]:
    hops = max(1, min(hops, MAX_HOPS))
    cypher = f"""
    MATCH (src:Page {{slug: $slug}})-[:LINKS_TO*1..{hops}]-(n:Page)
    RETURN DISTINCT n.slug AS slug, n.title AS title, n.section AS section
    LIMIT 20
    """
    result = session.run(cypher, slug=slug)
    return [dict(row) for row in result]


def main() -> None:
    parser = argparse.ArgumentParser(description="im-human wiki search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top", type=int, default=5, help="Number of results")
    parser.add_argument("--section", default=None, help="Filter by section slug")
    parser.add_argument("--tags", nargs="+", default=[], help="Filter by tags")
    parser.add_argument("--hops", type=int, default=0, help="Graph expansion hops from top result")
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        sys.exit(1)

    print(f"[QUERY] '{args.query}' (top={args.top})")
    query_vec = embed_query(args.query)

    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD"))
    )
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as session:
            results = vector_search(session, query_vec, args.top, args.section, args.tags)

            if not results:
                print("[INFO] No results found.")
                return

            print(f"\n[RESULTS] {len(results)} chunks:\n")
            for i, r in enumerate(results, 1):
                print(f"  {i}. [{r['section']}] {r['title']} (score={r['score']:.3f})")
                print(f"     slug: {r['slug']}")
                excerpt = r["excerpt"] or ""
                print(f"     {excerpt[:200]}{'...' if len(excerpt) > 200 else ''}\n")

            if args.hops > 0 and results:
                top_slug = results[0]["slug"]
                print(f"[GRAPH] Neighbours of '{top_slug}' ({args.hops} hop(s)):\n")
                neighbours = graph_expand(session, top_slug, args.hops)
                for n in neighbours:
                    print(f"  [{n['section']}] {n['title']} — {n['slug']}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
