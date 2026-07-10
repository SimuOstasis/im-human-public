# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""MainWindow — интеграционный центр фазы M5 Visual Interface.

Собирает 5 QDockWidget-панелей (D-04, D-05), постоянный дисклеймер (UI-09),
QThread+SimulationWorker (D-07), подключает все 9 сигналов из
UI-SPEC.md §Signal/Slot Contracts, реализует _on_state_updated диспетчер
во все панели, CRITICAL→QMessageBox (D-09), QSettings-персистентность (D-06).

Угрозы:
  T-06-13: closeEvent вызывает on_stop()+thread.quit()+thread.wait(2000) —
           предотвращает зомби-процесс
  T-06-14: Все взаимодействия с Worker только через сигналы/слоты
           (QueuedConnection); UI никогда не вызывает engine.tick напрямую
  T-06-15: Блокирующий QMessageBox.warning при PAUSED+CRITICAL (D-09)
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from src.ui.human_panel import HumanPanel
from src.ui.time_controls import TimeControls
from src.ui.telemetry_dashboard import TelemetryDashboard
from src.ui.substance_manager import SubstanceManager
from src.ui.event_log import EventLog
from src.ui.disclaimer import create_disclaimer_label
from src.ui.worker import SimulationWorker
from src.domain.simulation_state import SimulationStatus


class MainWindow(QMainWindow):
    """Главное окно приложения im-human.

    Структура:
    - 5 QDockWidget: Профиль (Left), Управление временем (Top),
      Биомаркеры (Right/tabbed), Вещества (Right), Журнал событий (Bottom)
    - Пустой QWidget() как centralWidget (D-04)
    - Дисклеймер — permanentWidget в QStatusBar (UI-09)
    - QThread + SimulationWorker через moveToThread (D-07)
    - 9 сигналов из UI-SPEC.md §Signal/Slot Contracts
    - QSettings("im-human", "simulator") — геометрия + состояние доков (D-06)
    """

    # Сигнал для передачи HumanProfile в Worker через QueuedConnection (CR-01)
    _start_simulation = Signal(object)  # HumanProfile

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("im-human — Симулятор")

        # ── Пустой centralWidget (D-04: нет centralWidget с содержимым) ───────
        self.setCentralWidget(QWidget())

        # ── Создать экземпляры панелей ─────────────────────────────────────────
        self.human_panel = HumanPanel()
        self.time_controls = TimeControls()
        self.telemetry = TelemetryDashboard()
        self.substances = SubstanceManager()
        self.event_log = EventLog()

        # ── 5 QDockWidget с русскими заголовками (D-05, §Copywriting Panel Titles) ──

        # «Профиль» → левая область
        self._profile_dock = QDockWidget("Профиль", self)
        self._profile_dock.setObjectName("dock_profile")
        self._profile_dock.setWidget(self.human_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._profile_dock)

        # «Управление временем» → верхняя область
        self._time_dock = QDockWidget("Управление временем", self)
        self._time_dock.setObjectName("dock_time")
        self._time_dock.setWidget(self.time_controls)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self._time_dock)

        # «Вещества» → правая область
        self._substances_dock = QDockWidget("Вещества", self)
        self._substances_dock.setObjectName("dock_substances")
        self._substances_dock.setWidget(self.substances)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._substances_dock)

        # «Биомаркеры» → правая область, табирован с «Вещества» (D-05)
        self._telemetry_dock = QDockWidget("Биомаркеры", self)
        self._telemetry_dock.setObjectName("dock_telemetry")
        self._telemetry_dock.setWidget(self.telemetry)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._telemetry_dock)
        self.tabifyDockWidget(self._substances_dock, self._telemetry_dock)

        # «Журнал событий» → нижняя область
        self._event_log_dock = QDockWidget("Журнал событий", self)
        self._event_log_dock.setObjectName("dock_event_log")
        self._event_log_dock.setWidget(self.event_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._event_log_dock)

        # ── Дисклеймер — permanentWidget в statusBar (UI-09) ──────────────────
        self.statusBar().addPermanentWidget(create_disclaimer_label())

        # ── QSettings — восстановить геометрию и состояние доков (D-06) ───────
        # ВАЖНО: вызывается ПОСЛЕ всех addDockWidget()
        settings = QSettings("im-human", "simulator")
        geometry = settings.value("mainwindow/geometry")
        if geometry:
            restored = self.restoreGeometry(geometry)
            # If geometry is off-screen (e.g. saved from offscreen Qt tests), reset to center
            from PySide6.QtWidgets import QApplication as _QApp
            screen = _QApp.primaryScreen()
            if restored and screen and not screen.availableGeometry().intersects(self.frameGeometry()):
                self.setGeometry(100, 100, 1400, 900)
        else:
            self.setGeometry(100, 100, 1400, 900)
        state = settings.value("mainwindow/dockstate")
        if state:
            self.restoreState(state)

        # ── Threading: Worker Object паттерн (D-07) ────────────────────────────
        self._worker = SimulationWorker()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

        # ── Хранить текущий профиль (для подстановки при start_requested) ─────
        self._current_profile = None

        # ── Флаг последнего CRITICAL-тика (предотвращает повторный диалог) ────
        self._last_critical_tick: int = -1

        # ── Флаг: диалог уже показан (защита от вложенных exec()) ────────────
        self._dialog_open: bool = False

        # ── Последний известный статус (для корректного resume после Cancel) ──
        self._last_sim_status: "SimulationStatus" = SimulationStatus.IDLE

        # ── Throttle: рендерить графики не чаще 10 fps (100ms) ───────────────
        self._last_render_t: float = 0.0

        # ── Подключение всех 9 сигналов (UI-SPEC.md §Signal/Slot Contracts) ───

        # Worker → UI (2 сигнала)
        self._worker.state_updated.connect(self._on_state_updated)
        self._worker.error_occurred.connect(self._on_engine_error)

        # UI → Worker: DirectConnection because run() is a while-loop (not a Qt
        # event loop), so QueuedConnection signals are never delivered without
        # explicit processEvents(). DirectConnection is safe here — all slots are
        # simple GIL-protected flag setters; _schedules uses threading.Lock.
        _DC = Qt.ConnectionType.DirectConnection

        self._start_simulation.connect(self._worker.on_start, _DC)
        self.time_controls.start_requested.connect(self._on_start_requested)
        self.time_controls.pause_requested.connect(self._worker.on_pause, _DC)
        self.time_controls.resume_requested.connect(self._worker.on_resume, _DC)
        self.time_controls.stop_requested.connect(self._on_stop_requested)
        self.time_controls.speed_changed.connect(self._worker.on_speed_changed, _DC)
        self.substances.substance_added.connect(self._worker.on_substance_added, _DC)
        self.substances.substance_removed.connect(self._worker.on_substance_removed, _DC)

        # HumanPanel → MainWindow (профиль)
        self.human_panel.profile_changed.connect(self._on_profile_changed)
        # Prime _current_profile: HumanPanel already emitted profile_changed in __init__
        # before this connection was made, so trigger it manually now.
        self.human_panel._on_preset_selected(self.human_panel.preset_combo.currentIndex())

    # ── Слоты и обработчики ────────────────────────────────────────────────────

    def _on_stop_requested(self) -> None:
        """Пауза → диалог подтверждения → стоп или возобновление."""
        if self._dialog_open:
            return

        # Поставить на паузу немедленно, пока диалог открыт
        was_running = (self._last_sim_status == SimulationStatus.RUNNING)
        if was_running:
            self._worker.on_pause()

        self._dialog_open = True
        try:
            msg = QMessageBox(self)
            msg.setWindowTitle("Остановить симуляцию")
            msg.setText("Остановить симуляцию? Прогресс будет сброшен.")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            msg.button(QMessageBox.StandardButton.Ok).setText("Подтвердить")
            msg.button(QMessageBox.StandardButton.Cancel).setText("Отмена")
            result = msg.exec()
        finally:
            self._dialog_open = False

        if result == QMessageBox.StandardButton.Ok:
            self._worker.on_stop()
        elif was_running:
            # Отмена — вернуть к тому моменту, когда была нажата кнопка стоп
            self._worker.on_resume()

    def _on_profile_changed(self, profile) -> None:
        """Сохранить текущий профиль и обновить цветовые зоны дашборда.

        Args:
            profile: HumanProfile — выбранный пользователем профиль
        """
        self._current_profile = profile
        self.telemetry.apply_ranges(profile)

    def _on_start_requested(self, _ignored) -> None:
        """Обработчик кнопки «Запустить».

        TimeControls эмитирует start_requested(None); MainWindow подставляет
        текущий профиль из HumanPanel (согласно плану 06-03).
        Передаёт профиль в Worker через сигнал _start_simulation (QueuedConnection),
        чтобы не нарушать Worker Object паттерн (CR-01, T-06-14).
        """
        if self._current_profile is not None:
            self.event_log.reset()
            self._start_simulation.emit(self._current_profile)

    def _on_state_updated(self, state) -> None:
        """Диспетчер состояния симуляции во все 5 панелей.

        ТОЧНЫЙ порядок UI-SPEC.md §Signal/Slot Contracts:
          1. TelemetryDashboard.update(state.biomarker_values)
          2. HumanPanel.update_indices(state.biological_age, state.resilience_index)
          3. TimeControls.update_status(state.status, state.tick_count)
          4. EventLog.add_events(state.events)
          5. SubstanceManager.update_concentrations(state.substance_concentrations)
          6. Если PAUSED+CRITICAL → QMessageBox.warning (D-09)

        Args:
            state: SimulationState — копия состояния из Worker (model_copy)
        """
        # Skip all UI updates while a modal dialog is open — modifying widgets
        # during QMessageBox.exec()'s inner event loop confuses Qt's paint system.
        if self._dialog_open:
            return

        # 3. Управление временем — статус и кнопки (всегда, не throttle)
        # Must run unconditionally so Pause/Resume button states update immediately.
        self._last_sim_status = state.status
        self.time_controls.update_status(state.status, state.tick_count)

        # Heavy rendering throttled to 5fps
        now = time.monotonic()
        if now - self._last_render_t < 0.2:
            return
        self._last_render_t = now

        # 1. Телеметрия — обновить кривые плотов
        self.telemetry.update(state.biomarker_values)

        # 2. Панель профиля — хронологический и биологический возраст, устойчивость
        self.human_panel.update_chrono_age(state.tick_count)
        self.human_panel.update_indices(state.biological_age, state.resilience_index)

        # 4. Журнал событий — только новые события
        self.event_log.add_events(state.events)

        # 5. Менеджер веществ — концентрации C(t)
        self.substances.update_concentrations(state.substance_concentrations)

        # 6. CRITICAL → QMessageBox.warning (D-09, T-06-15)
        if state.status == SimulationStatus.PAUSED:
            # Найти CRITICAL-события; показать диалог для последнего нового CRITICAL
            critical_events = [
                e for e in state.events if e.severity == "CRITICAL"
            ]
            if critical_events:
                last_crit = critical_events[-1]
                # Флаг предотвращает повторный диалог на одном тике
                if last_crit.tick != self._last_critical_tick and not self._dialog_open:
                    self._last_critical_tick = last_crit.tick
                    self._dialog_open = True
                    try:
                        QMessageBox.warning(
                            self,
                            "Критическое событие",
                            last_crit.message,
                        )
                    finally:
                        self._dialog_open = False

    def _on_engine_error(self, message: str) -> None:
        """Обработчик сигнала error_occurred (UI-SPEC.md §Error States).

        Пишет красную запись в журнал событий и показывает предупреждение.

        Args:
            message: текст ошибки из Worker (исключение)
        """
        self.event_log.add_error(message)
        QMessageBox.warning(
            self,
            "Критическое событие",
            "Симуляция остановлена из-за ошибки. Проверьте журнал событий.",
        )

    # ── Жизненный цикл окна ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Сохранить геометрию/состояние доков и корректно завершить QThread.

        Порядок (T-06-13):
          1. Сохранить QSettings
          2. Остановить Worker (on_stop)
          3. Завершить поток (quit + wait 2000 мс)
          4. Вызвать super().closeEvent(event)
        """
        # Сохранить геометрию и состояние доков (D-06)
        settings = QSettings("im-human", "simulator")
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        settings.setValue("mainwindow/dockstate", self.saveState())

        # Корректно остановить KB thread (T-07-06: завершить до simulation thread)
        self.substances.close_kb_thread()

        # Корректно остановить поток (T-06-13)
        # Прямой вызов on_stop() необходим: run() — это while-цикл, а не Qt event loop,
        # поэтому QueuedConnection никогда не доставляется (CR-02 revert).
        self._worker.on_stop()
        self._thread.quit()
        self._thread.wait(10000)

        super().closeEvent(event)
