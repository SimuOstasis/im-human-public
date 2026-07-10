#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Batch ERS update: compute evidence from mortality KB, write to .md, re-ingest.

Для каждого из 7 веществ и 23 биомаркеров (из SUBSTANCE_SLUG_MAP / BIOMARKER_SLUG_MAP):
    1. Запрашивает факты из Mortality KB через KBClient
    2. Вычисляет уровень ERS (1–5) по avg_si
    3. Обновляет YAML frontmatter + callout [!info] ERS в .md файле (update_wiki_ers)
    4. DUAL-LAYER: после обновления .md запускает ingest_wiki.py --changed-only

Usage (PowerShell, vault root):
    $env:PYTHONIOENCODING="utf-8"
    .\\.neo4j\\venv\\Scripts\\python.exe .neo4j\\update_ers_pages.py --dry-run
    .\\.neo4j\\venv\\Scripts\\python.exe .neo4j\\update_ers_pages.py
    .\\.neo4j\\venv\\Scripts\\python.exe .neo4j\\update_ers_pages.py --substances-only
    .\\.neo4j\\venv\\Scripts\\python.exe .neo4j\\update_ers_pages.py --biomarkers-only

Note (PYTHONIOENCODING):
    При запуске в PowerShell/cmd с кодировкой cp1251 символы звёзд (★☆) и кириллица
    в stdout могут выводиться с ошибкой. Установите $env:PYTHONIOENCODING="utf-8"
    перед запуском. Файлы .md пишутся с encoding="utf-8" в update_wiki_ers — независимо
    от настроек терминала.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Добавить корень проекта в sys.path для импорта src.engine.kb_client
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Добавить .neo4j/ для импорта _utils
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Импорты из проекта
# ---------------------------------------------------------------------------

from src.engine.kb_client import KBClient, _ERS_LABELS, update_wiki_ers  # noqa: E402

from _utils import load_dotenv  # noqa: E402

load_dotenv()

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

VAULT_ROOT = _PROJECT_ROOT

# ---------------------------------------------------------------------------
# Маппинг: substance_id → путь к .md файлу
# Имена файлов из generate_substance_pages.py (SUBSTANCE_FILE_NAMES)
# ---------------------------------------------------------------------------

SUBSTANCE_MD_MAP: dict[str, Path] = {
    "omega3":      VAULT_ROOT / "03 - Substances" / "Omega-3.md",
    "metformin":   VAULT_ROOT / "03 - Substances" / "Metformin.md",
    "rapamycin":   VAULT_ROOT / "03 - Substances" / "Rapamycin.md",
    "vitamin_d3":  VAULT_ROOT / "03 - Substances" / "Vitamin D3.md",
    "ashwagandha": VAULT_ROOT / "03 - Substances" / "Ashwagandha.md",
    "magnesium":   VAULT_ROOT / "03 - Substances" / "Magnesium.md",
    "nmn":         VAULT_ROOT / "03 - Substances" / "NMN.md",
}

# ---------------------------------------------------------------------------
# Маппинг: biomarker_code → путь к .md файлу
# Имена файлов из generate_biomarker_pages.py (FILE_NAMES) + CATEGORY_FOLDER
# ---------------------------------------------------------------------------

_BIO_DIR = VAULT_ROOT / "02 - Biomarkers"

BIOMARKER_MD_MAP: dict[str, Path] = {
    # 01 - Lipids
    "ldlC":                        _BIO_DIR / "01 - Lipids" / "LDL Cholesterol.md",
    "hdlC":                        _BIO_DIR / "01 - Lipids" / "HDL Cholesterol.md",
    "triglycerides":               _BIO_DIR / "01 - Lipids" / "Triglycerides.md",
    "apoB":                        _BIO_DIR / "01 - Lipids" / "Apolipoprotein B.md",
    # 02 - Glucose
    "fastingGlucose":              _BIO_DIR / "02 - Glucose" / "Fasting Glucose.md",
    "fastingInsulin":              _BIO_DIR / "02 - Glucose" / "Fasting Insulin.md",
    "homaIr":                      _BIO_DIR / "02 - Glucose" / "HOMA-IR.md",
    "hba1c":                       _BIO_DIR / "02 - Glucose" / "HbA1c.md",
    # 03 - Inflammation
    "hsCrp":                       _BIO_DIR / "03 - Inflammation" / "hs-CRP.md",
    "il6":                         _BIO_DIR / "03 - Inflammation" / "Interleukin-6.md",
    # 04 - Liver
    "alt":                         _BIO_DIR / "04 - Liver" / "ALT.md",
    "ast":                         _BIO_DIR / "04 - Liver" / "AST.md",
    "ggt":                         _BIO_DIR / "04 - Liver" / "GGT.md",
    "albumin":                     _BIO_DIR / "04 - Liver" / "Albumin.md",
    # 05 - Kidney
    "creatinine":                  _BIO_DIR / "05 - Kidney" / "Serum Creatinine.md",
    "egfr":                        _BIO_DIR / "05 - Kidney" / "eGFR.md",
    "urineAlbuminCreatinineRatio": _BIO_DIR / "05 - Kidney" / "UACR.md",
    "sodium":                      _BIO_DIR / "05 - Kidney" / "Sodium.md",
    "potassium":                   _BIO_DIR / "05 - Kidney" / "Potassium.md",
    # 06 - Blood Count
    "hemoglobin":                  _BIO_DIR / "06 - Blood Count" / "Hemoglobin.md",
    # 08 - Vitamins
    "vitaminD25Oh":                _BIO_DIR / "08 - Vitamins" / "25(OH)D.md",
    # 13 - Telemetry
    "systolicBloodPressure":       _BIO_DIR / "13 - Telemetry" / "Systolic Blood Pressure.md",
    "hrvRmssd":                    _BIO_DIR / "13 - Telemetry" / "HRV RMSSD.md",
}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _avg_si(facts: list[dict]) -> float:
    """Вычислить средний si из списка фактов."""
    si_values = [f.get("si") for f in facts if f.get("si") is not None]
    return sum(si_values) / len(si_values) if si_values else 0.0


def update_all(client: KBClient, dry_run: bool = False,
               do_substances: bool = True, do_biomarkers: bool = True) -> list[Path]:
    """Обновить ERS для всех веществ и/или биомаркеров.

    Args:
        client:         Активный KBClient (Human + Mortality DB).
        dry_run:        Если True — только печатать план без записи .md.
        do_substances:  Обрабатывать вещества (SUBSTANCE_MD_MAP).
        do_biomarkers:  Обрабатывать биомаркеры (BIOMARKER_MD_MAP).

    Returns:
        Список путей .md файлов, которые были обновлены (пуст при dry_run).
    """
    changed: list[Path] = []

    # --- Вещества ---
    if do_substances:
        print(f"\n[INFO] === Вещества ({len(SUBSTANCE_MD_MAP)}) ===")
        for sub_id, md_path in SUBSTANCE_MD_MAP.items():
            facts = client.get_substance_evidence(sub_id)
            if not facts:
                print(f"[WARN] {sub_id}: нет фактов в mortality KB, пропуск ERS")
                continue

            level = client.compute_ers_level(facts)
            avg = _avg_si(facts)
            label = _ERS_LABELS[level]
            count = len(facts)

            if dry_run:
                print(f"  [DRY] {sub_id}: уровень={level}, label={label!r}, "
                      f"фактов={count}, avg_si={avg:.2f}, файл={md_path.name}")
                continue

            if not md_path.exists():
                print(f"[WARN] {sub_id}: файл не найден: {md_path}", file=sys.stderr)
                continue

            try:
                update_wiki_ers(md_path, level, label, count, avg)
                changed.append(md_path)
                print(f"  [OK] {sub_id}: ERS={level}/5 ({label}), si={avg:.2f}, "
                      f"фактов={count} → {md_path.name}")
            except Exception as exc:
                print(f"[WARN] {sub_id}: не удалось обновить {md_path.name}: {exc}",
                      file=sys.stderr)

    # --- Биомаркеры ---
    if do_biomarkers:
        print(f"\n[INFO] === Биомаркеры ({len(BIOMARKER_MD_MAP)}) ===")
        for biomarker_code, md_path in BIOMARKER_MD_MAP.items():
            facts = client.get_biomarker_context(biomarker_code)
            if not facts:
                print(f"[WARN] {biomarker_code}: нет фактов в mortality KB, пропуск ERS")
                continue

            level = client.compute_ers_level(facts)
            avg = _avg_si(facts)
            label = _ERS_LABELS[level]
            count = len(facts)

            if dry_run:
                print(f"  [DRY] {biomarker_code}: уровень={level}, label={label!r}, "
                      f"фактов={count}, avg_si={avg:.2f}, файл={md_path.name}")
                continue

            if not md_path.exists():
                print(f"[WARN] {biomarker_code}: файл не найден: {md_path}", file=sys.stderr)
                continue

            try:
                update_wiki_ers(md_path, level, label, count, avg)
                changed.append(md_path)
                print(f"  [OK] {biomarker_code}: ERS={level}/5 ({label}), si={avg:.2f}, "
                      f"фактов={count} → {md_path.name}")
            except Exception as exc:
                print(f"[WARN] {biomarker_code}: не удалось обновить {md_path.name}: {exc}",
                      file=sys.stderr)

    return changed


def _run_ingest_wiki(changed: list[Path]) -> None:
    """DUAL-LAYER: запустить ingest_wiki.py --changed-only после обновления .md файлов.

    Команда по CLAUDE.md §Жёсткие правила синхронизации (DUAL-WRITE):
        cd W:\\Obsidian\\human\\.neo4j
        .\\venv\\Scripts\\python.exe ingest_wiki.py --changed-only

    Не падает при ненулевом коде ingest — печатает WARN.
    """
    if not changed:
        print("\n[INFO] Нет изменённых файлов — ingest_wiki.py не запускается")
        return

    print(f"\n[INFO] DUAL-LAYER: запуск ingest_wiki.py --changed-only "
          f"({len(changed)} файлов изменено)")

    ingest_wiki_py = _SCRIPT_DIR / "ingest_wiki.py"
    if not ingest_wiki_py.exists():
        print(f"[WARN] ingest_wiki.py не найден: {ingest_wiki_py}", file=sys.stderr)
        return

    result = subprocess.run(
        [sys.executable, str(ingest_wiki_py), "--changed-only"],
        cwd=str(_SCRIPT_DIR),
        capture_output=False,
        check=False,
    )
    if result.returncode != 0:
        print(f"[WARN] ingest_wiki.py завершился с кодом {result.returncode} — "
              f"Human DB может не быть синхронизирована", file=sys.stderr)
    else:
        print("[INFO] DUAL-LAYER: ingest_wiki.py --changed-only завершён успешно")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Batch ERS-обновление: вещества + биомаркеры → .md → ingest_wiki.

    Опции:
        --dry-run           Печатать план ERS без записи .md и без ingest
        --substances-only   Обрабатывать только вещества
        --biomarkers-only   Обрабатывать только биомаркеры
    """
    parser = argparse.ArgumentParser(
        description=(
            "Batch ERS update: вычислить ERS из mortality KB, "
            "обновить .md веществ/биомаркеров, синхронизировать Human DB."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Печатать план ERS без записи .md и без ingest_wiki",
    )
    parser.add_argument(
        "--substances-only",
        action="store_true",
        help="Обрабатывать только вещества (пропустить биомаркеры)",
    )
    parser.add_argument(
        "--biomarkers-only",
        action="store_true",
        help="Обрабатывать только биомаркеры (пропустить вещества)",
    )
    args = parser.parse_args()

    do_substances = not args.biomarkers_only
    do_biomarkers = not args.substances_only

    if args.dry_run:
        print("=== DRY RUN — запись .md и ingest_wiki не выполняются ===")

    # Инициализировать KBClient — T-07-03: не выводить credentials при ошибке
    try:
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ImportError:
        print("[ERROR] neo4j driver не установлен. Запустите: pip install neo4j",
              file=sys.stderr)
        sys.exit(1)

    client: KBClient | None = None
    try:
        client = KBClient()
        changed = update_all(
            client,
            dry_run=args.dry_run,
            do_substances=do_substances,
            do_biomarkers=do_biomarkers,
        )

        # DUAL-LAYER синхронизация (только при реальном запуске)
        if not args.dry_run:
            _run_ingest_wiki(changed)

        total = len(changed)
        if args.dry_run:
            print("\n[INFO] Dry-run завершён — файлы не изменены")
        else:
            print(f"\n[DONE] Обновлено файлов: {total}")

    except ServiceUnavailable:
        # T-07-03: не логировать URI/password
        print(
            "[ERROR] Neo4j недоступен. Убедитесь что сервер запущен.",
            file=sys.stderr,
        )
        sys.exit(1)
    except AuthError:
        # T-07-03: не логировать учётные данные
        print(
            "[ERROR] Ошибка аутентификации Neo4j. "
            "Проверьте NEO4J_USER/NEO4J_PASSWORD в .neo4j/.env.",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
