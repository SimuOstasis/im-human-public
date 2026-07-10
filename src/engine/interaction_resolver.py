# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""InteractionResolver — резолвер взаимодействий веществ для im-human simulator.

Реализует:
  - apply_synergy: модульная функция для синергетического усиления дельты
  - apply_antagonism: модульная функция для антагонистического ослабления дельты
  - check_self_toxicity: модульная функция для обнаружения токсического превышения
  - InteractionResolver: класс-оркестратор для всех взаимодействий в тиковом цикле

Требования плана:
  ENG-04, ENG-11 — synergy/antagonism/toxicity с формулами из RESEARCH.md Area 3

Угрозы (T-05-07):
  - Division by zero при cmax=0: использовать cmax.get(sub, 1.0) как fallback

Запрещено: никаких file I/O внутри методов — данные передаются как аргументы.
"""
from __future__ import annotations

from src.domain.simulation_state import SimulationEvent

# ─── Константы модуля ────────────────────────────────────────────────────────

TOXICITY_MULTIPLIER: float = 2.0  # C >= Cmax * 2.0 → токсично (T-08 accept)


# ─── Модульные функции (используются тестами и классом) ──────────────────────


def apply_synergy(
    base_delta: float,
    coeff: float,
    c_a: float,
    cmax_a: float,
    c_b: float,
    cmax_b: float,
) -> float:
    """Вернуть дельту с учётом синергетического усиления.

    Формула (RESEARCH.md Area 3):
      если c_a <= 0 или c_b <= 0: вернуть base_delta без изменений
      overlap_factor = min(c_a / cmax_a, c_b / cmax_b)  # [0..1]
      synergy_boost = base_delta * (coeff - 1.0) * overlap_factor
      result = base_delta + synergy_boost = base_delta * (1 + (coeff - 1) * overlap)

    Семантика: при coeff=1.3 и 100% обоих → результат = base_delta * 1.3.
    При 50% концентрации обоих → overlap_factor=0.5 → результат = base_delta * 1.15.

    Args:
        base_delta: Исходная дельта биомаркера от вещества.
        coeff: Коэффициент синергии из interactions.json (напр. 1.3).
        c_a: Текущая концентрация вещества A.
        cmax_a: Cmax вещества A (защита от деления на 0: если 0 → 1.0).
        c_b: Текущая концентрация вещества B.
        cmax_b: Cmax вещества B (защита от деления на 0: если 0 → 1.0).

    Returns:
        float — усиленная дельта.
    """
    if c_a <= 0.0 or c_b <= 0.0:
        return base_delta

    # T-05-07: защита от деления на ноль
    safe_cmax_a = cmax_a if cmax_a > 0.0 else 1.0
    safe_cmax_b = cmax_b if cmax_b > 0.0 else 1.0

    overlap_factor = min(c_a / safe_cmax_a, c_b / safe_cmax_b)
    synergy_boost = base_delta * (coeff - 1.0) * overlap_factor
    return base_delta + synergy_boost


def apply_antagonism(
    base_delta: float,
    coeff: float,
    c_antagonist: float,
    cmax_antagonist: float,
) -> float:
    """Вернуть дельту с учётом антагонистического ослабления.

    Формула (RESEARCH.md Area 3):
      если c_antagonist <= 0: вернуть base_delta без изменений
      antagonism_fraction = (1 - coeff) * (c_antagonist / cmax_antagonist)
      result = base_delta * (1 - antagonism_fraction)

    Семантика: при coeff=0.7 и 100% антагониста → эффект снижается на 30%.

    Args:
        base_delta: Исходная дельта биомаркера от целевого вещества.
        coeff: Коэффициент антагонизма из interactions.json (напр. 0.7).
        c_antagonist: Текущая концентрация антагониста.
        cmax_antagonist: Cmax антагониста (защита от деления на 0: если 0 → 1.0).

    Returns:
        float — ослабленная дельта.
    """
    if c_antagonist <= 0.0:
        return base_delta

    # T-05-07: защита от деления на ноль
    safe_cmax = cmax_antagonist if cmax_antagonist > 0.0 else 1.0

    antagonism_fraction = (1.0 - coeff) * (c_antagonist / safe_cmax)
    return base_delta * (1.0 - antagonism_fraction)


def check_self_toxicity(
    substance_id: str,
    c_current: float,
    c_max: float,
    interactions: list[dict],
    tick: int = 0,
) -> SimulationEvent | None:
    """Проверить самотоксичность вещества и вернуть CRITICAL событие при превышении.

    Формула (RESEARCH.md Area 3):
      threshold = c_max * TOXICITY_MULTIPLIER (2.0)
      если c_current >= threshold → CRITICAL SimulationEvent

    Args:
        substance_id: ID вещества (напр. 'rapamycin').
        c_current: Текущая концентрация.
        c_max: Cmax вещества.
        interactions: Список словарей из interactions.json.
        tick: Текущий тик симуляции (по умолчанию 0 для обратной совместимости).

    Returns:
        SimulationEvent с severity='CRITICAL' при токсическом превышении,
        или None если нет самотоксичности или не превышен порог.
    """
    # Найти самореференцию toxicity для данного вещества
    tox_entries = [
        i for i in interactions
        if i.get("substanceA") == substance_id
        and i.get("substanceB") == substance_id
        and i.get("type") == "toxicity"
    ]
    if not tox_entries:
        return None

    # T-05-07: защита от деления на ноль при c_max=0
    safe_cmax = c_max if c_max > 0.0 else 1.0
    threshold = safe_cmax * TOXICITY_MULTIPLIER

    if c_current >= threshold:
        return SimulationEvent(
            tick=tick,
            event_type="THRESHOLD_BREACH",
            biomarker=None,
            value=c_current,
            message=(
                f"{substance_id}: концентрация {c_current:.4f} "
                f"превышает токсический порог {threshold:.4f} "
                f"({TOXICITY_MULTIPLIER:.0f}×Cmax)"
            ),
            severity="CRITICAL",
        )
    return None


# ─── Класс InteractionResolver ───────────────────────────────────────────────


class InteractionResolver:
    """Оркестратор взаимодействий — применяет синергии, антагонизмы, проверяет токсичность.

    Использует interactions_data (из interactions.json) и substances_data
    (из substances.json) для построения lookup-таблиц.

    Не читает файлы — все данные передаются в конструкторе.
    """

    def __init__(
        self,
        interactions_data: list[dict],
        substances_data: list[dict],
    ) -> None:
        """Инициализировать резолвер.

        Args:
            interactions_data: Список взаимодействий из interactions.json.
            substances_data: Список веществ из substances.json.
        """
        # Lookup по frozenset пары веществ
        self.interactions_lookup: dict[frozenset, dict] = {}
        for entry in interactions_data:
            key = frozenset({entry["substanceA"], entry["substanceB"]})
            self.interactions_lookup[key] = entry

        # cmax_lookup удалён (WR-03): значения Cmax отслеживаются динамически
        # через state.substance_cmax и передаются в apply_interactions/check_toxicity.
        # Поле "cmax" в substances.json отсутствует — все статические значения были 1.0.

        # Разделить взаимодействия по типу
        self.synergies: list[dict] = [
            e for e in interactions_data if e.get("type") == "synergy"
        ]
        self.antagonisms: list[dict] = [
            e for e in interactions_data if e.get("type") == "antagonism"
        ]
        self.toxicities: list[dict] = [
            e for e in interactions_data if e.get("type") == "toxicity"
        ]

        # Сохранить все взаимодействия для check_toxicity
        self._interactions_data = interactions_data

        # Построить effectProfile lookup из substances_data
        self._effect_profiles: dict[str, dict[str, float]] = {}
        for sub in substances_data:
            sub_id = sub.get("id", "")
            if sub_id:
                self._effect_profiles[sub_id] = sub.get("effectProfile", {})

    def apply_interactions(
        self,
        biomarker_values: dict[str, float],
        substance_concentrations: dict[str, float],
        substance_cmax: dict[str, float],
    ) -> dict[str, float]:
        """Применить все взаимодействия к биомаркерам.

        Последовательность:
          1. Синергии: усилить дельты overlapping биомаркеров
          2. Антагонизмы: ослабить дельты целевых биомаркеров

        Токсичность проверяется отдельно через check_toxicity().

        Args:
            biomarker_values: Текущие значения биомаркеров (мутируется in-place).
            substance_concentrations: Текущие концентрации веществ.
            substance_cmax: Cmax для каждого вещества (для нормализации).

        Returns:
            dict[str, float] — обновлённые значения биомаркеров.
        """
        # 1. Синергии
        for synergy in self.synergies:
            sub_a: str = synergy["substanceA"]
            sub_b: str = synergy["substanceB"]
            c_a = substance_concentrations.get(sub_a, 0.0)
            c_b = substance_concentrations.get(sub_b, 0.0)

            if c_a <= 0.0 or c_b <= 0.0:
                continue

            # T-05-07: защита от деления на ноль
            cmax_a = substance_cmax.get(sub_a, 1.0) or 1.0
            cmax_b = substance_cmax.get(sub_b, 1.0) or 1.0

            coeff: float = synergy.get("coefficient", 1.0)

            # Применить к overlapping биомаркерам (пересечение effectProfiles)
            profile_a = self._effect_profiles.get(sub_a, {})
            profile_b = self._effect_profiles.get(sub_b, {})
            overlapping_bm = set(profile_a.keys()) & set(profile_b.keys())

            for bm_code in overlapping_bm:
                if bm_code in biomarker_values:
                    # Синергетический буст: применяем к дельте вещества A (base_delta),
                    # а не к полному значению биомаркера. Используем apply_synergy()
                    # из этого же модуля для консистентности.
                    base_delta_a = profile_a.get(bm_code, 0.0)
                    boosted = apply_synergy(
                        base_delta_a, coeff,
                        c_a, cmax_a, c_b, cmax_b,
                    )
                    biomarker_values[bm_code] += (boosted - base_delta_a)

        # 2. Антагонизмы
        for antagonism in self.antagonisms:
            sub_a: str = antagonism["substanceA"]
            sub_b: str = antagonism["substanceB"]
            coeff: float = antagonism.get("coefficient", 1.0)

            # Семантика: "совместный приём снижает эффективность обоих" (interactions.json).
            # Симметричное применение: каждое вещество ослабляет эффект другого.
            # ПРИМЕЧАНИЕ (WR-04): при coeff=0.7 и 100% обоих веществ:
            #   каждое направление снижает эффект на 30%; совместный эффект ≈ 1 - (1-0.3)^2 = 51%.
            #   Это соответствует взаимному ослаблению, задокументированному в RESEARCH.md.
            #   Если нужно ровно 30% снижения — применять только одно направление.
            for sub_antagonist, sub_target in [(sub_a, sub_b), (sub_b, sub_a)]:
                c_ant = substance_concentrations.get(sub_antagonist, 0.0)
                if c_ant <= 0.0:
                    continue

                c_target = substance_concentrations.get(sub_target, 0.0)
                if c_target <= 0.0:
                    continue

                # T-05-07: защита от деления на ноль
                cmax_ant = substance_cmax.get(sub_antagonist, 1.0) or 1.0
                cmax_target = substance_cmax.get(sub_target, 1.0) or 1.0

                antagonism_fraction = (1.0 - coeff) * (c_ant / cmax_ant)
                ratio_before = c_target / cmax_target
                ratio_after = ratio_before * (1.0 - antagonism_fraction)
                delta_ratio = ratio_before - ratio_after

                # Применить к биомаркерам целевого вещества
                profile_target = self._effect_profiles.get(sub_target, {})
                for bm_code, effect_delta in profile_target.items():
                    if bm_code in biomarker_values:
                        biomarker_values[bm_code] += effect_delta * (-delta_ratio)

        return biomarker_values

    def check_toxicity(
        self,
        substance_concentrations: dict[str, float],
        substance_cmax: dict[str, float],
    ) -> bool:
        """Проверить, есть ли токсическое превышение для любого вещества.

        Использует TOXICITY_MULTIPLIER = 2.0.
        Возвращает True если хотя бы одно вещество превышает 2×Cmax.

        Args:
            substance_concentrations: Текущие концентрации.
            substance_cmax: Cmax для каждого вещества.

        Returns:
            True если есть токсическое превышение, иначе False.
        """
        for entry in self.toxicities:
            sub_id: str = entry["substanceA"]
            # Самотоксичность: substanceA == substanceB
            if entry["substanceA"] != entry["substanceB"]:
                continue

            c = substance_concentrations.get(sub_id, 0.0)
            # T-05-07: защита от деления на ноль
            cmax = substance_cmax.get(sub_id, 1.0) or 1.0

            if c >= cmax * TOXICITY_MULTIPLIER:
                return True

        return False
