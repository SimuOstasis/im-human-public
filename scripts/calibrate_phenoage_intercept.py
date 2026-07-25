#!/usr/bin/env python
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Разовый calibration-скрипт: пересчёт PHENOAGE_INTERCEPT_PARTIAL (HF-02, D-06/D-14).

НЕ импортируется НИ ОДНИМ модулем под src/ — это calibration-time-only утилита,
её единственный побочный эффект — печать нового числового значения intercept'а,
которое затем ВРУЧНУЮ вставляется в src/engine/mortality_risk.py (Task 2).

Зависимости этого скрипта (`biolearn`, транзитивно `numpy`/`pandas`/`requests`)
НЕ добавляются в requirements.txt (D-14) — приложение их никогда не импортирует.
Легитимность `biolearn` проверена перед установкой (T-12-SC): PyPI-листинг
`biolearn` (https://pypi.org/project/biolearn/) — 34 релиза начиная с 2023 года,
лицензия New BSD, автор "Biolearn developers", соответствует официальному сайту
проекта https://bio-learn.github.io и статье https://www.biorxiv.org/content/
10.1101/2023.12.02.569722v4.full.pdf, процитированной в 12-RESEARCH.md.

Запуск (в ОТДЕЛЬНОМ calibration-окружении, не в venv/ проекта):
    python -m venv /tmp/calib-venv
    /tmp/calib-venv/Scripts/python.exe -m pip install --no-deps biolearn
    /tmp/calib-venv/Scripts/python.exe -m pip install \
        numpy pandas pyyaml requests scikit-learn scipy openpyxl xlrd appdirs matplotlib
    /tmp/calib-venv/Scripts/python.exe scripts/calibrate_phenoage_intercept.py

Примечание: `biolearn`'s объявленные зависимости `cvxpy`/`ecos` НЕ нужны для этого
скрипта (они используются только DNA-метилирование-imputation частью пакета,
`biolearn.imputation`, не затрагиваемой здесь) — `--no-deps` install избегает их
(на момент калибровки `ecos` не имел прекомпилированных wheel для актуальной
версии Python на машине исполнителя, а сборка требовала недоступного MSVC-тулчейна).

────────────────────────────────────────────────────────────────────────────
МЕТОДОЛОГИЯ (Подход A, D-14)
────────────────────────────────────────────────────────────────────────────

1. Референсный генератор — ИСТИННАЯ нелинейная формула Levine et al. 2018
   (PMC5940111 "An epigenetic biomarker of aging for lifespan and healthspan",
   Table 1 + Methods), реализованная ниже дословно (см. `_true_phenotypic_age`).

2. Референсные данные для ВСЕХ 9 маркеров формулы — реальная выборка NHANES
   2010 (`biolearn.load.load_nhanes(2010)`, США, Национальное обследование
   здоровья и питания, N≈2877 взрослых 18-80 лет после отбрасывания строк с
   пропусками и CRP<=0). Обоснование выбора диапазона (executor's discretion,
   явно разрешено плана-текстом): вместо произвольной синтетической сетки для
   4 отслеживаемых маркеров (albumin/creatinine/glucose/hsCRP) × возраст,
   использована РЕАЛЬНАЯ совместная эмпирическая выборка NHANES — это строже,
   чем независимая сетка, потому что сохраняет настоящие корреляции между
   маркерами и возрастом, а не выдуманные комбинации. Для 5 отсутствующих в
   кодовой базе маркеров (Lymphocyte%, MCV, RDW, ALP, WBC) те же самые реальные
   NHANES-строки дают референсные значения "из коробки" — не требуется
   отдельного шага импутации/populational-average (A1 из 12-RESEARCH.md
   становится строго избыточным допущением при таком дизайне: вместо
   "population-reference midpoint" используется полное реальное распределение).

3. КРИТИЧЕСКАЯ находка, исправляющая 12-RESEARCH.md §HF-02 Deep-Dive (задокументирована
   как Rule 1 auto-fix в 12-01-SUMMARY.md): единицы измерения в самой публикации
   Levine 2018 (PMC5940111, Table 1) — Albumin **г/л**, Creatinine **мкмоль/л**,
   Glucose **ммоль/л** (то есть НАПРЯМУЮ единицы NHANES SI-переменных, БЕЗ
   конвертации в г/дл или мг/дл!) — а НЕ "конвенциональные клинические" г/дл/мг/дл,
   как было ошибочно процитировано в исследовательской фазе. Эмпирическая проверка
   подтверждает: конвертация в г/дл/мг/дл перед нелинейной формулой приводит к
   насыщению (все phenotypic_age ≈ 88-111 лет независимо от хронологического
   возраста, корреляция ≈ 0); использование "сырых" NHANES SI-значений напрямую
   даёт физиологически осмысленный результат (корреляция с хронологическим
   возрастом ≈ 0.93, диапазон ≈ 1-111 лет). Перепроверено независимо через
   `biolearn.hematology.phenotypic_age()` (сторонняя реализация той же формулы) —
   оба пути (собственная реализация ниже и biolearn) сходятся с точностью до
   погрешности округления коэффициентов.
   Отдельно исправлена "свёрнутая" форма Gompertz-трансформа M из
   12-RESEARCH.md ("1 − exp(−1.51714 · exp(xb)^0.0076927)") — константа 1.51714
   на самом деле равна (exp(120·γ) − 1), а НЕ показателю степени; корректная
   несвёрнутая форма — `M = 1 − exp(−exp(xb) · (exp(120·γ) − 1) / γ)` (используется
   ниже; совпадает с `biolearn.hematology.phenotypic_age()`).
   ВАЖНО: конвертации в `src/engine/mortality_risk.py::_to_phenoage_units()`
   (г/л→г/дл, мкмоль/л→мг/дл, ммоль/л→мг/дл) этим НЕ затрагиваются и НЕ меняются —
   они относятся к УЖЕ существующей упрощённой линейной формуле кодовой базы,
   калиброванной эмпирически под собственную (внутренне самосогласованную)
   шкалу; этот скрипт лишь пересчитывает интерсепт под референс, не трогая
   PHENOAGE_BETA/PHENOAGE_AGE_COEF/структуру _to_phenoage_units (D-06/D-14).

4. OLS по ОДНОМУ свободному параметру (интерсепт), при фиксированных
   PHENOAGE_BETA/PHENOAGE_AGE_COEF кодовой базы, применённых к тем же реальным
   NHANES-строкам через конвертации, зеркалирующие
   `_to_phenoage_units()` (г/дл/мг/дл-шкала). Для единственного аддитивного
   свободного параметра OLS сводится к замкнутой форме:
       intercept* = mean(reference_age − partial_sum_без_intercept)
   (минимизирует сумму квадратов остатков по определению метода наименьших
   квадратов для константного сдвига).

Ограничение: R² подгонки низкий (остаточное std ≈ 18-19 лет на уровне отдельных
людей) — упрощённая 4-маркерная линейная модель кодовой базы объясняет лишь
часть дисперсии истинной 9-маркерной нелинейной PhenoAge. Это ОЖИДАЕМО и не
является ошибкой скрипта: D-06 требует методологически обоснованный ИНТЕРСЕПТ
(аддитивную поправку), а не полную реконструкцию точности исходной модели —
это прямо признанное в 12-RESEARCH.md ограничение упрощённой архитектуры
(Approach A "Genuine problem"), не устраняемое пересчётом одной константы.
"""

from __future__ import annotations

import sys

try:
    import numpy as np
except ImportError:
    print(
        "ОШИБКА: numpy не установлен в этом calibration-окружении. "
        "См. docstring этого файла — инструкция по установке.",
        file=sys.stderr,
    )
    raise

# ─── Фиксированные константы кодовой базы (src/engine/mortality_risk.py) ─────
# НЕ вычисляются, копируются вручную для сверки — этот скрипт НЕ импортирует
# src/, чтобы оставаться полностью независимым от проектного venv (D-06/D-14:
# BETA/AGE_COEF/_to_phenoage_units НЕ меняются, только PHENOAGE_INTERCEPT_PARTIAL).
PHENOAGE_BETA: dict[str, float] = {
    "albumin": -0.0336,
    "creatinine": 0.0095,
    "glucose": 0.1953,
    "log_hscrp": 0.0954,
}
PHENOAGE_AGE_COEF: float = 0.0804

# ─── Истинная нелинейная формула Levine et al. 2018 (PMC5940111 Table 1) ────
# Единицы — НАПРЯМУЮ единицы NHANES SI-переменных (см. п.3 в докстринге выше):
#   Albumin [г/л], Creatinine [мкмоль/л], Glucose [ммоль/л], CRP [мг/дл, log],
#   Lymphocyte% [%], MCV [фл], RDW [%], ALP [Ед/л], WBC [10^3/мкл], Age [лет].
_LEVINE_INTERCEPT = -19.907
_LEVINE_BETA: dict[str, float] = {
    "albumin": -0.0336,
    "creatinine": 0.0095,
    "glucose": 0.1953,
    "log_crp": 0.0954,
    "lymphocyte_percent": -0.0120,
    "mean_cell_volume": 0.0268,
    "rdw": 0.3306,
    "alkaline_phosphate": 0.00188,
    "wbc": 0.0554,
    "age": 0.0804,
}
_GAMMA = 0.0076927
# Gompertz-трансформ константы обратного преобразования в PhenotypicAge (годы):
_C1, _C2, _C3 = 141.50225, -0.00553, 0.090165


def _true_phenotypic_age(
    albumin_gl: "np.ndarray",
    creatinine_umoll: "np.ndarray",
    glucose_mmoll: "np.ndarray",
    crp_mgdl: "np.ndarray",
    lymphocyte_pct: "np.ndarray",
    mcv_fl: "np.ndarray",
    rdw_pct: "np.ndarray",
    alp_ul: "np.ndarray",
    wbc_10e3ul: "np.ndarray",
    age_years: "np.ndarray",
) -> "np.ndarray":
    """Истинная нелинейная PhenoAge (Levine et al. 2018), векторизованная.

    Все аргументы принимаются в единицах Table 1 публикации PMC5940111 —
    НАПРЯМУЮ единицы NHANES SI-переменных, БЕЗ конвертации в г/дл/мг/дл (см.
    п.3 в докстринге модуля — это исправляет 12-RESEARCH.md).
    """
    xb = (
        _LEVINE_INTERCEPT
        + _LEVINE_BETA["albumin"] * albumin_gl
        + _LEVINE_BETA["creatinine"] * creatinine_umoll
        + _LEVINE_BETA["glucose"] * glucose_mmoll
        + _LEVINE_BETA["log_crp"] * np.log(crp_mgdl)
        + _LEVINE_BETA["lymphocyte_percent"] * lymphocyte_pct
        + _LEVINE_BETA["mean_cell_volume"] * mcv_fl
        + _LEVINE_BETA["rdw"] * rdw_pct
        + _LEVINE_BETA["alkaline_phosphate"] * alp_ul
        + _LEVINE_BETA["wbc"] * wbc_10e3ul
        + _LEVINE_BETA["age"] * age_years
    )
    # Полная (несвёрнутая) форма Gompertz-трансформа мортальности — совпадает с
    # `biolearn.hematology.phenotypic_age()`, см. п.3 докстринга (исправление
    # "свёрнутой" формы 12-RESEARCH.md).
    mortality_score = 1.0 - np.exp(
        -np.exp(xb) * (np.exp(120.0 * _GAMMA) - 1.0) / _GAMMA
    )
    # 1.00001 (не буквальная 1.0) — эпсилон-guard против log(0) при насыщении
    # mortality_score→1.0 для экстремальных строк (float64-underflow exp(очень
    # большое отрицательное число)=0.0 ровно); заимствован дословно из
    # `biolearn.hematology.phenotypic_age()` (независимая сверка, п.3 докстринга) —
    # без него часть выборки даёт -inf вместо конечного потолка.
    return _C1 + np.log(_C2 * np.log(1.00001 - mortality_score)) / _C3


def _codebase_partial_sum(
    albumin_gl: "np.ndarray",
    creatinine_umoll: "np.ndarray",
    glucose_mmoll: "np.ndarray",
    crp_mgdl: "np.ndarray",
    age_years: "np.ndarray",
) -> "np.ndarray":
    """Линейная сумма кодовой базы БЕЗ интерсепта — зеркалирует
    `src/engine/mortality_risk.py::_to_phenoage_units()` + `compute_biological_age()`.

    WR-01 code-review fix (2026-07-19): albumin/creatinine/glucose передаются
    напрямую в SI-единицах Table 1 (г/л, мкмоль/л, ммоль/л) — БЕЗ конвертации в
    г/дл/мг/дл, зеркалируя исправленный `_to_phenoage_units()`. CRP (`crp_mgdl`,
    как и в `_true_phenotypic_age` выше) уже в мг/дл — единицах NHANES
    `c_reactive_protein` — и используется без дополнительной конвертации; это
    зеркалирует РЕЗУЛЬТАТ конвертации приложения (hsCrp мг/л → мг/дл, ÷10),
    а не её вход, поэтому здесь второй ÷10 не нужен (не путать с
    `_to_phenoage_units()`, где вход — сырой мг/л).
    """
    log_hscrp = np.log(np.maximum(0.01, crp_mgdl))
    return (
        PHENOAGE_BETA["albumin"] * albumin_gl
        + PHENOAGE_BETA["creatinine"] * creatinine_umoll
        + PHENOAGE_BETA["glucose"] * glucose_mmoll
        + PHENOAGE_BETA["log_hscrp"] * log_hscrp
        + PHENOAGE_AGE_COEF * age_years
    )


def main() -> float:
    # Windows-консоли с кодовой страницей cp1251/cp866 иначе роняют кириллический
    # вывод в UnicodeEncodeError или молча искажают его — не влияет на корректность
    # вычислений, только на читаемость diagnостических print() ниже.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        from biolearn.load import load_nhanes
    except ImportError:
        print(
            "ОШИБКА: biolearn не установлен в этом calibration-окружении.\n"
            "Этот скрипт НЕ добавляет biolearn в requirements.txt проекта (D-14) —\n"
            "запустите его в отдельном одноразовом venv. См. докстринг модуля.",
            file=sys.stderr,
        )
        raise

    # Реальная выборка NHANES 2010 (единственный доступный в biolearn.load_nhanes
    # цикл, содержащий CRP — 2012 его не публикует, см. biolearn/load.py) — 9
    # маркеров Levine 2018 + возраст, реальные пациенты, без синтетической сетки
    # (обоснование выбора — п.2 докстринга).
    df = load_nhanes(2010)
    required = [
        "age",
        "albumin",
        "creatinine",
        "glucose",
        "c_reactive_protein",
        "lymphocyte_percent",
        "mean_cell_volume",
        "red_blood_cell_distribution_width",
        "alkaline_phosphate",
        "white_blood_cell_count",
    ]
    df = df.dropna(subset=required)
    df = df[df["c_reactive_protein"] > 0]  # log(CRP) требует CRP > 0
    n = len(df)
    print(f"NHANES 2010 cohort: n={n} (age {df['age'].min():.0f}-{df['age'].max():.0f})")

    age = df["age"].to_numpy(dtype=float)
    albumin_gl = df["albumin"].to_numpy(dtype=float)
    creatinine_umoll = df["creatinine"].to_numpy(dtype=float)
    glucose_mmoll = df["glucose"].to_numpy(dtype=float)
    crp_mgdl = df["c_reactive_protein"].to_numpy(dtype=float)
    lymphocyte_pct = df["lymphocyte_percent"].to_numpy(dtype=float)
    mcv_fl = df["mean_cell_volume"].to_numpy(dtype=float)
    rdw_pct = df["red_blood_cell_distribution_width"].to_numpy(dtype=float)
    alp_ul = df["alkaline_phosphate"].to_numpy(dtype=float)
    wbc_10e3ul = df["white_blood_cell_count"].to_numpy(dtype=float)

    reference_age = _true_phenotypic_age(
        albumin_gl,
        creatinine_umoll,
        glucose_mmoll,
        crp_mgdl,
        lymphocyte_pct,
        mcv_fl,
        rdw_pct,
        alp_ul,
        wbc_10e3ul,
        age,
    )
    corr = float(np.corrcoef(age, reference_age)[0, 1])
    print(
        f"Референсный (истинный нелинейный) PhenoAge: "
        f"min={reference_age.min():.1f} mean={reference_age.mean():.1f} "
        f"max={reference_age.max():.1f}, corr(age)={corr:.3f}"
    )

    partial = _codebase_partial_sum(
        albumin_gl, creatinine_umoll, glucose_mmoll, crp_mgdl, age
    )
    resid = reference_age - partial
    intercept = float(resid.mean())
    print(
        f"Партиальная сумма кодовой базы (без интерсепта): "
        f"min={partial.min():.1f} mean={partial.mean():.1f} max={partial.max():.1f}"
    )
    print(f"Остаточное std (диагностика fit-качества): {resid.std():.2f} лет")
    print(f"n использовано для OLS-подгонки интерсепта: {n}")
    print("=== RESULT ===")
    print(f"PHENOAGE_INTERCEPT_PARTIAL = {intercept!r}")
    return intercept


if __name__ == "__main__":
    main()
