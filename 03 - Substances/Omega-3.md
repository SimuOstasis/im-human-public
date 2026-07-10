---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
id: omega3
name: Omega-3 Fatty Acids
name_ru: Омега-3 жирные кислоты
category: supplement
evidence_level: high
is_drug: false
half_life_hours: 72.0
bioavailability: 0.85
tags: [substance, supplement, omega3]
---

# Омега-3 жирные кислоты (`omega3`)

> **Категория:** Добавка | **Доказательность:** Высокий | **T½:** 72.0 ч

---

## Описание

Омега-3 полиненасыщенные жирные кислоты (EPA и DHA) — незаменимые липиды морского происхождения. Снижают уровень триглицеридов, оказывают противовоспалительное действие через ингибирование арахидонового каскада и активацию PPAR-γ. Улучшают вариабельность сердечного ритма.

---

## Фармакокинетика

| Параметр | Значение |
|---------|---------|
| Биодоступность | 85% |
| Период полувыведения | 72.0 ч |
| Скорость абсорбции | 0.12 /тик |
| Скорость элиминации | 0.00960 /тик |
| Диапазон доз | 500–4000 mg |
| Доза по умолчанию | 2000 mg |

---

## Эффекты на биомаркеры

| Биомаркер | Направление | Дельта/тик (100% конц.) | Ссылка |
|-----------|------------|------------------------|--------|
| [[02 - Biomarkers/01 - Lipids/LDL Cholesterol\|Холестерин ЛПНП]] | ↓ | -0.00300 | — |
| [[02 - Biomarkers/01 - Lipids/Triglycerides\|Триглицериды]] | ↓ | -0.00500 | — |
| [[02 - Biomarkers/01 - Lipids/HDL Cholesterol\|Холестерин ЛПВП]] | ↑ | +0.00100 | — |
| [[02 - Biomarkers/03 - Inflammation/hs-CRP\|Высокочувствительный СРБ]] | ↓ | -0.00100 | — |
| [[02 - Biomarkers/13 - Telemetry/HRV RMSSD\|HRV (RMSSD)]] | ↑ | +0.00020 | — |

> *Дельты — абсолютные изменения на 1 тик при 100% терапевтической концентрации. Движок Phase 5 масштабирует: applied_delta = delta × C(t)/Tmax*

---

## Взаимодействия

Полная матрица: [[04 - Interactions/Interactions Index]]

- **synergy**: с `vitamin_d3` (коэффициент 1.3): Омега-3 и Витамин D3 совместно усиливают противовоспалительный эффект через разные механизмы (EPA/DHA и VDR-путь). hs-CRP снижается сильнее при совместном приёме.

---

## Связанные страницы

- [[02 - Biomarkers/01 - Lipids/LDL Cholesterol\|Холестерин ЛПНП]]
- [[02 - Biomarkers/01 - Lipids/Triglycerides\|Триглицериды]]
- [[02 - Biomarkers/01 - Lipids/HDL Cholesterol\|Холестерин ЛПВП]]
- [[02 - Biomarkers/03 - Inflammation/hs-CRP\|Высокочувствительный СРБ]]
- [[02 - Biomarkers/13 - Telemetry/HRV RMSSD\|HRV (RMSSD)]]

---

## Источники

*Связь с mortality KB: [[mortality:Omega-3 Fatty Acids]]*

---

## Исправления

*(append-only)*
