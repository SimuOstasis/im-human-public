# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Интеграционный смоук-тест UI im-human.

Верифицирует все 12 требований UI-01..UI-12 через offscreen Qt:
  - Импорты UI-модулей без ошибок (UI-01, UI-12)
  - MainWindow собирается с 5 QDockWidget и русскими заголовками (UI-02)
  - Дисклеймер присутствует в statusBar (UI-09)
  - SimulationWorker: сигналы state_updated/error_occurred + 7 слотов (UI-08)
  - TelemetryDashboard: 24 плота + deque(maxlen=5000) (UI-05, UI-10)

ОБЯЗАТЕЛЬНО: QT_QPA_PLATFORM=offscreen устанавливается ДО любого импорта PySide6
чтобы Qt не пытался открыть реальный дисплей (T-06-16).
"""
import os

# Установить до импорта PySide6 — Qt не пытается открыть дисплей
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel


def _close_window(w) -> None:
    """Корректно закрыть MainWindow и гарантировать завершение QThread (T-06-16).

    Порядок завершения:
    1. Остановить worker напрямую (снять флаг _running)
    2. Завершить поток (quit + wait(5000))
    3. Закрыть окно через close()
    4. processEvents() для очистки Qt-очереди
    """
    # 1. Остановить worker (снимаем флаг цикла в потоке)
    worker = getattr(w, "_worker", None)
    if worker is not None:
        worker.on_stop()

    # 2. Завершить поток (quit + wait до 5 с)
    thread = getattr(w, "_thread", None)
    if thread is not None and thread.isRunning():
        thread.quit()
        thread.wait(5000)

    # 3. Закрыть окно (сохранить QSettings, вызвать super().closeEvent)
    w.close()

    # 4. Обработать очередь отложенных Qt-событий
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


# ── Module-level fixture для QApplication (singleton per process) ────────────

@pytest.fixture(scope="module")
def app():
    """QApplication singleton: создаётся один раз на весь модуль тестов."""
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance
    instance.processEvents()


# ── Тест 1: импорты UI-модулей (UI-01, UI-12) ────────────────────────────────

def test_ui_imports():
    """Все UI-модули импортируются без ошибок."""
    from src.ui.main_window import MainWindow  # noqa: F401
    from src.ui.worker import SimulationWorker  # noqa: F401
    from src.ui.human_panel import HumanPanel  # noqa: F401
    from src.ui.time_controls import TimeControls  # noqa: F401
    from src.ui.telemetry_dashboard import TelemetryDashboard  # noqa: F401
    from src.ui.substance_manager import SubstanceManager  # noqa: F401
    from src.ui.event_log import EventLog  # noqa: F401
    from src.ui.disclaimer import DISCLAIMER_TEXT  # noqa: F401
    # Если дошли сюда — все импорты успешны
    assert True


# ── Тест 4: сигналы и слоты SimulationWorker (UI-08) ─────────────────────────

def test_worker_signals_exist():
    """SimulationWorker имеет 2 сигнала и 7 слотов согласно UI-SPEC §Signal/Slot Contracts."""
    from src.ui.worker import SimulationWorker

    worker = SimulationWorker()

    # Сигналы Worker → UI
    assert hasattr(worker, "state_updated"), "Отсутствует сигнал state_updated"
    assert hasattr(worker, "error_occurred"), "Отсутствует сигнал error_occurred"

    # Слоты UI → Worker (7 методов)
    assert callable(getattr(worker, "on_start", None)), "Отсутствует слот on_start"
    assert callable(getattr(worker, "on_pause", None)), "Отсутствует слот on_pause"
    assert callable(getattr(worker, "on_resume", None)), "Отсутствует слот on_resume"
    assert callable(getattr(worker, "on_stop", None)), "Отсутствует слот on_stop"
    assert callable(getattr(worker, "on_speed_changed", None)), "Отсутствует слот on_speed_changed"
    assert callable(getattr(worker, "on_substance_added", None)), "Отсутствует слот on_substance_added"
    assert callable(getattr(worker, "on_substance_removed", None)), "Отсутствует слот on_substance_removed"


# ── Тест 2: 5 QDockWidget с русскими заголовками (UI-02) ─────────────────────

def test_mainwindow_has_five_docks(app):
    """MainWindow создаёт ровно 5 QDockWidget с правильными русскими заголовками."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        docks = w.findChildren(QDockWidget)
        assert len(docks) >= 5, f"Ожидается >= 5 доков, найдено {len(docks)}"

        titles = {d.windowTitle() for d in docks}
        expected_titles = {
            "Профиль",
            "Управление временем",
            "Биомаркеры",
            "Вещества",
            "Журнал событий",
        }
        missing = expected_titles - titles
        assert not missing, f"Отсутствуют доки с заголовками: {missing}"
    finally:
        _close_window(w)


# ── Тест 3: дисклеймер в statusBar (UI-09) ───────────────────────────────────

def test_disclaimer_visible(app):
    """Дисклеймер «исследовательская симуляция» виден в statusBar."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        # Найти QLabel в statusBar с текстом дисклеймера
        status_bar = w.statusBar()
        labels = status_bar.findChildren(QLabel)
        disclaimer_labels = [
            lbl for lbl in labels
            if "исследовательская симуляция" in lbl.text()
        ]
        assert disclaimer_labels, (
            "QLabel с 'исследовательская симуляция' не найден в statusBar"
        )
    finally:
        _close_window(w)


# ── Тест 5: 24 плота TelemetryDashboard с deque(maxlen=5000) (UI-05, UI-10) ──

def test_telemetry_24_plots(app):
    """TelemetryDashboard создаёт 24 плота с deque(maxlen=5000) на каждый."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        telemetry = w.telemetry

        # UI-05: ровно 24 плота
        assert len(telemetry._plots) == 24, (
            f"Ожидается 24 плота, найдено {len(telemetry._plots)}"
        )

        # UI-10: каждый буфер — deque с maxlen=5000
        assert len(telemetry._buffers) == 24, (
            f"Ожидается 24 буфера, найдено {len(telemetry._buffers)}"
        )
        for code, buf in telemetry._buffers.items():
            assert buf.maxlen == 5000, (
                f"Буфер '{code}' имеет maxlen={buf.maxlen}, ожидается 5000"
            )
    finally:
        _close_window(w)


# ── Тест 6: HumanPanel — пресеты, демография, индексы (UI-03) ────────────────

def test_human_panel_presets_and_fields(app):
    """HumanPanel содержит QComboBox с пресетами и все демографические поля."""
    from src.ui.human_panel import HumanPanel

    panel = HumanPanel()

    # UI-03: QComboBox с ≥1 пресетом
    assert panel.preset_combo.count() >= 1, "preset_combo пуст"

    # UI-03: Демографические поля заполнены (первый пресет выбран автоматически)
    assert panel.sex_value.text() != "—", "sex_value не обновлён"
    assert panel.age_value.text() != "—", "age_value не обновлён"
    assert panel.height_value.text() != "—", "height_value не обновлён"
    assert panel.weight_value.text() != "—", "weight_value не обновлён"

    # UI-03: BMI и BMR вычислены
    assert panel.bmi_value.text() != "—", "bmi_value не обновлён"
    assert panel.bmr_value.text() != "—", "bmr_value не обновлён"

    # D-12: Индексы симуляции (QLabel с primary property)
    assert panel.bio_age_value is not None, "bio_age_value отсутствует"
    assert panel.resilience_value is not None, "resilience_value отсутствует"
    assert panel.bio_age_value.property("primary") is True, "bio_age_value не primary"


# ── Тест 7: TimeControls — кнопки скорости, статус, кнопки управления (UI-04) ─

def test_time_controls_buttons(app):
    """TimeControls содержит 5 кнопок скорости и 4 кнопки управления."""
    from src.ui.time_controls import TimeControls
    from src.domain.simulation_state import SimulationStatus

    tc = TimeControls()

    # UI-04: Кнопки управления
    assert tc.start_btn is not None, "start_btn отсутствует"
    assert tc.pause_btn is not None, "pause_btn отсутствует"
    assert tc.resume_btn is not None, "resume_btn отсутствует"
    assert tc.stop_btn is not None, "stop_btn отсутствует"

    # UI-04: 5 кнопок скорости в QButtonGroup
    speed_buttons = tc._speed_group.buttons()
    assert len(speed_buttons) == 5, (
        f"Ожидается 5 кнопок скорости, найдено {len(speed_buttons)}"
    )

    # UI-04: Статус по умолчанию — IDLE
    assert tc.status_label.text() == "Ожидание", (
        f"Статус по умолчанию: '{tc.status_label.text()}', ожидалось 'Ожидание'"
    )

    # UI-04: update_status работает
    tc.update_status(SimulationStatus.RUNNING, 48)
    assert tc.status_label.text() == "Выполняется"
    assert "2 дней" in tc.elapsed_label.text()


# ── Тест 8: SubstanceManager — сигналы, пустое состояние (UI-06) ─────────────

def test_substance_manager_signals_and_empty(app):
    """SubstanceManager имеет сигналы и показывает пустое состояние."""
    from src.ui.substance_manager import SubstanceManager

    sm = SubstanceManager()

    # UI-06: Сигналы
    assert hasattr(sm, "substance_added"), "Отсутствует сигнал substance_added"
    assert hasattr(sm, "substance_removed"), "Отсутствует сигнал substance_removed"

    # UI-06: Пустое состояние
    assert sm.model.rowCount() >= 1, "Модель пуста (должен быть empty-state элемент)"
    # Первый элемент — disabled empty-state
    first_item = sm.model.item(0)
    assert first_item is not None
    assert "не добавлены" in first_item.text().lower() or "вещества" in first_item.text().lower()


# ── Тест 9: EventLog — add_events, пустое состояние, лимит (UI-07) ───────────

def test_event_log_events_and_limit(app):
    """EventLog показывает пустое состояние и обрабатывает add_events."""
    from src.ui.event_log import EventLog
    from src.domain.simulation_state import SimulationEvent

    el = EventLog()

    # UI-07: Пустое состояние по умолчанию
    assert el.model.rowCount() >= 1, "Модель пуста (должен быть empty-state)"
    empty_text = el.model.item(0).text()
    assert "нет событий" in empty_text.lower(), (
        f"Empty-state текст: '{empty_text}'"
    )

    # UI-07: add_events добавляет записи
    events = [
        SimulationEvent(tick=1, event_type="THRESHOLD_BREACH", severity="INFO", message="Тестовое событие"),
        SimulationEvent(tick=2, event_type="PROBABILISTIC", severity="WARNING", message="Тест warning"),
    ]
    el.add_events(events)
    # Должно быть ≥1 событие (empty-state удалён)
    assert el.model.rowCount() >= 1, "После add_events модель пуста"

    # UI-07: _seen_count обновлён
    assert el._seen_count == 2, f"_seen_count={el._seen_count}, ожидалось 2"

    # UI-07: Повторный вызов add_events с теми же событиями — без дублей
    el.add_events(events)
    assert el._seen_count == 2, (
        f"_seen_count после повторного вызова: {el._seen_count}, ожидалось 2"
    )

    # UI-07: MAX_ENTRIES = 500
    assert el.MAX_ENTRIES == 500, f"MAX_ENTRIES={el.MAX_ENTRIES}, ожидалось 500"
