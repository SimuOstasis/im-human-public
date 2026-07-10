# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""_age_utils — общая утилита определения возрастного диапазона для движка.

Единственная реализация _get_age_band, импортируемая homeostasis.py и event_detector.py.
Устраняет дублирование (WR-01).
"""
from __future__ import annotations

# Возрастные группы: (нижняя граница включительно, ключ в reference_ranges.json)
_AGE_GROUPS: list[tuple[int, str]] = [
    (18, "18-29"),
    (30, "30-39"),
    (40, "40-49"),
    (50, "50-59"),
    (60, "60-69"),
    (70, "70+"),
]


def get_age_band(age: int) -> str:
    """Вернуть строку возрастного диапазона для look-up в reference_ranges.json.

    Итерируется по убыванию возраста и возвращает первое совпадение.
    Границы: 18→"18-29", 30→"30-39", 40→"40-49", 50→"50-59", 60→"60-69", 70→"70+"

    Args:
        age: Возраст в годах.

    Returns:
        Строка-ключ возрастного диапазона (напр. "40-49").
        Возвращает "18-29" для возраста < 18 (edge-case).
    """
    for low, band in reversed(_AGE_GROUPS):
        if age >= low:
            return band
    return "18-29"  # fallback для edge-case (age < 18)
