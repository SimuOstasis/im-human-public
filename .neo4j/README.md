# im-human · Neo4j GraphRAG Schema

Двухслойная база знаний: Obsidian (human layer) ↔ Neo4j `Human` (AI semantic layer).  
Аналогична схеме `Mortality`, но расширена специфическими узлами симулятора.

## Quick start

```powershell
cd W:\Obsidian\human\.neo4j

# 1. Проверить подключение
.\venv\Scripts\python.exe check_connection.py

# 2. Создать схему (constraints, indexes)
.\venv\Scripts\python.exe setup_schema.py

# 3. Загрузить биомаркеры
.\venv\Scripts\python.exe ingest_biomarkers.py

# 4. Загрузить вещества
.\venv\Scripts\python.exe ingest_substances.py

# 5. Загрузить вики-страницы (с эмбеддингами)
.\venv\Scripts\python.exe ingest_wiki.py --dry-run
.\venv\Scripts\python.exe ingest_wiki.py

# 6. Статистика базы
.\venv\Scripts\python.exe db_stats.py

# 7. Запросы
.\venv\Scripts\python.exe query_wiki.py "HOMA-IR инсулинорезистентность"
.\venv\Scripts\python.exe query_facts.py "рапамицин mTOR"
```

## Incremental update

```powershell
# Только изменённые файлы
.\venv\Scripts\python.exe ingest_wiki.py --changed-only

# Конкретный раздел
.\venv\Scripts\python.exe ingest_wiki.py --section biomarkers
```

---

## Graph Schema

### Узлы (Nodes)

#### Wiki-слой (аналогичен Mortality)

| Узел | Ключ | Описание |
|------|------|---------|
| `:Page` | `slug` (unique) | Один markdown-файл |
| `:Chunk` | `id` (unique) | Текстовый чанк с 384d эмбеддингом |
| `:Tag` | `name` (unique) | Frontmatter tag |

#### Предметный слой (специфичен для Human)

| Узел | Ключ | Описание |
|------|------|---------|
| `:Biomarker` | `code` (unique) | Биомаркер (ldlC, hba1c, ...) |
| `:BiomarkerCategory` | `slug` (unique) | Категория (lipids, glucose, ...) |
| `:Organ` | `slug` (unique) | Система организма (cardiovascular, liver, ...) |
| `:Substance` | `id` (unique) | Вещество/интервенция |
| `:Interaction` | `hash` (unique) | Взаимодействие между двумя веществами |
| `:Effect` | `id` (unique) | Эффект вещества на орган/биомаркер |
| `:HumanProfile` | `profile_id` (unique) | Пресет или сохранённый профиль |
| `:SimulationRun` | `run_id` (unique) | Запуск симуляции (seed + config) |

### Связи (Relationships)

| Связь | От → До | Смысл |
|-------|---------|-------|
| `:LINKS_TO` | `:Page` → `:Page` | Obsidian `[[wikilink]]` |
| `:PART_OF` | `:Chunk` → `:Page` | Чанк принадлежит странице |
| `:HAS_TAG` | `:Page` → `:Tag` | Frontmatter тег |
| `:BELONGS_TO` | `:Biomarker` → `:BiomarkerCategory` | Биомаркер в категории |
| `:REFLECTS` | `:Biomarker` → `:Organ` | Биомаркер отражает состояние органа |
| `:TARGETS` | `:Substance` → `:Organ` | Вещество воздействует на орган |
| `:AFFECTS` | `:Substance` → `:Biomarker` | Вещество изменяет биомаркер |
| `:INTERACTS_WITH` | `:Substance` → `:Substance` | Взаимодействие (свойство `type`) |
| `:HAS_EFFECT` | `:Substance` → `:Effect` | Вещество имеет эффект |
| `:DOCUMENTED_IN` | `:Biomarker\|:Substance` → `:Page` | Связь с вики-страницей |
| `:REFERENCES_MORTALITY` | `:Page` → `:Page(Mortality)` | Ссылка на mortality KB |

---

## CONSTRAINTS и INDEXES

Создаются скриптом `setup_schema.py`:

```cypher
-- Wiki
CREATE CONSTRAINT page_slug_unique IF NOT EXISTS FOR (p:Page) REQUIRE p.slug IS UNIQUE
CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE
CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE

-- Biomarkers
CREATE CONSTRAINT biomarker_code_unique IF NOT EXISTS FOR (b:Biomarker) REQUIRE b.code IS UNIQUE
CREATE CONSTRAINT category_slug_unique IF NOT EXISTS FOR (c:BiomarkerCategory) REQUIRE c.slug IS UNIQUE
CREATE CONSTRAINT organ_slug_unique IF NOT EXISTS FOR (o:Organ) REQUIRE o.slug IS UNIQUE

-- Substances
CREATE CONSTRAINT substance_id_unique IF NOT EXISTS FOR (s:Substance) REQUIRE s.id IS UNIQUE
CREATE CONSTRAINT interaction_hash_unique IF NOT EXISTS FOR (i:Interaction) REQUIRE i.hash IS UNIQUE

-- Profiles
CREATE CONSTRAINT profile_id_unique IF NOT EXISTS FOR (p:HumanProfile) REQUIRE p.profile_id IS UNIQUE
CREATE CONSTRAINT run_id_unique IF NOT EXISTS FOR (r:SimulationRun) REQUIRE r.run_id IS UNIQUE

-- Indexes
CREATE INDEX biomarker_category IF NOT EXISTS FOR (b:Biomarker) ON (b.category)
CREATE INDEX organ_name IF NOT EXISTS FOR (o:Organ) ON (o.name)
```

---

## Векторный индекс

```cypher
CREATE VECTOR INDEX human_wiki_chunks IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}}
```

**Модель:** `paraphrase-multilingual-MiniLM-L12-v2` (384d) — та же, что в Mortality.

---

## Slug Format

`{section}/{filename-slug}`

| Папка Obsidian | Section slug | Пример slug |
|----------------|-------------|-------------|
| `00 - Inbox/` | `inbox` | `inbox/omega-3-study` |
| `01 - Human Profiles/` | `profiles` | `profiles/young-healthy-30m` |
| `02 - Biomarkers/` | `biomarkers` | `biomarkers/lipids/ldl-cholesterol` |
| `03 - Substances/` | `substances` | `substances/omega-3` |
| `04 - Interactions/` | `interactions` | `interactions/omega3-vitamin-d` |
| `05 - Simulation/` | `simulation` | `simulation/scenario-baseline` |
| `06 - Engine/` | `engine` | `engine/tick-formula` |
| `07 - Analysis/` | `analysis` | `analysis/simulation-assumptions` |

---

## Полезные Cypher запросы

```cypher
-- Все биомаркеры категории lipids
MATCH (b:Biomarker)-[:BELONGS_TO]->(c:BiomarkerCategory {slug: 'lipids'})
RETURN b.code, b.name, b.units ORDER BY b.name

-- Вещества, влияющие на конкретный биомаркер
MATCH (s:Substance)-[:AFFECTS]->(b:Biomarker {code: 'ldlC'})
RETURN s.name, s.category

-- Взаимодействия рапамицина
MATCH (s:Substance {id: 'rapamycin'})-[r:INTERACTS_WITH]->(s2:Substance)
RETURN s2.name, r.type, r.coefficient

-- Семантический поиск (после инgesт)
CALL db.index.vector.queryNodes('human_wiki_chunks', 5, $embedding)
YIELD node, score
MATCH (node)-[:PART_OF]->(p:Page)
RETURN p.title, p.slug, score

-- Биомаркеры без вики-страниц
MATCH (b:Biomarker)
WHERE NOT exists((b)-[:DOCUMENTED_IN]->(:Page))
RETURN b.code, b.name
```

---

## Environment (.env)

```
NEO4J_URI=bolt://<neo4j-host>:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
NEO4J_DATABASE=Human

MORTALITY_NEO4J_URI=bolt://<neo4j-host>:7687
MORTALITY_NEO4J_USER=neo4j
MORTALITY_NEO4J_PASSWORD=<password>
MORTALITY_NEO4J_DATABASE=Mortality
```

---

## Намеренные расхождения с Obsidian (Design Decisions)

### `reference_ranges` не хранятся в Neo4j

`src/data/biomarkers.json` содержит `reference_ranges` (optimal / borderline / high_risk) для каждого биомаркера.
Эти данные **намеренно не загружаются** в Neo4j — они используются только симулятором (`src/engine/`) напрямую из JSON.

Причина: референсные диапазоны — статические константы модели симулятора, а не связанные данные графа.
Добавлять `:ReferenceRange` узлы в Neo4j не имеет смысла до появления запросов, которые их используют.
