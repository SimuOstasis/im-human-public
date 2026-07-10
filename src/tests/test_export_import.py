# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Тесты экспорта/импорта состояния симуляции (DOCS-01, DOCS-02, DOCS-03).

TDD-гейт Wave 0: файл написан ДО реализации src/engine/exporter.py.
Все 4 теста падают с ImportError/ModuleNotFoundError — это ожидаемое поведение RED-фазы.

Контракт exporter.py (D-01..D-05):
  - export_simulation(state, profile, schedules) -> dict с ключами:
    {"version", "exported_at", "profile", "schedules", "state"}
  - save_simulation(state, profile, schedules, path: Path) -> None
  - load_simulation(path: Path) -> tuple[SimulationState, HumanProfile, list]
  - ValueError при несовместимой версии (D-04)
  - round-trip: 100 тиков → export → import → 50 тиков == 150-тиковый baseline (D-05)

Pitfall 1: rng_state после JSON round-trip должен оставаться tuple, не list.
  random.Random.setstate() принимает только tuple — list вызовет TypeError.
"""

from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


def test_export_container_structure(tmp_path):
    """export_simulation возвращает dict с ровно 5 обязательными ключами (D-01).

    Проверяет:
      - container — dict
      - set(container.keys()) == {"version", "exported_at", "profile", "schedules", "state"}
      - container["version"] == "1.0"
      - container["profile"] — непустой dict
      - container["state"] содержит ключ "biomarker_values"
    """
    from src.engine.exporter import export_simulation  # noqa: F401  # RED: ImportError здесь
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    container = export_simulation(state, profile, schedules=[])

    assert isinstance(container, dict), (
        f"export_simulation должен возвращать dict, получено {type(container)}"
    )
    assert set(container.keys()) == {"version", "exported_at", "profile", "schedules", "state"}, (
        f"Ожидаемые ключи: {{version, exported_at, profile, schedules, state}}, "
        f"получено: {set(container.keys())}"
    )
    assert container["version"] == "1.0", (
        f"container['version'] должен быть '1.0', получено: {container['version']!r}"
    )
    assert isinstance(container["profile"], dict) and container["profile"], (
        "container['profile'] должен быть непустым dict"
    )
    assert "biomarker_values" in container["state"], (
        f"container['state'] должен содержать 'biomarker_values', "
        f"ключи: {list(container['state'].keys())}"
    )


def test_load_simulation_version_check(tmp_path):
    """load_simulation выбрасывает ValueError при несовместимой версии (D-04).

    Алгоритм:
      1. Сохранить валидный снепшот через save_simulation.
      2. Прочитать JSON, заменить "version" на "9.9", записать обратно.
      3. load_simulation(path) должен выбросить ValueError.

    Все файловые операции — с явным encoding="utf-8" (D-23).
    """
    import json
    from src.engine.exporter import save_simulation, load_simulation  # noqa: F401  # RED: ImportError здесь
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()

    snap_path = tmp_path / "snap.json"
    save_simulation(state, profile, schedules=[], path=snap_path)

    # Подменить версию на несовместимую
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["version"] = "9.9"
    snap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError):
        load_simulation(snap_path)


def test_round_trip_100_50_vs_150(tmp_path):
    """Round-trip 100+50 тиков идентичен 150-тиковому baseline (D-05).

    Алгоритм:
      Baseline: seed=42, 150 тиков подряд -> state_base.biomarker_values
      Round-trip:
        1. seed=42, 100 тиков -> save_simulation -> load_simulation
        2. SimulationEngine(profile=profile_imp, seed=state_imp.seed) + 50 тиков
      Первый engine_b.tick(state_imp) автоматически восстановит RNG из state_imp.rng_state
      (simulation_engine.py строки 172-173).
      Сравнение: строгое == (не isclose) — движок детерминирован по design (ENG-01).

    Seed 42 без веществ гарантирует RUNNING статус после 150 тиков (Pitfall 2).
    """
    from src.engine.exporter import save_simulation, load_simulation  # noqa: F401  # RED: ImportError здесь
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    schedules: list = []

    # Путь 1: baseline — непрерывные 150 тиков
    engine_base = SimulationEngine(profile=profile, seed=42)
    state_base = engine_base.initialize()
    for _ in range(150):
        state_base = engine_base.tick(state_base, schedules=schedules)

    # Путь 2: 100 тиков → экспорт → импорт → 50 тиков
    engine_a = SimulationEngine(profile=profile, seed=42)
    state_a = engine_a.initialize()
    for _ in range(100):
        state_a = engine_a.tick(state_a, schedules=schedules)

    snap_path = tmp_path / "round_trip.json"
    save_simulation(state_a, profile, schedules=schedules, path=snap_path)
    state_imp, profile_imp, schedules_imp = load_simulation(snap_path)

    engine_b = SimulationEngine(profile=profile_imp, seed=state_imp.seed)
    for _ in range(50):
        state_imp = engine_b.tick(state_imp, schedules=schedules_imp)

    for code in state_base.biomarker_values:
        assert state_base.biomarker_values[code] == state_imp.biomarker_values[code], (
            f"Round-trip нарушает детерминизм: {code}: "
            f"baseline={state_base.biomarker_values[code]}, "
            f"resumed={state_imp.biomarker_values[code]}"
        )


def test_rng_state_is_tuple_after_load(tmp_path):
    """После load_simulation state.rng_state является tuple, не list (Pitfall 1).

    Критично: random.Random.setstate() принимает только tuple.
    Если rng_state оказался list (JSON десериализует массивы как list) —
    первый же engine.tick() вызовет TypeError в set_state.

    Проверяет: isinstance(state_imp.rng_state, tuple) is True.
    """
    from src.engine.exporter import save_simulation, load_simulation  # noqa: F401  # RED: ImportError здесь
    from src.engine.simulation_engine import SimulationEngine
    from src.domain.human_profile import HumanProfile

    profile = HumanProfile.from_preset("young_healthy_30m")
    engine = SimulationEngine(profile=profile, seed=42)
    state = engine.initialize()
    for _ in range(10):
        state = engine.tick(state, schedules=[])

    snap_path = tmp_path / "rng_check.json"
    save_simulation(state, profile, schedules=[], path=snap_path)
    state_imp, _profile_imp, _schedules_imp = load_simulation(snap_path)

    assert isinstance(state_imp.rng_state, tuple), (
        f"state.rng_state должен быть tuple после load_simulation, "
        f"получено {type(state_imp.rng_state).__name__}. "
        f"Pitfall 1: random.Random.setstate() не принимает list — TypeError при первом tick()."
    )
