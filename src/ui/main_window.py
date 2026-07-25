# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""MainWindow — интеграционный центр фазы M5 Visual Interface.

Собирает 5 QDockWidget-панелей (D-04, D-05), постоянный дисклеймер (UI-09),
QThread+SimulationWorker (D-07), подключает все 10 сигналов из
UI-SPEC.md §Signal/Slot Contracts, реализует _on_state_updated диспетчер
во все панели, CRITICAL→QMessageBox (D-09), QSettings-персистентность (D-06).

Угрозы:
  T-06-13: closeEvent вызывает shutdown()+thread.quit()+thread.wait(10000) —
           предотвращает зомби-процесс (IN-02: shutdown(), не on_stop() —
           см. closeEvent docstring)
  T-06-14: Все взаимодействия с Worker только через сигналы/слоты
           (QueuedConnection); UI никогда не вызывает engine.tick напрямую
  T-06-15: Блокирующий QMessageBox.warning при PAUSED+CRITICAL (D-09)
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
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
from src.engine.exporter import save_simulation, load_simulation

# WR-06 (10.1-REVIEW.md): _on_load_requested's broad `except Exception`
# around load_simulation() is intentional — it must cover ValueError,
# pydantic.ValidationError, json.JSONDecodeError и OSError, все они
# суть равноценные untrusted-file-input сбои (T-10-03). Но такой широкий
# catch также молча превращает НЕСВЯЗАННЫЙ баг (например, будущий
# AttributeError после рефакторинга exporter.load_simulation) в общее
# «файл повреждён» — логируем полный traceback перед конвертацией в
# пользовательское сообщение, чтобы не прятать реальные дефекты.
_logger = logging.getLogger(__name__)

# «Справка» (HF-03, Phase 12 Plan 04) — путь к User Guide анкорится к __file__
# (parent.parent.parent: src/ui/ -> src/ -> корень репозитория), а не к
# текущему рабочему каталогу/относительной строке (12-RESEARCH.md Pitfall 3) —
# иначе файл не найдётся при запуске из другого рабочего каталога (ярлык/будущий .exe).
_USER_GUIDE_FILE = Path(__file__).parent.parent.parent / "06 - Engine" / "User Guide.md"


def _build_user_guide_browser() -> QTextBrowser:
    """Создать QTextBrowser с отрендеренным markdown из User Guide (HF-03).

    Читает `_USER_GUIDE_FILE` и рендерит через `setMarkdown()`. При OSError
    (файл отсутствует/нечитаем) или UnicodeDecodeError (файл на диске не
    валидный UTF-8 — IN-03, 12-REVIEW.md: подкласс ValueError, не OSError,
    иначе не ловится этим блоком) показывает plain-text fallback вместо
    падения (CR-03 graceful-degradation паттерн, см. TelemetryDashboard.__init__).
    Викилинки [[...]] внутри контента не конвертируются в кликабельные ссылки —
    Qt md4c не разбирает эту нотацию (12-RESEARCH.md Pitfall 2, принятое
    ограничение, не блокирует HF-03).
    """
    browser = QTextBrowser()
    try:
        text = _USER_GUIDE_FILE.read_text(encoding="utf-8")
        browser.setMarkdown(text)
    except (OSError, UnicodeDecodeError):
        browser.setPlainText(
            "Не удалось загрузить руководство пользователя.\n"
            'Ожидаемый файл: "06 - Engine/User Guide.md".'
        )
    return browser


class MainWindow(QMainWindow):
    """Главное окно приложения im-human.

    Структура:
    - 5 QDockWidget: Профиль (Left), Управление временем (Top),
      Биомаркеры (Right/tabbed), Вещества (Right), Журнал событий (Bottom)
    - Пустой QWidget() как centralWidget (D-04)
    - Дисклеймер — permanentWidget в QStatusBar (UI-09)
    - QThread + SimulationWorker через moveToThread (D-07)
    - 10 сигналов из UI-SPEC.md §Signal/Slot Contracts
    - QSettings("im-human", "simulator") — геометрия + состояние доков (D-06)
    """

    # Сигнал для передачи HumanProfile в Worker через QueuedConnection (CR-01)
    _start_simulation = Signal(object)  # HumanProfile
    # Сигнал для передачи загруженного снепшота в Worker (HS-01, T-06-14)
    _load_simulation = Signal(object)  # tuple[SimulationState, HumanProfile, list[IntakeSchedule]]

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

        # ── Меню «Файл»: Сохранить/Загрузить (HS-01, UI-SPEC §Copywriting) ────
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&Файл")

        self._save_action = QAction("&Сохранить", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self._on_save_requested)
        file_menu.addAction(self._save_action)

        self._load_action = QAction("&Загрузить", self)
        self._load_action.setShortcut(QKeySequence.StandardKey.Open)
        self._load_action.triggered.connect(self._on_load_requested)
        file_menu.addAction(self._load_action)

        # «Экспорт всех графиков» — HF-01, Phase 12 Plan 02 (D-02). В отличие
        # от Сохранить/Загрузить, всегда включён — НЕ добавляется в
        # _update_menu_gating() (экспорт уже отрисованных виджетов безопасен
        # при любом статусе RUNNING/PAUSED/IDLE/STOPPED, UI-SPEC Interaction
        # Contract). Без shortcut — Ctrl+S/Ctrl+O уже заняты Сохранить/Загрузить.
        file_menu.addSeparator()
        self._export_all_action = QAction("&Экспорт всех графиков", self)
        self._export_all_action.triggered.connect(self._on_export_all_plots)
        file_menu.addAction(self._export_all_action)

        # «Новая» — вместо кнопки «Сброс» на панели управления временем
        # (по решению пользователя, 2026-07-13). То же необратимое действие
        # (confirm-диалог → on_stop() → FSM в STOPPED), тот же обработчик
        # _on_stop_requested. IN-01: «Новая» НЕ гейтится статусом — всегда
        # включена (см. _update_menu_gating, которая гейтит только
        # Сохранить/Загрузить и никогда не трогает stop_btn/эту команду).
        file_menu.addSeparator()
        self._new_simulation_action = QAction("&Новая", self)
        self._new_simulation_action.triggered.connect(self._on_stop_requested)
        file_menu.addAction(self._new_simulation_action)

        # «Справка» — HF-03, Phase 12 Plan 04 (D-13). Top-level QAction через
        # menu_bar.addAction (НЕ addMenu) — один клик сразу открывает диалог,
        # без выпадающего меню. Размещается правее «Файл» (стандартная
        # конвенция «Help is rightmost»). Всегда включён — не гейтится
        # _update_menu_gating() (статичный контент, не зависит от статуса
        # симуляции, та же логика что у постоянного дисклеймера в statusBar).
        self._help_action = QAction("&Справка", self)
        self._help_action.triggered.connect(self._on_help_requested)
        menu_bar.addAction(self._help_action)

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
        # WR-05 (10.1-REVIEW.md): _thread.start() deliberately moved below —
        # after state_updated/error_occurred/control-signal connections are
        # established (see the block a few lines down). Signals emitted with
        # no connected receiver are dropped, not queued; today this was
        # benign only because run()'s first branch idles until on_start()/
        # on_load() populate _state/_engine — impossible before those slots
        # are connected, since no user interaction can occur during
        # __init__. Starting the thread after wiring removes that fragile
        # ordering dependency entirely.

        # ── Хранить текущий профиль (для подстановки при start_requested) ─────
        self._current_profile = None

        # ── Хранить последнее известное состояние симуляции (для Save, HS-01) ─
        self._current_state = None

        # ── Флаг последнего CRITICAL-тика (предотвращает повторный диалог) ────
        self._last_critical_tick: int = -1

        # ── Флаг: диалог уже показан (защита от вложенных exec()) ────────────
        self._dialog_open: bool = False

        # ── Последний известный статус (для корректного resume после Cancel) ──
        self._last_sim_status: "SimulationStatus" = SimulationStatus.IDLE

        # ── Throttle: рендерить графики не чаще 10 fps (100ms) ───────────────
        self._last_render_t: float = 0.0

        # ── Подключение всех 10 сигналов (UI-SPEC.md §Signal/Slot Contracts) ──

        # Worker → UI (2 сигнала)
        self._worker.state_updated.connect(self._on_state_updated)
        self._worker.error_occurred.connect(self._on_engine_error)

        # UI → Worker: DirectConnection because run() is a while-loop (not a Qt
        # event loop), so QueuedConnection signals are never delivered without
        # explicit processEvents(). DirectConnection is safe here:
        #   - on_pause/on_resume/on_speed_changed/on_substance_added/
        #     on_substance_removed are simple GIL-protected flag setters
        #     (on_substance_* additionally use _schedules_lock, T-06-03).
        #   - on_start/on_load (WR-02, 12-REVIEW.md) are NOT simple flag
        #     setters — they construct SimulationEngine and reassign
        #     self._engine/self._state — but both acquire worker.py's
        #     self._state_lock around that mutation (worker.py on_start/
        #     on_load), and run() takes the SAME self._state_lock around
        #     every read/reassignment of self._engine/self._state (worker.py
        #     run(): the "ready" check and the sub-batch loop). So running
        #     on_start/on_load on the UI thread (DirectConnection) while
        #     run() executes concurrently on the worker thread is
        #     synchronized via _state_lock, not by DirectConnection/GIL
        #     atomicity alone.
        _DC = Qt.ConnectionType.DirectConnection

        self._start_simulation.connect(self._worker.on_start, _DC)
        self._load_simulation.connect(self._worker.on_load, _DC)
        self.time_controls.start_requested.connect(self._on_start_requested)
        self.time_controls.pause_requested.connect(self._worker.on_pause, _DC)
        self.time_controls.resume_requested.connect(self._worker.on_resume, _DC)
        self.time_controls.stop_requested.connect(self._on_stop_requested)
        self.time_controls.speed_changed.connect(self._worker.on_speed_changed, _DC)
        self.substances.substance_added.connect(self._worker.on_substance_added, _DC)
        self.substances.substance_removed.connect(self._worker.on_substance_removed, _DC)

        # WR-05: start the worker thread only after every self._worker.*
        # signal/slot connection above is established.
        self._thread.start()

        # HumanPanel → MainWindow (профиль)
        self.human_panel.profile_changed.connect(self._on_profile_changed)
        # Prime _current_profile: HumanPanel already emitted profile_changed in __init__
        # before this connection was made, so trigger it manually now.
        # IN-02 (10.1-REVIEW.md): use HumanPanel's public
        # emit_current_profile() instead of reaching into its private
        # _on_preset_selected/preset_combo surface.
        self.human_panel.emit_current_profile()

        # Инициализировать состояние меню «Файл» (IDLE → включено, D-02)
        self._update_menu_gating()

    # ── Слоты и обработчики ────────────────────────────────────────────────────

    @contextmanager
    def _modal_dialog(self):
        """Context manager for the `self._dialog_open = True/finally False`
        boilerplate around every modal dialog (IN-01, 12-REVIEW.md).

        Extracted after this exact pattern was duplicated verbatim across 6
        call sites (`_on_stop_requested`, `_on_save_requested`,
        `_on_load_requested`, `_on_export_all_plots` x2, `_on_help_requested`)
        — any future dialog added without it would silently reintroduce the
        race `_dialog_open` exists to prevent (see WR-03, 12-REVIEW.md).
        Usage: `with self._modal_dialog(): result = dialog.exec()`.
        """
        self._dialog_open = True
        try:
            yield
        finally:
            self._dialog_open = False

    def _on_stop_requested(self) -> None:
        """Пауза → диалог подтверждения → сброс или возобновление.

        Обработчик Файл→«Новая» (кнопка «Сброс» убрана с панели, 2026-07-13,
        см. time_controls.py). Терминальное действие (STOPPED не имеет
        исходящих переходов в FSM, см. simulation_state.py): следующий
        «Запустить» всегда начинает новый прогон с tick_count=0, даже если
        это состояние было Save/Load'нуто. Возобновляемая точка сохранения —
        «Пауза», не «Новая» (Resume после Load корректно продолжает с
        сохранённого tick_count).
        """
        if self._dialog_open:
            return

        # Поставить на паузу немедленно, пока диалог открыт
        was_running = (self._last_sim_status == SimulationStatus.RUNNING)
        if was_running:
            self._worker.on_pause()

        with self._modal_dialog():
            msg = QMessageBox(self)
            msg.setWindowTitle("Сбросить симуляцию")
            msg.setText(
                "Сбросить симуляцию? Весь прогресс будет потерян безвозвратно "
                "— следующий запуск начнётся заново с нуля. Чтобы позже "
                "продолжить с текущего момента, используйте «Пауза», а не «Новая»."
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            msg.button(QMessageBox.StandardButton.Ok).setText("Подтвердить")
            msg.button(QMessageBox.StandardButton.Cancel).setText("Отмена")
            result = msg.exec()

        if result == QMessageBox.StandardButton.Ok:
            self._worker.on_stop()
            # on_stop() больше НЕ завершает run()'s цикл (см. worker.py docstring —
            # иначе повторный «Запустить» после «Стоп» тихо ничего не делал бы), но
            # его следующий state_updated придёт не раньше чем через ~50мс простоя
            # + троттлинг. Раньше (когда on_stop() убивал цикл насовсем) сигнал не
            # приходил ВООБЩЕ никогда — Save/Load оставались отключены навсегда,
            # т.к. _last_sim_status застревал на RUNNING. Оставляем синхронную
            # финализацию здесь как немедленное, детерминированное обновление
            # вместо ожидания следующего асинхронного эмита.
            #
            # Полный сброс отображаемых показателей к дефолту (по решению
            # пользователя, 2026-07-13) — не только смена статуса. self._current_state
            # сбрасывается в None (а не просто транзишится в STOPPED), чтобы Save
            # сразу после «Новая» честно показывал «Нет данных» (main_window.py
            # _on_save_requested), а не тихо сохранял устаревшие day-N показатели,
            # которые уже не соответствуют обнулённым графикам/лейблам. Профиль
            # (self._current_profile) и список веществ (SubstanceManager._added) —
            # это настройка, не прогресс прогона, оставляем как есть.
            self._current_state = None
            self._last_sim_status = SimulationStatus.STOPPED
            # CR-03: reset so a repeat CRITICAL at the same tick (worker's
            # seed is hardcoded to 42, so a replayed run is deterministic)
            # still triggers the mandatory dialog instead of being silently
            # suppressed by the stale tick from the previous run.
            self._last_critical_tick = -1
            self.human_panel.update_indices(None, None)
            self.human_panel.update_chrono_age(0)
            self.telemetry.reset()
            self.event_log.reset()
            self.substances.update_concentrations({})
            # update_status() ДО _update_menu_gating(): последняя читает
            # time_controls.stop_btn.isEnabled() для гейтинга «Новая» — если
            # вызвать в обратном порядке, она прочитает ещё не обновлённое
            # (RUNNING/PAUSED-эры) значение stop_btn.
            self.time_controls.update_status(SimulationStatus.STOPPED, 0)
            self._update_menu_gating()
        elif was_running:
            # Отмена — вернуть к тому моменту, когда была нажата кнопка стоп
            self._worker.on_resume()

    def _update_menu_gating(self) -> None:
        """Пересчитать доступность «Файл → Сохранить/Загрузить» по статусу (D-02).

        Сохранить/Загрузить отключены пока self._last_sim_status == RUNNING,
        иначе включены. «Новая» (по решению пользователя, 2026-07-13) НЕ
        гейтится статусом — всегда включена, доступна в любой момент.
        _on_stop_requested() уже безопасно no-op'ится, если нечего сбрасывать
        (worker._state/self._current_state оба None при IDLE) — включённый
        пункт меню без активной симуляции просто покажет confirm-диалог ни о
        чём и ничего не изменит. Вызывается из __init__ (стартовое IDLE-
        состояние) и из _on_state_updated при каждом изменении статуса
        (UI-SPEC.md §Interaction/State Contract).
        """
        not_running = self._last_sim_status != SimulationStatus.RUNNING
        self._save_action.setEnabled(not_running)
        self._load_action.setEnabled(not_running)

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
            # WR-03 (10.1-REVIEW.md): _start_simulation uses
            # Qt.ConnectionType.DirectConnection, so this emit() runs
            # SimulationWorker.on_start() — including SimulationEngine(...)
            # and engine.initialize() — synchronously in this call stack. If
            # profile construction/engine initialization ever raises, the
            # exception would otherwise propagate straight out of this
            # button-click handler uncaught. Wrap it the same way
            # _on_load_requested already wraps its equivalent
            # untrusted-input operation (load_simulation).
            try:
                self._start_simulation.emit(self._current_profile)
            except Exception as exc:
                self.event_log.add_error(str(exc))
                QMessageBox.warning(self, "Ошибка запуска", str(exc))
                return
            # CR-02: _start_simulation is a DirectConnection, so on_start()
            # already ran synchronously above and self._worker._state now
            # reflects the fresh RUNNING state. Reflect it into
            # self._last_sim_status synchronously too — otherwise it stays
            # stale (IDLE/STOPPED) for up to the ~200ms render throttle,
            # during which a fast-follow "Новая" click would read
            # was_running=False in _on_stop_requested and skip the
            # protective on_pause() call, racing on_stop() against the
            # worker's inner tick loop.
            # WR-02 (10-REVIEW.md): read through get_state_snapshot() (which
            # acquires _state_lock internally) instead of the raw
            # self._worker._state attribute, matching the locking discipline
            # every other _state access in worker.py follows.
            self._on_state_updated(self._worker.get_state_snapshot())
        else:
            # WR-07: without this, a missing/invalid profile (e.g.
            # presets.json failed to load) makes «Запустить» a silent
            # no-op — no error dialog, no event-log entry, no feedback that
            # the app is in a broken/unusable state.
            QMessageBox.warning(
                self,
                "Нет профиля",
                "Профиль человека не загружен — выберите пресет.",
            )

    def _on_state_updated(self, state) -> None:
        """Диспетчер состояния симуляции во все 5 панелей.

        WR-05 (10-REVIEW.md): фактический порядок ОТЛИЧАЕТСЯ от исходного
        списка UI-SPEC.md §Signal/Slot Contracts — шаг 3 выполняется ПЕРВЫМ
        и БЕЗУСЛОВНО (минуя render-throttle), т.к. _update_menu_gating()
        должен видеть уже обновлённый time_controls.stop_btn:
          3. TimeControls.update_status(state.status, state.tick_count)
             + _update_menu_gating() — всегда, без троттлинга
        Также безусловно (D-01/D-09, 10.1-02): EventLog.set_status(state.status)
             — текст empty-state не должен зависеть от add_events()/throttle
             (Pitfall 3, 10.1-RESEARCH.md).
        Далее, только если проходит 200мс render-throttle (5fps):
          1. TelemetryDashboard.update(state.biomarker_values)
          2. HumanPanel.update_indices(state.biological_age, state.resilience_index)
          4. EventLog.add_events(state.events)
          5. SubstanceManager.update_concentrations(state.substance_concentrations)
          6. Если PAUSED+CRITICAL → QMessageBox.warning (D-09)

        Args:
            state: SimulationState — копия состояния из Worker (model_copy),
                либо None, если Worker ещё не запускался/не загружал сессию
                (get_state_snapshot() возвращает None, пока self._state is None).
        """
        # Worker ещё не запускался — нечего отображать (WR-03 re-check call
        # sites in _on_export_all_plots/_on_help_requested can legitimately
        # fire with no active simulation).
        if state is None:
            return

        # Skip all UI updates while a modal dialog is open — modifying widgets
        # during QMessageBox.exec()'s inner event loop confuses Qt's paint system.
        if self._dialog_open:
            return

        # 3. Управление временем — статус и кнопки (всегда, не throttle)
        # Must run unconditionally so Pause/Resume button states update immediately.
        # update_status() ДО _update_menu_gating(): последняя читает
        # time_controls.stop_btn.isEnabled() для гейтинга «Новая» — обратный
        # порядок читал бы состояние stop_btn с предыдущего вызова, на шаг позади.
        self._last_sim_status = state.status
        self._current_state = state
        self.time_controls.update_status(state.status, state.tick_count)
        self._update_menu_gating()
        self.event_log.set_status(state.status)

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

        CR-01 (10.1-REVIEW.md): once worker.py clears self._state/self._engine
        to None after a tick exception, run()'s ready-branch idles forever and
        never emits state_updated again — so _last_sim_status stays frozen at
        the pre-crash RUNNING value unless we update it here ourselves. Without
        this, _update_menu_gating() keeps Save/Load disabled forever (reading
        stale RUNNING), time_controls keeps showing "Выполняется", and the only
        recoverable action («Файл → Новая») discards self._current_state — the
        one path back to a usable UI destroys the last-good pre-crash snapshot
        instead of letting the user save it.

        Args:
            message: текст ошибки из Worker (исключение)
        """
        self.event_log.add_error(message)
        self._last_sim_status = SimulationStatus.STOPPED
        tick_count = self._current_state.tick_count if self._current_state else 0
        self.time_controls.update_status(SimulationStatus.STOPPED, tick_count)
        self._update_menu_gating()  # re-enables Save/Load for the still-valid _current_state
        # WR-01 (10.1-REVIEW.md): guard against a stacked modal dialog, same as
        # the CRITICAL path in _on_state_updated. error_occurred is a
        # QueuedConnection and QMessageBox.exec() still pumps queued
        # cross-thread signals, so this slot can re-enter while a CRITICAL
        # dialog is already modal — without this check we'd open a second
        # stacked modal, exactly what _dialog_open exists to prevent.
        if self._dialog_open:
            return
        self._dialog_open = True
        try:
            QMessageBox.warning(
                self,
                "Критическое событие",
                "Симуляция остановлена из-за ошибки. Проверьте журнал событий.",
            )
        finally:
            self._dialog_open = False

    def _on_save_requested(self) -> None:
        """Обработчик «Файл → Сохранить» (HS-01, D-01/D-02).

        Открывает QFileDialog.getSaveFileName, дописывает расширение .json
        при необходимости и сохраняет текущее состояние/профиль/расписания
        через exporter.save_simulation. Диалог обёрнут флагом self._dialog_open
        (T-06-14/pattern _on_stop_requested), чтобы _on_state_updated корректно
        пропускал обновления UI пока модальный диалог открыт.
        """
        if self._current_state is None or self._current_profile is None:
            QMessageBox.information(
                self,
                "Нет данных",
                "Нет активной симуляции для сохранения.",
            )
            return

        with self._modal_dialog():
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить симуляцию",
                "simulation.json",
                "JSON файлы (*.json);;Все файлы (*.*)",
            )

        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            save_simulation(
                self._current_state,
                self._current_profile,
                self.substances.get_schedules(),
                Path(path),
            )
        except Exception as exc:
            # Mirrors _on_load_requested's broad except (D-01): OSError
            # (locked file, no permission, full disk) must not crash the UI.
            # _logger.exception preserves the traceback (WR-06 rationale).
            # D-02 divergence: unlike load's generic str(exc) body, the
            # save-error message names the exact path that failed to save.
            _logger.exception("save_simulation failed for %s", path)
            self.event_log.add_error(str(exc))
            QMessageBox.warning(
                self,
                "Ошибка сохранения",
                f"Не удалось сохранить файл {path}: {exc}",
            )

    def _on_load_requested(self) -> None:
        """Обработчик «Файл → Загрузить» (HS-01, D-01/D-02/D-03).

        Открывает QFileDialog.getOpenFileName, вызывает exporter.load_simulation
        и при успехе восстанавливает профиль/состояние в MainWindow, список
        веществ в SubstanceManager (load_schedules) и движок в Worker
        (через сигнал _load_simulation, T-06-14 — никогда напрямую).

        При ValueError/pydantic.ValidationError (повреждённый/несовместимый
        файл) — пишет ошибку в EventLog и показывает QMessageBox.warning,
        НЕ изменяя состояние приложения (D-03).

        Не вызывает state.transition(...): загруженный PAUSED-снепшот
        остаётся PAUSED, обычный on_resume выполнит переход при нажатии
        «Возобновить» (exporter.py Pitfall 2).
        """
        with self._modal_dialog():
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Загрузить симуляцию",
                "",
                "JSON файлы (*.json);;Все файлы (*.*)",
            )

        if not path:
            return

        try:
            state, profile, schedules = load_simulation(Path(path))
        except Exception as exc:
            # Broad catch covers ValueError (version/missing-key, exporter.py)
            # and pydantic.ValidationError (schema mismatch) — both are
            # untrusted-file-input failures per the threat model (T-10-03).
            # WR-06: log the full traceback before converting to the generic
            # user-facing "corrupt file" message — otherwise an unrelated
            # programming bug in exporter.load_simulation would be silently
            # masked as bad input during development/QA.
            _logger.exception("load_simulation failed for %s", path)
            self.event_log.add_error(str(exc))
            QMessageBox.warning(
                self,
                "Ошибка загрузки",
                str(exc),
            )
            return

        self._current_profile = profile
        # CR-01 (12-REVIEW.md): don't alias self._current_state with the raw
        # loaded object — _load_simulation.emit() below hands this same
        # object to the Worker thread (on_load stores it by reference), so
        # assigning it here too would leave the UI thread and Worker thread
        # sharing one mutable SimulationState (including its nested
        # biomarker_values dict), exactly the T-10.1-01 hazard
        # get_state_snapshot()'s deep copy exists to prevent. Mirrors
        # _on_start_requested's safe pattern: read back through
        # get_state_snapshot() after the Worker has taken ownership.
        # CR-03: reset so a loaded snapshot whose latest CRITICAL event's
        # tick coincides with the tick already recorded from the current
        # session (plausible given the worker's hardcoded seed=42 and
        # deterministic engine — e.g. reloading the same paused-at-CRITICAL
        # snapshot just saved) still triggers the mandatory CRITICAL dialog
        # in _on_state_updated instead of being silently suppressed.
        # Mirrors _on_stop_requested's identical reset.
        self._last_critical_tick = -1
        # CR-02: reset per-run accumulators before applying the loaded
        # snapshot — otherwise TelemetryDashboard's deque buffers keep
        # appending onto the previous run's history (discontinuous jump in
        # the plots) and EventLog's length-based _seen_count cursor can
        # either interleave stale rows with the loaded run's events or hide
        # the loaded run's events entirely. Mirrors _on_stop_requested's
        # "Новая" flow, which already does this for the same reason.
        self.telemetry.reset()
        self.telemetry.apply_ranges(profile)
        self.event_log.reset()
        self.substances.load_schedules(schedules)
        self._load_simulation.emit((state, profile, schedules))
        # WR-06: bypass the shared 200ms render throttle for this explicit
        # Load call — otherwise a Load within 200ms of the previous render
        # (e.g. right after stopping, or two Loads in a row) silently skips
        # the heavy-render section (telemetry/human-panel/event-log/
        # substances), leaving stale pre-Load values visible until the next
        # Worker-driven tick.
        self._last_render_t = 0.0
        self._on_state_updated(self._worker.get_state_snapshot())

    def _on_export_all_plots(self) -> None:
        """Обработчик «Файл → Экспорт всех графиков» (HF-01, D-02..D-05).

        Порядок (UI-SPEC §Interaction/State Contract): 1) 0-plot guard ДО
        любого диалога → 2) формат (QInputDialog.getItem, раз в прогон) →
        3) папка (QFileDialog.getExistingDirectory) → 4) export_all() →
        5) completion QMessageBox (success/partial-failure). Отмена формата
        или папки прерывает поток тихо — без файлов и без completion-диалога.
        Все диалоги — в self._dialog_open guard (паттерн _on_save_requested/
        _on_load_requested), чтобы _on_state_updated не трогал UI пока
        модальный диалог открыт. Пункт меню всегда включён (не гейтится
        _update_menu_gating()) — экспорт уже отрисованных виджетов безопасен
        при любом статусе симуляции.
        """
        # 1. 0-plot guard — читается ДО открытия любого диалога.
        # IN-02 (12-REVIEW.md): public accessor instead of self.telemetry._plots.
        if self.telemetry.plot_count() == 0:
            QMessageBox.information(
                self,
                "Экспорт всех графиков",
                "Нет графиков для экспорта.",
            )
            return

        # 2. Формат — спрашивается один раз (D-03).
        with self._modal_dialog():
            fmt, ok = QInputDialog.getItem(
                self,
                "Экспорт всех графиков",
                "Выберите формат экспорта:",
                ["PNG", "SVG"],
                0,
                False,
            )
        # WR-03 (12-REVIEW.md): _on_state_updated silently drops
        # state_updated (including CRITICAL-event detection) for the whole
        # time this dialog is open. Re-check with a fresh snapshot right
        # after it closes so a CRITICAL warning/menu-gating update isn't
        # lost while the user was picking a format.
        self._on_state_updated(self._worker.get_state_snapshot())

        if not ok:
            return

        # 3. Папка назначения (D-04).
        with self._modal_dialog():
            folder = QFileDialog.getExistingDirectory(
                self,
                "Выберите папку для экспорта",
            )
        # WR-03: same re-check as above — this picker can legitimately stay
        # open for an arbitrary amount of user time, making the missed-
        # CRITICAL-event window non-negligible.
        self._on_state_updated(self._worker.get_state_snapshot())

        if not folder:
            return

        # 4. Экспорт (D-05 — единый timestamp, имена по коду biomarkers.json).
        ok_count, total, errors = self.telemetry.export_all(fmt, Path(folder))

        # 5. Completion — success или partial-failure вариант.
        if not errors:
            QMessageBox.information(
                self,
                "Экспорт завершён",
                f"Экспортировано {ok_count} графиков в \"{folder}\".",
            )
        else:
            # Русские названия биомаркеров по коду. IN-02 (12-REVIEW.md):
            # public accessor instead of self.telemetry._biomarkers.
            code_to_name = self.telemetry.biomarker_names()
            error_names = ", ".join(code_to_name.get(code, code) for code in errors)
            QMessageBox.warning(
                self,
                "Экспорт завершён с ошибками",
                f"Экспортировано {ok_count} из {total} графиков в \"{folder}\".\n"
                f"Ошибки: {error_names}.",
            )

    def _on_help_requested(self) -> None:
        """Обработчик «Справка» (HF-03, D-10/D-13).

        Открывает ОДИН объединённый QDialog (700×600, min 500×400,
        resizable): сверху User Guide через _build_user_guide_browser()
        (QTextBrowser.setMarkdown), снизу QGroupBox «Дисклеймер» с
        переиспользованным create_disclaimer_label() (байт-в-байт, не новая
        копия текста). Кнопка «Закрыть» (QDialogButtonBox.Close).
        dialog.exec() обёрнут в self._dialog_open guard (паттерн
        _on_save_requested/_on_load_requested/_on_stop_requested), чтобы
        _on_state_updated корректно пропускал обновления UI пока диалог
        открыт. «Справка» всегда включена, не гейтится _update_menu_gating().
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Справка")
        dialog.resize(700, 600)
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        layout.addWidget(_build_user_guide_browser())

        disclaimer_box = QGroupBox("Дисклеймер")
        box_layout = QVBoxLayout(disclaimer_box)
        box_layout.addWidget(create_disclaimer_label())
        layout.addWidget(disclaimer_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        with self._modal_dialog():
            dialog.exec()
        # WR-03 (12-REVIEW.md): re-check for CRITICAL events that
        # _on_state_updated silently dropped while this dialog was open —
        # see the identical pattern in _on_export_all_plots.
        self._on_state_updated(self._worker.get_state_snapshot())

    # ── Жизненный цикл окна ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Сохранить геометрию/состояние доков и корректно завершить QThread.

        Порядок (T-06-13):
          1. Сохранить QSettings
          2. Остановить Worker (shutdown() — не on_stop(), см. IN-02/T-06-13
             ниже: on_stop() больше не завершает run()'s цикл)
          3. Завершить поток (quit + wait 10000 мс)
          4. Вызвать super().closeEvent(event)
        """
        # Сохранить геометрию и состояние доков (D-06)
        settings = QSettings("im-human", "simulator")
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        settings.setValue("mainwindow/dockstate", self.saveState())

        # Корректно остановить KB thread (T-07-06: завершить до simulation thread)
        self.substances.close_kb_thread()

        # Корректно остановить поток (T-06-13)
        # shutdown() (не on_stop()!) необходим: run() — это while-цикл, а не Qt
        # event loop, поэтому QueuedConnection никогда не доставляется (CR-02
        # revert). on_stop() больше не завершает цикл (иначе повторный «Запустить»
        # после «Стоп» не работал бы — см. worker.py docstring) — shutdown()
        # это единственный способ реально остановить run() перед quit()/wait().
        self._worker.shutdown()
        self._thread.quit()
        self._thread.wait(10000)

        super().closeEvent(event)
