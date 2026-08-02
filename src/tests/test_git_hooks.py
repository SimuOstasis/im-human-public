# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
Регрессионные тесты для локального pre-push git-хука (FND-06, D-11).

Защищают от молчаливого удаления/выхолащивания `.githooks/pre-push` и
`tools/install_hooks.py`, реализующих локальный гейт «красный тест -> push
отклонён» (Phase 16, план 16-01). Все проверки — чтение содержимого файлов
по подстрокам; ни один тест не обращается к живой `git config` и не
запускает внешние процессы, чтобы не падать на GitHub Actions runner-е, где
инсталлятор не запускается (там нет активного core.hooksPath).
"""
from pathlib import Path

VAULT_ROOT = Path(__file__).parent.parent.parent
HOOK_PATH = VAULT_ROOT / ".githooks" / "pre-push"
INSTALLER_PATH = VAULT_ROOT / "tools" / "install_hooks.py"

# Устойчивая подстрока из заголовка хука, подтверждающая его обходимость
# (D-11: хук MUST NOT описываться как unbypassable гейт).
BYPASS_MARKER = "--no-verify"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pre_push_hook_exists():
    """.githooks/pre-push должен существовать на диске."""
    assert HOOK_PATH.exists(), f"Файл хука не найден: {HOOK_PATH}"


def test_pre_push_hook_runs_pytest():
    """Хук должен запускать pytest по пути src/tests."""
    content = _read(HOOK_PATH)
    assert "pytest" in content, (
        "'.githooks/pre-push' не содержит инвокацию pytest"
    )
    assert "src/tests" in content, (
        "'.githooks/pre-push' не запускает тесты по пути 'src/tests'"
    )


def test_pre_push_hook_documents_bypass():
    """Хук должен явно документировать свою обходимость (D-11)."""
    content = _read(HOOK_PATH)
    assert BYPASS_MARKER in content, (
        f"'.githooks/pre-push' не упоминает обход '{BYPASS_MARKER}' — "
        f"хук не должен описываться как unbypassable гейт (D-11)"
    )


def test_install_hooks_script_exists():
    """tools/install_hooks.py должен существовать и определять install_hooks/check_hooks."""
    assert INSTALLER_PATH.exists(), f"Файл инсталлятора не найден: {INSTALLER_PATH}"
    content = _read(INSTALLER_PATH)
    assert "core.hooksPath" in content, (
        "'tools/install_hooks.py' не содержит упоминания 'core.hooksPath'"
    )
    assert "def install_hooks" in content, (
        "'tools/install_hooks.py' не определяет функцию install_hooks"
    )
    assert "def check_hooks" in content, (
        "'tools/install_hooks.py' не определяет функцию check_hooks"
    )


def test_install_hooks_configures_hookspath():
    """Инсталлятор должен ссылаться на каталог .githooks и имя хука pre-push."""
    content = _read(INSTALLER_PATH)
    assert ".githooks" in content, (
        "'tools/install_hooks.py' не ссылается на каталог '.githooks'"
    )
    assert "pre-push" in content, (
        "'tools/install_hooks.py' не ссылается на имя хука 'pre-push'"
    )
