# src/ — исходный код im-human

Python-приложение симулятора (PySide6 UI + движок симуляции). Слой знаний
(вики + Neo4j) описан в [корневом README](../README.md) и `.neo4j/README.md`.

## Структура

```
src/
  domain/      — доменные модели: HumanProfile, SubstanceDefinition,
                 SimulationState, единицы измерения (Pydantic v2)
  engine/      — движок симуляции: фармакокинетика, гомеостаз,
                 разрешение взаимодействий, адаптивный степпер,
                 детектор событий, индекс биологического возраста,
                 детерминированный RNG, экспорт, KB-клиент
  ui/          — PySide6-интерфейс: главное окно, панель профиля,
                 управление временем, дашборд телеметрии, журнал
                 событий, менеджер веществ, воркер симуляции
  data/        — JSON-конфигурации: substances.json, interactions.json,
                 biomarkers.json, reference_ranges.json, presets.json
  scripts/     — генераторы вики-страниц (биомаркеры/профили/вещества)
  tests/       — pytest-тесты (см. README.md в корне — актуальные счётчики)
  main.py      — точка входа приложения
```

## Запуск

См. разделы «Установка» и «Быстрый старт» в [корневом README](../README.md).

## Тесты

```powershell
.\venv\Scripts\python.exe -m pytest src/tests/ -v
```

Подробности — раздел «Запуск тестов» в [корневом README](../README.md).
