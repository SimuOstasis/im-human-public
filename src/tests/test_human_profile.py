# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

# Источник: паттерн test_data_layer.py (существующий)
import json
import math
from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


# ─── PROF-01: Import ─────────────────────────────────────────────────────────

def test_import():
    from src.domain.human_profile import HumanProfile
    assert HumanProfile is not None


# ─── PROF-03: units.py ───────────────────────────────────────────────────────

def test_unit_conversions():
    from src.domain.units import kg_to_lbs, lbs_to_kg, cm_to_inches, inches_to_cm
    assert abs(kg_to_lbs(75.0) - 165.35) < 0.01
    assert abs(lbs_to_kg(165.35) - 75.0) < 0.01
    assert abs(cm_to_inches(178.0) - 70.08) < 0.01
    assert abs(inches_to_cm(70.08) - 178.0) < 0.1


# ─── PROF-04: FSM ────────────────────────────────────────────────────────────

def test_fsm_valid_transitions():
    from src.domain.simulation_state import SimulationState, SimulationStatus
    state = SimulationState(profile_id="test", seed=42)
    assert state.status == SimulationStatus.IDLE
    state.transition(SimulationStatus.RUNNING)
    assert state.status == SimulationStatus.RUNNING
    state.transition(SimulationStatus.PAUSED)
    assert state.status == SimulationStatus.PAUSED
    state.transition(SimulationStatus.RUNNING)
    assert state.status == SimulationStatus.RUNNING
    state.transition(SimulationStatus.STOPPED)
    assert state.status == SimulationStatus.STOPPED


def test_fsm_invalid_transitions():
    from src.domain.simulation_state import SimulationState, SimulationStatus
    state = SimulationState(profile_id="test", seed=42)
    with pytest.raises(ValueError):
        state.transition(SimulationStatus.STOPPED)  # IDLE → STOPPED запрещено
    state.transition(SimulationStatus.RUNNING)
    with pytest.raises(ValueError):
        state.transition(SimulationStatus.IDLE)  # RUNNING → IDLE запрещено


# ─── PROF-05: BMI / BMR / TDEE ───────────────────────────────────────────────

def test_bmi_male():
    from src.domain.human_profile import HumanProfile
    profile = HumanProfile.from_preset("young_healthy_30m")
    assert abs(profile.bmi - 23.67) < 0.1


def test_bmr_male():
    from src.domain.human_profile import HumanProfile
    profile = HumanProfile.from_preset("young_healthy_30m")
    # Male 30 178cm 75kg: 10*75 + 6.25*178 - 5*30 + 5 = 1717.5
    assert abs(profile.bmr - 1717.5) < 1.0


def test_bmr_female():
    from src.domain.human_profile import HumanProfile
    profile = HumanProfile.from_preset("middle_age_50f")
    # Female 50 165cm 70kg: 10*70 + 6.25*165 - 5*50 - 161 = 1320.25
    assert abs(profile.bmr - 1320.25) < 1.0


def test_tdee():
    from src.domain.human_profile import HumanProfile
    profile = HumanProfile.from_preset("young_healthy_30m")
    expected_tdee = profile.bmr * 1.55  # moderate
    assert abs(profile.tdee - expected_tdee) < 1.0


# ─── PROF-07: Пресеты ────────────────────────────────────────────────────────

def test_preset_young():
    from src.domain.human_profile import HumanProfile
    p = HumanProfile.from_preset("young_healthy_30m")
    assert p.demographics.age == 30
    assert p.demographics.sex.value == "male"


def test_preset_middle():
    from src.domain.human_profile import HumanProfile
    p = HumanProfile.from_preset("middle_age_50f")
    assert p.demographics.age == 50
    assert p.demographics.sex.value == "female"


def test_preset_elderly():
    from src.domain.human_profile import HumanProfile
    p = HumanProfile.from_preset("elderly_70m")
    assert p.demographics.age == 70
    assert p.demographics.sex.value == "male"


def test_preset_unknown():
    from src.domain.human_profile import HumanProfile
    with pytest.raises(KeyError):
        HumanProfile.from_preset("nonexistent_preset")


# ─── PROF-02: Sub-models ─────────────────────────────────────────────────────

def test_submodels():
    from src.domain.human_profile import HumanProfile
    profile = HumanProfile.from_preset("young_healthy_30m")
    assert hasattr(profile, "demographics")
    assert hasattr(profile, "physiology")
    assert hasattr(profile, "lifestyle")
    assert hasattr(profile, "predispositions")
    assert hasattr(profile, "organ_systems")


# ─── PROF-08: Wiki-страницы ───────────────────────────────────────────────────

def test_wiki_pages_exist():
    profiles_dir = VAULT_ROOT / "01 - Human Profiles"
    if not profiles_dir.exists():
        pytest.skip("01 - Human Profiles/ not present — run generate_profile_pages.py first")
    expected = ["Young Healthy 30M.md", "Middle Age 50F.md", "Elderly 70M.md"]
    for fname in expected:
        path = profiles_dir / fname
        assert path.exists(), f"Wiki page not found: {path}"
