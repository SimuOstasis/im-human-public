# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Регрессионные тесты wall-clock пейсинга SimulationWorker.run() (G-12-2, D-15).

До фикса worker.run() не имел никакого real-time ограничения скорости —
на x1 тик-цикл продвигался на тысячи тиков за доли секунды (см.
.planning/debug/sim-start-hang-speed.md). Эти тесты защищают от возврата
беспейсингового поведения (test_x1_is_wall_clock_paced) и от деградации
high-множительного throughput пейсинг-логикой (test_high_multiplier_not_crippled_by_pacing).

Пороги выбраны с большим запасом (беспейсинговый x1 давал бы тысячи тиков за
окно; запейсенный — единицы), чтобы не флейкать под CI-нагрузкой — тесты не
меряют точную частоту, а защищают от регрессии механизма.
"""
import os

# Установить до любого импорта PySide6 (D-05/D-07, зеркалирует
# test_benchmark.py) — Qt не пытается открыть реальный дисплей (T-06-16).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from src.domain.human_profile import HumanProfile
from src.ui.worker import SimulationWorker


def test_x1_is_wall_clock_paced():
    """На x1 (default speed) tick_count растёт на единицы тиков за ~1.3с, не на тысячи (G-12-2).

    RED до фикса: беспейсинговый worker.run() продвигал тик-цикл на тысячи
    тиков за это же окно. GREEN после фикса: пейсинг-блок ограничивает
    среднюю скорость до SIM_TICKS_PER_SECOND_AT_X1 * speed ~= 1 тик/сек.
    """
    app = QApplication.instance() or QApplication([])

    worker = SimulationWorker()
    profile = HumanProfile.from_preset("middle_age_50f")
    worker.on_start(profile)
    # speed остаётся default x1 — не меняем.

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.start()

    try:
        tick_before = worker.get_state_snapshot().tick_count

        time.sleep(1.3)

        snapshot_after = worker.get_state_snapshot()
        tick_after = snapshot_after.tick_count if snapshot_after is not None else tick_before

        delta = tick_after - tick_before
        print(f"\n[G-12-2 pacing] x1: {delta} тиков за ~1.3с окно")

        assert tick_after >= 1, (
            f"tick_count не вырос за 1.3с окно на x1 (tick_after={tick_after}) "
            f"— симуляция заморожена"
        )
        assert delta <= 60, (
            f"x1 не запейсен: {delta} тиков за 1.3с окно (ожидалось <= 60, "
            f"~1 тик/сек по D-15) — возможен возврат к беспейсинговому поведению"
        )
    finally:
        worker.shutdown()
        if thread.isRunning():
            thread.quit()
            thread.wait(5000)
        app.processEvents()


def test_high_multiplier_not_crippled_by_pacing():
    """На x10000 пейсинг добавляет ~0 сна — throughput не деградирует (G-12-2).

    Целевая скорость на x10000 (10000 тиков/сек) выше фактической CPU-
    пропускной способности worker.run(), поэтому дефицит времени
    (target_seconds - фактическое время батча) отрицателен и msleep не
    вызывается. Защищает test_worker_throughput_benchmark-подобный
    сценарий от искажения пейсинг-логикой.
    """
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
        print(f"\n[G-12-2 pacing] x10000: {delta} тиков за ~1.0с окно")

        # Без жёсткого числового порога (D-07 запрещает машинно-зависимый
        # порог, 10.1-CONTEXT.md) — зеркалирует test_worker_throughput_benchmark
        # (test_benchmark.py), измеренная delta печатается выше для сравнения.
        assert delta > 0, (
            f"x10000 искалечен пейсингом: tick_count не вырос за 1.0с окно "
            f"(delta={delta}) — throughput деградировал"
        )
    finally:
        worker.shutdown()
        if thread.isRunning():
            thread.quit()
            thread.wait(5000)
        app.processEvents()
