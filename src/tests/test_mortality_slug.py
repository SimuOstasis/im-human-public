# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Регрессионный гейт фазы 13 (INT-01, D-09/D-10): SUBSTANCE_SLUG_MAP в
.neo4j/ingest_cross_links.py должен указывать на content-bearing страницы
Mortality KB (research/biology/*), а не на service/* заглушки.

Загружает .neo4j/ingest_cross_links.py через importlib (файл не в пакете) —
тот же паттерн, что test_kb_client.py::test_ingest_cross_links.
RED до Task 2 (магазин со старыми service/* slug'ами).
"""
import importlib.util
import json
from pathlib import Path

# Корень проекта для построения абсолютных путей
_PROJECT_ROOT = Path(__file__).parents[2]


def _load_ingest_cross_links():
    ingest_path = _PROJECT_ROOT / ".neo4j" / "ingest_cross_links.py"
    spec = importlib.util.spec_from_file_location("ingest_cross_links", ingest_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_substance_ids() -> set[str]:
    substances_path = _PROJECT_ROOT / "src" / "data" / "substances.json"
    with open(substances_path, "r", encoding="utf-8") as f:
        substances = json.load(f)
    return {s["id"] for s in substances}


def test_corrected_slugs_point_at_research_biology_pages():
    """omega3/metformin/rapamycin re-pointed to research/biology/* (D-09)."""
    module = _load_ingest_cross_links()
    slug_map = module.SUBSTANCE_SLUG_MAP

    assert slug_map["omega3"] == "research/biology/omega-3-research"
    assert slug_map["metformin"] == "research/biology/metformin"
    assert slug_map["rapamycin"] == "research/biology/rapamycin"


def test_already_correct_slugs_unchanged():
    """vitamin_d3/nmn were already correct and must stay unchanged (D-09)."""
    module = _load_ingest_cross_links()
    slug_map = module.SUBSTANCE_SLUG_MAP

    assert slug_map["vitamin_d3"] == "research/biology/vitamin-d3"
    assert slug_map["nmn"] == "pathways/nmn-nr"


def test_no_substance_uses_service_prefix():
    """D-09 rule: no substance may point at a service/* stub."""
    module = _load_ingest_cross_links()
    slug_map = module.SUBSTANCE_SLUG_MAP

    for sub_id, slug in slug_map.items():
        assert not slug.startswith("service/"), (
            f"{sub_id} still points at a service/* stub page: {slug!r}"
        )


def test_substances_without_canonical_pages_are_not_mapped():
    """Missing canonical content must not be replaced by a service page."""
    slug_map = _load_ingest_cross_links().SUBSTANCE_SLUG_MAP

    assert "magnesium" not in slug_map
    assert "berberine" not in slug_map


def test_dead_ashwagandha_entry_removed():
    """ashwagandha is not one of the 7 canonical substances.json ids — must be gone."""
    module = _load_ingest_cross_links()
    slug_map = module.SUBSTANCE_SLUG_MAP

    assert "ashwagandha" not in slug_map


def test_map_keys_are_subset_of_canonical_substance_ids():
    """No stray/dead entries: every map key must be a real substances.json id.

    Substances without canonical Mortality pages are intentionally absent.
    """
    module = _load_ingest_cross_links()
    slug_map = module.SUBSTANCE_SLUG_MAP
    canonical_ids = _canonical_substance_ids()

    assert set(slug_map.keys()) <= canonical_ids
