#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human - Neo4j connection check.

Verifies connectivity to both Human and Mortality databases.

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe check_connection.py
"""

import os
import sys

from _utils import load_dotenv

load_dotenv()

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] neo4j package not found. Run: pip install neo4j")
    sys.exit(1)


def check_db(uri: str, user: str, password: str, database: str, label: str) -> bool:
    print(f"\n[CHECK] {label} — {uri} / {database}")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            total = result.single()["total"]
            print(f"  [OK] Connected. Total nodes: {total}")

            try:
                result = session.run("SHOW INDEXES YIELD name, type, state RETURN name, type, state LIMIT 10")
                rows = list(result)
                if rows:
                    print(f"  [OK] Indexes ({len(rows)} found):")
                    for row in rows:
                        print(f"       {row['name']} ({row['type']}) — {row['state']}")
                else:
                    print("  [INFO] No indexes yet (run setup_schema.py)")
            except Exception as e:
                print(f"  [INFO] Index listing skipped: {e}")

        driver.close()
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def main() -> None:
    ok_human = check_db(
        uri=os.environ.get("NEO4J_URI", ""),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", ""),
        database=os.environ.get("NEO4J_DATABASE", "Human"),
        label="Human DB",
    )

    ok_mortality = check_db(
        uri=os.environ.get("MORTALITY_NEO4J_URI", os.environ.get("NEO4J_URI", "")),
        user=os.environ.get("MORTALITY_NEO4J_USER", "neo4j"),
        password=os.environ.get("MORTALITY_NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "")),
        database=os.environ.get("MORTALITY_NEO4J_DATABASE", "Mortality"),
        label="Mortality KB (read-only)",
    )

    print()
    if ok_human and ok_mortality:
        print("[DONE] Both databases reachable.")
        sys.exit(0)
    elif ok_human:
        print("[WARN] Human DB OK, Mortality KB unreachable (cross-references will be skipped).")
        sys.exit(0)
    else:
        print("[FAIL] Human DB unreachable. Check .env and Neo4j server.")
        sys.exit(1)


if __name__ == "__main__":
    main()
