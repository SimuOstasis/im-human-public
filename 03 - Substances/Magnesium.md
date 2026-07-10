---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
id: magnesium
name: Magnesium
name_ru: Магний
category: supplement
evidence_level: high
is_drug: false
half_life_hours: 24.0
bioavailability: 0.4
tags: [substance, supplement, magnesium]
---

# Магний (`magnesium`)

> **Категория:** Добавка | **Доказательность:** Высокий | **T½:** 24.0 ч

---

## Описание

Магний — второй по распространённости внутриклеточный катион, кофактор более 300 ферментативных реакций. Регулирует сосудистый тонус, нейромышечную передачу, синтез АТФ и чувствительность к инсулину. Дефицит встречается у 40-60% взрослых.

---

## Фармакокинетика

| Параметр | Значение |
|---------|---------|
| Биодоступность | 40% |
| Период полувыведения | 24.0 ч |
| Скорость абсорбции | 0.15 /тик |
| Скорость элиминации | 0.02890 /тик |
| Диапазон доз | 100–600 mg |
| Доза по умолчанию | 300 mg |

---

## Эффекты на биомаркеры

| Биомаркер | Направление | Дельта/тик (100% конц.) | Ссылка |
|-----------|------------|------------------------|--------|
| [[02 - Biomarkers/13 - Telemetry/Systolic Blood Pressure\|Артериальное давление]] | ↓ | -0.02000 | — |
| [[02 - Biomarkers/13 - Telemetry/HRV RMSSD\|HRV (RMSSD)]] | ↑ | +0.00030 | — |
| [[02 - Biomarkers/02 - Glucose/Fasting Glucose\|Глюкоза натощак]] | ↓ | -0.00200 | — |

> *Дельты — абсолютные изменения на 1 тик при 100% терапевтической концентрации. Движок Phase 5 масштабирует: applied_delta = delta × C(t)/Tmax*

---

## Взаимодействия

Полная матрица: [[04 - Interactions/Interactions Index]]

- **synergy**: с `vitamin_d3` (коэффициент 1.2): Магний необходим для активации витамина D3 (25-OH → 1,25-OH). Дефицит магния снижает эффективность витамина D3 на 20-30%.

---

## Связанные страницы

- [[02 - Biomarkers/13 - Telemetry/Systolic Blood Pressure\|Артериальное давление]]
- [[02 - Biomarkers/13 - Telemetry/HRV RMSSD\|HRV (RMSSD)]]
- [[02 - Biomarkers/02 - Glucose/Fasting Glucose\|Глюкоза натощак]]

---

## Источники

*Связь с mortality KB: [[mortality:Magnesium]]*

---

## Исправления

*(append-only)*
