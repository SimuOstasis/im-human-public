# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""MortalityRiskEngine — биологический возраст и resilience для im-human simulator.

Реализует частичную PhenoAge (Levine et al. 2018) на 4 доступных биомаркерах из MVP-24.

Угрозы (T-05-14): biological_age в логах — информация локальна, сеть не используется.
"""
from __future__ import annotations

import math

# ─── Константы PhenoAge ──────────────────────────────────────────────────────

PHENOAGE_BETA: dict[str, float] = {
    "albumin":   -0.0336,
    "creatinine": 0.0095,
    "glucose":    0.1953,
    "log_hscrp":  0.0954,
}
PHENOAGE_AGE_COEF: float = 0.0804
# Calibrated intercept — методологически выведен (Phase 12, HF-02, D-06/D-14, Approach A),
# НЕ подобран под тестовый гейт. Метод: разовый calibration-скрипт
# scripts/calibrate_phenoage_intercept.py (не runtime-зависимость, не импортируется
# отсюда) прогоняет истинную нелинейную формулу Levine et al. 2018 (PMC5940111,
# Gompertz-трансформ, все 9 маркеров PhenoAge) по реальной выборке NHANES 2010
# (biolearn.load.load_nhanes, n=2877 взрослых 18-80 — обеспечивает референсные
# значения для 5 маркеров, отсутствующих в этой упрощённой модели: Lymphocyte%,
# MCV, RDW, ALP, WBC), получая референсные `biological_age`. Затем эта же линейная
# форма кодовой базы (фиксированные PHENOAGE_BETA/PHENOAGE_AGE_COEF выше, не
# менявшиеся) OLS-подгоняется под референс, варьируя ТОЛЬКО этот intercept
# (замкнутая форма для единственного свободного параметра: intercept =
# mean(референс − partial_sum_без_intercept)). Подробности метода, единицы
# измерения и найденные при выводе неточности исходного исследования (12-RESEARCH.md
# §HF-02 Deep-Dive) — в докстринге scripts/calibrate_phenoage_intercept.py и
# 12-01-SUMMARY.md.
#
# WR-01 code-review fix (2026-07-19): предыдущее значение (19.0565) было
# откалибровано против `_to_phenoage_units()`, которая ошибочно конвертировала
# albumin/creatinine/glucose в "конвенциональные" г/дл/мг/дл перед применением
# SI-калиброванных PHENOAGE_BETA — искажая чувствительность модели к этим
# маркерам (creatinine ~88× занижена, glucose ~18× завышена). После удаления
# этой ошибочной конвертации (albumin/creatinine/glucose теперь передаются
# напрямую в SI-единицах Table 1, как и предполагают PHENOAGE_BETA) intercept
# пересчитан заново тем же методом на той же NHANES-выборке (n=2877). Остаточное
# std подгонки на уровне отдельных NHANES-строк ≈19.9 года (было ≈18.6 —
# сопоставимо; это упрощённая 4-маркерная линейная модель объясняет лишь часть
# дисперсии истинной 9-маркерной нелинейной PhenoAge — ожидаемое ограничение
# архитектуры, не ошибка вывода intercept'а).
PHENOAGE_INTERCEPT_PARTIAL: float = 39.24825879622859

# ─── Константы resilience ────────────────────────────────────────────────────

RESILIENCE_PARAMS: dict[str, tuple[float, float]] = {
    "albumin":   (35.0, 55.0),   # g/L
    "egfr":      (30.0, 120.0),  # мл/мин/1.73м²
    "hrvRmssd":  (15.0, 80.0),   # мс
}


class MortalityRiskEngine:
    """Вычисляет биологический возраст (частичная PhenoAge) и resilience_index.

    Используется SimulationEngine на каждом тике (шаги 10/11).
    Нет file I/O — все данные из constantes модуля.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _to_phenoage_units(biomarkers: dict[str, float]) -> dict[str, float]:
        """Конвертировать биомаркеры в единицы PhenoAge Levine 2018 (PMC5940111 Table 1).

        Table 1 публикации использует НАПРЯМУЮ SI-единицы NHANES для albumin/
        creatinine/glucose (WR-01 code-review fix, 2026-07-19) — БЕЗ конвертации
        в "конвенциональные" г/дл/мг/дл, как ошибочно делалось ранее (см. находку
        в docstring scripts/calibrate_phenoage_intercept.py, п.3). Единственная
        реальная конвертация единиц — hsCrp: мг/л → мг/дл (÷10), т.к. приложение
        хранит hsCrp в мг/л, а формуле нужен log(CRP в мг/дл).

        Конвертации:
          albumin: g/L → g/L (без изменений, уже SI)
          creatinine: µmol/L → µmol/L (без изменений, уже SI)
          fastingGlucose: mmol/L → mmol/L (без изменений, уже SI)
          hsCrp: mg/L → log(mg/dL) = log(hsCrp ÷ 10)
        """
        return {
            "albumin": biomarkers.get("albumin", 45.0),
            "creatinine": biomarkers.get("creatinine", 80.0),
            "glucose": biomarkers.get("fastingGlucose", 5.0),
            "log_hscrp": math.log(max(0.01, biomarkers.get("hsCrp", 1.0) / 10.0)),
        }

    def compute_biological_age(
        self,
        biomarkers: dict[str, float],
        chronological_age: int,
    ) -> float:
        """Вычислить биологический возраст по частичной формуле PhenoAge.

        Использует 4 из 9 оригинальных биомаркеров PhenoAge: albumin, creatinine,
        fastingGlucose, hsCrp. Недостающие (Lymphocyte%, MCV, RDW, ALP, WBC) →
        заложены в PHENOAGE_INTERCEPT_PARTIAL.

        PHENOAGE_INTERCEPT_PARTIAL выведен методологически (Approach A, D-06/D-14) —
        см. комментарий к константе выше и scripts/calibrate_phenoage_intercept.py.

        Args:
            biomarkers: Словарь биомаркеров в единицах MVP-24.
            chronological_age: Хронологический возраст в годах.

        Returns:
            Биологический возраст в годах, зажатый в [1.0, 120.0].
        """
        converted = self._to_phenoage_units(biomarkers)
        linear = (
            PHENOAGE_BETA["albumin"] * converted["albumin"]
            + PHENOAGE_BETA["creatinine"] * converted["creatinine"]
            + PHENOAGE_BETA["glucose"] * converted["glucose"]
            + PHENOAGE_BETA["log_hscrp"] * converted["log_hscrp"]
            + PHENOAGE_AGE_COEF * chronological_age
            + PHENOAGE_INTERCEPT_PARTIAL
        )
        return max(1.0, min(120.0, linear))

    def compute_resilience(self, biomarkers: dict[str, float]) -> float:
        """Вычислить resilience_index — способность к восстановлению.

        Среднее нормированных значений albumin, eGFR, HRV RMSSD.
        Нормировка: clamp((val - low) / (high - low), 0, 1).

        Args:
            biomarkers: Словарь биомаркеров.

        Returns:
            float в [0.0, 1.0]; 0.5 если ни один биомаркер не найден.
        """
        scores: list[float] = []
        for key, (low, high) in RESILIENCE_PARAMS.items():
            val = biomarkers.get(key)
            if val is not None:
                norm = (val - low) / (high - low)
                scores.append(max(0.0, min(1.0, norm)))
        if not scores:
            return 0.5
        return sum(scores) / len(scores)
