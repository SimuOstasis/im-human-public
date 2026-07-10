#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Generate Obsidian wiki pages for all 7 MVP substances.

Reads src/data/substances.json + src/data/interactions.json + src/data/biomarkers.json,
writes 7 .md files into 03 - Substances/, Interactions Index into 04 - Interactions/,
updates ## Влияние веществ sections on biomarker pages, and adds HOME.md entries.

Skip-if-exists: Obsidian is source of truth (D-03) for substance pages.
Biomarker pages: only the ## Влияние веществ section is replaced/appended.

DUAL-LAYER: Markdown FIRST, Neo4j ingest in Plan 05.

Usage (PowerShell from vault root):
    $env:PYTHONIOENCODING="utf-8"
    venv\\Scripts\\python.exe src/scripts/generate_substance_pages.py
    venv\\Scripts\\python.exe src/scripts/generate_substance_pages.py --dry-run
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# CRITICAL: scripts/ is 3 levels below vault root (scripts->src->vault)
# generate script uses: Path(__file__).parent.parent.parent  (scripts->src->vault)
VAULT_ROOT = Path(__file__).parent.parent.parent
SUBSTANCES_FILE = VAULT_ROOT / "src" / "data" / "substances.json"
INTERACTIONS_FILE = VAULT_ROOT / "src" / "data" / "interactions.json"
BIOMARKERS_FILE = VAULT_ROOT / "src" / "data" / "biomarkers.json"
SUBSTANCES_DIR = VAULT_ROOT / "03 - Substances"
INTERACTIONS_DIR = VAULT_ROOT / "04 - Interactions"
HOME_FILE = VAULT_ROOT / "HOME.md"

# ---------------------------------------------------------------------------
# Mapping constants
# ---------------------------------------------------------------------------

# Latin Title Case filenames per CLAUDE.md convention
SUBSTANCE_FILE_NAMES: dict[str, str] = {
    "omega3":      "Omega-3",
    "vitamin_d3":  "Vitamin D3",
    "magnesium":   "Magnesium",
    "berberine":   "Berberine",
    "metformin":   "Metformin",
    "rapamycin":   "Rapamycin",
    "nmn":         "NMN",
}

CATEGORY_RU: dict[str, str] = {
    "supplement":  "Добавка",
    "drug":        "Лекарственный препарат",
    "nutrient":    "Нутриент",
    "experimental": "Экспериментальное",
    "lifestyle":   "Образ жизни",
}

EVIDENCE_RU: dict[str, str] = {
    "high":         "Высокий",
    "moderate":     "Умеренный",
    "low":          "Низкий",
    "experimental": "Экспериментальный",
}

# Biomarker category folder mapping (mirrors generate_biomarker_pages.py)
CATEGORY_FOLDER: dict[str, str] = {
    "lipids":       "01 - Lipids",
    "glucose":      "02 - Glucose",
    "inflammation": "03 - Inflammation",
    "liver":        "04 - Liver",
    "kidney":       "05 - Kidney",
    "blood_count":  "06 - Blood Count",
    "vitamins":     "08 - Vitamins",
    "telemetry":    "13 - Telemetry",
}

# Biomarker code -> file name mapping (mirrors generate_biomarker_pages.py FILE_NAMES)
BIOMARKER_FILE_NAMES: dict[str, str] = {
    "ldlC":                       "LDL Cholesterol",
    "hdlC":                       "HDL Cholesterol",
    "triglycerides":              "Triglycerides",
    "apoB":                       "Apolipoprotein B",
    "fastingGlucose":             "Fasting Glucose",
    "fastingInsulin":             "Fasting Insulin",
    "homaIr":                     "HOMA-IR",
    "hba1c":                      "HbA1c",
    "hsCrp":                      "hs-CRP",
    "il6":                        "Interleukin-6",
    "alt":                        "ALT",
    "ast":                        "AST",
    "ggt":                        "GGT",
    "albumin":                    "Albumin",
    "creatinine":                 "Serum Creatinine",
    "egfr":                       "eGFR",
    "urineAlbuminCreatinineRatio": "UACR",
    "sodium":                     "Sodium",
    "potassium":                  "Potassium",
    "hemoglobin":                 "Hemoglobin",
    "vitaminD25Oh":               "25(OH)D",
    "systolicBloodPressure":      "Systolic Blood Pressure",
    "restingHeartRate":           "Resting Heart Rate",
    "hrvRmssd":                   "HRV RMSSD",
}

# ---------------------------------------------------------------------------
# Authored content: Russian descriptions for all 7 substances (D-13)
# ---------------------------------------------------------------------------

DESCRIPTIONS: dict[str, str] = {
    "omega3": (
        "Омега-3 полиненасыщенные жирные кислоты (EPA и DHA) — незаменимые липиды морского "
        "происхождения. Снижают уровень триглицеридов, оказывают противовоспалительное действие "
        "через ингибирование арахидонового каскада и активацию PPAR-γ. Улучшают вариабельность "
        "сердечного ритма."
    ),
    "vitamin_d3": (
        "Витамин D3 (холекальциферол) — жирорастворимый витамин, синтезируемый в коже под "
        "действием UVB. Активная форма 1,25(OH)₂D связывается с VDR-рецепторами в более чем "
        "200 типах клеток. Регулирует иммунный ответ, абсорбцию кальция и экспрессию генов."
    ),
    "magnesium": (
        "Магний — второй по распространённости внутриклеточный катион, кофактор более 300 "
        "ферментативных реакций. Регулирует сосудистый тонус, нейромышечную передачу, синтез АТФ "
        "и чувствительность к инсулину. Дефицит встречается у 40-60% взрослых."
    ),
    "berberine": (
        "Берберин — изохинолиновый алкалоид из растений рода Berberis. Активирует AMPK-путь "
        "аналогично метформину, снижает глюкозу и липиды. Угнетает комплекс I митохондриальной "
        "дыхательной цепи. Биодоступность низкая, но клинический эффект сопоставим с некоторыми "
        "препаратами."
    ),
    "metformin": (
        "Метформин — бигуанид первой линии при диабете 2 типа. Активирует AMPK, снижает "
        "глюконеогенез в печени, повышает чувствительность тканей к инсулину. Изучается как "
        "геропротектор (испытание TAME). Рецептурный препарат."
    ),
    "rapamycin": (
        "Рапамицин (сиролимус) — макролидный антибиотик, ингибитор mTORC1. Продлевает жизнь у "
        "мышей во всех исследованиях. Снижает воспаление, активирует аутофагию, замедляет "
        "клеточное старение. Рецептурный иммуносупрессант; в симуляторе — в режиме низких доз "
        "(геропротекция)."
    ),
    "nmn": (
        "НМН (никотинамид мононуклеотид) — предшественник NAD⁺, сигнальной молекулы, участвующей "
        "в репарации ДНК, митохондриальном биогенезе и активации сиртуинов. Уровни NAD⁺ снижаются "
        "с возрастом на 50%. Клинические данные по НМН у людей пока ограничены."
    ),
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_json(path: Path) -> object:
    """Load a JSON file with UTF-8 encoding. Exit with code 2 if missing."""
    if not path.exists():
        print(
            f"[generate] ERROR: {path.name} not found — {path}",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(
            f"[generate] ERROR: Failed to parse {path.name}: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)


def build_biomarker_lookups(biomarkers_data: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Build (code -> name_ru, code -> category) from biomarkers.json in one pass."""
    names: dict[str, str] = {}
    categories: dict[str, str] = {}
    for bm in biomarkers_data.get("biomarkers", []):
        code = bm["code"]
        names[code] = bm["name_ru"]
        categories[code] = bm["category"]
    return names, categories


def biomarker_wikilink(code: str, biomarker_names: dict, biomarker_categories: dict) -> str:
    """Return Obsidian wikilink for a biomarker code."""
    name_ru = biomarker_names.get(code, code)
    category = biomarker_categories.get(code, "")
    folder = CATEGORY_FOLDER.get(category, "")
    file_name = BIOMARKER_FILE_NAMES.get(code, code)
    if folder:
        path = f"02 - Biomarkers/{folder}/{file_name}"
    else:
        path = f"02 - Biomarkers/{file_name}"
    # Escape | in alias per Obsidian table convention
    safe_name = name_ru.replace("|", r"\|")
    return f"[[{path}\\|{safe_name}]]"


# ---------------------------------------------------------------------------
# Page renderer
# ---------------------------------------------------------------------------


def render_substance_page(
    s: dict,
    interactions: list,
    biomarker_names: dict,
    biomarker_categories: dict,
) -> str:
    """Render a full substance wiki page per D-13."""
    sid = s["id"]
    name = s["name"]
    name_ru = s["name_ru"]
    category = s["category"]
    evidence = s["evidenceLevel"]
    is_drug = (category == "drug")
    half_life = s["halfLifeHours"]
    bioavail = s["bioavailability"]
    absorption = s["absorptionRate"]
    elimination = s["eliminationRate"]
    min_dose = s["minDose"]
    max_dose = s["maxDose"]
    default_dose = s["defaultDose"]
    dose_unit = s["doseUnit"]
    effect_profile = s.get("effectProfile", {})

    category_ru = CATEGORY_RU.get(category, category)
    evidence_ru = EVIDENCE_RU.get(evidence, evidence)
    description = DESCRIPTIONS.get(sid, f"*(Описание для `{sid}` не добавлено)*")
    file_name = SUBSTANCE_FILE_NAMES.get(sid, name)

    is_drug_yaml = "true" if is_drug else "false"
    tags_yaml = f"substance, {category}, {sid}"

    lines: list[str] = []

    # --- Frontmatter ---
    lines += [
        "---",
        f"id: {sid}",
        f"name: {name}",
        f"name_ru: {name_ru}",
        f"category: {category}",
        f"evidence_level: {evidence}",
        f"is_drug: {is_drug_yaml}",
        f"half_life_hours: {half_life}",
        f"bioavailability: {bioavail}",
        f"tags: [{tags_yaml}]",
        "---",
        "",
        f"# {name_ru} (`{sid}`)",
        "",
    ]

    # Drug warning block (only for drugs)
    if is_drug:
        lines += [
            "> ⚠️ **ЛЕКАРСТВЕННЫЙ ПРЕПАРАТ** — рецептурный. В симуляторе используется только как исследовательская модель.",
            "",
        ]

    # Info blockquote
    lines += [
        f"> **Категория:** {category_ru} | **Доказательность:** {evidence_ru} | **T½:** {half_life} ч",
        "",
        "---",
        "",
    ]

    # --- Section: Описание ---
    lines += [
        "## Описание",
        "",
        description,
        "",
        "---",
        "",
    ]

    # --- Section: Фармакокинетика ---
    lines += [
        "## Фармакокинетика",
        "",
        "| Параметр | Значение |",
        "|---------|---------|",
        f"| Биодоступность | {bioavail * 100:.0f}% |",
        f"| Период полувыведения | {half_life} ч |",
        f"| Скорость абсорбции | {absorption} /тик |",
        f"| Скорость элиминации | {elimination:.5f} /тик |",
        f"| Диапазон доз | {min_dose}–{max_dose} {dose_unit} |",
        f"| Доза по умолчанию | {default_dose} {dose_unit} |",
        "",
        "---",
        "",
    ]

    # --- Section: Эффекты на биомаркеры ---
    lines += [
        "## Эффекты на биомаркеры",
        "",
        "| Биомаркер | Направление | Дельта/тик (100% конц.) | Ссылка |",
        "|-----------|------------|------------------------|--------|",
    ]
    for code, delta in effect_profile.items():
        direction = "↑" if delta > 0 else "↓"
        delta_fmt = f"{delta:+.5f}"
        wikilink = biomarker_wikilink(code, biomarker_names, biomarker_categories)
        lines.append(f"| {wikilink} | {direction} | {delta_fmt} | — |")

    lines += [
        "",
        "> *Дельты — абсолютные изменения на 1 тик при 100% терапевтической концентрации. "
        "Движок Phase 5 масштабирует: applied_delta = delta × C(t)/Tmax*",
        "",
        "---",
        "",
    ]

    # --- Section: Взаимодействия ---
    # Filter interactions where this substance is involved
    relevant = [
        ix for ix in interactions
        if ix.get("substanceA") == sid or ix.get("substanceB") == sid
    ]
    # Exclude self-self toxicity from the list display (but keep for index)
    partner_list = []
    for ix in relevant:
        a = ix.get("substanceA", "")
        b = ix.get("substanceB", "")
        partner = b if a == sid else a
        if partner == sid:
            # self-self (toxicity at overdose)
            partner_display = f"{sid} (передозировка)"
        else:
            partner_display = SUBSTANCE_FILE_NAMES.get(partner, partner)
        ix_type = ix.get("type", "")
        coefficient = ix.get("coefficient", 1.0)
        desc = ix.get("description", "")
        partner_list.append((ix_type, partner_display, coefficient, desc))

    lines += [
        "## Взаимодействия",
        "",
        f"Полная матрица: [[04 - Interactions/Interactions Index]]",
        "",
    ]
    if partner_list:
        for ix_type, partner, coefficient, desc in partner_list:
            lines.append(f"- **{ix_type}**: с `{partner}` (коэффициент {coefficient}): {desc}")
    else:
        lines.append("*(взаимодействий с другими MVP-веществами нет)*")

    lines += [
        "",
        "---",
        "",
    ]

    # --- Section: Связанные страницы ---
    lines += [
        "## Связанные страницы",
        "",
    ]
    for code in effect_profile:
        link = biomarker_wikilink(code, biomarker_names, biomarker_categories)
        lines.append(f"- {link}")

    lines += [
        "",
        "---",
        "",
        "## Источники",
        "",
        f"*Связь с mortality KB: [[mortality:{name}]]*",
        "",
        "---",
        "",
        "## Исправления",
        "",
        "*(append-only)*",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactions Index renderer (D-15)
# ---------------------------------------------------------------------------


def render_interactions_index(interactions: list, substance_names: dict) -> str:
    """Render 04 - Interactions/Interactions Index.md per D-15."""
    today = datetime.date.today().isoformat()

    lines: list[str] = [
        "---",
        "tags: [interactions, index]",
        f"created: {today}",
        "---",
        "",
        "# Индекс взаимодействий веществ",
        "",
        "> Сводная матрица всех взаимодействий между 7 MVP-веществами. "
        "Источник: `src/data/interactions.json`.",
        "",
        "---",
        "",
        "| Вещество A | Вещество B | Тип | Коэффициент | Описание |",
        "|-----------|-----------|-----|------------|---------|",
    ]

    for ix in interactions:
        a = ix.get("substanceA", "")
        b = ix.get("substanceB", "")
        ix_type = ix.get("type", "")
        coefficient = ix.get("coefficient", 1.0)
        desc = ix.get("description", "").replace("|", r"\|")

        file_a = SUBSTANCE_FILE_NAMES.get(a, a)
        file_b = SUBSTANCE_FILE_NAMES.get(b, b)
        label_a = substance_names.get(a, file_a)
        label_b = substance_names.get(b, file_b)

        link_a = f"[[03 - Substances/{file_a}\\|{label_a}]]"
        # Self-self (overdose toxicity): no link for B
        if a == b:
            link_b = f"`{file_b}` (передозировка)"
        else:
            link_b = f"[[03 - Substances/{file_b}\\|{label_b}]]"

        lines.append(f"| {link_a} | {link_b} | {ix_type} | {coefficient} | {desc} |")

    lines += [
        "",
        "---",
        "",
        f"*Всего: {len(interactions)} взаимодействий | Источник: interactions.json | Обновлено: {today}*",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Biomarker page section updater (fills Phase 2 D-09 placeholder)
# ---------------------------------------------------------------------------


def update_biomarker_sections(
    substances: list,
    biomarker_names: dict,
    biomarker_categories: dict,
) -> int:
    """
    For each biomarker appearing in any substance effectProfile:
    - Find the biomarker page in 02 - Biomarkers/
    - If ## Влияние веществ section exists, replace ONLY that section content
    - If it does NOT exist, append the section

    Returns count of biomarker pages updated.
    """
    # Build map: biomarker_code -> list of (substance_id, name_ru, delta)
    bm_to_substances: dict[str, list[tuple]] = {}
    for s in substances:
        sid = s["id"]
        name_ru = s["name_ru"]
        for code, delta in s.get("effectProfile", {}).items():
            if code not in bm_to_substances:
                bm_to_substances[code] = []
            bm_to_substances[code].append((sid, name_ru, delta))

    updated = 0

    for code, subs_list in bm_to_substances.items():
        category = biomarker_categories.get(code, "")
        folder = CATEGORY_FOLDER.get(category, "")
        file_name = BIOMARKER_FILE_NAMES.get(code, code)

        if folder:
            bm_path = VAULT_ROOT / "02 - Biomarkers" / folder / f"{file_name}.md"
        else:
            bm_path = VAULT_ROOT / "02 - Biomarkers" / f"{file_name}.md"

        if not bm_path.exists():
            print(
                f"[generate] WARNING: Biomarker page not found: {bm_path} — skipping",
                file=sys.stderr,
            )
            continue

        try:
            content = bm_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot read {bm_path}: {exc}",
                file=sys.stderr,
            )
            continue

        # Build the new section content
        section_lines: list[str] = [
            "## Влияние веществ",
            "",
            "| Вещество | Эффект | Дельта/тик |",
            "|---------|--------|-----------|",
        ]
        for sid, sub_name_ru, delta in subs_list:
            direction = "↑" if delta > 0 else "↓"
            delta_fmt = f"{delta:+.5f}"
            file_s = SUBSTANCE_FILE_NAMES.get(sid, sid)
            safe_sub = sub_name_ru.replace("|", r"\|")
            link_s = f"[[03 - Substances/{file_s}\\|{safe_sub}]]"
            section_lines.append(f"| {link_s} | {direction} | {delta_fmt} |")

        section_lines += [
            "",
            "> *Дельты при 100% концентрации за 1 тик. Источник: substances.json (Phase 4)*",
            "",
        ]

        new_section = "\n".join(section_lines)

        # Replace or append the section (T-04-06 threat mitigation)
        # Pattern: ## Влияние веществ ... until next ## heading or end of file
        section_pattern = re.compile(
            r"(## Влияние веществ\n).*?(?=\n## |\Z)",
            re.DOTALL,
        )

        if section_pattern.search(content):
            # Replace only the section content
            new_content = section_pattern.sub(new_section + "\n", content)
        else:
            # Append the section at the end (after last content)
            if not content.endswith("\n"):
                content += "\n"
            # Replace the placeholder block if present
            placeholder_pattern = re.compile(
                r"> \[!info\] Phase 4 placeholder\n> \*\(Phase 4.*?\)\*\n\n"
                r"\| Вещество \|.*?\n(?:\|.*?\n)*\n---\n\n",
                re.DOTALL,
            )
            if placeholder_pattern.search(content):
                new_content = placeholder_pattern.sub(new_section + "\n\n---\n\n", content)
            else:
                new_content = content + "\n" + new_section

        try:
            bm_path.write_text(new_content, encoding="utf-8")
            updated += 1
            print(f"[generate] ✓ Updated biomarker page: {file_name}.md")
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot write {bm_path}: {exc}",
                file=sys.stderr,
            )

    return updated


# ---------------------------------------------------------------------------
# HOME.md point-edit updater (T-04-07 threat mitigation)
# ---------------------------------------------------------------------------


def update_home_md() -> None:
    """
    Apply targeted point-edits to HOME.md to add substances and interactions entries.
    NEVER rewrites HOME.md wholesale — only targeted string replacements (T-04-07).
    """
    if not HOME_FILE.exists():
        print("[generate] WARNING: HOME.md not found — skipping update", file=sys.stderr)
        return

    content = HOME_FILE.read_text(encoding="utf-8")
    modified = False

    # Add substances count to existing navigation table row (idempotent)
    # The row already exists from the initial HOME.md setup; update the count
    old_substances_row = "| [[03 - Substances/\\|03 · Вещества]] | Вещества и интервенции | — |"
    new_substances_row = "| [[03 - Substances/\\|03 · Вещества]] | Вещества и интервенции | 7 |"
    if old_substances_row in content:
        content = content.replace(old_substances_row, new_substances_row)
        modified = True
        print("[generate] ✓ HOME.md: updated substances count to 7")

    # Add interactions count to existing navigation table row (idempotent)
    old_interactions_row = "| [[04 - Interactions/\\|04 · Взаимодействия]] | Матрица взаимодействий | — |"
    new_interactions_row = "| [[04 - Interactions/\\|04 · Взаимодействия]] | Матрица взаимодействий | 1 |"
    if old_interactions_row in content:
        content = content.replace(old_interactions_row, new_interactions_row)
        modified = True
        print("[generate] ✓ HOME.md: updated interactions count to 1")

    # Add index entries after Biomarkers Index row (idempotent per-entry check)
    biomarkers_index_row = "| [[08 - Index/Biomarkers Index\\|08 · Индексы → Биомаркеры]] | Индекс биомаркеров по категориям | 1 |"
    interactions_index_entry = "| [[04 - Interactions/Interactions Index\\|04 · Взаимодействия → Индекс]] | Матрица взаимодействий | 1 |"
    substances_index_entry = "| [[03 - Substances/Omega-3\\|03 · Вещества → Омега-3]] | Вещества MVP (7) | 7 |"
    if biomarkers_index_row in content:
        additions = []
        if interactions_index_entry not in content:
            additions.append(interactions_index_entry)
        if substances_index_entry not in content:
            additions.append(substances_index_entry)
        if additions:
            content = content.replace(
                biomarkers_index_row,
                "\n".join([biomarkers_index_row] + additions),
            )
            modified = True
            print(f"[generate] ✓ HOME.md: added {len(additions)} index entries")

    # Update footer timestamp
    today_str = datetime.date.today().isoformat()
    new_content_with_date = re.sub(
        r"\*Последнее обновление: \d{4}-\d{2}-\d{2}\*",
        f"*Последнее обновление: {today_str}*",
        content,
    )
    if new_content_with_date != content:
        content = new_content_with_date
        modified = True

    if modified:
        HOME_FILE.write_text(content, encoding="utf-8")
        print("[generate] ✓ HOME.md updated")
    else:
        print("[generate] ✓ HOME.md already up to date")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="im-human substance page generator",
        epilog=(
            "Reads substances.json + interactions.json + biomarkers.json, "
            "writes 7 Obsidian wiki pages + Interactions Index + biomarker section updates."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing any files",
    )
    args = parser.parse_args()

    print("[generate] Starting substance page generation")

    # Load data
    substances = load_json(SUBSTANCES_FILE)
    print(f"[generate] Reading substances.json ({len(substances)} substances)")

    interactions = load_json(INTERACTIONS_FILE)
    print(f"[generate] Reading interactions.json ({len(interactions)} interactions)")

    biomarkers_data = load_json(BIOMARKERS_FILE)
    biomarker_names, biomarker_categories = build_biomarker_lookups(biomarkers_data)
    print(f"[generate] Reading biomarkers.json ({len(biomarker_names)} biomarkers)")

    # Build substance_names for Interactions Index
    substance_names: dict[str, str] = {s["id"]: s["name_ru"] for s in substances}

    if args.dry_run:
        print("[generate] [dry-run] Would create:")
        for s in substances:
            sid = s["id"]
            file_name = SUBSTANCE_FILE_NAMES.get(sid, s["name"])
            print(f"[generate] [dry-run]   03 - Substances/{file_name}.md")
        print("[generate] [dry-run]   04 - Interactions/Interactions Index.md")
        print("[generate] [dry-run]   Update biomarker pages: ## Влияние веществ sections")
        print("[generate] [dry-run]   Update HOME.md (point-edit)")
        return

    # Create directories
    SUBSTANCES_DIR.mkdir(parents=True, exist_ok=True)
    INTERACTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate substance pages (skip-if-exists per D-03)
    created = 0
    skipped = 0
    failed = 0

    for s in substances:
        sid = s["id"]
        file_name = SUBSTANCE_FILE_NAMES.get(sid, s["name"])
        target = SUBSTANCES_DIR / f"{file_name}.md"

        # Skip-if-exists guard (Obsidian is source of truth D-03)
        if target.exists():
            print(f"[generate] ✓ already exists: {file_name}.md")
            skipped += 1
            continue

        try:
            content = render_substance_page(s, interactions, biomarker_names, biomarker_categories)
            target.write_text(content, encoding="utf-8")
            rel = target.relative_to(VAULT_ROOT)
            print(f"[generate] ✓ Created: {rel}")
            created += 1
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot write {target}: {exc}",
                file=sys.stderr,
            )
            failed += 1

    # Render Interactions Index (always overwrite — aggregates all substances)
    index_path = INTERACTIONS_DIR / "Interactions Index.md"
    try:
        index_content = render_interactions_index(interactions, substance_names)
        index_path.write_text(index_content, encoding="utf-8")
        print(f"[generate] ✓ Written: 04 - Interactions/Interactions Index.md")
    except OSError as exc:
        print(
            f"[generate] ERROR: Cannot write {index_path}: {exc}",
            file=sys.stderr,
        )
        failed += 1

    # Update biomarker pages with ## Влияние веществ sections
    updated_bm = update_biomarker_sections(substances, biomarker_names, biomarker_categories)

    # Update HOME.md with point-edits
    update_home_md()

    # Summary
    print(
        f"\n[generate] Done. Substance pages: {created} created, {skipped} skipped. "
        f"Interactions Index: written. "
        f"Biomarker sections: {updated_bm} updated."
    )

    if failed > 0:
        print(f"[generate] WARNING: {failed} items failed — see errors above", file=sys.stderr)

    print("[generate] DUAL-LAYER: Markdown создан. Запустите Plan 05 для ingest Neo4j.")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
