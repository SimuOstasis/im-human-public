---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, stepper, simulation]
created: 2026-06-23
phase: M7
---

# Адаптивный степпер

Модуль управляет батч-выполнением тиков симуляции: проверяет расписание доз, прерывает выполнение при паузе/остановке и поддерживает скорости от x1 до x10000. Реализован в `src/engine/adaptive_stepper.py`.

## Формула/Алгоритм

### Алгоритм should_dose() — 4-этапная проверка

Определяет, нужно ли давать дозу на текущем тике (вызывается для каждого `IntakeSchedule`).

**Этапы проверки (последовательно, ранний выход при False):**

```
Этап 1: tick < start_tick           → False  (симуляция ещё не достигла начала расписания)
Этап 2: duration_ticks задан
        и tick >= start_tick + duration_ticks
                                    → False  (расписание истекло)
Этап 3: tick % 24 != hour_of_day   → False  (не тот час дня; тик = час)
Этап 4: CycleConfig проверка:
        day_number  = (tick - start_tick) // 24
        day_in_cycle = day_number % cycle_length  (cycle_length = on_days + off_days)
        если day_in_cycle >= on_days → False (off-фаза цикла)

Иначе → True (доза выдаётся)
```

**Защита от ZeroDivisionError (T-05-10):** если `cycle_length ≤ 0` — этап 4 пропускается (всегда True — always-on).

### Алгоритм run_batch()

Выполняет `num_ticks` тиков последовательно с проверкой статуса ДО и ПОСЛЕ каждого тика:

```
для каждого тика из num_ticks:
    если state.status in (PAUSED, STOPPED) → выйти досрочно
    state = engine.tick(state, schedules)
    если state.status in (PAUSED, STOPPED) → выйти досрочно
вернуть state
```

Двойная проверка гарантирует: если `engine.tick()` поставил на паузу (например, при CRITICAL событии), следующий тик не запустится.

### Скорости выполнения

| Множитель | Тиков за batch | Реальное время (≈1 сек UI) |
|-----------|----------------|---------------------------|
| x1 | 1 | 1 час симуляции |
| x10 | 10 | ~10 часов |
| x100 | 100 | ~4 дня |
| x1000 | 1000 | ~6 недель |
| x10000 | 10000 | ~14 месяцев |

`SPEED_TICKS` — константа словаря `{множитель: num_ticks}`, используется UI для маппинга кнопок.

## Параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `start_tick` | `int` | Тик начала расписания (по умолчанию 0) |
| `duration_ticks` | `int \| None` | Длительность расписания в тиках; `None` = бессрочно |
| `hour_of_day` | `int` | Час дозирования (0–23) |
| `cycle.on_days` | `int` | Количество дней приёма в цикле |
| `cycle.off_days` | `int` | Количество дней перерыва в цикле |
| `num_ticks` | `int` | Количество тиков в одном batch (1..10000) |

## Пример (вход → выход)

**Расписание Rapamycin: on_days=1, off_days=6, hour_of_day=8, start_tick=0**

```
cycle_length = 1 + 6 = 7 (1 раз в неделю)

Тик 8:   tick % 24 = 8 ✓; day_number=0, day_in_cycle=0 < 1 → True  ✓ ДОЗА
Тик 9:   tick % 24 = 9 ≠ 8 → False  ✗ НЕТ ДОЗЫ (не тот час)
Тик 32:  tick % 24 = 8 ✓; day_number=1, day_in_cycle=1 >= 1 → False ✗ НЕТ (off-день)
Тик 56:  tick % 24 = 8 ✓; day_number=2, day_in_cycle=2 >= 1 → False ✗ НЕТ (off-день)
Тик 176: tick % 24 = 8 ✓; day_number=7, day_in_cycle=0 < 1 → True  ✓ ДОЗА (новый цикл)
```

Rapamycin дозируется 1 раз в неделю (каждые 168 тиков = 7 дней).

## Ограничения

- **Фиксированный hourly tick:** 1 тик = 1 час; суб-часовое расписание невозможно.
- **Один hour_of_day:** расписание с несколькими дозами в день требует нескольких объектов `IntakeSchedule`.
- **Stateless:** `AdaptiveStepper` не хранит состояние между вызовами `run_batch`; `engine.tick()` полностью управляет SimulationState.
- **run_batch не Thread-safe:** вызывается из одного QThread; параллельный запуск нескольких batch не предусмотрен.

## Ссылки

- [Pharmacokinetics Model](Pharmacokinetics%20Model.md) — engine.tick() вызывает PK-модель для обновления концентраций
- [RNG Seeding](RNG%20Seeding.md) — rng передаётся в engine.tick() для PROBABILISTIC событий
- [Event Detector](Event%20Detector.md) — CRITICAL событие → state.status = PAUSED → run_batch прерывается
- [Rapamycin](../03%20-%20Substances/Rapamycin.md) — пример CycleConfig on_days=1 off_days=6 для should_dose()
