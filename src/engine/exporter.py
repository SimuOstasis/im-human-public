# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""exporter.py — JSON экспорт/импорт полного состояния симуляции (DOCS-01, DOCS-02).

Публичный API:
  export_simulation(state, profile, schedules) -> dict
  save_simulation(state, profile, schedules, path) -> None
  load_simulation(path) -> tuple[SimulationState, HumanProfile, list[IntakeSchedule]]

Контейнер (D-01): {"version", "exported_at", "profile", "schedules", "state"}
Версия валидируется при импорте (D-04): ValueError при несовместимой версии.

Pitfall 1 (rng_state):
  JSON десериализует массивы как Python list. SimulationState.rng_state аннотирован
  как `tuple | None`. Pydantic v2 с model_validate(dict) приводит list -> tuple
  автоматически, но для надёжности используем model_validate_json() напрямую.

Pitfall 2 (PAUSED state):
  Если state.status == PAUSED, вызывающий код должен выполнить
  state.transition(SimulationStatus.RUNNING) перед первым tick().
  load_simulation намеренно НЕ вызывает transition — решение остаётся за вызывающим.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.domain.simulation_state import SimulationState
from src.domain.human_profile import HumanProfile
from src.domain.substance import IntakeSchedule

EXPORT_VERSION = "1.0"


def _validate_version(version: str) -> None:
    """Проверить совместимость версии контейнера.

    Args:
        version: строка версии из JSON-контейнера.

    Raises:
        ValueError: если version не совпадает с EXPORT_VERSION.
    """
    if version != EXPORT_VERSION:
        raise ValueError(
            f"Несовместимая версия контейнера: получена '{version}', "
            f"ожидается '{EXPORT_VERSION}'. "
            f"Используйте файл, сохранённый текущей версией приложения."
        )


def export_simulation(
    state: SimulationState,
    profile: HumanProfile,
    schedules: list,
) -> dict:
    """Экспортировать полное состояние симуляции в JSON-совместимый dict (D-01).

    Args:
        state: текущее состояние симуляции (SimulationState).
        profile: профиль человека (HumanProfile).
        schedules: список IntakeSchedule (может быть пустым).

    Returns:
        dict с ключами: version, exported_at, profile, schedules, state.
        Включает профиль полностью — импорт не зависит от presets.json (D-01).
    """
    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.model_dump(),
        "schedules": [s.model_dump() for s in schedules],
        "state": state.model_dump(),
    }


def save_simulation(
    state: SimulationState,
    profile: HumanProfile,
    schedules: list,
    path: Path,
) -> None:
    """Сохранить снепшот симуляции в JSON-файл (D-02).

    Args:
        state: текущее состояние симуляции.
        profile: профиль человека.
        schedules: список IntakeSchedule.
        path: путь к файлу для записи (Path-объект).

    Note:
        Файл записывается в UTF-8, без ASCII-экранирования (D-23).
        Path traversal не проверяется — вызывающий контролирует путь (T-08-04 accept).
    """
    container = export_simulation(state, profile, schedules)
    path.write_text(
        json.dumps(container, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _coerce_rng_state(rng_raw) -> tuple | None:
    """Привести rng_state из JSON к правильной структуре tuple.

    Python random.Random.getstate() возвращает (version: int, internalstate: tuple, gauss_next).
    При JSON round-trip оба уровня становятся list. Нужно глубокое приведение:
      - внешний list -> tuple
      - второй элемент (internalstate) list -> tuple

    Args:
        rng_raw: rng_state из json.loads — может быть None, list или уже tuple.

    Returns:
        tuple совместимый с random.Random.setstate(), или None.
    """
    if rng_raw is None:
        return None
    # Pydantic или json.loads могут вернуть list или tuple
    rng_outer = tuple(rng_raw) if isinstance(rng_raw, list) else rng_raw
    # Второй элемент (internalstate) тоже должен быть tuple
    if len(rng_outer) >= 2 and isinstance(rng_outer[1], list):
        rng_inner = tuple(rng_outer[1])
        rng_outer = (rng_outer[0], rng_inner) + rng_outer[2:]
    return rng_outer


def load_simulation(
    path: Path,
) -> tuple[SimulationState, HumanProfile, list[IntakeSchedule]]:
    """Загрузить снепшот симуляции из JSON-файла (D-03, D-04).

    Args:
        path: путь к ранее сохранённому JSON-файлу.

    Returns:
        Кортеж (state, profile, schedules).

    Raises:
        ValueError: если версия контейнера не совпадает с EXPORT_VERSION,
            или если в данных отсутствует обязательный ключ 'state' или 'profile'.
        pydantic.ValidationError: если данные не прошли валидацию Pydantic.

    Note (Pitfall 1 — rng_state):
        JSON десериализует tuple как list на всех уровнях вложенности.
        random.Random.getstate() возвращает (version, internalstate_tuple, gauss_next).
        Оба уровня приводятся к tuple через _coerce_rng_state() перед Pydantic-валидацией.

    Note (Pitfall 2 — PAUSED state):
        Если state.status == PAUSED, вызывающий код должен выполнить
        state.transition(SimulationStatus.RUNNING) перед первым engine.tick().
        Эта функция намеренно НЕ вызывает transition — решение остаётся за вызывающим.
    """
    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)

    # D-04: проверить версию до десериализации
    _validate_version(data.get("version"))

    # КРИТИЧНО (Pitfall 1): rng_state из JSON имеет вложенные list на двух уровнях.
    # random.Random.setstate() требует tuple на обоих уровнях.
    # Приводим явно до передачи в Pydantic.
    try:
        state_data = data["state"]
        profile_data = data["profile"]
    except KeyError as exc:
        raise ValueError(
            f"Повреждённый файл снепшота: отсутствует ключ {exc}."
        ) from exc

    rng_raw = state_data.get("rng_state")
    if rng_raw is not None:
        state_data["rng_state"] = _coerce_rng_state(rng_raw)

    state = SimulationState.model_validate(state_data)
    profile = HumanProfile.model_validate(profile_data)
    schedules = [IntakeSchedule.model_validate(s) for s in data.get("schedules", [])]

    return state, profile, schedules
