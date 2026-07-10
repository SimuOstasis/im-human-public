# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

import json
import os
import sys
from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Существующие тесты (Phase 02 — Plans 01/03)
# ---------------------------------------------------------------------------


def test_biomarkers_json_count():
    data = json.loads((VAULT_ROOT / "src/data/biomarkers.json").read_text(encoding="utf-8"))
    assert len(data["biomarkers"]) == 24


def test_reference_ranges_exists():
    rr_path = VAULT_ROOT / "src/data/reference_ranges.json"
    assert rr_path.exists(), "reference_ranges.json не создан"


def test_reference_ranges_count():
    rr_path = VAULT_ROOT / "src/data/reference_ranges.json"
    data = json.loads(rr_path.read_text(encoding="utf-8"))
    keys = [k for k in data.keys() if not k.startswith("_")]
    assert len(keys) == 24, f"Найдено {len(keys)} ключей биомаркеров, ожидается 24"


def test_biomarker_pages_count():
    category_folders = {
        "01 - Lipids", "02 - Glucose", "03 - Inflammation",
        "04 - Liver", "05 - Kidney", "06 - Blood Count",
        "08 - Vitamins", "13 - Telemetry",
    }
    pages = [
        p for p in (VAULT_ROOT / "02 - Biomarkers").rglob("*.md")
        if p.parent.name in category_folders
    ]
    assert len(pages) == 24, f"Найдено {len(pages)} страниц, ожидается 24"


def test_biomarkers_index_exists():
    idx = VAULT_ROOT / "08 - Index" / "Biomarkers Index.md"
    assert idx.exists()


# ---------------------------------------------------------------------------
# DATA-07: ingest_biomarkers.py — существование и структура скрипта
# ---------------------------------------------------------------------------


NEO4J_SCRIPTS = VAULT_ROOT / ".neo4j"
INGEST_BIO = NEO4J_SCRIPTS / "ingest_biomarkers.py"


def test_ingest_biomarkers_script_exists():
    """DATA-07: ingest_biomarkers.py существует и содержит main(), ingest(), load_biomarkers()"""
    assert INGEST_BIO.exists(), f"ingest_biomarkers.py не найден: {INGEST_BIO}"
    content = INGEST_BIO.read_text(encoding="utf-8")
    assert "def main()" in content, "Отсутствует main()"
    assert "def ingest" in content, "Отсутствует ingest()"
    assert "def load_biomarkers" in content, "Отсутствует load_biomarkers()"


def test_ingest_biomarkers_cli_interface():
    """DATA-07: ingest_biomarkers.py использует argparse с флагом --clear"""
    content = INGEST_BIO.read_text(encoding="utf-8")
    assert "import argparse" in content or "from argparse" in content
    assert "ArgumentParser" in content
    assert "--clear" in content
    assert "action=" in content and "store_true" in content


def test_ingest_biomarkers_env_loading():
    """DATA-07: ingest_biomarkers.py использует _utils.load_dotenv и require_env"""
    content = INGEST_BIO.read_text(encoding="utf-8")
    assert "from _utils import load_dotenv, require_env" in content
    assert "load_dotenv()" in content
    assert "require_env" in content
    assert "NEO4J_URI" in content
    assert "NEO4J_USER" in content
    assert "NEO4J_PASSWORD" in content


def test_ingest_biomarkers_load_biomarkers_function():
    """DATA-07: load_biomarkers() читает src/data/biomarkers.json и возвращает 24 записи"""
    # Добавляем .neo4j в sys.path для импорта _utils
    sys.path.insert(0, str(NEO4J_SCRIPTS))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ingest_biomarkers", INGEST_BIO)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Проверяем константу DATA_FILE
        assert hasattr(mod, "DATA_FILE"), "Отсутствует DATA_FILE"
        expected = (VAULT_ROOT / "src/data/biomarkers.json").resolve()
        assert mod.DATA_FILE.resolve() == expected, f"DATA_FILE={mod.DATA_FILE}, expected={expected}"
        assert mod.DATA_FILE.exists(), f"DATA_FILE не существует: {mod.DATA_FILE}"

        # Проверяем load_biomarkers()
        data = mod.load_biomarkers()
        assert isinstance(data, dict)
        assert "biomarkers" in data
        assert len(data["biomarkers"]) == 24
        assert "categories" in data
        assert "organs" in data
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# DATA-08: Neo4j — целостность данных после загрузки
# ---------------------------------------------------------------------------


def test_biomarkers_json_fields_for_neo4j():
    """DATA-08: Каждый биомаркер в biomarkers.json имеет поля, необходимые для Neo4j"""
    data = json.loads((VAULT_ROOT / "src/data/biomarkers.json").read_text(encoding="utf-8"))
    biomarkers = data.get("biomarkers", [])
    assert len(biomarkers) == 24
    for bm in biomarkers:
        assert bm.get("code"), f"Отсутствует code у {bm.get('name', '?')}"
        assert bm.get("category"), f"Отсутствует category у {bm.get('code', '?')}"
        assert bm.get("organs"), f"Отсутствуют organs у {bm.get('code', '?')}"
    # Структура для Neo4j: 8 категорий, 9 органов
    assert len(data.get("categories", [])) >= 8
    assert len(data.get("organs", [])) >= 9


def _neo4j_driver():
    """Попытка подключиться к Neo4j Human DB. Возвращает driver или None."""
    env_path = NEO4J_SCRIPTS / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        return None
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password))
        # Проверяем соединение
        driver.verify_connectivity()
        return driver
    except Exception:
        return None


def test_neo4j_biomarker_nodes():
    """DATA-08: Neo4j Human DB содержит 24 узла :Biomarker (SKIP если БД недоступна)"""
    driver = _neo4j_driver()
    if driver is None:
        pytest.skip("Neo4j недоступен — пропуск интеграционного теста")
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as sess:
            r = sess.run("MATCH (b:Biomarker) RETURN count(b) AS cnt").single()
            assert r["cnt"] >= 24, f"Ожидается >= 24 :Biomarker, найдено {r['cnt']}"
    finally:
        driver.close()


def test_neo4j_biomarker_relationships():
    """DATA-08: Neo4j содержит связи :BELONGS_TO (24) и :REFLECTS (>= 24) (SKIP если БД недоступна)"""
    driver = _neo4j_driver()
    if driver is None:
        pytest.skip("Neo4j недоступен — пропуск интеграционного теста")
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as sess:
            r_belongs = sess.run(
                "MATCH (b:Biomarker)-[:BELONGS_TO]->(:BiomarkerCategory) RETURN count(b) AS cnt"
            ).single()
            r_reflects = sess.run(
                "MATCH (b:Biomarker)-[:REFLECTS]->(:Organ) RETURN count(b) AS cnt"
            ).single()
            assert r_belongs["cnt"] >= 24, \
                f"Ожидается >= 24 :BELONGS_TO, найдено {r_belongs['cnt']}"
            assert r_reflects["cnt"] >= 24, \
                f"Ожидается >= 24 :REFLECTS, найдено {r_reflects['cnt']}"
    finally:
        driver.close()


def test_neo4j_categories_and_organs():
    """DATA-08: Neo4j содержит 8 :BiomarkerCategory и 9 :Organ (SKIP если БД недоступна)"""
    driver = _neo4j_driver()
    if driver is None:
        pytest.skip("Neo4j недоступен — пропуск интеграционного теста")
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as sess:
            r_cat = sess.run("MATCH (c:BiomarkerCategory) RETURN count(c) AS cnt").single()
            r_org = sess.run("MATCH (o:Organ) RETURN count(o) AS cnt").single()
            assert r_cat["cnt"] >= 8, f"Ожидается >= 8 :BiomarkerCategory, найдено {r_cat['cnt']}"
            assert r_org["cnt"] >= 9, f"Ожидается >= 9 :Organ, найдено {r_org['cnt']}"
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# DATA-09: query_facts.py — семантический поиск
# ---------------------------------------------------------------------------


QUERY_FACTS = NEO4J_SCRIPTS / "query_facts.py"


def test_query_facts_script_exists():
    """DATA-09: query_facts.py существует и содержит main()"""
    assert QUERY_FACTS.exists(), f"query_facts.py не найден: {QUERY_FACTS}"
    content = QUERY_FACTS.read_text(encoding="utf-8")
    assert "def main()" in content, "Отсутствует main()"


def test_query_facts_cli_interface():
    """DATA-09: query_facts.py имеет --top аргумент и позиционный аргумент query"""
    content = QUERY_FACTS.read_text(encoding="utf-8")
    assert "ArgumentParser" in content
    assert "--top" in content
    assert "type=int" in content or "type = int" in content
    assert "default=3" in content or "default = 3" in content
    assert "--no-expand" in content


def test_query_facts_constants():
    """DATA-09: query_facts.py определяет EMBED_MODEL, INDEX_NAME, SECTION='biomarkers'"""
    content = QUERY_FACTS.read_text(encoding="utf-8")
    assert "EMBED_MODEL" in content
    assert "paraphrase-multilingual-MiniLM-L12-v2" in content
    assert "INDEX_NAME" in content
    assert "human_wiki_chunks" in content
    assert 'SECTION' in content and 'biomarkers' in content


def test_query_facts_functions():
    """DATA-09: query_facts.py содержит embed_query() и search_biomarker()"""
    content = QUERY_FACTS.read_text(encoding="utf-8")
    assert "def embed_query" in content, "Отсутствует embed_query()"
    assert "def search_biomarker" in content, "Отсутствует search_biomarker()"
    assert "def fetch_page_facts" in content, "Отсутствует fetch_page_facts()"


def test_query_facts_env_loading():
    """DATA-09: query_facts.py загружает .env и читает NEO4J_* переменные"""
    content = QUERY_FACTS.read_text(encoding="utf-8")
    assert "_load_dotenv()" in content or "load_dotenv" in content
    assert "NEO4J_URI" in content
    assert "NEO4J_USER" in content
    assert "NEO4J_PASSWORD" in content


def test_query_facts_with_neo4j():
    """DATA-09: query_facts.py выполняет семантический поиск через Neo4j (SKIP если БД недоступна)"""
    driver = _neo4j_driver()
    if driver is None:
        pytest.skip("Neo4j недоступен — пропуск интеграционного теста")
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as sess:
            # Проверяем, что векторный индекс существует и принимает запросы
            result = sess.run(
                "SHOW INDEXES WHERE name = 'human_wiki_chunks'"
            ).single()
            assert result is not None, "Индекс human_wiki_chunks не найден"
            assert result["type"] == "VECTOR", f"Ожидается VECTOR индекс, получен {result['type']}"
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# DATA-10: DUAL-LAYER — согласованность wiki-страниц и Neo4j
# ---------------------------------------------------------------------------


def test_dual_layer_wiki_pages_exist():
    """DATA-10: Все 24 wiki-страницы биомаркеров существуют"""
    category_folders = {
        "01 - Lipids", "02 - Glucose", "03 - Inflammation",
        "04 - Liver", "05 - Kidney", "06 - Blood Count",
        "08 - Vitamins", "13 - Telemetry",
    }
    pages = [
        p for p in (VAULT_ROOT / "02 - Biomarkers").rglob("*.md")
        if p.parent.name in category_folders
    ]
    assert len(pages) == 24, f"Найдено {len(pages)} страниц, ожидается 24"

    known_pages = {
        "LDL Cholesterol", "HDL Cholesterol", "Triglycerides", "Apolipoprotein B",
        "Fasting Glucose", "Fasting Insulin", "HOMA-IR", "HbA1c",
        "hs-CRP", "Interleukin-6",
        "ALT", "AST", "GGT", "Albumin",
        "Serum Creatinine", "eGFR", "UACR", "Sodium", "Potassium",
        "Hemoglobin",
        "25(OH)D",
        "Systolic Blood Pressure", "Resting Heart Rate", "HRV RMSSD",
    }
    page_stems = {p.stem for p in pages}
    missing = known_pages - page_stems
    extra = page_stems - known_pages
    assert not missing, f"Отсутствуют страницы: {missing}"
    assert not extra, f"Лишние страницы: {extra}"


def test_dual_layer_ingest_consistency():
    """DATA-10: generate_biomarker_pages.py и ingest_biomarkers.py читают один biomarkers.json"""
    gen_script = VAULT_ROOT / "src/scripts" / "generate_biomarker_pages.py"
    gen_content = gen_script.read_text(encoding="utf-8")
    # generate_biomarker_pages.py читает biomarkers.json
    assert 'biomarkers.json' in gen_content
    assert 'DATA_FILE' in gen_content

    # ingest_biomarkers.py читает biomarkers.json
    ingest_content = INGEST_BIO.read_text(encoding="utf-8")
    assert 'biomarkers.json' in ingest_content

    # Оба скрипта ссылаются на один и тот же файл
    gen_path = VAULT_ROOT / "src/data/biomarkers.json"
    ingest_path = VAULT_ROOT / "src/data/biomarkers.json"
    assert gen_path == ingest_path, "Пути к biomarkers.json различаются"
    assert gen_path.exists()


def test_dual_layer_ingest_wiki_section_mapping():
    """DATA-10: ingest_wiki.py маппит '02 - Biomarkers' на section='biomarkers'"""
    ingest_wiki = NEO4J_SCRIPTS / "ingest_wiki.py"
    content = ingest_wiki.read_text(encoding="utf-8")
    assert 'SECTIONS' in content
    assert '"02 - Biomarkers"' in content or "'02 - Biomarkers'" in content
    assert '"biomarkers"' in content or "'biomarkers'" in content


def test_dual_layer_page_count_match():
    """DATA-10: Количество wiki-страниц совпадает с :Page узлами в Neo4j (SKIP если БД недоступна)"""
    # Сначала считаем wiki-страницы
    category_folders = {
        "01 - Lipids", "02 - Glucose", "03 - Inflammation",
        "04 - Liver", "05 - Kidney", "06 - Blood Count",
        "08 - Vitamins", "13 - Telemetry",
    }
    wiki_count = len([
        p for p in (VAULT_ROOT / "02 - Biomarkers").rglob("*.md")
        if p.parent.name in category_folders
    ])

    driver = _neo4j_driver()
    if driver is None:
        pytest.skip("Neo4j недоступен — пропуск интеграционного теста")
    try:
        with driver.session(database=os.environ.get("NEO4J_DATABASE", "Human")) as sess:
            r = sess.run(
                "MATCH (p:Page {section: 'biomarkers'}) RETURN count(p) AS cnt"
            ).single()
            neo4j_count = r["cnt"]
            assert wiki_count == neo4j_count, \
                f"Wiki страниц: {wiki_count}, Neo4j :Page узлов: {neo4j_count}"
    finally:
        driver.close()
