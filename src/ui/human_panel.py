# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""HumanPanel — панель профиля человека для главного окна симулятора.

Отображает демографические данные, BMI/BMR и индексные показатели
(biological_age, resilience_index) выбранного пресета.

UI-03: Профиль человека с выбором пресета через QComboBox.
D-12: biological_age + resilience_index — два QLabel с акцентным стилем.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from src.domain.human_profile import HumanProfile

# Путь к presets.json: src/ui/human_panel.py → src/ → presets.json
_PRESETS_FILE = Path(__file__).parent.parent / "data" / "presets.json"

# Словарь отображения пола
_SEX_DISPLAY = {
    "male": "Мужской",
    "female": "Женский",
    "unspecified": "Не указан",
}


class HumanPanel(QWidget):
    """Панель профиля человека.

    Показывает:
    - QComboBox для выбора пресета (3 пресета из presets.json)
    - Демографические данные: пол, возраст, рост, вес
    - Вычисленные индексы: BMI, BMR
    - Показатели симуляции: биологический возраст, индекс устойчивости

    Signals:
        profile_changed(HumanProfile): эмитируется при смене пресета
    """

    profile_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── Выбор пресета ──────────────────────────────────────────────────────
        self.preset_combo = QComboBox()
        self._load_presets()
        layout.addRow("Пресет профиля:", self.preset_combo)

        # ── Демографические данные ─────────────────────────────────────────────
        self.sex_value = QLabel("—")
        layout.addRow("Пол:", self.sex_value)

        self.age_value = QLabel("—")
        layout.addRow("Возраст:", self.age_value)

        self.height_value = QLabel("—")
        layout.addRow("Рост:", self.height_value)

        self.weight_value = QLabel("—")
        layout.addRow("Вес:", self.weight_value)

        # ── Вычисленные физические показатели ─────────────────────────────────
        self.bmi_value = QLabel("—")
        layout.addRow("BMI:", self.bmi_value)

        self.bmr_value = QLabel("—")
        layout.addRow("BMR:", self.bmr_value)

        # ── Индексы симуляции (D-12) ───────────────────────────────────────────
        self.chrono_age_value = QLabel("—")
        layout.addRow("Хронологический возраст:", self.chrono_age_value)

        self.bio_age_value = QLabel("—")
        self.bio_age_value.setProperty("primary", True)
        layout.addRow("Биологический возраст:", self.bio_age_value)

        self.resilience_value = QLabel("—")
        self.resilience_value.setProperty("primary", True)
        layout.addRow("Индекс устойчивости:", self.resilience_value)

        self._base_age: float = 0.0

        # Подключить сигнал и выбрать первый пресет
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        if self.preset_combo.count() > 0:
            self._on_preset_selected(0)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_presets(self) -> None:
        """Загружает пресеты из presets.json и заполняет QComboBox."""
        try:
            data = json.loads(_PRESETS_FILE.read_text(encoding="utf-8"))
            for preset in data.get("presets", []):
                display_name = preset.get("display_name", preset["profile_id"])
                profile_id = preset["profile_id"]
                self.preset_combo.addItem(display_name, userData=profile_id)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            # Fallback — одна заглушка если файл не читается
            self.preset_combo.addItem(f"Ошибка загрузки пресетов: {exc}", userData=None)

    def _on_preset_selected(self, index: int) -> None:
        """Обработчик смены пресета. Обновляет QLabel-значения и эмитирует сигнал."""
        preset_id = self.preset_combo.itemData(index)
        if preset_id is None:
            return

        try:
            profile = HumanProfile.from_preset(preset_id)
        except KeyError as exc:
            # T-06-06: защита от неизвестного preset_id
            self.sex_value.setText(f"Не удалось загрузить пресет: {preset_id}")
            self.age_value.setText("—")
            self.height_value.setText("—")
            self.weight_value.setText("—")
            self.bmi_value.setText("—")
            self.bmr_value.setText("—")
            return

        # Обновить демографические данные
        d = profile.demographics
        self.sex_value.setText(_SEX_DISPLAY.get(d.sex.value, d.sex.value))
        self.age_value.setText(f"{d.age} лет")
        self.height_value.setText(f"{d.height_cm:.0f} см")
        self.weight_value.setText(f"{d.weight_kg:.1f} кг")

        # Обновить вычисленные показатели
        self.bmi_value.setText(f"{profile.bmi:.2f}")
        self.bmr_value.setText(f"{profile.bmr:.0f} ккал/день")

        # Сохранить базовый возраст для расчёта хронологического возраста
        self._base_age = float(d.age)
        self.chrono_age_value.setText(f"{d.age} лет")

        # Эмитировать сигнал с выбранным профилем
        self.profile_changed.emit(profile)

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_chrono_age(self, tick_count: int) -> None:
        """Обновить хронологический возраст по числу прошедших тиков (1 тик = 1 час)."""
        if self._base_age == 0.0:
            return
        years_elapsed = tick_count / (24 * 365.25)
        current_age = self._base_age + years_elapsed
        self.chrono_age_value.setText(f"{current_age:.2f} лет")

    def update_indices(
        self,
        biological_age: float | None,
        resilience_index: float | None,
    ) -> None:
        """Обновляет QLabel-значения индексов из сигнала state_updated.

        Args:
            biological_age: биологический возраст в годах или None (не вычислен)
            resilience_index: индекс устойчивости 0–1 или None (не вычислен)
        """
        if biological_age is None:
            self.bio_age_value.setText("—")
        else:
            self.bio_age_value.setText(f"{biological_age:.1f} лет")

        if resilience_index is None:
            self.resilience_value.setText("—")
        else:
            self.resilience_value.setText(f"{resilience_index:.2f}")
