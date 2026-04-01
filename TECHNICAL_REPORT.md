# AGORA Technical Report
*For technical interview preparation — March 2026*

---

## 1. Project Overview

**AGORA (Explore-AGORA)** is a computational toolkit for AI policy research. It processes a corpus of ~622 U.S. congressional legislative documents tagged as AI-related (from the AGORA dataset on Zenodo), and builds a **multiplex knowledge graph** with three analytical layers: legislative sponsorship, thematic communities, and named entities.

**Core design principles:**
- **Computational minimalism** — use deterministic algorithms where possible; LLMs only where necessary
- **Reproducibility** — all random processes are seeded; all thresholds are centralized in `config.py`
- **Resilience** — checkpointing enables resumable runs; retries with exponential backoff handle API failures
- **Transparency** — every output artifact is auditable (JSONL, GraphML, CSV)

---

## 2. System Architecture

### High-Level Flowchart

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                        DATA SOURCES                             │
  │  AGORA CSV corpus (Zenodo)  ·  Sponsor CSV  ·  Fulltext files  │
  └──────────────────────────┬──────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Phase 0       │
                    │ Knowledge Graph │  documents.csv + segments.csv
                    │ Build           │  → nodes.csv + edges.csv
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
  ┌────────▼──────┐ ┌────────▼──────┐ ┌────────▼──────┐
  │   Phase 1     │ │   Phase 2     │ │   Phase 3     │
  │ Sponsor Graph │ │  Community    │ │  NER Agent    │
  │ (deterministic│ │  Detection    │ │  (Claude LLM  │
  │  CSV parse)   │ │  (Louvain)    │ │   + memory)   │
  └────────┬──────┘ └────────┬──────┘ └────────┬──────┘
           └─────────────────┼─────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Phase 4       │
                    │  Multiplex      │
                    │  Graph Assembly │
                    │                 │
                    │  layer_1_sponsor│
                    │  layer_2_community
                    │  layer_3_entity │
                    │  + combined     │
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             │               │               │
     ┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼───────┐
     │  Graph Query │ │  Web UI     │ │  Supabase   │
     │  (BFS+rank)  │ │  (Flask +   │ │  Sync       │
     │              │ │  annotation)│ │             │
     └──────────────┘ └─────────────┘ └─────────────┘
```

---

## 3. Component Deep Dives

### 3.1 Configuration (`config.py`)

Single source of truth for all constants — no hardcoded values anywhere else in the pipeline.

**Key settings:**
```python
ANTHROPIC_MODEL_BULK = "claude-haiku-4-5-20251001"
ANTHROPIC_RATE_DELAY_SECONDS = 0.65      # ~92 RPM (under 100 RPM limit)
ANTHROPIC_RETRY_BASE_DELAY = 2           # doubles each retry: 2, 4, 8 seconds

LOUVAIN_RESOLUTION = 1.5
SIMILARITY_THRESHOLD = 0.25              # minimum edge weight for graph
COMMUNITY_SIMILARITY_WEIGHTS = {
    "jaccard_taxonomy": 0.50,
    "cosine_summary": 0.25,
    "dense_cosine": 0.20,
    "cosponsor_jaccard": 0.05,
}
SUBCLUSTERING_SIZE_THRESHOLD = 80        # recurse if community > 80 docs

NER_CHUNK_SIZE = 6000                    # max chars per section chunk
NER_MAX_PARSING_RULES = 7               # max active rules in prompt
```

---

### 3.2 Phase 0: Knowledge Graph Build (`knowledge_graph.py`)

**Input:** `documents.csv`, `segments.csv`, `authorities.csv`, `collections.csv`

**What it does:** Constructs a base knowledge graph as labeled nodes and typed edges before any agent processing.

**Node types:** Document, Segment, Authority, Collection, Tag, Topic

**Edge types:**
- `HAS_SEGMENT` — document → segment
- `HAS_TAG` — segment/document → tag
- `HAS_TOPIC` — segment/document → topic
- `UNDER_AUTHORITY` — document → authority
- `IN_COLLECTION` — document → collection

**Outputs:** `pipeline/graph/nodes.csv`, `edges.csv`, `stats.json`

---

### 3.3 Phase 1: Sponsor Graph (`agents/sponsor_graph.py`)

**Pure deterministic.** No LLM involved.

```
agora_with_sponsors.csv
        │
  Parse sponsor records
  (bioguide_id, party, state, district, chamber)
        │
  ┌─────┴──────────────────────┐
  │                            │
Build Sponsor nodes      Build SPONSORED_BY edges
(205 sponsors)           (document → sponsor)
                                │
                         Build SHARES_SPONSOR edges
                         (docs sharing same sponsor)
        │
  ┌─────┴──────────────────┐
sponsor_nodes.csv     sponsor_edges.csv
doc_sponsor_matrix.json
doc_url_map.json
```

**Key design choice:** Bill sections that share the same Congress.gov URL are grouped as one logical bill — multi-section bills are treated cohesively.

---

### 3.4 Phase 2: Community Detection (`agents/community_detector.py`)

**Goal:** Group 622 documents into thematic communities using graph clustering.

**Flowchart:**

```
  agora_with_sponsors.csv
           │
  1. BILL GROUPING
     Group doc sections by Congress.gov URL
     Merge taxonomy tags from all sections → canonical doc per bill
           │
  2. COMPUTE 3 SIMILARITY SIGNALS (pairwise across all canonical docs)
     │
     ├─ Taxonomy Jaccard (weight: 0.50)
     │    80+ binary "Category: Subcategory" columns
     │    sim(A,B) = |tags_A ∩ tags_B| / |tags_A ∪ tags_B|
     │
     ├─ TF-IDF Cosine (weight: 0.25)
     │    Vectorize: Short Summary + Long Summary + Tags
     │    sim = cosine(tfidf_A, tfidf_B)
     │
     └─ Dense Embedding Cosine (weight: 0.20)
          sentence-transformers: all-MiniLM-L6-v2
          sim = dot(unit_emb_A, unit_emb_B)
           │
  3. COMBINE: combined_score = Σ weight_i × signal_i
     Keep edge if combined_score > 0.25
           │
  4. BUILD GRAPH: nodes = canonical docs, edges = above threshold
           │
  5. LOUVAIN CLUSTERING (Pass 1)
     nx.community.louvain_communities(G, resolution=1.5, seed=42)
           │
  6. EXPAND: map canonical IDs back to all sections in each bill
           │
  7. SUBCLUSTER (Pass 2)
     For communities > 80 docs:
       Re-run Louvain on subgraph (resolution=2.5, depth ≤ 2)
           │
  8. ENRICH each community:
     - doc_centrality (weighted degree within community subgraph)
     - label (top-3 taxonomy tags present in ≥40% of members)
     - dominant_party (most common party among sponsors)
     - bill_groups (multi-section bills within community)
           │
  communities.json (243 communities, 535 docs)
```

**Why three signals?** Redundancy and cross-validation. Taxonomy captures topical alignment; TF-IDF captures surface-level text similarity; dense embeddings capture latent semantic similarity. No single signal dominates.

**Why Louvain?** It's unsupervised (no need for pre-specified k), naturally handles variable-size clusters, and is widely interpretable in graph analysis contexts.

---

### 3.5 Phase 3: NER Agent with Memory (`agents/ner_agent.py`)

This is the only LLM-driven phase. It extracts 5 entity types from legislative fulltext.

**Entity types:**

| Type | Fields | Example |
|---|---|---|
| organizations | name, acronym, context | DARPA, NSF |
| offices | name, parent_org, context | Office of the CTO (DoD) |
| roles | title, org, context | Secretary of Defense |
| legislation_refs | name, citation, ref_type, context | cites / amends / enacts / repeals |
| named_docs | name, doc_type, owner_org, context | National AI Strategy (OSTP) |

**Full workflow:**

```
Load communities.json (sorted by community_id)
│
For each community:
│
├─ Load or create CommunityMemory JSON
│    {entity_roster, disambiguation_rules, parsing_rules, oddities}
│
├─ Sort member docs by centrality DESC
│    (highest-confidence docs processed first → seeds memory for later docs)
│
└─ For each document:
     │
     ├─ Check ner_checkpoint.jsonl → skip if already done/failed
     │
     ├─ Load fulltext (local file or Supabase Storage)
     │
     ├─ Chunk text at SEC./SECTION. boundaries (max 6000 chars each)
     │    Fallback: subsection headers → hard character splits
     │
     └─ For each chunk:
          │
          ├─ Build prompt:
          │    system_prompt (static task instructions)
          │    + memory_context (entity roster top-N, disambiguation rules,
          │                      parsing rules ≤7, oddities)
          │    + user_prompt (doc title, summary, chunk text)
          │
          ├─ Call Claude Haiku 4.5
          │    Retry: 3 attempts, exponential backoff (2s, 4s, 8s)
          │    Rate limit: sleep 0.65s after each call
          │
          ├─ Parse JSON (try direct parse → fallback strict re-attempt)
          │
          ├─ Validate schema: all 5 entity type keys present
          │
          └─ Filter generic terms:
               Drop entities < 5 chars
               Drop matches to GENERIC_STEMS frozenset
               ("federal agencies", "the committee", etc.)
          │
     ├─ Merge all chunks (deduplicate by name)
     ├─ Append EntityRecord to entities.jsonl
     ├─ Update CommunityMemory (roster, rules, disambiguation)
     └─ Append checkpoint record (status: done / failed)
│
Generate ner_coverage_report.json
```

**Memory system detail:**

```
{community_id}_memory.json
├── entity_roster: {
│     "organizations": [{name, acronym, mention_count}, ...],  ← top-20
│     "offices": [...],                                          ← top-15
│     "roles": [...],                                            ← top-10
│     "legislation_refs": [...],                                 ← top-15
│     "named_docs": [...]                                        ← top-10
│   }
├── disambiguation_rules: {"the Department": "Department of Defense", ...}
├── parsing_rules: ["Office names follow 'Office of [noun]' pattern", ...]
│     (max 7 active; older rules archived to archived_rules[])
├── oddities: [{description, example_doc}, ...]
├── docs_processed: 12
└── docs_total: 34
```

**Why process by centrality?** High-centrality docs are most representative of the community. Processing them first builds the memory with the most relevant entities, improving context quality for lower-confidence docs.

**Safeguards:**
1. **Rate limiting is non-negotiable** — violating 0.65s delay causes silent NER corruption
2. Generic term filtering prevents noise ("federal agencies", "the committee")
3. Canonical org map resolves 22 common acronyms ("dod" → "Department of Defense")
4. Parsing rules capped at 7 active entries to prevent prompt bloat
5. Checkpoint file means the pipeline can be killed and resumed with zero re-work

---

### 3.6 Phase 4: Multiplex Graph Assembly (`agents/graph_builder.py`)

Combines all three agent outputs into a layered NetworkX MultiDiGraph.

```
Phase 1 outputs          Phase 2 outputs          Phase 3 outputs
sponsor_nodes.csv        communities.json          entities.jsonl
sponsor_edges.csv                │                 canonical_entity_map.json
        │                        │                          │
        └────────────────────────┼──────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     LAYER ASSEMBLY       │
                    │                         │
                    │  Layer 1: Sponsor Graph  │
                    │   Nodes: Sponsor, Doc    │
                    │   Edges: SPONSORED_BY,   │
                    │          SHARES_SPONSOR  │
                    │                         │
                    │  Layer 2: Community      │
                    │   Nodes: Community, Doc  │
                    │   Edges: IN_COMMUNITY    │
                    │          (weight=centrality)│
                    │                         │
                    │  Layer 3: Entity         │
                    │   Nodes: Org, Office,    │
                    │          Role, Legislation│
                    │          Named_Doc       │
                    │   Edges: MENTIONS_ORG,   │
                    │          INVOLVES_ROLE,  │
                    │          REFERENCES_LEGISLATION, etc.│
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
     layer_1_sponsor.graphml  layer_2_community.graphml
     layer_3_entity.graphml   multiplex_combined.graphml
                              multiplex_stats.json
```

---

### 3.7 LLM Client (`agents/llm_client.py`)

Shared Anthropic SDK wrapper. All Claude calls go through here.

```python
def call_claude_json(system, user, model, max_tokens):
    for attempt in range(ANTHROPIC_MAX_RETRIES):      # 3 attempts
        try:
            response = client.messages.create(...)
            time.sleep(ANTHROPIC_RATE_DELAY_SECONDS)  # 0.65s

            # Two-pass JSON parsing:
            parsed = json.loads(response)             # Pass 1: direct
            if parsed is None:
                # Pass 2: retry with strict "Return ONLY valid JSON" prefix
                response = client.messages.create(strict_prompt)
                parsed = json.loads(response)

            return parsed, prompt_tokens, completion_tokens

        except (RateLimitError, InternalServerError):
            delay = RETRY_BASE_DELAY * (2 ** attempt) # 2, 4, 8 seconds
            time.sleep(delay)

    return None, 0, 0
```

---

### 3.8 Graph Query (`graph_query.py`)

BFS neighborhood expansion with relevance ranking.

```
seed_node_id (e.g., "document:1234")
        │
  BFS from seed (up to max_hops)
  Filter by: relation type, node type
        │
  Score each visited node:
    score = Σ (relation_weight × hop_decay^hops)

  DEFAULT_RELATION_WEIGHTS:
    HAS_TOPIC:      1.00
    HAS_TAG:        0.85
    HAS_SEGMENT:    0.75
    IN_COLLECTION:  0.65
    UNDER_AUTHORITY:0.55

  DEFAULT_HOP_DECAY = 0.7
        │
  Sort by score DESC, limit N
        │
  Return ranked neighborhood
```

---

### 3.9 Web Application (`web/`)

Flask app with four route modules.

| Route module | Purpose |
|---|---|
| `documents.py` | List docs with pagination; fetch fulltext (local or Supabase) |
| `annotation.py` | Save/load manual entity annotations; upsert to entity dictionary |
| `dictionary.py` | Browse and edit canonical entity dictionary |
| `auto_extract.py` | Trigger NER or serve cached NER results |

Manual annotations saved to `pipeline/agents/output/manual_annotations/{agora_id}.json`.

---

### 3.10 Supabase Integration (`supabase/`)

**`client.py`** — Typed fetch helpers with pagination:
- `fetch_documents()` — paginate `agora_documents` table
- `fetch_segments(doc_ids)` — filter by document ID list
- `fetch_fulltext(agora_id)` — download from Storage bucket `fulltexts/agora/{agora_id}.txt`
- `expand_taxonomy_tags(row)` — convert `TEXT[]` array → flat boolean-style keys (for community detector compatibility)

**`sync.py`** — Zenodo → Supabase pipeline:
1. Download ZIP from Zenodo (record ID in config)
2. Extract and normalize CSVs
3. Transform taxonomy columns → `TEXT[]` arrays
4. Upsert into Supabase in 500-row batches
5. Upload fulltext files to Storage

---

## 4. Key Coding Principles

### 4.1 Deterministic-First, LLM-Last

Three of four pipeline phases use no LLM at all. The LLM (Claude Haiku) is only invoked in Phase 3 for entity extraction — where structured pattern matching would fail. This minimizes cost, latency, and non-determinism.

### 4.2 Centralized Configuration

All numeric thresholds, model names, and path constants live in `config.py`. No magic numbers anywhere in agent or pipeline code. This enables tuning without touching logic.

### 4.3 Resumable via Checkpointing

Every document processed (success or failure) is recorded in `ner_checkpoint.jsonl`. On re-run, the agent skips checkpointed docs. This means the pipeline can be interrupted at any time with zero lost work.

### 4.4 Community-Aware Stateful Memory

Each Louvain community maintains persistent JSON memory across document runs. The memory injects:
- Accumulated entity roster (top-N entities per type, by mention count)
- Disambiguation rules learned from earlier docs in the community
- Structural parsing patterns (capped at 7 active rules to prevent prompt bloat)

This reduces redundant extraction and improves cross-document consistency — later docs in a community benefit from context extracted from earlier, higher-centrality docs.

### 4.5 Centrality-Ordered Processing

Documents are processed within each community in descending order of centrality (weighted degree in the community subgraph). High-centrality docs are most representative — processing them first "seeds" the community memory with the most relevant entities.

### 4.6 Multi-Signal Similarity (Redundant Evidence)

Community detection uses three independent similarity signals:
- **Taxonomy Jaccard (50%)** — topical alignment via binary legislative tags
- **TF-IDF Cosine (25%)** — surface-level text similarity on summaries
- **Dense Cosine (20%)** — latent semantic similarity via sentence-transformers

No single signal dominates. If one fails or is noisy for a subset of documents, the others compensate. The weighted combination is tunable in `config.py`.

### 4.7 Rate Limiting as First-Class Constraint

`ANTHROPIC_RATE_DELAY_SECONDS = 0.65` is enforced after every LLM call in `llm_client.py`. This is documented explicitly as non-negotiable: violating it causes silent NER corruption (model returns data but pipeline becomes unreliable). The sleep is embedded in the shared client, not left to callers.

### 4.8 Two-Pass JSON Parsing

Every Claude response goes through:
1. Direct `json.loads()` — fast path
2. On failure: re-prompt with strict "Return ONLY valid JSON starting with `{`" prefix → retry parse

This handles the real-world case where models occasionally output markdown code fences or explanatory text around JSON.

### 4.9 Schema Validation Before Storage

Every NER output is validated for the presence of all 5 required entity type keys before being written to `entities.jsonl`. This prevents partially-formed records from polluting downstream graph assembly.

### 4.10 Graph Layering (Multiplex)

Rather than one monolithic graph, AGORA builds three independent layers assembled into a multiplex. Each layer supports independent analytical queries (Who sponsors what? What communities cluster together? What entities appear in what documents?) as well as joint multi-layer analysis.

---

## 5. Data Flow Summary

### Input Sources

| Source | Rows | Description |
|---|---|---|
| `documents.csv` | 622 | Congress-only documents filtered from ~11k AGORA corpus |
| `segments.csv` | 4,087 | Text segments per document |
| `fulltext/` | 619 files | Plain text of each bill |
| `agora_with_sponsors.csv` | varies | Bioguide sponsor data per document |

### Output Artifacts

| Phase | Artifacts |
|---|---|
| Phase 0 | `nodes.csv`, `edges.csv`, `stats.json` |
| Phase 1 | `sponsor_nodes.csv`, `sponsor_edges.csv`, `doc_sponsor_matrix.json` |
| Phase 2 | `communities.json` (243 communities, 535 docs) |
| Phase 3 | `entities.jsonl`, `memory/*.json`, `ner_checkpoint.jsonl`, `ner_coverage_report.json` |
| Phase 4 | `layer_1_sponsor.graphml`, `layer_2_community.graphml`, `layer_3_entity.graphml`, `multiplex_combined.graphml` |

---

## 6. CLI Entry Points

```bash
# Build base knowledge graph
python3 -m pipeline.cli build-knowledge-graph \
  --documents-csv knowledge_graph/data/documents.csv \
  --segments-csv knowledge_graph/data/segments.csv

# Run community detection
python3 -m pipeline.cli detect-communities \
  --sponsors-csv knowledge_graph/data/agora_with_sponsors.csv

# Calibration run: NER on 2 docs in community 001
python3 -m pipeline.cli build-multiplex-graph \
  --agents ner --community community:001 --limit 2

# Full NER + multiplex graph assembly
python3 -m pipeline.cli build-multiplex-graph --agents all

# Query neighborhood of a document node
python3 -m pipeline.cli query-neighborhood \
  --seed-node-id document:1234 --max-hops 2

# Sync to Supabase
python3 -m pipeline.cli sync-supabase --tables documents,segments
```

---

## 7. Technologies Used

| Category | Technology |
|---|---|
| LLM | Anthropic Claude Haiku 4.5 (via `anthropic` SDK) |
| Graph | NetworkX (construction, Louvain clustering, GraphML export) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| TF-IDF | scikit-learn `TfidfVectorizer` |
| Web | Flask |
| Cloud DB | Supabase (PostgreSQL + Storage) |
| Data | pandas, CSV/JSONL |
| CLI | argparse (via `cli.py`) |
| Language | Python 3.9+ |

---

## 8. Limitations and Future Work

### Current Limitations
- **Scope:** Congress-only subset (622 docs of ~11k total AGORA corpus)
- **Entity linking:** No disambiguation to external knowledge bases (Wikidata, etc.)
- **Co-sponsors:** Only primary sponsor tracked in Phase 1
- **Relationship extraction:** Entity-to-entity edges not yet populated in Phase 3

### Planned Extensions
- Cosponsor relationship graph (Phase 1 extension)
- Full corpus expansion (lift from 622 to ~11k docs)
- Temporal analysis (community/entity evolution across congresses)
- Interactive graph visualization UI
- Federated Supabase sync (keep local and cloud in sync)
