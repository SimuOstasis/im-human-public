# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Фармакокинетическое ядро (PK Engine) — ENG-02.

Реализует одночастотную экспоненциальную PK-модель (D-01/D-02/D-04):
  C(t) = Cmax × e^(-ke × Δt)
  ke   = ln(2) / half_life_hours
  Cmax_increment = dose_mg × bioavailability / (Vd_l_kg × weight_kg)

Статические методы доступны как методы PKEngine И как модульные функции
(compute_ke, compute_cmax_increment, compute_decay) для обратной совместимости
с тест-скелетами из Plan 05-01.

Нет file I/O внутри класса — substances.json загружается снаружи и передаётся
в __init__ готовым списком словарей (T-05-03, T-05-04 mitigated via ValueError).
"""

import math


# ---------------------------------------------------------------------------
# PKEngine — основной класс
# ---------------------------------------------------------------------------

class PKEngine:
    """Фармакокинетический движок для симулятора im-human.

    Принимает список веществ из substances.json при инициализации и кэширует
    константы элиминации (ke) для всех веществ, чтобы не пересчитывать их
    в тиковом цикле (требование производительности D-08).

    Attributes:
        ke_cache: Словарь {substance_id: ke}, предрасчитанный в __init__.
        substances: Словарь {substance_id: substance_dict} для быстрого доступа.
    """

    def __init__(self, substances_data: list[dict]) -> None:
        """Инициализировать PKEngine из списка словарей substances.json.

        Args:
            substances_data: Список словарей вещества из substances.json.
                             Каждый словарь обязан содержать поля
                             "id" и "halfLifeHours".

        Raises:
            ValueError: Если halfLifeHours <= 0 для любого вещества.
        """
        self.substances: dict[str, dict] = {s["id"]: s for s in substances_data}
        self.ke_cache: dict[str, float] = {
            s["id"]: self.compute_ke(s["halfLifeHours"])
            for s in substances_data
        }

    # ------------------------------------------------------------------
    # Статические методы (D-01 / D-02) — вызываются напрямую из тестов
    # и из simulation_engine.py без создания экземпляра PKEngine
    # ------------------------------------------------------------------

    @staticmethod
    def compute_ke(half_life_hours: float) -> float:
        """Вычислить константу элиминации ke = ln(2) / T½.

        Args:
            half_life_hours: Период полувыведения в часах (T½ > 0).

        Returns:
            Константа элиминации ke (1/час).

        Raises:
            ValueError: Если half_life_hours <= 0.
        """
        if half_life_hours <= 0:
            raise ValueError(
                f"half_life_hours must be positive, got {half_life_hours}"
            )
        return math.log(2) / half_life_hours

    @staticmethod
    def compute_cmax_increment(
        dose_mg: float,
        bioavailability: float,
        vd_l_kg: float,
        weight_kg: float,
    ) -> float:
        """Вычислить прирост концентрации при дозировании (D-02).

        Формула: Cmax_increment = dose_mg × F / (Vd × W)

        Args:
            dose_mg: Доза в мг (уже после конвертации IU→мг для vitamin_d3).
            bioavailability: Биодоступность F [0, 1].
            vd_l_kg: Объём распределения в л/кг.
            weight_kg: Вес тела в кг.

        Returns:
            Прирост концентрации в условных единицах (мг/л).

        Raises:
            ValueError: Если vd_l_kg <= 0 или weight_kg <= 0.
        """
        if vd_l_kg <= 0:
            raise ValueError(
                f"vd_l_kg must be positive, got {vd_l_kg}"
            )
        if weight_kg <= 0:
            raise ValueError(
                f"weight_kg must be positive, got {weight_kg}"
            )
        return dose_mg * bioavailability / (vd_l_kg * weight_kg)

    @staticmethod
    def decay_concentration(
        current_c: float,
        ke: float,
        delta_t_hours: float = 1.0,
    ) -> float:
        """Применить экспоненциальный распад концентрации за delta_t тиков (D-01).

        Формула: C_new = C_old × exp(-ke × Δt)

        Args:
            current_c: Текущая концентрация C (≥ 0).
            ke: Константа элиминации (1/час), предрасчитанная через compute_ke.
            delta_t_hours: Длительность тика в часах (по умолчанию 1.0).

        Returns:
            Новая концентрация C_new ≥ 0. При current_c == 0.0 возвращает 0.0.
        """
        if current_c == 0.0:
            return 0.0
        return current_c * math.exp(-ke * delta_t_hours)

    # ------------------------------------------------------------------
    # Метод экземпляра: применение эффектов веществ на биомаркеры (D-04)
    # ------------------------------------------------------------------

    def apply_substance_effects(
        self,
        biomarker_values: dict[str, float],
        substance_concentrations: dict[str, float],
        substance_cmax: dict[str, float],
    ) -> dict[str, float]:
        """Применить эффекты всех активных веществ на биомаркеры (D-04).

        Формула: applied_delta = effectProfile[biomarker] × C(t) / Cmax
        Мутирует biomarker_values in-place для производительности (D-08).

        Args:
            biomarker_values: Словарь текущих значений биомаркеров (мутируется).
            substance_concentrations: Текущие концентрации {sub_id: C}.
            substance_cmax: Максимальные концентрации {sub_id: Cmax}.

        Returns:
            Тот же объект biomarker_values (мутация in-place).
        """
        for sub_id, c in substance_concentrations.items():
            # Пропустить практически нулевые концентрации (оптимизация D-08)
            if c < 1e-12:
                continue

            sub = self.substances.get(sub_id)
            if sub is None:
                continue

            cmax = substance_cmax.get(sub_id, c)
            ratio = c / cmax if cmax > 0 else 0.0

            effect_profile: dict[str, float] = sub.get("effectProfile", {})
            for biomarker_code, base_delta in effect_profile.items():
                if biomarker_code in biomarker_values:
                    biomarker_values[biomarker_code] += base_delta * ratio

        return biomarker_values


# ---------------------------------------------------------------------------
# Модульные функции-алиасы — для совместимости с тест-скелетами Plan 05-01
# (тесты импортируют `from src.engine.pharmacokinetics import compute_decay`)
# ---------------------------------------------------------------------------

def compute_ke(half_life_hours: float) -> float:
    """Алиас PKEngine.compute_ke — для прямого импорта в тестах."""
    return PKEngine.compute_ke(half_life_hours)


def compute_cmax_increment(
    dose_mg: float,
    bioavailability: float,
    vd_l_kg: float,
    weight_kg: float,
) -> float:
    """Алиас PKEngine.compute_cmax_increment — для прямого импорта в тестах."""
    return PKEngine.compute_cmax_increment(dose_mg, bioavailability, vd_l_kg, weight_kg)


def compute_decay(
    current_c: float,
    ke: float,
    delta_t: float = 1.0,
) -> float:
    """Алиас PKEngine.decay_concentration — для прямого импорта в тестах.

    Принимает параметр delta_t (а не delta_t_hours) в соответствии
    с сигнатурой тест-скелетов из Plan 05-01.
    """
    return PKEngine.decay_concentration(current_c, ke, delta_t)
