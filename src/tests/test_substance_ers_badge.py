# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""TDD-гейт Phase 13 Plan 04: ERS-звёзды в списке веществ (D-07).

Покрывает 4 поведения:
    - до разрешения уровня — префикс отсутствует, текст строки не меняется
    - после _on_ers_ready(sub_id, level>=1) — префикс появляется (без выбора строки)
    - update_concentrations() сохраняет уже разрешённый префикс (Pitfall 3)
    - _on_ers_ready(sub_id, 0) — префикс НЕ добавляется (KB недоступна/нет фактов)

RED до Task 2 (Wave 0 гейт): все тесты падают, пока ErsBadgeWorker/_on_ers_ready
не реализованы в src/ui/substance_manager.py.

ОБЯЗАТЕЛЬНО: QT_QPA_PLATFORM=offscreen устанавливается ДО любого импорта PySide6
(паттерн test_kb_client.py).
"""
import os

# Установить до импорта PySide6 — Qt не пытается открыть дисплей
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.domain.substance import IntakeSchedule
from src.engine.kb_client import _ers_stars


# ── Module-level fixture для QApplication (singleton per process) ──────────────

@pytest.fixture(scope="module")
def app():
    """QApplication singleton: создаётся один раз на весь модуль тестов.

    Паттерн идентичен test_kb_client.py.
    """
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance
    instance.processEvents()


def _teardown_substance_manager(sm, app) -> None:
    """Завершить оба QThread (KB + ERS) и закрыть виджет.

    Зеркалирует teardown test_substance_manager_tabs (test_kb_client.py) — quit()+
    wait(5000) под guard'ом isRunning(), затем sm.close() + app.processEvents().
    Расширено для нового self._ers_thread (Task 2).
    """
    kb_worker = getattr(sm, "_kb_worker", None)
    if kb_worker is not None:
        kb_worker._cancelled = True
    kb_thread = getattr(sm, "_kb_thread", None)
    if kb_thread is not None and kb_thread.isRunning():
        kb_thread.quit()
        kb_thread.wait(5000)

    ers_thread = getattr(sm, "_ers_thread", None)
    if ers_thread is not None and ers_thread.isRunning():
        ers_thread.quit()
        ers_thread.wait(5000)

    sm.close()
    app.processEvents()


def _build_omega3_schedule(sm) -> IntakeSchedule:
    """Собрать валидное IntakeSchedule для "omega3" из каталога sm._substances."""
    sub = sm._substances["omega3"]
    return IntakeSchedule(
        substance_id="omega3",
        dose_mg=sub["defaultDose"],
        hour_of_day=8,
        min_dose=sub["minDose"],
        max_dose=sub["maxDose"],
    )


def _row_item_for(sm, sub_id: str):
    """Найти QStandardItem строки списка по substance_id (UserRole)."""
    from PySide6.QtCore import Qt  # noqa: PLC0415

    for row in range(sm.model.rowCount()):
        item = sm.model.item(row)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == sub_id:
            return item
    return None


# ── Тест 1: до разрешения уровня — текст без звёзд ─────────────────────────────

def test_badge_absent_before_resolution(app):
    """До вызова _on_ers_ready строка показывает ровно pre-Phase-13 текст,
    без звёзд ★/☆ — «без клика на вещество» ничего не должно появляться сверх
    существующего формата.
    """
    from src.ui.substance_manager import SubstanceManager  # noqa: PLC0415

    sm = SubstanceManager()
    try:
        schedule = _build_omega3_schedule(sm)
        sm.load_schedules([schedule])

        item = _row_item_for(sm, "omega3")
        assert item is not None, "Строка для omega3 должна существовать после load_schedules"

        name_ru = sm._substances["omega3"]["name_ru"]
        expected = f"{name_ru}: 0.000 (нет в плазме)"
        assert item.text() == expected, (
            f"До разрешения ERS текст строки должен быть ровно {expected!r}, "
            f"получено {item.text()!r}"
        )
        assert "★" not in item.text(), "Не должно быть закрашенных звёзд до разрешения"
        assert "☆" not in item.text(), "Не должно быть пустых звёзд-плейсхолдеров до разрешения"
    finally:
        _teardown_substance_manager(sm, app)


# ── Тест 2: после разрешения — звёздный префикс появляется ────────────────────

def test_badge_appears_after_resolution(app):
    """_on_ers_ready("omega3", 4) добавляет префикс _ers_stars(4) + пробел перед
    именем вещества, без необходимости выбирать строку.
    """
    from src.ui.substance_manager import SubstanceManager  # noqa: PLC0415

    sm = SubstanceManager()
    try:
        schedule = _build_omega3_schedule(sm)
        sm.load_schedules([schedule])

        sm._on_ers_ready("omega3", 4)

        item = _row_item_for(sm, "omega3")
        assert item is not None

        expected_prefix = f"{_ers_stars(4)} "
        assert item.text().startswith(expected_prefix), (
            f"Текст строки должен начинаться с {expected_prefix!r}, "
            f"получено {item.text()!r}"
        )
        assert "Омега-3" in item.text() or sm._substances["omega3"]["name_ru"] in item.text()
    finally:
        _teardown_substance_manager(sm, app)


# ── Тест 3: звёзды переживают тик симуляции (Pitfall 3) ────────────────────────

def test_badge_survives_tick(app):
    """update_concentrations() не должен стирать уже разрешённый звёздный префикс —
    это regression-гейт на Pitfall 3 (13-RESEARCH.md).
    """
    from src.ui.substance_manager import SubstanceManager  # noqa: PLC0415

    sm = SubstanceManager()
    try:
        schedule = _build_omega3_schedule(sm)
        sm.load_schedules([schedule])
        sm._on_ers_ready("omega3", 4)

        sm.update_concentrations({"omega3": 0.123})

        item = _row_item_for(sm, "omega3")
        assert item is not None

        expected_prefix = f"{_ers_stars(4)} "
        assert item.text().startswith(expected_prefix), (
            f"Префикс звёзд должен пережить update_concentrations, "
            f"получено {item.text()!r}"
        )
        assert "0.123" in item.text(), (
            f"Концентрация должна обновиться внутри той же строки, получено {item.text()!r}"
        )
    finally:
        _teardown_substance_manager(sm, app)


# ── Тест 4: уровень 0 — без звёзд (KB недоступна / нет фактов) ─────────────────

def test_level_zero_means_no_badge(app):
    """_on_ers_ready(sub_id, 0) — sentinel «нет данных» — не добавляет префикс."""
    from src.ui.substance_manager import SubstanceManager  # noqa: PLC0415

    sm = SubstanceManager()
    try:
        sub = sm._substances["vitamin_d3"]
        schedule = IntakeSchedule(
            substance_id="vitamin_d3",
            dose_mg=sub["defaultDose"],
            hour_of_day=8,
            min_dose=sub["minDose"],
            max_dose=sub["maxDose"],
        )
        sm.load_schedules([schedule])

        sm._on_ers_ready("vitamin_d3", 0)

        item = _row_item_for(sm, "vitamin_d3")
        assert item is not None

        assert "★" not in item.text(), "Уровень 0 не должен рисовать закрашенные звёзды"
        assert "☆" not in item.text(), "Уровень 0 не должен рисовать пустые звёзды-плейсхолдеры"
        name_ru = sub["name_ru"]
        assert item.text() == f"{name_ru}: 0.000 (нет в плазме)"
    finally:
        _teardown_substance_manager(sm, app)
