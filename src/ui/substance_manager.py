# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""SubstanceManager — список веществ, диалог добавления, удаление.

Режим отображения (управляется будущей страницей конфигурации):
  - split (default): QSplitter — список слева, «Научный контекст» справа
  - tabs (future):   QTabWidget — «Список» и «Научный контекст» как вкладки

KB-04: Выбор вещества → KB-запрос через KBWorker в QThread (UI не блокируется).
Сигналы: substance_added(IntakeSchedule), substance_removed(str).
update_concentrations обновляет C(t) в списке.

Угрозы (07-04 threat model):
  T-07-04: KB-запрос в QThread — UI никогда не блокируется
  T-07-05: cancel() перед request_evidence — race condition защита
  T-07-06: close_kb_thread() — корректное завершение QThread при выходе
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QMetaObject, QThread, Signal
from PySide6.QtGui import QFontDatabase, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QComboBox,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.domain.substance import IntakeSchedule


class SubstanceManager(QWidget):
    """Виджет управления веществами: список, диалог добавления, удаление.

    Сигналы (UI-SPEC.md §Signal/Slot Contracts):
        substance_added  — эмит IntakeSchedule при подтверждении диалога
        substance_removed — эмит substance_id при нажатии «Удалить»

    KB-04: split-режим (default) — QSplitter: список слева, KB-контекст справа.
    Tabs-режим (future config): self.tabs получает вторую вкладку «Научный контекст».
    KBWorker в персистентном QThread — KB-запрос не блокирует UI.
    """

    substance_added = Signal(object)    # IntakeSchedule
    substance_removed = Signal(str)     # substance_id

    # Индекс в модели для пустого состояния
    _EMPTY_ROW_INDEX = 0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Загрузить substances.json (WR-02: graceful degradation при ошибке чтения)
        data_path = Path(__file__).parent.parent / "data" / "substances.json"
        try:
            with data_path.open(encoding="utf-8") as fh:
                raw = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            import warnings
            warnings.warn(f"substances.json not found or invalid: {exc}")
            raw = []
        self._substances: dict[str, dict] = {s["id"]: s for s in raw}

        # ── Layout внешний ──────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # ── QSplitter: список слева, научный контекст справа ──────────────────
        # Режим «tabs» (будущая конфигурация): self.tabs содержит обе вкладки.
        # Режим «split» (текущий default): self.tabs слева, self.kb_text справа.
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ── Левая сторона: QTabWidget с вкладкой «Список» ─────────────────────
        self.tabs = QTabWidget(self._splitter)

        list_tab = QWidget()
        list_layout = QVBoxLayout(list_tab)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(8)

        # Список веществ
        self.model = QStandardItemModel(self)
        self.list_view = QListView(list_tab)
        self.list_view.setModel(self.model)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        list_layout.addWidget(self.list_view)

        # Кнопки
        self.add_btn = QPushButton("Добавить вещество", list_tab)
        self.remove_btn = QPushButton("Удалить", list_tab)
        list_layout.addWidget(self.add_btn)
        list_layout.addWidget(self.remove_btn)

        self.tabs.addTab(list_tab, "Список")
        self._splitter.addWidget(self.tabs)

        # ── Правая сторона: панель «Научный контекст» ─────────────────────────
        kb_panel = QWidget(self._splitter)
        kb_panel_layout = QVBoxLayout(kb_panel)
        kb_panel_layout.setContentsMargins(4, 0, 0, 0)
        kb_panel_layout.setSpacing(4)

        kb_header = QLabel("Научный контекст", kb_panel)
        kb_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kb_header.setObjectName("kb_panel_header")
        kb_panel_layout.addWidget(kb_header)

        self.kb_text = QTextEdit(kb_panel)
        self.kb_text.setReadOnly(True)
        self.kb_text.setPlainText("Выберите вещество из списка.")

        # Моноширинный шрифт для читаемости данных (07-UI-SPEC §Typography monospace)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSize(9)
        self.kb_text.setFont(fixed_font)

        kb_panel_layout.addWidget(self.kb_text)
        self._splitter.addWidget(kb_panel)

        # Начальное соотношение: 40% список / 60% контекст
        self._splitter.setSizes([160, 240])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        layout.addWidget(self._splitter)

        # ── Подключить кнопки ──────────────────────────────────────────────────
        self.add_btn.clicked.connect(self._open_add_dialog)
        self.remove_btn.clicked.connect(self._remove_selected)

        # Хранить добавленные: substance_id → IntakeSchedule
        self._added: dict[str, IntakeSchedule] = {}
        # Хранить порядок substance_id по строкам модели
        self._row_ids: list[str] = []

        # Показать пустое состояние
        self._show_empty_state()

        # ── KBWorker + QThread setup (KB-04, T-07-04) ─────────────────────────
        self._kb_client = None
        self._kb_worker = None
        self._kb_thread = QThread(self)

        try:
            from src.engine.kb_client import KBClient, KBWorker  # noqa: PLC0415
            self._kb_client = KBClient()
            self._kb_worker = KBWorker(self._kb_client)
            self._kb_worker.moveToThread(self._kb_thread)
            self._kb_worker.result_ready.connect(self.kb_text.setPlainText)
            self._kb_thread.start()
        except Exception:
            # Graceful degradation: Neo4j/драйвер недоступен при старте
            # Приложение продолжает работу без KB-функциональности
            pass

        # ── Подключить сигнал выбора (Pitfall 1: selectionModel, НЕ list_view) ─
        # QListView не имеет currentRowChanged — только selectionModel() имеет
        self.list_view.selectionModel().currentRowChanged.connect(self._on_row_changed)

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _show_empty_state(self) -> None:
        """Добавить disabled-элемент пустого состояния."""
        if self.model.rowCount() == 0:
            item = QStandardItem("Вещества не добавлены. Нажмите «Добавить вещество».")
            item.setFlags(Qt.ItemFlag.NoItemFlags)  # disabled
            item.setData("#9e9e9e", Qt.ItemDataRole.ForegroundRole)
            self.model.appendRow(item)
            self._empty_shown = True
        else:
            self._empty_shown = False

    def _clear_empty_state(self) -> None:
        """Удалить элемент пустого состояния, если он есть."""
        if getattr(self, "_empty_shown", False) and self.model.rowCount() > 0:
            # Найти disabled-элемент и удалить
            for row in range(self.model.rowCount()):
                item = self.model.item(row)
                if item and not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    self.model.removeRow(row)
                    self._empty_shown = False
                    break

    def _on_row_changed(self, current, previous) -> None:
        """Триггер KB-запроса при смене выбранной строки (D-06, KB-04).

        Сигнатура: QItemSelectionModel.currentRowChanged(QModelIndex, QModelIndex).
        Защита от race condition: cancel() перед request_evidence() (T-07-05, Pitfall 2).
        """
        row = current.row() if current.isValid() else -1

        if row == -1:
            # Ничего не выбрано
            if self._kb_worker is not None:
                self._kb_worker.cancel()
            self.kb_text.setPlainText("Выберите вещество из списка.")
            return

        # Получить substance_id через model.item(row).data(UserRole)
        item = self.model.item(row)
        if item is None:
            self.kb_text.setPlainText("Выберите вещество из списка.")
            return

        sub_id = item.data(Qt.ItemDataRole.UserRole)
        if sub_id is None:
            # Клик по disabled empty-state строке
            if self._kb_worker is not None:
                self._kb_worker.cancel()
            self.kb_text.setPlainText("Выберите вещество из списка.")
            return

        # Запустить KB-запрос
        self.kb_text.setPlainText("Загрузка...")

        if self._kb_worker is None:
            self.kb_text.setPlainText("mortality KB недоступен")
            return

        # cancel + request_evidence + invoke run (T-07-05 race condition protection)
        self._kb_worker.cancel()
        self._kb_worker.request_evidence(sub_id)
        # Запустить run() через QueuedConnection (пересечение границы потоков)
        # WR-04: проверяем возвращаемое значение — False если слот не найден
        ok = QMetaObject.invokeMethod(
            self._kb_worker,
            "run",
            Qt.ConnectionType.QueuedConnection,
        )
        if not ok:
            self.kb_text.setPlainText("Ошибка: KB-запрос не удалось поставить в очередь")

    def _open_add_dialog(self) -> None:
        """Открыть диалог добавления вещества."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить вещество")
        form = QFormLayout(dialog)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)

        # Комбобокс веществ
        combo = QComboBox(dialog)
        for sub_id, sub in self._substances.items():
            combo.addItem(sub["name_ru"], userData=sub_id)
        form.addRow("Вещество:", combo)

        # Спинбокс дозы
        dose_spin = QDoubleSpinBox(dialog)
        dose_spin.setDecimals(1)

        def _update_dose_range(index: int) -> None:
            sub_id = combo.itemData(index)
            sub = self._substances[sub_id]
            dose_spin.setRange(sub["minDose"], sub["maxDose"])
            dose_spin.setValue(sub["defaultDose"])

        combo.currentIndexChanged.connect(_update_dose_range)
        # Инициализировать для первого элемента
        _update_dose_range(0)
        form.addRow("Доза (мг):", dose_spin)

        # Спинбокс часа приёма
        hour_spin = QSpinBox(dialog)
        hour_spin.setRange(0, 23)
        hour_spin.setValue(8)
        form.addRow("Час приёма (0–23):", hour_spin)

        # Кнопки OK/Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        sub_id = combo.currentData()
        sub = self._substances[sub_id]
        dose = dose_spin.value()
        hour = hour_spin.value()

        # WR-03: предотвратить двойное добавление одного вещества
        if sub_id in self._added:
            QMessageBox.information(
                self,
                "Уже добавлено",
                f"«{sub['name_ru']}» уже в списке. Удалите его перед повторным добавлением.",
            )
            return

        try:
            schedule = IntakeSchedule(
                substance_id=sub_id,
                dose_mg=dose,
                hour_of_day=hour,
                min_dose=sub["minDose"],
                max_dose=sub["maxDose"],
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Ошибка дозировки",
                f"Доза вне допустимого диапазона [{sub['minDose']}–{sub['maxDose']}] мг:\n{exc}",
            )
            return

        # Убрать пустое состояние перед добавлением
        self._clear_empty_state()

        # Добавить в модель
        name_ru = sub["name_ru"]
        item = QStandardItem(f"{name_ru}: 0.000 (нет в плазме)")
        item.setData(sub_id, Qt.ItemDataRole.UserRole)
        self.model.appendRow(item)

        self._added[sub_id] = schedule
        self._row_ids.append(sub_id)

        self.substance_added.emit(schedule)

    def _remove_selected(self) -> None:
        """Удалить выбранное вещество из списка."""
        indexes = self.list_view.selectedIndexes()
        if not indexes:
            return

        row = indexes[0].row()
        item = self.model.item(row)
        if item is None:
            return

        sub_id = item.data(Qt.ItemDataRole.UserRole)
        if sub_id is None:
            # Клик по disabled-элементу пустого состояния
            return

        self.model.removeRow(row)
        self._added.pop(sub_id, None)
        if sub_id in self._row_ids:
            self._row_ids.remove(sub_id)

        # Если список пуст — показать пустое состояние
        if self.model.rowCount() == 0:
            self._show_empty_state()

        self.substance_removed.emit(sub_id)

    # ── Публичный API ─────────────────────────────────────────────────────────

    def close_kb_thread(self) -> None:
        """Корректно завершить KB QThread при закрытии окна.

        Вызывается из MainWindow.closeEvent() перед завершением simulation thread.
        Паттерн аналогичен Phase 6 D-63 (T-07-06, Pitfall 5).
        """
        if self._kb_worker is not None:
            self._kb_worker.cancel()
        if self._kb_thread.isRunning():
            self._kb_thread.quit()
            self._kb_thread.wait(5000)

    def update_concentrations(self, concentrations: dict) -> None:
        """Обновить отображение C(t) для всех добавленных веществ.

        Вызывается из MainWindow._on_state_updated с
        state.substance_concentrations (dict[str, float]).

        Формат (UI-SPEC.md §State Labels):
            «{name_ru}: {c:.3f}» если c > 0
            «{name_ru}: 0.000 (нет в плазме)» если c == 0 или отсутствует
        """
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item is None:
                continue
            sub_id = item.data(Qt.ItemDataRole.UserRole)
            if sub_id is None:
                continue  # disabled empty-state item

            sub = self._substances.get(sub_id)
            if sub is None:
                continue

            name_ru = sub["name_ru"]
            c = concentrations.get(sub_id, 0.0)
            if c > 0:
                item.setText(f"{name_ru}: {c:.3f}")
            else:
                item.setText(f"{name_ru}: 0.000 (нет в плазме)")
