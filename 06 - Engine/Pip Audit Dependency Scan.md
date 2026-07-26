---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, security, dependencies, pip-audit]
created: 2026-07-16
phase: M11
---

# Проверка зависимостей pip-audit

Разовая проверка корневого `requirements.txt` инструментом `pip-audit` (официальный PyPA-инструмент
поиска известных уязвимостей в зависимостях, FND-03) в ТЕКУЩЕМ dev-venv на этой машине (не в
чистом throwaway venv — D-14). Команды, вывод и версии ниже взяты из реального прогона на этой
машине в рамках выполнения Phase 11, а не из теоретического описания. Отдельная непрерывная
проверка `pip-audit` уже встроена в CI (`.github/workflows/ci.yml`, Plan 01) — эта страница
документирует именно текущее (на момент прогона) состояние зависимостей, а не заменяет CI-шаг (D-18).

## Процедура

### 1. Установка pip-audit в dev-venv

```powershell
venv\Scripts\python.exe -m pip install pip-audit
```

Результат: `pip-audit` уже присутствовал в venv (был установлен ранее в рамках исследования фазы);
версия — `2.10.1`.

### 2. Запуск проверки по requirements.txt (текстовый вывод)

```powershell
venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Результат фактического прогона:
```
No known vulnerabilities found
```
Код возврата: `0`.

### 3. Запуск с JSON-выводом (полный список разрешённых пакетов)

```powershell
venv\Scripts\python.exe -m pip_audit -r requirements.txt -f json -o pip-audit-report.json
```

Результат: JSON-объект с ключами `dependencies` (полный разрешённый граф зависимостей — **56
пакетов**, включая транзитивные: `pydantic`, `neo4j`, `sentence-transformers`, `PySide6`,
`pyqtgraph`, `pytest`, `python-dotenv`, `torch`, `numpy`, `scipy`, `transformers` и др.) и `fixes`
(пустой массив `[]` — подтверждает отсутствие уязвимостей, требующих исправления). Файл
`pip-audit-report.json` — рабочий артефакт разового прогона; не коммитится в репозиторий (см.
Ограничения).

## Параметры

| Параметр | Значение | Описание |
|----------|----------|----------|
| Инструмент | `pip-audit 2.10.1` | Официальный PyPA-инструмент, использует базу советов OSV/PyPI |
| Объект аудита | `requirements.txt` (корень репозитория) | D-15 — единственный охваченный объект; `.neo4j/venv` не покрыт |
| Окружение | Текущий dev-venv на этой машине (`Python 3.14.5`) | D-14 — не throwaway venv, в отличие от прецедента Phase 09-03 |
| Дата разового прогона | 2026-07-16 | Выполнено в рамках Phase 11, Plan 03 |
| Найдено уязвимостей | 0 | `fixes: []` в JSON-выводе, `"No known vulnerabilities found"` в текстовом |
| Изменения requirements.txt | Нет (файл байт-в-байт не менялся) | D-16 — правки нижних границ версий применяются только при реальной находке; в этом прогоне находок нет |

## Пример (вход → выход)

**Текстовый режим:**
```
venv\Scripts\python.exe -m pip_audit -r requirements.txt
→ exit 0
→ No known vulnerabilities found
```

**JSON-режим (сокращённо):**
```
venv\Scripts\python.exe -m pip_audit -r requirements.txt -f json -o pip-audit-report.json
→ exit 0
→ {"dependencies": [ ...56 пакетов... ], "fixes": []}
```

**Смежная (вне scope) находка — full-environment режим без `-r`:**
```
venv\Scripts\python.exe -m pip_audit
→ Found 2 known vulnerabilities in 1 package
  pip  26.1.1  PYSEC-2026-196  Fix: 26.1.2
```

## Ограничения

- Область проверки — только корневой `requirements.txt` (D-15). Отдельный venv `.neo4j/venv`
  (используется скриптами `.neo4j/*.py`) НЕ охвачен этим прогоном — у него нет собственного
  `requirements.txt` в git, воспроизводимая повторная проверка потребовала бы дополнительной работы
  вне рамок этой фазы.
- Прогон дал чистый результат — правок `requirements.txt` в этом проходе не потребовалось (D-16:
  нижние границы версий поднимаются только при реальной находке уязвимости, вписывающейся под
  существующий верхний пин из Phase 09/LINE-03; верхние границы не трогаются никогда).
- **Сноска про `pip` (Open Question 1, вне scope):** сам инструмент `pip` (версия `26.1.1` в этом
  venv) имеет 2 известные уязвимости (`PYSEC-2026-196`), исправленные в `26.1.2` — это видно только
  при запуске `pip-audit` БЕЗ флага `-r` (full-environment режим). `pip` как бинарник пакетного
  менеджера не является строкой в `requirements.txt`, поэтому формально вне scope этой проверки
  (D-15). Обновляется независимо командой `venv\Scripts\python.exe -m pip install --upgrade pip`,
  никак не связанной с пинами в `requirements.txt`.
- Непрерывная проверка (D-18) — отдельный шаг `pip-audit -r requirements.txt` уже встроен в
  `.github/workflows/ci.yml` (Plan 01) и запускается на каждый push/PR в `main`. Эта страница
  документирует только разовое ручное состояние на момент прогона, а не заменяет CI-шаг.
- `pip-audit-report.json` — рабочий JSON-артефакт полного прогона; не коммитится в git-репозиторий
  (не является частью `requirements.txt`/кода, значения без даты быстро устаревают).

## Ссылки

- [Neo4j Backup Restore](Neo4j%20Backup%20Restore.md) — аналогичная структура операционного отчёта в `06 - Engine/`
- `requirements.txt` (корень репозитория) — объект аудита; верхние границы версий зафиксированы в
  Phase 09 (LINE-03) и не меняются этой проверкой
- `.github/workflows/ci.yml` — непрерывный CI-шаг `pip-audit` (D-09/D-18), не заменяет эту разовую
  проверку
