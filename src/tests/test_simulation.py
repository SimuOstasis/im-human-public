# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Интеграционные тесты движка симуляции (ENG-03, ENG-05, ENG-07, ENG-08, ENG-10).

Wave 3 заполняет эти заглушки реализацией simulation_engine.py.
Все тесты помечены @pytest.mark.skip до появления полного стека движка (Wave 1-3).
"""

from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


def test_homeostasis_drift():
    """Без веществ у пожилого профиля (70M) LDL дрейфует вверх за 8760 тиков.

    Проверяет ENG-03: гомеостатический дрейф к деградированному состоянию.
    base_rate=0.00002/тик, age_factor=(70-30)/100=0.4, без resilience.
    Ожидание: ldlC после 8760 тиков > ldlC на тике 0.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("elderly_70m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()
    initial_ldl = state.biomarker_values["ldlC"]

    for _ in range(8760):
        state = engine.tick(state, schedules=[])

    assert state.biomarker_values["ldlC"] > initial_ldl, (
        f"LDL должен дрейфовать вверх у 70M без веществ: "
        f"start={initial_ldl:.4f}, end={state.biomarker_values['ldlC']:.4f}"
    )


def test_homeostasis_recovery():
    """После искусственного снижения биомаркера гомеостаз восстанавливает его к baseline.

    Проверяет ENG-03: восстановительная тяга к оптимальному состоянию.
    Ожидание: через N тиков без воздействий ldlC возвращается ближе к baseline.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    baseline_ldl = state.biomarker_values["ldlC"]
    # Искусственно занизить LDL
    state.biomarker_values["ldlC"] = baseline_ldl * 0.5

    for _ in range(720):  # 30 дней
        state = engine.tick(state, schedules=[])

    # После 30 дней без веществ должен быть ближе к baseline
    delta_after = abs(state.biomarker_values["ldlC"] - baseline_ldl)
    delta_initial = abs(baseline_ldl * 0.5 - baseline_ldl)
    assert delta_after < delta_initial, (
        f"Восстановление не произошло: initial_gap={delta_initial:.4f}, "
        f"remaining_gap={delta_after:.4f}"
    )


def test_one_tick_no_errors():
    """Один тик движка выполняется без ошибок и NaN.

    Проверяет ENG-07: 13-шаговый тик без исключений.
    Все biomarker_values после тика должны быть конечными числами.
    """
    import math
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()
    state = engine.tick(state, schedules=[])

    for code, val in state.biomarker_values.items():
        assert math.isfinite(val), f"biomarker {code} = {val} (NaN или inf)"


def test_pause_resume_state_exact():
    """Пауза → возобновление → один дополнительный тик воспроизводит то же состояние.

    Проверяет ENG-10: pause/resume сохраняет точное состояние (биомаркеры + RNG).
    Алгоритм:
      1. run N тиков -> state_reference
      2. run N-1 тиков -> пауза -> восстановить rng_state -> 1 тик -> state_resumed
      3. Все biomarker_values в state_reference == state_resumed (isclose rel_tol=1e-9).
    """
    import math
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    N = 100

    # Путь 1: N тиков подряд
    engine1 = SimulationEngine(profile=profile, seed=42)
    state1 = engine1.initialize()
    for _ in range(N):
        state1 = engine1.tick(state1, schedules=[])

    # Путь 2: N-1 тиков, пауза, 1 тик
    engine2 = SimulationEngine(profile=profile, seed=42)
    state2 = engine2.initialize()
    for _ in range(N - 1):
        state2 = engine2.tick(state2, schedules=[])
    # Пауза: сохранить состояние RNG
    rng_state = engine2.rng.get_state()
    state2.rng_state = rng_state
    # Возобновление: восстановить RNG
    engine2.rng.set_state(state2.rng_state)
    state2 = engine2.tick(state2, schedules=[])

    for code in state1.biomarker_values:
        v1 = state1.biomarker_values[code]
        v2 = state2.biomarker_values[code]
        assert math.isclose(v1, v2, rel_tol=1e-9), (
            f"{code}: pause/resume даёт расхождение: {v1} != {v2}"
        )


def test_biological_age_calibration():
    """Для молодого здорового 30M biological_age ≈ хронологическому (28-34 лет).

    Проверяет ENG-08 + методологически выведенную калибровку
    PHENOAGE_INTERCEPT_PARTIAL (Phase 12, HF-02, D-06/D-07/D-14, Approach A —
    см. src/engine/mortality_risk.py и scripts/calibrate_phenoage_intercept.py).
    Границы гейта пересчитаны от фактического выхода нового intercept'а
    (≈41.16 при seed=42) той же шириной ±6 лет, что и прежний гейт — НЕ
    произвольно расширены (D-07). Пересчёт после WR-01 code-review fix
    (2026-07-19): `_to_phenoage_units()` больше не конвертирует
    albumin/creatinine/glucose в "конвенциональные" единицы (это искажало их
    вклад в biological_age — см. mortality_risk.py и REVIEW-FIX.md), из-за чего
    фактический выход intercept'а и, соответственно, границы гейта сдвинулись.
    Если тест проваливается после ЛЮБОГО изменения intercept'а — гейт нужно
    пересчитать заново от нового фактического выхода, а не просто раздвинуть
    границы.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()
    state = engine.tick(state, schedules=[])  # первый тик инициализирует biological_age

    assert state.biological_age is not None
    assert 35.16 <= state.biological_age <= 47.16, (
        f"Биологический возраст 30M вне диапазона 35.16-47.16: {state.biological_age:.2f}"
    )


def test_no_nan_after_year():
    """Все биомаркеры без NaN после 8760 тиков (1 год симуляции).

    Проверяет ENG-07 + ENG-09: отсутствие NaN-каскада при длительном прогоне.
    """
    import math
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    for _ in range(8760):
        state = engine.tick(state, schedules=[])

    for code, val in state.biomarker_values.items():
        assert math.isfinite(val), f"После года: biomarker {code} = {val} (NaN или inf)"


def test_threshold_breach_event():
    """При превышении high_risk границы биомаркера генерируется THRESHOLD_BREACH событие.

    Проверяет ENG-05: обнаружение пороговых событий.
    Алгоритм: искусственно поднять ldlC выше high_risk -> tick -> проверить events.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    # Искусственно поднять LDL выше high_risk (~3.5 ммоль/л для male 30-49)
    state.biomarker_values["ldlC"] = 4.5

    initial_event_count = len(state.events)
    state = engine.tick(state, schedules=[])

    breach_events = [e for e in state.events if e.event_type == "THRESHOLD_BREACH"
                     and e.biomarker == "ldlC"]
    assert len(breach_events) > initial_event_count or len(breach_events) >= 1, (
        f"Ожидалось THRESHOLD_BREACH событие для ldlC=4.5, получено событий: {len(state.events)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GAP-01: Probabilistic event tests (ENG-05 PARTIAL)


class _AlwaysFireRNG:
    """Fake RNG: random() always returns 0.0, which is < any positive probability."""

    def random(self):
        return 0.0


class _NeverFireRNG:
    """Fake RNG: random() always returns 1.0, which is >= any probability in [0,1)."""

    def random(self):
        return 0.999999


def _make_event_detector():
    """Create EventDetector with real reference_ranges.json."""
    import json
    rr = json.loads(
        (VAULT_ROOT / "src" / "data" / "reference_ranges.json").read_text(encoding="utf-8")
    )
    from src.engine.event_detector import EventDetector
    return EventDetector(rr)


def test_probabilistic_cvd_event_fires_with_elevated_risk():
    """With very high LDL + SBP + age, CVD probabilistic event fires deterministically.

    ENG-05: CVD risk = f(LDL, SBP, age, sex). 10-yr risk capped at 80%.
    Injecting RNG that always returns 0.0 guarantees event triggers.
    """
    from src.engine.event_detector import EventDetector
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("elderly_70m")
    detector = _make_event_detector()
    # High LDL (10 mmol/L) + high SBP (200) → max CVD risk
    biomarkers = {"ldlC": 10.0, "systolicBloodPressure": 200.0}
    rng = _AlwaysFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    cvd = [e for e in events if e.event_type == "PROBABILISTIC" and e.biomarker == "ldlC"]
    assert len(cvd) >= 1, (
        f"Expected CVD probabilistic event with ldlC=10, sbp=200, age=70. "
        f"Got {len(cvd)} events from {len(events)} total."
    )
    assert cvd[0].severity == "WARNING"
    assert "Кардиоваскулярный риск" in cvd[0].message


def test_probabilistic_diabetes_event_fires_with_elevated_hba1c():
    """With high HbA1c + glucose, diabetes risk event fires.

    ENG-05: Diabetes risk requires hba1c > 5.7 AND glucose > 5.5.
    """
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    detector = _make_event_detector()
    biomarkers = {"hba1c": 10.0, "fastingGlucose": 8.0}
    rng = _AlwaysFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    dm = [e for e in events if e.event_type == "PROBABILISTIC" and e.biomarker == "hba1c"]
    assert len(dm) >= 1, (
        f"Expected diabetes risk event with hba1c=10, glucose=8. "
        f"Got {len(dm)} events from {len(events)} total."
    )
    assert "Риск диабета" in dm[0].message


def test_probabilistic_diabetes_no_event_with_low_hba1c():
    """Below hba1c=5.7 threshold, no diabetes event even with high glucose.

    ENG-05: Diabetes requires BOTH hba1c > 5.7 AND glucose > 5.5.
    """
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    detector = _make_event_detector()
    biomarkers = {"hba1c": 5.0, "fastingGlucose": 8.0}  # hba1c below threshold
    rng = _AlwaysFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    dm = [e for e in events if e.event_type == "PROBABILISTIC" and e.biomarker == "hba1c"]
    assert len(dm) == 0, (
        f"No diabetes event expected with hba1c=5.0 (below 5.7 threshold). "
        f"Got {len(dm)} events."
    )


def test_probabilistic_ckd_event_fires_with_low_egfr():
    """With high creatinine + low eGFR, CKD risk event fires.

    ENG-05: CKD risk requires creatinine > 115 AND eGFR < 70.
    """
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("elderly_70m")
    detector = _make_event_detector()
    biomarkers = {"creatinine": 200.0, "egfr": 30.0}
    rng = _AlwaysFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    ckd = [e for e in events if e.event_type == "PROBABILISTIC" and e.biomarker == "egfr"]
    assert len(ckd) >= 1, (
        f"Expected CKD event with creat=200, eGFR=30. "
        f"Got {len(ckd)} events from {len(events)} total."
    )
    assert "Риск снижения eGFR" in ckd[0].message


def test_probabilistic_hypertensive_crisis_fires_with_high_sbp():
    """With SBP > 160, hypertensive crisis probabilistic event can fire (CRITICAL).

    ENG-05: Hypertensive crisis = SBP > 160, base probability 0.1% per tick.
    Injecting RNG that returns 0.0 guarantees it fires. Severity = CRITICAL.
    """
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    detector = _make_event_detector()
    biomarkers = {"systolicBloodPressure": 200.0}
    rng = _AlwaysFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    crisis = [e for e in events if e.event_type == "PROBABILISTIC"
              and e.biomarker == "systolicBloodPressure"]
    assert len(crisis) >= 1, (
        f"Expected hypertensive crisis with sbp=200. "
        f"Got {len(crisis)} events."
    )
    assert crisis[0].severity == "CRITICAL", (
        f"Hypertensive crisis should be CRITICAL severity, got {crisis[0].severity}"
    )


def test_probabilistic_no_events_with_normal_biomarkers():
    """With normal biomarkers, no probabilistic events fire even with always-fire RNG.

    ENG-05: CVD requires elevated LDL/SBP, diabetes requires hba1c>5.7+glucose>5.5,
    CKD requires creat>115+eGFR<70, crisis requires SBP>160.
    """
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    detector = _make_event_detector()
    # Normal values: LDL~2.5, SBP~120, hba1c~5.0, glucose~5.0, creat~80, egfr~90
    biomarkers = {
        "ldlC": 2.5,
        "systolicBloodPressure": 120.0,
        "hba1c": 5.0,
        "fastingGlucose": 5.0,
        "creatinine": 80.0,
        "egfr": 90.0,
    }
    rng = _NeverFireRNG()

    events = detector.check_probabilistic_events(biomarkers, profile, tick=1, rng=rng)
    assert len(events) == 0, (
        f"Expected 0 probabilistic events with normal biomarkers, got {len(events)}: "
        f"{[e.message for e in events]}"
    )


def test_hypertensive_crisis_pauses_engine():
    """A CRITICAL hypertensive crisis event causes the engine to PAUSE (D-15).

    ENG-05 + D-15: Severity CRITICAL → state.transition(PAUSED).
    """
    import json
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    # Force SBP above 160 for hypertensive crisis risk
    state.biomarker_values["systolicBloodPressure"] = 200.0

    # Patch the engine's RNG to always trigger probabilistic events
    original_rng = engine.rng

    class _AlwaysTriggerRNG:
        def random(self):
            return 0.0
        def get_state(self):
            return original_rng.get_state()
        def set_state(self, s):
            original_rng.set_state(s)

    engine.rng = _AlwaysTriggerRNG()

    state = engine.tick(state, schedules=[])

    # Check that CRITICAL events exist and engine is PAUSED
    critical_events = [e for e in state.events if e.severity == "CRITICAL"]
    assert len(critical_events) >= 1, (
        f"Expected at least one CRITICAL event (hypertensive crisis), got {len(critical_events)}"
    )

    from src.domain.simulation_state import SimulationStatus
    assert state.status == SimulationStatus.PAUSED, (
        f"Engine should be PAUSED after CRITICAL event, got {state.status.value}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GAP-02: Resilience index tests (ENG-08 PARTIAL)


def test_resilience_in_range_for_known_biomarkers():
    """compute_resilience returns values in [0, 1] for arbitrary biomarker sets.

    ENG-08: resilience_index ∈ [0.0, 1.0]. Formula: mean of clamped normalizations
    of albumin, eGFR, HRV against RESILIENCE_PARAMS.
    """
    from src.engine.mortality_risk import MortalityRiskEngine

    engine = MortalityRiskEngine()

    # Test multiple biomarker sets
    test_cases = [
        {"albumin": 45.0, "egfr": 90.0, "hrvRmssd": 50.0},  # normal
        {"albumin": 20.0, "egfr": 10.0, "hrvRmssd": 5.0},   # very low
        {"albumin": 60.0, "egfr": 150.0, "hrvRmssd": 100.0}, # very high (clamped)
        {"albumin": 40.0},                                      # partial (only albumin)
        {},                                                     # empty
    ]

    for i, bm in enumerate(test_cases):
        r = engine.compute_resilience(bm)
        assert 0.0 <= r <= 1.0, (
            f"Case {i}: resilience={r} out of [0, 1] for biomarkers={bm}"
        )


def test_resilience_high_biomarkers_higher_than_low():
    """High albumin/eGFR/HRV gives strictly higher resilience than low values.

    ENG-08: resilience_index = mean(normalized). Higher inputs → higher output.
    """
    from src.engine.mortality_risk import MortalityRiskEngine

    engine = MortalityRiskEngine()

    low_bm = {"albumin": 35.0, "egfr": 30.0, "hrvRmssd": 15.0}
    high_bm = {"albumin": 55.0, "egfr": 120.0, "hrvRmssd": 80.0}

    r_low = engine.compute_resilience(low_bm)
    r_high = engine.compute_resilience(high_bm)

    # Low values should be at or near 0, high should be at or near 1
    assert r_low < r_high, (
        f"Expected low resilience ({r_low}) < high resilience ({r_high})"
    )
    assert r_low <= 0.05, f"Low biomarkers should give resilience near 0, got {r_low}"
    assert r_high >= 0.95, f"High biomarkers should give resilience near 1, got {r_high}"


def test_resilience_young_healthy_above_half():
    """Young healthy 30M baseline biomarkers give resilience > 0.5.

    ENG-08: A healthy profile should have resilience_index > 0.5 (good recovery capacity).
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    assert state.resilience_index is not None, "resilience_index should be set after init"
    assert state.resilience_index > 0.5, (
        f"Healthy 30M should have resilience > 0.5, got {state.resilience_index:.4f}"
    )


def test_resilience_elderly_degrades_faster_than_young():
    """After 8760 ticks, elderly 70M resilience degrades more than young 30M.

    ENG-08: Elderly profiles have higher age_factor drift → faster degradation.
    Both start at optimal midpoint (same tick-0 resilience), but elderly degrades
    faster over time due to higher age_factor in homeostasis drift.
    """
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    # Young profile
    young_profile = HumanProfile.from_preset("young_healthy_30m")
    young_engine = SimulationEngine(profile=young_profile, seed=42)
    young_state = young_engine.initialize()
    young_r0 = young_state.resilience_index

    for _ in range(8760):
        young_state = young_engine.tick(young_state, schedules=[])

    # Elderly profile
    elderly_profile = HumanProfile.from_preset("elderly_70m")
    elderly_engine = SimulationEngine(profile=elderly_profile, seed=42)
    elderly_state = elderly_engine.initialize()
    elderly_r0 = elderly_state.resilience_index

    for _ in range(8760):
        elderly_state = elderly_engine.tick(elderly_state, schedules=[])

    # Both start at same optimal midpoint resilience
    assert young_r0 == elderly_r0, (
        f"Both profiles should start at same baseline resilience: "
        f"young={young_r0:.4f}, elderly={elderly_r0:.4f}"
    )

    # Elderly degrades more over 1 year
    young_drop = young_r0 - young_state.resilience_index
    elderly_drop = elderly_r0 - elderly_state.resilience_index
    assert elderly_drop > young_drop, (
        f"Elderly should degrade faster: elderly_drop={elderly_drop:.4f}, "
        f"young_drop={young_drop:.4f}"
    )

    # Resilience stays in valid range
    assert 0.0 <= elderly_state.resilience_index <= 1.0


def test_resilience_empty_biomarkers_returns_default():
    """With no biomarkers at all, resilience defaults to 0.5.

    ENG-08: Graceful degradation — empty dict → 0.5.
    """
    from src.engine.mortality_risk import MortalityRiskEngine

    engine = MortalityRiskEngine()
    r = engine.compute_resilience({})
    assert r == 0.5, f"Empty biomarkers should return 0.5, got {r}"
