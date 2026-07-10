# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Тесты воспроизводимости и паузы/возобновления (ENG-01, ENG-10).

Тесты активны; движок реализован в Phase 5 (simulation_engine.py).
"""

from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


def test_seed_reproducibility():
    """Два прогона с одним seed дают побитово идентичные biomarker_values.

    Проверяет ENG-01 (RNG детерминизм) + ENG-10 (воспроизводимость).
    Алгоритм:
      1. run_simulation(seed=42, ticks=8760, profile="young_healthy_30m") -> state1
      2. run_simulation(seed=42, ticks=8760, profile="young_healthy_30m") -> state2
      3. state1.biomarker_values[code] == state2.biomarker_values[code] для всех биомаркеров.
    Использует == (не isclose) — требуется побитовая идентичность.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")

    def run(seed: int) -> dict:
        engine = SimulationEngine(profile=profile, seed=seed)
        state = engine.initialize()
        for _ in range(8760):
            state = engine.tick(state, schedules=[])
        return state.biomarker_values.copy()

    values1 = run(42)
    values2 = run(42)

    for code in values1:
        assert values1[code] == values2[code], (
            f"Нарушение воспроизводимости: {code}: {values1[code]} != {values2[code]}"
        )


def test_pause_resume_reproducibility():
    """Пауза → возобновление → продолжение совпадает с непрерывным прогоном.

    Проверяет ENG-10: RNG состояние корректно сохраняется/восстанавливается.
    Алгоритм:
      1. Непрерывный прогон: seed=42, ticks=200 -> state_continuous
      2. Прогон с паузой: seed=42, 100 тиков -> сохранить rng_state -> восстановить -> 100 тиков -> state_resumed
      3. state_continuous.biomarker_values == state_resumed.biomarker_values (побитово).

    Критерий: RNG состояние должно быть сохранено в SimulationState.rng_state
    перед паузой и восстановлено при возобновлении.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")

    # Путь 1: непрерывный прогон 200 тиков
    engine1 = SimulationEngine(profile=profile, seed=42)
    state1 = engine1.initialize()
    for _ in range(200):
        state1 = engine1.tick(state1, schedules=[])

    # Путь 2: 100 тиков -> пауза -> 100 тиков
    engine2 = SimulationEngine(profile=profile, seed=42)
    state2 = engine2.initialize()
    for _ in range(100):
        state2 = engine2.tick(state2, schedules=[])

    # Сохранить состояние RNG (пауза)
    state2.rng_state = engine2.rng.get_state()

    # Создать новый движок (симуляция перезагрузки приложения)
    engine3 = SimulationEngine(profile=profile, seed=42)  # seed не важен — будет overridden
    engine3.rng.set_state(state2.rng_state)               # восстановить RNG

    for _ in range(100):
        state2 = engine3.tick(state2, schedules=[])

    for code in state1.biomarker_values:
        assert state1.biomarker_values[code] == state2.biomarker_values[code], (
            f"Pause/resume нарушает воспроизводимость: "
            f"{code}: continuous={state1.biomarker_values[code]}, "
            f"resumed={state2.biomarker_values[code]}"
        )
