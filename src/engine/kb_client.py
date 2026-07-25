# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""kb_client.py — Cross-database клиент запросов к Neo4j Human + Mortality DB.

Использует один GraphDatabase.driver с переключением database через
session(database=) — Community Edition не поддерживает Fabric (D-02, D-09).

Классы:
    KBClient  — синхронные cross-DB запросы (Human lookup + Mortality :Fact)
    KBWorker  — QThread worker с cancellation для UI (KB-01, KB-04)

Безопасность:
    T-07-01: все Cypher параметризованы ($page_slug, $id, $code) — нет конкатенации
    T-07-02: только MATCH/RETURN в Mortality DB — нет SET/MERGE/DELETE
    T-07-03: password не выводится в логах/ошибках

Примечание по импортам:
    neo4j импортируется lazily внутри __init__ и _query_facts (не на уровне модуля),
    чтобы не блокировать импорт модуля в тестах (neo4j driver инициализирует
    thread pool при импорте что вызывает зависание в некоторых средах).
    PySide6 импортируется условно — доступен в Qt-приложении, необязателен
    для batch-скриптов из .neo4j/venv (update_ers_pages.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from PySide6.QtCore import QObject, Signal, Slot
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    QObject = object  # type: ignore[misc,assignment]

    def Signal(*args, **kwargs):  # type: ignore[misc]
        return None

    def Slot(*args, **kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator

# ---------------------------------------------------------------------------
# Cypher queries (verbatim from W:\Obsidian\mortality\.neo4j\query_facts.py
# строки 17–32, verified 2026-06-23)
# ---------------------------------------------------------------------------

_SCHEMA_05 = """
MATCH (target:Page {slug: $page_slug})
OPTIONAL MATCH (target)-[:LINKS_TO]-(neighbour:Page)
WITH target, collect(neighbour) + [target] AS pages
UNWIND pages AS p
MATCH (f:Fact)-[:FACT_OF]->(p)
WHERE f.si >= 0.5
OPTIONAL MATCH (f)-[:FROM_SOURCE]->(s:Source)
RETURN DISTINCT
       f.subject    AS subject,
       f.predicate  AS predicate,
       f.object     AS object,
       f.si         AS si,
       f.wi         AS wi,
       f.importance AS importance,
       p.slug AS source_page,
       collect(DISTINCT {url: s.url_or_doi, title: s.title}) AS sources
ORDER BY f.wi DESC, f.si DESC
"""


# ---------------------------------------------------------------------------
# Вспомогательная функция: загрузка .env (логика из .neo4j/_utils.py)
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Path | None = None) -> None:
    """Загрузить .env файл и выставить переменные окружения через setdefault.

    Реализация копирует логику .neo4j/_utils.py строки 8–17.
    Путь по умолчанию: три уровня вверх от src/engine/ → .neo4j/.env

    Приоритет: setdefault устанавливает значение только если переменная
    отсутствует в os.environ. Это намеренно — системные/CI переменные
    имеют приоритет над .env файлом (WR-06).

    Inline-комментарии (#) в значениях обрезаются:
        NEO4J_PASSWORD=secret123  # production → «secret123»
    """
    path = env_path or (Path(__file__).parent.parent.parent / ".neo4j" / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("#")[0].strip()  # WR-06: отбросить inline-комментарий
        os.environ.setdefault(key.strip(), value)


# ---------------------------------------------------------------------------
# KBClient — синхронные cross-DB запросы
# ---------------------------------------------------------------------------

class KBClient:
    """Клиент cross-database запросов к двум Neo4j-базам на одном сервере.

    Human DB:    lookup mortality_slug для вещества или биомаркера
    Mortality DB: запрос :Fact узлов через _SCHEMA_05

    Graceful degradation (D-11):
        - slug отсутствует в Human DB → возвращает []
        - Mortality DB недоступна → возвращает [], приложение не падает
    """

    def __init__(self, env_path: Path | None = None) -> None:
        """Инициализировать драйвер из .env.

        Args:
            env_path: путь к .env файлу (None → три уровня вверх / .neo4j / .env)
        """
        _load_dotenv(env_path)
        uri = os.environ.get("NEO4J_URI", "neo4j://127.0.0.1:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "")
        self._human_db = os.environ.get("NEO4J_DATABASE", "Human")
        self._mortality_db = os.environ.get("MORTALITY_NEO4J_DATABASE", "Mortality")
        # Lazy import neo4j (driver инициализирует thread pool при импорте)
        from neo4j import GraphDatabase  # noqa: PLC0415
        # Один driver — два database через session(database=)
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    # ------------------------------------------------------------------
    # Внутренние методы: slug lookup
    # ------------------------------------------------------------------

    def _get_mortality_slug_substance(self, substance_id: str) -> str | None:
        """Получить mortality_slug для вещества из Human DB.

        Параметризованный запрос (T-07-01).
        Использует next() вместо .single() для совместимости с mock и реальным driver.
        """
        with self._driver.session(database=self._human_db) as session:
            result = session.run(
                "MATCH (s:Substance {id: $id}) RETURN s.mortality_slug AS slug",
                id=substance_id,
            )
            rec = next(iter(result), None)
            return rec["slug"] if rec else None

    def _get_mortality_slug_biomarker(self, biomarker_code: str) -> str | None:
        """Получить mortality_slug для биомаркера из Human DB.

        Параметризованный запрос (T-07-01).
        Использует next() вместо .single() для совместимости с mock и реальным driver.
        """
        with self._driver.session(database=self._human_db) as session:
            result = session.run(
                "MATCH (b:Biomarker {code: $code}) RETURN b.mortality_slug AS slug",
                code=biomarker_code,
            )
            rec = next(iter(result), None)
            return rec["slug"] if rec else None

    def _query_facts(self, page_slug: str) -> list[dict]:
        """Запросить :Fact узлы из Mortality DB через _SCHEMA_05.

        Параметризованный запрос (T-07-01). Mortality DB — READ ONLY (T-07-02).
        """
        with self._driver.session(database=self._mortality_db) as session:
            result = session.run(_SCHEMA_05, page_slug=page_slug)
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Публичные методы: KB запросы
    # ------------------------------------------------------------------

    def get_substance_evidence(self, substance_id: str) -> list[dict]:
        """Получить факты из Mortality DB для вещества.

        Шаг 1: lookup mortality_slug в Human DB по substance_id.
        Шаг 2: запрос :Fact через _SCHEMA_05 из Mortality DB.

        Graceful degradation (D-11):
            - slug is None → []
            - ServiceUnavailable / AuthError / любое исключение → []

        Args:
            substance_id: внутренний идентификатор вещества (напр. "omega3")

        Returns:
            list[dict] с ключами subject/predicate/object/si/wi/importance/source_page
        """
        try:
            slug = self._get_mortality_slug_substance(substance_id)
            if not slug:
                return []
            return self._query_facts(slug)
        except Exception:
            return []

    def get_biomarker_context(self, biomarker_code: str) -> list[dict]:
        """Получить факты из Mortality DB для биомаркера.

        Аналогично get_substance_evidence, но lookup через :Biomarker {code}.

        Graceful degradation (D-11): slug отсутствует или DB недоступна → []

        IN-03 (13-REVIEW.md): реализовано и покрыто тестами (KB-03,
        test_kb_client.py::test_get_biomarker_context), но пока не вызывается
        ни из одного UI-пути — намеренно staged раньше своего потребителя
        (планируемая панель деталей биомаркера, будущая фаза). Не удалять как
        "мёртвый код" без проверки ROADMAP.

        Args:
            biomarker_code: внутренний код биомаркера (напр. "ldlC")

        Returns:
            list[dict] с ключами subject/predicate/object/si/wi/importance/source_page
        """
        try:
            slug = self._get_mortality_slug_biomarker(biomarker_code)
            if not slug:
                return []
            return self._query_facts(slug)
        except Exception:
            return []

    def compute_ers_level(self, facts: list[dict]) -> int:
        """Вычислить уровень ERS (1–5) по средневзвешенному si.

        Пороги (D-13):
            < 0.2 → 1, < 0.4 → 2, < 0.6 → 3, < 0.8 → 4, >= 0.8 → 5

        Args:
            facts: список фактов из get_substance_evidence / get_biomarker_context

        Returns:
            int 1–5; 1 если facts пустой или si отсутствует
        """
        if not facts:
            return 1
        # D-06: Используем _compute_weighted_si — единую точку вычисления (WR-02),
        # взвешенную по importance (Critical=3/Major=2/Minor=1), а не плоское среднее
        weighted_si = _compute_weighted_si(facts)
        # weighted_si == 0.0 когда все si=None → _compute_weighted_si вернул 0.0 (нет данных)
        # < 0.2 перехватывает этот случай и возвращает уровень 1
        if weighted_si < 0.2:
            return 1
        if weighted_si < 0.4:
            return 2
        if weighted_si < 0.6:
            return 3
        if weighted_si < 0.8:
            return 4
        return 5

    def close(self) -> None:
        """Закрыть Neo4j driver."""
        self._driver.close()


# ---------------------------------------------------------------------------
# _compute_weighted_si — единая точка вычисления importance-взвешенного si (D-06)
# ---------------------------------------------------------------------------

# Веса важности факта (D-06: Critical весит больше Minor)
_IMPORTANCE_WEIGHTS: dict[str, int] = {"Critical": 3, "Major": 2, "Minor": 1}
_DEFAULT_IMPORTANCE_WEIGHT = 1  # importance отсутствует/неизвестна -> вес как у Minor


def _compute_weighted_si(facts: list[dict]) -> float:
    """Вычислить importance-взвешенный si по списку фактов (D-06).

    Каждый факт взвешивается по своей важности (Critical=3 / Major=2 / Minor=1,
    неизвестная/отсутствующая importance -> вес 1). Фильтрует факты с si=None.
    Единая точка вычисления (WR-02) — используется и compute_ers_level(), и
    заголовком _format_facts(), чтобы уровень и отображаемое число никогда не
    расходились.

    Args:
        facts: список фактов из get_substance_evidence / get_biomarker_context

    Returns:
        float — взвешенный si (sum(si_i * w_i) / sum(w_i)), либо 0.0 если facts
        пустой или все si=None
    """
    weighted = [
        (f.get("si"), _IMPORTANCE_WEIGHTS.get(f.get("importance"), _DEFAULT_IMPORTANCE_WEIGHT))
        for f in facts
        if f.get("si") is not None
    ]
    if not weighted:
        return 0.0
    total_weight = sum(w for _, w in weighted)
    return sum(si * w for si, w in weighted) / total_weight


# ---------------------------------------------------------------------------
# _source_label — метка провенанса источника факта (D-05)
# ---------------------------------------------------------------------------

def _source_label(sources: list[dict] | None) -> str:
    """Свернуть список источников факта (:FROM_SOURCE -> :Source) в одну метку.

    OPTIONAL MATCH в _SCHEMA_05 даёт один элемент с url=None/title=None, когда у
    факта нет ни одного :Source — такие «пустые» элементы отфильтровываются перед
    подсчётом кардинальности (D-05).

    Args:
        sources: список {"url": ..., "title": ...} из _SCHEMA_05 (может быть None
                 если ключ sources отсутствует в факте — defensive access)

    Returns:
        «не указан» (0 реальных источников), title/url единственного источника (1),
        либо «{title_of_first} и ещё {N-1}» (N>1)
    """
    real_sources = [
        s for s in (sources or [])
        if (s.get("title") or s.get("url"))
    ]
    if not real_sources:
        return "не указан"
    first = real_sources[0]
    first_label = first.get("title") or first.get("url") or "не указан"
    if len(real_sources) == 1:
        return first_label
    return f"{first_label} и ещё {len(real_sources) - 1}"


# ---------------------------------------------------------------------------
# _format_facts — модульная функция форматирования
# ---------------------------------------------------------------------------

def _format_facts(facts: list[dict], substance_id: str, client: KBClient,
                  name_map: dict | None = None) -> str:
    """Форматировать список фактов в plaintext для QTextEdit.setPlainText().

    Формат (по контракту 13-UI-SPEC.md §Copywriting Contract, расширяет 07-UI-SPEC.md):

        Доказательная база: {name}
        ERS: {level}/5 · Фактов: {count} · Средневзвешенный si: {weighted_si:.2f}

        {subject} → {predicate} → {object} (si={si:.2f}) [Источник: {source_label}]
        {subject} (si={si:.2f}) [Источник: {source_label}]  -- если predicate/object пусты (Pitfall 5)
        ... (до 5 фактов)

    Args:
        facts:       список фактов (уже отсортирован по wi DESC из _SCHEMA_05)
        substance_id: идентификатор вещества (fallback для имени)
        client:      KBClient для вычисления ERS уровня
        name_map:    dict id→name_ru для отображения русских имён (опционально)

    Returns:
        Plaintext-строка без HTML/Markdown
    """
    if not facts:
        return "Данные в mortality KB не найдены"

    # Имя вещества: name_ru из маппинга или substance_id как fallback
    name = substance_id
    if name_map and substance_id in name_map:
        name = name_map[substance_id]

    level = client.compute_ers_level(facts)
    count = len(facts)

    # D-06/WR-02: единая точка вычисления — тот же взвешенный si кормит и уровень
    # (через client.compute_ers_level -> _compute_weighted_si), и число в заголовке,
    # чтобы показанное значение никогда не расходилось с уровнем, который оно объясняет
    weighted_si = _compute_weighted_si(facts)

    lines = [
        f"Доказательная база: {name}",
        f"ERS: {level}/5 · Фактов: {count} · Средневзвешенный si: {weighted_si:.2f}",
        "",
    ]

    # Топ-5 фактов (facts уже отсортированы ORDER BY wi DESC, si DESC)
    for fact in facts[:5]:
        subject = fact.get("subject", "")
        predicate = fact.get("predicate", "")
        obj = fact.get("object", "")
        si_val = fact.get("si")
        si_str = f"{si_val:.2f}" if si_val is not None else "N/A"
        source_label = _source_label(fact.get("sources"))
        if predicate and obj:
            lines.append(
                f"{subject} → {predicate} → {obj} (si={si_str}) [Источник: {source_label}]"
            )
        else:
            # Pitfall 5: ~75% фактов в базе не разбиты на S->P->O — не рисовать
            # болтающиеся стрелки для факта-предложения без predicate/object
            lines.append(f"{subject} (si={si_str}) [Источник: {source_label}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# KBWorker — QObject worker для QThread (KB-01, KB-04)
# ---------------------------------------------------------------------------

class KBWorker(QObject):
    """Worker Object для выполнения KB-запросов в QThread.

    Паттерн идентичен SimulationWorker из src/ui/worker.py (D-08 Phase 7).
    Перемещается в QThread через moveToThread().

    Signals (Worker → UI):
        result_ready: форматированный текст для QTextEdit.setPlainText()

    Slots (UI → Worker):
        run: запустить KB-запрос для _substance_id
    """

    result_ready = Signal(str)  # форматированный текст для QTextEdit.setPlainText()

    def __init__(self, kb_client: KBClient) -> None:
        super().__init__()
        self._client = kb_client
        self._cancelled: bool = False
        self._substance_id: str | None = None
        # Загрузить маппинг id→name_ru из substances.json (graceful degradation)
        self._name_map: dict = {}
        try:
            substances_path = (
                Path(__file__).parent.parent / "data" / "substances.json"
            )
            data = json.loads(substances_path.read_text(encoding="utf-8"))
            for item in data:
                sub_id = item.get("id", "")
                name_ru = item.get("name_ru", "")
                if sub_id and name_ru:
                    self._name_map[sub_id] = name_ru
        except Exception:
            # graceful degradation — используем substance_id как fallback.
            # IN-01: FileNotFoundError/json.JSONDecodeError уже покрыты Exception.
            pass

    def request_evidence(self, substance_id: str) -> None:
        """Установить целевое вещество и сбросить флаг отмены.

        Вызывается из UI thread — thread-safe присваивание.
        """
        self._cancelled = False
        self._substance_id = substance_id

    def cancel(self) -> None:
        """Установить флаг отмены для текущего запроса.

        Вызывается из UI thread перед запросом нового вещества.
        """
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """Выполнить KB-запрос для _substance_id.

        Вызывается через QThread / queued connection.
        Проверяет _cancelled до и после запроса для предотвращения
        race condition при быстрой смене вещества (Pitfall 2).
        """
        if self._substance_id is None or self._cancelled:
            return
        sub_id = self._substance_id
        try:
            facts = self._client.get_substance_evidence(sub_id)
            if self._cancelled:
                return
            text = _format_facts(facts, sub_id, self._client, self._name_map)
        except Exception as exc:
            if self._cancelled:
                return
            text = f"mortality KB недоступен: {exc}"
        if not self._cancelled:
            self.result_ready.emit(text)


# ---------------------------------------------------------------------------
# ERS — константы и вспомогательная функция (KB-05, KB-07)
# ---------------------------------------------------------------------------

# Русские метки уровней ERS (D-12, D-13; 07-UI-SPEC.md §ERS Badge Format Label by level)
_ERS_LABELS: dict[int, str] = {
    1: "Минимальная",
    2: "Низкая",
    3: "Умеренная",
    4: "Высокая",
    5: "Очень высокая",
}


def _ers_stars(level: int) -> str:
    """Вернуть строку из звёзд для уровня ERS 1–5.

    Символы из 07-UI-SPEC.md §ERS Badge Format Stars by level:
        1=★☆☆☆☆, 2=★★☆☆☆, 3=★★★☆☆, 4=★★★★☆, 5=★★★★★

    Args:
        level: уровень ERS 1–5

    Returns:
        Строка из 5 символов — level закрашенных + (5-level) пустых
    """
    level = max(1, min(5, level))
    return "★" * level + "☆" * (5 - level)


# ---------------------------------------------------------------------------
# update_wiki_ers — обновление YAML frontmatter + ERS callout в .md (KB-07)
# ---------------------------------------------------------------------------

def update_wiki_ers(
    md_path: Path,
    evidence_level: int,
    evidence_label: str,
    fact_count: int,
    avg_si: float,
) -> None:
    """Записать ERS данные в YAML frontmatter и callout Obsidian wiki-файла.

    Обновляет:
        - YAML frontmatter: evidence_level, evidence_label
        - Callout после frontmatter: > [!info] ERS: {stars} {label}

    Stars по уровню (07-UI-SPEC.md §ERS Badge Format):
        1=★☆☆☆☆, 2=★★☆☆☆, 3=★★★☆☆, 4=★★★★☆, 5=★★★★★

    Args:
        md_path:        путь к .md файлу (Path)
        evidence_level: уровень 1–5
        evidence_label: «Минимальная»/«Низкая»/«Умеренная»/«Высокая»/«Очень высокая»
        fact_count:     количество фактов
        avg_si:         средний si
    """
    import re

    text = md_path.read_text(encoding="utf-8")

    # Звёзды по уровню (07-UI-SPEC.md §ERS Badge Format Stars by level)
    stars = _ers_stars(evidence_level)

    # 1. Обновить YAML frontmatter — хирургическая замена нужных полей
    fm_pattern = re.compile(r"^(---\n)(.*?)(---\n)", re.DOTALL | re.MULTILINE)
    match = fm_pattern.match(text)
    if match is None:
        # WR-06: raise instead of silently no-op'ing — the function's contract
        # is to always write the ERS callout; a silent skip here previously
        # left evidence_level/evidence_label unwritten with no error surfaced.
        raise ValueError(f"{md_path}: no YAML frontmatter found, cannot write ERS data")

    fm_body = match.group(2)
    # Удалить старые поля evidence_level / evidence_label если есть
    fm_body = re.sub(r"^evidence_level:.*\n?", "", fm_body, flags=re.MULTILINE)
    fm_body = re.sub(r"^evidence_label:.*\n?", "", fm_body, flags=re.MULTILINE)
    fm_body += f'evidence_level: {evidence_level}\nevidence_label: "{evidence_label}"\n'
    new_frontmatter = f"---\n{fm_body}---\n"
    # WR-06: fm_end anchored to the actual (recomputed) frontmatter boundary
    # instead of re-deriving it via a hardcoded text[4:] magic-number offset,
    # which broke silently for CRLF line endings or files with no frontmatter.
    fm_end = len(new_frontmatter)
    text = new_frontmatter + text[match.end():]

    # 2. Удалить старый ERS callout если есть
    # WR-03: паттерн [★☆]+ идентифицирует именно наш callout, избегая удаления
    # других [!info] блоков пользователя. (?=\n(?!> )|\Z) — до строки без >.
    text = re.sub(
        r"\n> \[!info\] ERS: [★☆]+.*?(?=\n(?!> )|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )

    # 3. Вставить новый callout после frontmatter (fm_end уже указывает точно
    # на позицию сразу после закрывающего "---\n" — см. WR-06 выше)
    callout = (
        f"\n> [!info] ERS: {stars} {evidence_label} доказательная база\n"
        f"> Источник: mortality KB · Фактов: {fact_count} · Средний si: {avg_si:.2f}\n"
    )
    text = text[:fm_end] + callout + text[fm_end:]

    md_path.write_text(text, encoding="utf-8")
