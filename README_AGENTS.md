# AGORA: AI Policy Analysis System
## Quick Reference for Claude Agents

**Last Updated:** 2026-03-13
**Status:** Active development on knowledge graph and agent pipelines
**Next Feature:** Supabase connection


**Key Instruction**
Do not spin up explore agents or bash commands unless absolutely necessary! Use context provided in existing .md files and plan files as much as possible!
---

## 🎯 Current Project Focus

A multi-stage system for discovering, ranking, and analyzing AI policy documents from U.S. Congress. The project combines:
1. **Knowledge graph construction** over the AGORA corpus
2. **Multi-agent NER/analysis** for entity and relationship extraction
3. **Document similarity matching** against .docx files

**Key Entry Points:** `pipeline/cli.py`, `pipeline/config.py`

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
## 🤖 Agent Architecture

**Directory:** `pipeline/agents/`

**Components:**
- `agents/memory/` — Persistent context across agent runs
- `agents/output/` — Generated artifacts, extracted entities, relationships
- `agents/checkpoints/` — State saves for resumable runs

**Current Agents:**
1. **NER Agent** — Extracts named entities (organizations, roles, legislation refs, offices, docs)
   - Settings in `config.py`: `NER_CHUNK_SIZE`, `NER_MAX_PARSING_RULES`, `NER_MEMORY_TOP_N`
   - Read NER_AGENT.md
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

### Knowledge Graph Schema
- [knowledge_graph/README.md](knowledge_graph/README.md) — Full data schema, join keys, limitations

### Interactive Exploration
- `notebooks/graph_exploration.ipynb` — Jupyter notebook for KG visualization & analysis

---

## 🔐 Environment & Setup


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
