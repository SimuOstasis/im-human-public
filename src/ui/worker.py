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
  - IN-03 (10.1-REVIEW.md): _paused/_speed НЕ защищены _state_lock — это
    осознанный выбор, опирающийся на атомарность single-attribute-assignment
    под CPython GIL, а не пропуск блокировки. Оба флага читаются/пишутся
    только целиком (bool/int), никогда не изменяются на месте (нет += и
    т.п.), поэтому lock здесь не даёт дополнительной гарантии корректности —
    но он и не требуется для этих двух атрибутов на CPython.

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

# G-12-2 (D-15, 12-05-PLAN.md): целевая скорость симуляции в тиках/сек при
# множителе x1 — 1 тик (1 модельный час) в реальную секунду (~1 Гц), по
# исходному замыслу Phase 06 (06-CONTEXT.md: "При x1: emit каждый тик,
# ~1 Гц реального времени"). Целевая скорость на любом множителе =
# SIM_TICKS_PER_SECOND_AT_X1 * speed (x10=10/с, x100=100/с, x1000=1000/с,
# x10000=10000/с — последние два CPU-bound, пейсинг там добавляет ~0 сна).
SIM_TICKS_PER_SECOND_AT_X1 = 1.0

# Максимальный размер одного слайса QThread.msleep() внутри пейсинг-цикла
# (G-12-2) — задержка реакции на Пауза/Стоп/смену скорости во время
# низкоскоростного ожидания ограничена порядка этого значения в мс.
_PACE_SLICE_MS = 50


class SimulationWorker(QObject):
    """Worker Object для выполнения движка симуляции в QThread.

    Использует Worker Object паттерн (D-07): объект создаётся в UI-потоке,
    затем перемещается в QThread через moveToThread().

    Signals (Worker → UI):
        state_updated: Эмит копии SimulationState каждые N тиков (N=speed).
        error_occurred: Эмит сообщения об ошибке движка.

    Slots (UI → Worker, подключаются в MainWindow):
        on_start, on_load, on_pause, on_resume, on_stop,
        on_speed_changed, on_substance_added, on_substance_removed
    """

    # ── Сигналы Worker → UI ──────────────────────────────────────────────────
    state_updated = Signal(object)   # SimulationState (model_copy(deep=True), D-06)
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
        # WR-05 (10-REVIEW.md): on_start/on_load/on_pause/on_resume/on_stop are
        # called directly (not via queued signal) from the UI thread and mutate
        # _state/_engine, while run() concurrently reads/reassigns the same
        # attributes on the worker QThread with no synchronization — unlike
        # _schedules, which _schedules_lock already protects (T-06-03).
        self._state_lock = threading.Lock()

    def get_state_snapshot(self) -> SimulationState | None:
        """Вернуть независимый глубокий снапшот self._state (WR-02, D-06).

        Позволяет вызывающим (например, MainWindow) читать _state без
        обращения к приватному атрибуту напрямую и без риска гонки с
        run()'s циклом, который переприсваивает self._state на потоке Worker.

        D-06 (T-10.1-01, 10.1-05-PLAN.md): раньше возвращался self._state
        НАПРЯМУЮ — вложенные dict (biomarker_values и др.) оставались
        расшарены по ссылке между Worker-потоком (пишет) и UI-потоком
        (читает). model_copy(deep=True) снимает независимую копию под
        тем же _state_lock, устраняя гонку данных.
        """
        with self._state_lock:
            return self._state.model_copy(deep=True) if self._state is not None else None

    # ── Слоты управления (UI → Worker) ──────────────────────────────────────

    @Slot(object)
    def on_start(self, profile: HumanProfile) -> None:
        """Подготовить движок и начальное состояние перед запуском QThread.

        Принимает HumanProfile — создаёт engine + initialize().

        WR-04 (10-REVIEW.md): ранее также принимался готовый SimulationState,
        но эта ветка не пересоздавала self._engine (Pitfall 1 — идентичная
        ошибка, которую on_load() ниже явно исправляет пересозданием engine).
        Ветка была недостижима в продакшене (единственный вызывающий путь —
        MainWindow._start_simulation.emit(self._current_profile), всегда
        HumanProfile) и удалена, а не исправлена — восстановление уже
        готового state обслуживается отдельным, корректным on_load().

        Фактический запуск цикла происходит при старте QThread → run();
        on_start только подготавливает state.
        """
        with self._state_lock:
            self._profile = profile
            self._engine = SimulationEngine(self._profile, self._seed)
            self._state = self._engine.initialize()
        self._paused = False

    @Slot(object)
    def on_load(self, payload) -> None:
        """Восстановить движок и состояние из загруженного снепшота (HS-01).

        Args:
            payload: кортеж (SimulationState, HumanProfile, list[IntakeSchedule])
                полученный из src.engine.exporter.load_simulation через
                MainWindow._on_load_requested (T-06-14: только через сигнал).

        Pitfall 1 (RESEARCH.md): on_start()'s SimulationState-ветка НЕ пересоздаёт
        self._engine, оставляя run()-цикл заблокированным навсегда на
        `if self._state is None or self._engine is None: continue`. on_load
        КРИТИЧНО пересоздаёт self._engine с тем же seed, что и в загруженном
        state, гарантируя детерминизм и живой run()-цикл.

        Не выполняет FSM-переход состояния — если загруженный state.status == PAUSED,
        он должен остаться PAUSED (exporter.py Pitfall 2); обычный on_resume-флоу
        выполнит переход PAUSED → RUNNING когда пользователь нажмёт «Возобновить».
        """
        state, profile, schedules = payload
        with self._state_lock:
            # WR-03 (10.1-REVIEW.md): _profile assigned inside the same lock
            # as _engine/_state, matching the locking discipline the rest of
            # this module follows for cross-thread-mutable attributes.
            self._profile = profile
            # КРИТИЧНО (Pitfall 1): пересоздать движок с исходным seed из state
            self._engine = SimulationEngine(profile, seed=state.seed)
            self._state = state
        with self._schedules_lock:
            self._schedules = list(schedules)
        self._paused = (state.status == SimulationStatus.PAUSED)

    @Slot()
    def on_pause(self) -> None:
        """Поставить симуляцию на паузу.

        Устанавливает флаг _paused и переводит FSM в PAUSED если статус RUNNING.
        """
        self._paused = True  # IN-03: атомарная запись под CPython GIL, см. модульный docstring
        with self._state_lock:
            if self._state is not None and self._state.status == SimulationStatus.RUNNING:
                self._state.transition(SimulationStatus.PAUSED)

    @Slot()
    def on_resume(self) -> None:
        """Возобновить симуляцию после паузы.

        Переводит FSM из PAUSED → RUNNING и сбрасывает флаг _paused.
        """
        with self._state_lock:
            if self._state is not None and self._state.status == SimulationStatus.PAUSED:
                self._state.transition(SimulationStatus.RUNNING)
        self._paused = False  # IN-03: атомарная запись под CPython GIL, см. модульный docstring

    @Slot()
    def on_stop(self) -> None:
        """Полностью сбросить прогон (Файл→«Новая», НЕ поток).

        НЕ трогает self._running (см. история ниже) — поток остаётся жив.

        Очищает self._state/self._engine в None, а не просто транзишит
        .status → STOPPED. Регрессия #2 (2026-07-13): пока on_stop() только
        транзишила статус, run()'s idle-ветка (status != RUNNING) продолжала
        каждые ~200мс эмитить state_updated со СТАРЫМИ данными (tick_count/
        biomarker_values из-до сброса) — MainWindow._on_state_updated тут же
        заново применял их во все панели, сводя UI-сброс (main_window.py
        _on_stop_requested: telemetry.reset(), update_indices(None,None) и
        т.д.) на нет почти сразу после подтверждения. С self._state = None
        run()'s ready-проверка (`self._state is not None and self._engine
        is not None`) становится False — цикл просто простаивает, ничего не
        эмитит, пока следующий on_start()/on_load() не заполнит их заново.

        Регрессия #1 (история): on_stop() раньше сама выставляла
        self._running = False, из-за чего run()'s while-цикл завершался
        насовсем (started сигнал QThread срабатывает один раз за всё время
        жизни потока — run() не запускается заново) — повторный «Запустить»
        после «Стоп» тихо ничего не делал. Используй shutdown() для
        настоящего завершения потока (перед закрытием приложения).
        """
        with self._state_lock:
            self._state = None
            self._engine = None
        self._paused = False

    def shutdown(self) -> None:
        """Завершить run()'s while-цикл насовсем (перед QThread.quit()/wait()).

        В отличие от on_stop() (FSM-переход, поток остаётся жив и готов
        принять новый on_start()), это разовая, необратимая команда — только
        для закрытия приложения (MainWindow.closeEvent) и тестового teardown.
        """
        self._running = False

    @Slot(int)
    def on_speed_changed(self, multiplier: int) -> None:
        """Изменить скорость симуляции (D-08).

        Клампит значение: min 1. Эффект применяется на следующей итерации run().
        """
        self._speed = max(1, int(multiplier))  # IN-03: атомарная запись под CPython GIL, см. модульный docstring

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
        - Эмитит state.model_copy(deep=True) один раз на батч → ≤ 5 emit/сек
          (UI-08, WR-04 10-REVIEW.md: throttle interval — 0.2s — matches the
          inline comment above the emit calls below, not the previously-stated
          10/с; D-06: deep=True устраняет расшаривание вложенных dict между
          Worker- и UI-потоком, T-10.1-01)
        - При исключении: эмитит error_occurred и завершает цикл
        - G-12-2 (D-15): после батча — wall-clock пейсинг слайсами
          QThread.msleep() до SIM_TICKS_PER_SECOND_AT_X1 * speed тиков/сек
          (~0 сна на CPU-bound высоких множителях), затем один
          QThread.yieldCurrentThread() для обработки очереди сигналов
          (D-05: заменяет msleep(1)-на-каждый-тик, который на Windows
          реально спит ~14.8мс из-за разрешения системного таймера)

        T-06-04: run_batch вызывается ТОЛЬКО когда status==RUNNING и не paused.
        """
        # If on_stop() was called before run() started, exit without overriding.
        if self._running is False:
            return
        self._running = True

        while self._running:
            # Ждём пока on_start подготовит engine и state (WR-05: под локом,
            # т.к. on_start/on_load переприсваивают эти атрибуты с UI-потока)
            with self._state_lock:
                ready = self._state is not None and self._engine is not None
                status = self._state.status if self._state is not None else None
            if not ready:
                QThread.msleep(50)
                continue

            # Пропускаем итерацию если paused или движок не в RUNNING
            # (T-06-04: engine.tick() бросает ValueError если status != RUNNING)
            if self._paused or status != SimulationStatus.RUNNING:
                # Emit while paused so UI gets status update (buttons, label)
                now = time.monotonic()
                if now - self._last_emit_t >= 0.2:
                    with self._state_lock:
                        snapshot = self._state.model_copy(deep=True) if self._state is not None else None
                    if snapshot is not None:
                        self.state_updated.emit(snapshot)
                    self._last_emit_t = now
                QThread.msleep(50)
                continue

            # N = количество тиков на батч (D-08: масштабируется со скоростью).
            # G-12-2: один атомарный снимок speed переиспользуется и для N, и
            # для пейсинга ниже — без гонки между двумя чтениями self._speed.
            speed = max(1, self._speed)
            N = speed

            # G-12-2: момент начала батч-итерации (включая время вычисления
            # батча) — используется пейсинг-блоком ниже для расчёта дефицита
            # реального времени относительно целевой скорости тиков/сек.
            iter_start = time.monotonic()

            # Снимок расписаний под локом (T-06-03)
            with self._schedules_lock:
                schedules_snapshot = list(self._schedules)

            # Sub-batching: yield GIL every _GIL_WINDOW ticks so the main thread
            # (UI) gets CPU time. Without this, a 100-tick batch holds the GIL for
            # ~135ms, starving Qt's event loop and freezing the window.
            _GIL_WINDOW = 30
            remaining = N
            # IN-02 (10-REVIEW.md): AdaptiveStepper is stateless (see its own
            # docstring) — construct once per run() iteration instead of once
            # per sub-batch, avoiding an unnecessary allocation in the hot loop.
            stepper = AdaptiveStepper()
            try:
                while remaining > 0 and self._running:
                    # WR-05: reassigning self._state races with on_pause/on_resume/
                    # on_stop mutating the same reference from the UI thread — the
                    # lock makes the check-then-reassign atomic relative to them.
                    with self._state_lock:
                        if (
                            self._paused
                            or self._state is None
                            or self._state.status != SimulationStatus.RUNNING
                        ):
                            break
                        sub_n = min(_GIL_WINDOW, remaining)
                        self._state = stepper.run_batch(
                            self._state, self._engine, schedules_snapshot, sub_n
                        )
                    remaining -= sub_n
                    if remaining > 0:
                        QThread.yieldCurrentThread()  # Release GIL; allow main thread to run
            except Exception as exc:
                # CR-01 (10.1-REVIEW.md): a batch/tick exception used to set
                # self._running = False and break out of the OUTER while loop,
                # permanently killing run() for the rest of the process
                # lifetime — QThread.started fires exactly once, so nothing
                # ever restarts run(). Instead, mirror on_stop()'s pattern:
                # clear _state/_engine so the ready-check goes false and the
                # loop idles, letting a subsequent on_start()/on_load() from
                # the UI thread recover the worker without a restart.
                # WR-01: emit the raw exception text — EventLog.add_error is
                # the UI-facing formatter and already prefixes "Ошибка
                # движка: " itself; prefixing here too produced a duplicated
                # "Ошибка движка: Ошибка движка: <text>" in the journal.
                self.error_occurred.emit(str(exc))
                with self._state_lock:
                    self._state = None
                    self._engine = None
                self._paused = False
                continue

            # Emit at most 5 times/s — pyqtgraph software rendering on Windows
            # cannot sustain 20fps with 24 live plots without freezing.
            now = time.monotonic()
            if now - self._last_emit_t >= 0.2:
                with self._state_lock:
                    snapshot = self._state.model_copy(deep=True) if self._state is not None else None
                if snapshot is not None:
                    self.state_updated.emit(snapshot)
                self._last_emit_t = now

            # G-12-2 (D-15): wall-clock пейсинг — ограничивает среднюю
            # скорость итерации до SIM_TICKS_PER_SECOND_AT_X1 * speed
            # тиков/сек. На CPU-bound высоких множителях (x1000/x10000)
            # батч сам по себе уже занял >= target_seconds, remaining
            # отрицателен на первой же проверке — msleep не вызывается,
            # throughput не деградирует. Сон разбит на слайсы <=
            # _PACE_SLICE_MS, чтобы Пауза/Стоп/смена скорости оставались
            # отзывчивыми во время низкоскоростного (x1) ожидания.
            target_seconds = N / (SIM_TICKS_PER_SECOND_AT_X1 * speed)
            while self._running and not self._paused:
                with self._state_lock:
                    if self._state is None:
                        # on_stop() clears _state but leaves _running/_paused
                        # untouched (Regression #1) — без этой проверки Стоп
                        # во время x1-пейсинга ждал бы до target_seconds
                        # (~1с), а не ~_PACE_SLICE_MS, как заявлено выше.
                        break
                remaining = target_seconds - (time.monotonic() - iter_start)
                if remaining <= 0:
                    break
                QThread.msleep(min(int(remaining * 1000), _PACE_SLICE_MS))
                if max(1, self._speed) != speed:
                    # Скорость изменилась во время ожидания — прервать сон и
                    # отдать управление следующей итерации, которая пересчитает
                    # target по новой скорости.
                    break

            # Уступка GIL: обеспечивает обработку очереди сигналов Qt без
            # 14.8мс-издержки msleep(1) на Windows (D-05, 10.1-RESEARCH.md
            # Code Example 5) — yieldCurrentThread() стоит ~0.015мс/вызов
            QThread.yieldCurrentThread()
