---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, interactions, simulation]
created: 2026-06-23
phase: M7
---

# Резолвер взаимодействий

Модуль разрешает взаимодействия между веществами (синергия, антагонизм, токсичность) и применяет их к биомаркерам на каждом тике симуляции. Реализован в `src/engine/interaction_resolver.py`.

## Формула/Алгоритм

### 1. Синергия (apply_synergy)

Синергия усиливает эффект вещества A на биомаркер, когда вещество B присутствует одновременно. Применяется к пересечению effectProfile биомаркеров обоих веществ.

```
overlap_factor = min(c_a / cmax_a, c_b / cmax_b)   — [0..1], ограничен концентрацией слабейшего
synergy_boost  = base_delta × (coeff - 1.0) × overlap_factor
result         = base_delta + synergy_boost
               = base_delta × (1 + (coeff - 1) × overlap_factor)
```

**Защита от деления на ноль:** если `cmax_a = 0` или `cmax_b = 0`, используется `1.0` как безопасный fallback.

**Граничный случай:** если `c_a ≤ 0` или `c_b ≤ 0` — синергия не применяется, возвращается `base_delta`.

**Пример (coeff = 1.3):**
- При 100% обоих веществ: `overlap_factor = 1.0` → эффект ×1.3
- При 50% обоих: `overlap_factor = 0.5` → эффект ×1.15

### 2. Антагонизм (apply_antagonism)

Антагонизм ослабляет эффект целевого вещества при наличии антагониста. В `InteractionResolver.apply_interactions()` применяется симметрично: A ослабляет B и B ослабляет A.

```
antagonism_fraction = (1 - coeff) × (c_antagonist / cmax_antagonist)
result = base_delta × (1 - antagonism_fraction)
```

**Симметричное применение (A↔B):**
```
Направление A→B: снижение эффекта B на antagonism_fraction_A
Направление B→A: снижение эффекта A на antagonism_fraction_B
```

**Пример (coeff = 0.7, оба на 100%):**
- `antagonism_fraction = (1 - 0.7) × 1.0 = 0.3`
- Каждое направление снижает на 30%
- Суммарный эффект пары ≈ `1 - (1 - 0.3)² ≈ 51%` от исходного

### 3. Самотоксичность (check_self_toxicity)

Когда концентрация вещества превышает `TOXICITY_MULTIPLIER × Cmax`, генерируется CRITICAL событие. Самотоксичность определяется записью в `interactions.json` с `substanceA == substanceB` и `type = "toxicity"`.

```
threshold = cmax × TOXICITY_MULTIPLIER
если c_current >= threshold → CRITICAL SimulationEvent
```

## Параметры

| Константа | Значение | Источник | Описание |
|-----------|----------|----------|----------|
| `TOXICITY_MULTIPLIER` | 2.0 | `interaction_resolver.py:23` | Множитель Cmax для токсического порога |

## Пример (вход → выход)

**Сценарий:** Omega-3 и Berberine действуют синергетически на LDL.

| Параметр | Значение |
|----------|----------|
| `coeff` (synergy) | 1.3 |
| `base_delta` для LDL от Omega-3 | -0.01 ммоль/л/тик |
| `c_a` (Omega-3) / `cmax_a` | 0.8 / 1.0 = 80% |
| `c_b` (Berberine) / `cmax_b` | 0.6 / 1.0 = 60% |

**Расчёт:**
```
overlap_factor = min(0.8, 0.6) = 0.6
synergy_boost  = -0.01 × (1.3 - 1.0) × 0.6 = -0.0018
result         = -0.01 + (-0.0018) = -0.0118 ммоль/л/тик
```

Эффект снижения LDL усиливается на 18% вместо максимального ×1.3 (потому что Berberine только на 60%).

**Сценарий самотоксичности Rapamycin (Cmax = 0.1, текущее = 0.22):**
```
threshold = 0.1 × 2.0 = 0.2
0.22 >= 0.2 → CRITICAL: "rapamycin: концентрация 0.2200 превышает токсический порог 0.2000 (2×Cmax)"
```

## Ограничения

- **Только парные взаимодействия:** не моделируются тройные и более сложные взаимодействия.
- **Симметричная модель антагонизма:** взаимное 30%-ное снижение даёт суммарно ~51% эффекта, что не всегда совпадает с реальной биологией.
- **effectProfile — абсолютные дельты:** взаимодействия применяются к фиксированным дельтам per-tick, не к фармакодинамическим кривым.
- **Нет временной задержки:** синергия/антагонизм мгновенны (нет lag-фазы).
- **Данные из `interactions.json`:** пары веществ и коэффициенты заданы статически; динамически не пересчитываются.

## Ссылки

- [Pharmacokinetics Model](Pharmacokinetics%20Model.md) — концентрации веществ (c_a, c_b, Cmax), используемые в формулах
- [Omega-3](../03%20-%20Substances/Omega-3.md) — пример effectProfile для синергетических расчётов
- [Rapamycin](../03%20-%20Substances/Rapamycin.md) — пример вещества с записью самотоксичности в interactions.json
- [Event Detector](Event%20Detector.md) — генерация CRITICAL событий при токсическом превышении
