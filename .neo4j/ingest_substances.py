#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Ingest substances from substances.json into Neo4j.

Creates :Substance, :Interaction, :Effect nodes and all relationships.

Usage:
    cd W:\Obsidian\human\.neo4j
    .\venv\Scripts\python.exe ingest_substances.py
    .\venv\Scripts\python.exe ingest_substances.py --clear
"""

import hashlib
import json
import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

VAULT_ROOT        = Path(__file__).parent.parent
SUBSTANCES_FILE   = VAULT_ROOT / "src" / "data" / "substances.json"
INTERACTIONS_FILE = VAULT_ROOT / "src" / "data" / "interactions.json"


def interaction_hash(sub_a: str, sub_b: str, interaction_type: str) -> str:
    key = f"{min(sub_a, sub_b)}::{max(sub_a, sub_b)}::{interaction_type}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def ingest(session, substances: list, interactions: list, clear: bool) -> None:
    if clear:
        print("[WARN] Clearing substance/interaction nodes...")
        session.run("MATCH (n:Substance) DETACH DELETE n")
        session.run("MATCH (n:Interaction) DETACH DELETE n")
        session.run("MATCH (n:Effect) DETACH DELETE n")

    # Create substances
    for s in substances:
        session.run("""
            MERGE (sub:Substance {id: $id})
            SET sub.name = $name,
                sub.name_ru = $name_ru,
                sub.category = $category,
                sub.evidence_level = $evidence_level,
                sub.dose_unit = $dose_unit,
                sub.min_dose = $min_dose,
                sub.max_dose = $max_dose,
                sub.default_dose = $default_dose,
                sub.bioavailability = $bioavailability,
                sub.half_life_hours = $half_life_hours,
                sub.absorption_rate = $absorption_rate,
                sub.elimination_rate = $elimination_rate,
                sub.accumulation_threshold = $accumulation_threshold,
                sub.is_drug = $is_drug
        """,
            id=s["id"], name=s["name"],
            name_ru=s.get("name_ru", s["name"]),
            category=s["category"],
            evidence_level=s["evidenceLevel"],
            dose_unit=s["doseUnit"],
            min_dose=s["minDose"], max_dose=s["maxDose"],
            default_dose=s["defaultDose"],
            bioavailability=s["bioavailability"],
            half_life_hours=s["halfLifeHours"],
            absorption_rate=s.get("absorptionRate", 0.1),
            elimination_rate=s.get("eliminationRate", 0.1),
            accumulation_threshold=s.get("accumulationThreshold", 0.0),
            is_drug=(s["category"] == "drug")
        )

        # Link to target organs
        for organ_slug in s.get("targetSystems", []):
            session.run("""
                MATCH (sub:Substance {id: $sub_id})
                MERGE (o:Organ {slug: $organ})
                MERGE (sub)-[:TARGETS]->(o)
            """, sub_id=s["id"], organ=organ_slug)

        # Create effects on biomarkers
        for biomarker_code, delta in s.get("effectProfile", {}).items():
            effect_id = f"{s['id']}::{biomarker_code}"
            effect_type = "benefit" if delta >= 0 else "harm"
            session.run("""
                MERGE (e:Effect {id: $id})
                SET e.delta = $delta, e.type = $type
                WITH e
                MATCH (sub:Substance {id: $sub_id})
                MERGE (sub)-[:HAS_EFFECT]->(e)
                WITH e
                MERGE (b:Biomarker {code: $code})
                MERGE (e)-[:ON_BIOMARKER]->(b)
            """, id=effect_id, delta=delta, type=effect_type, sub_id=s["id"], code=biomarker_code)

        print(f"  [SUB] {s['id']} ({s['category']}, {s['evidenceLevel']})")

    # Create interactions
    for ix in interactions:
        h = interaction_hash(ix["substanceA"], ix["substanceB"], ix["type"])
        session.run("""
            MERGE (i:Interaction {hash: $hash})
            SET i.type = $type,
                i.coefficient = $coefficient,
                i.description = $description
            WITH i
            MATCH (a:Substance {id: $sub_a})
            MATCH (b:Substance {id: $sub_b})
            MERGE (a)-[:INTERACTS_WITH {type: $type, coefficient: $coefficient}]->(b)
            MERGE (b)-[:INTERACTS_WITH {type: $type, coefficient: $coefficient}]->(a)
        """,
            hash=h, type=ix["type"],
            coefficient=ix.get("coefficient", 1.0),
            description=ix.get("description", ""),
            sub_a=ix["substanceA"], sub_b=ix["substanceB"]
        )
        print(f"  [IX] {ix['substanceA']} <-> {ix['substanceB']} ({ix['type']})")

    print(f"\n[DONE] Ingested {len(substances)} substances, {len(interactions)} interactions.")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    if not SUBSTANCES_FILE.exists():
        print(f"[ERROR] Not found: {SUBSTANCES_FILE}")
        print("[INFO] Run M3 to create substances.json first.")
        sys.exit(1)

    with SUBSTANCES_FILE.open(encoding="utf-8") as f:
        substances = json.load(f)

    interactions = []
    if INTERACTIONS_FILE.exists():
        with INTERACTIONS_FILE.open(encoding="utf-8") as f:
            interactions = json.load(f)

    print(f"[INFO] {len(substances)} substances, {len(interactions)} interactions")

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD"))
    )
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as session:
            ingest(session, substances, interactions, args.clear)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
