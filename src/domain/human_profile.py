# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""HumanProfile — core domain model for im-human simulator.

Pydantic v2 nested model with 5 sub-models, computed properties (bmi/bmr/tdee),
and a class method to load preset profiles from src/data/presets.json.

Decisions honored:
  D-01: nested sub-models (not flat)
  D-02: OrganSystems has exactly 7 systems
  D-03: Predispositions has exactly 5 risks
  D-06: Mifflin-St Jeor BMR, sex-branched (+5 male / -161 female)
  D-07: PhysicalActivity Enum with multiplier property
  D-08: no biomarker dict (engine computes dynamically in Phase 5)
  D-09: from_preset classmethod reads presets.json
"""
from __future__ import annotations

from enum import Enum
import json
from pathlib import Path

from pydantic import BaseModel, Field

# ─── Paths ───────────────────────────────────────────────────────────────────
# src/domain/human_profile.py is 3 levels below vault root
VAULT_ROOT = Path(__file__).parent.parent.parent
PRESETS_FILE = VAULT_ROOT / "src" / "data" / "presets.json"


# ─── Enums ───────────────────────────────────────────────────────────────────

class Sex(str, Enum):
    male = "male"
    female = "female"
    unspecified = "unspecified"


class MethylationRate(str, Enum):
    slow = "slow"
    normal = "normal"
    fast = "fast"


class AutophagyEfficiency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class SmokingStatus(str, Enum):
    none = "none"
    former = "former"
    active = "active"


class PhysicalActivity(str, Enum):
    """Activity level with TDEE multiplier (D-07)."""

    sedentary = "sedentary"   # 1.2
    low = "low"               # 1.375
    moderate = "moderate"     # 1.55
    high = "high"             # 1.725
    athlete = "athlete"       # 1.9

    @property
    def multiplier(self) -> float:
        """Return Harris–Benedict activity factor for TDEE calculation."""
        _MULTIPLIERS = {
            "sedentary": 1.2,
            "low": 1.375,
            "moderate": 1.55,
            "high": 1.725,
            "athlete": 1.9,
        }
        return _MULTIPLIERS[self.value]


# ─── Nested sub-models (D-01) ─────────────────────────────────────────────────

class Demographics(BaseModel):
    """Anthropometric and demographic identifiers."""

    sex: Sex
    age: int = Field(ge=1, le=120)
    height_cm: float = Field(ge=50.0, le=250.0)
    weight_kg: float = Field(ge=20.0, le=300.0)


class Physiology(BaseModel):
    """Physiological baseline coefficients."""

    body_fat_pct: float = Field(ge=2.0, le=60.0)
    metabolic_rate_coef: float = Field(ge=0.5, le=1.5, default=1.0)
    methylation: MethylationRate = MethylationRate.normal
    autophagy_efficiency: AutophagyEfficiency = AutophagyEfficiency.normal


class Lifestyle(BaseModel):
    """Behavioural lifestyle factors (0–100 integer scales)."""

    stress: int = Field(ge=0, le=100)
    sleep_quality: int = Field(ge=0, le=100)
    physical_activity: PhysicalActivity = PhysicalActivity.moderate
    diet_quality: int = Field(ge=0, le=100)
    alcohol: int = Field(ge=0, le=100)
    smoking: SmokingStatus = SmokingStatus.none


class Predispositions(BaseModel):
    """Genetic/familial risk predispositions (D-03).
    Each field is a probability 0.0 (no risk) – 1.0 (maximum risk).
    Exactly 5 risk factors.
    """

    cardiovascular_risk: float = Field(ge=0.0, le=1.0)
    diabetes_risk: float = Field(ge=0.0, le=1.0)
    neurodegeneration_risk: float = Field(ge=0.0, le=1.0)
    liver_disease_risk: float = Field(ge=0.0, le=1.0)
    kidney_disease_risk: float = Field(ge=0.0, le=1.0)


class OrganSystems(BaseModel):
    """Organ system health scores (D-02).
    Each field: 0.0 = total failure, 1.0 = perfect health.
    Exactly 7 systems.
    """

    cardiovascular: float = Field(ge=0.0, le=1.0)
    liver: float = Field(ge=0.0, le=1.0)
    kidney: float = Field(ge=0.0, le=1.0)
    nervous: float = Field(ge=0.0, le=1.0)
    immune: float = Field(ge=0.0, le=1.0)
    metabolic: float = Field(ge=0.0, le=1.0)
    cellular_repair: float = Field(ge=0.0, le=1.0)


# ─── Root model (D-01) ────────────────────────────────────────────────────────

class HumanProfile(BaseModel):
    """Central domain model — biological profile of a human for simulation.

    NOT flat: all sub-domains are accessed via nested sub-models.
    Does NOT store biomarker baseline dict (D-08) — engine computes dynamically.
    """

    profile_id: str
    display_name: str
    demographics: Demographics
    physiology: Physiology
    lifestyle: Lifestyle
    predispositions: Predispositions
    organ_systems: OrganSystems

    # ─── Computed properties (D-05, D-06, D-07) ──────────────────────────────

    @property
    def bmi(self) -> float:
        """Body Mass Index = weight_kg / height_m^2, rounded to 2 decimal places."""
        h_m = self.demographics.height_cm / 100.0
        return round(self.demographics.weight_kg / (h_m ** 2), 2)

    @property
    def bmr(self) -> float:
        """Mifflin-St Jeor Basal Metabolic Rate (kcal/day), sex-branched (D-06).

        Male:   10*weight_kg + 6.25*height_cm - 5*age + 5
        Female: 10*weight_kg + 6.25*height_cm - 5*age - 161
        """
        w = self.demographics.weight_kg
        h = self.demographics.height_cm
        a = self.demographics.age
        base = 10.0 * w + 6.25 * h - 5.0 * a
        if self.demographics.sex == Sex.male:
            return round(base + 5.0, 1)
        elif self.demographics.sex == Sex.female:
            return round(base - 161.0, 1)
        else:
            # Sex.unspecified: average of male/female constants (5 + (-161)) / 2 = -78
            return round(base - 78.0, 1)

    @property
    def tdee(self) -> float:
        """Total Daily Energy Expenditure = BMR x physical activity multiplier (D-07)."""
        return round(self.bmr * self.lifestyle.physical_activity.multiplier, 1)

    # ─── Factory method (D-09) ────────────────────────────────────────────────

    @classmethod
    def from_preset(cls, preset_id: str) -> "HumanProfile":
        """Load a preset profile from src/data/presets.json.

        Args:
            preset_id: One of 'young_healthy_30m', 'middle_age_50f', 'elderly_70m'.

        Raises:
            FileNotFoundError: If presets.json does not exist at PRESETS_FILE.
            KeyError: If preset_id is not found in presets.json.

        Returns:
            A fully validated HumanProfile instance.
        """
        if not PRESETS_FILE.exists():
            raise FileNotFoundError(
                f"presets.json not found at: {PRESETS_FILE}"
            )
        with PRESETS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        presets = {p["profile_id"]: p for p in data.get("presets", [])}
        if preset_id not in presets:
            available = list(presets.keys())
            raise KeyError(
                f"Unknown preset '{preset_id}'. Available presets: {available}"
            )
        return cls.model_validate(presets[preset_id])
