---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, biological-age, phenoage, simulation]
created: 2026-06-22
phase: M4
---

# Формула биологического возраста

Частичная реализация PhenoAge (Levine et al. 2018), адаптированная для MVP-24 биомаркеров im-human.

## Базовая формула (полная PhenoAge)

```
PhenoAge = β₁×albumin + β₂×creatinine + β₃×glucose + β₄×log(hsCrp) + β₅×возраст + intercept
```

## Доступные биомаркеры из MVP-24

Из 9 оригинальных биомаркеров PhenoAge в MVP-24 доступны только 4.
Недостающие (Lymphocyte%, MCV, RDW, ALP, WBC) заложены в скорректированный intercept.

| Биомаркер      | Единица MVP-24 | Единица Levine | Конвертация    | Коэффициент β |
| -------------- | -------------- | -------------- | -------------- | ------------- |
| albumin        | g/L            | g/dL           | ÷10            | -0.0336       |
| creatinine     | µmol/L         | mg/dL          | ÷88.4          | +0.0095       |
| fastingGlucose | mmol/L         | mg/dL          | ×18            | +0.1953       |
| hsCrp          | mg/L           | log(mg/dL)     | ÷10, затем log | +0.0954       |

## Коэффициенты в формуле

| Параметр | Значение | Источник |
|----------|----------|----------|
| β_age | 0.0804 | Levine et al. 2018 |
| intercept_partial | +19.0 | \[ASSUMED\] откалиброван под симулятор |
| intercept_original | −19.9067 | Levine 2018 (включает 9 биомаркеров) |

**Calibration note:** intercept_partial = 19.0 откалиброван так, чтобы young_healthy_30m
(с baseline биомаркерами из гомеостатической инициализации) давал biological_age ≈ 30.6 лет.
Базовые значения из reference_ranges: fastingGlucose optimal midpoint = 2.75 mmol/L.

## Ограничения модели

- biological_age ∈ \[1.0, 120.0\] — зажимание применяется к выходу формулы
- Точность: частичная модель (4 из 9 биомаркеров) даёт приближение, не клиническую точность
- Пропущенные биомаркеры будут добавлены в v2 (Lymphocyte%, MCV, RDW, ALP, WBC)

## Resilience Index (D-11)

```
resilience_index = среднее([clamp((b − low) / (high − low), 0, 1) для b в {albumin, eGFR, HRV}])
```

| Биомаркер | low | high | Единица |
|-----------|-----|------|---------|
| albumin | 35.0 | 55.0 | g/L |
| eGFR | 30.0 | 120.0 | мл/мин/1.73м² |
| HRV RMSSD | 15.0 | 80.0 | мс |

**Семантика:** 1.0 = быстрое восстановление (все три биомаркера в верхней части оптимального диапазона), 0.0 = нет восстановления.

Resilience_index влияет на скорость гомеостатического drift и recovery в каждом тике.

## Ссылки

- [[Albumin]] — albumin страница
- [[eGFR]] — eGFR страница
- [[Pharmacokinetics Model]] — PK-модель движка
