#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human - Ingest cross-links: set mortality_slug on :Substance and :Biomarker nodes.

One-shot script: adds the `mortality_slug` string property to existing Human DB nodes
so kb_client.py can look up facts in the Mortality KB without cross-database edges
(Neo4j Community Edition does not support Fabric / cross-DB traversal - D-09).

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe ingest_cross_links.py
    .\\venv\\Scripts\\python.exe ingest_cross_links.py --dry-run
    .\\venv\\Scripts\\python.exe ingest_cross_links.py --clear
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure the .neo4j/ directory is on sys.path so _utils is importable when this
# script is loaded via importlib from a different working directory (e.g. tests).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _utils import load_dotenv, require_env

load_dotenv()  # reads .neo4j/.env via _utils; no-op if file absent

# ---------------------------------------------------------------------------
# Slug mappings (D-10: hardcoded; verified against Mortality DB — Task 1 checkpoint)
# ---------------------------------------------------------------------------

# Only canonical pages from substantive Mortality sections are valid targets.
# Magnesium and berberine are absent because no canonical Mortality page exists.
# Slugs use path-prefix format (research/biology/, pathways/). Phase 13
# (D-09, live-verified 2026-07-19) re-pointed omega3/metformin/rapamycin from
# service/* stub pages to content-bearing research/biology/* pages; vitamin_d3/nmn
# were already correct and are unchanged.
SUBSTANCE_SLUG_MAP: dict[str, str] = {
    "omega3":       "research/biology/omega-3-research",
    "metformin":    "research/biology/metformin",
    "rapamycin":    "research/biology/rapamycin",
    "vitamin_d3":   "research/biology/vitamin-d3",
    "nmn":          "pathways/nmn-nr",
}

# 23 biomarker codes → Mortality DB slugs
# Most biomarker pages absent from Mortality KB (KB focuses on interventions, not biomarker refs)
# insulin-igf exists; others return graceful empty (0 facts) — acceptable per D-11
# restingHeartRate excluded — no confirmed slug (Task 1 checkpoint)
BIOMARKER_SLUG_MAP: dict[str, str] = {
    "ldlC":                        "service/ldl-cholesterol",
    "hdlC":                        "service/hdl-cholesterol",
    "triglycerides":               "service/triglycerides",
    "apoB":                        "service/apolipoprotein-b",
    "fastingGlucose":              "service/fasting-glucose",
    "fastingInsulin":              "service/insulin-igf",
    "homaIr":                      "service/homa-ir",
    "hba1c":                       "service/hba1c",
    "hsCrp":                       "service/hs-crp",
    "il6":                         "service/interleukin-6",
    "alt":                         "service/alt",
    "ast":                         "service/ast",
    "ggt":                         "service/ggt",
    "albumin":                     "service/albumin",
    "creatinine":                  "service/serum-creatinine",
    "egfr":                        "service/egfr",
    "urineAlbuminCreatinineRatio": "service/uacr",
    "sodium":                      "service/sodium",
    "potassium":                   "service/potassium",
    "hemoglobin":                  "service/hemoglobin",
    "vitaminD25Oh":                "service/25-oh-vitamin-d",
    "systolicBloodPressure":       "service/systolic-blood-pressure",
    "hrvRmssd":                    "service/hrv-rmssd",
}


# ---------------------------------------------------------------------------
# Core ingest function
# ---------------------------------------------------------------------------

def ingest(session, *, human_db: str = "Human", clear: bool = False) -> None:
    """Set mortality_slug on :Substance and :Biomarker nodes in Human DB.

    Parameters
    ----------
    session:
        Active Neo4j session (already opened on the Human database).
    human_db:
        Database name (informational — caller opens the session on the correct DB).
    clear:
        If True, remove existing mortality_slug from all :Substance and :Biomarker
        nodes before re-applying the mappings.
    """
    if clear:
        print("[INFO] --clear: removing existing mortality_slug from :Substance nodes...")
        session.run("MATCH (s:Substance) WHERE s.mortality_slug IS NOT NULL REMOVE s.mortality_slug")
        print("[INFO] --clear: removing existing mortality_slug from :Biomarker nodes...")
        session.run("MATCH (b:Biomarker) WHERE b.mortality_slug IS NOT NULL REMOVE b.mortality_slug")

    # --- Substances ---
    sub_hit = 0
    for sub_id, slug in SUBSTANCE_SLUG_MAP.items():
        result = session.run(
            "MATCH (s:Substance {id: $id}) SET s.mortality_slug = $slug",
            id=sub_id,
            slug=slug,
        )
        props_set = int(result.consume().counters.properties_set)
        if props_set > 0:
            sub_hit += 1
        else:
            print(f"[WARN] Substance not found in Human DB: id={sub_id!r} (slug={slug!r})", file=sys.stderr)

    print(f"[INFO] Substances: {sub_hit}/{len(SUBSTANCE_SLUG_MAP)} mortality_slug set")

    # --- Biomarkers ---
    bio_hit = 0
    for code, slug in BIOMARKER_SLUG_MAP.items():
        result = session.run(
            "MATCH (b:Biomarker {code: $code}) SET b.mortality_slug = $slug",
            code=code,
            slug=slug,
        )
        props_set = int(result.consume().counters.properties_set)
        if props_set > 0:
            bio_hit += 1
        else:
            print(f"[WARN] Biomarker not found in Human DB: code={code!r} (slug={slug!r})", file=sys.stderr)

    print(f"[INFO] Biomarkers: {bio_hit}/{len(BIOMARKER_SLUG_MAP)} mortality_slug set")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set mortality_slug on :Substance/:Biomarker nodes in Human DB."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove existing mortality_slug before re-applying mappings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print mappings without writing to Neo4j.",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no writes to Neo4j ===")
        print(f"\nSUBSTANCE_SLUG_MAP ({len(SUBSTANCE_SLUG_MAP)} entries):")
        for k, v in SUBSTANCE_SLUG_MAP.items():
            print(f"  {k!r:30s} → {v!r}")
        print(f"\nBIOMARKER_SLUG_MAP ({len(BIOMARKER_SLUG_MAP)} entries):")
        for k, v in BIOMARKER_SLUG_MAP.items():
            print(f"  {k!r:40s} → {v!r}")
        return

    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ImportError:
        print("[ERROR] neo4j driver not installed. Run: pip install neo4j", file=sys.stderr)
        sys.exit(1)

    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD")),
    )
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as session:
            ingest(session, human_db=os.environ.get("NEO4J_DATABASE", "Human"), clear=args.clear)
    except ServiceUnavailable:
        # T-07-03: do not log password or URI details
        print("[ERROR] Neo4j is unavailable. Check that the database is running.", file=sys.stderr)
        sys.exit(1)
    except AuthError:
        # T-07-03: do not log credentials
        print("[ERROR] Neo4j authentication failed. Check NEO4J_USER/NEO4J_PASSWORD in .neo4j/.env.", file=sys.stderr)
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
