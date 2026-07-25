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
import os

# Установить до любого импорта PySide6 (test_worker_throughput_benchmark,
# D-05/D-07) — Qt не пытается открыть реальный дисплей (T-06-16).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def test_worker_throughput_benchmark():
    """Пропускная способность worker.run() (тиков/сек) на x10000 (D-05/D-07).

    Меряет уровень worker.run() (с msleep/yield/sub-batching), НЕ голый
    engine.tick() — существующий test_benchmark_8760_ticks_under_5_seconds
    выше меряет только движок и не покрывает эту фазу (10.1-RESEARCH.md
    Validation Architecture § Test Map, D-05/D-07).

    Без жёсткого числового порога (D-07 явно запрещает машинно-зависимый
    порог, 10.1-CONTEXT.md) — печатает измеренную пропускную способность
    для сравнения baseline до/после фиксов D-02..D-06, ассертит только
    рост tick_count за фиксированное wall-time окно.
    """
    import time

    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    from src.domain.human_profile import HumanProfile
    from src.ui.worker import SimulationWorker

    app = QApplication.instance() or QApplication([])

    worker = SimulationWorker()
    profile = HumanProfile.from_preset("middle_age_50f")
    worker.on_start(profile)
    worker.on_speed_changed(10000)

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.start()

    try:
        tick_before = worker.get_state_snapshot().tick_count

        time.sleep(1.0)

        snapshot_after = worker.get_state_snapshot()
        tick_after = snapshot_after.tick_count if snapshot_after is not None else tick_before

        delta = tick_after - tick_before
        print(
            f"\n[D-05/D-07 benchmark] {delta} тиков за ~1.0с окно на x10000 "
            f"(baseline измерение до/после фиксов D-02..D-06)"
        )

        assert delta > 0, (
            f"tick_count не вырос за 1.0с окно (delta={delta}) — worker.run() не продвигается на x10000"
        )
    finally:
        worker.shutdown()
        if thread.isRunning():
            thread.quit()
            thread.wait(5000)
        app.processEvents()
