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
| Холестерин ЛПНП | `ldlC` | mmol/L | Clinical | [[02 - Biomarkers/01 - Lipids/LDL Cholesterol\|ссылка]] |
| Холестерин ЛПВП | `hdlC` | mmol/L | Clinical | [[02 - Biomarkers/01 - Lipids/HDL Cholesterol\|ссылка]] |
| Триглицериды | `triglycerides` | mmol/L | Clinical | [[02 - Biomarkers/01 - Lipids/Triglycerides\|ссылка]] |
| Аполипопротеин B | `apoB` | g/L | Extended | [[02 - Biomarkers/01 - Lipids/Apolipoprotein B\|ссылка]] |

---

## Углеводный обмен (4 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Глюкоза натощак | `fastingGlucose` | mmol/L | Clinical | [[02 - Biomarkers/02 - Glucose/Fasting Glucose\|ссылка]] |
| Инсулин натощак | `fastingInsulin` | mcU/mL | Clinical | [[02 - Biomarkers/02 - Glucose/Fasting Insulin\|ссылка]] |
| Индекс HOMA-IR | `homaIr` | ratio | Calculated | [[02 - Biomarkers/02 - Glucose/HOMA-IR\|ссылка]] |
| HbA1c | `hba1c` | % | Clinical | [[02 - Biomarkers/02 - Glucose/HbA1c\|ссылка]] |

---

## Воспаление (2 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Высокочувствительный СРБ | `hsCrp` | mg/L | Clinical | [[02 - Biomarkers/03 - Inflammation/hs-CRP\|ссылка]] |
| Интерлейкин-6 | `il6` | pg/mL | Research | [[02 - Biomarkers/03 - Inflammation/Interleukin-6\|ссылка]] |

---

## Функция печени (4 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| АЛТ | `alt` | U/L | Clinical | [[02 - Biomarkers/04 - Liver/ALT\|ссылка]] |
| АСТ | `ast` | U/L | Clinical | [[02 - Biomarkers/04 - Liver/AST\|ссылка]] |
| ГГТ | `ggt` | U/L | Clinical | [[02 - Biomarkers/04 - Liver/GGT\|ссылка]] |
| Альбумин | `albumin` | g/L | Clinical | [[02 - Biomarkers/04 - Liver/Albumin\|ссылка]] |

---

## Функция почек (5 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Креатинин | `creatinine` | umol/L | Clinical | [[02 - Biomarkers/05 - Kidney/Serum Creatinine\|ссылка]] |
| Расчётная СКФ | `egfr` | mL/min/1.73m2 | Calculated | [[02 - Biomarkers/05 - Kidney/eGFR\|ссылка]] |
| UACR | `urineAlbuminCreatinineRatio` | mg/g | Clinical | [[02 - Biomarkers/05 - Kidney/UACR\|ссылка]] |
| Натрий | `sodium` | mmol/L | Clinical | [[02 - Biomarkers/05 - Kidney/Sodium\|ссылка]] |
| Калий | `potassium` | mmol/L | Clinical | [[02 - Biomarkers/05 - Kidney/Potassium\|ссылка]] |

---

## Клинический анализ крови (1 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Гемоглобин | `hemoglobin` | g/L | Clinical | [[02 - Biomarkers/06 - Blood Count/Hemoglobin\|ссылка]] |

---

## Витамины и нутриенты (1 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Витамин D | `vitaminD25Oh` | ng/mL | Clinical | [[02 - Biomarkers/08 - Vitamins/25(OH)D\|ссылка]] |

---

## Физиологическая телеметрия (3 биомаркеров)

| Биомаркер | Код | Единицы | Статус | Страница |
|-----------|-----|---------|--------|---------|
| Артериальное давление | `systolicBloodPressure` | mmHg | Clinical | [[02 - Biomarkers/13 - Telemetry/Systolic Blood Pressure\|ссылка]] |
| Пульс покоя | `restingHeartRate` | bpm | Clinical | [[02 - Biomarkers/13 - Telemetry/Resting Heart Rate\|ссылка]] |
| HRV (RMSSD) | `hrvRmssd` | ms | Clinical | [[02 - Biomarkers/13 - Telemetry/HRV RMSSD\|ссылка]] |

---

*Всего: 24 MVP-биомаркера | Сгенерировано: generate_biomarker_pages.py | Обновлено: 2026-06-20*
