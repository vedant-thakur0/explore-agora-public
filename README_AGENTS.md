# AGORA: AI Policy Analysis System
## Quick Reference for Claude Agents

**Last Updated:** 2026-03-13
**Status:** Active development on knowledge graph and agent pipelines
**Next Feature:** Supabase connection

---

## 🎯 Project Overview

AGORA is a multi-stage system for discovering, ranking, and analyzing AI policy documents from U.S. Congress. The project combines:
1. **Data ingestion** from Congress.gov with semantic ranking
2. **Knowledge graph construction** over the AGORA corpus
3. **Multi-agent NER/analysis** for entity and relationship extraction
4. **Document similarity matching** against .docx files

**Key Entry Points:** `pipeline/cli.py`, `pipeline/config.py`, notebooks in `notebooks/`

---

## 📁 Directory Structure

```
agora/
├── pipeline/                      # Main ingestion & ranking pipeline
│   ├── cli.py                     # CLI entry point for all operations
│   ├── config.py                  # Global configuration, paths, LLM settings
│   ├── models.py                  # Data classes: DocumentRecord, CandidateRecord
│   ├── store.py                   # File I/O, CSV export, JSON persistence
│   ├── congress.py                # Congress.gov API integration, bill fetching
│   ├── ranker.py                  # Ranking logic: TF-IDF centroid, thresholds
│   ├── docx_matcher.py            # Match incoming .docx against positive profile
│   ├── build_positive_profile.py  # Generate training reference dataset
│   ├── session_pull.py            # Session data ingestion (experimental)
│   ├── knowledge_graph.py         # KG community detection, Louvain clustering
│   ├── graph_query.py             # Query KG structure
│   ├── trial_one_call_hr.py       # Single-call batch retrieval from Congress
│   │
│   ├── raw/                       # Snapshots of raw API payloads
│   ├── normalized/                # Normalized JSONL documents
│   ├── fulltext/                  # Plain-text fulltext by agora_id
│   ├── runs/                      # Run manifests, candidate JSONL, docx match results
│   ├── review_exports/            # CSV exports for human review (decisions tracked)
│   ├── datasets/                  # Training/reference artifacts (positive profile)
│   │
│   ├── agents/                    # Agent execution outputs & memory
│   │   ├── memory/                # Agent persistent memory across runs
│   │   ├── output/                # Agent output artifacts
│   │   └── checkpoints/           # Agent checkpoint saves
│   ├── multiplex_graph/           # Graph community detection output
│   │
│   ├── config/                    # Tuning reference files
│   ├── fixtures/                  # Sample data for offline testing
│   └── tests/                     # Unit tests
│
├── knowledge_graph/               # KG-specific analysis & documentation
│   ├── README.md                  # Data sources, schema, join keys
│   └── data/                      # Filtered Congress-only datasets
│       ├── documents.csv          # 622 Congress documents
│       ├── segments.csv           # 4,087 text segments from those docs
│       └── fulltext/              # 619 plain-text files
│
├── notebooks/                     # Jupyter notebooks for exploration
│   └── graph_exploration.ipynb    # Interactive KG exploration
│
├── requirements.txt               # Python dependencies
├── .env                           # Environment secrets (Congress API key, etc.)
└── CLAUDE.md                      # User preferences & collaboration guidelines (if exists)
```

---

## 🔧 Key Components

### 1. **Models & Data Classes** (`pipeline/models.py`)

```python
DocumentRecord         # Single document from Congress.gov
  - source_id, source_url, title
  - congress, bill_type, bill_number
  - text, extraction_quality
  - text_sha256 (computed property)

CandidateRecord        # Ranked candidate for review
  - run_id, source_id, candidate_score, candidate_tier
  - evidence_snippets, matched_signals
  - review_decision, reviewed_by, reviewed_at
```

**Key Fields:**
- `text_sha256`: Uniquely identifies document content; used for deduplication
- `candidate_tier`: `high`, `medium`, `low`, `skip` (set by ranker)
- `extraction_quality`: `retrieved`, `partial`, `missing` (text availability)

### 2. **Configuration & Paths** (`pipeline/config.py`)

**Global Paths:**
```python
BASE_DIR             = pipeline/
PROJECT_ROOT         = agora/
RAW_DIR, NORMALIZED_DIR, FULLTEXT_DIR, RUNS_DIR, REVIEW_EXPORTS_DIR
AGENTS_DIR, AGENTS_OUTPUT_DIR, AGENTS_CHECKPOINT_DIR, MEMORY_DIR
MULTIPLEX_GRAPH_DIR
```

**LLM Settings:**
```python
ANTHROPIC_MODEL_BULK = "claude-haiku-4-5-20251001"
ANTHROPIC_RATE_DELAY_SECONDS = 0.65  # ~92 RPM
ANTHROPIC_MAX_RETRIES = 1
ANTHROPIC_RETRY_BASE_DELAY = 2
```

**Community Detection (Knowledge Graph):**
```python
LOUVAIN_RESOLUTION = 1.5
SIMILARITY_THRESHOLD = 0.25
DENSE_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COMMUNITY_SIMILARITY_WEIGHTS = {
    "jaccard_taxonomy": 0.50, 
    "cosine_summary": 0.25, 
    "dense_cosine": 0.20,
    "cosponsor_jaccard": 0.05,
}
```

**NER Agent Settings:**
```python
NER_CHUNK_SIZE = 6000
NER_MAX_PARSING_RULES = 7
NER_MEMORY_TOP_N = {...}
```

### 3. **Data Flow Pipeline**

```
Congress.gov API
       ↓
fetch_bills() → raw/ (JSON snapshots)
       ↓
build_records() + hydrate_text() → normalized/ (JSONL)
       ↓
rank_records() → runs/<run_id>_candidates.jsonl
       ↓
export_review_csv() → review_exports/<run_id>_review.csv
       ↓
[Human review + decision tracking]
       ↓
Positive profile → datasets/agora_positive_profile_v1.jsonl
       ↓
Knowledge graph (community detection, NER agents) → agents/output/
```

---

## 🚀 Core Operations (Pipeline CLI)

All commands run from project root: `python3 -m agora.pipeline.cli <command> [options]`

### **1. Fetch Bills from Congress.gov** deprecated, need to rework (ignore section unless explicitly required)

```bash
# Live fetch
python3 -m agora.pipeline.cli fetch \
  --since 2025-01-01 \
  --limit 100

# With custom run ID
python3 -m agora.pipeline.cli fetch \
  --since 2025-01-01 \
  --limit 100 \
  --run-id my_custom_id

# Offline (fixture testing)
python3 -m agora.pipeline.cli fetch \
  --since 2025-01-01 \
  --limit 10 \
  --fixture-json pipeline/fixtures/sample_bills.json \
  --run-id localtest
```

**Output:**
- `runs/<run_id>/raw_payload.json` (API snapshots)
- `runs/<run_id>/manifest.json` (summary: records_fetched, records_with_text)
- `normalized/<run_id>.jsonl` (DocumentRecord JSONL)

### **2. Rank Candidates**

```bash
python3 -m agora.pipeline.cli rank-candidates \
  --run-id <RUN_ID>
  # Optional: --min-score 0.3 --high-threshold 0.7 --medium-threshold 0.5
```

**Logic:**
- Loads documents from `normalized/<run_id>.jsonl`
- Filters out already-reviewed (via `review_exports/`)
- Vectorizes against reference texts (TF-IDF centroid)
- Assigns `candidate_tier`: high (>0.7), medium (0.5-0.7), low, skip (<0.3)
- Saves to `runs/<run_id>_candidates.jsonl`

**Tuning:** Edit `pipeline/config.py` thresholds or `ranker.py` logic. See [TUNING_RUNBOOK.md](pipeline/TUNING_RUNBOOK.md).

### **3. Export for Review**

```bash
python3 -m agora.pipeline.cli export-review \
  --run-id <RUN_ID> \
  --out pipeline/review_exports/<RUN_ID>_review.csv
```

**Output:** CSV with columns:
- `source_id`, `title`, `candidate_score`, `candidate_tier`
- `evidence_snippets`, `matched_signals`
- `include` / `reject` / `unsure` (fill in for decisions)

**Decision Tracking:** Once reviewed, decisions persist in `runs/` index. Future ranks skip already-reviewed docs.

### **4. One-Call HR Trial (Recommended)**

Batch fetch + optional per-bill detail hydration:

```bash
python3 -m agora.pipeline.cli trial-one-call-hr \
  --since 2026-01-01 \
  --limit 251 \
  --top-k 50 \
  --hydrate-details \
  --detail-delay-sec 0.1 \
  --detail-max-retries 2 \
  --out-json runs/trial_<timestamp>.json
```

**Fast variant (list only):**
```bash
python3 -m agora.pipeline.cli trial-one-call-hr \
  --since 2026-01-01 --limit 250 --top-k 50
```

### **5. Match Incoming .docx Files**

```bash
python3 -m agora.pipeline.cli match-docx \
  --docx-dir /path/to/docx \
  --profile-jsonl pipeline/datasets/agora_positive_profile_v1.jsonl \
  --top-k 50 \
  --min-score 0.0 \
  --max-profile-matches 5 \
  --out-json runs/docx_match_<timestamp>.json
```

**Scoring:** `0.70 * semantic_similarity + 0.30 * keyword_score`

**Output:** JSON with matched documents, scores, and evidence.

### **6. Build Positive Profile**

Generate training reference from labeled documents:

```bash
python3 -m agora.pipeline.build_positive_profile \
  --input-csv pipeline/datasets/documents.csv \
  --out-prefix pipeline/datasets/agora_positive_profile_v1
```

**Generated artifacts:**
- `.jsonl` (serialized records with profile_text)
- `.csv` (human-readable)
- `_report.json` (statistics)
- `_lineage.json` (data provenance)

---

## 📊 Knowledge Graph

**Entry Point:** `pipeline/knowledge_graph.py`, `pipeline/graph_query.py`

**Data Sources:**
- Documents: `knowledge_graph/data/documents.csv` (622 Congress docs)
- Segments: `knowledge_graph/data/segments.csv` (4,087 segments)
- Full text: `knowledge_graph/data/fulltext/` (619 .txt files)

**Join Keys:** first two most important
- `documents.csv` → `AGORA ID` = filename in `fulltext/<agora_id>.txt`
- `segments.csv` → `Document ID` = `AGORA ID`
- `documents.csv` → `Authority` = issuer 
- `documents.csv` → `Collections` (semicolon-delimited) = thematic groups

**Community Detection:**
- Louvain clustering with resolution=1.5
- Weighted by taxonomy overlap, summary similarity, cosponsor overlap
- Output: `multiplex_graph/<run_id>_communities.json`

**Features to Add:** Entity linking (NER agents), relationship inference

---

## 🤖 Agent Architecture

**Directory:** `pipeline/agents/`

**Components:**
- `agents/memory/` — Persistent context across agent runs
- `agents/output/` — Generated artifacts, extracted entities, relationships
- `agents/checkpoints/` — State saves for resumable runs

**Current Agents:**
1. **NER Agent** — Extracts named entities (organizations, roles, legislation refs, offices, docs)
   - Settings in `config.py`: `NER_CHUNK_SIZE`, `NER_MAX_PARSING_RULES`, `NER_MEMORY_TOP_N`
   - Processes documents in sections, maintains entity memory

2. **Graph Query Agent** — Queries KG structure, retrieves neighbors, communities
   - Entry: `pipeline/graph_query.py`
   - Returns structured graph slices

3. **Session Pull Agent** (experimental) — Ingests session data
   - Entry: `pipeline/session_pull.py`

**Progress Tracking:**
- Agent outputs saved to `agents/output/<agent_name>_<timestamp>.json`
- Checkpoints in `agents/checkpoints/` for resumable work
- Memory in `agents/memory/<topic>_memory.jsonl` for context reuse

---

## 📋 Important Files & References

### Tuning & Ranking (Deprecated)
- [TUNING_RUNBOOK.md](pipeline/TUNING_RUNBOOK.md) — Process, guardrails, rollback for ranking tuning
- [TUNING_CHANGELOG.md](pipeline/TUNING_CHANGELOG.md) — Append-only history of tuning impacts

### API & Data Ingestion (Deprecated)
- [API_SESSION_INGESTION_PLAYBOOK.md](pipeline/API_SESSION_INGESTION_PLAYBOOK.md) — Session data ingestion guide

### Knowledge Graph Schema
- [knowledge_graph/README.md](knowledge_graph/README.md) — Full data schema, join keys, limitations

### Interactive Exploration
- `notebooks/graph_exploration.ipynb` — Jupyter notebook for KG visualization & analysis

---

## 🔐 Environment & Setup

**Required:**
```bash
export CONGRESS_API_KEY="your_key_here"
```

**Optional .env file** (at repo root):
```
CONGRESS_API_KEY=your_key_here
```

**Dependencies:**
- `python-docx>=1.1.0` — .docx parsing
- `anthropic>=0.40.0` — Claude API for agents
- `networkx>=3.3` — Graph operations
- `sentence-transformers>=2.7.0` — Dense embeddings
- `optuna>=3.6.0` — Hyperparameter tuning
- `numpy`, `pandas` — Data processing

**Install:**
```bash
pip install -r requirements.txt
```

---

## 📝 For Claude Agents: How to Update This README

When you make significant changes, **update this file in these sections:**

1. **Project Status** (top): Update timestamp, current phase
2. **Directory Structure**: Add/remove directories, update descriptions
3. **Key Components**: Add new classes/modules, update config settings
4. **Core Operations**: Add new CLI commands, update existing ones
5. **Agent Architecture**: Log new agents, their purpose, settings
6. **Important Files**: Add/remove documentation links
7. **Progress Log** (below): Append dated entries for major work

### Template for Agent Work:
```markdown
### [Date] - [Agent Name/Task]
- **Status:** [In Progress / Complete]
- **Changes:** Brief description
- **Files Modified:** [List of key files]
- **New Settings:** Any config.py additions
- **Next Steps:** Blockers or follow-up work
```

---

## 📊 Progress Log

### 2026-03-13 - Bill Sponsors Data Export
- **Status:** Complete
- **Changes:** Created comprehensive bill sponsors CSV with sponsor details, bills, and committee info
- **Files Modified:** `knowledge_graph/data/bill_sponsors.csv` (new), `knowledge_graph/data/bill_sponsors_README.md` (new)
- **Data:** 205 unique sponsors, 509 sponsored bills, 507 with committee information (99.6% coverage)
- **Sources:** Aggregated from `agora_with_sponsors.csv`, `agora_comprehensive_data.csv`, and `pulled_data.json`
- **Features:** Sponsor BioGuide IDs, party/state/district, policy areas, committee counts, Congress.gov API URLs for committee details
- **Next Steps:** Users can fetch full committee details via included Congress.gov API endpoints

### 2026-03-12 - Initial Agent README
- **Status:** Complete
- **Changes:** Created comprehensive README for Claude agents
- **Purpose:** Reduce time agents spend reading scattered docs
- **Key Sections:** Quick overview, directory map, core operations, agent architecture
- **Next Steps:** Agents to update this log as they make changes

### 2025-02-26 - Knowledge Graph Dev
- **Status:** Complete
- **Changes:** Added community detection, Louvain clustering
- **Files Modified:** `pipeline/config.py`, `pipeline/knowledge_graph.py`
- **New Settings:** `LOUVAIN_RESOLUTION`, `COMMUNITY_SIMILARITY_WEIGHTS`

### 2025-02-15 - Docx/Txt Matcher Pipeline
- **Status:** Complete
- **Changes:** Added `.docx` matching against positive profile
- **Files Modified:** `pipeline/docx_matcher.py`, `pipeline/cli.py`
- **Scoring:** `0.70 * semantic + 0.30 * keyword`

### 2025-02-10 - Positive Profile Build
- **Status:** Complete
- **Changes:** Generate training reference from labeled corpus
- **Files Modified:** `pipeline/build_positive_profile.py`
- **Artifacts:** JSONL, CSV, report, lineage

---

## 🎓 Common Workflows for Agents

### **Task: Improve Ranking Quality**
1. Get current run: `python3 -m agora.pipeline.cli fetch --since <date> --limit 50`
2. Rank: `python3 -m agora.pipeline.cli rank-candidates --run-id <ID>`
3. Export: `python3 -m agora.pipeline.cli export-review --run-id <ID>`
4. Review CSV, make decisions
5. Evaluate precision/recall against ground truth
6. Adjust `config.py` thresholds or `ranker.py` logic
7. Rerun and compare — document change in [TUNING_CHANGELOG.md](pipeline/TUNING_CHANGELOG.md)

### **Task: Extract Entities from Document Set**
1. Identify document IDs in `pipeline/normalized/` or `knowledge_graph/data/documents.csv`
2. Run NER agent on document text (stored in `agents/output/`)
3. Save results to `agents/output/ner_entities_<timestamp>.jsonl`
4. Link entities to document IDs for later relationship inference

### **Task: Analyze Knowledge Graph Communities**
1. Access graph data in `multiplex_graph/` or compute via `pipeline/knowledge_graph.py`
2. Use `pipeline/graph_query.py` to explore specific communities
3. Visualize in `notebooks/graph_exploration.ipynb`
4. Document findings and save to `agents/output/`

### **Task: Add a New Document Source**
1. Implement fetch logic in new module (e.g., `pipeline/custom_source.py`)
2. Return `DocumentRecord` objects
3. Integrate into CLI via `pipeline/cli.py`
4. Store in `raw/`, `normalized/` following existing schema
5. Update this README with new source description

---

## 🔗 Quick Links

- **CLI Entry:** `pipeline/cli.py`
- **Configuration:** `pipeline/config.py`
- **Data Classes:** `pipeline/models.py`
- **File I/O:** `pipeline/store.py`
- **Ranking Logic:** `pipeline/ranker.py`
- **Knowledge Graph:** `pipeline/knowledge_graph.py`
- **Agent Outputs:** `pipeline/agents/output/`
- **Tuning Guide:** `pipeline/TUNING_RUNBOOK.md`
- **Tuning History:** `pipeline/TUNING_CHANGELOG.md`

---

**For detailed API docs, see individual module docstrings. For data schema, see [knowledge_graph/README.md](knowledge_graph/README.md).**
