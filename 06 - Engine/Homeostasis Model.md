---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, homeostasis, simulation]
created: 2026-06-23
phase: M7
---

# Модель гомеостаза

Движок гомеостаза управляет долгосрочным поведением биомаркеров: возрастным дрейфом к деградированным значениям и восстановлением к оптимуму под влиянием образа жизни. Реализован в `src/engine/homeostasis.py`.

## Формула/Алгоритм

### 1. Дрейф (apply_drift)

Каждый тик каждый биомаркер смещается к деградированному значению (соответствующему пожилому возрасту или зоне high_risk). Скорость зависит от возраста и resilience_index.

```
age_factor    = max(0, (age - 30) / 100)
effective_rate = BASE_DRIFT_RATE × (1 + age_factor) × (1 - resilience × 0.5)
drift         = (degraded_value - current_value) × effective_rate
new_value     = current_value + drift
```

**Поведение:**
- При возрасте ≤ 30 лет: `age_factor = 0`, дрейф минимален.
- При возрасте 80 лет: `age_factor = 0.5`, дрейф в 1.5× быстрее.
- Высокий `resilience_index` (= 1.0) снижает дрейф на 50%.

### 2. Восстановление (apply_recovery)

Биомаркеры, отклонившиеся от baseline (например, под воздействием болезни), возвращаются к нему через RECOVERY_RATE каждый тик.

```
gap      = baseline[code] - current_value
recovery = gap × RECOVERY_RATE × resilience_index × (1 + lifestyle_bonus)
new_value = current_value + recovery
```

### 3. Lifestyle-бонус (compute_lifestyle_bonus)

Суммарный бонус образа жизни влияет на скорость восстановления. Зажимается в диапазоне [-0.5, +0.5].

```
stress_penalty  = -stress / 200          (диапазон -0.5..0)
sleep_bonus     = sleep_quality / 200    (диапазон 0..+0.5)
diet_bonus      = diet_quality / 200     (диапазон 0..+0.5)
activity_bonus  = (multiplier - 1.2) / 0.7 × 0.3
alcohol_penalty = -alcohol / 200         (диапазон -0.5..0)
total           = clamp(sum, -0.5, +0.5)
```

Где `multiplier` — множитель физической активности из `PhysicalActivity.multiplier`.

### 4. Инициализация биомаркеров (initialize_biomarkers)

Baseline вычисляется как середина optimal-диапазона по полу и возрастной группе:

```
baseline = (low + high) / 2          — обычный биомаркер
baseline = high                      — если low is None (инвертированный: HDL, eGFR, HRV)
baseline = low × 1.1                 — если high is None (нет верхней границы)
```

## Параметры

| Константа | Значение | Источник | Описание |
|-----------|----------|----------|----------|
| `BASE_DRIFT_RATE` | 0.00002 | `homeostasis.py:28` | Скорость дрейфа/тик при возрасте 30 лет |
| `RECOVERY_RATE` | 0.00005 | `homeostasis.py:29` | Скорость восстановления к baseline/тик |

Пометка `[ASSUMED из RESEARCH.md]` в коде означает, что значения константы приближены на основе биологических наблюдений, не из клинических данных.

## Пример (вход → выход)

**Сценарий:** мужчина 50 лет, LDL холестерин.

| Параметр | Значение |
|----------|----------|
| `age` | 50 |
| `resilience_index` | 0.7 |
| `baseline` (LDL оптимум) | 2.5 ммоль/л |
| `current_value` | 2.5 ммоль/л |
| `degraded_value` (high_risk[0]) | 4.1 ммоль/л |
| `lifestyle_bonus` | +0.1 |

**Расчёт дрейфа за 1 тик:**
```
age_factor    = max(0, (50 - 30) / 100) = 0.2
effective_rate = 0.00002 × (1 + 0.2) × (1 - 0.7 × 0.5)
              = 0.00002 × 1.2 × 0.65 = 0.0000156
drift         = (4.1 - 2.5) × 0.0000156 = +0.000025 ммоль/л/тик
```

**Расчёт восстановления за 1 тик (при gap = 0):**
```
gap      = 2.5 - 2.5 = 0
recovery = 0 × 0.00005 × 0.7 × 1.1 = 0
```

За год (8760 тиков) без интервенций LDL сместится приблизительно на +0.22 ммоль/л.

## Ограничения

- **Линейная модель:** дрейф и восстановление пропорциональны разности; нет нелинейных порогов.
- **Нет циркадных ритмов:** биомаркеры не колеблются в течение суток (1 тик = 1 час, но ритм не моделируется).
- **Единый resilience_index:** одно значение для всех биомаркеров; в реальности стойкость орган-специфична.
- **Constants ASSUMED:** `BASE_DRIFT_RATE` и `RECOVERY_RATE` — приближённые значения, не из клинических испытаний.
- **Нет межбиомаркерных зависимостей** в drift: LDL и инсулинорезистентность не влияют друг на друга напрямую через homeostasis.py (это задача interaction_resolver.py).

## Ссылки

- [[06 - Engine/Pharmacokinetics Model]] — PK-модель, концентрации веществ, которые влияют на биомаркеры через effectProfile
- [[06 - Engine/Interaction Resolver]] — синергии и антагонизмы между веществами, меняющие дельты биомаркеров
- [[02 - Biomarkers/01 - Lipids/LDL Cholesterol]] — пример биомаркера с дрейфом в high_risk зону
- [[06 - Engine/Biological Age Formula]] — формула биологического возраста, зависящая от накопленного дрейфа
