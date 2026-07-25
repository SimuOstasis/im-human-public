# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""TimeControls — панель управления временем симуляции.

Содержит кнопки скорости (x1–x10000), кнопки Запустить/Пауза/Возобновить/Сброс,
статус симуляции и счётчик модельного времени.

Кнопка называется «Сброс», не «Стоп»: она необратимо завершает текущий прогон
(FSM STOPPED терминален, .transition() из него никуда не ведёт) — при следующем
«Запустить» тики начнутся заново с 0, даже если состояние было Save/Load'нуто
после «Сброс». Возобновляемая точка сохранения — это «Пауза» (Save после неё
корректно Resume'ится с того же tick_count через «Возобновить»).

UI-04: Управление временем симуляции.
D-08: Кнопки скорости в QButtonGroup (checkable, exclusive); speed_changed эмитит multiplier.
T-06-07: _apply_button_states отключает недопустимые кнопки по таблице §Button States.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.domain.simulation_state import SimulationStatus

# Пары (текст кнопки, множитель скорости)
_SPEED_BUTTONS: list[tuple[str, int]] = [
    ("x1", 1),
    ("x10", 10),
    ("x100", 100),
    ("x1000", 1000),
    ("x10000", 10000),
]

# Маппинг SimulationStatus → текст статуса (UI-SPEC.md §State Labels)
_STATUS_TEXT: dict[SimulationStatus, str] = {
    SimulationStatus.IDLE: "Ожидание",
    SimulationStatus.RUNNING: "Выполняется",
    SimulationStatus.PAUSED: "Приостановлено",
    SimulationStatus.STOPPED: "Сброшено",
}


def _ru_days(n: int) -> str:
    """Вернуть правильную форму слова «день» для числительного n (IN-01).

    Стандартное русское склонение: 1, 21, 31... → «день»; 2-4, 22-24... →
    «дня»; 0, 5-20, 25-30... → «дней» (11-14 — исключение, всегда «дней»).
    """
    n_abs = abs(n)
    if n_abs % 100 in (11, 12, 13, 14):
        return "дней"
    last_digit = n_abs % 10
    if last_digit == 1:
        return "день"
    if last_digit in (2, 3, 4):
        return "дня"
    return "дней"


class TimeControls(QWidget):
    """Панель управления временем симуляции.

    Содержит:
    - 5 кнопок скорости в QButtonGroup (checkable, exclusive): x1..x10000
    - Кнопки: «Запустить», «Пауза», «Возобновить», «Сброс»
    - QLabel статуса симуляции и модельного времени

    Signals (UI-SPEC.md §Signal/Slot Contracts):
        start_requested(object): пользователь нажал «Запустить»
        pause_requested(): пользователь нажал «Пауза»
        resume_requested(): пользователь нажал «Возобновить»
        stop_requested(): пользователь нажал «Сброс» (имя сигнала/слота не менялось,
            только видимый пользователю текст кнопки — см. модульный docstring)
        speed_changed(int): пользователь выбрал кнопку скорости (значение = множитель)
    """

    # ── Сигналы (точное соответствие UI-SPEC.md §Signal/Slot Contracts) ────────
    start_requested = Signal(object)
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    speed_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # D-04: последний статус, для которого реально выполнялся repolish
        # QSS кнопок в _apply_button_states — None означает «ещё ни разу»,
        # так что самый первый вызов (из __init__ ниже) всегда реполирует.
        self._last_applied_status: SimulationStatus | None = None

        # Корневой макет: вертикальный (строка кнопок управления + строка статуса)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(4)

        # ── Строка 1: кнопки управления ────────────────────────────────────────
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)

        # Кнопка «Запустить»
        self.start_btn = QPushButton("Запустить")
        self.start_btn.setProperty("primary", True)
        controls_layout.addWidget(self.start_btn)

        # Кнопки скорости: QButtonGroup (checkable, exclusive)
        self._speed_group = QButtonGroup(self)
        self._speed_group.setExclusive(True)
        self._speed_multiplier_map: dict[QPushButton, int] = {}

        for label, multiplier in _SPEED_BUTTONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            self._speed_group.addButton(btn)
            self._speed_multiplier_map[btn] = multiplier
            controls_layout.addWidget(btn)

        # По умолчанию выбрать x1
        first_speed_btn = list(self._speed_multiplier_map.keys())[0]
        first_speed_btn.setChecked(True)
        first_speed_btn.setProperty("active", True)

        # Кнопки «Пауза» / «Возобновить»
        self.pause_btn = QPushButton("Пауза")
        controls_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("Возобновить")
        self.resume_btn.setProperty("primary", True)
        self.resume_btn.setVisible(False)
        controls_layout.addWidget(self.resume_btn)

        # «Сброс» больше не показывается как кнопка на панели — вместо неё
        # MainWindow добавляет пункт «Новая» в меню «Файл» (тот же confirm-
        # диалог и обработчик). stop_btn остаётся как внутренний, невидимый
        # держатель enabled/disabled-состояния (см. _apply_button_states) —
        # MainWindow читает stop_btn.isEnabled() вместо дублирования таблицы
        # состояний. Явно parent'им, раз он не добавляется в layout.
        self.stop_btn = QPushButton("Сброс", self)
        self.stop_btn.setVisible(False)

        root_layout.addLayout(controls_layout)

        # ── Строка 2: статус и модельное время ────────────────────────────────
        status_layout = QHBoxLayout()
        status_layout.setSpacing(16)

        self.status_label = QLabel("Ожидание")
        self.status_label.setProperty("secondary", True)
        status_layout.addWidget(self.status_label)

        self.elapsed_label = QLabel("Модельное время: 0 дней")
        self.elapsed_label.setProperty("secondary", True)
        status_layout.addWidget(self.elapsed_label)

        status_layout.addStretch()
        root_layout.addLayout(status_layout)

        # ── Подключить сигналы кнопок ──────────────────────────────────────────
        self.start_btn.clicked.connect(lambda: self.start_requested.emit(None))
        self.pause_btn.clicked.connect(self.pause_requested.emit)
        self.resume_btn.clicked.connect(self.resume_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

        # Обработчик кнопок скорости
        for btn, multiplier in self._speed_multiplier_map.items():
            btn.clicked.connect(lambda checked, m=multiplier, b=btn: self._on_speed_clicked(b, m))

        # Начальное состояние кнопок
        self._apply_button_states(SimulationStatus.IDLE)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _on_speed_clicked(self, clicked_btn: QPushButton, multiplier: int) -> None:
        """Обработчик клика по кнопке скорости."""
        # Обновить QSS property "active" на всех кнопках скорости
        for btn in self._speed_multiplier_map:
            is_active = btn is clicked_btn
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.speed_changed.emit(multiplier)

    def _apply_button_states(self, status: SimulationStatus) -> None:
        """Применяет состояния кнопок по таблице UI-SPEC.md §Button States.

        T-06-07: предотвращает недопустимые действия (напр. старт при RUNNING).

        Button States by Simulation Status:
        ┌─────────────────┬───────┬─────────┬────────┬─────────┐
        │ Кнопка          │ IDLE  │ RUNNING │ PAUSED │ STOPPED │
        ├─────────────────┼───────┼─────────┼────────┼─────────┤
        │ Запустить       │  вкл  │  откл   │  откл  │   вкл   │
        │ Пауза           │  откл │  вкл    │ скрыта │  откл   │
        │ Возобновить     │ скрыт │  скрыт  │  вкл   │  скрыт  │
        │ Сброс           │  откл │  вкл    │  вкл   │  откл   │
        │ Кнопки скорости │  вкл  │  вкл    │  откл  │   вкл   │
        └─────────────────┴───────┴─────────┴────────┴─────────┘

        D-04: repolish (unpolish/polish) 4 кнопок выполняется только когда
        `status` реально отличается от последнего применённого — иначе это
        полная переоценка QSS 5 раз/с без визуальных изменений (MainWindow
        зовёт update_status на каждом эмите state_updated в обход throttle).
        Ветки setEnabled/setVisible/setProperty ниже остаются безусловными —
        они дешёвые и должны отражать актуальный статус каждый вызов.
        """
        status_changed = status != self._last_applied_status

        if status == SimulationStatus.IDLE:
            self.start_btn.setEnabled(True)
            self.start_btn.setProperty("primary", True)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setVisible(True)
            self.resume_btn.setVisible(False)
            self.stop_btn.setEnabled(False)
            self._set_speed_buttons_enabled(True)

        elif status == SimulationStatus.RUNNING:
            self.start_btn.setEnabled(False)
            self.start_btn.setProperty("primary", False)
            self.pause_btn.setEnabled(True)
            self.pause_btn.setVisible(True)
            self.resume_btn.setVisible(False)
            self.stop_btn.setEnabled(True)
            self._set_speed_buttons_enabled(True)

        elif status == SimulationStatus.PAUSED:
            self.start_btn.setEnabled(False)
            self.start_btn.setProperty("primary", False)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setVisible(False)
            self.resume_btn.setVisible(True)
            self.resume_btn.setEnabled(True)
            self.resume_btn.setProperty("primary", True)
            self.stop_btn.setEnabled(True)
            self._set_speed_buttons_enabled(False)

        elif status == SimulationStatus.STOPPED:
            self.start_btn.setEnabled(True)
            self.start_btn.setProperty("primary", True)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setVisible(True)
            self.resume_btn.setVisible(False)
            self.stop_btn.setEnabled(False)
            self._set_speed_buttons_enabled(True)

        # D-04: переполировать кнопки для QSS-перерисовки только при реальной
        # смене статуса — иначе безусловный repolish 4 кнопок при каждом
        # вызове update_status (до 5 раз/с) впустую переоценивает QSS.
        if status_changed:
            for btn in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self._last_applied_status = status

    def _set_speed_buttons_enabled(self, enabled: bool) -> None:
        """Включает или отключает все кнопки скорости."""
        for btn in self._speed_multiplier_map:
            btn.setEnabled(enabled)

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_status(self, status: SimulationStatus, tick_count: int) -> None:
        """Обновляет статус симуляции, модельное время и состояния кнопок.

        Args:
            status: текущий статус из SimulationState.status
            tick_count: текущее число тиков из SimulationState.tick_count
                        (тик = 1 час; дни = tick_count // 24)
        """
        # Обновить текст статуса
        status_text = _STATUS_TEXT.get(status, status.value)
        self.status_label.setText(status_text)

        # Обновить модельное время
        days = tick_count // 24
        self.elapsed_label.setText(f"Модельное время: {days} {_ru_days(days)}")

        # Обновить состояния кнопок
        self._apply_button_states(status)
