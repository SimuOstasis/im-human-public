# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""EventDetector — преобразует значения биомаркеров в SimulationEvent объекты.

Два типа событий:
  THRESHOLD_BREACH — значение биомаркера пересекло high_risk границу (D-12)
  PROBABILISTIC    — вероятностные события (CVD, диабет, почки, гипертония) (D-13)

Severity CRITICAL автоматически паузирует FSM (D-15).

Threat mitigations:
  T-05-09: math.isfinite(val) guard — NaN/Inf → пропустить событие
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from src.domain.simulation_state import SimulationEvent
from src.engine._age_utils import get_age_band as _get_age_band  # WR-01: единая реализация

if TYPE_CHECKING:
    from src.domain.human_profile import HumanProfile

# ─── Константы модуля ─────────────────────────────────────────────────────────

# Биомаркеры, у которых риск при НИЗКОМ значении (high_risk[1] = верхний порог снизу)
INVERTED_BIOMARKERS: frozenset[str] = frozenset({
    "hdlC",
    "egfr",
    "albumin",
    "hrvRmssd",
    "hemoglobin",
})

# Базовый 10-летний кардиоваскулярный риск (5%)
CVD_BASE_10YR: float = 0.05


# ─── EventDetector ────────────────────────────────────────────────────────────

class EventDetector:
    """Детектор событий симуляции — пороговые и вероятностные нарушения.

    Конструктор принимает reference_ranges dict (из reference_ranges.json).
    Не хранит состояние между тиками — stateless.
    """

    def __init__(self, reference_ranges: dict) -> None:
        """Инициализация с reference_ranges из reference_ranges.json."""
        self.reference_ranges = reference_ranges

    # ─── Пороговые события ────────────────────────────────────────────────────

    def check_threshold_breaches(
        self,
        biomarker_values: dict[str, float],
        profile: "HumanProfile",
        tick: int,
    ) -> list[SimulationEvent]:
        """Проверить все биомаркеры на пересечение high_risk порога.

        Для инвертированных биомаркеров: риск при val <= threshold (high_risk[1]).
        Для обычных: риск при val >= threshold (high_risk[0]).

        T-05-09: NaN/Inf значения пропускаются (math.isfinite guard).

        Returns:
            Список SimulationEvent с event_type="THRESHOLD_BREACH".
        """
        sex_key = profile.demographics.sex.value
        age_band = _get_age_band(profile.demographics.age)
        events: list[SimulationEvent] = []

        for code, val in biomarker_values.items():
            # T-05-09: пропустить не-числовые значения
            if not math.isfinite(val):
                continue

            if code not in self.reference_ranges:
                continue

            rr_entry = self.reference_ranges[code]
            # Проверить наличие sex_key и age_band (graceful degradation)
            if sex_key not in rr_entry:
                continue
            sex_entry = rr_entry[sex_key]
            if age_band not in sex_entry:
                continue

            rr = sex_entry[age_band].get("high_risk")
            if rr is None or len(rr) < 2:
                continue

            if code in INVERTED_BIOMARKERS:
                # high_risk = [null, threshold] — риск при значении НИЖЕ threshold
                threshold = rr[1]
                if threshold is not None and val <= threshold:
                    # CRITICAL если значение упало ещё на 20% ниже порога
                    severity = "CRITICAL" if val <= threshold * 0.8 else "WARNING"
                    events.append(SimulationEvent(
                        tick=tick,
                        event_type="THRESHOLD_BREACH",
                        biomarker=code,
                        value=val,
                        message=f"{code}={val:.3f} ниже порога {threshold}",
                        severity=severity,
                    ))
            else:
                # high_risk = [threshold, null] — риск при значении ВЫШЕ threshold
                threshold = rr[0]
                if threshold is not None and val >= threshold:
                    # CRITICAL если значение превысило порог ещё на 30%
                    severity = "CRITICAL" if val >= threshold * 1.3 else "WARNING"
                    events.append(SimulationEvent(
                        tick=tick,
                        event_type="THRESHOLD_BREACH",
                        biomarker=code,
                        value=val,
                        message=f"{code}={val:.3f} выше порога {threshold}",
                        severity=severity,
                    ))

        return events

    # ─── Вероятностные события ────────────────────────────────────────────────

    def check_probabilistic_events(
        self,
        biomarker_values: dict[str, float],
        profile: "HumanProfile",
        tick: int,
        rng: object,
    ) -> list[SimulationEvent]:
        """Вычислить вероятностные события на основе текущих значений биомаркеров.

        Все 4 события используют rng.random() для детерминированных проверок.
        Graceful degradation: если биомаркер отсутствует — использовать default.

        Args:
            biomarker_values: Текущие значения биомаркеров из SimulationState.
            profile: Профиль пользователя (возраст, пол).
            tick: Текущий тик симуляции.
            rng: SimulationRNG или любой объект с методом random() → float [0, 1).

        Returns:
            Список SimulationEvent с event_type="PROBABILISTIC".
        """
        events: list[SimulationEvent] = []
        age = profile.demographics.age
        sex = profile.demographics.sex.value

        # ── 1. Кардиоваскулярный риск (CVD) ──────────────────────────────────
        ldl = biomarker_values.get("ldlC", 2.0)
        sbp = biomarker_values.get("systolicBloodPressure", 120.0)
        if math.isfinite(ldl) and math.isfinite(sbp):
            ldl_factor = max(1.0, ldl / 2.5)
            # WR-05: при SBP=120 → 1.0 (норма), SBP=140 → 1.5, SBP=160 → 2.0
            bp_factor = max(1.0, 1.0 + (sbp - 120.0) / 40.0)
            age_factor = max(1.0, (age - 40) / 10.0)
            sex_mult = 1.3 if sex == "male" else 1.0
            p_10yr = min(0.8, CVD_BASE_10YR * ldl_factor * bp_factor * age_factor * sex_mult)
            # Конвертация 10-летнего риска в per-tick (87600 часов = 10 лет)
            p_tick = 1.0 - (1.0 - p_10yr) ** (1.0 / 87600.0)
            if rng.random() < p_tick:
                events.append(SimulationEvent(
                    tick=tick,
                    event_type="PROBABILISTIC",
                    biomarker="ldlC",
                    value=p_10yr,
                    message=f"Кардиоваскулярный риск: 10-летний риск {p_10yr:.1%}",
                    severity="WARNING",
                ))

        # ── 2. Риск диабета ───────────────────────────────────────────────────
        hba1c = biomarker_values.get("hba1c", 5.0)
        gluc = biomarker_values.get("fastingGlucose", 5.0)
        if math.isfinite(hba1c) and math.isfinite(gluc) and hba1c > 5.7 and gluc > 5.5:
            p_10yr_dm = min(0.5, 0.1 * (hba1c - 5.7) / 0.8)
            p_tick_dm = 1.0 - (1.0 - p_10yr_dm) ** (1.0 / 87600.0)
            if rng.random() < p_tick_dm:
                events.append(SimulationEvent(
                    tick=tick,
                    event_type="PROBABILISTIC",
                    biomarker="hba1c",
                    value=hba1c,
                    message=f"Риск диабета: HbA1c={hba1c:.1f}%, глюкоза={gluc:.1f}",
                    severity="WARNING",
                ))

        # ── 3. Риск снижения функции почек (CKD) ─────────────────────────────
        creat = biomarker_values.get("creatinine", 80.0)
        egfr = biomarker_values.get("egfr", 90.0)
        if math.isfinite(creat) and math.isfinite(egfr) and creat > 115.0 and egfr < 70.0:
            p_10yr_ckd = min(0.3, 0.05 * (1.0 - egfr / 90.0))
            p_tick_ckd = 1.0 - (1.0 - p_10yr_ckd) ** (1.0 / 87600.0)
            if rng.random() < p_tick_ckd:
                events.append(SimulationEvent(
                    tick=tick,
                    event_type="PROBABILISTIC",
                    biomarker="egfr",
                    value=egfr,
                    message=f"Риск снижения eGFR: creatinine={creat:.0f}, eGFR={egfr:.0f}",
                    severity="WARNING",
                ))

        # ── 4. Гипертонический криз ───────────────────────────────────────────
        sbp_crisis = biomarker_values.get("systolicBloodPressure", 120.0)
        if math.isfinite(sbp_crisis) and sbp_crisis > 160.0:
            if rng.random() < 0.001:
                events.append(SimulationEvent(
                    tick=tick,
                    event_type="PROBABILISTIC",
                    biomarker="systolicBloodPressure",
                    value=sbp_crisis,
                    message=f"Гипертонический криз: АД сист.={sbp_crisis:.0f} мм рт.ст.",
                    severity="CRITICAL",
                ))

        return events
