---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, rng, simulation]
created: 2026-06-23
phase: M7
---

# Детерминированный RNG (Сидирование)

Модуль обеспечивает воспроизводимость симуляции: при одном seed последовательность случайных чисел побитово идентична на любой машине. Реализован в `src/engine/rng.py`.

## Формула/Алгоритм

### Алгоритм Mersenne Twister

Python-класс `random.Random(seed)` реализует алгоритм Mersenne Twister (MT19937). Используется изолированный экземпляр, не связанный с глобальным `random`.

```
rng = SimulationRNG(seed)     → random.Random(seed) внутри
val = rng.random()            → float в [0.0, 1.0), следующее число из MT
```

### Сохранение состояния (get_state)

```
state = rng.get_state()       → self._rng.getstate()
                              → кортеж (~2500 int, непрозрачный)
```

Состояние кортежа фиксирует текущую позицию в последовательности MT. Хранится в `SimulationState.rng_state` перед паузой.

### Восстановление состояния (set_state)

```
rng.set_state(state)          → self._rng.setstate(state)
```

После `set_state` следующий вызов `rng.random()` продолжает последовательность ровно с той же позиции, что была при `get_state`.

### Запрещённые источники случайности

В рамках симуляции запрещено использовать:
- `os.urandom()` — криптографический RNG, не детерминирован
- `datetime.now()` / временные метки — недетерминированы
- `random.random()` (глобальный модуль) — может иметь внешнее состояние

Разрешено: только `SimulationRNG` (локальный изолированный экземпляр).

## Параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `seed` | `int ≥ 0` | Начальное значение. Одинаковый seed → идентичная последовательность |
| `state` | `tuple` | Непрозрачный кортеж состояния MT (~2500 int). Не изменять вручную |

### Сериализация rng_state

При экспорте симуляции (Phase 8, `exporter.py`) кортеж `rng_state` сериализуется в JSON как массив чисел. При импорте массив конвертируется обратно в `tuple` перед `set_state`.

```python
# Экспорт
rng_state_json = list(rng.get_state())  # tuple → list → JSON array

# Импорт
rng.set_state(tuple(rng_state_json))    # JSON array → list → tuple
```

Формат tuple: `(version: int, internalstate: list[int], gauss_next: float | None)`.

## Пример (вход → выход)

**Детерминированность:**
```python
rng1 = SimulationRNG(seed=42)
rng2 = SimulationRNG(seed=42)

vals1 = [rng1.random() for _ in range(5)]
vals2 = [rng2.random() for _ in range(5)]
assert vals1 == vals2  # True — побитово идентично
# [0.6394..., 0.0250..., 0.2759..., 0.2232..., 0.7364...]
```

**Сохранение и восстановление:**
```python
rng = SimulationRNG(seed=42)
_ = rng.random()               # потребить одно число

state = rng.get_state()        # снять состояние
val_before = rng.random()      # = 0.0250...

rng.set_state(state)           # восстановить
val_after = rng.random()       # = 0.0250... (идентично)
assert val_before == val_after  # True
```

## Ограничения

- **Версия Python:** MT19937 стандартизирован, но точная реализация `random.Random` зависит от CPython. Воспроизводимость гарантирована в пределах одной мажорной версии Python.
- **Размер состояния:** кортеж `get_state()` содержит ~625 элементов по 32 бита ≈ 2.5 Кб при сериализации в JSON.
- **Не криптографический:** MT19937 не подходит для задач безопасности; используется только для воспроизводимости симуляции.
- **Один поток:** экземпляр `SimulationRNG` не является потокобезопасным; не используется параллельно из нескольких QThread.

## Ссылки

- [[06 - Engine/Adaptive Stepper]] — run_batch передаёт rng в engine.tick()
- [[06 - Engine/Event Detector]] — PROBABILISTIC события используют `rng.random()` для детерминированных проверок
- [[06 - Engine/Pharmacokinetics Model]] — экспорт SimulationState включает rng_state (связь с exporter.py)
