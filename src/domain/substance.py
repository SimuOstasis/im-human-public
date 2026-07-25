# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""SubstanceDefinition, IntakeSchedule, CycleConfig — core domain models for M3.

Pydantic v2 models for substances and intake schedules.

Decisions honored:
  D-02: SubstanceCategory enum (supplement / drug)
  D-03: is_drug derived from category via model_validator(mode="after")
  D-05: SubstanceDefinition.from_json = cls.model_validate(data)
  D-06: field_validator on dose_mg enforces min_dose <= dose_mg <= max_dose
  D-07: IntakeSchedule with 7 public fields (substance_id, dose_mg, interval_hours,
         hour_of_day, cycle, start_tick, duration_ticks) + helper fields min/max_dose
  D-08: CycleConfig(on_days, off_days) — e.g. Rapamycin CycleConfig(on_days=1, off_days=6)
  D-09: effectProfile values are per-tick deltas in biomarker units at 100% concentration
  D-10: engine (Phase 5) scales delta by C(t)/Tmax
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class SubstanceCategory(str, Enum):
    """Substance classification for regulatory and disclaimer logic (D-02)."""

    supplement = "supplement"
    drug = "drug"


# ─── CycleConfig (D-08) ───────────────────────────────────────────────────────

class CycleConfig(BaseModel):
    """On/off cycling protocol for substances taken intermittently.

    Example: Rapamycin once-per-week = CycleConfig(on_days=1, off_days=6).
    None on IntakeSchedule.cycle means continuous intake.
    """

    on_days: int = Field(ge=1, description="Consecutive days the substance is taken")
    off_days: int = Field(ge=0, description="Consecutive days the substance is withheld")


# ─── SubstanceDefinition (D-05) ───────────────────────────────────────────────

class SubstanceDefinition(BaseModel):
    """Core domain model for a substance or intervention.

    JSON keys are camelCase (from substances.json / ingest_substances.py schema).
    Python attributes are snake_case. Both work via populate_by_name=True.

    Fields follow the ingest_substances.py schema exactly:
      id, name, name_ru, category, doseUnit, minDose, maxDose,
      defaultDose, bioavailability, halfLifeHours, effectProfile, targetSystems,
      absorptionRate, eliminationRate, accumulationThreshold.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    name_ru: str = ""
    category: SubstanceCategory
    dose_unit: str = Field(alias="doseUnit")
    min_dose: float = Field(alias="minDose", ge=0)
    max_dose: float = Field(alias="maxDose", gt=0)
    default_dose: float = Field(alias="defaultDose", ge=0)
    bioavailability: float = Field(ge=0.0, le=1.0)
    half_life_hours: float = Field(alias="halfLifeHours", gt=0)
    absorption_rate: float = Field(alias="absorptionRate", default=0.1, ge=0)
    elimination_rate: float = Field(alias="eliminationRate", default=0.1, ge=0)
    accumulation_threshold: float = Field(alias="accumulationThreshold", default=0.0, ge=0)
    effect_profile: dict[str, float] = Field(alias="effectProfile", default_factory=dict)
    target_systems: list[str] = Field(alias="targetSystems", default_factory=list)

    # Derived field — set by model_validator(mode="after") based on category (D-03)
    is_drug: bool = False

    @model_validator(mode="after")
    def _set_is_drug(self) -> "SubstanceDefinition":
        """Derive is_drug from category after all fields are validated (D-03)."""
        self.is_drug = self.category == SubstanceCategory.drug
        return self

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SubstanceDefinition":
        """Parse a substance dict (camelCase JSON) into a SubstanceDefinition (D-05).

        Args:
            data: Raw dict from substances.json or similar source.

        Returns:
            Validated SubstanceDefinition instance.

        Raises:
            pydantic.ValidationError: If required fields are missing or invalid.
        """
        return cls.model_validate(data)


# ─── IntakeSchedule (D-06, D-07) ──────────────────────────────────────────────

class IntakeSchedule(BaseModel):
    """Defines when and how a substance is taken.

    Public contract (D-07): 7 fields —
      substance_id, dose_mg, interval_hours, hour_of_day, cycle,
      start_tick, duration_ticks.

    Helper fields min_dose / max_dose enable the field_validator (D-06) to
    enforce therapeutic dose bounds at construction time, before the engine
    ever sees the schedule.

    IMPORTANT — field declaration order:
      min_dose and max_dose are declared BEFORE dose_mg so that info.data
      contains them when the dose_mg field_validator runs (Pydantic v2 behaviour).
    """

    substance_id: str

    # ── Dose bounds (declared before dose_mg so validator sees them in info.data) ──
    min_dose: float = Field(default=0.0, ge=0, description="Minimum therapeutic dose (mg)")
    max_dose: float = Field(default=float("inf"), gt=0, description="Maximum safe dose (mg)")

    # ── Dose (D-06) ─────────────────────────────────────────────────────────────
    dose_mg: float = Field(gt=0, description="Dose in mg per intake event")

    @field_validator("dose_mg", mode="after")
    @classmethod
    def _validate_dose_range(cls, v: float, info: Any) -> float:
        """Enforce min_dose <= dose_mg <= max_dose (D-06, T-04-02 mitigate).

        Uses info.data which contains already-validated peer fields.
        min_dose and max_dose are declared before dose_mg to guarantee presence.
        """
        data = info.data
        min_d = data.get("min_dose", 0.0)
        max_d = data.get("max_dose", float("inf"))
        if v < min_d or v > max_d:
            raise ValueError(
                f"dose_mg {v} outside therapeutic range [{min_d}, {max_d}]"
            )
        return v

    # ── D-07 schedule fields ─────────────────────────────────────────────────
    interval_hours: float = Field(default=24.0, gt=0, description="Hours between doses")
    hour_of_day: int = Field(default=0, ge=0, le=23, description="Hour of simulation tick (0-23)")
    cycle: CycleConfig | None = Field(default=None, description="Optional on/off cycle (D-08)")
    start_tick: int = Field(default=0, ge=0, description="Simulation tick to begin intake")
    duration_ticks: int | None = Field(
        default=None,
        description="Total ticks to apply schedule (None = indefinite)",
    )
