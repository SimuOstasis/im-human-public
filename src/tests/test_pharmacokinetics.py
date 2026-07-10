# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Тесты фармакокинетики (ENG-02, ENG-09).

Wave 1: все тесты активированы после реализации pharmacokinetics.py (Plan 05-02).
"""

import json
import math
from pathlib import Path

import pytest

from src.engine.pharmacokinetics import (
    PKEngine,
    compute_cmax_increment,
    compute_decay,
)

VAULT_ROOT = Path(__file__).parent.parent.parent

# Загрузить substances.json один раз на уровне модуля
SUBSTANCES: list[dict] = json.loads(
    (VAULT_ROOT / "src/data/substances.json").read_text(encoding="utf-8")
)


def test_half_life_decay():
    """Через T½ часов концентрация должна упасть ровно вдвое.

    Проверяет формулу C_new = C_old * exp(-ke * delta_t),
    где ke = ln(2) / half_life_hours.
    При delta_t = half_life_hours -> C_new == C_old / 2 (точность 1e-9 по rel_tol).
    """
    C0 = 10.0
    half_life = 6.2   # metformin halfLifeHours
    ke = PKEngine.compute_ke(half_life)
    C_after = compute_decay(C0, ke, delta_t=half_life)
    assert math.isclose(C_after, C0 / 2, rel_tol=1e-9)


@pytest.mark.parametrize("substance", SUBSTANCES, ids=[s["id"] for s in SUBSTANCES])
def test_cmax_positive(substance: dict):
    """Cmax_increment всегда положительный и конечный при валидных параметрах.

    Формула: Cmax = dose_mg * bioavailability / (Vd_l_kg * weight_kg).
    Параметризован по всем 7 веществам из substances.json.
    """
    dose_native = substance["defaultDose"]
    conversion = substance.get("dose_conversion_to_mg", 1.0)
    dose_mg = dose_native * conversion
    bioavailability = substance["bioavailability"]
    vd = substance["volume_of_distribution_l_kg"]
    weight_kg = 70.0

    cmax = compute_cmax_increment(dose_mg, bioavailability, vd, weight_kg)
    assert math.isfinite(cmax), f"{substance['id']}: cmax is not finite: {cmax}"
    assert cmax > 0, f"{substance['id']}: cmax <= 0: {cmax}"


@pytest.mark.parametrize("substance", SUBSTANCES, ids=[s["id"] for s in SUBSTANCES])
def test_no_nan_after_8760_ticks(substance: dict):
    """8760 тиков decay не должны производить NaN для любого вещества.

    Критично для воспроизводимости: после 1 года (8760 ч) концентрация
    должна быть >= 0 и конечной (не NaN, не inf).
    Параметризован по всем 7 веществам.
    """
    C = 5.0
    ke = PKEngine.compute_ke(substance["halfLifeHours"])
    for _ in range(8760):
        C = compute_decay(C, ke)
    assert not math.isnan(C), f"{substance['id']}: C is NaN after 8760 ticks"
    assert C >= 0.0, f"{substance['id']}: C < 0 after 8760 ticks: {C}"
    assert math.isfinite(C), f"{substance['id']}: C is not finite after 8760 ticks: {C}"


def test_bounds_stay_nonnegative():
    """Концентрация никогда не уходит в отрицательную область.

    При любом количестве тиков с нулевой дозой C(t) -> 0 (но не < 0).
    Проверяем с начальным C=1e-300 (очень малое число) и ke=log(2)/1.0
    (короткий T½ для быстрой проверки).
    """
    C = 1e-300
    ke = PKEngine.compute_ke(1.0)  # короткий T½ = 1 час
    for _ in range(1000):
        C = compute_decay(C, ke)
        assert C >= 0.0, f"Концентрация отрицательная: {C}"


def test_vitamin_d3_no_nan():
    """Витамин D3 (IU -> мг конвертация) не производит NaN за 8760 тиков.

    Критичный крайний случай: dose_conversion_to_mg=0.000025 даёт очень
    маленький Cmax (~0.0005 мг/л). Проверяем, что масштабирование C/Cmax
    корректно и эффекты не взрываются в NaN/inf.
    """
    dose_iu = 2000.0
    dose_mg = dose_iu * 0.000025  # конвертация IU -> мг: 1 IU = 0.025 мкг = 0.000025 мг
    cmax = compute_cmax_increment(dose_mg, bioavailability=0.70, vd_l_kg=1.0, weight_kg=70.0)
    assert cmax > 0, f"cmax <= 0: {cmax}"
    assert math.isfinite(cmax), f"cmax is not finite: {cmax}"

    C = cmax
    ke = PKEngine.compute_ke(720.0)  # halfLifeHours vitamin_d3
    for _ in range(8760):
        C = compute_decay(C, ke)
        ratio = C / cmax if cmax > 0 else 0.0
        assert math.isfinite(ratio), f"ratio стал нефинитным: C={C}, cmax={cmax}"
    assert not math.isnan(C), f"C is NaN after 8760 ticks"
    assert C >= 0, f"C < 0 after 8760 ticks: {C}"
