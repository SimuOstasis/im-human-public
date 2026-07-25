# log.md — Хронологический журнал im-human

## License

This work is licensed under the Apache License, Version 2.0. See [[LICENSE.txt]] for the full text.

Copyright © 2026 Vladimir Bazhin. Contact: info@simuostasis.com

> Append-only. Записи не удаляются.  
> Формат: `## [ГГГГ-ММ-ДД] тип | описание`
> Публичный файл (в git) — без локальных путей, адресов, логинов, паролей. Полная версия — в `log_internal.md` (вне git).

---

## [2026-06-18] init | M0 Foundation — Инициализация проекта im-human

**Obsidian структура:**
- Созданы папки: 00-Inbox, 01-HumanProfiles, 02-Biomarkers (13 категорий), 03-Substances, 04-Interactions, 05-Simulation, 06-Engine, 07-Analysis, 08-Index, 09-Templates, src/, .neo4j/, .planning/
- Созданы: CLAUDE.md, HOME.md, MILESTONES.md, log.md
- Шаблоны: Biomarker Template.md, Substance Template.md, Human Profile Template.md

**Планирование:**
- MILESTONES.md: 8 milestones M0–M7 с задачами и критериями готовности
- .planning/PROJECT.md: ADR-001 (Python), ADR-002 (DUAL-LAYER), ADR-003 (база Human), ADR-004 (embedding model)

**Neo4j:**
- .neo4j/README.md: полная схема узлов и связей
- .neo4j/setup_schema.py: constraints + indexes + vector index (384d)
- .neo4j/check_connection.py: проверка Human + Mortality DB
- .neo4j/ingest_wiki.py: загрузка вики с эмбеддингами
- .neo4j/ingest_biomarkers.py: загрузка биомаркеров
- .neo4j/ingest_substances.py: загрузка веществ
- .neo4j/query_wiki.py: семантический поиск
- .neo4j/db_stats.py: статистика базы
- .neo4j/.env: подключение к bolt://<NEO4J_SERVER_IP>:7687 (Human + Mortality)
- venv создан с Python 3.14.6, установлен neo4j==6.2.0, pyyaml

**Данные:**
- src/data/biomarkers.json: 24 MVP биомаркера с референсными диапазонами
- src/requirements.txt

**Статус Neo4j:**
- ✅ Сервер <NEO4J_SERVER_IP>:7687 доступен
- ✅ База Human создана (create_database.py)
- ✅ Схема применена (11 constraints, 8 indexes + VECTOR INDEX human_wiki_chunks 384d ONLINE)
- ✅ Mortality KB: 26332 узлов, доступна для чтения
- check_connection.py: оба DB ONLINE

---

## [2026-06-19] verify | M0 Foundation — Финальная верификация завершена

**M0 Milestone закрыт — все 5 success criteria пройдены.**

**Задача 1 — Структура M0 (Success Criterion 3):**
- Все 10 wiki-папок (00 - Inbox .. 09 - Templates) существуют
- Системные папки src/, .neo4j/, .planning/ существуют
- Ключевые артефакты: CLAUDE.md, HOME.md, log.md, .planning/PROJECT.md, src/__init__.py — на месте
- FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-12: VERIFIED

**Задача 2 — Neo4j схема + подключение (Success Criteria 1, 2):**
- setup_schema.py: exit 0 — схема применена (11 constraints, 8 indexes + VECTOR INDEX human_wiki_chunks 384d ONLINE)
- check_connection.py: exit 0 — Human DB (онлайн) + Mortality KB (26332 узлов, онлайн)
- FOUND-05, FOUND-08, FOUND-10: VERIFIED

**Задача 3 — ingest + query + DUAL-WRITE (Success Criteria 4, 5):**
- ingest_wiki.py --dry-run: exit 0 — обнаружено 3 страницы (шаблоны в 09 - Templates)
- ingest_wiki.py (полный): exit 0 — 3 страницы загружены с эмбеддингами
- query_wiki.py "HOME": exit 0 — 5 результатов из векторного индекса human_wiki_chunks
- TOKENIZERS_PARALLELISM=false добавлен для стабильности на Windows
- FOUND-06, FOUND-07: VERIFIED

**Итог M0:** git-репозиторий + корневой venv + .neo4j/venv + схема Neo4j + подключение + ingest + семантический поиск — всё работает end-to-end.

---

## [2026-07-09] infra | Phase 09-02 — приватный GitHub remote создан

**GitHub-репозиторий (D-08/D-09/D-10):**
- URL: https://github.com/SimuOstasis/im-human
- Видимость: **PRIVATE** (подтверждено `gh repo view --json visibility`)
- Запушены ветки: `main`, `gsd-reviewfix/01-794`, `gsd-reviewfix/03-1858`
- Запушен тег: `v1.0`
- Prerequisite: git-история подтверждена чистой от `.env`/секретов (Plan 01, D-03) до открытия репозитория наружу — перепроверено независимо перед push
- Способ выполнения: ассистент через `gh` CLI (`gh repo create im-human --private --source=. --push`), с явным подтверждением пользователя на execute-phase checkpoint (D-09)

---

## [2026-07-09] docs | Phase 9 Plan 6 — LINE-02 завершён: backup/restore Neo4j задокументирован

**Реальная проверка (Plan 05):**
- Живая `Human` продампена через `neo4j-admin database dump` в локальный backup-файл вне репозитория (4 257 343 байта; путь — см. `log_internal.md`)
- Восстановлена в одноразовую тестовую БД `human-restore-test` (не в живую `Human`)
- Счётчики узлов/связей (811/1098) совпали с baseline 1:1 по всем label'ам и типам связей
- Тестовая БД `human-restore-test` удалена после проверки

**Документация (Plan 06):**
- Создана вики-страница `06 - Engine/Neo4j Backup Restore.md` — реальные команды, пути и счётчики из фактического прогона Plan 05
- Ссылка добавлена в `HOME.md` (раздел `06 - Engine`, счётчик 7→8)
- Страница синхронизирована в Neo4j через `ingest_wiki.py --changed-only` (exit 0, `engine/neo4j-backup-restore` [OK])
- `:Page`-узел подтверждён bolt-запросом: `slug=engine/neo4j-backup-restore`, `title=Neo4j Backup Restore`, count=1

**LINE-02 закрыт:** backup/restore Neo4j не только выполнен и проверен реальным восстановлением, но и задокументирован как операционный runbook в DUAL-LAYER (Obsidian + Neo4j).

---

## [2026-07-10] security | Утечка IP локальной машины устранена из git-истории

**Обнаружение:** IP Neo4j-сервера (эта же локальная машина, D-13) был закоммичен в первом же коммите репозитория (`chore: initial project structure`, 2026-06-19) и, несмотря на частичное исправление README в Phase 01, оставался в истории и в 10 текущих закоммиченных файлах на момент подготовки репозитория к публикации. Проверка D-03 (Plan 01) была ограничена историей `.env` и не покрывала произвольные строки — этот пробел и привёл к утечке.

**Устранение:**
- Значение заменено на плейсхолдер во всех затронутых файлах (текущих и незакоммиченных на тот момент планинг-документах Phase 09)
- История переписана `git-filter-repo --replace-text` (196 коммитов, все 3 ветки + тег `v1.0`) — прежний прерванный `git filter-branch` не был доведён до конца и не тронул реальные ссылки, обнаружен и убран
- Полный бэкап истории до перезаписи сохранён локально вне репозитория (путь — см. `log_internal.md`)
- `git push --force` всех веток и тега в приватный `origin` (GitHub) — подтверждено `git ls-remote` + `git log -S` по свежему `fetch`: совпадений не осталось
- Проверка секретов/credentials — чисто, `.env` никогда не коммитился

**Репозиторий на момент исправления:** PRIVATE. Публичного раскрытия за время утечки не зафиксировано.

---

## [2026-07-10] policy | Введён двухслойный лог (log.md + log_internal.md)

**Причина:** предыдущий инцидент (утечка IP выше) показал, что `log.md` — публичный, версионируемый файл — не место для локальных путей/адресов.

**Новое правило (см. CLAUDE.md):**
- `log.md` — только публично-безопасные записи, коммитится в git
- `log_internal.md` — полные детали: локальные пути (`W:\...`), адреса, доступы; в `.gitignore` через маску `*_internal*`, никогда не коммитится
- Каждая запись сначала пишется в `log_internal.md` (полная версия), затем публичная версия — в `log.md`

---

## [2026-07-10] infra | .neo4j/venv пересоздан, live-проверка :Page закрыта

**Уточнение:** `.neo4j/venv` указывал на Python другого, действующего локального пользователя этой машины (не на удалённый/устаревший профиль) — текущая сессия не имела прав на его `AppData`, отсюда ошибка запуска. Не связано с зависаниями подключения, зафиксированными при верификации Plan 06 (2026-07-09) — причина тех зависаний осталась невыясненной.

**Исправление:** venv пересоздан заново (текущий пользователь), переустановлены зафиксированные зависимости (`neo4j==6.2.0` — совпадает с исходной установкой). Подключение работает сразу, без зависаний.

**Решено:** на машине с этим репозиторием работают два пользователя Windows. Установлен system-wide Python (доступен всем локальным аккаунтам), `.neo4j/venv` пересоздан на нём. Права на файловой системе подтверждены для обоих аккаунтов.

**Результат:** последняя незакрытая ручная проверка фазы 09 (DUAL-WRITE `:Page`-узел для страницы Neo4j Backup Restore) выполнена — узел на месте, `count=1`, заголовок совпадает. `09-VERIFICATION.md` обновлён (human_needed → passed, 7/7). `09-VALIDATION.md` обновлён (15/15 задач green, gaps: 0).

---

## [2026-07-10] docs | Актуализация документации вики + README (Phase 10, UX-стабилизация)

Проход по вики-страницам со сверкой по реальному коду; акцент на описании логики работы и
инструкциях. Закрыта часть tech-debt HS-04/TD-04 из Application Development Review.

**Создано:**
- `06 - Engine/Simulation Engine.md` — центральная страница 13-шагового цикла тика (Mermaid:
  конвейер тика, батчи, FSM состояний). Добавлена в HOME.md.
- `Assets/how-it-works.svg` — иллюстрация «4 шага» для раздела README для новичков.

**Исправлено под фактические данные:**
- Таблица веществ (HOME.md, MILESTONES.md): удалён несуществующий «Ресвератрол», «Витамин D» →
  «Витамин D3», категории приведены к `substances.json` (7 веществ).
- Имена пресетов приведены к `presets.json`: `young_healthy_30m`, `middle_age_50f`, `elderly_70m`
  (User Guide, Known Limitations).
- Число взаимодействий «10» → **6** (Known Limitations, Simulation Assumptions) — по факту
  `interactions.json`.
- UI Guide: противоречивая таблица скоростей заменена на единую и непротиворечивую.
- README.md полностью переписан: оглавление; **раздел «Описание принципов работы (простыми
  словами)»** для новичка/пятиклассника с картинкой и Mermaid-схемами (архитектура, DUAL-LAYER,
  цикл тика); число тестов приведено к фактическому (~100 в 12 файлах); таблицы веществ (7) и
  взаимодействий (6).

**Сверка с кодом:** страницы движка (PK, гомеостаз, био-возраст, взаимодействия, детектор событий,
adaptive stepper, RNG) сверены с исходниками — формулы и константы актуальны.

**DUAL-WRITE (Neo4j):** `ingest_wiki.py --changed-only` → Processed: 5, Errors: 0 (синхронизированы
изменённые контент-страницы движка/анализа/UI). Корневые HOME/README/MILESTONES — вне области
ingest. Подключение и адрес сервера — см. `log_internal.md`.

---

## [2026-07-10] plan | Создан форвардный план развития im-human

**Создано:**
- `07 - Analysis/Development Plan_2026-07-10.md` — форвардный план развития приложения (волны 0–4)
  на основе трёх источников: собственный review 2026-06-28, ревью проекта agent (2026-07-02) и
  сквозной Product Line Development Plan. Синтезирует текущее состояние (milestone v2.0, Phase 10),
  переносимые уроки из agent (дисциплина git, отказ от «тихих» xfail, дедупликация формул, pip-audit,
  README для человека) и шаги по волнам. Отдельным блоком включены **шаги 1 и 2 по производительности
  UI** (установка PyOpenGL/GPU-рендер; обновление только видимых графиков дашборда); шаги 3–7 того же
  анализа помечены как выполняемые к этому моменту рутинно. Зарегистрирована в HOME.md (07 - Analysis).

**DUAL-WRITE (Neo4j):** `ingest_wiki.py --changed-only` → Processed: 2, Skipped: 52, Errors: 0
(синхронизированы `analysis/development-plan-2026-07-10`, `interactions/interactions-index`).
Адрес сервера — см. `log_internal.md`.

---

## [2026-07-11] plan | Проверен Milestone v2.1 и создан план v2.2

**Проверка:** план Milestone v2.1 сверён с общим планом линейки и ревью соседних проектов.

**Решение по v2.1:** оставлена стабилизация — воспроизводимость, UX, Save/Load, честная маркировка
`biologicalAge`, справка, dependency hygiene, лёгкий CI/`pip-audit` и измеримая UI-производительность.
Собственные v2-фичи и межпродуктовая интеграция вынесены из v2.1.

**Создано:**
- `07 - Analysis/Milestone v2.2. Development Plan_2026-07-11.md` — следующий milestone: экспорт результатов,
  новые механики модели, интеграция с mortality и design note по возможному Hovorka-модулю из agent.

**Обновлено:**
- `07 - Analysis/Milestone v2.1. Development Plan_2026-07-10.md` — уточнены границы Milestone v2.1.
- `HOME.md` — добавлена ссылка на v2.2.

**Уточнение:** внутренняя нумерация «Фаза 0–4» убрана, чтобы не конфликтовать с GSD. v2.1 разложен
на Phase 10–12, v2.2 — на Phase 13–17; `.planning/ROADMAP.md` приведён к той же раскладке.

**Дополнение 2026-07-11:** с учётом того, что текущий GSD roadmap v2.0 идёт до Phase 13, номера в планах
уточнены без правки `.planning`: v2.1 = Phase 14–16, v2.2 = Phase 17–21. Phase 21 переформулирована
как Human-Agent data contract: сначала контракт данных, брокер сообщений как возможный транспортный слой,
engine-adapter только как крайний вариант без переноса Hovorka-кода в Human.

---

## [2026-07-11] plan | DOS-01 — множественные времена приёма в сутки добавлены в backlog

**Запрос:** проверить, планируется ли возможность задать несколько фиксированных времён приёма в
сутки для одного вещества (например, 10:00 и 14:00), вместо единственного времени на расписание.

**Проверка кода:** текущая модель расписания (`IntakeSchedule`) поддерживает только одно время
приёма в сутки на вещество; поле для интервала между дозами объявлено, но движком не используется;
интерфейс не позволяет задать одно вещество дважды в разное время без обхода UI. Проверка планов
подтвердила отсутствие этой фичи в GSD roadmap (Phase 09–13), requirements, обоих milestone-планах
(v2.1, v2.2) и Known Limitations.

**Добавлено:** новое требование **DOS-01** в GSD requirements (deferred/experimental, по образцу
существующего INT-02) и заметка в roadmap; в план v2.2 — блок «Расписание приёма» в Phase 19 (перед
новыми биологическими механиками, как менее объёмная предпосылка); в Known Limitations — уточняющая
врезка и строка в таблице roadmap v2+.

**DUAL-WRITE (Neo4j):** `ingest_wiki.py --changed-only` → Processed: 3, Skipped: 52, Errors: 0
(Known Limitations, оба milestone-плана). Подключение — см. `log_internal.md`.
