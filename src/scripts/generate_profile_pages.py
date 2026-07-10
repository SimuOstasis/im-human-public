#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Generate Obsidian wiki pages for 3 preset human profiles.

Reads src/data/presets.json, imports HumanProfile from domain for BMI/BMR
computation (single source of truth — no inline formula duplication),
writes 3 .md files into "01 - Human Profiles/".
Skip-if-exists: Obsidian is source of truth (DUAL-LAYER rule).

Usage (PowerShell from vault root):
    $env:PYTHONIOENCODING="utf-8"
    venv\\Scripts\\python.exe src/scripts/generate_profile_pages.py
    venv\\Scripts\\python.exe src/scripts/generate_profile_pages.py --dry-run
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# CRITICAL: scripts/ is 3 levels below vault root (scripts->src->vault)
# Pitfall 3 from RESEARCH.md: use .parent.parent.parent for src/scripts/
VAULT_ROOT   = Path(__file__).parent.parent.parent
DATA_FILE    = VAULT_ROOT / "src" / "data" / "presets.json"
PROFILES_DIR = VAULT_ROOT / "01 - Human Profiles"
TEMPLATE     = VAULT_ROOT / "09 - Templates" / "Human Profile Template.md"

# ---------------------------------------------------------------------------
# Profile ID → wiki filename mapping (Latin Title Case per CLAUDE.md)
# ---------------------------------------------------------------------------

FILE_NAMES: dict[str, str] = {
    "young_healthy_30m": "Young Healthy 30M",
    "middle_age_50f":    "Middle Age 50F",
    "elderly_70m":       "Elderly 70M",
}

# Activity multipliers (mirrors PhysicalActivity enum in domain)
_ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,
    "low":       1.375,
    "moderate":  1.55,
    "high":      1.725,
    "athlete":   1.9,
}

# Russian display names for organ systems
_ORGAN_NAMES_RU: dict[str, str] = {
    "cardiovascular":  "Сердечно-сосудистая",
    "liver":           "Печень",
    "kidney":          "Почки",
    "nervous":         "Нервная",
    "immune":          "Иммунная",
    "metabolic":       "Метаболическая",
    "cellular_repair": "Клеточное восстановление",
}

# Russian display names for predispositions
_PRED_NAMES_RU: dict[str, str] = {
    "cardiovascular_risk":      "ССЗ",
    "diabetes_risk":            "Диабет 2 типа",
    "neurodegeneration_risk":   "Нейродегенерация",
    "liver_disease_risk":       "Заболевания печени",
    "kidney_disease_risk":      "Заболевания почек",
}

# Russian display names for physiology fields
_PHYS_NAMES_RU: dict[str, str] = {
    "body_fat_pct":          "Жировая масса",
    "metabolic_rate_coef":   "Скорость метаболизма",
    "methylation":           "Метилирование",
    "autophagy_efficiency":  "Эффективность аутофагии",
}

# Russian display names for lifestyle fields
_LIFESTYLE_NAMES_RU: dict[str, str] = {
    "stress":              "Стресс",
    "sleep_quality":       "Качество сна",
    "physical_activity":   "Физическая активность",
    "diet_quality":        "Качество питания",
    "alcohol":             "Алкоголь",
    "smoking":             "Курение",
}

# Sex display (internal value → Russian label)
_SEX_RU: dict[str, str] = {
    "male":        "мужской",
    "female":      "женский",
    "unspecified": "не указан",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    """Load a JSON file with UTF-8 encoding. Exit with code 2 if missing."""
    if not path.exists():
        fname = path.name
        print(
            f"[generate] ERROR: {fname} not found — {path}",
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


def verify_template() -> None:
    """Verify that Human Profile Template.md exists (PROF-06 — do NOT recreate)."""
    if not TEMPLATE.exists():
        print(
            f"[generate] ERROR: Human Profile Template.md not found — {TEMPLATE}\n"
            f"[generate] PROF-06 prerequisite missing. Template must exist before running this script.",
            file=sys.stderr,
        )
        sys.exit(3)
    print(f"[generate] OK — Human Profile Template exists: {TEMPLATE.relative_to(VAULT_ROOT)}")


def compute_bmi(weight_kg: float, height_cm: float) -> float:
    """BMI = weight_kg / height_m^2 (rounded to 2 dp)."""
    h_m = height_cm / 100.0
    return round(weight_kg / (h_m ** 2), 2)


def compute_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Mifflin-St Jeor BMR (kcal/day). Fallback when domain import unavailable (D-06).
    Male:   10*w + 6.25*h - 5*age + 5
    Female: 10*w + 6.25*h - 5*age - 161
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if sex == "male":
        return round(base + 5, 1)
    else:
        return round(base - 161, 1)


def compute_tdee(bmr: float, physical_activity: str) -> float:
    """TDEE = BMR × activity multiplier."""
    multiplier = _ACTIVITY_MULTIPLIERS.get(physical_activity, 1.2)
    return round(bmr * multiplier, 1)


# ---------------------------------------------------------------------------
# Page renderer — uses template section structure (PROF-06, Human Profile Template)
# ---------------------------------------------------------------------------


def render_page(preset: dict) -> str:
    """Render a full profile wiki page using Human Profile Template.md section structure.

    Imports HumanProfile.from_preset to source BMI/BMR — single source of truth (D-06).
    """
    profile_id   = preset["profile_id"]
    display_name = preset["display_name"]

    demo  = preset["demographics"]
    phys  = preset["physiology"]
    life  = preset["lifestyle"]
    preds = preset["predispositions"]
    orgs  = preset["organ_systems"]

    # --- Source BMI/BMR from domain model (single source of truth, no duplication) ---
    try:
        from src.domain.human_profile import HumanProfile
    except ImportError as exc:
        print(f"[generate] WARNING: Cannot import HumanProfile ({exc}); using inline fallback", file=sys.stderr)
        HumanProfile = None  # type: ignore

    if HumanProfile is not None:
        profile = HumanProfile.from_preset(profile_id)   # let Pydantic/KeyError errors propagate
        bmi = profile.bmi
        bmr = profile.bmr
        tdee = profile.tdee
    else:
        # Fallback: compute inline using identical D-06 formula
        bmi  = compute_bmi(demo["weight_kg"], demo["height_cm"])
        bmr  = compute_bmr(demo["weight_kg"], demo["height_cm"], demo["age"], demo["sex"])
        tdee = compute_tdee(bmr, life["physical_activity"])

    today = datetime.date.today().isoformat()

    # --- Frontmatter ---
    lines = [
        "---",
        f"profile_id: {profile_id}",
        f"name: {display_name}",
        "preset: true",
        "tags: [profile]",
        f"created: {today}",
        "---",
        "",
        f"# Профиль: {display_name}",
        "",
        "---",
        "",
    ]

    # --- Section: Демография (Demographics) ---
    sex_display = _SEX_RU.get(demo["sex"], demo["sex"])
    lines += [
        "## Демография",
        "",
        "| Параметр | Значение |",
        "|---------|---------|",
        f"| Пол | {sex_display} |",
        f"| Возраст | {demo['age']} лет |",
        f"| Рост | {demo['height_cm']} см |",
        f"| Вес | {demo['weight_kg']} кг |",
        f"| BMI (расчётный) | {bmi} кг/м² |",
        f"| BMR (расчётный) | {bmr} ккал/сут |",
        f"| TDEE (расчётный) | {tdee} ккал/сут |",
        "",
        "---",
        "",
    ]

    # --- Section: Физиология (Physiology) ---
    lines += [
        "## Физиология",
        "",
        "| Параметр | Значение |",
        "|---------|---------|",
        f"| Жировая масса | {phys['body_fat_pct']} % |",
        f"| Скорость метаболизма | {phys['metabolic_rate_coef']} коэф. (0.5–1.5) |",
        f"| Метилирование | {phys['methylation']} |",
        f"| Эффективность аутофагии | {phys['autophagy_efficiency']} |",
        "",
        "---",
        "",
    ]

    # --- Section: Образ жизни (Lifestyle) ---
    lines += [
        "## Образ жизни",
        "",
        "| Параметр | Значение (0–100 или категория) |",
        "|---------|-------------------------------|",
        f"| Стресс | {life['stress']} |",
        f"| Качество сна | {life['sleep_quality']} |",
        f"| Физическая активность | {life['physical_activity']} |",
        f"| Качество питания | {life['diet_quality']} |",
        f"| Алкоголь | {life['alcohol']} |",
        f"| Курение | {life['smoking']} |",
        "",
        "---",
        "",
    ]

    # --- Section: Предрасположенности (Predispositions) ---
    lines += [
        "## Предрасположенности (0–1)",
        "",
        "| Риск | Значение |",
        "|------|---------|",
        f"| ССЗ | {preds['cardiovascular_risk']} |",
        f"| Диабет 2 типа | {preds['diabetes_risk']} |",
        f"| Нейродегенерация | {preds['neurodegeneration_risk']} |",
        f"| Заболевания печени | {preds['liver_disease_risk']} |",
        f"| Заболевания почек | {preds['kidney_disease_risk']} |",
        "",
        "---",
        "",
    ]

    # --- Section: Исходное состояние систем (OrganSystems) ---
    # Template shows values as 0–100 scale; store raw 0.0–1.0 values (float precision preserved)
    lines += [
        "## Исходное состояние систем (0.0–1.0)",
        "",
        "| Система | Значение |",
        "|---------|---------|",
        f"| Сердечно-сосудистая | {orgs['cardiovascular']} |",
        f"| Печень | {orgs['liver']} |",
        f"| Почки | {orgs['kidney']} |",
        f"| Нервная | {orgs['nervous']} |",
        f"| Иммунная | {orgs['immune']} |",
        f"| Метаболическая | {orgs['metabolic']} |",
        f"| Клеточное восстановление | {orgs['cellular_repair']} |",
        "",
        "---",
        "",
    ]

    # --- Section: Исходные индексы (placeholder — computed by engine Phase 5) ---
    lines += [
        "## Исходные индексы",
        "",
        "> [!info] Phase 5 placeholder",
        "> Значения рассчитываются движком динамически (Phase 5). Здесь показаны начальные ориентиры.",
        "",
        "| Индекс | Значение |",
        "|--------|---------|",
        "| Биологический возраст | — лет |",
        "| Воспаление | — |",
        "| Окислительный стресс | — |",
        "| Токсическая нагрузка | — |",
        "| Индекс устойчивости | — |",
        "",
        "---",
        "",
    ]

    # --- Section: Исправления ---
    lines += [
        "## Исправления",
        "",
        "*(append-only)*",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HOME.md point-edit updater
# ---------------------------------------------------------------------------


def update_home(vault_root: Path, created: int, skipped: int) -> None:
    """Add '01 - Human Profiles' entry to HOME.md navigation table (point-edit only).

    Never rewrites HOME.md wholesale — only targeted string.replace() calls.
    Pattern from generate_biomarker_pages.py lines 745-789.
    """
    home = vault_root / "HOME.md"
    if not home.exists():
        print("[generate] WARNING: HOME.md not found — skipping update", file=sys.stderr)
        return

    content = home.read_text(encoding="utf-8")

    # Update count for "01 - Human Profiles" row in nav table (idempotent)
    # The HOME.md already has | [[01 - Human Profiles/\|01 · Профили]] | ... | — |
    # Update the count from "—" to the actual number
    total = created + skipped
    if total > 0:
        # Replace count column for profiles row
        old_row = "| [[01 - Human Profiles/\\|01 · Профили]] | Пресетные и пользовательские профили | — |"
        new_row = f"| [[01 - Human Profiles/\\|01 · Профили]] | Пресетные и пользовательские профили | {total} |"
        if old_row in content:
            content = content.replace(old_row, new_row)
            print(f"[generate] OK — HOME.md: updated profiles count to {total}")
        elif f"| {total} |" in content and "01 · Профили" in content:
            print(f"[generate] OK — HOME.md: profiles count already up to date ({total})")
        else:
            # Try to find and update any existing count
            updated = re.sub(
                r"(\[\[01 - Human Profiles/\\?\|01 · Профили\]\] \| [^|]+ \| )[^|]+(\|)",
                rf"\g<1>{total} \g<2>",
                content,
            )
            if updated != content:
                content = updated
                print(f"[generate] OK — HOME.md: updated profiles count (regex) to {total}")
            else:
                print("[generate] INFO: HOME.md profiles row not matched — skipping count update")

    # Update footer timestamp
    today_str = datetime.date.today().isoformat()
    content = re.sub(
        r"\*Последнее обновление: \d{4}-\d{2}-\d{2}\*",
        f"*Последнее обновление: {today_str}*",
        content,
    )

    try:
        home.write_text(content, encoding="utf-8")
        print("[generate] OK — HOME.md updated")
    except OSError as exc:
        print(f"[generate] WARNING: Could not write HOME.md: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="im-human profile page generator",
        epilog=(
            "Reads presets.json, writes 3 Obsidian profile pages to '01 - Human Profiles/'.\n"
            "Imports HumanProfile.from_preset() for BMI/BMR (single source of truth, D-06)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing any files",
    )
    args = parser.parse_args()

    print("[generate] Starting profile page generation")

    # Verify Human Profile Template.md exists (PROF-06 prerequisite)
    verify_template()

    data = load_json(DATA_FILE)
    presets = data.get("presets", [])
    print(f"[generate] Reading presets.json ({len(presets)} presets)")

    created = 0
    skipped = 0
    failed  = 0

    for preset in presets:
        profile_id   = preset["profile_id"]
        display_name = preset["display_name"]
        file_base    = FILE_NAMES.get(profile_id, display_name)

        target_path = PROFILES_DIR / f"{file_base}.md"

        if args.dry_run:
            rel = f"01 - Human Profiles/{file_base}.md"
            print(f"[generate] [dry-run] would create: {rel}")
            continue

        # Skip-if-exists (Obsidian is source of truth — DUAL-LAYER)
        if target_path.exists():
            print(f"[generate] OK — already exists: {file_base}.md")
            skipped += 1
            continue

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = render_page(preset)
            target_path.write_text(content, encoding="utf-8")
            rel = str(target_path).replace(str(VAULT_ROOT), "").lstrip("/\\")
            print(f"[generate] OK — Created: {rel}")
            created += 1
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot write {target_path}: {exc}",
                file=sys.stderr,
            )
            failed += 1

    if args.dry_run:
        print(f"[generate] [dry-run] Would create: {len(presets)} pages")
        return

    print(f"[generate] Done. Created: {created}, Skipped: {skipped}, Total: {len(presets)}")

    # Update HOME.md (point-edit, never wholesale rewrite)
    update_home(VAULT_ROOT, created, skipped)

    if failed > 0:
        print(f"[generate] WARNING: {failed} pages failed — see errors above", file=sys.stderr)
        sys.exit(1)

    print("[generate] Next: run ingest_profiles.py (DUAL-LAYER)")


if __name__ == "__main__":
    main()
