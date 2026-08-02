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
| [00 · Inbox](00%20-%20Inbox/) | Входящие материалы | — |
| [01 · Профили](01%20-%20Human%20Profiles/) | Пресетные и пользовательские профили | 3 |
| [02 · Биомаркеры](02%20-%20Biomarkers/) | Справочник биомаркеров (13 категорий) | 24 |
| [03 · Вещества](03%20-%20Substances/) | Вещества и интервенции | 7 |
| [04 · Взаимодействия](04%20-%20Interactions/) | Матрица взаимодействий | 1 |
| [05 · Симуляции](05%20-%20Simulation/) | Сценарии и результаты | 1 |
| [05 · UI Guide](05%20-%20Simulation/UI%20Guide.md) | Документация интерфейса (запуск, панели, скорости) | — |
| [06 · Движок](06%20-%20Engine/) | Архитектура, формулы, цикл тика | 12 |
| [07 · Анализ](07%20-%20Analysis/) | Синтез, допущения и планы развития | 7 |
| [08 · Индексы](08%20-%20Index/) | Каталоги по категориям | — |
| [08 · Индексы → Биомаркеры](08%20-%20Index/Biomarkers%20Index.md) | Индекс биомаркеров по категориям | 1 |
| [04 · Взаимодействия → Индекс](04%20-%20Interactions/Interactions%20Index.md) | Матрица взаимодействий | 1 |
| [09 · Шаблоны](09%20-%20Templates/) | Шаблоны страниц | — |

---

## Биомаркеры MVP (24)

### Липиды
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Холестерин ЛПНП | `ldlC` | [LDL Cholesterol](02%20-%20Biomarkers/01%20-%20Lipids/LDL%20Cholesterol.md) |
| Холестерин ЛПВП | `hdlC` | [HDL Cholesterol](02%20-%20Biomarkers/01%20-%20Lipids/HDL%20Cholesterol.md) |
| Триглицериды | `triglycerides` | [Triglycerides](02%20-%20Biomarkers/01%20-%20Lipids/Triglycerides.md) |
| Аполипопротеин B | `apoB` | [Apolipoprotein B](02%20-%20Biomarkers/01%20-%20Lipids/Apolipoprotein%20B.md) |

### Углеводный обмен
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Глюкоза натощак | `fastingGlucose` | [Fasting Glucose](02%20-%20Biomarkers/02%20-%20Glucose/Fasting%20Glucose.md) |
| Инсулин натощак | `fastingInsulin` | [Fasting Insulin](02%20-%20Biomarkers/02%20-%20Glucose/Fasting%20Insulin.md) |
| HOMA-IR | `homaIr` | [HOMA-IR](02%20-%20Biomarkers/02%20-%20Glucose/HOMA-IR.md) |
| HbA1c | `hba1c` | [HbA1c](02%20-%20Biomarkers/02%20-%20Glucose/HbA1c.md) |

### Воспаление
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| hs-CRP | `hsCrp` | [hs-CRP](02%20-%20Biomarkers/03%20-%20Inflammation/hs-CRP.md) |
| Интерлейкин-6 | `il6` | [Interleukin-6](02%20-%20Biomarkers/03%20-%20Inflammation/Interleukin-6.md) |

### Печень
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| АЛТ | `alt` | [ALT](02%20-%20Biomarkers/04%20-%20Liver/ALT.md) |
| АСТ | `ast` | [AST](02%20-%20Biomarkers/04%20-%20Liver/AST.md) |
| ГГТ | `ggt` | [GGT](02%20-%20Biomarkers/04%20-%20Liver/GGT.md) |
| Альбумин | `albumin` | [Albumin](02%20-%20Biomarkers/04%20-%20Liver/Albumin.md) |

### Почки
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Креатинин | `creatinine` | [Serum Creatinine](02%20-%20Biomarkers/05%20-%20Kidney/Serum%20Creatinine.md) |
| Расчётная СКФ | `egfr` | [eGFR](02%20-%20Biomarkers/05%20-%20Kidney/eGFR.md) |
| UACR | `urineAlbuminCreatinineRatio` | [UACR](02%20-%20Biomarkers/05%20-%20Kidney/UACR.md) |

### Электролиты
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Натрий | `sodium` | [Sodium](02%20-%20Biomarkers/05%20-%20Kidney/Sodium.md) |
| Калий | `potassium` | [Potassium](02%20-%20Biomarkers/05%20-%20Kidney/Potassium.md) |

### Витамины
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| 25(OH)D | `vitaminD25Oh` | [25(OH)D](02%20-%20Biomarkers/08%20-%20Vitamins/25(OH)D.md) |

### Кровь
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Гемоглобин | `hemoglobin` | [Hemoglobin](02%20-%20Biomarkers/06%20-%20Blood%20Count/Hemoglobin.md) |

### Физиология
| Биомаркер | Код | Страница |
|-----------|-----|---------|
| Артериальное давление | `systolicBloodPressure` | [Systolic Blood Pressure](02%20-%20Biomarkers/13%20-%20Telemetry/Systolic%20Blood%20Pressure.md) |
| Пульс покоя | `restingHeartRate` | [Resting Heart Rate](02%20-%20Biomarkers/13%20-%20Telemetry/Resting%20Heart%20Rate.md) |
| HRV | `hrvRmssd` | [HRV RMSSD](02%20-%20Biomarkers/13%20-%20Telemetry/HRV%20RMSSD.md) |

---

## Вещества MVP

Источник истины — `src/data/substances.json` (7 веществ).

| Вещество | `id` | Категория | EvidenceLevel | Страница |
|---------|------|----------|--------------|---------|
| Омега-3 | `omega3` | supplement | high | [Omega-3](03%20-%20Substances/Omega-3.md) |
| Витамин D3 | `vitamin_d3` | supplement | high | [Vitamin D3](03%20-%20Substances/Vitamin%20D3.md) |
| Магний | `magnesium` | supplement | high | [Magnesium](03%20-%20Substances/Magnesium.md) |
| Берберин | `berberine` | supplement | moderate | [Berberine](03%20-%20Substances/Berberine.md) |
| Метформин ⚠️ | `metformin` | drug | high | [Metformin](03%20-%20Substances/Metformin.md) |
| Рапамицин ⚠️ | `rapamycin` | drug | moderate | [Rapamycin](03%20-%20Substances/Rapamycin.md) |
| NMN | `nmn` | supplement | low | [NMN](03%20-%20Substances/NMN.md) |

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

- [Simulation Engine](06%20-%20Engine/Simulation%20Engine.md) — **цикл тика (13 шагов)**, как соединяются все субмодули
- [Pharmacokinetics Model](06%20-%20Engine/Pharmacokinetics%20Model.md) — PK-формулы, таблица Vd, 7 веществ
- [Biological Age Formula](06%20-%20Engine/Biological%20Age%20Formula.md) — частичная PhenoAge, resilience index
- [Homeostasis Model](06%20-%20Engine/Homeostasis%20Model.md) — дрейф, восстановление, lifestyle-бонус
- [Interaction Resolver](06%20-%20Engine/Interaction%20Resolver.md) — синергии, антагонизмы, самотоксичность
- [Event Detector](06%20-%20Engine/Event%20Detector.md) — THRESHOLD_BREACH, вероятностные события (CVD, диабет, CKD)
- [Adaptive Stepper](06%20-%20Engine/Adaptive%20Stepper.md) — should_dose(), скорости x1/x10/x100/x1000/x10000
- [RNG Seeding](06%20-%20Engine/RNG%20Seeding.md) — Mersenne Twister, get_state/set_state, детерминизм
- [User Guide](06%20-%20Engine/User%20Guide.md) — пошаговые инструкции для пользователя
- [Neo4j Backup Restore](06%20-%20Engine/Neo4j%20Backup%20Restore.md) — neo4j-admin dump/load, восстановление в тестовую БД
- [Pip Audit Dependency Scan](06%20-%20Engine/Pip%20Audit%20Dependency%20Scan.md) — разовая проверка requirements.txt на уязвимости, чистый результат
- [UI Performance Benchmark](06%20-%20Engine/UI%20Performance%20Benchmark.md) — замер времени кадра UI дашборда в трёх конфигурациях рендера при высоких скоростях симуляции

---

## 07 - Analysis

- [Simulation Assumptions](07%20-%20Analysis/Simulation%20Assumptions.md) — детерминизм, тик=1 час, линейные дельты
- [Known Limitations](07%20-%20Analysis/Known%20Limitations.md) — ограничения модели, дисклеймер, roadmap v2+
- [Legal Disclaimer Review](07%20-%20Analysis/Legal%20Disclaimer%20Review.md) — исследование практик формулировки дисклеймера (best-practices, НЕ юридическое заключение)
- [Legal Checkpoint - Prescription Disclaimer](07%20-%20Analysis/Legal%20Checkpoint%20-%20Prescription%20Disclaimer.md) — внешний юридический checkpoint по дисклеймеру рецептурных препаратов, не блокирует релиз и НЕ является юридическим заключением
- [Application Development Review_2026-06-28](07%20-%20Analysis/Application%20Development%20Review_2026-06-28.md) — комплексный технический и продуктовый review приложения
- [Milestone v2.1. Development Plan_2026-07-10](07%20-%20Analysis/Milestone%20v2.1.%20Development%20Plan_2026-07-10.md) — GSD Phase 14–16: доверие, UX, воспроизводимость, UI-производительность
- [Milestone v2.2. Development Plan_2026-07-11](07%20-%20Analysis/Milestone%20v2.2.%20Development%20Plan_2026-07-11.md) — GSD Phase 17–21: экспорт результатов, v2-механики, интеграция с mortality/agent

---

## Системные файлы

- [README](README.md) — обзор проекта, установка, запуск, **раздел «Как это работает» для новичков**
- CLAUDE — правила работы
- [MILESTONES](MILESTONES.md) — план разработки
- [LICENSE.txt](LICENSE.txt) — лицензия Apache 2.0
- [log](log.md) — хронологический лог (публичный)
- [README](.neo4j/README.md) — Neo4j документация
- [src/README.md](src/README.md) — документация кода

---

*Последнее обновление: 2026-07-11 — проверен план Milestone v2.1; v2-фичи и межпродуктовая интеграция вынесены в [Milestone v2.2. Development Plan_2026-07-11](07%20-%20Analysis/Milestone%20v2.2.%20Development%20Plan_2026-07-11.md).*
