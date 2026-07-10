# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
Тесты для фазы 08: проверка наличия и содержимого wiki-страниц документации.
GAP-01..GAP-05 — требования DOCS-05..DOCS-09.
"""
from pathlib import Path

VAULT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = VAULT_ROOT / "06 - Engine"
ANALYSIS_DIR = VAULT_ROOT / "07 - Analysis"


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
