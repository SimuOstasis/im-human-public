# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""SimulationWorker — Worker Object паттерн (D-07) для QThread-интеграции.

Перемещается в QThread через moveToThread(). Движок симуляции выполняется
в рабочем потоке, UI не блокируется даже при x10000.

Threading:
  - UI → Worker: управляющие сигналы через QueuedConnection (автоматически)
  - Worker → UI: state_updated / error_occurred через QueuedConnection
  - _schedules доступ: threading.Lock (D-10, T-06-03)

Угрозы:
  T-06-03: threading.Lock вокруг всех операций с _schedules
  T-06-04: проверка status==RUNNING и _paused до вызова run_batch;
           исключения ловятся и эмитятся как error_occurred
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.engine.simulation_engine import SimulationEngine
from src.engine.adaptive_stepper import AdaptiveStepper
from src.domain.simulation_state import SimulationState, SimulationStatus
from src.domain.human_profile import HumanProfile
from src.domain.substance import IntakeSchedule


class SimulationWorker(QObject):
    """Worker Object для выполнения движка симуляции в QThread.

    Использует Worker Object паттерн (D-07): объект создаётся в UI-потоке,
    затем перемещается в QThread через moveToThread().

    Signals (Worker → UI):
        state_updated: Эмит копии SimulationState каждые N тиков (N=speed).
        error_occurred: Эмит сообщения об ошибке движка.

    Slots (UI → Worker, подключаются в MainWindow):
        on_start, on_pause, on_resume, on_stop,
        on_speed_changed, on_substance_added, on_substance_removed
    """

    # ── Сигналы Worker → UI ──────────────────────────────────────────────────
    state_updated = Signal(object)   # SimulationState (model_copy)
    error_occurred = Signal(str)     # текст ошибки движка

    def __init__(self) -> None:
        super().__init__()
        self._running: bool | None = None  # None=not started, True=running, False=stopped
        self._paused: bool = False
        self._speed: int = 1
        self._state: SimulationState | None = None
        self._engine: SimulationEngine | None = None
        self._profile: HumanProfile | None = None
        self._seed: int = 42
        self._schedules_lock = threading.Lock()
        self._schedules: list[IntakeSchedule] = []
        self._last_emit_t: float = 0.0  # throttle: emit state_updated max 20/s

    # ── Слоты управления (UI → Worker) ──────────────────────────────────────

    @Slot(object)
    def on_start(self, profile_or_state: HumanProfile | SimulationState) -> None:
        """Подготовить движок и начальное состояние перед запуском QThread.

        Принимает либо HumanProfile (создаёт engine + initialize()),
        либо готовый SimulationState (повторное использование существующего).

        Фактический запуск цикла происходит при старте QThread → run();
        on_start только подготавливает state.
        """
        if isinstance(profile_or_state, HumanProfile):
            self._profile = profile_or_state
            self._engine = SimulationEngine(self._profile, self._seed)
            self._state = self._engine.initialize()
        elif isinstance(profile_or_state, SimulationState):
            self._state = profile_or_state
        self._paused = False

    @Slot()
    def on_pause(self) -> None:
        """Поставить симуляцию на паузу.

        Устанавливает флаг _paused и переводит FSM в PAUSED если статус RUNNING.
        """
        self._paused = True
        if self._state is not None and self._state.status == SimulationStatus.RUNNING:
            self._state.transition(SimulationStatus.PAUSED)

    @Slot()
    def on_resume(self) -> None:
        """Возобновить симуляцию после паузы.

        Переводит FSM из PAUSED → RUNNING и сбрасывает флаг _paused.
        """
        if self._state is not None and self._state.status == SimulationStatus.PAUSED:
            self._state.transition(SimulationStatus.RUNNING)
        self._paused = False

    @Slot()
    def on_stop(self) -> None:
        """Остановить симуляцию полностью.

        Учитывает _ALLOWED_TRANSITIONS: PAUSED → RUNNING → STOPPED,
        RUNNING → STOPPED напрямую.
        """
        self._running = False
        if self._state is None:
            return
        if self._state.status == SimulationStatus.PAUSED:
            # PAUSED разрешён только → RUNNING, поэтому сначала resume
            self._state.transition(SimulationStatus.RUNNING)
            self._state.transition(SimulationStatus.STOPPED)
        elif self._state.status == SimulationStatus.RUNNING:
            self._state.transition(SimulationStatus.STOPPED)
        # IDLE/STOPPED — уже в терминальном или нейтральном состоянии, ничего

    @Slot(int)
    def on_speed_changed(self, multiplier: int) -> None:
        """Изменить скорость симуляции (D-08).

        Клампит значение: min 1. Эффект применяется на следующей итерации run().
        """
        self._speed = max(1, int(multiplier))

    @Slot(object)
    def on_substance_added(self, schedule: IntakeSchedule) -> None:
        """Добавить расписание вещества потокобезопасно (D-10, T-06-03)."""
        with self._schedules_lock:
            self._schedules.append(schedule)

    @Slot(str)
    def on_substance_removed(self, substance_id: str) -> None:
        """Удалить расписание вещества по ID потокобезопасно (D-10, T-06-03)."""
        with self._schedules_lock:
            self._schedules = [
                s for s in self._schedules if s.substance_id != substance_id
            ]

    # ── Цикл выполнения (вызывается из QThread.started) ─────────────────────

    def run(self) -> None:
        """Цикл батч-выполнения движка. Вызывается по сигналу QThread.started.

        Работает в Worker-потоке. Алгоритм (D-08):
        - Ждёт готовности state/engine (on_start должен быть вызван первым)
        - Пропускает итерацию если paused или state.status != RUNNING
        - Выполняет N = max(1, speed) тиков через AdaptiveStepper().run_batch()
        - Эмитит state.model_copy() один раз на батч → ≤ 10 emit/сек (UI-08)
        - При исключении: эмитит error_occurred и завершает цикл
        - QThread.msleep(1) в конце итерации для обработки очереди сигналов

        T-06-04: run_batch вызывается ТОЛЬКО когда status==RUNNING и не paused.
        """
        # If on_stop() was called before run() started, exit without overriding.
        if self._running is False:
            return
        self._running = True

        while self._running:
            # Ждём пока on_start подготовит engine и state
            if self._state is None or self._engine is None:
                QThread.msleep(50)
                continue

            # Пропускаем итерацию если paused или движок не в RUNNING
            # (T-06-04: engine.tick() бросает ValueError если status != RUNNING)
            if self._paused or self._state.status != SimulationStatus.RUNNING:
                # Emit while paused so UI gets status update (buttons, label)
                now = time.monotonic()
                if now - self._last_emit_t >= 0.2:
                    self.state_updated.emit(self._state.model_copy())
                    self._last_emit_t = now
                QThread.msleep(50)
                continue

            # N = количество тиков на батч (D-08: масштабируется со скоростью)
            N = max(1, self._speed)

            # Снимок расписаний под локом (T-06-03)
            with self._schedules_lock:
                schedules_snapshot = list(self._schedules)

            # Sub-batching: yield GIL every _GIL_WINDOW ticks so the main thread
            # (UI) gets CPU time. Without this, a 100-tick batch holds the GIL for
            # ~135ms, starving Qt's event loop and freezing the window.
            _GIL_WINDOW = 5
            remaining = N
            try:
                while remaining > 0 and self._running:
                    if self._paused or self._state.status != SimulationStatus.RUNNING:
                        break
                    sub_n = min(_GIL_WINDOW, remaining)
                    self._state = AdaptiveStepper().run_batch(
                        self._state, self._engine, schedules_snapshot, sub_n
                    )
                    remaining -= sub_n
                    if remaining > 0:
                        QThread.msleep(1)  # Release GIL; allow main thread to run
            except Exception as exc:
                self.error_occurred.emit(f"Ошибка движка: {exc}")
                self._running = False
                break

            # Emit at most 5 times/s — pyqtgraph software rendering on Windows
            # cannot sustain 20fps with 24 live plots without freezing.
            now = time.monotonic()
            if now - self._last_emit_t >= 0.2:
                self.state_updated.emit(self._state.model_copy())
                self._last_emit_t = now

            # Пауза 1 мс: гарантирует обработку очереди сигналов Qt
            # и не позволяет превысить ~1000 итераций/сек на быстрых батчах
            QThread.msleep(1)
