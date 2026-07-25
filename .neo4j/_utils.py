#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Shared utilities for .neo4j scripts."""
import os
import sys
from pathlib import Path


def load_dotenv(env_path: Path | None = None) -> None:
    path = env_path or Path(__file__).with_name(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("#")[0].strip()  # drop inline comment, e.g. "secret  # prod"
        os.environ.setdefault(key.strip(), value)


def require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"[ERROR] Missing required env var: {key}. Check .neo4j/.env")
        sys.exit(1)
    return val
