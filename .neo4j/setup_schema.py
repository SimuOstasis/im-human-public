#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Neo4j schema initialisation.

Creates all UNIQUE constraints, RANGE indexes and the vector index
for the `Human` database. Idempotent — safe to re-run.

Usage (PowerShell):
    cd W:\Obsidian\human\.neo4j
    .\venv\Scripts\python.exe setup_schema.py
    .\venv\Scripts\python.exe setup_schema.py --drop-all   # WARNING: destroys all data
"""

import argparse
import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] neo4j package not found. Run: pip install neo4j")
    sys.exit(1)


NEO4J_URI      = require_env("NEO4J_URI")
NEO4J_USER     = require_env("NEO4J_USER")
NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "Human")
EMBED_DIM      = 384

# ---------------------------------------------------------------------------
# Constraint & index definitions
# ---------------------------------------------------------------------------

CONSTRAINTS = [
    # Wiki layer
    ("page_slug_unique",        "Page",           "slug"),
    ("chunk_id_unique",         "Chunk",           "id"),
    ("tag_name_unique",         "Tag",             "name"),
    # Biomarker layer
    ("biomarker_code_unique",   "Biomarker",       "code"),
    ("category_slug_unique",    "BiomarkerCategory", "slug"),
    ("organ_slug_unique",       "Organ",           "slug"),
    # Substance layer
    ("substance_id_unique",     "Substance",       "id"),
    ("interaction_hash_unique", "Interaction",     "hash"),
    ("effect_id_unique",        "Effect",          "id"),
    # Simulation layer
    ("profile_id_unique",       "HumanProfile",    "profile_id"),
    ("run_id_unique",           "SimulationRun",   "run_id"),
]

INDEXES = [
    # (index_name, label, properties)
    ("biomarker_category",    "Biomarker",    ["category"]),
    ("biomarker_status",      "Biomarker",    ["status"]),
    ("substance_evidence",    "Substance",    ["evidence_level"]),
    ("substance_category",    "Substance",    ["category"]),
    ("organ_name_idx",        "Organ",        ["name"]),
    ("page_section",          "Page",         ["section"]),
    ("page_title",            "Page",         ["title"]),
    ("run_seed",              "SimulationRun", ["seed"]),
]

VECTOR_INDEX = {
    "name": "human_wiki_chunks",
    "label": "Chunk",
    "property": "embedding",
    "dimensions": EMBED_DIM,
    "similarity": "cosine",
}


def ensure_constraints(session) -> None:
    for name, label, prop in CONSTRAINTS:
        cypher = (
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
        )
        session.run(cypher)
        print(f"  [OK] CONSTRAINT {name}")


def ensure_indexes(session) -> None:
    for name, label, props in INDEXES:
        props_str = ", ".join(f"n.{p}" for p in props)
        cypher = (
            f"CREATE INDEX {name} IF NOT EXISTS "
            f"FOR (n:{label}) ON ({props_str})"
        )
        session.run(cypher)
        print(f"  [OK] INDEX {name}")


def ensure_vector_index(session) -> None:
    vi = VECTOR_INDEX
    cypher = f"""
    CREATE VECTOR INDEX {vi['name']} IF NOT EXISTS
    FOR (c:{vi['label']}) ON (c.{vi['property']})
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {vi['dimensions']},
      `vector.similarity_function`: '{vi['similarity']}'
    }}}}
    """
    session.run(cypher)
    print(f"  [OK] VECTOR INDEX {vi['name']} ({vi['dimensions']}d, {vi['similarity']})")


def drop_all(session) -> None:
    print("[WARN] Dropping ALL nodes and relationships...")
    session.run("MATCH (n) DETACH DELETE n")
    print("  [OK] Database cleared")


def print_stats(session) -> None:
    result = session.run(
        "MATCH (n) RETURN labels(n)[0] AS lbl, count(*) AS cnt ORDER BY cnt DESC"
    )
    rows = list(result)
    print("\n[STATS] Node counts:")
    if any(r["lbl"] for r in rows):
        for row in rows:
            if row["lbl"]:
                print(f"  {row['lbl']}: {row['cnt']}")
    else:
        print("  (empty — ready for ingest)")


def main() -> None:
    parser = argparse.ArgumentParser(description="im-human Neo4j schema setup")
    parser.add_argument("--drop-all", action="store_true",
                        help="DELETE ALL DATA before creating schema (destructive!)")
    args = parser.parse_args()

    print(f"[INFO] Connecting to {NEO4J_URI} / database={NEO4J_DATABASE}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            # Verify connection
            session.run("RETURN 1")
            print("[INFO] Connection OK\n")

            if args.drop_all:
                confirm = input("Type 'DELETE ALL' to confirm: ")
                if confirm != "DELETE ALL":
                    print("Aborted.")
                    return
                drop_all(session)

            print("[INFO] Creating constraints...")
            ensure_constraints(session)

            print("\n[INFO] Creating indexes...")
            ensure_indexes(session)

            print("\n[INFO] Creating vector index...")
            ensure_vector_index(session)

            print_stats(session)

        print("\n[DONE] Schema setup complete.")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
