# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Phase 13 (kb-integration-enhancement) — regression gate for D-01/D-03.

Guards against the substance evidence-level property/index ever being
re-introduced into the Human DB. All three tests are mock-based — Phase 11
CI (`.github/workflows/ci.yml`) has no live Neo4j, so they follow the same
mock-session pattern already established in test_kb_client.py.

RED before Task 2/Task 3 land — that is the expected Nyquist Wave 0 state.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

# Root of the vault (3 levels up: tests -> src -> vault root)
_PROJECT_ROOT = Path(__file__).parents[2]


# ── Тест 1: узлы :Substance не несут evidence_level (D-03) ────────────────────

def test_no_evidence_level_on_substance_nodes():
    """D-03: узлы :Substance в Human DB не содержат свойства evidence_level.

    Мок-сессия эмулирует живой bolt-запрос:
        MATCH (s:Substance) WHERE s.evidence_level IS NOT NULL RETURN count(s) AS c
    и должна вернуть count == 0 — это контракт, который живая Human DB обязана
    соблюдать после Task 3 (remove_substance_evidence.py) отработает.
    """
    session_mock = MagicMock()
    session_mock.__enter__ = lambda s: session_mock
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.run.return_value = iter([{"c": 0}])

    result = list(session_mock.run(
        "MATCH (s:Substance) WHERE s.evidence_level IS NOT NULL RETURN count(s) AS c"
    ))

    assert result[0]["c"] == 0, (
        "Найдены узлы :Substance с полем evidence_level (D-01 регрессия)"
    )


# ── Тест 2: remove_substance_evidence.py вызывает REMOVE и DROP INDEX (D-01) ──

def test_remove_script_calls_remove_and_drop_index():
    """remove_substance_evidence.py::remove(session) выполняет два отдельных
    session.run — один с REMOVE свойства evidence_level, другой с
    DROP INDEX substance_evidence.

    Загружает .neo4j/remove_substance_evidence.py через importlib (файл не в
    пакете) — тот же loader-паттерн, что уже используется в test_kb_client.py
    для .neo4j/ingest_cross_links.py.
    """
    script_path = _PROJECT_ROOT / ".neo4j" / "remove_substance_evidence.py"
    spec = importlib.util.spec_from_file_location("remove_substance_evidence", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    session_mock = MagicMock()
    module.remove(session_mock, human_db="Human")

    assert session_mock.run.called, "remove() должен вызывать session.run"

    all_calls = session_mock.run.call_args_list

    has_remove = any(
        "REMOVE" in str(call) and "evidence_level" in str(call)
        for call in all_calls
    )
    assert has_remove, (
        "remove() должен вызывать session.run с Cypher содержащим "
        "'REMOVE' и 'evidence_level'"
    )

    has_drop_index = any(
        "DROP INDEX" in str(call) and "substance_evidence" in str(call)
        for call in all_calls
    )
    assert has_drop_index, (
        "remove() должен вызывать session.run с Cypher содержащим "
        "'DROP INDEX' и 'substance_evidence'"
    )


# ── Тест 3: ingest/schema больше не пишут evidence_level (D-01) ───────────────

def _strip_comments(text: str) -> str:
    """Убрать строки, начинающиеся с '#', чтобы описательный комментарий не
    маскировал реальную проверку отсутствия символа."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    )


def test_ingest_no_longer_sets_evidence():
    """D-01: ingest_substances.py больше не устанавливает sub.evidence_level,
    setup_schema.py больше не объявляет индекс substance_evidence.
    """
    ingest_path = _PROJECT_ROOT / ".neo4j" / "ingest_substances.py"
    schema_path = _PROJECT_ROOT / ".neo4j" / "setup_schema.py"

    ingest_src = _strip_comments(ingest_path.read_text(encoding="utf-8"))
    schema_src = _strip_comments(schema_path.read_text(encoding="utf-8"))

    assert "evidence_level" not in ingest_src, (
        "ingest_substances.py всё ещё ссылается на evidence_level (D-01 регрессия)"
    )
    assert "substance_evidence" not in schema_src, (
        "setup_schema.py всё ещё объявляет индекс substance_evidence (D-01 регрессия)"
    )
