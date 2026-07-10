# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""SimulationEngine — главный 13-шаговый оркестратор тика симуляции (ENG-07).

Интегрирует PK, Homeostasis, Interactions, EventDetector, MortalityRisk
в один детерминированный тиковый цикл (1 тик = 1 час).

Запрещено внутри tick(): file I/O, создание BaseModel-объектов кроме SimulationEvent.

Угрозы:
  T-05-12: tick() при status≠RUNNING → ValueError
  T-05-13: rng_state сохраняется после каждого тика (шаг 13)
  T-05-14: biological_age в логах — локальные данные, сеть не используется
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from src.engine.rng import SimulationRNG
from src.engine.pharmacokinetics import PKEngine
from src.engine.homeostasis import HomeostasisEngine
from src.engine.interaction_resolver import InteractionResolver
from src.engine.event_detector import EventDetector
from src.engine.adaptive_stepper import AdaptiveStepper
from src.engine.mortality_risk import MortalityRiskEngine
from src.domain.simulation_state import SimulationState, SimulationStatus
from src.domain.human_profile import HumanProfile

VAULT_ROOT = Path(__file__).parent.parent.parent

# Максимально безопасные значения биомаркеров (D-08 clamp)
MAX_SAFE_VALUES: dict[str, float] = {
    "ldlC": 20.0,
    "hdlC": 10.0,
    "triglycerides": 30.0,
    "apob": 5.0,
    "fastingGlucose": 50.0,
    "fastingInsulin": 500.0,
    "homaIr": 50.0,
    "hba1c": 20.0,
    "hsCrp": 100.0,
    "il6": 500.0,
    "alt": 1000.0,
    "ast": 1000.0,
    "ggt": 1000.0,
    "albumin": 80.0,
    "creatinine": 1000.0,
    "egfr": 200.0,
    "uacr": 10000.0,
    "sodium": 200.0,
    "potassium": 10.0,
    "vitaminD25Oh": 500.0,
    "hemoglobin": 250.0,
    "systolicBloodPressure": 300.0,
    "hrvRmssd": 200.0,
}


class SimulationEngine:
    """Главный движок симуляции — интегрирует все субмодули в тиковый цикл.

    Принимает HumanProfile и seed. Данные веществ/взаимодействий/диапазонов
    загружаются из src/data/ при инициализации, если не переданы явно.

    Attributes:
        profile: Профиль человека.
        seed: Начальный seed для RNG.
        rng: Детерминированный генератор случайных чисел.
        pk: Фармакокинетический движок.
        homeostasis: Движок гомеостаза.
        interaction_resolver: Резолвер взаимодействий веществ.
        event_detector: Детектор пороговых и вероятностных событий.
        mortality_risk: Движок биологического возраста.
        baseline_biomarkers: Исходные значения биомаркеров (вычисляются при init).
    """

    def __init__(
        self,
        profile: HumanProfile,
        seed: int = 42,
        substances_data: list[dict] | None = None,
        interactions_data: list[dict] | None = None,
        reference_ranges: dict | None = None,
    ) -> None:
        """Инициализировать движок.

        Args:
            profile: Профиль человека.
            seed: Seed для RNG (ENG-01 детерминизм).
            substances_data: Список веществ из substances.json (загружается если None).
            interactions_data: Список взаимодействий из interactions.json (загружается если None).
            reference_ranges: Справочник диапазонов из reference_ranges.json (загружается если None).
        """
        self.profile = profile
        self.seed = seed

        if substances_data is None:
            substances_data = json.loads(
                (VAULT_ROOT / "src" / "data" / "substances.json").read_text(encoding="utf-8")
            )
        if interactions_data is None:
            interactions_data = json.loads(
                (VAULT_ROOT / "src" / "data" / "interactions.json").read_text(encoding="utf-8")
            )
        if reference_ranges is None:
            reference_ranges = json.loads(
                (VAULT_ROOT / "src" / "data" / "reference_ranges.json").read_text(encoding="utf-8")
            )

        self.substances: dict[str, dict] = {s["id"]: s for s in substances_data}
        self.reference_ranges = reference_ranges

        # Инициализация субмодулей
        self.rng = SimulationRNG(seed)
        self.pk = PKEngine(substances_data)
        self.homeostasis = HomeostasisEngine(reference_ranges)
        self.interaction_resolver = InteractionResolver(interactions_data, substances_data)
        self.event_detector = EventDetector(reference_ranges)
        self.mortality_risk = MortalityRiskEngine()

        # Baseline вычисляется один раз при инициализации (производительность)
        self.baseline_biomarkers: dict[str, float] = self.homeostasis.initialize_biomarkers(profile)

    def initialize(self) -> SimulationState:
        """Создать начальное состояние симуляции.

        Returns:
            SimulationState в статусе RUNNING с baseline биомаркерами.
        """
        state = SimulationState(profile_id=self.profile.profile_id, seed=self.seed)
        state.transition(SimulationStatus.RUNNING)
        state.biomarker_values = dict(self.baseline_biomarkers)
        state.substance_concentrations = {}
        state.substance_cmax = {}
        state.events = []
        state.tick_count = 0
        state.current_time_hours = 0.0
        # WR-06: вычислить resilience и biological_age сразу по baseline,
        # чтобы первый тик использовал реальные значения, а не 1.0/None.
        state.resilience_index = self.mortality_risk.compute_resilience(state.biomarker_values)
        state.biological_age = self.mortality_risk.compute_biological_age(
            state.biomarker_values, self.profile.demographics.age
        )
        state.rng_state = self.rng.get_state()
        return state

    def initialize_state(self) -> SimulationState:
        """Псевдоним initialize() для обратной совместимости."""
        return self.initialize()

    def tick(self, state: SimulationState, schedules: list) -> SimulationState:
        """Выполнить один тик симуляции (13 шагов, 1 тик = 1 час).

        Нет file I/O. Нет создания BaseModel кроме SimulationEvent при реальных событиях.

        Args:
            state: Текущее состояние (FSM RUNNING).
            schedules: Список IntakeSchedule (или duck-typed объектов).

        Returns:
            Обновлённый SimulationState.

        Raises:
            ValueError: Если state.status не RUNNING (T-05-12).
        """
        if state.status != SimulationStatus.RUNNING:
            raise ValueError(
                f"Cannot tick non-RUNNING state: {state.status.value}"
            )

        # Восстановить RNG state для детерминизма при pause/resume
        if state.rng_state is not None:
            self.rng.set_state(state.rng_state)

        # Шаг 1: Приращение времени
        state.tick_count += 1
        state.current_time_hours += 1.0
        state.events = []  # Reset per-tick: EventLog.add_events uses _seen_count for dedup

        # Шаг 2: Применение доз по расписанию
        # WR-07: tick_count уже увеличен; для 0-индексированного расписания
        # используем (tick_count - 1), чтобы тик 0 = первый час (0:00).
        dose_tick = state.tick_count - 1
        for schedule in schedules:
            if AdaptiveStepper.should_dose(schedule, dose_tick):
                sub = self.substances.get(schedule.substance_id)
                if sub is None:
                    continue
                conversion = sub.get("dose_conversion_to_mg", 1.0)
                dose_mg = schedule.dose_mg * conversion
                increment = PKEngine.compute_cmax_increment(
                    dose_mg,
                    sub["bioavailability"],
                    sub["volume_of_distribution_l_kg"],
                    self.profile.demographics.weight_kg,
                )
                prev_c = state.substance_concentrations.get(schedule.substance_id, 0.0)
                new_c = prev_c + increment
                state.substance_concentrations[schedule.substance_id] = new_c
                if new_c > state.substance_cmax.get(schedule.substance_id, 0.0):
                    state.substance_cmax[schedule.substance_id] = new_c

        # Шаг 3: Экспоненциальный PK-распад
        for sub_id in list(state.substance_concentrations.keys()):
            c = state.substance_concentrations[sub_id]
            if c < 1e-12:
                continue
            ke = self.pk.ke_cache.get(sub_id)
            if ke is None:
                # Неизвестное вещество (не загружено в PKEngine) — удалить устаревшую концентрацию
                del state.substance_concentrations[sub_id]
                continue
            state.substance_concentrations[sub_id] = c * math.exp(-ke)

        # Шаг 4: Эффекты веществ на биомаркеры (D-04)
        self.pk.apply_substance_effects(
            state.biomarker_values,
            state.substance_concentrations,
            state.substance_cmax,
        )

        # Шаг 5: Взаимодействия между веществами
        self.interaction_resolver.apply_interactions(
            state.biomarker_values,
            state.substance_concentrations,
            state.substance_cmax,
        )

        # Шаг 6: Гомеостаз — drift + recovery
        lifestyle_bonus = HomeostasisEngine.compute_lifestyle_bonus(self.profile)
        resilience = state.resilience_index if state.resilience_index is not None else 1.0
        self.homeostasis.apply_drift(state.biomarker_values, self.profile, resilience)
        self.homeostasis.apply_recovery(
            state.biomarker_values,
            self.baseline_biomarkers,
            resilience,
            lifestyle_bonus,
        )

        # Шаг 7: Зажимание значений [0, max_safe] (D-08)
        for code in list(state.biomarker_values.keys()):
            val = state.biomarker_values[code]
            max_s = MAX_SAFE_VALUES.get(code, 1e6)
            state.biomarker_values[code] = max(0.0, min(val, max_s))

        # Шаг 8: THRESHOLD_BREACH события
        new_events = self.event_detector.check_threshold_breaches(
            state.biomarker_values,
            self.profile,
            state.tick_count,
        )
        state.events.extend(new_events)

        # Шаг 9: Вероятностные события
        prob_events = self.event_detector.check_probabilistic_events(
            state.biomarker_values,
            self.profile,
            state.tick_count,
            self.rng,
        )
        state.events.extend(prob_events)

        # Шаг 10: Обновление biological_age
        state.biological_age = self.mortality_risk.compute_biological_age(
            state.biomarker_values,
            self.profile.demographics.age,
        )

        # Шаг 11: Обновление resilience_index
        state.resilience_index = self.mortality_risk.compute_resilience(state.biomarker_values)

        # Шаг 12: CRITICAL → PAUSED (D-15)
        critical = [e for e in new_events + prob_events if e.severity == "CRITICAL"]
        if critical and state.status == SimulationStatus.RUNNING:
            state.transition(SimulationStatus.PAUSED)

        # Шаг 13: Сохранить RNG state (T-05-13)
        state.rng_state = self.rng.get_state()
        return state
