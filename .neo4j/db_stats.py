#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Neo4j database statistics.

Usage:
    cd W:\Obsidian\human\.neo4j
    .\venv\Scripts\python.exe db_stats.py
"""

import os
import sys
from pathlib import Path

from _utils import load_dotenv, require_env

load_dotenv()

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] pip install neo4j")
    sys.exit(1)


def main() -> None:
    driver = GraphDatabase.driver(
        require_env("NEO4J_URI"),
        auth=(require_env("NEO4J_USER"), require_env("NEO4J_PASSWORD"))
    )
    db = os.environ.get("NEO4J_DATABASE", "Human")

    try:
        with driver.session(database=db) as session:
            print(f"[STATS] Database: {db}\n")

            # Node counts by label
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt "
                "ORDER BY cnt DESC"
            )
            print("Node counts:")
            for row in result:
                if row["label"]:
                    print(f"  {row['label']:30s} {row['cnt']:>6}")

            # Relationship counts
            result = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt "
                "ORDER BY cnt DESC"
            )
            print("\nRelationship counts:")
            for row in result:
                print(f"  {row['rel']:30s} {row['cnt']:>6}")

            # Index status
            try:
                result = session.run(
                    "SHOW INDEXES YIELD name, type, state, populationPercent "
                    "RETURN name, type, state, populationPercent "
                    "ORDER BY name"
                )
                print("\nIndexes:")
                for row in result:
                    pct = f"{row['populationPercent']:.1f}%" if row["populationPercent"] is not None else "n/a"
                    print(f"  {row['name']:40s} {row['type']:20s} {row['state']:10s} {pct}")
            except Exception as e:
                print(f"\nIndexes: (skipped — {e})")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
