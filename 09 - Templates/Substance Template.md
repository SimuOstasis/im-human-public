---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
id: {{ID}}
name: {{NAME_EN}}
name_ru: {{NAME_RU}}
category: supplement|nutrient|drug|experimental|lifestyle
evidence_level: high|moderate|low|experimental
dose_unit: mg|mcg|g|IU
min_dose: 0
max_dose: 0
default_dose: 0
half_life_hours: 0
bioavailability: 0.0
tags: [{{TAGS}}]
---

# {{NAME_RU}} (`{{ID}}`)

{{#if category == "drug"}}
> ⚠️ **ЛЕКАРСТВЕННЫЙ ПРЕПАРАТ** — рецептурный. В симуляторе используется только как исследовательская модель.
{{/if}}

> **Категория:** {{CATEGORY}} | **Доказательность:** {{EVIDENCE_LEVEL}}  
> **Диапазон доз:** {{MIN_DOSE}}–{{MAX_DOSE}} {{DOSE_UNIT}} | **T½:** {{HALF_LIFE_HOURS}} ч

---

## Описание

{{ОПИСАНИЕ ВЕЩЕСТВА}}

---

## Фармакокинетика

| Параметр | Значение |
|---------|---------|
| Биодоступность | {{BIOAVAILABILITY * 100}}% |
| Период полувыведения | {{HALF_LIFE_HOURS}} ч |
| Скорость абсорбции | |
| Скорость элиминации | |
| Порог кумуляции | |
| Терапевтическое окно | |

---

## Механизм действия

{{МЕХАНИЗМ}}

---

## Эффекты на биомаркеры

| Биомаркер | Направление | Дельта (игровая) | Уровень доказательности |
|-----------|------------|------------------|------------------------|
| [[02 - Biomarkers/\|]] | ↑/↓ | | |

---

## Эффекты на системы организма

| Система | Направление | Сила | Примечание |
|---------|------------|------|-----------|
| | | | |

---

## Взаимодействия

| Вещество | Тип | Коэффициент | Описание |
|---------|-----|------------|---------|
| [[03 - Substances/\|]] | synergy/antagonism | | |

---

## Противопоказания

`contraindicationTags: []`

---

## Схемы приёма (типичные)

- **Стандартная:** {{DEFAULT_DOSE}} {{DOSE_UNIT}} 1×/сутки
- **Цикловая:** 

---

## Источники

*Связь с mortality KB: [[mortality:{{CONCEPT}}]]*

---

## Исправления

*(append-only)*
