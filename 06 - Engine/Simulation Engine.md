---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, simulation, tick, orchestrator]
created: 2026-07-10
phase: v2.0 / M10
---

# Движок симуляции (тиковый цикл)

Центральная страница о том, **как работает движок целиком**: как один «тик» (1 час модельного
времени) проходит через все субмодули и как из этого складывается многолетняя траектория
биомаркеров. Реализован в `src/engine/simulation_engine.py` (класс `SimulationEngine`).

> Это страница-«карта»: она связывает воедино [Pharmacokinetics Model](Pharmacokinetics%20Model.md),
> [Homeostasis Model](Homeostasis%20Model.md), [Interaction Resolver](Interaction%20Resolver.md),
> [Event Detector](Event%20Detector.md), [Biological Age Formula](Biological%20Age%20Formula.md),
> [Adaptive Stepper](Adaptive%20Stepper.md) и [RNG Seeding](RNG%20Seeding.md).

---

## Ключевые понятия

| Понятие | Значение |
|---------|---------|
| **Тик** | Минимальный шаг времени. **1 тик = 1 астрономический час.** |
| **Batch (батч)** | Пачка тиков, выполняемая за одну итерацию UI-цикла. Размер = множитель скорости (×1..×10000). См. [Adaptive Stepper](Adaptive%20Stepper.md). |
| **SimulationState** | Изменяемое состояние: значения биомаркеров, концентрации веществ, Cmax, счётчик тиков, состояние RNG, события. |
| **Baseline** | Базовые значения биомаркеров, вычисленные один раз при инициализации по полу/возрасту профиля. |
| **Детерминизм** | При одинаковом `seed` и профиле результат **побитово идентичен** на любой машине. |

---

## Инициализация (`initialize`)

Перед первым тиком движок один раз готовит стартовое состояние:

1. Загружает `substances.json`, `interactions.json`, `reference_ranges.json` (если не переданы явно).
2. Создаёт субмодули: `SimulationRNG`, `PKEngine`, `HomeostasisEngine`, `InteractionResolver`,
   `EventDetector`, `MortalityRiskEngine`.
3. Вычисляет `baseline_biomarkers` — середину оптимального диапазона по полу/возрасту (D-06).
4. Сразу считает стартовые `resilience_index` и `biological_age` по baseline (WR-06), чтобы
   первый тик работал с реальными значениями, а не с заглушками `1.0`/`None`.
5. Переводит FSM в статус `RUNNING` и сохраняет состояние RNG.

---

## Один тик: 13 шагов (`tick`)

Каждый вызов `tick(state, schedules)` выполняет строго упорядоченный конвейер. Внутри тика
**запрещён** файловый ввод-вывод и создание новых Pydantic-объектов (кроме `SimulationEvent`) —
это требование производительности и детерминизма.

```mermaid
flowchart TD
    A["Вход: state (RUNNING) + schedules"] --> G{"status == RUNNING?"}
    G -- нет --> ERR["ValueError (T-05-12)"]
    G -- да --> R["Восстановить состояние RNG"]
    R --> S1["1. Время: tick_count += 1, +1 час"]
    S1 --> S2["2. Дозы по расписанию → прирост концентраций (Cmax increment)"]
    S2 --> S3["3. Экспоненциальный PK-распад: C = C·e^(−ke)"]
    S3 --> S4["4. Эффекты веществ на биомаркеры: Δ = effect × C/Cmax"]
    S4 --> S5["5. Взаимодействия: синергии и антагонизмы"]
    S5 --> S6["6. Гомеостаз: дрейф к деградации + восстановление к baseline"]
    S6 --> S7["7. Зажим значений в [0, max_safe] (D-08)"]
    S7 --> S8["8. Пороговые события THRESHOLD_BREACH"]
    S8 --> S9["9. Вероятностные события (CVD, диабет, почки, гипертония)"]
    S9 --> S10["10. Пересчёт биологического возраста"]
    S10 --> S11["11. Пересчёт resilience_index"]
    S11 --> S12{"12. Есть CRITICAL?"}
    S12 -- да --> P["RUNNING → PAUSED (D-15)"]
    S12 -- нет --> S13
    P --> S13["13. Сохранить состояние RNG (T-05-13)"]
    S13 --> OUT["Выход: обновлённый state"]
```

### Пошаговое описание

| Шаг | Что делает | Модуль |
|-----|-----------|--------|
| **0** | Проверяет `status == RUNNING` (иначе `ValueError`), восстанавливает `rng_state` для детерминизма при pause/resume | `simulation_engine` / [RNG](RNG%20Seeding.md) |
| **1** | Увеличивает `tick_count` и модельное время на 1 час; очищает список событий тика | — |
| **2** | Для каждого расписания проверяет `should_dose()`; при выдаче дозы конвертирует единицы (IU→мг), считает прирост концентрации `ΔC = D·F/(Vd·W)`, обновляет `Cmax` | [Stepper](Adaptive%20Stepper.md) + [PK](Pharmacokinetics%20Model.md) |
| **3** | Экспоненциально уменьшает концентрацию каждого вещества: `C·e^(−ke)`; удаляет концентрации неизвестных веществ | [PK](Pharmacokinetics%20Model.md) |
| **4** | Применяет эффекты веществ на биомаркеры пропорционально `C/Cmax` | [PK](Pharmacokinetics%20Model.md) |
| **5** | Усиливает (синергия) или ослабляет (антагонизм) дельты у пересекающихся биомаркеров | [Interactions](Interaction%20Resolver.md) |
| **6** | Возрастной дрейф к «деградированным» значениям + восстановление к baseline с учётом resilience и образа жизни | [Homeostasis](Homeostasis%20Model.md) |
| **7** | Зажимает все биомаркеры в безопасные границы `[0, max_safe]` | `simulation_engine` (D-08) |
| **8** | Сравнивает значения с зоной `high_risk` → `WARNING`/`CRITICAL` | [Events](Event%20Detector.md) |
| **9** | Проверяет вероятностные риски через `rng.random()` | [Events](Event%20Detector.md) |
| **10** | Обновляет `biological_age` (частичная PhenoAge) | [Bio-Age](Biological%20Age%20Formula.md) |
| **11** | Обновляет `resilience_index` (albumin, eGFR, HRV) | [Bio-Age](Biological%20Age%20Formula.md) |
| **12** | Если появилось `CRITICAL`-событие — переводит FSM `RUNNING → PAUSED` | `simulation_engine` (D-15) |
| **13** | Сохраняет состояние RNG в `state.rng_state` | [RNG](RNG%20Seeding.md) |

> **Порядок важен.** Сначала «внешние» силы (дозы → распад → эффекты → взаимодействия), затем
> «внутренние» (гомеостаз), затем зажим, и только потом — детектирование событий по уже
> финальным значениям тика.

---

## Как тики складываются в батчи

UI не вызывает `tick()` напрямую. Между UI и движком стоит [Adaptive Stepper](Adaptive%20Stepper.md):

```mermaid
flowchart LR
    UI["UI: выбрана скорость ×N"] --> W["SimulationWorker (QThread)"]
    W --> B["AdaptiveStepper.run_batch(N тиков)"]
    B --> T1["tick()"] --> T2["tick()"] --> Tn["… N раз"]
    Tn --> E["state_updated → перерисовка ≈5 fps"]
    B -. "CRITICAL/PAUSED/STOPPED" .-> STOP["Ранний выход из батча"]
```

- Множитель скорости = число тиков в одном батче: ×1 → 1, … ×10000 → 10000.
- Движок работает в фоновом потоке `QThread` — интерфейс не зависает даже на ×10000.
- Если внутри батча возник `CRITICAL` (шаг 12 → PAUSED), батч прерывается досрочно.

---

## Автопауза при критических событиях (FSM)

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> RUNNING: Запустить
    RUNNING --> PAUSED: Пауза / CRITICAL-событие
    PAUSED --> RUNNING: Возобновить
    RUNNING --> STOPPED: Сброс
    PAUSED --> STOPPED: Сброс из паузы (через RUNNING)
    STOPPED --> [*]
```

Критическое событие (например, биомаркер ушёл далеко за порог `high_risk` или гипертонический
криз) автоматически ставит симуляцию на паузу и показывает диалог в UI.

---

## Границы ответственности

- `SimulationEngine` **только оркестрирует** — вся предметная логика в субмодулях.
- Внутри `tick()` нет файлового I/O и сети (`biological_age` считается локально, T-05-14).
- Экспорт/восстановление состояния (включая `rng_state`) — отдельный модуль
  `src/engine/exporter.py`, см. [User Guide](User%20Guide.md).

---

## Ссылки

- [Pharmacokinetics Model](Pharmacokinetics%20Model.md) — шаги 2–4 (дозы, распад, эффекты)
- [Interaction Resolver](Interaction%20Resolver.md) — шаг 5 (синергии/антагонизмы)
- [Homeostasis Model](Homeostasis%20Model.md) — шаг 6 (дрейф/восстановление)
- [Event Detector](Event%20Detector.md) — шаги 8–9 (события)
- [Biological Age Formula](Biological%20Age%20Formula.md) — шаги 10–11 (возраст/устойчивость)
- [Adaptive Stepper](Adaptive%20Stepper.md) — батчи и скорости
- [RNG Seeding](RNG%20Seeding.md) — детерминизм (шаги 0 и 13)
- [Simulation Assumptions](../07%20-%20Analysis/Simulation%20Assumptions.md) — почему модель устроена именно так
