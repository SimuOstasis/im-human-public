# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Активация локального pre-push git-хука (FND-06, D-11).

Хук .githooks/pre-push — ЛОКАЛЬНЫЙ гейт, не гейт на стороне GitHub;
границы и обходимость (`git push --no-verify`) описаны в его собственном
заголовке. Эта утилита выполняет одноразовую активацию
`git config core.hooksPath .githooks` на текущей машине: после свежего
клонирования репозитория её нужно запустить заново — активация является
частью локальной git-конфигурации и не переносится вместе с историей.

Usage (PowerShell, из корня репозитория):
    venv\\Scripts\\python.exe tools/install_hooks.py            # установка
    venv\\Scripts\\python.exe tools/install_hooks.py --check    # только проверка
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).parent.parent

HOOKS_DIR = ".githooks"
HOOK_NAME = "pre-push"


def install_hooks(repo_root: Path) -> int:
    """Активирует core.hooksPath=.githooks. Возвращает 0 при успехе."""
    hook_path = repo_root / HOOKS_DIR / HOOK_NAME
    if not hook_path.exists():
        print(f"install_hooks: файл хука не найден: {hook_path}", file=sys.stderr)
        return 1

    if os.name != "nt":
        current_mode = hook_path.stat().st_mode
        hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result = subprocess.run(
        ["git", "config", "core.hooksPath", HOOKS_DIR],
        cwd=str(repo_root),
        check=True,
    )
    print(
        f"install_hooks: core.hooksPath установлен в '{HOOKS_DIR}' "
        f"(код возврата git config: {result.returncode})"
    )
    return 0


def check_hooks(repo_root: Path) -> int:
    """Проверяет активацию core.hooksPath, ничего не меняя. 0 = активен."""
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    current = result.stdout.strip()
    if current == HOOKS_DIR:
        print(f"check_hooks: core.hooksPath активен ('{current}')")
        return 0
    print(
        f"check_hooks: core.hooksPath НЕ активен "
        f"(текущее значение: '{current or '(не задано)'}')",
        file=sys.stderr,
    )
    return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Активация локального pre-push git-хука im-human (FND-06)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверить активацию core.hooksPath, не изменяя конфигурацию",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.check:
        sys.exit(check_hooks(VAULT_ROOT))
    sys.exit(install_hooks(VAULT_ROOT))


if __name__ == "__main__":
    main()
