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
import queue
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QMetaObject, QThread, Signal, Slot
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
from src.engine.kb_client import _ers_stars

# IN-01 (10-REVIEW.md): число знаков после запятой в спинбоксе дозы —
# именованная константа вместо магического числа. Некоторым веществам
# (напр. дозируемым в мкг) может потребоваться больше точности в будущем.
_DOSE_DECIMALS = 1


class ErsBadgeWorker(QObject):
    """Worker Object для асинхронного разрешения ERS-уровня строк списка (D-07).

    Паттерн смоделирован буквально по kb_client.KBWorker (moveToThread), но
    отдельный от него — badge-запросы не должны конкурировать с «Научный
    контекст» панелью за один и тот же result_ready-сигнал/поток.

    Signals (Worker → UI):
        ers_ready(str, int) — (substance_id, level); level=0 означает
        «фактов нет / KB недоступна» — сигнал «без звёзд», не ошибка.

    Slots (UI → Worker):
        run: слить очередь запросов, для каждого id вызвать
        client.get_substance_evidence(id) + compute_ers_level.

    Изоляция строк (13-UI-SPEC §UI Considerations, partial-row backstop):
    ошибка/исключение на одном substance_id никогда не блокирует и не
    затирает уже разрешённые звёзды других строк — try/except внутри цикла,
    не вокруг него.
    """

    ers_ready = Signal(str, int)  # (substance_id, level)

    def __init__(self, kb_client) -> None:
        super().__init__()
        self._client = kb_client
        self._queue: queue.Queue[str] = queue.Queue()

    def request_level(self, substance_id: str) -> None:
        """Поставить substance_id в очередь на разрешение ERS-уровня.

        Вызывается из UI thread — queue.Queue thread-safe для put/get.
        """
        self._queue.put(substance_id)

    @Slot()
    def run(self) -> None:
        """Слить очередь запросов, разрешить уровень для каждого substance_id.

        Вызывается через QThread / queued connection. Каждый id обрабатывается
        независимо (Pitfall isolation) — исключение на одном id не прерывает
        обработку остальных и не блокирует уже показанные звёзды других строк.
        """
        while True:
            try:
                sub_id = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                facts = self._client.get_substance_evidence(sub_id)
                level = self._client.compute_ers_level(facts) if facts else 0
            except Exception:
                level = 0
            self.ers_ready.emit(sub_id, level)


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
        # WR-02: устойчивость к структурно некорректному (но синтаксически
        # валидному) substances.json — пропустить записи без "id" вместо краха.
        self._substances: dict[str, dict] = {}
        for s in raw:
            sid = s.get("id") if isinstance(s, dict) else None
            if sid:
                self._substances[sid] = s

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

        # ── D-07: кэши ERS-звёзд и последней концентрации per substance_id ────
        # _compose_row_text собирает текст строки из обоих кэшей — единая точка
        # записи, чтобы update_concentrations() никогда не стирал префикс звёзд
        # (Pitfall 3, 13-RESEARCH.md).
        self._ers_stars_by_id: dict[str, str] = {}
        self._last_concentrations: dict[str, float] = {}

        # ── KBWorker + QThread setup (KB-04, T-07-04) ─────────────────────────
        self._kb_client = None
        self._kb_worker = None
        self._kb_thread = QThread(self)

        # ── ErsBadgeWorker + отдельный QThread (D-07) ──────────────────────────
        # Отдельный от _kb_thread/_kb_worker поток: badge-разрешение не должно
        # конкурировать с «Научный контекст» панелью за один и тот же worker/сигнал.
        self._ers_worker = None
        self._ers_thread = QThread(self)

        try:
            from src.engine.kb_client import KBClient, KBWorker  # noqa: PLC0415
            self._kb_client = KBClient()
            self._kb_worker = KBWorker(self._kb_client)
            self._kb_worker.moveToThread(self._kb_thread)
            self._kb_worker.result_ready.connect(self.kb_text.setPlainText)
            self._kb_thread.start()

            # KBClient сконструирован успешно — можно завести badge worker
            # на том же клиенте (thread-safe driver, каждый запрос открывает
            # свою сессию — kb_client.py docstring).
            self._ers_worker = ErsBadgeWorker(self._kb_client)
            self._ers_worker.moveToThread(self._ers_thread)
            self._ers_worker.ers_ready.connect(self._on_ers_ready)
            self._ers_thread.start()
        except Exception as exc:
            # Graceful degradation: Neo4j/драйвер недоступен при старте
            # Приложение продолжает работу без KB-функциональности,
            # но ошибка логируется (WR-03) — иначе регрессия в kb_client.py
            # неотличима от штатного "Neo4j не настроен". self._ers_worker
            # остаётся None — ERS-разрешение не запускается ни для одной строки
            # (error backstop, 13-UI-SPEC §UI Considerations).
            import logging
            logging.getLogger(__name__).warning("KB client unavailable: %s", exc)

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

    def _compose_row_text(self, sub_id: str) -> str:
        """Собрать полный текст строки списка: [звёзды ] {name_ru}: {conc_text} (D-07).

        Единая точка композиции — вызывается из _open_add_dialog, load_schedules,
        update_concentrations и _on_ers_ready, чтобы звёздный префикс и текст
        концентрации никогда не расходились/не стирали друг друга (Pitfall 3).

        Префикс — кэшированные звёзды + один пробел, либо "" если уровень ещё
        не разрешён (не рисуем плейсхолдер — 13-UI-SPEC §Copywriting Contract).
        """
        sub = self._substances.get(sub_id)
        name_ru = sub["name_ru"] if sub else sub_id

        stars = self._ers_stars_by_id.get(sub_id)
        prefix = f"{stars} " if stars else ""

        c = self._last_concentrations.get(sub_id, 0.0)
        conc_text = f"{c:.3f}" if c > 0 else "0.000 (нет в плазме)"

        return f"{prefix}{name_ru}: {conc_text}"

    def _on_ers_ready(self, sub_id: str, level: int) -> None:
        """Слот: ErsBadgeWorker.ers_ready(sub_id, level) — обновить префикс строки (D-07).

        level >= 1 → кэшировать звёзды (_ers_stars, переиспользован из
        kb_client.py, Don't Hand-Roll) и перерисовать строку.
        level == 0 → sentinel «нет фактов / KB недоступна» — префикс НЕ
        устанавливается (13-UI-SPEC: нет плейсхолдер-глифа, только отсутствие
        звёзд).
        """
        if level >= 1:
            self._ers_stars_by_id[sub_id] = _ers_stars(level)

        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == sub_id:
                item.setText(self._compose_row_text(sub_id))
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
        if not self._substances:
            QMessageBox.warning(
                self,
                "Каталог веществ недоступен",
                "Не удалось загрузить substances.json — добавление вещества недоступно.",
            )
            return

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
        dose_spin.setDecimals(_DOSE_DECIMALS)

        def _update_dose_range(index: int) -> None:
            sub_id = combo.itemData(index)
            sub = self._substances[sub_id]
            min_dose = sub["minDose"]
            max_dose = sub["maxDose"]
            if min_dose > max_dose:
                # IN-01: malformed substances.json entry (inverted range) —
                # log instead of silently producing a degenerate/unusable
                # spin box with no indication of why.
                import logging  # noqa: PLC0415
                logging.getLogger(__name__).warning(
                    "Substance %r has minDose (%s) > maxDose (%s) in "
                    "substances.json — dose range may be unusable",
                    sub_id, min_dose, max_dose,
                )
            dose_spin.setRange(min_dose, max_dose)
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

        # Добавить в модель (D-07: текст через _compose_row_text — без звёзд
        # до разрешения, идентично pre-Phase-13 формату)
        item = QStandardItem(self._compose_row_text(sub_id))
        item.setData(sub_id, Qt.ItemDataRole.UserRole)
        self.model.appendRow(item)

        self._added[sub_id] = schedule
        self._row_ids.append(sub_id)

        # D-07: асинхронно запросить ERS-уровень (не блокирует UI thread —
        # T-07-04). Никакого синхронного KBClient-вызова здесь.
        if self._ers_worker is not None:
            self._ers_worker.request_level(sub_id)
            QMetaObject.invokeMethod(
                self._ers_worker,
                "run",
                Qt.ConnectionType.QueuedConnection,
            )

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
        """Корректно завершить KB и ERS QThread при закрытии окна.

        Вызывается из MainWindow.closeEvent() перед завершением simulation thread.
        Паттерн аналогичен Phase 6 D-63 (T-07-06, Pitfall 5). Расширено на
        self._ers_thread (D-07, T-07-06 parity) — оба QThread должны корректно
        завершиться, иначе приложение зависает при выходе.
        """
        if self._kb_worker is not None:
            self._kb_worker.cancel()
        if self._kb_thread.isRunning():
            self._kb_thread.quit()
            self._kb_thread.wait(5000)

        if self._ers_thread.isRunning():
            self._ers_thread.quit()
            self._ers_thread.wait(5000)

        # WR-04: close the Neo4j driver — otherwise the connection pool / bolt
        # sockets stay open for the lifetime of the process on every shutdown.
        if self._kb_client is not None:
            self._kb_client.close()

    def closeEvent(self, event) -> None:
        """Гарантировать корректное завершение обоих QThread при close() виджета.

        Rule 1 (auto-fix bug, deviation from plan literal text): существующие
        тесты (test_kb_client.py::test_substance_manager_tabs,
        test_ui_integration.py::test_substance_manager_signals_and_empty /
        test_substance_manager_schedules_roundtrip) вызывают только sm.close()
        и вручную останавливают _kb_thread, но не знают о новом self._ers_thread
        (не в их scope правки — files_modified этого плана их не включает).
        Без этого override PySide6 при уничтожении виджета удаляет ещё
        работающий self._ers_thread как child QObject → фатальный
        "QThread: Destroyed while thread is still running" (abort, exit 127).
        close_kb_thread() идемпотентен (isRunning() guard) — повторный вызов
        из MainWindow.closeEvent() безопасен.
        """
        self.close_kb_thread()
        super().closeEvent(event)

    def get_schedules(self) -> list[IntakeSchedule]:
        """Вернуть список всех добавленных расписаний (для Save, HS-01).

        Вызывается из MainWindow._on_save_requested.
        """
        return list(self._added.values())

    def load_schedules(self, schedules: list[IntakeSchedule]) -> None:
        """Заменить список веществ загруженным набором (для Load, HS-01).

        Очищает текущий список виджета и _added/_row_ids, затем заполняет заново
        из переданного списка. Если schedules пуст — показывает пустое состояние.

        НЕ эмитит substance_added/substance_removed — вызывающий (MainWindow)
        должен отдельно передать тот же список в Worker.on_load() (Pitfall 2,
        RESEARCH.md: эти два обновления не связаны автоматически сигналом,
        в отличие от инкрементального добавления через диалог).
        """
        self.model.clear()
        self._added.clear()
        self._row_ids.clear()
        # WR-05: концентрация — tick-state, не должна пережить reload (в отличие
        # от _ers_stars_by_id, который substance-invariant и намеренно кэшируется).
        self._last_concentrations.clear()

        if not schedules:
            self._show_empty_state()
            return

        for schedule in schedules:
            sub_id = schedule.substance_id
            # D-07: текст через _compose_row_text (без звёзд до разрешения)
            item = QStandardItem(self._compose_row_text(sub_id))
            item.setData(sub_id, Qt.ItemDataRole.UserRole)
            self.model.appendRow(item)
            self._added[sub_id] = schedule
            self._row_ids.append(sub_id)

            # D-07: асинхронно запросить ERS-уровень для каждой загруженной
            # строки — не блокирует UI thread (T-07-04).
            if self._ers_worker is not None:
                self._ers_worker.request_level(sub_id)
                QMetaObject.invokeMethod(
                    self._ers_worker,
                    "run",
                    Qt.ConnectionType.QueuedConnection,
                )

    def update_concentrations(self, concentrations: dict) -> None:
        """Обновить отображение C(t) для всех добавленных веществ.

        Вызывается из MainWindow._on_state_updated с
        state.substance_concentrations (dict[str, float]).

        Формат (UI-SPEC.md §State Labels):
            «[звёзды ]{name_ru}: {c:.3f}» если c > 0
            «[звёзды ]{name_ru}: 0.000 (нет в плазме)» если c == 0 или отсутствует

        D-07 / Pitfall 3: запись концентрации в _last_concentrations, затем
        setText через _compose_row_text — НИКОГДА голый setText(f"{name_ru}: ...")
        напрямую, иначе уже разрешённый звёздный префикс стирается на каждом тике.
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

            self._last_concentrations[sub_id] = concentrations.get(sub_id, 0.0)
            item.setText(self._compose_row_text(sub_id))
