# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""HomeostasisEngine — гомеостатическая модель биомаркеров для im-human simulator.

Реализует:
  - initialize_biomarkers: инициализация 24 биомаркеров по полу/возрасту из reference_ranges.json
  - apply_drift: дрейф к деградированному состоянию с учётом возраста и resilience
  - apply_recovery: восстановление к baseline с учётом lifestyle
  - compute_lifestyle_bonus: суммарный lifestyle-бонус [-0.5..+0.5]
  - clamp_values: зажимание значений биомаркеров [0, max_safe]

Требования плана:
  ENG-03 — гомеостатическая модель (drift/recovery/lifestyle)
  D-06 — baseline = середина optimal_range по полу и возрасту
  D-08 — зажимание [0.0, max_safe_value] каждый тик

Угрозы (T-05-06):
  - Защитная обработка None в initialize_biomarkers (low/high is None)

Запрещено: никаких file I/O внутри методов — reference_ranges передаётся конструктором.
"""
from __future__ import annotations

from src.domain.human_profile import HumanProfile
from src.engine._age_utils import get_age_band as _get_age_band  # WR-01: единая реализация

# ─── Константы модуля ────────────────────────────────────────────────────────

BASE_DRIFT_RATE: float = 0.00002   # дрейф/тик при возрасте 30 [ASSUMED из RESEARCH.md]
RECOVERY_RATE: float = 0.00005    # скорость возврата к оптимуму/тик [ASSUMED из RESEARCH.md]


class HomeostasisEngine:
    """Движок гомеостаза — управляет биомаркерным дрейфом и восстановлением.

    Принимает reference_ranges как dict (не читает файлы — File I/O запрещено
    внутри методов по RESEARCH.md требованиям производительности).
    """

    def __init__(self, reference_ranges: dict) -> None:
        """Инициализировать движок.

        Args:
            reference_ranges: Словарь из reference_ranges.json, уже загруженный.
                              Ключи: коды биомаркеров (ldlC, hdlC, ...).
                              Метаключи начинаются с '_' — пропускаются.
        """
        self.reference_ranges = reference_ranges

    # ─── Публичные методы ─────────────────────────────────────────────────────

    def initialize_biomarkers(self, profile: HumanProfile) -> dict[str, float]:
        """Инициализировать базовые значения биомаркеров по профилю.

        Для каждого биомаркера вычисляет baseline как середину optimal-диапазона
        по полу и возрасту (D-06).

        Обработка None (T-05-06):
          - low is None: инвертированный маркер (HDL, eGFR, HRV); baseline = high
          - high is None: нет верхней границы; baseline = low * 1.1

        Args:
            profile: HumanProfile с demographics.sex и demographics.age.

        Returns:
            dict[str, float] с 24 ключами биомаркеров.
        """
        sex_key: str = profile.demographics.sex.value  # "male" / "female"
        age_band: str = _get_age_band(profile.demographics.age)

        result: dict[str, float] = {}

        for code, sex_data in self.reference_ranges.items():
            # Пропустить метаключи (начинаются с '_')
            if code.startswith("_"):
                continue

            age_data = sex_data.get(sex_key, {}).get(age_band, {})
            ranges = age_data.get("optimal")
            if ranges is None:
                # Биомаркер не имеет optimal-ключа — пропустить безопасно
                continue

            low = ranges[0]
            high = ranges[1]

            if low is None:
                # Инвертированный биомаркер: хорошо = высокое значение (HDL, eGFR, HRV)
                # baseline = high (нижняя граница оптимума = минимально хорошее значение)
                baseline = float(high)
            elif high is None:
                # Нет верхней границы: baseline = low * 1.1 (практический "умеренно хорошо")
                baseline = float(low) * 1.1
            else:
                baseline = (float(low) + float(high)) / 2.0

            result[code] = baseline

        return result

    def _compute_degraded_value(
        self,
        code: str,
        sex_key: str,
        age_band: str,
        baseline: float,
    ) -> float:
        """Вычислить деградированное (пожилое) значение биомаркера.

        Логика:
        - Если есть high_risk и его нижняя граница (high_risk[0]) не None → degraded = high_risk[0]
        - Если high_risk[0] is None (инвертированный, напр. HDL: high_risk=[null, 0.8]) →
          деградация вниз: degraded = high_risk[1] (верхняя граница high_risk = нижний порог опасности)
        - Fallback: degraded = baseline * 1.5

        Args:
            code: Код биомаркера (напр. 'ldlC').
            sex_key: 'male' или 'female'.
            age_band: Возрастная группа (напр. '70+').
            baseline: Текущее значение для расчёта fallback.

        Returns:
            float — деградированное значение.
        """
        code_data = self.reference_ranges.get(code, {})
        age_data = code_data.get(sex_key, {}).get(age_band, {})
        high_risk = age_data.get("high_risk")

        if high_risk is not None and len(high_risk) >= 2:
            low_hr = high_risk[0]
            high_hr = high_risk[1]
            if low_hr is not None:
                # Обычный биомаркер: degraded = начало зоны high_risk (низкое значение плохое)
                # Не используем т.к. RESEARCH.md говорит: degraded = high_risk_start
                return float(low_hr)
            elif high_hr is not None:
                # Инвертированный биомаркер (HDL, eGFR): риск при значении НИЖЕ high_hr
                # Деградированное = граница опасности (значение падает к этому уровню)
                return float(high_hr)

        # Fallback: инвертированный биомаркер деградирует вниз (30% снижение),
        # обычный биомаркер деградирует вверх (50% рост).
        from src.engine.event_detector import INVERTED_BIOMARKERS
        if code in INVERTED_BIOMARKERS:
            return baseline * 0.7   # инвертированный: хуже = ниже baseline
        return baseline * 1.5       # обычный: хуже = выше baseline

    def apply_drift(
        self,
        biomarker_values: dict[str, float],
        profile: HumanProfile,
        resilience_index: float,
    ) -> dict[str, float]:
        """Применить гомеостатический дрейф к деградированным значениям.

        Каждый биомаркер смещается к deградированному уровню на каждом тике.
        Скорость зависит от возраста и resilience_index.

        Формула (RESEARCH.md Area 2):
          age_factor = max(0, (age - 30) / 100)
          effective_rate = BASE_DRIFT_RATE * (1 + age_factor) * (1 - resilience * 0.5)
          drift = (degraded - current) * effective_rate

        Args:
            biomarker_values: Текущие значения биомаркеров (мутируется in-place).
            profile: HumanProfile для возраста/пола.
            resilience_index: Индекс стойкости [0..1].

        Returns:
            dict[str, float] — обновлённые значения (тот же объект).
        """
        sex_key: str = profile.demographics.sex.value
        age: int = profile.demographics.age
        age_band: str = _get_age_band(age)

        age_factor = max(0.0, (age - 30) / 100.0)
        effective_rate = (
            BASE_DRIFT_RATE
            * (1.0 + age_factor)
            * (1.0 - resilience_index * 0.5)
        )

        for code, current_val in biomarker_values.items():
            degraded = self._compute_degraded_value(code, sex_key, age_band, current_val)
            drift = (degraded - current_val) * effective_rate
            biomarker_values[code] = current_val + drift

        return biomarker_values

    def apply_recovery(
        self,
        biomarker_values: dict[str, float],
        baseline: dict[str, float],
        resilience_index: float,
        lifestyle_bonus: float = 0.0,
    ) -> dict[str, float]:
        """Применить гомеостатическое восстановление к baseline.

        Биомаркеры, отклонившиеся от baseline (например, из-за болезни),
        возвращаются к нему через RECOVERY_RATE.

        Формула (RESEARCH.md Area 2):
          gap = baseline[code] - current
          recovery = gap * RECOVERY_RATE * resilience * (1 + lifestyle_bonus)

        Args:
            biomarker_values: Текущие значения (мутируется in-place).
            baseline: Baseline значения (из initialize_biomarkers).
            resilience_index: Индекс стойкости [0..1].
            lifestyle_bonus: Lifestyle-бонус [-0.5..+0.5].

        Returns:
            dict[str, float] — обновлённые значения (тот же объект).
        """
        for code, current_val in biomarker_values.items():
            if code not in baseline:
                continue
            gap = baseline[code] - current_val
            recovery = gap * RECOVERY_RATE * resilience_index * (1.0 + lifestyle_bonus)
            biomarker_values[code] = current_val + recovery

        return biomarker_values

    @staticmethod
    def compute_lifestyle_bonus(profile: HumanProfile) -> float:
        """Вычислить суммарный бонус образа жизни.

        Нормализует каждый lifestyle-фактор профиля и суммирует в
        итоговый бонус в диапазоне [-0.5, +0.5].

        Формула (RESEARCH.md Area 2):
          stress_penalty  = -stress / 200             (max -0.5)
          sleep_bonus     = sleep_quality / 200       (max +0.5)
          diet_bonus      = diet_quality / 200        (max +0.5)
          activity_bonus  = (multiplier - 1.2) / 0.7 * 0.3
          alcohol_penalty = -alcohol / 200            (max -0.5)

        Args:
            profile: HumanProfile с lifestyle-полями.

        Returns:
            float в диапазоне [-0.5, +0.5].
        """
        ls = profile.lifestyle
        stress_penalty = -ls.stress / 200.0
        sleep_bonus = ls.sleep_quality / 200.0
        diet_bonus = ls.diet_quality / 200.0
        activity_bonus = (ls.physical_activity.multiplier - 1.2) / 0.7 * 0.3
        alcohol_penalty = -ls.alcohol / 200.0

        total = stress_penalty + sleep_bonus + diet_bonus + activity_bonus + alcohol_penalty
        return max(-0.5, min(0.5, total))

    def clamp_values(
        self,
        biomarker_values: dict[str, float],
        max_safe: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Зажать значения биомаркеров в безопасные границы [0, max_safe].

        Реализует D-08: зажимание [0.0, max_safe_value] каждый тик.

        Args:
            biomarker_values: Значения биомаркеров (мутируется in-place).
            max_safe: Словарь максимально безопасных значений по коду.
                     Если None или ключ отсутствует — верхний предел 1e6.

        Returns:
            dict[str, float] — зажатые значения (тот же объект).
        """
        for code, val in biomarker_values.items():
            upper = max_safe.get(code, 1e6) if max_safe else 1e6
            biomarker_values[code] = max(0.0, min(val, upper))

        return biomarker_values
