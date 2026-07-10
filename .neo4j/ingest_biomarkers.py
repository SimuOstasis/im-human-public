#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Ingest biomarkers from biomarkers.json into Neo4j.

Creates :Biomarker, :BiomarkerCategory, :Organ nodes and
:BELONGS_TO, :REFLECTS relationships.

Usage:
    cd W:\Obsidian\human\.neo4j
    .\venv\Scripts\python.exe ingest_biomarkers.py
    .\venv\Scripts\python.exe ingest_biomarkers.py --clear
"""

import json
import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

VAULT_ROOT = Path(__file__).parent.parent
DATA_FILE  = VAULT_ROOT / "src" / "data" / "biomarkers.json"


def load_biomarkers() -> dict:
    if not DATA_FILE.exists():
        print(f"[ERROR] Not found: {DATA_FILE}")
        sys.exit(1)
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def ingest(session, data: dict, clear: bool) -> None:
    if clear:
        print("[WARN] Clearing biomarker nodes...")
        session.run("MATCH (n:Biomarker) DETACH DELETE n")
        session.run("MATCH (n:BiomarkerCategory) DETACH DELETE n")
        session.run("MATCH (n:Organ) DETACH DELETE n")

    # Create categories
    for cat in data.get("categories", []):
        session.run("""
            MERGE (c:BiomarkerCategory {slug: $slug})
            SET c.name = $name, c.description = $description
        """, slug=cat["slug"], name=cat["name"],
             description=cat.get("description", ""))
        print(f"  [CAT] {cat['slug']}")

    # Create organs
    for organ in data.get("organs", []):
        session.run("""
            MERGE (o:Organ {slug: $slug})
            SET o.name = $name
        """, slug=organ["slug"], name=organ["name"])
        print(f"  [ORG] {organ['slug']}")

    # Create biomarkers
    created = 0
    for bm in data.get("biomarkers", []):
        session.run("""
            MERGE (b:Biomarker {code: $code})
            SET b.name = $name,
                b.name_ru = $name_ru,
                b.units = $units,
                b.category = $category,
                b.status = $status,
                b.mvp = $mvp,
                b.formula = $formula
        """, code=bm["code"], name=bm["name"],
             name_ru=bm.get("name_ru", bm["name"]),
             units=bm.get("units", ""),
             category=bm.get("category", ""),
             status=bm.get("status", ""),
             mvp=bm.get("mvp", False),
             formula=bm.get("formula", ""))

        # Link to category
        if bm.get("category"):
            session.run("""
                MATCH (b:Biomarker {code: $code})
                MATCH (c:BiomarkerCategory {slug: $cat})
                MERGE (b)-[:BELONGS_TO]->(c)
            """, code=bm["code"], cat=bm["category"])

        # Link to organs
        for organ_slug in bm.get("organs", []):
            session.run("""
                MATCH (b:Biomarker {code: $code})
                MERGE (o:Organ {slug: $organ})
                MERGE (b)-[:REFLECTS]->(o)
            """, code=bm["code"], organ=organ_slug)

        created += 1

    print(f"\n[DONE] Created/updated {created} biomarkers.")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        sys.exit(1)

    data = load_biomarkers()
    print(f"[INFO] Loaded {len(data.get('biomarkers', []))} biomarkers from {DATA_FILE}")

    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD"))
    )
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as session:
            ingest(session, data, args.clear)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
