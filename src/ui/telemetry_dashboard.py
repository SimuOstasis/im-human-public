# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""TelemetryDashboard — 24 мини-плота PyQtGraph в QScrollArea+QGridLayout 4×6.

Функции:
  - 24 pg.PlotWidget итерируются из biomarkers.json (порядок = порядок сетки)
  - deque(maxlen=5000) на биомаркер (D-03, UI-10) — ограничение памяти
  - Цветовые зоны через pg.LinearRegionItem (D-13) — optimal/borderline/high_risk
  - apply_ranges(profile) обновляет зоны при смене профиля (не каждый тик)
  - update(biomarker_values) аппендит в deque и вызывает curve.setData

Decisions: D-03 (deque maxlen=5000), D-11 (4×6 GridLayout), D-13 (LinearRegionItem)
Requirements: UI-05 (24 графика), UI-10 (даунсэмплинг ≤5000 точек)
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.domain.human_profile import Sex

# Путь к файлу биомаркеров (src/ui/telemetry_dashboard.py → 2 уровня вверх → src/data/)
_BIOMARKERS_FILE = Path(__file__).parent.parent / "data" / "biomarkers.json"


class TelemetryDashboard(QWidget):
    """Виджет дашборда с 24 живыми мини-плотами PyQtGraph.

    Компоновка: QScrollArea → QWidget → QGridLayout (4 колонки × 6 строк).
    Каждый плот содержит:
      - curve (#3daee9) — живая линия биомаркера
      - deque(maxlen=5000) — ограниченный буфер истории (UI-10)
      - pg.LinearRegionItem × 1-3 — цветовые зоны диапазонов (D-13)

    Публичный интерфейс:
      apply_ranges(profile)         — обновить цветовые зоны по полу профиля
      update(biomarker_values)      — добавить новые значения и перерисовать плоты
    """

    def __init__(self) -> None:
        super().__init__()

        # Загрузить biomarkers.json (коды, русские названия, единицы, reference_ranges)
        # CR-03: обработка отсутствующего или повреждённого файла
        try:
            data = json.loads(_BIOMARKERS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            import warnings
            warnings.warn(f"biomarkers.json not found or invalid: {exc}")
            data = {"reference_ranges": {}, "biomarkers": []}
        self._ranges: dict = data["reference_ranges"]
        self._biomarkers: list[dict] = data["biomarkers"]

        # Внутренние хранилища
        self._plots: dict[str, pg.PlotWidget] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._buffers: dict[str, collections.deque] = {}
        self._regions: dict[str, list] = {}  # список LinearRegionItem per code

        # ── Компоновка: QVBoxLayout → QScrollArea → inner QWidget + QGridLayout ──
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer_layout.addWidget(self._scroll)

        inner_widget = QWidget()
        self._scroll.setWidget(inner_widget)

        grid = QGridLayout(inner_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(4)

        # ── Создать 24 мини-плота (4 колонки × 6 строк) ──────────────────────
        tick_font = QFont("Segoe UI", 10)

        for i, bm in enumerate(self._biomarkers):
            code: str = bm["code"]
            name_ru: str = bm["name_ru"]
            units: str = bm["units"]
            row = i // 4
            col = i % 4

            # Инициализация PlotWidget по контракту UI-SPEC.md §PyQtGraph Plot Contracts
            plot = pg.PlotWidget(title=f"{name_ru} ({units})")
            plot.setBackground('#2d2d2d')
            plot.showGrid(x=False, y=True, alpha=0.3)
            plot.setMouseEnabled(x=False, y=False)
            plot.getAxis('left').setStyle(tickFont=tick_font)
            plot.getAxis('left').setPen(pg.mkPen('#3a3a3a'))
            plot.getAxis('bottom').hide()
            plot.setMinimumHeight(120)
            plot.setMinimumWidth(200)

            # Линия биомаркера — акцентный цвет #3daee9
            curve = plot.plot(pen=pg.mkPen('#3daee9', width=1.5))

            # Буфер истории — максимум 5000 точек (D-03, UI-10)
            buf: collections.deque = collections.deque(maxlen=5000)

            # Сохранить
            self._plots[code] = plot
            self._curves[code] = curve
            self._buffers[code] = buf
            self._regions[code] = []

            grid.addWidget(plot, row, col)

        # Растянуть все 4 колонки и 6 строк равномерно (UI-SPEC.md §Grid layout)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        for r in range(6):
            grid.setRowStretch(r, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────────

    def apply_ranges(self, profile) -> None:  # profile: HumanProfile
        """Обновить цветовые зоны (LinearRegionItem) на всех плотах по полу профиля.

        Вызывать при смене пресета — не каждый тик (D-13).
        Sex-специфичный приоритет: optimal_m / optimal_f → optimal (fallback).

        Args:
            profile: HumanProfile — профиль с profile.demographics.sex.
        """
        sex: Sex = profile.demographics.sex

        for code, plot in self._plots.items():
            # Удалить ранее добавленные зоны
            for region in self._regions[code]:
                plot.removeItem(region)
            self._regions[code] = []

            if code not in self._ranges:
                continue

            ranges = self._ranges[code]
            new_regions: list[pg.LinearRegionItem] = []

            # ── Optimal диапазон (sex-специфичный) ───────────────────────────
            optimal = None
            if sex == Sex.male and "optimal_m" in ranges:
                optimal = ranges["optimal_m"]
            elif sex == Sex.female and "optimal_f" in ranges:
                optimal = ranges["optimal_f"]
            elif "optimal" in ranges:
                optimal = ranges["optimal"]

            if optimal is not None:
                region = pg.LinearRegionItem(
                    values=[
                        optimal.get("min", -1e9),
                        optimal.get("max", 1e9),
                    ],
                    orientation="horizontal",
                    brush=pg.mkBrush(0, 200, 0, 30),
                    movable=False,
                )
                plot.addItem(region)
                new_regions.append(region)

            # ── Borderline диапазон ───────────────────────────────────────────
            if "borderline" in ranges:
                borderline = ranges["borderline"]
                region = pg.LinearRegionItem(
                    values=[
                        borderline.get("min", -1e9),
                        borderline.get("max", 1e9),
                    ],
                    orientation="horizontal",
                    brush=pg.mkBrush(255, 200, 0, 30),
                    movable=False,
                )
                plot.addItem(region)
                new_regions.append(region)

            # ── High-risk диапазон ────────────────────────────────────────────
            if "high_risk" in ranges:
                high_risk = ranges["high_risk"]
                region = pg.LinearRegionItem(
                    values=[
                        high_risk.get("min", -1e9),
                        high_risk.get("max", 1e9),
                    ],
                    orientation="horizontal",
                    brush=pg.mkBrush(220, 50, 50, 30),
                    movable=False,
                )
                plot.addItem(region)
                new_regions.append(region)

            self._regions[code] = new_regions

    def update(self, biomarker_values: dict[str, float]) -> None:
        """Добавить новые значения биомаркеров в буферы и обновить кривые.

        Вызывается из MainWindow._on_state_updated при каждом сигнале state_updated.
        Безопасно при отсутствии кода в biomarker_values (T-06-09 — mitigate).

        Args:
            biomarker_values: dict с ключами = camelCase коды биомаркеров (из SimulationState).
                              Пример: {"ldlC": 2.4, "hdlC": 1.5, ...}
        """
        for code, buf in self._buffers.items():
            # T-06-09: проверить наличие кода перед доступом (безопасность от отсутствующих полей)
            if code in biomarker_values:
                buf.append(biomarker_values[code])
                # Display last 300 points max — deque keeps 5000 for data accuracy.
                # Rendering 5000×24 points per frame freezes pyqtgraph on software renderer.
                display = list(buf)[-300:]
                self._curves[code].setData(display)
