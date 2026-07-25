#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human - One-shot cleanup: remove the stale evidence_level property/index
from :Substance nodes in the Human DB (Phase 13, D-01/D-10).

sub.evidence_level and the substance_evidence index were a literal duplication
of substance evidence levels inside the Human DB (Success Criterion 2
violation, found by discuss/research). ingest_substances.py/setup_schema.py
no longer write/declare them (see Task 2) — this script sheds the property
from nodes created by prior ingest runs. Idempotent: safe to re-run, a
no-op once the Human DB is clean. The mortality KB is not touched.

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe remove_substance_evidence.py
    .\\venv\\Scripts\\python.exe remove_substance_evidence.py --dry-run
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
# Cypher statements (parameterless — no user-supplied data, T-13-01)
# ---------------------------------------------------------------------------

_REMOVE_EVIDENCE_LEVEL = (
    "MATCH (s:Substance) WHERE s.evidence_level IS NOT NULL "
    "REMOVE s.evidence_level"
)
_DROP_SUBSTANCE_EVIDENCE_INDEX = "DROP INDEX substance_evidence IF EXISTS"


# ---------------------------------------------------------------------------
# Core cleanup function
# ---------------------------------------------------------------------------

def remove(session, *, human_db: str = "Human") -> None:
    """Remove the stale evidence_level property and its index from :Substance.

    Parameters
    ----------
    session:
        Active Neo4j session (already opened on the Human database).
    human_db:
        Database name (informational — caller opens the session on the correct DB).

    Neo4j Community Edition forbids REMOVE and DROP INDEX in the same
    auto-commit transaction step, so these run as two separate session.run
    calls.
    """
    result = session.run(_REMOVE_EVIDENCE_LEVEL)
    # IN-04: properties_set is the correct counter for REMOVE too — the driver
    # has no separate properties_removed attribute (verified against the
    # installed neo4j driver; see 13-REVIEW.md IN-04). Do not "fix" this to
    # properties_removed — that attribute does not exist and would raise
    # AttributeError on every run.
    props_removed = int(result.consume().counters.properties_set)
    print(f"[INFO] evidence_level removed from {props_removed} :Substance node(s)")

    session.run(_DROP_SUBSTANCE_EVIDENCE_INDEX)
    print("[INFO] substance_evidence index dropped (if it existed)")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove the stale evidence_level property/index from :Substance nodes in Human DB."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the statements without writing to Neo4j.",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no writes to Neo4j ===")
        print(f"\n{_REMOVE_EVIDENCE_LEVEL}")
        print(f"\n{_DROP_SUBSTANCE_EVIDENCE_INDEX}")
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
            remove(session, human_db=os.environ.get("NEO4J_DATABASE", "Human"))
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
