# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Тесты системы взаимодействий веществ (ENG-04, ENG-11).

Активированы в Plan 05-03: interaction_resolver.py реализован.
Тестируют модульные функции apply_synergy, apply_antagonism, check_self_toxicity.
"""

from pathlib import Path
import json

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


def test_synergy_amplifies_effect():
    """Синергия omega3+vitamin_d3 усиливает эффект на общие биомаркеры на 30%.

    Проверяет ENG-04/ENG-11: применение synergy коэффициента 1.3.
    Формула: result = base_delta * coeff при overlap_factor=1.0 (100% обоих).
    При 100% концентрации обоих: apply_synergy(base, 1.3, c, c, c, c) = base * 1.3.
    """
    from src.engine.interaction_resolver import apply_synergy

    base_delta = -0.001  # hsCrp дельта от omega3
    coeff = 1.3          # из interactions.json (omega3 + vitamin_d3)
    c_a, cmax_a = 1.0, 1.0    # 100% концентрация omega3
    c_b, cmax_b = 1.0, 1.0    # 100% концентрация vitamin_d3

    result = apply_synergy(base_delta, coeff, c_a, cmax_a, c_b, cmax_b)

    # При 100% обоих: overlap_factor=1.0, result = base_delta + base_delta*(1.3-1.0)*1.0
    #               = base_delta * 1.3
    expected = base_delta * 1.3
    assert abs(result - expected) < 1e-9, (
        f"Синергия 1.3 при 100%/100%: ожидалось {expected:.6f}, получено {result:.6f}"
    )


def test_antagonism_dampens_effect():
    """Антагонизм metformin+rapamycin снижает эффект metformin на 30%.

    Проверяет ENG-04/ENG-11: применение antagonism коэффициента 0.7.
    Формула: result = base_delta * (1.0 - (1.0 - coeff) * c_antagonist/cmax_antagonist).
    При 100% антагониста: result = base_delta * 0.7.
    """
    from src.engine.interaction_resolver import apply_antagonism

    base_delta = -0.010  # fastingGlucose дельта от metformin
    coeff = 0.7          # из interactions.json (metformin + rapamycin)
    c_antagonist = 1.0
    cmax_antagonist = 1.0  # 100% rapamycin

    result = apply_antagonism(base_delta, coeff, c_antagonist, cmax_antagonist)

    expected = base_delta * 0.7
    assert abs(result - expected) < 1e-9, (
        f"Антагонизм 0.7 при 100%: ожидалось {expected:.6f}, получено {result:.6f}"
    )


def test_toxicity_triggers_critical_flag():
    """Rapamycin при C > 200% Cmax генерирует SimulationEvent с severity=CRITICAL.

    Проверяет ENG-11: check_self_toxicity() возвращает CRITICAL событие.
    Данные из interactions.json: rapamycin self-toxicity.
    Порог: C_current >= Cmax * 2.0 (TOXICITY_MULTIPLIER).
    """
    from src.engine.interaction_resolver import check_self_toxicity

    interactions_path = VAULT_ROOT / "src" / "data" / "interactions.json"
    interactions = json.loads(interactions_path.read_text(encoding="utf-8"))

    # rapamycin при 250% Cmax (выше порога 200%)
    cmax = 1.0
    c_toxic = cmax * 2.5

    event = check_self_toxicity("rapamycin", c_toxic, cmax, interactions)

    assert event is not None, "Ожидалось CRITICAL событие при C > 200% Cmax"
    assert event.severity == "CRITICAL", f"severity должен быть CRITICAL, получено: {event.severity}"
    assert event.event_type == "THRESHOLD_BREACH", f"event_type: {event.event_type}"

    # Дополнительная проверка: при C < 2*Cmax событие не возникает
    c_safe = cmax * 1.5  # 150% — ниже порога 200%
    event_safe = check_self_toxicity("rapamycin", c_safe, cmax, interactions)
    assert event_safe is None, f"При C=150% Cmax событие не должно быть (получено: {event_safe})"
