---
project: im-human
type: index
---

# HOME — im-human: Симулятор биологической модели человека

## License

This work is licensed under the Apache License, Version 2.0. See [LICENSE.txt](LICENSE.txt) for the full text.

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
| [[05 - Simulation/UI Guide\|05 · UI Guide]] | Документация интерфейса (запуск, панели, скорости) | — |
| [[06 - Engine/\|06 · Движок]] | Архитектура, формулы, цикл тика | 10 |
| [[07 - Analysis/\|07 · Анализ]] | Синтез и допущения | 2 |
| [[08 - Index/\|08 · Индексы]] | Каталоги по категориям | — |
| [[08 - Index/Biomarkers Index\|08 · Индексы → Биомаркеры]] | Индекс биомаркеров по категориям | 1 |
| [[04 - Interactions/Interactions Index\|04 · Взаимодействия → Индекс]] | Матрица взаимодействий | 1 |
| [[09 - Templates/\|09 · Шаблоны]] | Шаблоны страниц | — |

---

## Биомаркеры MVP (24)

### Липиды
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Холестерин ЛПНП | `ldlC` | [[02 - Biomarkers/01 - Lipids/LDL Cholesterol]] |
| Холестерин ЛПВП | `hdlC` | [[02 - Biomarkers/01 - Lipids/HDL Cholesterol]] |
| Триглицериды | `triglycerides` | [[02 - Biomarkers/01 - Lipids/Triglycerides]] |
| Аполипопротеин B | `apoB` | [[02 - Biomarkers/01 - Lipids/Apolipoprotein B]] |

### Углеводный обмен
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Глюкоза натощак | `fastingGlucose` | [[02 - Biomarkers/02 - Glucose/Fasting Glucose]] |
| Инсулин натощак | `fastingInsulin` | [[02 - Biomarkers/02 - Glucose/Fasting Insulin]] |
| HOMA-IR | `homaIr` | [[02 - Biomarkers/02 - Glucose/HOMA-IR]] |
| HbA1c | `hba1c` | [[02 - Biomarkers/02 - Glucose/HbA1c]] |

### Воспаление
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| hs-CRP | `hsCrp` | [[02 - Biomarkers/03 - Inflammation/hs-CRP]] |
| Интерлейкин-6 | `il6` | [[02 - Biomarkers/03 - Inflammation/Interleukin-6]] |

### Печень
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| АЛТ | `alt` | [[02 - Biomarkers/04 - Liver/ALT]] |
| АСТ | `ast` | [[02 - Biomarkers/04 - Liver/AST]] |
| ГГТ | `ggt` | [[02 - Biomarkers/04 - Liver/GGT]] |
| Альбумин | `albumin` | [[02 - Biomarkers/04 - Liver/Albumin]] |

### Почки
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Креатинин | `creatinine` | [[02 - Biomarkers/05 - Kidney/Serum Creatinine]] |
| Расчётная СКФ | `egfr` | [[02 - Biomarkers/05 - Kidney/eGFR]] |
| UACR | `urineAlbuminCreatinineRatio` | [[02 - Biomarkers/05 - Kidney/UACR]] |

### Электролиты
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Натрий | `sodium` | [[02 - Biomarkers/05 - Kidney/Sodium]] |
| Калий | `potassium` | [[02 - Biomarkers/05 - Kidney/Potassium]] |

### Витамины
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| 25(OH)D | `vitaminD25Oh` | [[02 - Biomarkers/08 - Vitamins/25(OH)D]] |

### Кровь
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Гемоглобин | `hemoglobin` | [[02 - Biomarkers/06 - Blood Count/Hemoglobin]] |

### Физиология
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Артериальное давление | `systolicBloodPressure` | [[02 - Biomarkers/13 - Telemetry/Systolic Blood Pressure]] |
| Пульс покоя | `restingHeartRate` | [[02 - Biomarkers/13 - Telemetry/Resting Heart Rate]] |
| HRV | `hrvRmssd` | [[02 - Biomarkers/13 - Telemetry/HRV RMSSD]] |

---

## Вещества MVP

Источник истины — `src/data/substances.json` (7 веществ).

| Вещество | `id` | Категория | EvidenceLevel | Страница |
|---------|------|----------|--------------|---------|
| Омега-3 | `omega3` | supplement | high | [[03 - Substances/Omega-3]] |
| Витамин D3 | `vitamin_d3` | supplement | high | [[03 - Substances/Vitamin D3]] |
| Магний | `magnesium` | supplement | high | [[03 - Substances/Magnesium]] |
| Берберин | `berberine` | supplement | moderate | [[03 - Substances/Berberine]] |
| Метформин ⚠️ | `metformin` | drug | high | [[03 - Substances/Metformin]] |
| Рапамицин ⚠️ | `rapamycin` | drug | moderate | [[03 - Substances/Rapamycin]] |
| NMN | `nmn` | supplement | low | [[03 - Substances/NMN]] |

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

- [[06 - Engine/Simulation Engine]] — **цикл тика (13 шагов)**, как соединяются все субмодули
- [[06 - Engine/Pharmacokinetics Model]] — PK-формулы, таблица Vd, 7 веществ
- [[06 - Engine/Biological Age Formula]] — частичная PhenoAge, resilience index
- [[06 - Engine/Homeostasis Model]] — дрейф, восстановление, lifestyle-бонус
- [[06 - Engine/Interaction Resolver]] — синергии, антагонизмы, самотоксичность
- [[06 - Engine/Event Detector]] — THRESHOLD_BREACH, вероятностные события (CVD, диабет, CKD)
- [[06 - Engine/Adaptive Stepper]] — should_dose(), скорости x1/x10/x100/x1000/x10000
- [[06 - Engine/RNG Seeding]] — Mersenne Twister, get_state/set_state, детерминизм
- [[06 - Engine/User Guide]] — пошаговые инструкции для пользователя
- [[06 - Engine/Neo4j Backup Restore]] — neo4j-admin dump/load, восстановление в тестовую БД

---

## 07 - Analysis

- [[07 - Analysis/Simulation Assumptions]] — детерминизм, тик=1 час, линейные дельты
- [[07 - Analysis/Known Limitations]] — ограничения модели, дисклеймер, roadmap v2+
- [[Application Development Review_2026-06-28]] — комплексный технический и продуктовый review приложения

---

## Системные файлы

- [[README.md]] — обзор проекта, установка, запуск, **раздел «Как это работает» для новичков**
- [[CLAUDE.md]] — правила работы
- [[MILESTONES.md]] — план разработки
- [[LICENSE.txt]] — лицензия Apache 2.0
- [[log.md]] — хронологический лог (публичный)
- [[.neo4j/README]] — Neo4j документация
- [[src/README.md]] — документация кода

---

*Последнее обновление: 2026-07-10 — актуализация документации (Phase 10, UX-стабилизация): добавлена страница [[06 - Engine/Simulation Engine]], исправлены таблица веществ, счётчик взаимодействий (6), имена пресетов.*
