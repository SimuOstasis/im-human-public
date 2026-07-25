# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Disclaimer — постоянный виджет дисклеймера для QStatusBar.

UI-09: QLabel с точным текстом из CLAUDE.md §Дисклеймер.
Шрифт 11px, цвет #9e9e9e (text secondary).
Добавляется в QStatusBar как permanentWidget — виден при всех статусах симуляции.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

# Точный текст дисклеймера из CLAUDE.md §Дисклеймер (UI-09).
# Короткая форма сохранена намеренно (ограниченное пространство QStatusBar, D-21,
# .planning/phases/11-foundation/11-CONTEXT.md) — расширенная формулировка живёт в
# 07 - Analysis/Known Limitations.md.
DISCLAIMER_TEXT = (
    "Это исследовательская симуляция, а не медицинский диагностический инструмент.\n"
    "Результаты не являются медицинской рекомендацией.\n"
    "Не является медицинской или юридической консультацией.\n"
    "Все числа отражают внутреннюю механику модели.\n"
    "Рапамицин и метформин — рецептурные препараты."
)


def create_disclaimer_label() -> QLabel:
    """Создать QLabel с текстом дисклеймера для QStatusBar.

    Возвращает QLabel, который MainWindow (план 06-06) добавляет
    в QStatusBar.addPermanentWidget() — виден постоянно при любом
    статусе симуляции (UI-09).

    Returns:
        QLabel со шрифтом 11px и цветом #9e9e9e (UI-SPEC.md §Disclaimer).
    """
    label = QLabel(DISCLAIMER_TEXT)
    label.setStyleSheet("font-size: 11px; color: #9e9e9e;")
    return label
