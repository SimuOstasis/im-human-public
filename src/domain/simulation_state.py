# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""SimulationState FSM — controlled lifecycle state machine for simulation runs."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SimulationStatus(str, Enum):
    """Simulation lifecycle statuses."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


# Таблица допустимых переходов
_ALLOWED_TRANSITIONS: dict[SimulationStatus, set[SimulationStatus]] = {
    SimulationStatus.IDLE:    {SimulationStatus.RUNNING},
    SimulationStatus.RUNNING: {SimulationStatus.PAUSED, SimulationStatus.STOPPED},
    SimulationStatus.PAUSED:  {SimulationStatus.RUNNING},
    SimulationStatus.STOPPED: set(),  # терминальное состояние
}


class SimulationEvent(BaseModel):
    """Событие симуляции — пороговое или вероятностное.

    Создаётся engine-модулями и хранится в SimulationState.events (append-only).
    Severity CRITICAL автоматически паузирует движок (D-15).
    """
    tick: int
    event_type: str   # "THRESHOLD_BREACH" | "PROBABILISTIC"
    biomarker: str | None = None
    value: float | None = None
    message: str
    severity: str     # "INFO" | "WARNING" | "CRITICAL"


class SimulationState(BaseModel):
    """FSM representing the lifecycle of a single simulation run.

    Поля статуса/идентификатора (Phase 3) + расширение D-16 (Phase 5):
    tick_count, current_time_hours, biomarker_values, substance_concentrations,
    substance_cmax, events, biological_age, resilience_index, rng_state.
    """
    model_config = ConfigDict(frozen=False)  # transition() mutates self.status (WR-03)

    # Исходные поля Phase 3 (D-04)
    status: SimulationStatus = SimulationStatus.IDLE
    profile_id: str
    seed: int = Field(ge=0)

    # Расширение D-16 (Phase 5)
    tick_count: int = 0
    current_time_hours: float = 0.0
    biomarker_values: dict[str, float] = Field(default_factory=dict)
    substance_concentrations: dict[str, float] = Field(default_factory=dict)
    substance_cmax: dict[str, float] = Field(default_factory=dict)  # Cmax для масштабирования D-04
    events: list[SimulationEvent] = Field(default_factory=list)
    biological_age: float | None = None
    resilience_index: float | None = None
    rng_state: tuple | None = None  # состояние RNG для паузы/возобновления (Area 8)

    def transition(self, new_status: SimulationStatus) -> None:
        """Execute FSM transition. Raises ValueError on invalid transition."""
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status.value} -> {new_status.value}. "
                f"Allowed from {self.status.value}: {[s.value for s in allowed]}"
            )
        self.status = new_status
