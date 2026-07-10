#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human - Create the Human database on the Neo4j server.

Must be run once before setup_schema.py.
Uses the system database to create Human.

Usage:
    cd W:\\Obsidian\\human\\.neo4j
    .\\venv\\Scripts\\python.exe create_database.py
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
    uri      = require_env("NEO4J_URI")
    user     = require_env("NEO4J_USER")
    password = require_env("NEO4J_PASSWORD")
    db_name  = os.environ.get("NEO4J_DATABASE", "Human")

    print(f"[INFO] Connecting to {uri}")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session(database="system") as session:
            result = session.run("SHOW DATABASES YIELD name RETURN name")
            existing = [r["name"].lower() for r in result]
            print(f"[INFO] Existing databases: {existing}")

            if db_name.lower() in existing:
                print(f"[OK] Database '{db_name}' already exists.")
            else:
                session.run(f"CREATE DATABASE `{db_name}` IF NOT EXISTS")
                print(f"[OK] Created database '{db_name}'.")

        # Verify we can connect to the new database
        with driver.session(database=db_name) as session:
            result = session.run("RETURN 1 AS ok")
            result.single()
            print(f"[OK] Connected to '{db_name}' successfully.")

        print("\n[DONE] Run setup_schema.py next.")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
