# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
Phase 4 — M3 Substance & Intervention Model: test suite (SUBS-09).

TDD gate for Waves 2-3: tests are written first; they will initially
fail when artifacts are missing — that is the correct RED state.
"""
import json
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level root (3 levels up: tests → src → vault root)
# ---------------------------------------------------------------------------
VAULT_ROOT = Path(__file__).parent.parent.parent

# Expected substance IDs (D-01)
_EXPECTED_IDS = [
    "omega3",
    "vitamin_d3",
    "magnesium",
    "berberine",
    "metformin",
    "rapamycin",
    "nmn",
]

# Required top-level fields in every substance entry (D-02, D-05, ingest_substances.py schema)
_REQUIRED_FIELDS = [
    "id", "name", "name_ru", "category",
    "doseUnit", "minDose", "maxDose", "defaultDose",
    "bioavailability", "halfLifeHours", "effectProfile", "targetSystems",
]

# Required fields in every interaction entry (CONTEXT.md interaction matrix spec)
_INTERACTION_FIELDS = ["substanceA", "substanceB", "type", "coefficient", "description"]


# ---------------------------------------------------------------------------
# 1. substances.json count and IDs
# ---------------------------------------------------------------------------
def test_substances_json_count():
    """substances.json must contain exactly 7 entries with the canonical IDs."""
    substances_path = VAULT_ROOT / "src" / "data" / "substances.json"
    assert substances_path.exists(), (
        f"substances.json не найден: {substances_path}"
    )
    data = json.loads(substances_path.read_text(encoding="utf-8"))
    assert len(data) == 7, (
        f"Ожидается 7 веществ, найдено {len(data)}: {[s.get('id') for s in data]}"
    )
    found_ids = {s.get("id") for s in data}
    missing = sorted(set(_EXPECTED_IDS) - found_ids)
    assert not missing, (
        f"Отсутствуют вещества с ID: {missing}"
    )


# ---------------------------------------------------------------------------
# 2. Schema validation for every substance
# ---------------------------------------------------------------------------
def test_substance_schema_fields():
    """Every substance must have all required fields and correct category values."""
    substances_path = VAULT_ROOT / "src" / "data" / "substances.json"
    assert substances_path.exists(), "substances.json не найден"
    data = json.loads(substances_path.read_text(encoding="utf-8"))

    # Category rules (D-02)
    _DRUGS = {"metformin", "rapamycin"}
    _SUPPLEMENTS = {"omega3", "vitamin_d3", "magnesium", "berberine", "nmn"}

    for s in data:
        sub_id = s.get("id", "<unknown>")
        # Required fields
        missing_fields = [f for f in _REQUIRED_FIELDS if f not in s]
        assert not missing_fields, (
            f"Вещество '{sub_id}': отсутствуют поля {missing_fields}"
        )
        # Category assertion (D-02)
        if sub_id in _DRUGS:
            assert s["category"] == "drug", (
                f"'{sub_id}' должен иметь category='drug', получено '{s['category']}'"
            )
        elif sub_id in _SUPPLEMENTS:
            assert s["category"] == "supplement", (
                f"'{sub_id}' должен иметь category='supplement', получено '{s['category']}'"
            )


# ---------------------------------------------------------------------------
# 3. Dose validator rejects overdose (D-06)
# ---------------------------------------------------------------------------
def test_dose_validator_rejects_overdose():
    """IntakeSchedule must raise ValidationError when dose_mg > maxDose."""
    try:
        from src.domain.substance import SubstanceDefinition, IntakeSchedule, CycleConfig  # noqa: F401
        from pydantic import ValidationError
    except ImportError as exc:
        pytest.skip(f"src.domain.substance не создан ещё: {exc}")

    substances_path = VAULT_ROOT / "src" / "data" / "substances.json"
    assert substances_path.exists(), "substances.json не найден"
    data = json.loads(substances_path.read_text(encoding="utf-8"))

    omega3 = next((s for s in data if s["id"] == "omega3"), None)
    assert omega3 is not None, "omega3 не найден в substances.json"

    # Overdose: double the max dose must fail
    with pytest.raises(ValidationError):
        IntakeSchedule(
            substance_id="omega3",
            dose_mg=omega3["maxDose"] * 2,
            interval_hours=24.0,
            hour_of_day=8,
            cycle=None,
            start_tick=0,
            duration_ticks=None,
            min_dose=omega3["minDose"],
            max_dose=omega3["maxDose"],
        )

    # Valid dose must succeed
    valid_schedule = IntakeSchedule(
        substance_id="omega3",
        dose_mg=omega3["defaultDose"],
        interval_hours=24.0,
        hour_of_day=8,
        cycle=None,
        start_tick=0,
        duration_ticks=None,
        min_dose=omega3["minDose"],
        max_dose=omega3["maxDose"],
    )
    assert valid_schedule.dose_mg == omega3["defaultDose"]


# ---------------------------------------------------------------------------
# 4. IntakeSchedule creation (D-07)
# ---------------------------------------------------------------------------
def test_intake_schedule_creation():
    """IntakeSchedule must be creatable with all 7 required fields accessible."""
    try:
        from src.domain.substance import IntakeSchedule
    except ImportError as exc:
        pytest.skip(f"src.domain.substance не создан ещё: {exc}")

    schedule = IntakeSchedule(
        substance_id="omega3",
        dose_mg=2000.0,       # within Omega-3 range 500–4000
        interval_hours=24.0,
        hour_of_day=8,
        cycle=None,
        start_tick=0,
        duration_ticks=None,
        min_dose=500.0,
        max_dose=4000.0,
    )
    # Assert all 7 core fields are accessible
    assert schedule.substance_id == "omega3"
    assert schedule.dose_mg == 2000.0
    assert schedule.interval_hours == 24.0
    assert schedule.hour_of_day == 8
    assert schedule.cycle is None
    assert schedule.start_tick == 0
    assert schedule.duration_ticks is None


# ---------------------------------------------------------------------------
# 5. CycleConfig for Rapamycin (D-08)
# ---------------------------------------------------------------------------
def test_cycle_config_rapamycin():
    """CycleConfig on_days=1, off_days=6 must work and attach to IntakeSchedule."""
    try:
        from src.domain.substance import IntakeSchedule, CycleConfig
    except ImportError as exc:
        pytest.skip(f"src.domain.substance не создан ещё: {exc}")

    cycle = CycleConfig(on_days=1, off_days=6)
    assert cycle.on_days == 1
    assert cycle.off_days == 6

    schedule = IntakeSchedule(
        substance_id="rapamycin",
        dose_mg=5.0,
        interval_hours=24.0,
        hour_of_day=8,
        cycle=CycleConfig(on_days=1, off_days=6),
        start_tick=0,
        duration_ticks=None,
        min_dose=1.0,
        max_dose=10.0,
    )
    assert schedule.cycle is not None
    assert schedule.cycle.on_days == 1


# ---------------------------------------------------------------------------
# 6. SubstanceDefinition.from_json (D-05, D-09)
# ---------------------------------------------------------------------------
def test_substance_from_json():
    """SubstanceDefinition.from_json must parse omega3 correctly."""
    try:
        from src.domain.substance import SubstanceDefinition
    except ImportError as exc:
        pytest.skip(f"src.domain.substance не создан ещё: {exc}")

    substances_path = VAULT_ROOT / "src" / "data" / "substances.json"
    assert substances_path.exists(), "substances.json не найден"
    data = json.loads(substances_path.read_text(encoding="utf-8"))

    omega3_dict = next((s for s in data if s["id"] == "omega3"), None)
    assert omega3_dict is not None, "omega3 не найден в substances.json"

    result = SubstanceDefinition.from_json(omega3_dict)
    assert result.id == "omega3"
    assert result.category == "supplement"
    assert result.half_life_hours > 0
    assert result.bioavailability > 0
    assert len(result.effect_profile) > 0


# ---------------------------------------------------------------------------
# 7. interactions.json schema (CONTEXT.md spec)
# ---------------------------------------------------------------------------
def test_interactions_json_schema():
    """interactions.json must have synergy, antagonism, and toxicity entries."""
    interactions_path = VAULT_ROOT / "src" / "data" / "interactions.json"
    assert interactions_path.exists(), (
        f"interactions.json не найден: {interactions_path}"
    )
    data = json.loads(interactions_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) > 0, (
        "interactions.json должен быть непустым списком"
    )

    types_found = {entry.get("type") for entry in data}
    assert "synergy" in types_found, "interactions.json: нет ни одной записи type='synergy'"
    assert "antagonism" in types_found, "interactions.json: нет ни одной записи type='antagonism'"
    assert "toxicity" in types_found, "interactions.json: нет ни одной записи type='toxicity'"

    for i, entry in enumerate(data):
        missing = [f for f in _INTERACTION_FIELDS if f not in entry]
        assert not missing, (
            f"interactions.json[{i}]: отсутствуют поля {missing}"
        )


# ---------------------------------------------------------------------------
# 8. Neo4j Substance → Biomarker links
# ---------------------------------------------------------------------------
def test_neo4j_substance_biomarker_links():
    """Neo4j must have HAS_EFFECT→ON_BIOMARKER chains for all 7 substances."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        pytest.skip("neo4j driver не установлен")

    # Load .env from .neo4j/.env
    env_path = VAULT_ROOT / ".neo4j" / ".env"
    env_vars: dict = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env_vars[key.strip()] = val.strip()

    uri = env_vars.get("NEO4J_URI", "")
    user = env_vars.get("NEO4J_USER", "")
    password = env_vars.get("NEO4J_PASSWORD", "")
    database = env_vars.get("NEO4J_DATABASE", "Human")

    if not uri or not user or not password:
        pytest.skip("Neo4j credentials не найдены в .neo4j/.env")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
    except Exception as exc:
        pytest.skip(f"Neo4j недоступен (подключение): {exc}")

    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (s:Substance)-[:HAS_EFFECT]->(e:Effect)-[:ON_BIOMARKER]->(b:Biomarker) "
            "RETURN s.id AS substance_id, count(b) AS cnt"
        )
        rows = result.data()
    driver.close()

    assert len(rows) > 0, "Neo4j: нет связей Substance→Effect→Biomarker"
    found_ids = {row["substance_id"] for row in rows}
    missing = sorted(set(_EXPECTED_IDS) - found_ids)
    assert not missing, (
        f"Neo4j: отсутствуют вещества без эффектов: {missing}"
    )


# ---------------------------------------------------------------------------
# 9. Substance wiki pages exist in 03 - Substances/ (SUBS-04, GAP-04-01)
# ---------------------------------------------------------------------------
# Expected filenames use Latin Title Case with spaces (CLAUDE.md convention)
_SUBSTANCE_FILE_NAMES = {
    "omega3": "Omega-3",
    "vitamin_d3": "Vitamin D3",
    "magnesium": "Magnesium",
    "berberine": "Berberine",
    "metformin": "Metformin",
    "rapamycin": "Rapamycin",
    "nmn": "NMN",
}


def test_substance_wiki_pages_exist():
    """All 7 substance wiki pages must exist in 03 - Substances/ with correct filenames (SUBS-04)."""
    substances_dir = VAULT_ROOT / "03 - Substances"
    assert substances_dir.is_dir(), (
        f"Папка '03 - Substances' не найдена: {substances_dir}"
    )

    missing = []
    for sub_id, filename in _SUBSTANCE_FILE_NAMES.items():
        page = substances_dir / f"{filename}.md"
        if not page.exists():
            missing.append(f"{filename}.md (id={sub_id})")

    assert not missing, (
        f"Отсутствуют wiki-страницы веществ: {missing}. "
        f"Ожидаемые файлы в '{substances_dir}': "
        f"{[f'{v}.md' for v in _SUBSTANCE_FILE_NAMES.values()]}"
    )

    # Also verify count matches (no extra stray files)
    md_files = list(substances_dir.glob("*.md"))
    assert len(md_files) == 7, (
        f"В '03 - Substances' найдено {len(md_files)} .md файлов вместо 7: "
        f"{[p.name for p in md_files]}"
    )


# ---------------------------------------------------------------------------
# 10. ingest_substances.py exists with required content (SUBS-06, GAP-04-02)
# ---------------------------------------------------------------------------
def test_ingest_substances_script_exists():
    """ingest_substances.py must exist at .neo4j/ and contain 'def ingest' and 'HAS_EFFECT' (SUBS-06)."""
    ingest_path = VAULT_ROOT / ".neo4j" / "ingest_substances.py"
    assert ingest_path.exists(), (
        f"ingest_substances.py не найден: {ingest_path}"
    )

    content = ingest_path.read_text(encoding="utf-8")

    assert "def ingest" in content, (
        "ingest_substances.py: отсутствует 'def ingest'"
    )
    assert "HAS_EFFECT" in content, (
        "ingest_substances.py: отсутствует 'HAS_EFFECT'"
    )
    assert "ON_BIOMARKER" in content, (
        "ingest_substances.py: отсутствует 'ON_BIOMARKER'"
    )


# ---------------------------------------------------------------------------
# 11. Interactions Index wiki page exists (SUBS-08, GAP-04-03)
# ---------------------------------------------------------------------------
def test_interactions_index_wiki_page():
    """04 - Interactions/Interactions Index.md must exist (SUBS-08)."""
    index_path = VAULT_ROOT / "04 - Interactions" / "Interactions Index.md"
    assert index_path.exists(), (
        f"Interactions Index.md не найден: {index_path}"
    )

    content = index_path.read_text(encoding="utf-8")
    assert len(content) > 100, (
        "Interactions Index.md пустой или слишком короткий (< 100 символов)"
    )


# ---------------------------------------------------------------------------
# 12. SC-4: Collective wiki pages check (phase-level success criterion)
# ---------------------------------------------------------------------------
def test_phase4_sc4_wiki_pages_exist():
    """SC-4: 7 substance wiki pages + Interactions Index must all exist."""
    # Check substance pages
    substances_dir = VAULT_ROOT / "03 - Substances"
    assert substances_dir.is_dir(), (
        f"SC-4 FAIL: папка '03 - Substances' не найдена"
    )

    md_files = list(substances_dir.glob("*.md"))
    assert len(md_files) == 7, (
        f"SC-4 FAIL: в '03 - Substances' найдено {len(md_files)} .md вместо 7: "
        f"{[p.name for p in md_files]}"
    )

    # Check Interactions Index
    index_path = VAULT_ROOT / "04 - Interactions" / "Interactions Index.md"
    assert index_path.exists(), (
        f"SC-4 FAIL: '04 - Interactions/Interactions Index.md' не найден"
    )

    # Cross-check: each substance page filename matches expected set
    found_names = {p.stem for p in md_files}
    expected_names = set(_SUBSTANCE_FILE_NAMES.values())
    unexpected = found_names - expected_names
    missing = expected_names - found_names
    assert not unexpected and not missing, (
        f"SC-4 FAIL: несовпадение имён файлов. "
        f"Неожиданные: {unexpected}, Отсутствуют: {missing}"
    )
