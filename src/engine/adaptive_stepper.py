# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""AdaptiveStepper — управление батч-выполнением тиков симуляции.

Тонкая обёртка над engine.tick(): управляет количеством тиков,
проверяет расписание доз (IntakeSchedule + CycleConfig) и прерывается
при SimulationStatus.PAUSED/STOPPED.

Не содержит PK-логики. Вызывается из QThread в Phase 6 (UI).

Threat mitigations:
  T-05-10: cycle_length <= 0 → пропустить cycle check (treat as always-on)
  T-05-11: 10000 тиков запускаются из QThread — UI не блокируется (Phase 6)
"""
from __future__ import annotations

from src.domain.simulation_state import SimulationState, SimulationStatus

# ─── Константы скоростей (для документации UI, не для логики) ────────────────
SPEED_TICKS: dict[int, int] = {
    1: 1,
    10: 10,
    100: 100,
    1000: 1000,
    10000: 10000,
}


class AdaptiveStepper:
    """Батч-выполнение тиков с поддержкой паузы и расписания доз.

    Stateless — не хранит состояние между вызовами run_batch.
    UI (Phase 6) создаёт экземпляр один раз и вызывает run_batch из QThread.
    """

    def __init__(self) -> None:
        """Нет параметров — stepper не хранит состояние."""
        pass

    def run_batch(
        self,
        state: SimulationState,
        engine: object,
        schedules: list,
        num_ticks: int,
    ) -> SimulationState:
        """Выполнить num_ticks тиков последовательно.

        Прерывается досрочно при state.status == PAUSED или STOPPED.
        PAUSED проверяется ДО и ПОСЛЕ каждого тика (D-15: CRITICAL → PAUSED).

        Args:
            state: Текущее состояние симуляции (FSM).
            engine: Объект с методом tick(state, schedules) → SimulationState.
            schedules: Список IntakeSchedule для передачи в engine.tick().
            num_ticks: Количество тиков для выполнения (1..10000).

        Returns:
            Обновлённый SimulationState после выполнения тиков.
        """
        for _ in range(num_ticks):
            # Ранний выход если уже PAUSED/STOPPED до тика
            if state.status in (SimulationStatus.PAUSED, SimulationStatus.STOPPED):
                break
            state = engine.tick(state, schedules)
            # Ранний выход если тик поставил на паузу (например, CRITICAL event)
            if state.status in (SimulationStatus.PAUSED, SimulationStatus.STOPPED):
                break
        return state

    @staticmethod
    def should_dose(schedule: object, tick: int) -> bool:
        """Проверить, нужно ли давать дозу на данном тике.

        Алгоритм:
          1. Проверить start_tick (tick < start_tick → False)
          2. Проверить duration_ticks (tick >= start + duration → False)
          3. Проверить час дня (tick % 24 != hour_of_day → False)
          4. Проверить CycleConfig (day_in_cycle >= on_days → False)
          5. Иначе → True

        T-05-10: cycle_length <= 0 → пропустить cycle check (treat as always-on).

        Args:
            schedule: IntakeSchedule или объект с атрибутами
                      substance_id, dose_mg, hour_of_day,
                      start_tick, duration_ticks, cycle (CycleConfig|None).
            tick: Текущий тик симуляции (тики = часы).

        Returns:
            True если доза должна быть выдана на этом тике.
        """
        start_tick = getattr(schedule, "start_tick", 0)

        # 1. Ещё не началось
        if tick < start_tick:
            return False

        # 2. Истёк срок
        duration = getattr(schedule, "duration_ticks", None)
        if duration is not None and tick >= start_tick + duration:
            return False

        # 3. Час дня (тик — это час; 1 тик = 1 час)
        hour_of_day = getattr(schedule, "hour_of_day", 0)
        if tick % 24 != hour_of_day:
            return False

        # 4. Цикл on/off (например, Rapamycin: on_days=1, off_days=6)
        cycle = getattr(schedule, "cycle", None)
        if cycle is not None:
            on_days = getattr(cycle, "on_days", 1)
            off_days = getattr(cycle, "off_days", 0)
            cycle_length = on_days + off_days
            # T-05-10: защита от ZeroDivisionError
            if cycle_length <= 0:
                pass  # treat as always-on
            else:
                day_number = (tick - start_tick) // 24
                day_in_cycle = day_number % cycle_length
                if day_in_cycle >= on_days:
                    return False

        return True


# ─── Модульная функция-обёртка (для обратной совместимости с тестами) ─────────


def run_batch(
    state: SimulationState,
    schedules: list,
    engine: object,
    num_ticks: int,
) -> SimulationState:
    """Модульная обёртка над AdaptiveStepper.run_batch.

    Используется в test_benchmark.py для удобного импорта:
      from src.engine.adaptive_stepper import run_batch
    """
    return AdaptiveStepper().run_batch(state, engine, schedules, num_ticks)


# ─── Встроенные тесты для проверки should_dose ────────────────────────────────

if __name__ == "__main__":
    """Rapamycin CycleConfig(on_days=1, off_days=6), hour_of_day=8, start_tick=0."""

    class _FakeCycle:
        on_days = 1
        off_days = 6

    class _FakeSchedule:
        substance_id = "rapamycin"
        dose_mg = 5.0
        hour_of_day = 8
        start_tick = 0
        duration_ticks = None
        cycle = _FakeCycle()

    s = _FakeSchedule()

    # Тик 8: день 0, час 8, day_in_cycle=0 < 1 → True
    assert AdaptiveStepper.should_dose(s, 8) is True, "тик 8 должен быть дозой"
    # Тик 32: день 1, час 8, day_in_cycle=1 >= 1 → False (off-день)
    assert AdaptiveStepper.should_dose(s, 32) is False, "тик 32 не доза (off-день)"
    # Тик 56: день 2, день цикла=2 >= 1 → False
    assert AdaptiveStepper.should_dose(s, 56) is False, "тик 56 не доза (off-день 2)"
    # Тик 176: день 7 (=7 % 7 = 0), day_in_cycle=0 < 1 → True (новый цикл)
    assert AdaptiveStepper.should_dose(s, 176) is True, "тик 176 доза (новый цикл)"
    # Тик 9: час 9 != 8 → False
    assert AdaptiveStepper.should_dose(s, 9) is False, "тик 9: wrong hour"

    print("AdaptiveStepper.should_dose OK — все тесты пройдены")
