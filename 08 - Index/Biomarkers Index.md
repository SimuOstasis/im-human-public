---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
type: index
category: biomarkers
created: 2026-06-20
---

# Biomarkers Index

> Все 24 MVP-биомаркера симулятора im-human. Источник: `src/data/biomarkers.json`.

---

## Липиды (4 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Холестерин ЛПНП | `ldlC` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/01%20-%20Lipids/LDL%20Cholesterol.md) |
| Холестерин ЛПВП | `hdlC` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/01%20-%20Lipids/HDL%20Cholesterol.md) |
| Триглицериды | `triglycerides` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/01%20-%20Lipids/Triglycerides.md) |
| Аполипопротеин B | `apoB` | g/L | Extended | [ссылка](../02%20-%20Biomarkers/01%20-%20Lipids/Apolipoprotein%20B.md) |

---

## Углеводный обмен (4 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Глюкоза натощак | `fastingGlucose` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/02%20-%20Glucose/Fasting%20Glucose.md) |
| Инсулин натощак | `fastingInsulin` | mcU/mL | Clinical | [ссылка](../02%20-%20Biomarkers/02%20-%20Glucose/Fasting%20Insulin.md) |
| Индекс HOMA-IR | `homaIr` | ratio | Calculated | [ссылка](../02%20-%20Biomarkers/02%20-%20Glucose/HOMA-IR.md) |
| HbA1c | `hba1c` | % | Clinical | [ссылка](../02%20-%20Biomarkers/02%20-%20Glucose/HbA1c.md) |

---

## Воспаление (2 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Высокочувствительный СРБ | `hsCrp` | mg/L | Clinical | [ссылка](../02%20-%20Biomarkers/03%20-%20Inflammation/hs-CRP.md) |
| Интерлейкин-6 | `il6` | pg/mL | Research | [ссылка](../02%20-%20Biomarkers/03%20-%20Inflammation/Interleukin-6.md) |

---

## Функция печени (4 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| АЛТ | `alt` | U/L | Clinical | [ссылка](../02%20-%20Biomarkers/04%20-%20Liver/ALT.md) |
| АСТ | `ast` | U/L | Clinical | [ссылка](../02%20-%20Biomarkers/04%20-%20Liver/AST.md) |
| ГГТ | `ggt` | U/L | Clinical | [ссылка](../02%20-%20Biomarkers/04%20-%20Liver/GGT.md) |
| Альбумин | `albumin` | g/L | Clinical | [ссылка](../02%20-%20Biomarkers/04%20-%20Liver/Albumin.md) |

---

## Функция почек (5 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Креатинин | `creatinine` | umol/L | Clinical | [ссылка](../02%20-%20Biomarkers/05%20-%20Kidney/Serum%20Creatinine.md) |
| Расчётная СКФ | `egfr` | mL/min/1.73m2 | Calculated | [ссылка](../02%20-%20Biomarkers/05%20-%20Kidney/eGFR.md) |
| UACR | `urineAlbuminCreatinineRatio` | mg/g | Clinical | [ссылка](../02%20-%20Biomarkers/05%20-%20Kidney/UACR.md) |
| Натрий | `sodium` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/05%20-%20Kidney/Sodium.md) |
| Калий | `potassium` | mmol/L | Clinical | [ссылка](../02%20-%20Biomarkers/05%20-%20Kidney/Potassium.md) |

---

## Клинический анализ крови (1 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Гемоглобин | `hemoglobin` | g/L | Clinical | [ссылка](../02%20-%20Biomarkers/06%20-%20Blood%20Count/Hemoglobin.md) |

---

## Витамины и нутриенты (1 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Витамин D | `vitaminD25Oh` | ng/mL | Clinical | [ссылка](../02%20-%20Biomarkers/08%20-%20Vitamins/25(OH)D.md) |

---

## Физиологическая телеметрия (3 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Артериальное давление | `systolicBloodPressure` | mmHg | Clinical | [ссылка](../02%20-%20Biomarkers/13%20-%20Telemetry/Systolic%20Blood%20Pressure.md) |
| Пульс покоя | `restingHeartRate` | bpm | Clinical | [ссылка](../02%20-%20Biomarkers/13%20-%20Telemetry/Resting%20Heart%20Rate.md) |
| HRV (RMSSD) | `hrvRmssd` | ms | Clinical | [ссылка](../02%20-%20Biomarkers/13%20-%20Telemetry/HRV%20RMSSD.md) |

---

*Всего: 24 MVP-биомаркера | Сгенерировано: generate_biomarker_pages.py | Обновлено: 2026-06-20*
