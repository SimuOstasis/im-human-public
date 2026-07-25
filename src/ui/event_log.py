# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""EventLog — журнал событий симуляции с цветовым кодированием.

UI-07: QDockWidget → QWidget + QListView.
Формат строки: [{tick:>8}] {severity:8} {message}
CRITICAL — красный фон (#cf6679 20%), WARNING — жёлтый (#c89a2e 20%).
Новейшие события сверху, максимум 500 записей.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QListView, QVBoxLayout, QWidget

from src.domain.simulation_state import SimulationStatus


class EventLog(QWidget):
    """Журнал событий симуляции.

    Метод add_events(events) добавляет только новые события (по _seen_count),
    вставляет их сверху (insertRow 0), ограничивает список 500 элементами.
    """

    # Лимит отображаемых событий (UI-SPEC.md §Event Log Entry Contract)
    MAX_ENTRIES = 500

    # Цвета фона по severity (20% альфа)
    _BG_CRITICAL = QColor(207, 102, 121, 51)   # #cf6679 ~20%
    _BG_WARNING  = QColor(200, 154, 46, 51)    # #c89a2e ~20%
    _FG_ERROR    = QColor(207, 102, 121, 220)  # для add_error

    # Текст empty-state по статусу симуляции (D-01/D-09, 10.1-UI-SPEC.md
    # §Copywriting Contract — строки дословные, не перефразировать).
    _EMPTY_TEXT: dict[SimulationStatus, str] = {
        SimulationStatus.IDLE: "Нет событий. Запустите симуляцию.",
        SimulationStatus.STOPPED: "Нет событий. Запустите симуляцию.",
        SimulationStatus.RUNNING: "Симуляция выполняется. Событий пока нет.",
        SimulationStatus.PAUSED: "Симуляция выполняется. Событий пока нет.",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.model = QStandardItemModel(self)
        self.list_view = QListView(self)
        self.list_view.setModel(self.model)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.list_view)

        # Счётчик уже отображённых событий (добавляем только новые)
        self._seen_count: int = 0

        # WR-02 (10.1-REVIEW.md): сигнатура первого события текущего прогона
        # (tick, severity, message) — используется вместе с len() для
        # обнаружения смены run identity даже когда новый список events того
        # же размера, что и предыдущий (см. add_events).
        self._first_event_sig: tuple | None = None

        # Флаг: показан ли элемент пустого состояния
        self._empty_shown: bool = True

        # Текущий статус симуляции (D-01/D-09) — определяет текст empty-state
        self._current_status: SimulationStatus = SimulationStatus.IDLE

        # Показать стартовый empty-state
        self._add_empty_item()

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _add_empty_item(self) -> None:
        """Показать disabled-элемент пустого состояния."""
        item = QStandardItem("Нет событий. Запустите симуляцию.")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(QColor("#9e9e9e"), Qt.ItemDataRole.ForegroundRole)
        self.model.appendRow(item)

    def _clear_empty_state(self) -> None:
        """Удалить элемент пустого состояния при первом реальном событии."""
        if not self._empty_shown:
            return
        # Найти и удалить disabled-элемент (находится в конце при пустом логе)
        for row in range(self.model.rowCount() - 1, -1, -1):
            item = self.model.item(row)
            if item and not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                self.model.removeRow(row)
                self._empty_shown = False
                return

    def _make_item(self, tick: int, severity: str, message: str) -> QStandardItem:
        """Создать QStandardItem с форматом и цветом по severity."""
        text = f"[{tick:>8}] {severity:8} {message}"
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        if severity == "CRITICAL":
            item.setBackground(self._BG_CRITICAL)
        elif severity == "WARNING":
            item.setBackground(self._BG_WARNING)
        # INFO — без цвета фона, цвет текста наследуется из темы (#e0e0e0)

        return item

    def _trim_to_limit(self) -> None:
        """Удалить самые старые записи (снизу) при превышении лимита 500."""
        while self.model.rowCount() > self.MAX_ENTRIES:
            self.model.removeRow(self.model.rowCount() - 1)

    # ── Публичный API ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Сбросить состояние журнала для новой симуляции.

        Вызывать из MainWindow._on_start_requested перед запуском новой
        симуляции, чтобы _seen_count не ссылался на события предыдущего
        прогона (CR-04).
        """
        self.model.clear()
        self._seen_count = 0
        self._first_event_sig = None
        self._empty_shown = True
        self._add_empty_item()

    def set_status(self, status: SimulationStatus) -> None:
        """Обновить текст empty-state по текущему статусу симуляции (D-01/D-09).

        Не трогает реальные события и не меняет _empty_shown/_seen_count —
        только подменяет текст уже показанного disabled-элемента, если он
        сейчас отображается. Вызывается из MainWindow._on_state_updated в
        безусловной (нетроттлируемой) секции, независимо от add_events()
        (Pitfall 3 — add_events() early-return'ит при пустом логе).
        """
        self._current_status = status
        if not self._empty_shown:
            return
        for row in range(self.model.rowCount() - 1, -1, -1):
            item = self.model.item(row)
            if item and not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                item.setText(self._EMPTY_TEXT[status])
                return

    def add_events(self, events: list) -> None:
        """Добавить новые события из state.events.

        Обрабатывает только события начиная с self._seen_count.
        Вставляет новейшие сверху (insertRow 0).
        Ограничивает отображение 500 элементами.

        Вызывается из MainWindow._on_state_updated с state.events.

        WR-02 (10.1-REVIEW.md, carried over from prior review's WR-04):
        _seen_count по себе — чисто length-based эвристика, детектирующая
        только СОКРАЩЕНИЕ списка events как сигнал «началась новая история,
        начни заново». Same-length-но-другого-содержимого список (например,
        два разных загруженных снепшота с одинаковым числом событий) она бы
        молча трактовала как «новых событий нет». Поэтому дополнительно
        сравниваем сигнатуру первого события (tick, severity, message) с
        сохранённой от предыдущего вызова: расхождение — тоже сигнал смены
        run identity, даже при равной длине. ОБЯЗАТЕЛЬНО всё равно вызывай
        reset() перед первым add_events() нового/загруженного прогона (см.
        MainWindow._on_load_requested, _on_stop_requested) — эта проверка
        дополняет, а не заменяет тот контракт.
        """
        # If events list is shorter than seen count, the engine reset it (per-tick reset).
        if len(events) < self._seen_count:
            self._seen_count = 0

        if events:
            first_sig = (events[0].tick, events[0].severity, events[0].message)
            if self._first_event_sig is not None and first_sig != self._first_event_sig:
                # Same or greater length, but a different run's first event —
                # run identity changed without a shorter list to detect it.
                self._seen_count = 0
            self._first_event_sig = first_sig

        new_events = events[self._seen_count:]
        if not new_events:
            return

        # Убрать empty-state при первом реальном событии
        self._clear_empty_state()

        # Вставлять новые события сверху (новейшие сверху)
        for event in new_events:
            item = self._make_item(event.tick, event.severity, event.message)
            self.model.insertRow(0, item)

        self._seen_count = len(events)

        # Ограничить список 500 элементами (UI-SPEC §Event Log Entry Contract)
        self._trim_to_limit()

    def add_error(self, message: str) -> None:
        """Добавить красный элемент ошибки движка сверху.

        Вызывается из MainWindow._on_engine_error при сигнале error_occurred.
        (UI-SPEC.md §Error States)
        """
        self._clear_empty_state()

        text = f"Ошибка движка: {message}"
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setBackground(self._BG_CRITICAL)
        item.setForeground(self._FG_ERROR)

        self.model.insertRow(0, item)
        self._trim_to_limit()
