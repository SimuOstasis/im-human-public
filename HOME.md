---
project: im-human
type: index
---

# HOME — im-human: Симулятор биологической модели человека

## License

This work is licensed under the Apache License, Version 2.0. See [[LICENSE.txt]] for the full text.

Copyright © 2026 Vladimir Bazhin. Contact: info@simuostasis.com

> Визуальная и физическая симуляция воздействия веществ и интервенций на условную биологическую модель человека.  
> Стек: Python · PySide6 · Obsidian · Neo4j  
> ⚠️ Исследовательская симуляция, не медицинский инструмент.

---

## Навигация

| Раздел | Описание | Страниц |
|--------|---------|---------|
| [[00 - Inbox/\|00 · Inbox]] | Входящие материалы | — |
| [[01 - Human Profiles/\|01 · Профили]] | Пресетные и пользовательские профили | 3 |
| [[02 - Biomarkers/\|02 · Биомаркеры]] | Справочник биомаркеров (13 категорий) | 24 |
| [[03 - Substances/\|03 · Вещества]] | Вещества и интервенции | 7 |
| [[04 - Interactions/\|04 · Взаимодействия]] | Матрица взаимодействий | 1 |
| [[05 - Simulation/\|05 · Симуляции]] | Сценарии и результаты | 1 |
| [[UI Guide\|05 · UI Guide]] | Документация интерфейса (запуск, панели, скорости) | — |
| [[06 - Engine/\|06 · Движок]] | Архитектура, формулы, цикл тика | 11 |
| [[07 - Analysis/\|07 · Анализ]] | Синтез, допущения и планы развития | 6 |
| [[08 - Index/\|08 · Индексы]] | Каталоги по категориям | — |
| [[Biomarkers Index\|08 · Индексы → Биомаркеры]] | Индекс биомаркеров по категориям | 1 |
| [[Interactions Index\|04 · Взаимодействия → Индекс]] | Матрица взаимодействий | 1 |
| [[09 - Templates/\|09 · Шаблоны]] | Шаблоны страниц | — |

---

## Биомаркеры MVP (24)

### Липиды
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Холестерин ЛПНП | `ldlC` | [[LDL Cholesterol]] |
| Холестерин ЛПВП | `hdlC` | [[HDL Cholesterol]] |
| Триглицериды | `triglycerides` | [[Triglycerides]] |
| Аполипопротеин B | `apoB` | [[Apolipoprotein B]] |

### Углеводный обмен
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Глюкоза натощак | `fastingGlucose` | [[Fasting Glucose]] |
| Инсулин натощак | `fastingInsulin` | [[Fasting Insulin]] |
| HOMA-IR | `homaIr` | [[HOMA-IR]] |
| HbA1c | `hba1c` | [[HbA1c]] |

### Воспаление
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| hs-CRP | `hsCrp` | [[hs-CRP]] |
| Интерлейкин-6 | `il6` | [[Interleukin-6]] |

### Печень
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| АЛТ | `alt` | [[ALT]] |
| АСТ | `ast` | [[AST]] |
| ГГТ | `ggt` | [[GGT]] |
| Альбумин | `albumin` | [[Albumin]] |

### Почки
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Креатинин | `creatinine` | [[Serum Creatinine]] |
| Расчётная СКФ | `egfr` | [[eGFR]] |
| UACR | `urineAlbuminCreatinineRatio` | [[UACR]] |

### Электролиты
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Натрий | `sodium` | [[Sodium]] |
| Калий | `potassium` | [[Potassium]] |

### Витамины
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| 25(OH)D | `vitaminD25Oh` | [[25(OH)D]] |

### Кровь
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Гемоглобин | `hemoglobin` | [[Hemoglobin]] |

### Физиология
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Артериальное давление | `systolicBloodPressure` | [[Systolic Blood Pressure]] |
| Пульс покоя | `restingHeartRate` | [[Resting Heart Rate]] |
| HRV | `hrvRmssd` | [[HRV RMSSD]] |

---

## Вещества MVP

Источник истины — `src/data/substances.json` (7 веществ).

| Вещество | `id` | Категория | EvidenceLevel | Страница |
|---------|------|----------|--------------|---------|
| Омега-3 | `omega3` | supplement | high | [[Omega-3]] |
| Витамин D3 | `vitamin_d3` | supplement | high | [[Vitamin D3]] |
| Магний | `magnesium` | supplement | high | [[Magnesium]] |
| Берберин | `berberine` | supplement | moderate | [[Berberine]] |
| Метформин ⚠️ | `metformin` | drug | high | [[Metformin]] |
| Рапамицин ⚠️ | `rapamycin` | drug | moderate | [[Rapamycin]] |
| NMN | `nmn` | supplement | low | [[NMN]] |

---

## Внутренние индексы движка

| Индекс | Код | Диапазон |
|--------|-----|---------|
| Окислительный стресс | `oxidativeStressIndex` | 0–100 |
| Системное воспаление | `systemicInflammationIndex` | 0–100 |
| Чувствительность к инсулину | `insulinSensitivityIndex` | 0–100 |
| Аутофагия | `autophagyActivity` | 0–100 |
| Нагрузка стареющих клеток | `senescentCellBurden` | 0–100 |
| Биологический возраст | `biologicalAge` | лет |

---

## 06 - Engine

- [[Simulation Engine]] — **цикл тика (13 шагов)**, как соединяются все субмодули
- [[Pharmacokinetics Model]] — PK-формулы, таблица Vd, 7 веществ
- [[Biological Age Formula]] — частичная PhenoAge, resilience index
- [[Homeostasis Model]] — дрейф, восстановление, lifestyle-бонус
- [[Interaction Resolver]] — синергии, антагонизмы, самотоксичность
- [[Event Detector]] — THRESHOLD_BREACH, вероятностные события (CVD, диабет, CKD)
- [[Adaptive Stepper]] — should_dose(), скорости x1/x10/x100/x1000/x10000
- [[RNG Seeding]] — Mersenne Twister, get_state/set_state, детерминизм
- [[User Guide]] — пошаговые инструкции для пользователя
- [[Neo4j Backup Restore]] — neo4j-admin dump/load, восстановление в тестовую БД
- [[Pip Audit Dependency Scan]] — разовая проверка requirements.txt на уязвимости, чистый результат

---

## 07 - Analysis

- [[Simulation Assumptions]] — детерминизм, тик=1 час, линейные дельты
- [[Known Limitations]] — ограничения модели, дисклеймер, roadmap v2+
- [[Legal Disclaimer Review]] — исследование практик формулировки дисклеймера (best-practices, НЕ юридическое заключение)
- [[Application Development Review_2026-06-28]] — комплексный технический и продуктовый review приложения
- [[Milestone v2.1. Development Plan_2026-07-10]] — GSD Phase 14–16: доверие, UX, воспроизводимость, UI-производительность
- [[Milestone v2.2. Development Plan_2026-07-11]] — GSD Phase 17–21: экспорт результатов, v2-механики, интеграция с mortality/agent

---

## Системные файлы

- [[README]] — обзор проекта, установка, запуск, **раздел «Как это работает» для новичков**
- [[CLAUDE]] — правила работы
- [[MILESTONES]] — план разработки
- [[LICENSE.txt]] — лицензия Apache 2.0
- [[log]] — хронологический лог (публичный)
- [[.neo4j/README]] — Neo4j документация
- [[src/README.md]] — документация кода

---

*Последнее обновление: 2026-07-11 — проверен план Milestone v2.1; v2-фичи и межпродуктовая интеграция вынесены в [[Milestone v2.2. Development Plan_2026-07-11]].*
