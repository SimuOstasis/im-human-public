#!/usr/bin/env python3
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
im-human · Generate Obsidian wiki pages for all 24 MVP biomarkers.

Reads src/data/biomarkers.json + src/data/reference_ranges.json,
writes 24 .md files into 02 - Biomarkers/ and Biomarkers Index.md.
Skip-if-exists: Obsidian is source of truth (D-03).

Usage (PowerShell from vault root):
    venv\\Scripts\\python.exe src/scripts/generate_biomarker_pages.py
    venv\\Scripts\\python.exe src/scripts/generate_biomarker_pages.py --dry-run
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# CRITICAL: scripts/ is 3 levels below vault root (scripts->src->vault)
# ingest_wiki.py uses:  Path(__file__).parent.parent  (.neo4j/ -> vault)
# generate script uses: Path(__file__).parent.parent.parent  (scripts->src->vault)
VAULT_ROOT = Path(__file__).parent.parent.parent
DATA_FILE  = VAULT_ROOT / "src" / "data" / "biomarkers.json"
REF_FILE   = VAULT_ROOT / "src" / "data" / "reference_ranges.json"

# ---------------------------------------------------------------------------
# Mapping constants (verbatim from 02-PATTERNS.md)
# ---------------------------------------------------------------------------

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

CATEGORY_NAME_RU: dict[str, str] = {
    "lipids":       "Липиды",
    "glucose":      "Углеводный обмен",
    "inflammation": "Воспаление",
    "liver":        "Функция печени",
    "kidney":       "Функция почек",
    "blood_count":  "Клинический анализ крови",
    "vitamins":     "Витамины и нутриенты",
    "telemetry":    "Физиологическая телеметрия",
}

ORGAN_NAME_RU: dict[str, str] = {
    "cardiovascular":  "Сердечно-сосудистая система",
    "liver":           "Печень",
    "kidney":          "Почки",
    "nervous":         "Нервная система",
    "immune":          "Иммунная система",
    "metabolic":       "Метаболическая система",
    "cellular_repair": "Клеточное восстановление",
    "bone":            "Костная система",
    "muscle":          "Мышечная система",
}

# File naming contract per UI-SPEC (6 special cases)
FILE_NAMES: dict[str, str] = {
    "ldlC":                        "LDL Cholesterol",
    "hdlC":                        "HDL Cholesterol",
    "triglycerides":               "Triglycerides",
    "apoB":                        "Apolipoprotein B",
    "fastingGlucose":              "Fasting Glucose",
    "fastingInsulin":              "Fasting Insulin",
    "homaIr":                      "HOMA-IR",
    "hba1c":                       "HbA1c",
    "hsCrp":                       "hs-CRP",
    "il6":                         "Interleukin-6",
    "alt":                         "ALT",
    "ast":                         "AST",
    "ggt":                         "GGT",
    "albumin":                     "Albumin",
    "creatinine":                  "Serum Creatinine",
    "egfr":                        "eGFR",
    "urineAlbuminCreatinineRatio":  "UACR",
    "sodium":                      "Sodium",
    "potassium":                   "Potassium",
    "hemoglobin":                  "Hemoglobin",
    "vitaminD25Oh":                "25(OH)D",
    "systolicBloodPressure":       "Systolic Blood Pressure",
    "restingHeartRate":            "Resting Heart Rate",
    "hrvRmssd":                    "HRV RMSSD",
}

FORMULAS: dict[str, str] = {
    "homaIr":                      "fastingInsulin × fastingGlucose / 22.5",
    "egfr":                        "CKD-EPI 2021: варьируется по полу и SCr/κ. Источник: KDIGO 2021",
    "urineAlbuminCreatinineRatio":  "Albumin (mg/dL) / Creatinine (mg/dL) × 1000",
}

# ---------------------------------------------------------------------------
# Authored content: Russian descriptions for all 24 biomarkers (D-06)
# ---------------------------------------------------------------------------

DESCRIPTIONS: dict[str, str] = {
    "ldlC": (
        "LDL-холестерин (липопротеины низкой плотности) — основная транспортная форма "
        "холестерина в крови, доставляющая его к периферическим тканям. "
        "В симуляторе выступает первичным детерминантом сердечно-сосудистого риска: "
        "повышенный ЛПНП ускоряет накопление атеросклеротических бляшек и увеличивает "
        "расчётный индекс биологического возраста. "
        "Отражает функцию сердечно-сосудистой системы и чувствительность к веществам "
        "класса статинов, Омега-3 и диетическим интервенциям. "
        "Единица: mmol/L; нормализуется по полу, возрасту и наличию сердечно-сосудистых событий."
    ),
    "hdlC": (
        "HDL-холестерин (липопротеины высокой плотности) — «защитная» фракция липидов, "
        "участвующая в обратном транспорте холестерина из периферических тканей в печень. "
        "В модели симулятора высокий уровень ЛПВП снижает суммарный сердечно-сосудистый риск "
        "и замедляет прогрессию атеросклероза. "
        "Биомаркер чувствителен к физической активности, алкогольным интервенциям и омега-3. "
        "Нормативные значения различаются по полу: у женщин оптимальный порог выше, "
        "что отражает защитное действие эстрогенов на липидный метаболизм."
    ),
    "triglycerides": (
        "Триглицериды — нейтральные жиры, основная форма хранения энергии в жировой ткани "
        "и главный компонент хиломикронов после приёма пищи. "
        "В симуляторе повышенные триглицериды сигнализируют об инсулинорезистентности, "
        "метаболическом синдроме и риске панкреатита. "
        "Биомаркер отражает состояние метаболической и сердечно-сосудистой систем: "
        "высокие значения усиливают окислительный стресс и системное воспаление. "
        "Измеряется натощак в mmol/L; чувствителен к диете, Омега-3 и физической нагрузке."
    ),
    "apoB": (
        "Аполипопротеин B (ApoB) — белковый компонент атерогенных частиц (ЛПНП, ЛПОНП, ЛП(а)), "
        "каждая из которых несёт ровно одну молекулу ApoB. "
        "В симуляторе ApoB является более точным предиктором атеросклеротического риска, "
        "чем одно лишь значение ЛПНП, поскольку считает общее число атерогенных частиц. "
        "Биомаркер отражает функцию сердечно-сосудистой системы и реагирует на статины, "
        "ниацин и PCSK9-ингибиторы. "
        "Измеряется в g/L; пороговые значения различаются по полу и возрасту."
    ),
    "fastingGlucose": (
        "Глюкоза натощак — концентрация сахара в плазме крови после ночного голодания, "
        "ключевой показатель углеводного обмена и функции β-клеток поджелудочной железы. "
        "В симуляторе выступает первичным входным сигналом для расчёта индекса HOMA-IR "
        "и оценки риска диабета 2 типа. "
        "Биомаркер отражает состояние метаболической системы и реагирует на метформин, "
        "берберин, диетические интервенции и физическую активность. "
        "Измеряется в mmol/L натощак (не менее 8 часов без еды)."
    ),
    "fastingInsulin": (
        "Инсулин натощак — базальный уровень инсулина в крови, отражающий компенсаторную "
        "реакцию поджелудочной железы на инсулинорезистентность. "
        "В симуляторе является вторым аргументом формулы HOMA-IR и одним из ключевых "
        "индикаторов метаболического здоровья. "
        "Хронически повышенный инсулин ускоряет старение через активацию mTOR "
        "и подавление аутофагии. "
        "Биомаркер чувствителен к метформину, ограничению калорий, рапамицину "
        "и низкоуглеводным диетическим стратегиям."
    ),
    "homaIr": (
        "Индекс HOMA-IR (Homeostatic Model Assessment of Insulin Resistance) — расчётный "
        "маркер инсулинорезистентности, вычисляемый как произведение инсулина натощак "
        "и глюкозы натощак, делённое на 22,5. "
        "В симуляторе HOMA-IR интегрирует два отдельных биомаркера в единый индекс "
        "метаболической дисфункции, коррелирующий с риском диабета и сердечно-сосудистых событий. "
        "Повышение HOMA-IR в модели подавляет чувствительность к инсулину и ускоряет "
        "накопление висцерального жира. "
        "Расчётный биомаркер: вычисляется автоматически из fastingInsulin и fastingGlucose."
    ),
    "hba1c": (
        "HbA1c (гликированный гемоглобин) — доля гемоглобина, необратимо связанного с глюкозой, "
        "отражающая среднюю концентрацию глюкозы в крови за предшествующие 2–3 месяца. "
        "В симуляторе HbA1c является долгосрочным маркером гликемического контроля "
        "в отличие от «мгновенного» снимка глюкозы натощак. "
        "Биомаркер реагирует медленно (обновляется со сдвигом ~3 месяца в реальном времени, "
        "ускоренным в симуляции) и отражает кумулятивный ответ метаболической системы. "
        "Измеряется в %; в симуляции чувствителен к метформину, диете и физической активности."
    ),
    "hsCrp": (
        "Высокочувствительный С-реактивный белок (hs-CRP) — острофазовый белок печени, "
        "маркер системного воспаления низкой интенсивности. "
        "В симуляторе hs-CRP отражает активность иммунной системы и выступает посредником "
        "между воспалительными интервенциями и сердечно-сосудистым риском. "
        "Повышенный hs-CRP ускоряет эндотелиальную дисфункцию и увеличивает "
        "индекс биологического возраста. "
        "Биомаркер чувствителен к Омега-3, статинам, ресвератролу и противовоспалительным диетам."
    ),
    "il6": (
        "Интерлейкин-6 (IL-6) — провоспалительный цитокин, секретируемый иммунными клетками, "
        "жировой тканью и скелетными мышцами в ответ на воспаление, травму или инфекцию. "
        "В симуляторе IL-6 является ключевым медиатором системного воспалительного ответа: "
        "хроническое повышение ускоряет саркопению, нейродегенерацию и атеросклероз. "
        "Биомаркер исследовательского статуса отражает работу иммунной системы "
        "и реагирует на Омега-3, рапамицин и антиоксиданты. "
        "Измеряется в pg/mL; референсные значения одинаковы для обоих полов."
    ),
    "alt": (
        "АЛТ (аланинаминотрансфераза) — внутриклеточный фермент, "
        "высвобождающийся при повреждении гепатоцитов. "
        "В симуляторе АЛТ является первичным маркером гепатотоксичности: "
        "повышение сигнализирует о стрессе клеток печени под воздействием веществ "
        "или метаболических нарушений. "
        "Биомаркер отражает функцию печени и реагирует на гепатотоксические вещества, "
        "алкоголь, высококалорийную диету и силовые нагрузки. "
        "Нормативные значения дифференцированы по полу: верхняя граница нормы у мужчин выше."
    ),
    "ast": (
        "АСТ (аспартатаминотрансфераза) — фермент, присутствующий в печени, сердце и мышцах; "
        "повышается при повреждении любого из этих органов. "
        "В симуляторе АСТ дополняет АЛТ как маркер печёночного стресса: "
        "соотношение АСТ/АЛТ > 2 в модели указывает на алкогольный паттерн поражения печени. "
        "Биомаркер отражает функцию печени и чувствителен к тем же интервенциям, что и АЛТ. "
        "Нормативные пороги идентичны для обоих полов, измеряется в U/L."
    ),
    "ggt": (
        "ГГТ (гамма-глутамилтрансфераза) — фермент желчевыводящих путей и печени, "
        "чувствительный маркер холестаза и алкогольного поражения. "
        "В симуляторе ГГТ отражает синергетический эффект алкоголя с другими "
        "гепатотоксическими агентами и является индикатором оксидативного стресса в печени. "
        "Биомаркер реагирует на алкоголь, ожирение и некоторые медикаменты. "
        "Нормативные значения строго дифференцированы по полу: пороги у женщин значительно ниже."
    ),
    "albumin": (
        "Альбумин — основной белок плазмы крови, синтезируемый исключительно печенью; "
        "поддерживает онкотическое давление и транспортирует гормоны, жирные кислоты и лекарства. "
        "В симуляторе альбумин является интегральным маркером функции печени и нутритивного статуса: "
        "снижение означает печёночную недостаточность или хроническое воспаление. "
        "Биомаркер медленно реагирует на изменения (период полувыведения ~20 дней) "
        "и ухудшается при длительном дефиците белка или прогрессирующем циррозе. "
        "Измеряется в g/L; оптимальный диапазон одинаков для обоих полов."
    ),
    "creatinine": (
        "Сывороточный креатинин — продукт метаболизма креатина в мышцах, "
        "выводимый почками путём клубочковой фильтрации. "
        "В симуляторе является первичным маркером почечной функции: "
        "рост концентрации отражает снижение СКФ и накопление азотистых шлаков. "
        "Биомаркер зависит от мышечной массы, поэтому нормативные значения "
        "существенно различаются по полу. "
        "Используется совместно с eGFR для оценки стадии хронической болезни почек "
        "в модели CKD-EPI 2021."
    ),
    "egfr": (
        "Расчётная скорость клубочковой фильтрации (eGFR) — ключевой интегральный показатель "
        "функции почек, вычисляемый по формуле CKD-EPI 2021 из уровня креатинина, "
        "возраста и пола. "
        "В симуляторе eGFR определяет стадию хронической болезни почек и регулирует "
        "скорость выведения веществ через почечный путь элиминации. "
        "Снижение eGFR < 60 в модели запускает протективные механизмы и предупреждения. "
        "Расчётный биомаркер: автоматически пересчитывается из creatinine при каждом тике симуляции."
    ),
    "urineAlbuminCreatinineRatio": (
        "UACR (соотношение альбумин/креатинин в моче) — ранний чувствительный маркер "
        "гломерулярного повреждения почек, позволяющий выявить нефропатию до снижения eGFR. "
        "В симуляторе UACR отражает целостность гломерулярного фильтрационного барьера: "
        "повышение свидетельствует о почечной гипертензии или диабетической нефропатии. "
        "Биомаркер чувствителен к диабетическому и гипертензивному поражению почек "
        "и реагирует на ингибиторы АПФ, метформин и контроль артериального давления. "
        "Измеряется в mg/g; расчётный из отдельных значений альбумина и креатинина мочи."
    ),
    "sodium": (
        "Натрий — основной внеклеточный катион, регулирующий осмолярность плазмы, "
        "водный баланс и нейромышечную передачу. "
        "В симуляторе натрий поддерживает осмотический гомеостаз: "
        "как гипонатриемия (< 130 ммоль/л), так и гипернатриемия (> 145 ммоль/л) "
        "являются клинически опасными состояниями. "
        "Биомаркер отражает функцию почек и реагирует на диуретики, избыточный приём жидкости "
        "и нарушения ренин-ангиотензин-альдостероновой системы. "
        "Диапазоны включают поле low_risk для гипонатриемии и high_risk для гипернатриемии."
    ),
    "potassium": (
        "Калий — основной внутриклеточный катион, критически важный для поддержания "
        "потенциала действия клеток сердечной мышцы и возбудимости нейронов. "
        "В симуляторе дисбаланс калия (как гипо-, так и гиперкалиемия) "
        "повышает риск жизнеугрожающих аритмий, что влияет на сердечно-сосудистый риск-индекс. "
        "Биомаркер отражает функцию почек и сердечно-сосудистой системы: "
        "реагирует на диуретики, АПФ-ингибиторы и дисфункцию почек. "
        "Нормальный диапазон узкий (3,5–5,0 ммоль/л); отклонения в обе стороны опасны."
    ),
    "hemoglobin": (
        "Гемоглобин — железосодержащий белок эритроцитов, транспортирующий кислород "
        "от лёгких к тканям и углекислый газ в обратном направлении. "
        "В симуляторе снижение гемоглобина (анемия) ухудшает кислородное обеспечение тканей, "
        "снижает энергетический статус и ускоряет усталость мышечной системы. "
        "Биомаркер отражает функцию иммунной системы и кроветворения; "
        "реагирует на дефицит железа, В12, хроническое воспаление и высотную адаптацию. "
        "Нормативные диапазоны значительно различаются по полу и незначительно снижаются с возрастом."
    ),
    "vitaminD25Oh": (
        "25(OH)D (кальцидиол) — основная транспортная форма витамина D в крови, "
        "отражающая суммарный статус витамина D из пищи, добавок и синтеза в коже под УФ. "
        "В симуляторе 25(OH)D влияет на иммунную модуляцию, минеральный обмен костей "
        "и экспрессию генов, регулирующих воспаление и клеточную пролиферацию. "
        "Дефицит (< 20 нг/мл) в модели активирует вторичный гиперпаратиреоз и снижает "
        "минеральную плотность костей. "
        "Биомаркер чувствителен к добавкам витамина D3 и воздействию солнечного света."
    ),
    "systolicBloodPressure": (
        "Систолическое артериальное давление — пиковое давление в артериях в момент сокращения "
        "левого желудочка сердца, основной показатель гемодинамической нагрузки на сосудистую стенку. "
        "В симуляторе систолическое давление является ключевым детерминантом сердечно-сосудистого "
        "риска: хроническая гипертензия (> 130 мм рт. ст.) ускоряет атеросклероз "
        "и повышает риск инфаркта и инсульта. "
        "Биомаркер отражает состояние сердечно-сосудистой системы и реагирует на "
        "физическую нагрузку, стресс, натрий в рационе и антигипертензивные вещества. "
        "Измеряется в мм рт. ст.; телеметрический маркер, обновляется в реальном времени."
    ),
    "restingHeartRate": (
        "Пульс покоя — частота сердечных сокращений в состоянии полного покоя, "
        "интегральный показатель вегетативного тонуса и кардиоваскулярной эффективности. "
        "В симуляторе повышенный пульс покоя (> 80 уд/мин) увеличивает нагрузку на "
        "миокард и ассоциируется с более высоким сердечно-сосудистым риском. "
        "Биомаркер реагирует на аэробные тренировки (снижает), кофеин (повышает), "
        "стресс и бета-адреноблокаторы. "
        "Телеметрический маркер, измеряемый в уд/мин; оптимальный диапазон 50–70 уд/мин."
    ),
    "hrvRmssd": (
        "HRV RMSSD (вариабельность сердечного ритма, среднеквадратичное отклонение "
        "последовательных RR-интервалов) — показатель активности парасимпатической нервной системы "
        "и адаптационного резерва организма. "
        "В симуляторе HRV RMSSD является маркером вегетативного баланса: "
        "высокие значения отражают хорошее восстановление и низкий стресс-ответ. "
        "Биомаркер отражает состояние сердечно-сосудистой и нервной систем; "
        "снижается при хроническом воспалении, стрессе и недосыпании. "
        "Телеметрический маркер, измеряемый в мс; оптимальные значения > 50 мс."
    ),
}

# ---------------------------------------------------------------------------
# Organ mechanistic descriptions (D-08, UI-SPEC Section 6)
# ---------------------------------------------------------------------------

ORGAN_DESCRIPTIONS: dict[str, str] = {
    "cardiovascular": (
        "Биомаркер непосредственно отражает гемодинамическую нагрузку и атеросклеротические "
        "процессы в сосудах, определяя риск инфаркта миокарда и инсульта."
    ),
    "liver": (
        "Биомаркер синтезируется или метаболизируется в гепатоцитах, "
        "отражая детоксикационную, белковосинтетическую или экскреторную функцию печени."
    ),
    "kidney": (
        "Биомаркер регулируется или выводится почками, отражая скорость клубочковой "
        "фильтрации, канальциевую реабсорбцию и общее функциональное состояние нефронов."
    ),
    "nervous": (
        "Биомаркер влияет на нейротрансмиссию и вегетативный тонус, "
        "отражая адаптационный резерв центральной и периферической нервной системы."
    ),
    "immune": (
        "Биомаркер продуцируется иммунными клетками или регулирует иммунный ответ, "
        "отражая интенсивность воспалительных и противовоспалительных процессов в организме."
    ),
    "metabolic": (
        "Биомаркер является ключевым участником энергетического обмена, "
        "отражая чувствительность к инсулину, утилизацию глюкозы и жировой метаболизм."
    ),
    "cellular_repair": (
        "Биомаркер влияет на процессы аутофагии, апоптоза и репарации ДНК, "
        "отражая интенсивность клеточного обновления и нагрузку сенесцентными клетками."
    ),
    "bone": (
        "Биомаркер участвует в регуляции кальций-фосфорного обмена и ремоделирования костей, "
        "отражая минеральную плотность и риск остеопороза."
    ),
    "muscle": (
        "Биомаркер связан с синтезом или деградацией мышечного белка, "
        "отражая мышечную массу, силу и риск саркопении."
    ),
}

# Sex-differentiated biomarkers (need male/female table in Section 2)
SEX_DIFF_CODES = {"alt", "ggt", "creatinine", "hdlC", "hemoglobin"}

# Category order for index (UI-SPEC lines 313-321)
CATEGORY_ORDER = [
    "lipids", "glucose", "inflammation", "liver",
    "kidney", "blood_count", "vitamins", "telemetry",
]

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


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _fmt_range(lo, hi) -> str:
    """Format a [lo, hi] range pair as a human-readable string."""
    if lo is None and hi is None:
        return "—"
    if lo is None:
        return f"< {hi}"
    if hi is None:
        return f"≥ {lo}"
    return f"{lo} – {hi}"


def _pair(val) -> tuple:
    """Safely extract (lo, hi) from a reference_ranges.json value.
    Guards against malformed entries (scalar, 1-element list, None) so
    IndexError/TypeError propagates as '—' rather than killing the script.
    """
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        return val[0], val[1]
    return None, None


def _build_range_table(code: str, ranges: dict, units: str) -> str:
    """Build the Section 2 reference range table from reference_ranges.json."""
    bm_ranges = ranges.get(code)
    if not bm_ranges:
        return f"| Оптимальный | — | {units} | Нет данных |\n| Пограничный | — | {units} | — |\n| Высокий риск | — | {units} | — |"

    # Use male 30-39 as the typical row
    typical = bm_ranges.get("male", {}).get("30-39", {})

    # sodium/potassium have low_risk field — handle specially
    has_low_risk = "low_risk" in typical

    if has_low_risk:
        opt = typical.get("optimal", [None, None])
        border = typical.get("borderline", [None, None])
        low = typical.get("low_risk", [None, None])
        high = typical.get("high_risk", [None, None])
        rows = (
            f"| Оптимальный | {_fmt_range(*_pair(opt))} | {units} | Норма |\n"
            f"| Низкий риск | {_fmt_range(*_pair(low))} | {units} | Гипо-состояние |\n"
            f"| Пограничный | {_fmt_range(*_pair(border))} | {units} | Верхняя граница |\n"
            f"| Высокий риск | {_fmt_range(*_pair(high))} | {units} | Гиперсостояние |"
        )
        return rows

    opt = typical.get("optimal", [None, None])
    border = typical.get("borderline", [None, None])
    risk = typical.get("high_risk", [None, None])

    rows = (
        f"| Оптимальный | {_fmt_range(*_pair(opt))} | {units} | Мужчины 30–39 (типовой профиль) |\n"
        f"| Пограничный | {_fmt_range(*_pair(border))} | {units} | — |\n"
        f"| Высокий риск | {_fmt_range(*_pair(risk))} | {units} | — |"
    )
    return rows


def _build_sex_diff_table(code: str, ranges: dict, units: str) -> str:
    """Build dual male/female table for sex-differentiated biomarkers."""
    bm_ranges = ranges.get(code, {})
    male_30 = bm_ranges.get("male", {}).get("30-39", {})
    female_30 = bm_ranges.get("female", {}).get("30-39", {})

    def row_vals(r):
        opt = r.get("optimal", [None, None])
        brd = r.get("borderline", [None, None])
        hrisk = r.get("high_risk", [None, None])
        return _fmt_range(*_pair(opt)), _fmt_range(*_pair(brd)), _fmt_range(*_pair(hrisk))

    mo, mb, mr = row_vals(male_30)
    fo, fb, fr = row_vals(female_30)
    return (
        f"| Диапазон | Мужчины | Женщины | Единицы |\n"
        f"|----------|---------|---------|--------|\n"
        f"| Оптимальный | {mo} | {fo} | {units} |\n"
        f"| Пограничный | {mb} | {fb} | {units} |\n"
        f"| Высокий риск | {mr} | {fr} | {units} |"
    )


# ---------------------------------------------------------------------------
# Page renderer
# ---------------------------------------------------------------------------


def render_page(bm: dict, all_biomarkers: list, ranges: dict) -> str:
    """Render a full 7-section biomarker wiki page."""
    code     = bm["code"]
    name_en  = bm["name"]
    name_ru  = bm["name_ru"]
    category = bm["category"]
    units    = bm["units"]
    status   = bm["status"]
    organs   = bm.get("organs", [])

    folder       = CATEGORY_FOLDER.get(category, category)
    cat_name_ru  = CATEGORY_NAME_RU.get(category, category)
    file_name    = FILE_NAMES.get(code, name_en)

    # Escape | in wikilink aliases (T-02-04)
    safe_cat = cat_name_ru.replace("|", r"\|")

    tags = f"biomarker, mvp, {category}"

    # --- Frontmatter ---
    organs_yaml = ", ".join(organs)
    lines = [
        "---",
        f"code: {code}",
        f"name: {name_en}",
        f"name_ru: {name_ru}",
        f"category: {category}",
        f"units: {units}",
        f"status: {status}",
        "mvp: true",
        f"organs: [{organs_yaml}]",
        f"tags: [{tags}]",
        "---",
        "",
        f"# {name_ru} (`{code}`)",
        "",
        f"> **Единицы:** {units} | **Статус:** {status} | **Категория:** [[02 - Biomarkers/{folder}/\\|{safe_cat}]]",
        "",
        "---",
        "",
    ]

    # --- Section 1: Описание ---
    description = DESCRIPTIONS.get(code, f"*(Описание для `{code}` не добавлено)*")
    lines += [
        "## Описание",
        "",
        description,
        "",
        "---",
        "",
    ]

    # --- Section 2: Референсные диапазоны ---
    callout = (
        "> [!warning] Примечание симуляции\n"
        "> Диапазоны — параметры игровой модели, не персональные медицинские нормы. "
        "Значения основаны на клинических рекомендациях (ACC/AHA, KDIGO, ADA, WHO) "
        "и помечены [ASSUMED] — требуют проверки (D-15)."
    )

    if code in SEX_DIFF_CODES:
        main_table = (
            "| Диапазон | Значение | Единицы | Примечание |\n"
            "|----------|---------|---------|-----------|"
        )
        typical_rows = _build_range_table(code, ranges, units)
        sex_table = _build_sex_diff_table(code, ranges, units)
        range_section = (
            f"{callout}\n\n"
            f"{main_table}\n"
            f"{typical_rows}\n\n"
            f"**Мужчины / Женщины:**\n\n"
            f"{sex_table}"
        )
    else:
        main_table = (
            "| Диапазон | Значение | Единицы | Примечание |\n"
            "|----------|---------|---------|-----------|"
        )
        typical_rows = _build_range_table(code, ranges, units)
        range_section = f"{callout}\n\n{main_table}\n{typical_rows}"

    footer_strat = (
        "*Стратификация: пол (male/female) × возраст (18-29, 30-39, 40-49, 50-59, 60-69, 70+). "
        "Полные значения: `src/data/reference_ranges.json`*"
    )
    lines += [
        "## Референсные диапазоны",
        "",
        range_section,
        "",
        footer_strat,
        "",
        "---",
        "",
    ]

    # --- Section 3: Формула расчёта ---
    formula = FORMULAS.get(code)
    if formula:
        lines += [
            "## Формула расчёта",
            "",
            f"```",
            formula,
            "```",
            "",
            f"*Источник: {'CKD-EPI 2021 (KDIGO)' if code == 'egfr' else 'клиническая формула'}*",
            "",
            "---",
            "",
        ]
    else:
        lines += [
            "## Формула расчёта",
            "",
            "*(не расчётный биомаркер)*",
            "",
            "---",
            "",
        ]

    # --- Section 4: Связанные биомаркеры ---
    same_cat = [b for b in all_biomarkers if b["category"] == category and b["code"] != code]
    related_lines = ["## Связанные биомаркеры", "", f"*(Все биомаркеры категории «{cat_name_ru}»)*", ""]
    for rel in same_cat:
        rel_code   = rel["code"]
        rel_folder = CATEGORY_FOLDER.get(rel["category"], rel["category"])
        rel_file   = FILE_NAMES.get(rel_code, rel["name"])
        rel_name_ru = rel["name_ru"].replace("|", r"\|")
        related_lines.append(
            f"- [[02 - Biomarkers/{rel_folder}/{rel_file}\\|{rel_name_ru}]] (`{rel_code}`)"
        )
    if not same_cat:
        related_lines.append("*(нет связанных биомаркеров в данной категории)*")
    lines += related_lines + ["", "---", ""]

    # --- Section 5: Влияние веществ ---
    lines += [
        "## Влияние веществ",
        "",
        "> [!info] Phase 4 placeholder",
        "> *(Phase 4 — заполняется после M3)*",
        "",
        "| Вещество | Направление | Сила | Уровень доказательности |",
        "|---------|------------|------|------------------------|",
        "| — | — | — | — |",
        "",
        "---",
        "",
    ]

    # --- Section 6: Связь с системами организма ---
    organ_lines = ["## Связь с системами организма", ""]
    for organ_slug in organs:
        organ_name = ORGAN_NAME_RU.get(organ_slug, organ_slug)
        organ_desc = ORGAN_DESCRIPTIONS.get(organ_slug, "*(описание не добавлено)*")
        organ_lines.append(f"- **{organ_name}:** {organ_desc}")
    lines += organ_lines + ["", "---", ""]

    # --- Section 7: Источники ---
    lines += [
        "## Источники",
        "",
        f"*Связь с mortality KB: [[mortality:{name_en}]]*",
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
# Index renderer
# ---------------------------------------------------------------------------


def render_index(biomarkers: list) -> str:
    """Render 08 - Index/Biomarkers Index.md per UI-SPEC contract."""
    today = datetime.date.today().isoformat()

    lines = [
        "---",
        "type: index",
        "category: biomarkers",
        f"created: {today}",
        "---",
        "",
        "# Biomarkers Index",
        "",
        "> Все 24 MVP-биомаркера симулятора im-human. Источник: `src/data/biomarkers.json`.",
        "",
        "---",
        "",
    ]

    # Group by category in canonical order
    by_cat: dict[str, list] = {cat: [] for cat in CATEGORY_ORDER}
    for bm in biomarkers:
        cat = bm["category"]
        if cat in by_cat:
            by_cat[cat].append(bm)

    for cat in CATEGORY_ORDER:
        cat_bms = by_cat.get(cat, [])
        if not cat_bms:
            continue
        cat_name = CATEGORY_NAME_RU.get(cat, cat)
        n = len(cat_bms)
        lines += [
            f"## {cat_name} ({n} биомаркеров)",
            "",
            "| Биомаркер | Код | Единицы | Статус | Страница |",
            "|-----------|-----|---------|--------|---------|",
        ]
        for bm in cat_bms:
            bm_code = bm["code"]
            bm_folder = CATEGORY_FOLDER.get(bm["category"], bm["category"])
            bm_file = FILE_NAMES.get(bm_code, bm["name"])
            bm_name_ru = bm["name_ru"].replace("|", r"\|")
            link = f"[[02 - Biomarkers/{bm_folder}/{bm_file}\\|ссылка]]"
            lines.append(
                f"| {bm_name_ru} | `{bm_code}` | {bm['units']} | {bm['status']} | {link} |"
            )
        lines += ["", "---", ""]

    lines.append(
        f"*Всего: 24 MVP-биомаркера | Сгенерировано: generate_biomarker_pages.py | Обновлено: {today}*"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HOME.md point-edit updater (Pitfall 3 — never rewrite whole file)
# ---------------------------------------------------------------------------


def update_home(vault_root: Path) -> None:
    """Apply point-edits to HOME.md — fix 6 stale links + add index row."""
    home = vault_root / "HOME.md"
    if not home.exists():
        print("[generate] WARNING: HOME.md not found — skipping update", file=sys.stderr)
        return

    content = home.read_text(encoding="utf-8")

    # Fix 6 stale wikilinks (Pitfall 5 — UI-SPEC file names vs HOME.md names)
    replacements = [
        ("Biomarkers/01 - Lipids/ApoB]]",              "Biomarkers/01 - Lipids/Apolipoprotein B]]"),
        ("Biomarkers/03 - Inflammation/IL-6]]",         "Biomarkers/03 - Inflammation/Interleukin-6]]"),
        ("Biomarkers/08 - Vitamins/Vitamin D]]",        "Biomarkers/08 - Vitamins/25(OH)D]]"),
        ("Biomarkers/05 - Kidney/Creatinine]]",         "Biomarkers/05 - Kidney/Serum Creatinine]]"),
        ("Biomarkers/13 - Telemetry/Blood Pressure]]",  "Biomarkers/13 - Telemetry/Systolic Blood Pressure]]"),
        ("Biomarkers/13 - Telemetry/HRV]]",             "Biomarkers/13 - Telemetry/HRV RMSSD]]"),
    ]
    for old, new in replacements:
        content = content.replace(old, new)

    # Update biomarker count in nav table (— → 24)
    content = content.replace(
        "| [[02 - Biomarkers/\\|02 · Биомаркеры]] | Справочник биомаркеров (13 категорий) | — |",
        "| [[02 - Biomarkers/\\|02 · Биомаркеры]] | Справочник биомаркеров (13 категорий) | 24 |",
    )

    # Add Biomarkers Index row in nav table (idempotent)
    index_row = "| [[08 - Index/Biomarkers Index\\|08 · Индексы → Биомаркеры]] | Индекс биомаркеров по категориям | 1 |"
    if "Biomarkers Index" not in content:
        # Insert before the 09 · Шаблоны row or append after 08 · Индексы row
        content = content.replace(
            "| [[09 - Templates/\\|09 · Шаблоны]] |",
            f"{index_row}\n| [[09 - Templates/\\|09 · Шаблоны]] |",
        )

    # Update footer timestamp
    today_str = datetime.date.today().isoformat()
    content = re.sub(
        r"\*Последнее обновление: \d{4}-\d{2}-\d{2}\*",
        f"*Последнее обновление: {today_str}*",
        content,
    )

    home.write_text(content, encoding="utf-8")
    print("[generate] ✓ HOME.md updated")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="im-human biomarker page generator",
        epilog="Reads biomarkers.json + reference_ranges.json, writes 24 Obsidian wiki pages.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing any files",
    )
    args = parser.parse_args()

    print("[generate] Starting biomarker page generation")

    data = load_json(DATA_FILE)
    biomarkers = data.get("biomarkers", [])
    print(f"[generate] Reading biomarkers.json ({len(biomarkers)} biomarkers)")

    print("[generate] Reading reference_ranges.json")
    ranges = load_json(REF_FILE)

    created = 0
    skipped = 0
    failed  = 0

    # Group for category progress reporting
    cat_stats: dict[str, dict[str, int]] = {}
    for bm in biomarkers:
        cat = bm["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"created": 0, "skipped": 0, "total": 0, "failed": 0}
        cat_stats[cat]["total"] += 1

    for bm in biomarkers:
        code      = bm["code"]
        name_en   = bm["name"]
        category  = bm["category"]
        folder    = CATEGORY_FOLDER.get(category, category)
        file_name = FILE_NAMES.get(code, name_en)

        target_path = VAULT_ROOT / "02 - Biomarkers" / folder / f"{file_name}.md"

        if args.dry_run:
            rel = f"02 - Biomarkers/{folder}/{file_name}.md"
            print(f"[generate] [dry-run] would create: {rel}")
            continue

        # Skip-if-exists (D-03)
        if target_path.exists():
            print(f"[generate] ✓ already exists: {name_en}")
            skipped += 1
            cat_stats[category]["skipped"] += 1
            continue

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = render_page(bm, biomarkers, ranges)
            target_path.write_text(content, encoding="utf-8")
            rel = target_path.relative_to(VAULT_ROOT)
            print(f"[generate] ✓ Created: {rel}")
            created += 1
            cat_stats[category]["created"] += 1
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot write {target_path}: {exc}",
                file=sys.stderr,
            )
            failed += 1
            cat_stats[category]["failed"] += 1

    if args.dry_run:
        return

    # Category summary
    for cat in CATEGORY_ORDER:
        if cat in cat_stats:
            s = cat_stats[cat]
            name = CATEGORY_NAME_RU.get(cat, cat)
            failed_info = f" ({s['failed']} failed)" if s['failed'] else ""
            print(f"[generate] Category {name}: {s['created']}/{s['total']}{failed_info}")

    # Render index page (skip-if-exists)
    index_path = VAULT_ROOT / "08 - Index" / "Biomarkers Index.md"
    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            index_path.write_text(render_index(biomarkers), encoding="utf-8")
            rel = index_path.relative_to(VAULT_ROOT)
            print(f"[generate] ✓ Created index: {rel}")
        except OSError as exc:
            print(
                f"[generate] ERROR: Cannot write {index_path}: {exc}",
                file=sys.stderr,
            )
    else:
        print("[generate] ✓ already exists: Biomarkers Index")

    # Update HOME.md with point-edits
    update_home(VAULT_ROOT)

    if failed > 0:
        print(f"[generate] WARNING: {failed} pages failed — see errors above", file=sys.stderr)

    print(f"[generate] Done. Created: {created}, Skipped: {skipped}, Total: 24")
    print("[generate] Next: run ingest_biomarkers.py (DUAL-LAYER)")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
