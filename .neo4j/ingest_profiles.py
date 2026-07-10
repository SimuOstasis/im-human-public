#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Ingest preset HumanProfile nodes into Neo4j Human DB.

Reads src/data/presets.json, uses HumanProfile.from_preset() for computed
properties (bmi, bmr), and MERGEs one :HumanProfile node per preset.
Idempotent — safe to re-run (DUAL-LAYER layer 2, after Obsidian markdown).

Constraint `profile_id_unique` on :HumanProfile already defined in setup_schema.py
— do NOT add a duplicate here.

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe ingest_profiles.py
    .\\venv\\Scripts\\python.exe ingest_profiles.py --clear
"""

import json
import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

# .neo4j/ is 2 levels below vault root (.neo4j -> vault)
VAULT_ROOT = Path(__file__).parent.parent
DATA_FILE = VAULT_ROOT / "src" / "data" / "presets.json"

# Add vault root to sys.path so we can import src.domain.human_profile
if str(VAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(VAULT_ROOT))


def load_presets() -> dict:
    if not DATA_FILE.exists():
        print(f"[ERROR] Not found: {DATA_FILE}")
        sys.exit(1)
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


MERGE_QUERY = """
    MERGE (p:HumanProfile {profile_id: $profile_id})
    SET p.display_name = $display_name,
        p.sex = $sex,
        p.age = $age,
        p.height_cm = $height_cm,
        p.weight_kg = $weight_kg,
        p.bmi = $bmi,
        p.bmr = $bmr,
        p.physical_activity = $physical_activity,
        p.cardiovascular_risk = $cardiovascular_risk,
        p.diabetes_risk = $diabetes_risk,
        p.neurodegeneration_risk = $neurodegeneration_risk,
        p.liver_disease_risk = $liver_disease_risk,
        p.kidney_disease_risk = $kidney_disease_risk,
        p.organ_cardiovascular = $organ_cardiovascular,
        p.organ_liver = $organ_liver,
        p.organ_kidney = $organ_kidney,
        p.organ_nervous = $organ_nervous,
        p.organ_immune = $organ_immune,
        p.organ_metabolic = $organ_metabolic,
        p.organ_cellular_repair = $organ_cellular_repair,
        p.preset = true
"""


def ingest(session, data: dict, clear: bool) -> None:
    try:
        from src.domain.human_profile import HumanProfile
    except ImportError as exc:
        print(f"[ERROR] Cannot import HumanProfile: {exc}")
        print(f"[ERROR] VAULT_ROOT={VAULT_ROOT} — is src/domain/human_profile.py present?")
        sys.exit(1)

    # Collect all params first (before opening transaction) so import/preset
    # errors are raised before any Neo4j writes begin.
    all_params = []
    for preset in data.get("presets", []):
        profile_id = preset["profile_id"]

        # Use HumanProfile.from_preset as single source of truth for bmi/bmr (D-06)
        try:
            profile = HumanProfile.from_preset(profile_id)
        except (KeyError, FileNotFoundError) as exc:
            print(f"[ERROR] Cannot load preset '{profile_id}': {exc}")
            sys.exit(1)

        demo = preset["demographics"]
        predis = preset["predispositions"]
        organs = preset["organ_systems"]

        all_params.append({
            "profile_id":                profile_id,
            "display_name":              preset["display_name"],
            "sex":                       demo["sex"],
            "age":                       demo["age"],
            "height_cm":                 demo["height_cm"],
            "weight_kg":                 demo["weight_kg"],
            "bmi":                       profile.bmi,        # computed by HumanProfile
            "bmr":                       profile.bmr,        # computed by HumanProfile
            "physical_activity":         preset["lifestyle"]["physical_activity"],
            "cardiovascular_risk":       predis["cardiovascular_risk"],
            "diabetes_risk":             predis["diabetes_risk"],
            "neurodegeneration_risk":    predis["neurodegeneration_risk"],
            "liver_disease_risk":        predis["liver_disease_risk"],
            "kidney_disease_risk":       predis["kidney_disease_risk"],
            "organ_cardiovascular":      organs["cardiovascular"],
            "organ_liver":               organs["liver"],
            "organ_kidney":              organs["kidney"],
            "organ_nervous":             organs["nervous"],
            "organ_immune":              organs["immune"],
            "organ_metabolic":           organs["metabolic"],
            "organ_cellular_repair":     organs["cellular_repair"],
        })

    # Run all writes inside a single explicit transaction for atomicity (WR-01).
    with session.begin_transaction() as tx:
        if clear:
            print("[WARN] Clearing HumanProfile nodes...")
            tx.run("MATCH (n:HumanProfile) DETACH DELETE n")
        for params in all_params:
            tx.run(MERGE_QUERY, **params)
            print(f"  [PROFILE] {params['profile_id']}  bmi={params['bmi']}  bmr={params['bmr']}")
        tx.commit()

    print("")
    print(f"[DONE] Created/updated {len(all_params)} HumanProfile nodes.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest preset HumanProfile nodes into Neo4j Human DB."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="DELETE all :HumanProfile nodes before ingesting (destructive!)",
    )
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] neo4j package not found. Run: pip install neo4j")
        sys.exit(1)

    data = load_presets()
    print(f"[INFO] Loaded {len(data.get('presets', []))} presets from {DATA_FILE}")

    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD")),
    )
    try:
        with driver.session(
            database=os.environ.get("NEO4J_DATABASE", "Human")
        ) as session:
            ingest(session, data, args.clear)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
