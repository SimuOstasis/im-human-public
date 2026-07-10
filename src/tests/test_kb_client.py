# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""TDD-гейт фазы 7: Knowledge Base Integration.

Покрывает все требования KB-01..KB-07 через mock Neo4j driver и offscreen Qt.
Wave 0 — тесты написаны ДО реализации: все тесты должны падать RED до Wave 2+.

ОБЯЗАТЕЛЬНО: QT_QPA_PLATFORM=offscreen устанавливается ДО любого импорта PySide6
чтобы Qt не пытался открыть реальный дисплей (аналог паттерна из test_ui_integration.py).
"""
import os

# Установить до импорта PySide6 — Qt не пытается открыть дисплей
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Корень проекта для построения абсолютных путей
_PROJECT_ROOT = Path(__file__).parents[2]


# ── Module-level fixture для QApplication (singleton per process) ──────────────

@pytest.fixture(scope="module")
def app():
    """QApplication singleton: создаётся один раз на весь модуль тестов.

    Паттерн идентичен test_ui_integration.py — избегаем создания дублирующего
    QApplication если тесты запускаются вместе с другими модулями.
    """
    from PySide6.QtWidgets import QApplication
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance
    instance.processEvents()


# ── Вспомогательная функция: mock KBClient без реального Neo4j ────────────────

def _make_mock_client():
    """Создать KBClient минуя __init__ (без реального подключения к Neo4j).

    Паттерн: KBClient.__new__(KBClient) обходит __init__, затем присваиваем
    _driver/базы вручную (из RESEARCH.md §Mock Strategy).
    """
    from src.engine.kb_client import KBClient  # noqa: PLC0415

    client = KBClient.__new__(KBClient)
    client._driver = MagicMock()
    client._human_db = "Human"
    client._mortality_db = "Mortality"
    return client


def _make_session_mock(side_effects):
    """Создать mock сессии Neo4j с заданными side_effects для session.run.

    session_mock.__enter__ возвращает себя (context manager паттерн).
    side_effects: список значений, которые поочерёдно возвращает session.run.
    """
    session_mock = MagicMock()
    session_mock.__enter__ = lambda s: session_mock
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.run.side_effect = side_effects
    return session_mock


# ── Тест 1: импорт KBClient и KBWorker (KB-01) ────────────────────────────────

def test_kb_client_imports():
    """KB-01: KBClient и KBWorker импортируются из src.engine.kb_client без ошибок.

    RED: этот тест упадёт с ImportError/ModuleNotFoundError до Wave 2, когда
    src/engine/kb_client.py будет создан. Это ожидаемое поведение Wave 0.
    """
    from src.engine.kb_client import KBClient, KBWorker  # noqa: F401, PLC0415

    assert KBClient is not None, "KBClient должен быть классом"
    assert KBWorker is not None, "KBWorker должен быть классом"


# ── Тест 2: get_substance_evidence возвращает факты (KB-02) ───────────────────

def test_get_substance_evidence():
    """KB-02: get_substance_evidence('omega3') возвращает непустой list[dict]
    с ключами subject/predicate/object/si/wi при наличии slug в Human DB.

    RED: упадёт с ImportError до Wave 2.
    """
    mock_facts = [
        {
            "subject": "omega-3",
            "predicate": "reduces",
            "object": "triglycerides",
            "si": 0.91,
            "wi": 0.87,
        }
    ]

    client = _make_mock_client()
    # Два отдельных session mock — Human DB (slug lookup) и Mortality DB (факты)
    slug_session = MagicMock()
    slug_session.__enter__ = lambda s: slug_session
    slug_session.__exit__ = MagicMock(return_value=False)
    slug_session.run.return_value = iter([{"slug": "omega-3"}])

    facts_session = MagicMock()
    facts_session.__enter__ = lambda s: facts_session
    facts_session.__exit__ = MagicMock(return_value=False)
    facts_session.run.return_value = iter(mock_facts)

    client._driver.session.side_effect = [slug_session, facts_session]

    result = client.get_substance_evidence("omega3")

    assert isinstance(result, list), "Результат должен быть списком"
    assert len(result) >= 1, "Должен вернуть хотя бы один факт"
    assert result[0]["predicate"] == "reduces", "Predicate должен совпасть с mock"
    assert "subject" in result[0], "Факт должен содержать ключ 'subject'"
    assert "si" in result[0], "Факт должен содержать ключ 'si'"


# ── Тест 3: get_biomarker_context возвращает факты (KB-03) ────────────────────

def test_get_biomarker_context():
    """KB-03: get_biomarker_context('ldlC') возвращает список фактов.

    Slug берётся из :Biomarker {code} в Human DB, затем запрашивается Mortality DB.
    RED: упадёт с ImportError до Wave 2.
    """
    mock_facts = [
        {
            "subject": "ldl-cholesterol",
            "predicate": "associated_with",
            "object": "cardiovascular-risk",
            "si": 0.88,
            "wi": 0.84,
        }
    ]

    client = _make_mock_client()
    # Два отдельных session mock — Human DB (slug lookup) и Mortality DB (факты)
    slug_session = MagicMock()
    slug_session.__enter__ = lambda s: slug_session
    slug_session.__exit__ = MagicMock(return_value=False)
    slug_session.run.return_value = iter([{"slug": "ldl-cholesterol"}])

    facts_session = MagicMock()
    facts_session.__enter__ = lambda s: facts_session
    facts_session.__exit__ = MagicMock(return_value=False)
    facts_session.run.return_value = iter(mock_facts)

    client._driver.session.side_effect = [slug_session, facts_session]

    result = client.get_biomarker_context("ldlC")

    assert isinstance(result, list), "Результат должен быть списком"
    assert len(result) >= 1, "Должен вернуть хотя бы один факт"
    assert "subject" in result[0], "Факт должен содержать ключ 'subject'"


# ── Тест 4: graceful degradation — нет slug (KB-02, D-11) ────────────────────

def test_get_substance_evidence_no_slug():
    """KB-02 graceful degradation (D-11): если slug отсутствует (single() → None),
    get_substance_evidence возвращает пустой список без исключения.

    RED: упадёт с ImportError до Wave 2.
    """
    client = _make_mock_client()
    # single() вернёт None — slug не найден
    session_mock = _make_session_mock(
        side_effects=[
            iter([]),  # пустой итератор → single() даёт None
        ]
    )
    client._driver.session.return_value = session_mock

    result = client.get_substance_evidence("unknown_substance")

    assert result == [], "При отсутствии slug должен вернуть пустой список"


# ── Тест 5: SubstanceManager — split-режим с QSplitter (KB-04) ───────────────

def test_substance_manager_tabs(app):
    """KB-04: SubstanceManager в split-режиме (default):
    - self.tabs (QTabWidget) с одной вкладкой «Список» — слева в QSplitter
    - self.kb_text (QTextEdit, read-only) — справа в QSplitter
    - self._splitter (QSplitter) объединяет обе стороны

    Tabs-режим (future config): self.tabs получит вторую вкладку «Научный контекст».
    """
    from PySide6.QtWidgets import QSplitter, QTabWidget, QTextEdit  # noqa: PLC0415
    from src.ui.substance_manager import SubstanceManager  # noqa: PLC0415

    sm = SubstanceManager()

    try:
        # split-режим: QSplitter содержит tabs слева и kb_text справа
        assert hasattr(sm, "_splitter"), "SubstanceManager должен иметь атрибут _splitter"
        assert isinstance(sm._splitter, QSplitter), "_splitter должен быть QSplitter"

        # Левая сторона: QTabWidget с вкладкой «Список»
        assert hasattr(sm, "tabs"), "SubstanceManager должен иметь атрибут tabs"
        tabs = sm.tabs
        assert isinstance(tabs, QTabWidget), "tabs должен быть QTabWidget"
        assert tabs.count() >= 1, f"Ожидается >= 1 вкладки, получено {tabs.count()}"
        assert tabs.tabText(0) == "Список", (
            f"Вкладка 0 должна называться 'Список', получено '{tabs.tabText(0)}'"
        )

        # Правая сторона: read-only QTextEdit
        assert hasattr(sm, "kb_text"), "SubstanceManager должен иметь атрибут kb_text"
        assert isinstance(sm.kb_text, QTextEdit), "kb_text должен быть QTextEdit"
        assert sm.kb_text.isReadOnly(), "kb_text должен быть read-only"
    finally:
        # Очистить KB thread если запущен
        kb_worker = getattr(sm, "_kb_worker", None)
        if kb_worker is not None:
            kb_worker._cancelled = True
        kb_thread = getattr(sm, "_kb_thread", None)
        if kb_thread is not None and kb_thread.isRunning():
            kb_thread.quit()
            kb_thread.wait(5000)
        sm.close()
        app.processEvents()


# ── Тест 6: ingest_cross_links добавляет mortality_slug (KB-06) ───────────────

def test_ingest_cross_links():
    """KB-06: ingest_cross_links.ingest(session) вызывает session.run с Cypher
    содержащим 'SET' и 'mortality_slug' для веществ и биомаркеров.

    Загружает .neo4j/ingest_cross_links.py через importlib (файл не в пакете).
    RED: упадёт с FileNotFoundError до Wave 1.
    """
    ingest_path = _PROJECT_ROOT / ".neo4j" / "ingest_cross_links.py"
    spec = importlib.util.spec_from_file_location("ingest_cross_links", ingest_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    session_mock = MagicMock()
    module.ingest(session_mock, human_db="Human")

    # Проверить что session.run вызывался хотя бы раз
    assert session_mock.run.called, "ingest должен вызывать session.run"

    # Проверить что хотя бы один вызов содержит SET и mortality_slug
    all_calls = session_mock.run.call_args_list
    has_set = any(
        "SET" in str(call) and "mortality_slug" in str(call)
        for call in all_calls
    )
    assert has_set, (
        "ingest должен вызывать session.run с Cypher содержащим 'SET' и 'mortality_slug'"
    )


# ── Тест 7: update_wiki_ers обновляет frontmatter и callout (KB-05/KB-07) ─────

def test_update_wiki_ers(tmp_path):
    """KB-05/KB-07: update_wiki_ers записывает evidence_level и evidence_label
    в YAML frontmatter и добавляет callout-блок [!info] ERS со звёздами.

    RED: упадёт с ImportError до Wave 2.
    """
    from src.engine.kb_client import update_wiki_ers  # noqa: PLC0415

    # Создать временный .md файл с минимальным frontmatter
    md_file = tmp_path / "Test Substance.md"
    md_file.write_text(
        "---\ntags: [substance, test]\n---\n\n# Test Substance\n\nОписание вещества.\n",
        encoding="utf-8",
    )

    update_wiki_ers(
        md_path=md_file,
        evidence_level=4,
        evidence_label="Высокая",
        fact_count=12,
        avg_si=0.78,
    )

    result = md_file.read_text(encoding="utf-8")

    assert "evidence_level: 4" in result, (
        "Frontmatter должен содержать 'evidence_level: 4'"
    )
    assert "evidence_label" in result, (
        "Frontmatter должен содержать 'evidence_label'"
    )
    # Проверить callout ERS — подстрока [!info] ERS
    assert "[!info] ERS" in result, "Файл должен содержать callout [!info] ERS"
    # Проверить наличие звёзд (4 закрашенных для уровня 4 из 5)
    assert "★★★★" in result, "Callout должен содержать 4 заполненных звезды (★★★★)"
    assert "☆" in result, "Callout должен содержать 1 пустую звезду (☆)"


# ── Тест 8: KBWorker сигналы и отмена (KB-01, KB-04) ─────────────────────────

def test_kb_worker_signals():
    """KB-01, KB-04: KBWorker объявляет result_ready = Signal(str);
    request_evidence устанавливает _cancelled=False;
    cancel устанавливает _cancelled=True.

    RED: упадёт с ImportError до Wave 2.
    """
    from PySide6.QtCore import Signal  # noqa: PLC0415
    from src.engine.kb_client import KBWorker  # noqa: PLC0415

    # KBWorker должен иметь атрибут result_ready как Signal(str)
    assert hasattr(KBWorker, "result_ready"), (
        "KBWorker должен объявлять result_ready = Signal(str)"
    )

    # Создать экземпляр с mock-клиентом
    mock_client = MagicMock()
    worker = KBWorker(mock_client)

    # request_evidence должен сбрасывать _cancelled в False
    worker.request_evidence("omega3")
    assert worker._cancelled is False, (
        "После request_evidence _cancelled должен быть False"
    )

    # cancel должен устанавливать _cancelled в True
    worker.cancel()
    assert worker._cancelled is True, (
        "После cancel _cancelled должен быть True"
    )
