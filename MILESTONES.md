# MILESTONES — im-human: Симулятор биологической модели человека

## License

This work is licensed under the Apache License, Version 2.0. See [[LICENSE.txt]] for the full text.

Copyright © 2026 Vladimir Bazhin. Contact: info@simuostasis.com

**Проект:** im-human  
**Стек:** Python · PySide6 · Obsidian · Neo4j  
**Дата создания:** 2026-06-18  
**Разработка через:** GSD plugin

---

## Обзор

```
M0  Foundation & Infrastructure     [Неделя 1]     ████░░░░░░
M1  Data Layer — Biomarkers         [Неделя 1-2]   ░░░░░░░░░░
M2  Human Profile Model             [Неделя 2]     ░░░░░░░░░░
M3  Substance & Intervention Model  [Неделя 2-3]   ░░░░░░░░░░
M4  Simulation Engine               [Неделя 3-4]   ░░░░░░░░░░
M5  Visual Interface (PySide6)      [Неделя 4-5]   ░░░░░░░░░░
M6  Knowledge Base Integration      [Неделя 5-6]   ░░░░░░░░░░
M7  Export, Tests & Documentation   [Неделя 6]     ░░░░░░░░░░
```

---

## M0 · Foundation & Infrastructure

**Цель:** Проект запускается, Neo4j подключён, структура вики и Python окружение готовы.  
**Критерий готовности:** `check_connection.py` проходит, `pip install -r requirements.txt` работает, все папки созданы.

### Задачи

- [x] M0.1 — Создать структуру папок Obsidian (`00-09`, `src/`, `.neo4j/`, `.planning/`)
- [x] M0.2 — Написать `CLAUDE.md` (правила вики и архитектура)
- [x] M0.3 — Создать `HOME.md` (каталог всех страниц)
- [x] M0.4 — Создать `log.md` (append-only лог операций)
- [x] M0.5 — Настроить `.neo4j/.env` (подключение к базе `Human`)
- [ ] M0.6 — Адаптировать `ingest_wiki.py` из mortality для базы `Human`
- [x] M0.7 — Адаптировать `query_wiki.py` для базы `Human`
- [x] M0.8 — Написать `setup_schema.py` (создать схему Neo4j: узлы, индексы, constraints)
- [x] M0.9 — Создать `requirements.txt` (`neo4j`, `pyside6`, `pyyaml`, `sentence-transformers`, `pydantic`, `pytest`)
- [x] M0.10 — Написать `check_connection.py` и проверить подключение
- [ ] M0.11 — Инициализировать git репозиторий + `.gitignore`
- [x] M0.12 — Создать `.planning/PROJECT.md` для GSD

### Выходные артефакты

- `CLAUDE.md`, `HOME.md`, `log.md`, `MILESTONES.md`
- `.neo4j/` с полным набором скриптов
- `requirements.txt`
- Neo4j база `Human` с пустой схемой

---

## M1 · Data Layer — Biomarkers

**Цель:** Все 150+ биомаркеров из `Биомаркеры_v1.txt` представлены в вики и Neo4j.  
**Критерий готовности:** `query_facts.py "HOMA-IR"` возвращает страницу с формулой, референсными диапазонами и ссылками на связанные биомаркеры.

### Задачи

- [x] M1.1 — Создать шаблон `09 - Templates/Biomarker Template.md`
- [x] M1.2 — Парсить `Биомаркеры_v1.txt` → структурированные данные (Python скрипт)
- [x] M1.3 — Создать страницы для 24 MVP-биомаркеров в `02 - Biomarkers/`
- [x] M1.4 — Создать `src/data/biomarkers.json` (машиночитаемый справочник)
- [x] M1.5 — Создать `src/data/reference_ranges.json` (optimal / borderline / high_risk по полу и возрасту)
- [x] M1.6 — Определить Neo4j схему `:Biomarker`, `:BiomarkerCategory`, `:Organ`
- [x] M1.7 — Написать `ingest_biomarkers.py` — загрузка биомаркеров в Neo4j
- [x] M1.8 — Загрузить все 24 MVP-биомаркера в Neo4j, проверить запросами
- [x] M1.9 — Создать индексные страницы по категориям (`08 - Index/Biomarkers Index.md`)
- [x] M1.10 — Обновить `HOME.md`

### Структура страницы биомаркера

```markdown
---
code: ldlC
category: lipids
units: мг/дл или ммоль/л
status: Клинический
organs: [cardiovascular]
tags: [lipids, cardiovascular-risk]
---
# Холестерин ЛПНП (LDL-C)
## Описание | Референсные диапазоны | Формула | Связанные биомаркеры | Исправления
```

### Выходные артефакты

- 24 страницы биомаркеров MVP в `02 - Biomarkers/`
- `src/data/biomarkers.json`
- `src/data/reference_ranges.json`
- Neo4j: `:Biomarker` узлы с вектор-эмбеддингами

---

## M2 · Human Profile Model

**Цель:** Python dataclass `HumanProfile` со всеми параметрами из Требований_1.txt; Obsidian-шаблон для хранения профилей.  
**Критерий готовности:** Создать профиль через код → сохранить в Obsidian → загрузить из файла без потерь.

### Задачи

- [x] M2.1 — Написать `src/domain/human_profile.py` (Pydantic BaseModel)
- [x] M2.2 — Реализовать разделы: Demographics, Physiology, Lifestyle, Predispositions, OrganSystems
- [x] M2.3 — Написать `src/domain/units.py` (конвертации единиц: ммоль/л ↔ мг/дл, и др.)
- [x] M2.4 — Написать `src/domain/simulation_state.py` (FSM: idle→configured→running→paused→completed→failed)
- [x] M2.5 — Реализовать расчёт BMI и BMR из профиля
- [x] M2.6 — Создать шаблон `09 - Templates/Human Profile Template.md`
- [x] M2.7 — Создать 3 пресетных профиля: `Молодой здоровый 30M`, `Средний возраст 50F`, `Пожилой 70M`
- [x] M2.8 — Записать пресеты в Obsidian и Neo4j (`01 - Human Profiles/`)
- [x] M2.9 — Написать тесты `src/tests/test_human_profile.py`

### Параметры HumanProfile (ключевые)

```python
class HumanProfile(BaseModel):
    # Demographics
    sex: Literal["male", "female", "unspecified"]
    age: int  # 18-100
    height_cm: float  # 130-220
    weight_kg: float  # 35-250
    # Physiology
    body_fat_pct: float  # 3-65
    bmr_kcal: float  # расчётный
    metabolism_rate: float  # 0.5-1.5
    methylation_speed: Literal["slow", "normal", "fast"]
    autophagy_efficiency: Literal["low", "normal", "high"]
    # Lifestyle (0-100)
    stress: float; sleep_quality: float; diet_quality: float
    alcohol: float
    physical_activity: Literal["sedentary","low","moderate","high","athlete"]
    smoking: Literal["none","former","active"]
    # Predispositions (0-1)
    cvd_risk: float; diabetes_risk: float; neuro_risk: float
    liver_risk: float; kidney_risk: float
    # Organ Systems (0-100)
    cardiovascular: float; liver: float; kidney: float
    nervous: float; immune: float; metabolic: float
    cellular_repair: float
    # Derived indices
    biological_age: float
    inflammation_index: float
    oxidative_stress_index: float
    toxic_burden: float
    resilience_index: float
```

### Выходные артефакты

- `src/domain/human_profile.py`
- `src/domain/units.py`
- `src/domain/simulation_state.py`
- 3 пресетных профиля в Obsidian
- Neo4j: `:HumanProfile` узлы

---

## M3 · Substance & Intervention Model

**Цель:** 7+ веществ настроены с фармакокинетикой, взаимодействиями и уровнями доказательности. Данные хранятся в JSON и Neo4j.  
**Критерий готовности:** Запрос `query_facts.py "рапамицин mTOR"` возвращает эффекты и взаимодействия.

### Задачи

- [x] M3.1 — Написать `src/domain/substance.py` (SubstanceDefinition, IntakeSchedule)
- [x] M3.2 — Создать `src/data/substances.json` с 7 веществами MVP
- [x] M3.3 — Создать `src/data/interactions.json` (матрица synergy/antagonism/toxicity)
- [x] M3.4 — Написать страницы в `03 - Substances/` для каждого вещества
- [x] M3.5 — Определить Neo4j схему `:Substance`, `:Interaction`, `:Effect`
- [x] M3.6 — Написать `ingest_substances.py` — загрузка веществ в Neo4j
- [x] M3.7 — Проверить перекрёстные ссылки: вещество → биомаркер → орган
- [x] M3.8 — Создать страницы взаимодействий в `04 - Interactions/`
- [x] M3.9 — Написать тесты для SubstanceDefinition

### Вещества MVP

> Фактический состав `src/data/substances.json` (обновлено 2026-07-10; ранняя версия плана называла
> берберин «ресвератролом» — исправлено).

| Вещество | Категория | EvidenceLevel | Особенности |
|---------|----------|--------------|------------|
| Омега-3 | supplement | high | triglycerides ↓, inflammation ↓ |
| Витамин D3 | supplement | high | immune, bone |
| Магний | supplement | high | glucose, sleep, АД ↓ |
| Берберин | supplement | moderate | AMPK, glucose ↓, липиды ↓ |
| Метформин | **drug** ⚠️ | high | mTOR/AMPK, glucose |
| Рапамицин | **drug** ⚠️ | moderate | mTOR inhibitor |
| NMN | supplement | low | NAD+ precursor |

### Выходные артефакты

- `src/data/substances.json`, `src/data/interactions.json`
- 7+ страниц в `03 - Substances/`
- Neo4j: `:Substance`, `:Interaction`, `:Effect` узлы

---

## M4 · Simulation Engine

**Цель:** Детерминированный, воспроизводимый симуляционный движок в Python. Тик = 1 час. Все 13 шагов тика реализованы.  
**Критерий готовности:** Симуляция 1 года с одинаковым seed → одинаковый результат. Отклонение агрегированного шага от почасового ≤ 2% по ключевым индексам.

### Задачи

- [x] M4.1 — Написать `src/engine/rng.py` (seed-based LCG или Mersenne Twister обёртка)
- [x] M4.2 — Написать `src/engine/pharmacokinetics.py` (абсорбция, Vd, T½, выведение, кумуляция)
- [x] M4.3 — Написать `src/engine/homeostasis.py` (базовый износ, восстановление, образ жизни)
- [x] M4.4 — Написать `src/engine/interaction_resolver.py` (synergy, antagonism, toxicity)
- [x] M4.5 — Написать `src/engine/event_detector.py` (события с вероятностями из состояния модели)
- [x] M4.6 — Написать `src/engine/adaptive_stepper.py` (x1/x10/x100/x1000/x10000 + дробление)
- [x] M4.7 — Написать главный `src/engine/simulation_engine.py` (оркестрация 13 шагов тика)
- [x] M4.8 — Написать `src/engine/mortality_risk.py` (biological_age, resilience_index)
- [x] M4.9 — Написать тесты: период полувыведения, отсутствие NaN, граничные значения 0-100
- [x] M4.10 — Написать тесты: воспроизводимость по seed, пауза/возобновление
- [x] M4.11 — Написать тесты: синергия, антагонизм, токсический порог
- [x] M4.12 — Benchmark-тест: 1 модельный год за < 5 сек, отклонение ≤ 2%
- [x] M4.13 — Задокументировать все формулы в `06 - Engine/`

### Формула тика (каждый орган)

```python
next_health = clamp(
    current_health
    + recovery_rate(profile)           # сон, образ жизни
    + substance_benefits               # суммарный эффект веществ
    - age_related_wear(age)            # нелинейный с возрастом
    - lifestyle_damage(profile)        # стресс, алкоголь, курение
    - toxicity_damage                  # кумулятивная токсичность
    + random_event_delta(seed),        # стохастика
    0.0, 100.0
)
```

### Шаги тика движка

```
1. Определить приёмы веществ
2. Обновить концентрации (PK)
3. Рассчитать абсорбцию и выведение
4. Определить кумуляцию
5. Рассчитать взаимодействия
6. Применить полезные эффекты
7. Применить токсические эффекты
8. Рассчитать возрастной износ
9. Применить влияние сна, стресса, активности
10. Обновить здоровье систем
11. Ограничить показатели [0, 100]
12. Обнаружить события
13. Обновить biologicalAge и интегральные индексы
```

### Выходные артефакты

- `src/engine/*.py` (8 модулей)
- `src/tests/test_*.py` (≥ 12 тестов)
- `06 - Engine/` — документация формул

---

## M5 · Visual Interface (PySide6)

**Цель:** Работающее десктопное приложение с 4 основными зонами UI. Симуляция не блокирует UI (threading).  
**Критерий готовности:** Запустить приложение, создать профиль, добавить вещество, запустить симуляцию на x100, увидеть изменение биомаркеров на графике.

### Задачи

- [x] M5.1 — Настроить PySide6 (версия из `mortality/Scripts`)
- [x] M5.2 — Написать `src/ui/main_window.py` (QMainWindow, layout 4 зон)
- [x] M5.3 — Написать `src/ui/human_panel.py` (QFormLayout + sliders/spinboxes, пресеты, BMI/BMR)
- [x] M5.4 — Написать `src/ui/time_controls.py` (pause/x1/x10/x100/x1000/x10000, таймер)
- [x] M5.5 — Написать `src/ui/telemetry_dashboard.py` (QCharts или matplotlib/pyqtgraph, 24 биомаркера)
- [x] M5.6 — Написать `src/ui/substance_manager.py` (список веществ, дозы, расписания)
- [x] M5.7 — Написать `src/ui/event_log.py` (QListView + фильтры по категориям)
- [x] M5.8 — Реализовать threading: движок в QThread, UI обновляется по сигналу ≤ 10 Гц
- [x] M5.9 — Написать `src/ui/disclaimer.py` (постоянный баннер дисклеймера)
- [x] M5.10 — Реализовать даунсэмплинг истории графиков (буфер ≤ 5000 точек на биомаркер)
- [x] M5.11 — Тёмная тема + Русская локализация
- [x] M5.12 — Создать `src/main.py` (точка входа)

### 4 зоны UI

```
┌─────────────────┬────────────────────────────────────────┐
│  Профиль        │  Телеметрия (графики биомаркеров)      │
│  человека       │  [ LDL | HDL | hsCRP | HbA1c | ... ]  │
│  [параметры]    │                                        │
│  [пресеты]      │                                        │
├─────────────────┼────────────────────────────────────────┤
│  Вещества       │  Журнал событий                        │
│  и интервенции  │  [info] [warning] [critical] [report]  │
│  [добавить]     │                                        │
│  [расписание]   │  ▶ PAUSE  x1 x10 x100 x1000           │
└─────────────────┴────────────────────────────────────────┘
                    ⚠️ ДИСКЛЕЙМЕР (постоянный)
```

### Выходные артефакты

- `src/ui/*.py` (7 модулей)
- `src/main.py`
- Работающее приложение

---

## M6 · Knowledge Base Integration

**Цель:** UI и движок обращаются к mortality KB для получения научного контекста о веществах и биомаркерах.  
**Критерий готовности:** Клик на вещество в UI → показывает уровень доказательности и краткую справку из mortality KB.

### Задачи

- [x] M6.1 — Написать `src/engine/kb_client.py` (запросы к Neo4j mortality KB)
- [x] M6.2 — Реализовать `get_substance_evidence(substance_id)` — возвращает уровень доказательности и факты из mortality
- [x] M6.3 — Реализовать `get_biomarker_context(biomarker_code)` — связанные исследования из mortality
- [x] M6.4 — Добавить в UI панель «Научный контекст» (всплывающий или sidebar)
- [x] M6.5 — Перенести страницы биомаркеров с ссылками на mortality KB
- [x] M6.6 — Написать `ingest_cross_links.py` — создать связи `:REFERENCES` между human и mortality узлами
- [x] M6.7 — Обновить вики-страницы веществ с ERS-значками из mortality

### Выходные артефакты

- `src/engine/kb_client.py`
- Cross-links в Neo4j между `Human` и `Mortality` базами

---

## M7 · Export, Tests & Documentation

**Цель:** Полные тесты, экспорт/импорт сценариев, финальная документация.  
**Критерий готовности:** `pytest` — все тесты зелёные; экспорт сценария → импорт → симуляция даёт тот же результат.

### Задачи

- [x] M7.1 — Написать `src/engine/exporter.py` (JSON экспорт полного состояния симуляции)
- [x] M7.2 — Реализовать импорт с Pydantic валидацией и обработкой версий
- [x] M7.3 — Написать `src/tests/test_export_import.py`
- [x] M7.4 — Написать `src/tests/test_benchmark.py` (1 год за < 5 сек, ≤ 2% отклонение)
- [x] M7.5 — Написать итоговую документацию движка в `06 - Engine/`
- [x] M7.6 — Написать `README.md` (установка, запуск, быстрый старт)
- [x] M7.7 — Создать страницу `07 - Analysis/Simulation Assumptions.md` (игровые допущения)
- [x] M7.8 — Создать страницу `07 - Analysis/Known Limitations.md`
- [x] M7.9 — Финальный lint вики (проверить битые ссылки, страницы-сироты)
- [x] M7.10 — Полная пересборка Neo4j (`ingest_wiki.py --clear`)

### Формат экспорта

```json
{
  "schema_version": "1.0",
  "engine_version": "1.0.0",
  "seed": 42,
  "human_profile": { ... },
  "active_substances": [ ... ],
  "simulation_time_hours": 8760,
  "organ_health": { ... },
  "biomarker_values": { ... },
  "event_log": [ ... ],
  "exported_at": "2026-06-18T00:00:00Z"
}
```

### Выходные артефакты

- `src/engine/exporter.py`
- Полный набор тестов
- `README.md`
- `07 - Analysis/` — 2 аналитических страницы
- Документация в `06 - Engine/`

---

## Зависимости между milestones

```
M0 → M1 → M2 → M3 → M4 → M5
                          ↓
M6 ← (M4 + M5) ← M3 ← M1
                          ↓
M7 ← (M4 + M5 + M6)
```

---

## Технический долг и идеи v2

- A/B сравнение сценариев (Сценарий A без веществ vs Сценарий B с веществами)
- Streamlit web-версия для демо
- CGM-симуляция (непрерывный мониторинг глюкозы)
- Режим «исследовательский» с интервалами неопределённости
- Импорт реальных лабораторных данных (CSV, HL7 FHIR)
- Мобильная нотификация через Telegram-бот

---

*Последнее обновление: 2026-06-18*
