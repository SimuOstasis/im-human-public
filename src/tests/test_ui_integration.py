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
from pathlib import Path

# Установить до импорта PySide6 — Qt не пытается открыть дисплей
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtCore import QThread
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel


def _wait_until(condition, signal, timeout_ms: int = 5000) -> bool:
    """Дождаться выполнения condition, просыпаясь по signal (WR-05, 10-REVIEW.md).

    Раньше тесты busy-poll'или реальный фоновый QThread через
    time.monotonic()-дедлайн + app.processEvents() + time.sleep(0.02) — под
    CI-нагрузкой/contention 5-секундный бюджет мог исчерпаться из-за
    планировщика, а не из-за реальной регрессии, давая недетерминированный
    падающий тест. QSignalSpy.wait() блокирует именно до следующего
    испускания signal (или таймаута), так что тест реагирует на прогресс
    worker'а сразу же, а не по произвольному wall-clock тику.
    """
    spy = QSignalSpy(signal)
    deadline = time.monotonic() + (timeout_ms / 1000)
    while not condition():
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        spy.wait(min(remaining_ms, 500))
    return condition()


def _close_window(w) -> None:
    """Корректно закрыть MainWindow и гарантировать завершение QThread (T-06-16).

    Порядок завершения:
    1. Остановить worker напрямую (снять флаг _running)
    2. Завершить поток (quit + wait(5000))
    3. Закрыть окно через close()
    4. processEvents() для очистки Qt-очереди
    """
    # 1. Остановить worker (снимаем флаг цикла в потоке). shutdown() (не
    # on_stop()!) — on_stop() больше не завершает run()'s цикл (иначе повторный
    # «Запустить» после «Стоп» не работал бы в реальном приложении).
    worker = getattr(w, "_worker", None)
    if worker is not None:
        worker.shutdown()

    # 2. Завершить поток (quit + wait до 5 с)
    thread = getattr(w, "_thread", None)
    if thread is not None and thread.isRunning():
        thread.quit()
        # WR-02 (17-REVIEW.md): не отбрасывать результат wait() — если
        # завершение QThread когда-нибудь регрессирует, этот helper (finally
        # почти каждого UI-теста в файле) должен упасть на месте, а не молча
        # продолжить с живым потоком, который зомби-утечёт в следующие тесты.
        stopped = thread.wait(5000)
        assert stopped, "Worker QThread did not stop within 5s in test teardown (leak risk)"

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


# ── Тест 10: dark.qss — структура и цветовые токены (UI-11) ──────────────────

def test_dark_qss_structure():
    """dark.qss существует и содержитrequired color tokens per UI-SPEC §Color.

    Проверяет:
    - Файл существует
    - Наличие (минимум 1 вхождение) каждого требуемого цветового токена
    - Наличие селектора QDockWidget::title

    WR-06 (10-REVIEW.md): раньше проверялись точные количества вхождений
    (== 7/12/14/18/1), что делало тест хрупким к любому не связанному
    изменению stylesheet, повторно использующему существующий токен ещё в
    одном месте. Тест — "структурный" smoke test (см. docstring), а не
    линтер точных инвариантов стиля, поэтому проверяем только присутствие
    (>= 1) нужных токенов/селекторов.
    """
    qss_path = Path(__file__).resolve().parent.parent / "ui" / "styles" / "dark.qss"
    assert qss_path.exists(), f"dark.qss не найден: {qss_path}"

    content = qss_path.read_text(encoding="utf-8")

    # Цветовые токены — присутствие (UI-SPEC §Color Token Map)
    assert content.count("#1e1e1e") >= 1, "Отсутствует #1e1e1e (primary background)"
    assert content.count("#2d2d2d") >= 1, "Отсутствует #2d2d2d (secondary background)"
    assert content.count("#3daee9") >= 1, "Отсутствует #3daee9 (accent)"
    assert content.count("#e0e0e0") >= 1, "Отсутствует #e0e0e0 (text)"
    assert content.count("#cf6679") >= 1, "Отсутствует #cf6679 (critical)"

    # Ключевые селекторы
    assert "QDockWidget::title" in content, (
        "Отсутствует селектор QDockWidget::title в dark.qss"
    )


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
    assert "2 дня" in tc.elapsed_label.text()  # IN-01: 2 -> "дня", not "дней"


# ── Тест 8: SubstanceManager — сигналы, пустое состояние (UI-06) ─────────────

def test_substance_manager_signals_and_empty(app):
    """SubstanceManager имеет сигналы и показывает пустое состояние."""
    from src.ui.substance_manager import SubstanceManager

    sm = SubstanceManager()

    try:
        # UI-06: Сигналы
        assert hasattr(sm, "substance_added"), "Отсутствует сигнал substance_added"
        assert hasattr(sm, "substance_removed"), "Отсутствует сигнал substance_removed"

        # UI-06: Пустое состояние
        assert sm.model.rowCount() >= 1, "Модель пуста (должен быть empty-state элемент)"
        # Первый элемент — disabled empty-state
        first_item = sm.model.item(0)
        assert first_item is not None
        assert "не добавлены" in first_item.text().lower() or "вещества" in first_item.text().lower()
    finally:
        # Очистить KB thread если запущен (T-06-16 — иначе GC уничтожит работающий QThread)
        kb_worker = getattr(sm, "_kb_worker", None)
        if kb_worker is not None:
            kb_worker._cancelled = True
        kb_thread = getattr(sm, "_kb_thread", None)
        if kb_thread is not None and kb_thread.isRunning():
            kb_thread.quit()
            kb_thread.wait(5000)
        sm.close()
        app.processEvents()


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


# ── Тест 11: EventLog — MAX_ENTRIES enforcement при переполнении (UI-07) ──────

def test_event_log_max_entries_enforcement(app):
    """EventLog удаляет старые записи при добавлении > MAX_ENTRIES событий.

    Проверяет:
    - После добавления 500 событий — ровно 500 строк
    - После добавления 501 события — всё ещё 500 строк (старые удалены)
    - Новейшее событие (501-е) вверху (row 0)
    - Самое старое событие (1-е) удалено снизу
    """
    from src.ui.event_log import EventLog
    from src.domain.simulation_state import SimulationEvent

    el = EventLog()

    # Создать ровно 500 событий и добавить
    events = [
        SimulationEvent(tick=i, event_type="TEST", severity="INFO", message=f"Ev{i}")
        for i in range(500)
    ]
    el.add_events(events)
    assert el.model.rowCount() == 500, (
        f"После 500 событий: rowCount={el.model.rowCount()}, ожидалось 500"
    )

    # Добавить 501-е событие — лимит должен сработать
    events.append(
        SimulationEvent(tick=500, event_type="TEST", severity="INFO", message="Ev500")
    )
    el.add_events(events)

    # rowCount не должен превысить MAX_ENTRIES
    assert el.model.rowCount() <= el.MAX_ENTRIES, (
        f"После переполнения: rowCount={el.model.rowCount()}, "
        f"лимит {el.MAX_ENTRIES} нарушен"
    )

    # Новейшее событие — вверху (insertRow 0)
    top_text = el.model.item(0).text()
    assert "Ev500" in top_text, (
        f"Новейшее событие Ev500 должно быть вверху, найдено: '{top_text}'"
    )

    # Самое старое событие (Ev0) должно быть удалено снизу
    bottom_text = el.model.item(el.model.rowCount() - 1).text()
    assert "Ev0" not in bottom_text, (
        f"Самое старое событие Ev0 должно быть удалено, найдено внизу: '{bottom_text}'"
    )

    # _seen_count корректен
    assert el._seen_count == 501, (
        f"_seen_count={el._seen_count}, ожидалось 501"
    )


# ── Тест 12-14: SimulationWorker.on_load + SubstanceManager schedules (HS-01, Phase 10) ─

def test_worker_on_load_reassigns_engine():
    """on_load пересоздаёт self._engine на свежем worker (регрессия Pitfall 1).

    До фикса: on_start()'s SimulationState-ветка НЕ пересоздаёт self._engine,
    оставляя run()-цикл заблокированным навсегда на `if ... or self._engine is None: continue`.
    """
    from src.ui.worker import SimulationWorker
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile, seed=42)
    state = engine.initialize()

    worker = SimulationWorker()
    # on_start никогда не вызывался — worker._engine должен быть None до on_load
    assert worker._engine is None, "Предусловие теста нарушено: _engine не None до on_load"

    worker.on_load((state, profile, []))

    assert worker._engine is not None, (
        "Pitfall 1 регрессия: on_load не пересоздал self._engine — run() зависнет навсегда"
    )
    assert worker._state is state, "on_load не установил self._state в загруженный state"
    assert worker._profile is profile, "on_load не установил self._profile в загруженный profile"


def test_worker_on_load_restores_schedules():
    """on_load атомарно заменяет self._schedules загруженным списком (Pitfall 2)."""
    from src.ui.worker import SimulationWorker
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile
    from src.domain.substance import IntakeSchedule

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile, seed=42)
    state = engine.initialize()

    schedule = IntakeSchedule(
        substance_id="omega3",
        dose_mg=2000,
        hour_of_day=8,
        min_dose=500,
        max_dose=4000,
    )

    worker = SimulationWorker()
    worker.on_load((state, profile, [schedule]))

    assert worker._schedules == [schedule], (
        f"on_load не восстановил schedules: {worker._schedules!r}, ожидалось [{schedule!r}]"
    )


def test_substance_manager_schedules_roundtrip(app):
    """SubstanceManager.load_schedules/get_schedules — round-trip списка (Pitfall 2, Save/Load)."""
    from src.ui.substance_manager import SubstanceManager
    from src.domain.substance import IntakeSchedule

    sm = SubstanceManager()

    try:
        schedule = IntakeSchedule(
            substance_id="omega3",
            dose_mg=2000,
            hour_of_day=8,
            min_dose=500,
            max_dose=4000,
        )

        sm.load_schedules([schedule])
        assert sm.get_schedules() == [schedule], (
            f"get_schedules после load_schedules([schedule]) вернул {sm.get_schedules()!r}"
        )
        assert sm.model.rowCount() == 1, (
            f"После load_schedules с 1 расписанием rowCount={sm.model.rowCount()}, ожидалось 1"
        )

        sm.load_schedules([])
        assert sm.get_schedules() == [], (
            f"get_schedules после load_schedules([]) вернул {sm.get_schedules()!r}, ожидалось []"
        )
        assert sm.model.rowCount() >= 1, "После load_schedules([]) пустое состояние не показано"
        first_item = sm.model.item(0)
        assert first_item is not None
        assert "не добавлены" in first_item.text().lower(), (
            f"Ожидался empty-state текст, найдено: '{first_item.text()}'"
        )
    finally:
        # Очистить KB thread если запущен (T-06-16 — иначе GC уничтожит работающий QThread)
        kb_worker = getattr(sm, "_kb_worker", None)
        if kb_worker is not None:
            kb_worker._cancelled = True
        kb_thread = getattr(sm, "_kb_thread", None)
        if kb_thread is not None and kb_thread.isRunning():
            kb_thread.quit()
            kb_thread.wait(5000)
        sm.close()
        app.processEvents()


# ── Тест 15-18: Файл-меню — Save/Load handlers, gating, error (HS-01, Phase 10 Plan 02) ─

def test_save_writes_loadable_snapshot(app, tmp_path, monkeypatch):
    """_on_save_requested пишет JSON-снепшот, который round-trip'ится через load_simulation."""
    from src.ui.main_window import MainWindow
    from src.engine import exporter
    from src.engine.simulation_engine import SimulationEngine

    w = MainWindow()
    try:
        snap_path = tmp_path / "snap.json"
        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(snap_path), ""),
        )

        profile = w._current_profile
        assert profile is not None, "Предусловие теста нарушено: _current_profile не установлен"
        engine = SimulationEngine(profile, seed=42)
        state = engine.initialize()
        w._on_state_updated(state)

        w._on_save_requested()

        assert snap_path.exists(), "Файл снепшота не создан"
        loaded_state, loaded_profile, loaded_schedules = exporter.load_simulation(snap_path)
        assert loaded_state is not None
        assert loaded_profile is not None
        assert loaded_schedules == []
    finally:
        _close_window(w)


def test_load_restores_state(app, tmp_path, monkeypatch):
    """_on_load_requested восстанавливает engine в Worker и расписания в SubstanceManager."""
    from src.ui.main_window import MainWindow
    from src.engine import exporter
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.substance import IntakeSchedule

    w = MainWindow()
    try:
        profile = w._current_profile
        assert profile is not None
        engine = SimulationEngine(profile, seed=42)
        state = engine.initialize()

        schedule = IntakeSchedule(
            substance_id="omega3",
            dose_mg=2000,
            hour_of_day=8,
            min_dose=500,
            max_dose=4000,
        )

        snap_path = tmp_path / "snap.json"
        exporter.save_simulation(state, profile, [schedule], snap_path)

        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(snap_path), ""),
        )

        w._on_load_requested()

        assert w._worker._engine is not None, (
            "Pitfall 1 регрессия на уровне UI: load не пересоздал Worker._engine"
        )
        assert w.substances.get_schedules() == [schedule], (
            f"get_schedules после load: {w.substances.get_schedules()!r}, ожидалось [{schedule!r}]"
        )
    finally:
        _close_window(w)


def test_menu_gating_when_running(app):
    """Файл→Сохранить/Загрузить отключены при RUNNING, включены иначе (D-02)."""
    from src.ui.main_window import MainWindow
    from src.domain.simulation_state import SimulationStatus

    w = MainWindow()
    try:
        w._last_sim_status = SimulationStatus.RUNNING
        w._update_menu_gating()
        assert w._save_action.isEnabled() is False, "Сохранить должно быть отключено при RUNNING"
        assert w._load_action.isEnabled() is False, "Загрузить должно быть отключено при RUNNING"

        w._last_sim_status = SimulationStatus.PAUSED
        w._update_menu_gating()
        assert w._save_action.isEnabled() is True, "Сохранить должно быть включено при не-RUNNING"
        assert w._load_action.isEnabled() is True, "Загрузить должно быть включено при не-RUNNING"
    finally:
        _close_window(w)


def test_menu_reenabled_after_stop_confirm(app, monkeypatch):
    """Файл→Сохранить/Загрузить включаются обратно после Стоп→Подтвердить (регрессия).

    Баг: _on_stop_requested() вызывал Worker.on_stop(), после чего run() навсегда
    завершает цикл и больше НИКОГДА не эмитит state_updated. Раз UI полагался
    только на этот сигнал для обновления _last_sim_status/_update_menu_gating(),
    меню оставалось отключено бессрочно после любого Стоп→Подтвердить — реальный
    пользователь не мог сохранить/загрузить после единственной остановки симуляции.
    """
    from src.ui.main_window import MainWindow
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.simulation_state import SimulationStatus
    from PySide6.QtWidgets import QMessageBox

    w = MainWindow()
    try:
        profile = w._current_profile
        assert profile is not None
        engine = SimulationEngine(profile, seed=42)
        state = engine.initialize()  # initialize() уже возвращает статус RUNNING
        w._on_state_updated(state)
        assert w._last_sim_status == SimulationStatus.RUNNING
        assert w._save_action.isEnabled() is False, "Предусловие: RUNNING должен отключать меню"

        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.exec",
            lambda self: QMessageBox.StandardButton.Ok,
        )
        w._on_stop_requested()

        assert w._last_sim_status == SimulationStatus.STOPPED, (
            f"_last_sim_status после Stop+Confirm: {w._last_sim_status!r}, ожидалось STOPPED"
        )
        assert w._save_action.isEnabled() is True, "Сохранить должно включиться обратно после Stop"
        assert w._load_action.isEnabled() is True, "Загрузить должно включиться обратно после Stop"
        # 2026-07-13: по решению пользователя «Новая» полностью сбрасывает
        # показатели, включая _current_state → None (а не оставляет его в
        # STOPPED) — Save сразу после «Новая» должен честно сказать «Нет
        # данных», а не тихо сохранить устаревший day-N снепшот, который уже
        # не соответствует обнулённым графикам/лейблам (см. test_new_
        # simulation_resets_all_indicators для полной проверки сброса).
        assert w._current_state is None, (
            "_current_state должен стать None после «Новая», иначе Save "
            "молча сохранит устаревшие показатели вместо честного «Нет данных»"
        )
    finally:
        _close_window(w)


def test_new_simulation_resets_all_indicators(app, monkeypatch):
    """Файл→«Новая» сбрасывает ВСЕ показатели к дефолту, не только статус (по решению пользователя, 2026-07-13).

    До этого фикса «Новая»/«Сброс» меняла только FSM-статус — графики
    биомаркеров, возраст/устойчивость, журнал событий, концентрации веществ
    и счётчик модельного времени продолжали показывать данные последнего
    тика до следующего Start. Теперь всё сбрасывается сразу по подтверждению.
    """
    from src.ui.main_window import MainWindow
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.simulation_state import SimulationStatus
    from src.domain.substance import IntakeSchedule
    from PySide6.QtWidgets import QMessageBox

    w = MainWindow()
    try:
        profile = w._current_profile
        assert profile is not None

        # Симулировать «есть данные»: тикнувшее состояние + добавленное вещество
        # с ненулевой концентрацией — напрямую, без реального QThread (быстрее,
        # детерминированнее; корректность самого тикания уже покрыта другими тестами).
        engine = SimulationEngine(profile, seed=42)
        state = engine.initialize()
        state = engine.tick(state, [])
        state = engine.tick(state, [])
        w._on_state_updated(state)

        schedule = IntakeSchedule(
            substance_id="omega3", dose_mg=2000, hour_of_day=8, min_dose=500, max_dose=4000,
        )
        w.substances.load_schedules([schedule])
        w.substances.update_concentrations({"omega3": 1.5})

        # Предусловия: данные реально отображаются перед сбросом
        assert w._current_state.tick_count > 0
        assert any(len(buf) > 0 for buf in w.telemetry._buffers.values()), (
            "Предусловие: буферы графиков должны содержать точки после тиков"
        )
        omega3_row_text_before = w.substances.model.item(0).text()
        assert "0.000" not in omega3_row_text_before, (
            f"Предусловие: концентрация должна отображаться ненулевой, получили {omega3_row_text_before!r}"
        )

        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.exec",
            lambda self: QMessageBox.StandardButton.Ok,
        )
        w._new_simulation_action.trigger()

        # Проверка сброса всех показателей
        assert w._current_state is None
        assert w.human_panel.bio_age_value.text() == "—", "biologicalAge должен сброситься на плейсхолдер"
        assert w.human_panel.resilience_value.text() == "—", "resilience должен сброситься на плейсхолдер"
        assert all(len(buf) == 0 for buf in w.telemetry._buffers.values()), (
            "Все буферы графиков биомаркеров должны быть очищены"
        )
        assert w.event_log._seen_count == 0, "Журнал событий должен сброситься"
        omega3_row_text_after = w.substances.model.item(0).text()
        assert "0.000 (нет в плазме)" in omega3_row_text_after, (
            f"Концентрация вещества должна сброситься на 0, получили {omega3_row_text_after!r}"
        )
        assert w.substances.get_schedules() == [schedule], (
            "Список добавленных веществ — это настройка, не прогресс; «Новая» не должна его стирать"
        )
        assert w._current_profile is not None, "Выбранный профиль — настройка, не прогресс; не должен сбрасываться"
        assert w.time_controls.status_label.text() == "Сброшено"
        assert "0 дней" in w.time_controls.elapsed_label.text()

        # Save сразу после «Новая» должен честно сказать «Нет данных», не сохранять устаревшее
        info_calls = []
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.information",
            lambda *a, **k: info_calls.append(a),
        )
        w._on_save_requested()
        assert len(info_calls) == 1, "Save сразу после «Новая» должен показать «Нет данных», не открывать диалог сохранения файла"
    finally:
        _close_window(w)


def test_restart_after_stop_resumes_ticking(app, monkeypatch):
    """Клик «Запустить» после «Стоп» реально возобновляет тики (регрессия).

    Баг: on_stop() выставляла self._worker._running = False — условие выхода
    из run()'s while-цикла. run() — обычный Python-метод, подключённый к
    QThread.started (эмитится один раз за жизнь потока, повторно не
    вызывается) — однажды завершившись, run() никогда не перезапускается.
    Итог: после единственного «Стоп» повторный «Запустить» оставался активен
    и как будто срабатывал (внутреннее состояние worker'а обновлялось), но ни
    один тик больше не выполнялся и UI не обновлялся вообще.
    """
    from src.ui.main_window import MainWindow
    from src.domain.simulation_state import SimulationStatus
    from PySide6.QtWidgets import QMessageBox

    w = MainWindow()
    try:
        w._on_start_requested(None)
        _wait_until(
            lambda: w._last_sim_status == SimulationStatus.RUNNING,
            w._worker.state_updated,
        )
        assert w._last_sim_status == SimulationStatus.RUNNING, "Предусловие: 1й Start не запустился"
        assert w._worker._running is True

        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.exec",
            lambda self: QMessageBox.StandardButton.Ok,
        )
        w._on_stop_requested()
        assert w._worker._running is True, (
            "on_stop() не должна завершать run()'s цикл — иначе повторный Start не сработает"
        )
        assert w._worker._state is None and w._worker._engine is None, (
            "on_stop() должна полностью очистить _state/_engine (регрессия #2: иначе "
            "idle-ветка run() периодически ре-эмитит старые данные поверх UI-сброса)"
        )

        w._on_start_requested(None)
        assert w._worker._state is not None and w._worker._state.status == SimulationStatus.RUNNING, (
            "on_start() после Stop должен подготовить новый RUNNING-снепшот"
        )
        assert w._worker._state.tick_count == 0, "Новый прогон должен начинаться с tick_count=0"

        _wait_until(
            lambda: w._worker._state.tick_count > 0,
            w._worker.state_updated,
        )
        assert w._worker._state.tick_count > 0, (
            f"Тики не возобновились после повторного Start: tick_count={w._worker._state.tick_count}"
        )
    finally:
        _close_window(w)


def test_new_simulation_menu_action_replaces_stop_button(app, monkeypatch):
    """Файл→«Новая» скрывает stop_btn, всегда активна, повторяет confirm-диалог.

    Кнопка «Сброс» убрана с панели управления временем (по решению
    пользователя, 2026-07-13) в пользу пункта меню «Файл→Новая» с тем же
    необратимым действием. По отдельному решению пользователя «Новая» НЕ
    гейтится статусом симуляции (в отличие от старой кнопки «Сброс») —
    доступна всегда, включая IDLE/STOPPED, когда сбрасывать нечего;
    _on_stop_requested() в этом случае безопасно no-op'ится (worker._state и
    self._current_state оба None).
    """
    from src.ui.main_window import MainWindow
    from src.domain.simulation_state import SimulationStatus
    from PySide6.QtWidgets import QMessageBox

    w = MainWindow()
    try:
        assert w.time_controls.stop_btn.isVisible() is False, (
            "«Сброс» должен быть скрыт с панели управления временем"
        )
        assert w._new_simulation_action.isEnabled() is True, (
            "«Новая» должна быть активна даже при IDLE (по решению пользователя)"
        )

        # Клик при IDLE (нечего сбрасывать) — безопасный no-op, не должен падать
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.exec",
            lambda self: QMessageBox.StandardButton.Ok,
        )
        w._new_simulation_action.trigger()
        assert w._new_simulation_action.isEnabled() is True, (
            "«Новая» должна остаться активна после no-op триггера при IDLE"
        )

        w._on_start_requested(None)
        _wait_until(
            lambda: w._last_sim_status == SimulationStatus.RUNNING,
            w._worker.state_updated,
        )
        assert w._new_simulation_action.isEnabled() is True, "«Новая» активна при RUNNING"

        w._new_simulation_action.trigger()

        assert w._last_sim_status == SimulationStatus.STOPPED, (
            "Триггер «Новая» должен пройти тот же путь, что и старая кнопка «Сброс»"
        )
        assert w._new_simulation_action.isEnabled() is True, (
            "«Новая» должна остаться активна после подтверждения (STOPPED)"
        )
        assert w._save_action.isEnabled() is True and w._load_action.isEnabled() is True
    finally:
        _close_window(w)


def test_load_error_is_caught(app, tmp_path, monkeypatch):
    """Повреждённый/несовместимый файл не роняет UI, пишется в EventLog, состояние не меняется (D-03)."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        corrupt_path = tmp_path / "corrupt.json"
        corrupt_path.write_text('{"version": "0.0"}', encoding="utf-8")

        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(corrupt_path), ""),
        )
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.warning",
            lambda *a, **k: None,
        )

        state_before = w._worker._state

        # Must not raise
        w._on_load_requested()

        assert w._worker._state is state_before, (
            "Состояние Worker изменилось после ошибки загрузки (D-03 нарушен)"
        )
        top_item = w.event_log.model.item(0)
        assert top_item is not None
        assert "версия" in top_item.text().lower(), (
            f"Ошибка версии не записана в EventLog: '{top_item.text() if top_item else None}'"
        )
    finally:
        _close_window(w)


def test_save_error_is_caught(app, tmp_path, monkeypatch):
    """save_simulation, упавший с OSError, не роняет UI; путь к файлу — в сообщении (D-01/D-02)."""
    from src.ui.main_window import MainWindow
    from src.engine.simulation_engine import SimulationEngine

    w = MainWindow()
    try:
        profile = w._current_profile
        assert profile is not None, "Предусловие теста нарушено: _current_profile не установлен"
        engine = SimulationEngine(profile, seed=42)
        state = engine.initialize()
        w._on_state_updated(state)

        save_path = tmp_path / "out.json"
        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(save_path), ""),
        )

        def _raise_os_error(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(
            "src.ui.main_window.save_simulation",
            _raise_os_error,
        )

        captured: dict = {}
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.warning",
            lambda *a, **k: captured.setdefault("args", a),
        )

        # Must not raise
        w._on_save_requested()

        assert "args" in captured, "QMessageBox.warning не был вызван при ошибке сохранения"
        body = captured["args"][-1]
        assert str(save_path) in body, (
            f"Путь к файлу не найден в сообщении об ошибке сохранения (D-02): '{body}'"
        )
    finally:
        _close_window(w)


# ── Тест 19-21: HumanPanel — ≈ маркер и Known-Limitations tooltip (HS-02, Phase 10 Plan 03) ─

def test_bio_age_shows_approx_and_tooltip(app):
    """bio_age_value отображается с ≈ и содержит tooltip про ориентировочный индекс (D-04/D-06)."""
    from src.ui.human_panel import HumanPanel

    panel = HumanPanel()
    panel.update_indices(45.0, 0.82)

    assert panel.bio_age_value.text().startswith("≈"), (
        f"bio_age_value должен начинаться с ≈, найдено: '{panel.bio_age_value.text()}'"
    )
    tooltip = panel.bio_age_value.toolTip()
    assert tooltip, "bio_age_value: tooltip пуст"
    assert "Known Limitations" in tooltip, (
        f"bio_age_value: tooltip не ссылается на Known Limitations: '{tooltip}'"
    )
    assert "ориентировочный" in tooltip.lower(), (
        f"bio_age_value: tooltip не содержит 'ориентировочный': '{tooltip}'"
    )


def test_resilience_shows_approx_and_tooltip(app):
    """resilience_value отображается с ≈ и содержит tooltip про Known Limitations (D-05/D-06)."""
    from src.ui.human_panel import HumanPanel

    panel = HumanPanel()
    panel.update_indices(45.0, 0.82)

    assert panel.resilience_value.text().startswith("≈"), (
        f"resilience_value должен начинаться с ≈, найдено: '{panel.resilience_value.text()}'"
    )
    tooltip = panel.resilience_value.toolTip()
    assert "Known Limitations" in tooltip, (
        f"resilience_value: tooltip не ссылается на Known Limitations: '{tooltip}'"
    )


def test_indices_none_placeholder(app):
    """При None значениях оба лейбла показывают '—' без ≈ (плейсхолдер не изменён)."""
    from src.ui.human_panel import HumanPanel

    panel = HumanPanel()
    panel.update_indices(None, None)

    assert panel.bio_age_value.text() == "—", (
        f"bio_age_value при None должен быть '—', найдено: '{panel.bio_age_value.text()}'"
    )
    assert panel.resilience_value.text() == "—", (
        f"resilience_value при None должен быть '—', найдено: '{panel.resilience_value.text()}'"
    )


# ── Тест 22: EventLog empty-state текст зависит от SimulationStatus (D-01/D-09, Wave 0) ─

def test_event_log_status_dependent_empty_text(app):
    """EventLog empty-state текст меняется по SimulationStatus (D-01/D-09).

    IDLE/STOPPED -> "Нет событий. Запустите симуляцию."
    RUNNING/PAUSED (без реальных событий) -> "Симуляция выполняется. Событий пока нет."
    Тексты — дословная копия из 10.1-UI-SPEC.md §Copywriting Contract, менять
    по смыслу нельзя (10.1-CONTEXT.md §specifics).

    RED (Wave 0): `EventLog.set_status()` — целевой публичный API D-01, ещё не
    реализован в текущем коде (10.1-RESEARCH.md Code Example 1). Конкретный
    механизм проброса статуса на усмотрение исполнителя Wave 2 — если он
    выберет другой публичный API, этот тест адаптируется вместе с ним.
    """
    from src.ui.event_log import EventLog
    from src.domain.simulation_state import SimulationStatus

    el = EventLog()

    el.set_status(SimulationStatus.RUNNING)
    empty_text = el.model.item(el.model.rowCount() - 1).text()
    assert empty_text == "Симуляция выполняется. Событий пока нет.", (
        f"RUNNING empty-state текст: '{empty_text}'"
    )

    el.set_status(SimulationStatus.PAUSED)
    empty_text = el.model.item(el.model.rowCount() - 1).text()
    assert empty_text == "Симуляция выполняется. Событий пока нет.", (
        f"PAUSED empty-state текст: '{empty_text}'"
    )

    el.set_status(SimulationStatus.IDLE)
    empty_text = el.model.item(el.model.rowCount() - 1).text()
    assert empty_text == "Нет событий. Запустите симуляцию.", (
        f"IDLE empty-state текст: '{empty_text}'"
    )

    el.set_status(SimulationStatus.STOPPED)
    empty_text = el.model.item(el.model.rowCount() - 1).text()
    assert empty_text == "Нет событий. Запустите симуляцию.", (
        f"STOPPED empty-state текст: '{empty_text}'"
    )


# ── Тест 23: TelemetryDashboard — окно отображения ≤300 точек (D-02, Wave 0) ─

def test_telemetry_display_buffer_capped_at_300(app):
    """Кривая графика показывает не более 300 последних точек (D-02).

    Guard-тест: текущий код уже режет `list(buf)[-300:]`
    (telemetry_dashboard.py:227), поэтому может проходить и до фикса
    D-02 — назначение: зафиксировать контракт «окно отображения ≤300 точек»
    как регрессионную защиту при замене среза на `itertools.islice`/
    `deque(maxlen=300)` (см. 10.1-RESEARCH.md Code Example 2). Буфер
    `self._buffers` (maxlen=5000) продолжает хранить полную историю — это
    не проверяется здесь (уже покрыто test_telemetry_24_plots).
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    code = "sodium"

    for i in range(400):
        dash.update({code: float(i)})

    assert len(dash._buffers[code]) == 400, (
        f"Полный буфер '{code}' должен хранить все 400 точек, найдено {len(dash._buffers[code])}"
    )

    _x_data, y_data = dash._curves[code].getData()
    assert len(y_data) <= 300, (
        f"Отображаемая кривая '{code}' содержит {len(y_data)} точек, ожидается <= 300"
    )


# ── Тест 24: TelemetryDashboard — фиксированный Y-диапазон + clip/downsample (D-03, Wave 0) ─

def test_telemetry_fixed_yrange_and_clip_downsample_enabled(app):
    """Кривая графика имеет clipToView/autoDownsample включены, Y-диапазон фиксирован (D-03).

    ОБЯЗАТЕЛЬНО проверять `curve.opts['clipToView']`/`['autoDownsample']`
    напрямую, а не визуальный результат — pyqtgraph 0.14.0's
    `PlotItem.addItem()` безусловно перезаписывает эти опции значениями по
    умолчанию, если они переданы как kwargs в `plot.plot(...)` вместо явных
    вызовов `curve.setClipToView()`/`setDownsampling()` ПОСЛЕ `plot.plot()`
    (10.1-RESEARCH.md Pitfall 1 — эмпирически подтверждённая ловушка).

    `sodium` выбран как код с обеими конечными границами в одной зоне
    (`optimal: {"min": 136, "max": 145}`, единственная зона в
    reference_ranges.json для этого кода) — не требует особого fallback-
    алгоритма для открытых границ (Pitfall 2), упрощает тест.

    RED (Wave 0): текущий код не задаёт clipToView/autoDownsample/fixed Y-range.
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    code = "sodium"

    curve = dash._curves[code]
    assert curve.opts["clipToView"] is True, (
        f"curve.opts['clipToView'] для '{code}': {curve.opts['clipToView']!r}, ожидалось True (D-03)"
    )
    assert curve.opts["autoDownsample"] is True, (
        f"curve.opts['autoDownsample'] для '{code}': {curve.opts['autoDownsample']!r}, ожидалось True (D-03)"
    )

    plot = dash._plots[code]
    autorange_enabled = plot.getViewBox().autoRangeEnabled()
    assert autorange_enabled[1] is False, (
        f"Y-автодиапазон для '{code}' должен быть выключен (D-03), autoRangeEnabled={autorange_enabled!r}"
    )


# ── Тест 25: TimeControls — QSS repolish только при смене статуса (D-04, Wave 0) ─

def test_time_controls_repolish_only_on_status_change(app):
    """_apply_button_states repolish'ит 4 кнопки только при смене статуса (D-04).

    Текст (status_label/elapsed_label) обновляется КАЖДЫЙ вызов, вне
    зависимости от repolish-гейта. RED (Wave 0): текущий код
    (_apply_button_states, time_controls.py:226-229) безусловно
    unpolish/polish'ит 4 кнопки на каждый вызов, даже без смены статуса.
    """
    from unittest.mock import patch
    from src.ui.time_controls import TimeControls
    from src.domain.simulation_state import SimulationStatus

    tc = TimeControls()  # __init__ уже применил IDLE до начала патча ниже

    style_cls = type(tc.start_btn.style())
    with patch.object(style_cls, "unpolish") as mock_unpolish, \
         patch.object(style_cls, "polish") as mock_polish:

        # Тот же статус (IDLE), что уже применён в __init__ — НЕ должен реполишить
        tc.update_status(SimulationStatus.IDLE, 0)
        assert mock_unpolish.call_count == 0, (
            f"repolish вызван при неизменном статусе IDLE->IDLE: unpolish x{mock_unpolish.call_count} (D-04)"
        )
        assert tc.status_label.text() == "Ожидание", "текст статуса должен обновляться каждый вызов"

        # Реальная смена статуса — ДОЛЖЕН реполишить
        tc.update_status(SimulationStatus.RUNNING, 24)
        assert mock_unpolish.call_count > 0, (
            "repolish должен произойти при реальной смене статуса IDLE->RUNNING (D-04)"
        )
        assert mock_polish.call_count == mock_unpolish.call_count, (
            "unpolish и polish должны вызываться парой на каждую кнопку"
        )
        assert tc.status_label.text() == "Выполняется"
        assert "1 день" in tc.elapsed_label.text()  # IN-01: 1 -> "день", not "дней"

        # Тот же статус (RUNNING->RUNNING) — НЕ должен реполишить повторно
        calls_after_change = mock_unpolish.call_count
        tc.update_status(SimulationStatus.RUNNING, 48)
        assert mock_unpolish.call_count == calls_after_change, (
            "repolish не должен повториться при неизменном статусе RUNNING->RUNNING (D-04)"
        )
        assert "2 дня" in tc.elapsed_label.text(), "текст времени должен обновиться, даже без repolish"  # IN-01


# ── Тест 26: SimulationWorker — снапшот состояния через deep copy (D-06, Wave 0) ─

def test_worker_snapshot_is_deep_copy():
    """Снапшот состояния, пересекающий границу Worker->UI, не расшаривает dict (D-06).

    T-10.1-01 (threat_model): гонка данных Worker-поток(пишет)/UI-поток(читает)
    на вложенном `biomarker_values` dict устраняется `model_copy(deep=True)`.

    RED (Wave 0): `SimulationWorker.get_state_snapshot()` сейчас возвращает
    `self._state` НАПРЯМУЮ (без копии вообще, см. worker.py docstring) —
    `snapshot is state`, `biomarker_values` полностью расшарен. Target (D-06,
    10.1-CONTEXT.md): снапшот, читаемый UI-потоком, должен быть независимой
    `model_copy(deep=True)` копией — эта проверка не трогает
    worker._running/shutdown() (worker.py докстринг «Регрессия #1/#2»).
    Конкретный механизм (внутри run()'s emit и/или get_state_snapshot()) —
    на усмотрение исполнителя Wave 2; если он выберет другой публичный путь,
    тест адаптируется вместе с ним (аналогично D-01, см. 10.1-RESEARCH.md
    Assumption A2).
    """
    from src.ui.worker import SimulationWorker
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    worker = SimulationWorker()
    worker.on_start(profile)

    state = worker._state
    snapshot = worker.get_state_snapshot()

    assert snapshot is not state, (
        "get_state_snapshot() вернул self._state напрямую, а не независимый снапшот (D-06)"
    )
    assert snapshot.biomarker_values is not state.biomarker_values, (
        "snapshot.biomarker_values расшарен с оригиналом self._state.biomarker_values (D-06)"
    )


# ── Тест 27: MainWindow — переключение скорости отзывчиво во время RUNNING (D-08, Wave 0) ─

def test_speed_switch_responsive_during_running(app):
    """Переключение скорости x10000->x1000 во время RUNNING не блокирует UI (D-08).

    Живой QThread реально крутит суб-батчи на x10000 (не мок) — измеряется
    время самого DirectConnection-слота `on_speed_changed`, а не доставка
    сигнала (10.1-RESEARCH.md Pattern 1: торможение приходит от GIL-конкуренции
    с тик-циклом worker.py, а не от очереди сигналов, DirectConnection
    мгновенна). Порог 0.5с — щедрый, чтобы не флейкать под CI-нагрузкой;
    тест в первую очередь измеряет и защищает от подвисания, не гонится за
    точным числом (10.1-CONTEXT.md D-08 не фиксирует жёсткий порог).
    """
    import time as time_module
    from src.ui.main_window import MainWindow
    from src.domain.simulation_state import SimulationStatus

    w = MainWindow()
    try:
        w._on_start_requested(None)
        _wait_until(
            lambda: w._last_sim_status == SimulationStatus.RUNNING,
            w._worker.state_updated,
        )

        w._worker.on_speed_changed(10000)
        _wait_until(
            lambda: w._worker._state is not None and w._worker._state.tick_count > 0,
            w._worker.state_updated,
        )

        start = time_module.perf_counter()
        w._worker.on_speed_changed(1000)
        elapsed = time_module.perf_counter() - start

        assert elapsed < 0.5, (
            f"on_speed_changed занял {elapsed:.3f}с во время RUNNING x10000 "
            f"— щедрый порог 0.5с (D-08) превышен"
        )
    finally:
        _close_window(w)


# ── Тест 28: TelemetryDashboard.export_all (HF-01, Phase 12 Plan 02) ─────────

def test_batch_export_writes_files(app, tmp_path):
    """export_all("PNG", tmp_path) создаёт 24 .png с именами {код}_{ts}.png (D-05)."""
    import re

    from src.ui.telemetry_dashboard import TelemetryDashboard

    dashboard = TelemetryDashboard()
    try:
        ok, total, errors = dashboard.export_all("PNG", tmp_path)

        assert errors == [], f"Неожиданные ошибки экспорта: {errors}"
        assert ok == 24, f"Ожидалось 24 успешных экспорта, получено {ok}"
        assert total == 24, f"Ожидалось total=24, получено {total}"

        png_files = list(tmp_path.glob("*.png"))
        assert len(png_files) == 24, (
            f"Ожидалось 24 .png файла в tmp_path, найдено {len(png_files)}"
        )

        name_re = re.compile(r"^[A-Za-z0-9]+_\d{8}_\d{4}\.png$")
        codes_from_files = set()
        timestamps = set()
        for f in png_files:
            assert name_re.match(f.name), f"Имя файла не соответствует схеме {{код}}_{{ts}}.png: {f.name}"
            code, ts = f.stem.split("_", 1)
            codes_from_files.add(code)
            timestamps.add(ts)

        assert codes_from_files == set(dashboard._plots.keys()), (
            "Коды в именах файлов не совпадают с self._plots.keys() (D-05 — не хардкод)"
        )
        assert len(timestamps) == 1, (
            f"Ожидался единый timestamp на весь прогон, найдено {len(timestamps)}: {timestamps}"
        )
    finally:
        dashboard.close()
        app.processEvents()


def test_batch_export_svg_format(app, tmp_path):
    """export_all("SVG", tmp_path) создаёт .svg-файлы по той же схеме имени."""
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dashboard = TelemetryDashboard()
    try:
        ok, total, errors = dashboard.export_all("SVG", tmp_path)

        assert errors == []
        assert ok == 24
        assert total == 24
        svg_files = list(tmp_path.glob("*.svg"))
        assert len(svg_files) == 24, f"Ожидалось 24 .svg файла, найдено {len(svg_files)}"
    finally:
        dashboard.close()
        app.processEvents()


def test_batch_export_min_resolution(app, tmp_path):
    """export_all() рендерит PNG/SVG с длинной стороной >= 1024px (G-12-3).

    Регресс-тест на нативный ре-рендер (не апскейл): PNG-длинная сторона
    и SVG root-width должны быть >= 1024px (фактически == EXPORT_TARGET_WIDTH_PX),
    а не on-screen размер мини-плота (~200px). Размер проверяется через уже
    запиненный PySide6 QImage (PNG) и stdlib xml.etree.ElementTree (SVG) —
    без новой зависимости.
    """
    import re
    import xml.etree.ElementTree

    from PySide6.QtGui import QImage

    from src.ui.telemetry_dashboard import EXPORT_TARGET_WIDTH_PX, TelemetryDashboard

    dashboard = TelemetryDashboard()
    try:
        dashboard.export_all("PNG", tmp_path)
        png_path = next(tmp_path.glob("*.png"))
        img = QImage(str(png_path))
        long_side = max(img.width(), img.height())
        assert long_side >= 1024, (
            f"Длинная сторона PNG {long_side}px < 1024px (ожидалось >= "
            f"EXPORT_TARGET_WIDTH_PX={EXPORT_TARGET_WIDTH_PX})"
        )

        dashboard.export_all("SVG", tmp_path)
        svg_path = next(tmp_path.glob("*.svg"))
        root = xml.etree.ElementTree.parse(svg_path).getroot()
        width_attr = root.get("width")
        if width_attr is None:
            view_box = root.get("viewBox", "").split()
            width_attr = view_box[2] if len(view_box) >= 3 else "0"
        match = re.match(r"[\d.]+", width_attr)
        width = float(match.group()) if match else 0.0
        assert width >= 1024, (
            f"Ширина SVG {width}px < 1024px (ожидалось >= "
            f"EXPORT_TARGET_WIDTH_PX={EXPORT_TARGET_WIDTH_PX})"
        )
    finally:
        dashboard.close()
        app.processEvents()


# ── Тест 23-24: «Файл → Экспорт всех графиков» — меню/обработчик (HF-01, Phase 12 Plan 02) ─

def test_batch_export_empty_guard(app, monkeypatch):
    """0-plot guard срабатывает ДО открытия диалога формата (UI-SPEC порядок шаг 1)."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        # Опустошить _plots, имитируя повреждённый/отсутствующий biomarkers.json (CR-03).
        monkeypatch.setattr(w.telemetry, "_plots", {})

        def _fail_if_called(*a, **k):
            raise AssertionError("QInputDialog.getItem не должен вызываться при 0 плотах")

        monkeypatch.setattr(
            "src.ui.main_window.QInputDialog.getItem",
            _fail_if_called,
        )

        info_calls = []
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.information",
            lambda *a, **k: info_calls.append(a),
        )

        w._on_export_all_plots()

        assert len(info_calls) == 1, "Ожидался ровно один QMessageBox.information (empty guard)"
        assert info_calls[0][1] == "Экспорт всех графиков"
        assert info_calls[0][2] == "Нет графиков для экспорта."
    finally:
        _close_window(w)


def test_batch_export_menu_action_always_enabled(app):
    """«Экспорт всех графиков» всегда включён — не гейтится _update_menu_gating()."""
    from src.ui.main_window import MainWindow
    from src.domain.simulation_state import SimulationStatus

    w = MainWindow()
    try:
        assert w._export_all_action.isEnabled() is True

        w._last_sim_status = SimulationStatus.RUNNING
        w._update_menu_gating()
        assert w._export_all_action.isEnabled() is True, (
            "«Экспорт всех графиков» не должен отключаться при RUNNING (в отличие от Save/Load)"
        )
    finally:
        _close_window(w)


def test_batch_export_full_flow_success(app, tmp_path, monkeypatch):
    """Полный поток: формат→папка→export_all→success QMessageBox (D-02..D-05)."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        monkeypatch.setattr(
            "src.ui.main_window.QInputDialog.getItem",
            lambda *a, **k: ("PNG", True),
        )
        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getExistingDirectory",
            lambda *a, **k: str(tmp_path),
        )
        info_calls = []
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.information",
            lambda *a, **k: info_calls.append(a),
        )

        w._on_export_all_plots()

        assert len(list(tmp_path.glob("*.png"))) == 24
        assert len(info_calls) == 1
        assert info_calls[0][1] == "Экспорт завершён"
        assert "Экспортировано 24 графиков" in info_calls[0][2]
        assert str(tmp_path) in info_calls[0][2]
    finally:
        _close_window(w)


def test_batch_export_cancel_format_aborts_silently(app, tmp_path, monkeypatch):
    """Отмена диалога формата прерывает поток без файлов и без completion-диалога."""
    from src.ui.main_window import MainWindow

    w = MainWindow()
    try:
        monkeypatch.setattr(
            "src.ui.main_window.QInputDialog.getItem",
            lambda *a, **k: ("PNG", False),
        )

        folder_calls = []
        monkeypatch.setattr(
            "src.ui.main_window.QFileDialog.getExistingDirectory",
            lambda *a, **k: folder_calls.append(1) or str(tmp_path),
        )
        info_calls = []
        monkeypatch.setattr(
            "src.ui.main_window.QMessageBox.information",
            lambda *a, **k: info_calls.append(a),
        )

        w._on_export_all_plots()

        assert folder_calls == [], "Диалог папки не должен открываться после отмены формата"
        assert info_calls == [], "Completion-диалог не должен показываться после отмены"
        assert list(tmp_path.glob("*")) == [], "Файлы не должны создаваться после отмены"
    finally:
        _close_window(w)


# ── Тест 25-26: «Справка» — User Guide QTextBrowser + дисклеймер (HF-03, Phase 12 Plan 04) ─

def test_help_dialog_missing_file_fallback(app, tmp_path, monkeypatch):
    """_build_user_guide_browser() показывает plain-text fallback при OSError (CR-03)."""
    from src.ui import main_window as mw_module

    monkeypatch.setattr(mw_module, "_USER_GUIDE_FILE", tmp_path / "nonexistent" / "User Guide.md")

    browser = mw_module._build_user_guide_browser()

    assert "Не удалось загрузить руководство пользователя." in browser.toPlainText()


def test_help_dialog_shows_guide_and_disclaimer(app, monkeypatch):
    """«Справка» открывает один QDialog: User Guide (QTextBrowser) + переиспользованный дисклеймер (D-13)."""
    from PySide6.QtWidgets import QGroupBox, QLabel, QTextBrowser

    from src.ui.disclaimer import DISCLAIMER_TEXT
    from src.ui.main_window import MainWindow

    captured = []

    def _fake_exec(dialog_self):
        captured.append(dialog_self)
        return 0

    monkeypatch.setattr("src.ui.main_window.QDialog.exec", _fake_exec)

    w = MainWindow()
    try:
        w._on_help_requested()

        assert len(captured) == 1, "dialog.exec() должен вызываться ровно один раз"
        dialog = captured[0]

        browsers = dialog.findChildren(QTextBrowser)
        assert len(browsers) == 1, "Диалог должен содержать ровно один QTextBrowser (User Guide)"
        assert browsers[0].toPlainText().strip() != "", "User Guide не должен быть пустым"

        group_boxes = dialog.findChildren(QGroupBox)
        assert len(group_boxes) == 1, "Диалог должен содержать ровно один QGroupBox (Дисклеймер)"
        assert group_boxes[0].title() == "Дисклеймер"

        labels = group_boxes[0].findChildren(QLabel)
        assert len(labels) == 1
        assert labels[0].text() == DISCLAIMER_TEXT, (
            "Текст дисклеймера в диалоге должен быть идентичен disclaimer.DISCLAIMER_TEXT "
            "(переиспользован, не новая копия, D-13)"
        )
    finally:
        _close_window(w)


# ── Тест 29: viewport-culling — setData только для видимых строк (PERF-01, Wave 0) ─

def test_telemetry_culls_invisible_plots_setdata(app):
    """update() вызывает setData() только для кодов из буферизованного диапазона строк (D-03).

    RED (Wave 0): TelemetryDashboard пока не имеет ни `_plot_row`, ни
    `_visible_row_range()` — эти атрибуты появятся в Plan 17-02.
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    try:
        dash.resize(900, 200)
        dash.show()
        app.processEvents()

        first, last = dash._visible_row_range()
        last_row_index = dash._grid.rowCount() - 1
        assert last < last_row_index, (
            f"Предпосылка теста не достигнута: _visible_row_range()=({first}, {last}), "
            f"последняя строка сетки={last_row_index} → ожидалось, что хотя бы одна строка "
            f"будет отсечена маленьким viewport (D-01)"
        )

        dash.update({code: 1.0 for code in dash._buffers})

        for code, row in dash._plot_row.items():
            _x_data, y_data = dash._curves[code].getData()
            if first <= row <= last:
                assert y_data is not None and len(y_data) == 1, (
                    f"Код '{code}' (строка {row}) внутри видимого диапазона [{first}, {last}], "
                    f"наблюдалось y_data={y_data!r} → ожидался 1 элемент (D-03)"
                )
            else:
                assert y_data is None or len(y_data) == 0, (
                    f"Код '{code}' (строка {row}) вне видимого диапазона [{first}, {last}], "
                    f"наблюдалось y_data={y_data!r} → ожидалось пусто/None (D-03)"
                )

        assert len(dash._buffers) == 24, (
            f"Наблюдалось {len(dash._buffers)} буферов → ожидалось 24 (D-03)"
        )
        for code, buf in dash._buffers.items():
            assert len(buf) == 1, (
                f"Буфер '{code}' наблюдалось len={len(buf)} → ожидалось 1 (D-03 — данные "
                f"копятся у ВСЕХ 24 кодов независимо от видимости)"
            )
    finally:
        dash.close()
        app.processEvents()


# ── Тест 30: догон полным срезом при возврате плота в видимую область (PERF-01, Wave 0) ─

def test_telemetry_catchup_render_on_scroll_return(app):
    """Возврат отсечённого плота в видимую область даёт один полный catch-up setData() (D-04).

    RED (Wave 0): требует `_plot_row`/`_visible_row_range()`, которых пока нет.
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    try:
        dash.resize(900, 200)
        dash.show()
        app.processEvents()

        first, last = dash._visible_row_range()
        culled_codes = [
            code for code, row in dash._plot_row.items() if not (first <= row <= last)
        ]
        assert culled_codes, (
            f"Предпосылка теста не достигнута: ни один код не отсечён при диапазоне "
            f"[{first}, {last}]"
        )
        target_code = culled_codes[0]

        # WR-03 (17-REVIEW.md): >300 накопленных точек до возврата в видимую
        # область — иначе assert ниже (`== buf_len`) не отличает "срез
        # правильно закапан на 300" от "срез — сырой полный буфер", т.к. обе
        # ветки дают одинаковый результат при buf_len < 300.
        for i in range(400):
            dash.update({target_code: float(i)})

        _x_data, y_data = dash._curves[target_code].getData()
        assert y_data is None or len(y_data) == 0, (
            f"Код '{target_code}' вне видимого диапазона — наблюдалось y_data={y_data!r} "
            f"→ ожидалось пусто/None до прокрутки (D-03)"
        )

        sb = dash._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
        app.processEvents()

        new_first, new_last = dash._visible_row_range()
        target_row = dash._plot_row[target_code]
        assert new_first <= target_row <= new_last, (
            f"После прокрутки в максимум строка '{target_code}' (строка {target_row}) "
            f"наблюдалась вне нового диапазона [{new_first}, {new_last}] → ожидалось "
            f"внутри диапазона (D-04)"
        )

        # CR-01 (17-REVIEW.md): проверяем именно скролл-БЕЗ-update() catch-up —
        # раньше _on_scrolled не существовал, и полный срез появлялся только
        # как побочный эффект следующего update(), что означало permanently
        # blank plot при прокрутке во время паузы/останова симуляции.
        buf_len = len(dash._buffers[target_code])
        _x_data, y_data = dash._curves[target_code].getData()
        assert y_data is not None and len(y_data) == min(buf_len, 300), (
            f"Catch-up setData() для '{target_code}' СРАЗУ после прокрутки (без "
            f"нового update()): наблюдалось "
            f"len(y_data)={None if y_data is None else len(y_data)} → ожидалось "
            f"min(len(buf), 300)={min(buf_len, 300)} (CR-01, D-04)"
        )

        dash.update({target_code: 99.0})

        _x_data, y_data = dash._curves[target_code].getData()
        buf_len = len(dash._buffers[target_code])
        assert y_data is not None and len(y_data) == min(buf_len, 300), (
            f"Catch-up setData() для '{target_code}': наблюдалось "
            f"len(y_data)={None if y_data is None else len(y_data)} → ожидался срез, "
            f"ограниченный min(len(buf), 300)={min(buf_len, 300)} — полный срез (капнутый "
            f"на 300), а не одна последняя точка (D-04)"
        )
    finally:
        dash.close()
        app.processEvents()


# ── Тест 31: _visible_row_range() устойчив к нерастянутым/растянутым строкам (PERF-01, Wave 0) ─

def test_visible_row_range_after_resize(app):
    """_visible_row_range() устойчив к растянутым неоднородным строкам сетки (Pitfall 2, D-01).

    RED (Wave 0): требует `_grid`/`_visible_row_range()`, которых пока нет. Ни в одном
    состоянии тест не опирается на захардкоженную высоту строки или номер отсечённой
    строки — последний индекс строки выводится из `dash._grid.rowCount()`.
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    try:
        dash.show()
        last_row_index = dash._grid.rowCount() - 1

        # (а) viewport выше содержимого — строки растягиваются: диапазон покрывает всё
        dash.resize(900, 2000)
        app.processEvents()
        first_a, last_a = dash._visible_row_range()
        assert 0 <= first_a <= last_a <= last_row_index, (
            f"(а) наблюдалось диапазон=({first_a}, {last_a}) → инвариант клампинга "
            f"0 <= first <= last <= {last_row_index} нарушен"
        )
        assert first_a == 0 and last_a == last_row_index, (
            f"(а) viewport выше содержимого: наблюдалось диапазон=({first_a}, {last_a}) "
            f"→ ожидалось покрытие всех строк (0, {last_row_index})"
        )

        # (б) маленький viewport, скролл в нуле — диапазон начинается с 0, не доходит до последней
        dash.resize(900, 200)
        app.processEvents()
        dash._scroll.verticalScrollBar().setValue(0)
        app.processEvents()
        first_b, last_b = dash._visible_row_range()
        assert 0 <= first_b <= last_b <= last_row_index, (
            f"(б) наблюдалось диапазон=({first_b}, {last_b}) → инвариант клампинга нарушен"
        )
        assert first_b == 0 and last_b < last_row_index, (
            f"(б) скролл в нуле, маленький viewport: наблюдалось диапазон=({first_b}, {last_b}) "
            f"→ ожидалось start=0 и last < {last_row_index}"
        )

        # (в) прокрутка в максимум — диапазон заканчивается последней строкой, начинается > 0
        sb = dash._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
        app.processEvents()
        first_c, last_c = dash._visible_row_range()
        assert 0 <= first_c <= last_c <= last_row_index, (
            f"(в) наблюдалось диапазон=({first_c}, {last_c}) → инвариант клампинга нарушен"
        )
        assert last_c == last_row_index and first_c > 0, (
            f"(в) прокрутка в максимум: наблюдалось диапазон=({first_c}, {last_c}) "
            f"→ ожидалось last={last_row_index} и first > 0"
        )
    finally:
        dash.close()
        app.processEvents()


# ── Тест 32: export_all()/reset() игнорируют viewport-culling (PERF-01, регрессионный замок) ─

def test_export_and_reset_ignore_viewport_culling(app, tmp_path):
    """export_all() и reset() обходят все 24 плота независимо от viewport-culling (PERF-01).

    Регрессионный замок: этот тест зелёный ДО и ПОСЛЕ реализации PERF-01 — фиксирует,
    что culling `setData()` не должен протекать в пакетный экспорт и сброс истории.
    """
    from src.ui.telemetry_dashboard import TelemetryDashboard

    dash = TelemetryDashboard()
    try:
        dash.resize(900, 200)
        dash.show()
        app.processEvents()

        dash.update({code: 1.0 for code in dash._buffers})

        ok, total, errors = dash.export_all("PNG", tmp_path)
        assert errors == [], f"Неожиданные ошибки экспорта: {errors} (PERF-01)"
        assert ok == 24, (
            f"Наблюдалось ok={ok} → ожидалось 24 (culling не должен влиять на export_all, PERF-01)"
        )
        assert total == 24, f"Наблюдалось total={total} → ожидалось 24 (PERF-01)"
        png_files = list(tmp_path.glob("*.png"))
        assert len(png_files) == 24, (
            f"Наблюдалось {len(png_files)} .png файлов в tmp_path → ожидалось 24 (PERF-01)"
        )

        dash.reset()

        for code, buf in dash._buffers.items():
            assert len(buf) == 0, (
                f"Буфер '{code}' наблюдалось len={len(buf)} → ожидалось 0 после reset() (PERF-01)"
            )
            _x_data, y_data = dash._curves[code].getData()
            assert y_data is None or len(y_data) == 0, (
                f"Кривая '{code}' наблюдалось y_data={y_data!r} → ожидалось пусто после "
                f"reset() (PERF-01)"
            )
    finally:
        dash.close()
        app.processEvents()
