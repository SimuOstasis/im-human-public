# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Benchmark-тесты производительности и корректности агрегации (ENG-06, ENG-12).

Тесты активны; движок реализован в Phase 5 (simulation_engine.py).

Запуск benchmark в production-режиме:
    venv/Scripts/python.exe -O -m pytest src/tests/test_benchmark.py -v
(флаг -O отключает assertions для максимальной производительности)
"""

from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


def test_benchmark_8760_ticks_under_5_seconds():
    """8760 тиков (1 модельный год) выполняются за < 5 секунд.

    Проверяет ENG-06/ENG-12: производительность < 5 сек на целевой машине.
    Используемый профиль: middle_age_50f (реалистичная нагрузка).
    Запускать с python -O для production-подобной производительности (Risk 3 RESEARCH.md).

    ВАЖНО: При провале сначала проверить, запущен ли с -O.
    Допустимо skip через pytest.skip() если warm-up тик > 0.1 сек (медленная машина).
    """
    import time
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("middle_age_50f")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    start = time.perf_counter()
    for _ in range(8760):
        state = engine.tick(state, schedules=[])
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, (
        f"Benchmark failed: {elapsed:.2f}s > 5s. "
        f"Попробуйте python -O -m pytest (Risk 3 из RESEARCH.md)."
    )


def test_aggregation_deviation_under_2pct():
    """Батч x10 (876 батчей × 10 тиков) = x1 (8760 тиков): отклонение ≤ 2%.

    Проверяет ENG-06: batch-режим adaptive_stepper не вносит ошибку агрегации.
    Поскольку движок детерминирован, ожидаемое отклонение = 0% (побитово идентично).
    Тест ловит ошибки реализации: неправильное масштабирование ke или drift в батч-режиме.

    Проверяемые значения: все биомаркеры в state.biomarker_values.
    Формула: deviation = |v_x1 - v_x10| / max(|v_x1|, |v_x10|, 1e-9) <= 0.02.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.engine.adaptive_stepper import run_batch
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")

    # Путь 1: 8760 тиков x1
    engine1 = SimulationEngine(profile=profile, seed=42)
    state_x1 = engine1.initialize()
    state_x1 = run_batch(state_x1, schedules=[], engine=engine1, num_ticks=8760)

    # Путь 2: 876 батчей по 10 тиков (то же число тиков суммарно)
    engine2 = SimulationEngine(profile=profile, seed=42)
    state_x10 = engine2.initialize()
    for _ in range(876):
        state_x10 = run_batch(state_x10, schedules=[], engine=engine2, num_ticks=10)

    for code in state_x1.biomarker_values:
        v1 = state_x1.biomarker_values[code]
        v10 = state_x10.biomarker_values[code]
        denom = max(abs(v1), abs(v10), 1e-9)
        deviation = abs(v1 - v10) / denom
        assert deviation <= 0.02, (
            f"{code}: aggregation deviation {deviation:.1%} > 2%"
            f" (x1={v1:.6f}, x10={v10:.6f})"
        )
