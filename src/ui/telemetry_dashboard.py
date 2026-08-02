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

Decisions: D-03 (deque maxlen=5000), D-11 (4×6 GridLayout), D-13 (LinearRegionItem);
  Phase 17: D-01 (viewport-culling запас ±2 строки сетки), D-02 (критерий видимости по
  scrollbar+viewport геометрии, дешевле построчного per-widget region-запроса), D-03
  (Phase 17 — безусловное накопление в deque независимо от видимости, не путать с D-03
  Phase 6 выше), D-04 (однократный полный догон setData() при возврате плота в видимую
  область)
Requirements: UI-05 (24 графика), UI-10 (даунсэмплинг ≤5000 точек), PERF-01 (viewport-culling)
"""
from __future__ import annotations

import collections
import itertools
import json
import logging
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.domain.human_profile import Sex

_logger = logging.getLogger(__name__)

# Путь к файлу биомаркеров (src/ui/telemetry_dashboard.py → 2 уровня вверх → src/data/)
_BIOMARKERS_FILE = Path(__file__).parent.parent / "data" / "biomarkers.json"

# Целевая ширина (px) для batch-export графиков (export_all(), G-12-3).
# Жёсткий пол — >= 1024px по длинной стороне (требование пользователя из
# 12-UAT.md); 1200 взято с запасом. Длинная сторона мини-плотов — ширина
# (on-screen 200×120, landscape), поэтому задаём именно width; height
# pyqtgraph авто-пересчитывает через widthChanged, сохраняя aspect ratio
# (подлинный QGraphicsScene.render() в свежий холст, а не апскейл).
EXPORT_TARGET_WIDTH_PX = 1200


def _patch_pyqtgraph_svg_exporter_bug() -> None:
    """Пропатчить известный баг `pyqtgraph.exporters.SVGExporter` (0.14.0) в
    рамках запиненного диапазона `>=0.13.0,<0.15.0` (HF-01, Rule 1 auto-fix).

    Баг: `correctCoordinates()` безусловно делает `x, y = c.split(',')` для
    каждого пробел-разделённого токена в атрибуте `d` у `<path>` — но SVG
    команда закрытия подпути `Z`/`z` НЕ несёт координат и токен `'Z'` не
    содержит запятой, из-за чего `split(',')` возвращает список из одного
    элемента и падает `ValueError: not enough values to unpack`. Эта команда
    присутствует в SVG-выводе для ЛЮБОГО закрашенного прямоугольника (в т.ч.
    фон `PlotWidget`/`ViewBox`, добавляемый pyqtgraph по умолчанию) — баг
    воспроизводится на каждом плоте, не специфичен для этого приложения, и
    без фикса полностью ломает SVG-экспорт (0 из 24 успешных при любом
    вызове `export_all("SVG", ...)`), что прямо противоречит must-have HF-01
    (SVG — один из двух форматов, локальных в UI-SPEC).

    Фикс: копия оригинальной `correctCoordinates()` с единственным изменением
    — токены без запятой (только `Z`/`z`, единственные беспараметрические SVG
    path-команды) переносятся в выходную строку как есть, без попытки
    трансформировать координаты. Семантически безопасно: `Z` не имеет
    координат для трансформации по определению SVG-спецификации.

    Идемпотентно (флаг `_svg_exporter_patched` на самом модуле) — применяется
    один раз за процесс, лениво при первом SVG-экспорте.
    """
    import importlib

    svg_mod = importlib.import_module("pyqtgraph.exporters.SVGExporter")
    if getattr(svg_mod, "_im_human_svg_bug_patched", False):
        return

    import re
    import xml.dom.minidom as xmldom

    import numpy as np
    from pyqtgraph import functions as fn
    from pyqtgraph.Qt import QtGui

    def _patched_correct_coordinates(node, defs, item, options):
        # Верно оригиналу pyqtgraph.exporters.SVGExporter.correctCoordinates
        # (0.14.0) — единственное отличие помечено "# HF-01 FIX" ниже.
        for d in defs:
            if d.tagName == "linearGradient":
                d.removeAttribute("gradientUnits")
                for coord in ("x1", "x2", "y1", "y2"):
                    denominator = (
                        item.boundingRect().width()
                        if coord.startswith("x")
                        else item.boundingRect().height()
                    )
                    # WR-05 (12-REVIEW.md): boundingRect() can be zero-width/
                    # -height (before layout has settled, during rapid
                    # resize, or with a zero-size dock) — guard against
                    # ZeroDivisionError instead of letting it propagate and
                    # abort the whole SVG export.
                    percentage = (
                        round(float(d.getAttribute(coord)) * 100 / denominator)
                        if denominator
                        else 0
                    )
                    d.setAttribute(coord, f"{percentage}%")
                for child in filter(
                    lambda e: isinstance(e, xmldom.Element) and e.tagName == "stop",
                    d.childNodes,
                ):
                    offset = child.getAttribute("offset")
                    try:
                        child.setAttribute("offset", f"{round(float(offset) * 100)}%")
                    except ValueError:
                        continue

        groups = node.getElementsByTagName("g")
        groups2 = []
        for grp in groups:
            subGroups = [grp.cloneNode(deep=False)]
            textGroup = None
            for ch in grp.childNodes[:]:
                if isinstance(ch, xmldom.Element):
                    if textGroup is None:
                        textGroup = ch.tagName == "text"
                    if ch.tagName == "text":
                        if textGroup is False:
                            subGroups.append(grp.cloneNode(deep=False))
                            textGroup = True
                    else:
                        if textGroup is True:
                            subGroups.append(grp.cloneNode(deep=False))
                            textGroup = False
                subGroups[-1].appendChild(ch)
            groups2.extend(subGroups)
            for sg in subGroups:
                node.insertBefore(sg, grp)
            node.removeChild(grp)
        groups = groups2

        for grp in groups:
            matrix = grp.getAttribute("transform")
            match = re.match(r"matrix\((.*)\)", matrix)
            if match is None:
                vals = [1, 0, 0, 1, 0, 0]
            else:
                vals = [float(a) for a in match.groups()[0].split(",")]
            tr = np.array([[vals[0], vals[2], vals[4]], [vals[1], vals[3], vals[5]]])

            removeTransform = False
            for ch in grp.childNodes:
                if not isinstance(ch, xmldom.Element):
                    continue
                if ch.tagName == "polyline":
                    removeTransform = True
                    coords = np.array(
                        [
                            [float(a) for a in c.split(",")]
                            for c in ch.getAttribute("points").strip().split(" ")
                        ]
                    )
                    coords = fn.transformCoordinates(tr, coords, transpose=True)
                    ch.setAttribute(
                        "points",
                        " ".join([",".join([str(a) for a in c]) for c in coords]),
                    )
                elif ch.tagName == "path":
                    removeTransform = True
                    newCoords = ""
                    oldCoords = ch.getAttribute("d").strip()
                    if oldCoords == "":
                        continue
                    for c in oldCoords.split(" "):
                        if not c:
                            continue
                        if "," not in c:
                            # HF-01 FIX: беспараметрическая команда (Z/z —
                            # закрытие подпути) не содержит координат для
                            # трансформации — переносим как есть, не пытаемся
                            # split(",") (это и есть исходный краш upstream).
                            newCoords += c + " "
                            continue
                        x, y = c.split(",")
                        if x[0].isalpha():
                            t = x[0]
                            x = x[1:]
                        else:
                            t = ""
                        nc = fn.transformCoordinates(
                            tr, np.array([[float(x), float(y)]]), transpose=True
                        )
                        newCoords += t + str(nc[0, 0]) + "," + str(nc[0, 1]) + " "
                    if newCoords and newCoords[0] != "M":
                        newCoords = f"M{newCoords[1:]}"
                    ch.setAttribute("d", newCoords)
                elif ch.tagName == "text":
                    removeTransform = False
                    families = ch.getAttribute("font-family").split(",")
                    if len(families) == 1:
                        font = QtGui.QFont(families[0].strip('" '))
                        if font.styleHint() == font.StyleHint.SansSerif:
                            families.append("sans-serif")
                        elif font.styleHint() == font.StyleHint.Serif:
                            families.append("serif")
                        elif font.styleHint() == font.StyleHint.Courier:
                            families.append("monospace")
                        ch.setAttribute(
                            "font-family",
                            ", ".join(
                                [f if " " not in f else '"%s"' % f for f in families]
                            ),
                        )

                if (
                    removeTransform
                    and ch.getAttribute("vector-effect") != "non-scaling-stroke"
                    and grp.getAttribute("stroke-width") != ""
                ):
                    w = float(grp.getAttribute("stroke-width"))
                    s = fn.transformCoordinates(tr, np.array([[w, 0], [0, 0]]), transpose=True)
                    w = ((s[0] - s[1]) ** 2).sum() ** 0.5
                    ch.setAttribute("stroke-width", str(w))

                if options.get("scaling stroke") is True and ch.getAttribute(
                    "vector-effect"
                ) == "non-scaling-stroke":
                    ch.removeAttribute("vector-effect")

            if removeTransform:
                grp.removeAttribute("transform")

    svg_mod.correctCoordinates = _patched_correct_coordinates
    svg_mod._im_human_svg_bug_patched = True


def _compute_fixed_yrange(
    ranges: dict, padding_frac: float = 0.3
) -> tuple[float, float] | None:
    """Вычислить фиксированный Y-диапазон плота из конечных границ зон (D-03).

    Собирает все КОНЕЧНЫЕ (присутствующие) значения min/max из зон
    optimal/optimal_m/optimal_f/borderline/high_risk и добавляет padding.

    КАТЕГОРИЧЕСКИ не использует -1e9/1e9 fallback из apply_ranges() —
    те значения предназначены только для LinearRegionItem с открытыми
    границами, а не для границ оси Y (10.1-RESEARCH.md Pitfall 2).

    Args:
        ranges: словарь зон биомаркера из reference_ranges (self._ranges[code]).
        padding_frac: доля от span диапазона, добавляемая с каждой стороны.

    Returns:
        (lo, hi) — фиксированный диапазон с padding, либо None, если у
        биомаркера нет ни одной конечной границы (fallback на auto-range).
    """
    finite_bounds: list[float] = []
    for zone_key in ("optimal", "optimal_m", "optimal_f", "borderline", "high_risk"):
        zone = ranges.get(zone_key)
        if not zone:
            continue
        if "min" in zone:
            finite_bounds.append(zone["min"])
        if "max" in zone:
            finite_bounds.append(zone["max"])

    if not finite_bounds:
        return None

    lo, hi = min(finite_bounds), max(finite_bounds)
    span = hi - lo if hi > lo else max(abs(hi), 1.0)
    return (lo - span * padding_frac, hi + span * padding_frac)


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
        # WR-02 (10.1-REVIEW.md): OSError (covers FileNotFoundError,
        # PermissionError и т.д.) вместо только FileNotFoundError, плюс явная
        # проверка обязательных top-level ключей — синтаксически валидный, но
        # неполный JSON (например, схема без reference_ranges/biomarkers)
        # раньше падал с некэшированным KeyError двумя строками ниже, сводя
        # на нет graceful-degradation, ради которой этот блок и писался.
        try:
            data = json.loads(_BIOMARKERS_FILE.read_text(encoding="utf-8"))
            if "reference_ranges" not in data or "biomarkers" not in data:
                raise ValueError("biomarkers.json missing required top-level keys")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
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
        self._plot_row: dict[str, int] = {}  # код биомаркера → номер строки сетки (PERF-01)

        # ── Компоновка: QVBoxLayout → QScrollArea → inner QWidget + QGridLayout ──
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer_layout.addWidget(self._scroll)

        inner_widget = QWidget()
        self._scroll.setWidget(inner_widget)

        self._grid = QGridLayout(inner_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(4)

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
            # БЕЗ clipToView/autoDownsample kwargs здесь (Pitfall 1) — PlotItem.addItem()
            # безусловно затирает их значениями из self.ctrl, если передать как kwargs.
            curve = plot.plot(pen=pg.mkPen('#3daee9', width=1.5))

            # D-03: фиксированный Y-диапазон из reference_ranges.json (не auto-range на
            # каждый setData) — вычисляется из конечных границ зон, НЕ из -1e9/1e9
            # fallback apply_ranges() (Pitfall 2).
            fixed_range = _compute_fixed_yrange(self._ranges.get(code, {}))
            if fixed_range is not None:
                plot.setYRange(*fixed_range)
                plot.enableAutoRange(y=False)

            # D-03/Pitfall 1: clipToView/autoDownsample — ТОЛЬКО явные вызовы методов
            # ПОСЛЕ plot.plot() (addItem уже отработал), не kwargs.
            curve.setClipToView(True)
            curve.setDownsampling(auto=True)

            # Буфер истории — максимум 5000 точек (D-03, UI-10)
            buf: collections.deque = collections.deque(maxlen=5000)

            # Сохранить
            self._plots[code] = plot
            self._curves[code] = curve
            self._buffers[code] = buf
            self._regions[code] = []
            self._plot_row[code] = row

            self._grid.addWidget(plot, row, col)

        # Растянуть все 4 колонки и 6 строк равномерно (UI-SPEC.md §Grid layout)
        # WR-07 (17-REVIEW.md): границы циклов вычисляются из данных
        # (self._biomarkers), а не хардкодятся как 4×6 — иначе при изменении
        # состава biomarkers.json сетка растяжки молча разъедется с реальной
        # (уже частично заполненной/неполной) геткой виджетов.
        n_cols = 4
        n_rows = -(-len(self._biomarkers) // n_cols) if self._biomarkers else 0
        for c in range(n_cols):
            self._grid.setColumnStretch(c, 1)
        for r in range(n_rows):
            self._grid.setRowStretch(r, 1)

        # CR-01 (17-REVIEW.md): D-04 «однократный полный догон setData() при
        # возврате плота в видимую область» ранее происходил только как побочный
        # эффект следующего update() — плот, прокрученный в видимую область во
        # время паузы/останова симуляции (когда update() больше не вызывается),
        # оставался пустым навсегда, несмотря на полную историю в self._buffers.
        # Подписка на valueChanged скроллбара пересчитывает видимость и
        # перерисовывает попавшие в неё плоты независимо от прихода нового тика.
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    def _on_scrolled(self, _value: int) -> None:
        """Догоняющая перерисовка плотов, попавших в видимую область при скролле
        без нового тика симуляции (CR-01/D-04, 17-REVIEW.md).

        Не трогает self._buffers (данные уже накоплены безусловно — D-03) —
        только пересчитывает срез для newly-visible плотов и вызывает setData(),
        зеркаля срез, который делает update() (последние ≤300 точек).
        """
        first_row, last_row = self._visible_row_range()
        for code, row in self._plot_row.items():
            if first_row <= row <= last_row:
                buf = self._buffers[code]
                display = list(itertools.islice(buf, max(0, len(buf) - 300), len(buf)))
                self._curves[code].setData(display)

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────────

    def plot_count(self) -> int:
        """Число созданных плотов (IN-02, 12-REVIEW.md).

        Публичный accessor вместо прямого чтения self._plots извне
        (main_window.py's 0-plot guard в _on_export_all_plots).
        """
        return len(self._plots)

    def biomarker_names(self) -> dict[str, str]:
        """Отображение code → русское название биомаркера (IN-02, 12-REVIEW.md).

        Публичный accessor вместо прямого чтения self._biomarkers извне
        (main_window.py's code_to_name в _on_export_all_plots).
        """
        return {bm["code"]: bm["name_ru"] for bm in self._biomarkers}

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

    def _visible_row_range(self) -> tuple[int, int]:
        """Буферизованный диапазон видимых строк сетки (D-01: запас ±2 строки).

        Критерий видимости — по позиции скроллбара и высоте viewport `QScrollArea`
        (D-02), а не через попиксельный region-запрос у каждого виджета: последнее
        дорого пересчитывать для 24 плотов на каждый вызов `update()`. Высоты строк
        НИГДЕ не кэшируются —
        `rowCount()` и геометрия каждой строки перечитываются заново на каждом вызове,
        потому что `setRowStretch` растягивает и слегка разравнивает строки неодинаково,
        когда окно выше содержимого (17-RESEARCH.md Pitfall 2); закэшированная высота
        стала бы неверной сразу после такого resize.

        Returns:
            (first_row, last_row) — индексы первой и последней буферизованной строки,
            либо полный диапазон `(0, rowCount() - 1)`, если ни одна строка ещё не
            имеет валидной геометрии (виджет не был показан).
        """
        scroll_y = self._scroll.verticalScrollBar().value()
        viewport_h = self._scroll.viewport().height()
        visible_top, visible_bottom = scroll_y, scroll_y + viewport_h

        row_count = self._grid.rowCount()
        last_row_index = row_count - 1

        first_row: int | None = None
        last_row: int | None = None
        for row in range(row_count):
            item = self._grid.itemAtPosition(row, 0)
            if item is None:
                continue
            w = item.widget()
            row_top, row_bottom = w.y(), w.y() + w.height()
            if row_bottom > visible_top and row_top < visible_bottom:
                if first_row is None:
                    first_row = row
                last_row = row

        if first_row is None:
            # Ничего не видно (виджет ещё не показан, нулевая геометрия) —
            # деградировать в прежнее поведение (все строки), а не отсекать всё.
            return (0, last_row_index)
        return (max(0, first_row - 2), min(last_row_index, last_row + 2))

    def update(self, biomarker_values: dict[str, float]) -> None:
        """Добавить новые значения биомаркеров в буферы и обновить кривые.

        Вызывается из MainWindow._on_state_updated при каждом сигнале state_updated.
        Безопасно при отсутствии кода в biomarker_values (T-06-09 — mitigate).

        Args:
            biomarker_values: dict с ключами = camelCase коды биомаркеров (из SimulationState).
                              Пример: {"ldlC": 2.4, "hdlC": 1.5, ...}
        """
        first_row, last_row = self._visible_row_range()

        for code, buf in self._buffers.items():
            # T-06-09: проверить наличие кода перед доступом (безопасность от отсутствующих полей)
            if code in biomarker_values:
                buf.append(biomarker_values[code])  # D-03: безусловно, вне гейта видимости

                # PERF-01 (D-01/D-03/D-04): плоты вне буферизованного диапазона строк
                # пропускают и срез, и перерисовку — данные продолжают копиться в deque
                # выше, ничего не теряется, просто не отрисовывается, пока плот не виден.
                if not (first_row <= self._plot_row[code] <= last_row):
                    continue

                # Display last 300 points max — deque keeps 5000 for data accuracy.
                # Rendering 5000×24 points per frame freezes pyqtgraph on software renderer.
                # D-02: срез через itertools.islice — не материализует весь deque
                # (list(buf)) целиком на каждый кадр, только последние <=300 элементов.
                display = list(itertools.islice(buf, max(0, len(buf) - 300), len(buf)))
                self._curves[code].setData(display)

    def export_all(self, fmt: str, folder: Path) -> tuple[int, int, list[str]]:
        """Экспортировать все плоты дашборда в файлы PNG/SVG (HF-01, D-02..D-05).

        Единый timestamp (минутная гранулярность, D-05) применяется ко всем
        файлам одного прогона — не per-file. Имя файла: {code}_{ts}.{ext}, где
        {code} — ключ self._plots (уже равен полю code из biomarkers.json, не
        хардкодится повторно). Ошибка экспорта отдельного плота ловится и
        собирается в errors — цикл продолжается по остальным плотам (партиальный
        успех не прерывает прогон).

        Args:
            fmt: "PNG" или "SVG" — определяет exporter и расширение файла.
            folder: папка назначения (уже существующая, из QFileDialog.getExistingDirectory).

        Returns:
            (ok, total, errors) — ok = число успешно экспортированных файлов,
            total = len(self._plots), errors = список кодов биомаркеров с ошибкой.
        """
        if fmt not in ("PNG", "SVG"):
            # WR-01 (17-REVIEW.md): без валидации любой другой fmt молча
            # получал SVGExporter, но файл писался с расширением fmt.lower()
            # (например .pdf с SVG-содержимым внутри) — публичный метод без
            # защиты инварианта, которым сейчас пользуется только UI-диалог.
            raise ValueError(f"Unsupported export format: {fmt!r} (expected 'PNG' or 'SVG')")

        if fmt == "SVG":
            _patch_pyqtgraph_svg_exporter_bug()

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        ok = 0
        errors: list[str] = []
        for code, plot in self._plots.items():
            try:
                exporter = (
                    pyqtgraph.exporters.ImageExporter(plot.plotItem)
                    if fmt == "PNG"
                    else pyqtgraph.exporters.SVGExporter(plot.plotItem)
                )
                exporter.parameters()["width"] = EXPORT_TARGET_WIDTH_PX
                exporter.export(str(folder / f"{code}_{ts}.{fmt.lower()}"))
                ok += 1
            except Exception as exc:
                # WR-04 (12-REVIEW.md): log the exception before discarding it —
                # otherwise a systematic failure (read-only destination, disk
                # full, a regression in the SVG monkey-patch above) leaves the
                # user with zero diagnostic information and nothing in logs.
                _logger.warning("Export failed for %s: %s", code, exc, exc_info=True)
                errors.append(code)
        return ok, len(self._plots), errors

    def reset(self) -> None:
        """Очистить всю накопленную историю биомаркеров (Файл→«Новая»).

        Не трогает self._regions (цветовые зоны) — они привязаны к профилю
        (apply_ranges), не к прогону симуляции, и не устаревают при сбросе.
        """
        for code, buf in self._buffers.items():
            buf.clear()
            self._curves[code].setData([])
