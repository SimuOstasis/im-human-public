# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
Тесты для фазы 08: проверка наличия и содержимого wiki-страниц документации.
GAP-01..GAP-05 — требования DOCS-05..DOCS-09.

Также содержит регрессионные тесты фазы 10 (HS-04, задача 10-04-01):
числовые утверждения в README.md/HOME.md/Known Limitations.md (кол-во
тестов, веществ, взаимодействий) должны совпадать с живым кодом/данными,
а не быть захардкожены и потому подверженными дрейфу.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = VAULT_ROOT / "06 - Engine"
ANALYSIS_DIR = VAULT_ROOT / "07 - Analysis"
DATA_DIR = VAULT_ROOT / "src" / "data"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# GAP-01 — DOCS-05: пять страниц движка с обязательными секциями и константами
# ---------------------------------------------------------------------------

ENGINE_PAGES = [
    "Homeostasis Model.md",
    "Interaction Resolver.md",
    "Event Detector.md",
    "Adaptive Stepper.md",
    "RNG Seeding.md",
]

REQUIRED_SECTIONS = ["## Параметры", "## Ограничения", "## Ссылки"]

PAGE_CONSTANTS = {
    "Homeostasis Model.md": "BASE_DRIFT_RATE",
    "Interaction Resolver.md": "TOXICITY_MULTIPLIER",
    "Event Detector.md": "CVD_BASE_10YR",
    "Adaptive Stepper.md": "should_dose",
    "RNG Seeding.md": ["get_state", "set_state", "Mersenne"],
}


def test_engine_wiki_pages_exist():
    """Все пять страниц движка должны существовать на диске."""
    for name in ENGINE_PAGES:
        path = ENGINE_DIR / name
        assert path.exists(), f"Страница движка не найдена: {path}"


def test_engine_wiki_pages_have_required_sections():
    """Каждая страница движка содержит ## Параметры, ## Ограничения, ## Ссылки."""
    for name in ENGINE_PAGES:
        content = _read(ENGINE_DIR / name)
        for section in REQUIRED_SECTIONS:
            assert section in content, (
                f"Секция '{section}' отсутствует в '{name}'"
            )


def test_engine_wiki_pages_have_key_constants():
    """Каждая страница содержит ожидаемую ключевую константу или термин."""
    for name, constant in PAGE_CONSTANTS.items():
        content = _read(ENGINE_DIR / name)
        if isinstance(constant, list):
            # хотя бы один из вариантов должен присутствовать
            assert any(c in content for c in constant), (
                f"Ни одна из констант {constant} не найдена в '{name}'"
            )
        else:
            assert constant in content, (
                f"Константа '{constant}' не найдена в '{name}'"
            )


# ---------------------------------------------------------------------------
# GAP-02 — DOCS-06: README.md содержит обязательные секции и команды
# ---------------------------------------------------------------------------

def test_readme_sections():
    """README.md содержит ## Установка и ## Быстрый старт."""
    content = _read(VAULT_ROOT / "README.md")
    assert "## Установка" in content, "README.md не содержит секцию '## Установка'"
    assert "## Быстрый старт" in content, "README.md не содержит секцию '## Быстрый старт'"


def test_readme_has_test_command():
    """README.md содержит команду pytest src/tests/."""
    content = _read(VAULT_ROOT / "README.md")
    assert "pytest src/tests/" in content, (
        "README.md не содержит команду 'pytest src/tests/'"
    )


def test_readme_has_main_command():
    """README.md содержит команду python src/main.py."""
    content = _read(VAULT_ROOT / "README.md")
    assert "python src/main.py" in content, (
        "README.md не содержит команду 'python src/main.py'"
    )


def test_readme_has_disclaimer():
    """README.md содержит текст дисклеймера об исследовательской симуляции."""
    content = _read(VAULT_ROOT / "README.md")
    # Принимаем оба возможных формата
    has_disclaimer = (
        "исследовательская симуляция" in content
        or "не медицинский диагностический инструмент" in content
        or "research simulation" in content.lower()
    )
    assert has_disclaimer, (
        "README.md не содержит текст дисклеймера об исследовательской симуляции"
    )


# ---------------------------------------------------------------------------
# GAP-03 — DOCS-07: User Guide.md существует и содержит секцию Экспорт
# ---------------------------------------------------------------------------

def test_user_guide_exists():
    """06 - Engine/User Guide.md должен существовать."""
    path = ENGINE_DIR / "User Guide.md"
    assert path.exists(), f"User Guide не найден: {path}"


def test_user_guide_has_export_section():
    """User Guide содержит слово 'Экспорт' или 'экспорт'."""
    content = _read(ENGINE_DIR / "User Guide.md")
    assert "кспорт" in content, (
        "User Guide.md не содержит упоминания экспорта"
    )


# ---------------------------------------------------------------------------
# GAP-04 — DOCS-08: Analysis pages содержат нужный контент
# ---------------------------------------------------------------------------

def test_analysis_pages_exist():
    """Simulation Assumptions.md и Known Limitations.md должны существовать."""
    for name in ["Simulation Assumptions.md", "Known Limitations.md"]:
        path = ANALYSIS_DIR / name
        assert path.exists(), f"Страница анализа не найдена: {path}"


def test_simulation_assumptions_has_determinism():
    """Simulation Assumptions.md содержит 'детерминизм' или 'тик'."""
    content = _read(ANALYSIS_DIR / "Simulation Assumptions.md")
    has_term = "детерминизм" in content or "тик" in content
    assert has_term, (
        "Simulation Assumptions.md не содержит 'детерминизм' или 'тик'"
    )


UNMODELED_FACTORS = ["циркадные", "генетические", "нелинейные", "ферменты", "каскады"]


def test_known_limitations_has_min_3_unmodeled_factors():
    """Known Limitations.md упоминает минимум 3 неучтённых фактора из списка."""
    content = _read(ANALYSIS_DIR / "Known Limitations.md")
    found = [f for f in UNMODELED_FACTORS if f in content]
    assert len(found) >= 3, (
        f"Known Limitations.md содержит только {len(found)} из требуемых 3 факторов. "
        f"Найдено: {found}"
    )


def test_known_limitations_mentions_v2_roadmap():
    """Known Limitations.md упоминает v2 или CGM/FHIR в дорожной карте."""
    content = _read(ANALYSIS_DIR / "Known Limitations.md")
    has_v2 = "v2" in content or "CGM" in content or "FHIR" in content
    assert has_v2, (
        "Known Limitations.md не содержит упоминания roadmap v2, CGM или FHIR"
    )


# ---------------------------------------------------------------------------
# GAP-05 — DOCS-09: HOME.md ссылается на все 8 новых страниц
# ---------------------------------------------------------------------------

HOME_PAGE_REFS = [
    "Homeostasis Model",
    "Interaction Resolver",
    "Event Detector",
    "Adaptive Stepper",
    "RNG Seeding",
    "User Guide",
    "Simulation Assumptions",
    "Known Limitations",
]


def test_home_md_references_all_8_pages():
    """HOME.md содержит упоминание всех 8 новых страниц документации."""
    content = _read(VAULT_ROOT / "HOME.md")
    missing = [ref for ref in HOME_PAGE_REFS if ref not in content]
    assert not missing, (
        f"HOME.md не содержит ссылки на страницы: {missing}"
    )


# ---------------------------------------------------------------------------
# Phase 10 (HS-04, task 10-04-01) — live numeric-drift regression tests.
#
# These derive the ground truth from live code/data at test-run time
# (never a hardcoded literal) so that any future change (a new substance,
# a new interaction, a growing test suite) that isn't reflected in the
# docs is caught automatically, instead of relying on a one-time manual
# audit that goes stale the moment the codebase moves on.
# ---------------------------------------------------------------------------

def _live_substance_count() -> int:
    with open(DATA_DIR / "substances.json", encoding="utf-8") as f:
        return len(json.load(f))


def _live_interaction_count() -> int:
    with open(DATA_DIR / "interactions.json", encoding="utf-8") as f:
        return len(json.load(f))


def _live_collected_test_count() -> int:
    """Derive the exact live pytest node count via `--collect-only -q`.

    Mirrors the exact method Plan 10-04 used (D-09/Pitfall 5): never trust
    a number from a planning doc, always re-derive it at execution time.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(VAULT_ROOT / "src" / "tests"), "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=str(VAULT_ROOT),
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    assert match, (
        f"Не удалось извлечь количество тестов из вывода --collect-only.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return int(match.group(1))


def test_readme_substance_count_matches_data():
    """README.md заголовок '### Вещества (N)' совпадает с len(substances.json)."""
    n = _live_substance_count()
    content = _read(VAULT_ROOT / "README.md")
    match = re.search(r"Вещества \((\d+)\)", content)
    assert match, "README.md не содержит заголовок в формате 'Вещества (N)'"
    assert int(match.group(1)) == n, (
        f"README.md указывает {match.group(1)} веществ, "
        f"а src/data/substances.json содержит {n}"
    )


def test_readme_interaction_count_matches_data():
    """README.md заголовок '...взаимодействия (N)' совпадает с len(interactions.json)."""
    n = _live_interaction_count()
    content = _read(VAULT_ROOT / "README.md")
    match = re.search(r"взаимодействия \((\d+)\)", content)
    assert match, "README.md не содержит заголовок в формате 'взаимодействия (N)'"
    assert int(match.group(1)) == n, (
        f"README.md указывает {match.group(1)} взаимодействий, "
        f"а src/data/interactions.json содержит {n}"
    )


def test_home_md_substance_count_matches_data():
    """HOME.md упоминания 'N веществ' совпадают с len(substances.json)."""
    n = _live_substance_count()
    content = _read(VAULT_ROOT / "HOME.md")
    matches = re.findall(r"(\d+)\s+веществ", content)
    assert matches, "HOME.md не содержит упоминания 'N веществ'"
    wrong = [m for m in matches if int(m) != n]
    assert not wrong, (
        f"HOME.md содержит устаревшие упоминания количества веществ {wrong}, "
        f"а src/data/substances.json содержит {n}"
    )


def test_known_limitations_interaction_count_matches_data():
    """Known Limitations.md 'N вручную закодированных взаимодействий' совпадает с данными."""
    n = _live_interaction_count()
    content = _read(ANALYSIS_DIR / "Known Limitations.md")
    match = re.search(r"(\d+)\s+вручную закодированных взаимодействий", content)
    assert match, (
        "Known Limitations.md не содержит фразу "
        "'N вручную закодированных взаимодействий'"
    )
    assert int(match.group(1)) == n, (
        f"Known Limitations.md указывает {match.group(1)} взаимодействий, "
        f"а src/data/interactions.json содержит {n}"
    )


def test_readme_test_count_matches_live_collection():
    """README.md указывает ТОЧНОЕ число тестов из живого --collect-only, без '~' приближений."""
    n = _live_collected_test_count()
    content = _read(VAULT_ROOT / "README.md")

    assert "~100" not in content, (
        "README.md всё ещё содержит устаревшее приближение '~100 тестов'"
    )
    assert not re.search(r"~\d+\s*тест", content), (
        "README.md содержит приближённое (не точное) число тестов"
    )

    # Digit-boundary-safe match (Rule 1 fix, mirrors
    # test_readme_test_file_count_matches_live_directory below): a naive
    # substring search for e.g. "185" would false-positive-match inside an
    # unrelated larger number (e.g. "1850"), so require the number is not
    # adjacent to other digits.
    pattern = r"(?<!\d)" + re.escape(str(n)) + r"(?!\d)"
    occurrences = [m.start() for m in re.finditer(pattern, content)]
    assert occurrences, (
        f"README.md не содержит точное живое число тестов ({n}), "
        f"полученное из 'pytest --collect-only -q'. Возможен дрейф "
        f"документации относительно живого набора тестов."
    )


def _live_test_file_count() -> int:
    """Count test_*.py files under src/tests/ (excludes __init__.py).

    D-11 (Phase 14): file-count half of the docs-drift CI gate. Mirrors
    _live_collected_test_count's discipline — the expected value is
    derived only from a live glob at test-run time, never a hardcoded
    literal, so it cannot go stale.
    """
    return len(list((VAULT_ROOT / "src" / "tests").glob("test_*.py")))


def test_readme_test_file_count_matches_live_directory():
    """README.md указывает ТОЧНОЕ живое число файлов тестов в src/tests/."""
    n = _live_test_file_count()
    content = _read(VAULT_ROOT / "README.md")
    # Digit-boundary-safe match (Rule 1 fix): a naive substring search for
    # e.g. "16" would false-positive-match inside an unrelated "163" (test
    # count), so require the number is not adjacent to other digits.
    pattern = r"(?<!\d)" + re.escape(str(n)) + r"(?!\d)"
    occurrences = [m.start() for m in re.finditer(pattern, content)]
    assert occurrences, (
        f"README.md не содержит точное живое число файлов тестов ({n}), "
        f"полученное из живого glob('test_*.py') в src/tests/. Возможен "
        f"дрейф документации относительно живой директории тестов."
    )
