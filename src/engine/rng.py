# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Детерминированный RNG для симуляционного движка."""

import random


class SimulationRNG:
    """Детерминированный RNG на основе Mersenne Twister.

    Побитово идентичные результаты гарантированы при одном seed и одинаковом
    порядке вызовов. НЕ использовать os.urandom, datetime или глобальный random
    внутри симуляции — только этот класс.

    Использование:
        rng = SimulationRNG(seed=42)
        val = rng.random()          # float в [0.0, 1.0)
        state = rng.get_state()     # снять состояние для паузы
        rng.set_state(state)        # восстановить при возобновлении
    """

    def __init__(self, seed: int) -> None:
        """Инициализировать RNG с заданным seed.

        Args:
            seed: Начальное значение (int >= 0). Одинаковый seed даёт
                  побитово идентичные последовательности чисел.
        """
        self._rng = random.Random(seed)

    def random(self) -> float:
        """Вернуть следующее случайное число в [0.0, 1.0)."""
        return self._rng.random()

    def get_state(self) -> tuple:
        """Снять состояние RNG для паузы/сохранения.

        Сохранять в SimulationState.rng_state перед паузой.
        Returns:
            Кортеж состояния Mersenne Twister (непрозрачный, не изменять вручную).
        """
        return self._rng.getstate()

    def set_state(self, state: tuple) -> None:
        """Восстановить состояние RNG при возобновлении.

        Args:
            state: Кортеж, ранее полученный через get_state().
        """
        self._rng.setstate(state)
