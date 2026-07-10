---
license: Apache-2.0
copyright: "Copyright © 2026 Vladimir Bazhin"
contact: info@simuostasis.com
tags: [engine, neo4j, backup, ops]
created: 2026-07-04
phase: M9
---

# Backup и восстановление Neo4j

Операционный runbook для резервного копирования и восстановления базы `Human` через штатную утилиту `neo4j-admin` (D-04). Процедура выполнена и проверена реальным восстановлением в Plan 05 фазы 09 (Data Protection) — все команды и счётчики ниже взяты из фактического прогона, а не из теоретической документации. Скрипты подключения (`.neo4j/check_connection.py`, `.neo4j/db_stats.py`) используются для проверки состояния до/после.

## Процедура

### 1. Подготовка окружения (JAVA_HOME)

`neo4j-admin.bat` из связанного Neo4j Desktop DBMS требует явного указания `JAVA_HOME`/`PATH` на бандловый Zulu 21 рантайм — системный Java 17 несовместим (`UnsupportedClassVersionError`). Сам `neo4j-admin.bat` также не резолвится в свежей оболочке, пока не добавлена его директория (`bin` каталог DBMS) — либо через `cd`, либо через `$env:PATH`:

```powershell
$env:JAVA_HOME = "<путь к .Neo4jDesktop2\Cache\runtime\zulu21...>"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
cd "<путь к DBMS>\bin"   # либо добавить эту директорию в $env:PATH — здесь лежит neo4j-admin.bat
```

### 2. Создание дампа (dump)

Эта редакция/версия сервера (Enterprise 2026.05.0) требует офлайн-дамп — живая `Human` кратковременно останавливается. Остановка/запуск выполняются через Cypher к системной БД (`cypher-shell` или эквивалентный driver-скрипт):

```cypher
:use system
STOP DATABASE Human;
```

```powershell
$dumpArg = '--to-path=W:\Backups\neo4j-human'
& neo4j-admin.bat database dump Human $dumpArg
```

```cypher
:use system
START DATABASE Human;
```

Аргумент `--to-path` вынесен в отдельную переменную PowerShell без завершающего `\` перед закрывающей кавычкой — иначе PowerShell ломает парсинг аргумента (`Unmatched argument`).

Результат фактического прогона: exit 0, `Done: 103 files, 12.18MiB, 1.76 sec`. Простой живой `Human` составил ~2 минуты; после `START DATABASE` подтверждена online с исходным числом узлов (811).

### 3. Создание тестовой БД для проверки восстановления

Восстановление проверяется в отдельную одноразовую тестовую БД на том же сервере — никогда не поверх живой `Human` (D-05):

```cypher
CREATE DATABASE `human-restore-test` IF NOT EXISTS
```

Neo4j запрещает подчёркивания в именах баз данных ("contains illegal characters. Use simple ascii characters, numbers, dots and dashes") — поэтому используется имя `human-restore-test` (дефисы), а не `Human_restore_test`.

### 4. Загрузка дампа (load)

Файл дампа **копируется** (не переименовывается) под именем целевой БД — `neo4j-admin database load` требует, чтобы имя файла в `--from-path` совпадало с именем целевой БД, но канонический `Human.dump` при этом должен остаться нетронутым:

```cypher
:use system
STOP DATABASE `human-restore-test`;
```

```powershell
Copy-Item 'W:\Backups\neo4j-human\Human.dump' 'W:\Backups\neo4j-human\human-restore-test.dump'

& neo4j-admin.bat database load human-restore-test --from-path=W:\Backups\neo4j-human --overwrite-destination=true
```

```cypher
:use system
START DATABASE `human-restore-test`;
```

### 5. Проверка (verify)

Счётчики узлов по каждому label и связей по каждому типу восстановленной `human-restore-test` сравниваются с baseline живой `Human` (посчитанным заранее, до дампа):

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY cnt DESC
```

```cypher
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt ORDER BY cnt DESC
```

Паттерн скрипта — `.neo4j/db_stats.py`, запущен построчно по обеим базам. `db_stats.py` выбирает целевую БД через переменную окружения `NEO4J_DATABASE` (по умолчанию `Human`, см. `.neo4j/db_stats.py`) — перед вторым прогоном её нужно явно выставить, иначе оба прогона молча обратятся к живой `Human` и сравнение не будет проверкой восстановленной БД:

```powershell
$env:NEO4J_DATABASE = "human-restore-test"
.\venv\Scripts\python.exe db_stats.py
Remove-Item Env:\NEO4J_DATABASE   # сброс к значению по умолчанию (Human)
```

### 6. Удаление тестовой БД

После успешной проверки тестовая БД удаляется — не остаётся stale-копии данных ни в графе, ни на диске:

```cypher
DROP DATABASE `human-restore-test` IF EXISTS
```

```powershell
Remove-Item 'W:\Backups\neo4j-human\human-restore-test.dump' -ErrorAction SilentlyContinue
```

Канонический `Human.dump` при этом не затрагивается — в шаге 4 он копировался, а не переименовывался.

## Параметры

| Параметр | Значение | Описание |
|----------|----------|----------|
| Хост Neo4j | `<NEO4J_SERVER_IP>` (Neo4j Desktop, та же локальная машина — D-13) | Сервер, на котором выполняется `neo4j-admin` |
| Живая БД | `Human` | Источник дампа, никогда не перезаписывается restore-процедурой |
| Тестовая БД | `human-restore-test` | Одноразовая, создаётся перед load, удаляется после verify |
| Серверный/локальный путь дампа | `W:\Backups\neo4j-human\Human.dump` | Локально вне git-репозитория (D-07) — хост и клиент совпадают (D-13), промежуточный transfer-шаг не требуется |
| JAVA_HOME | `.Neo4jDesktop2\Cache\runtime\zulu21...` | Обязателен — системный Java 17 несовместим |

## Пример (вход → выход)

**Дамп:**
```
neo4j-admin database dump Human --to-path=W:\Backups\neo4j-human
→ exit 0, Done: 103 files, 12.18MiB, 1.76 sec
→ W:\Backups\neo4j-human\Human.dump — 4 257 343 байта (4.06 МБ)
```

**Восстановление и сверка счётчиков:**
```
baseline Human (до дампа):        811 узлов / 1098 связей
human-restore-test (после load):  811 узлов / 1098 связей
→ ALL COUNTS MATCH (10 label'ов узлов + 9 типов связей, построчно 1:1)
```

**Удаление тестовой БД:**
```
DROP DATABASE `human-restore-test`
SHOW DATABASES → human-restore-test отсутствует
```

## Ограничения

- `neo4j-admin` исполняется на хосте сервера Neo4j, не является bolt-операцией — нужен shell/filesystem-доступ к машине сервера (в этом случае хост и клиент совпадают, D-13).
- Файл дампа обязательно копируется (не переименовывается) под имя целевой БД перед `load` — иначе `neo4j-admin database load` завершается ошибкой; канонический `Human.dump` должен оставаться нетронутым.
- `human-restore-test` — одноразовая, всегда удаляется после проверки (T-09-04), включая рабочую копию `human-restore-test.dump` на диске; нельзя оставлять stale-копию чувствительных данных.
- Имена баз данных Neo4j не поддерживают подчёркивания — только ascii-буквы, цифры, точки и дефисы.
- Bolt-соединение без TLS (внутренняя сеть) — принятый риск `AR-09-02` (см. `.planning/phases/09-data-protection/09-SECURITY.md`, раздел Accepted Risks Log): предсуществующий паттерн, вне рамок фазы 09; соединение только для чтения, новых credentials не вводится.
- Для офлайн-дампа на этой редакции/версии сервера живая БД кратковременно останавливается (`STOP DATABASE` / dump / `START DATABASE`) — учитывать окно недоступности (~2 минуты) при планировании backup-операций.
- Значения credentials (`.env`) в этой процедуре нигде не фигурируют — только имя переменной окружения.

## Ссылки

- [[06 - Engine/RNG Seeding]] — аналогичная структура операционной/технической документации движка
- [[.neo4j/README]] — общая документация Neo4j-скриптов проекта
