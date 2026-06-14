# NER Agent — Plan & Architecture

> **Canonical counts, paths, and commands:** See [`FACTS.md`](FACTS.md) — do not duplicate those numbers here.

**Status:** Phase 3 Complete
**Last Updated:** 2026-03-18
**Entry Point:** `pipeline/agents/ner_agent.py`
**CLI:** `python3 -m pipeline.cli build-multiplex-graph --agents ner`

---

## Overview

The NER agent extracts named entities from U.S. federal legislative documents (AGORA corpus).
It is **Phase 3** of the multiplex knowledge graph pipeline:

```
Phase 1: Sponsor Graph  →  sponsor_nodes.csv, sponsor_edges.csv     ✅ Done
Phase 2: Community Detection  →  communities.json (243 communities)  ✅ Done
Phase 3: NER Agent  →  entities.jsonl, memory/, checkpoints/         ✅ Done (531 docs, macro_f1 ~0.17)
Phase 4: Graph Builder  →  Layer 3 entity graph (GraphML)            ⬜ Pending
```

---

## Entity Types

| Type | Fields | Graph Relation |
|---|---|---|
| **organizations** | name, acronym, context | `MENTIONS_ORG` |
| **offices** | name, parent_org, context | `MENTIONS_OFFICE` |
| **roles** | title, org, context | `INVOLVES_ROLE` |
| **legislation_refs** | name, citation, ref_type (cites/amends/enacts/repeals), context | `REFERENCES_LEGISLATION` |
| **named_docs** | name, doc_type (strategy/report/plan/initiative/program), owner_org, context | `INVOLVES_NAMED_DOC` |

Plus per-chunk metadata: `disambiguation_updates`, `new_parsing_rule`, `oddity`.

---

## Architecture

### Processing Flow

```
For each community (sorted by size):
  Load community memory (or create fresh)
  For each document (sorted by centrality, highest first):
    Skip if already checkpointed
    Load fulltext from data/fulltext/{agora_id}.txt
    Chunk text at SEC./SECTION. boundaries (max 6000 chars)
    For each chunk:
      Build prompt = system prompt + community memory context + user prompt
      Call Claude Haiku 4.5 → JSON entity extraction
      Filter generic terms, validate schema
      Track in-progress entities for cross-chunk context
    Merge chunk results (deduplicate by name)
    Append EntityRecord to entities.jsonl
    Update community memory (entity roster, disambiguation, parsing rules)
    Save checkpoint
```

### Key Design Decisions

1. **Community-aware memory** — entities accumulate within a community, providing disambiguation context (e.g., "the Department" → "Department of Defense" in a defense cluster)
2. **Centrality-first ordering** — most-connected docs processed first to seed memory with key entities early
3. **Section-boundary chunking** — respects legislative structure (`SEC. 1.`, `SEC. 2.`) rather than arbitrary splits
4. **Incremental checkpointing** — every doc is checkpointed; safe to interrupt and resume
5. **Rate limiting** — 0.65s delay between API calls (~92 RPM). **DO NOT BYPASS.**

### Memory System

Per-community JSON files in `pipeline/agents/memory/{community_id}_memory.json`:

- **Entity roster** — all seen entities with mention counts, capped at top-N per type for prompt injection
- **Disambiguation rules** — resolved ambiguous references ("the Director" → "Director of OSTP")
- **Parsing rules** — structural patterns observed (max 7 active, older ones archived)
- **Oddities** — unusual document structures flagged for review

**Prompt context limits** (from `config.py`):
| Type | Top-N injected |
|---|---|
| organizations | 20 |
| offices | 15 |
| roles | 10 |
| legislation_refs | 15 |
| named_docs | 10 |

---

## Configuration

All settings in `pipeline/config.py`:

```python
NER_CHUNK_SIZE = 6000              # max chars per section chunk
NER_MAX_PARSING_RULES = 7          # max active rules in prompt
NER_MEMORY_TOP_N = {               # context injection limits per entity type
    "organizations": 20,
    "offices": 15,
    "roles": 10,
    "legislation_refs": 15,
    "named_docs": 10,
}
ANTHROPIC_MODEL_BULK = "claude-haiku-4-5-20251001"
ANTHROPIC_RATE_DELAY_SECONDS = 0.65
ANTHROPIC_MAX_RETRIES = 3
```

---

## Data Paths

- **Fulltext source:** `data/fulltext/` (1,031 .txt files)
- **Communities input:** `pipeline/agents/output/communities.json` (243 communities, 535 docs)
- **NER output:** `pipeline/agents/output/entities.jsonl`
- **Errors:** `pipeline/agents/output/ner_errors.jsonl`
- **Memory:** `pipeline/agents/memory/{community_id}_memory.json`
- **Checkpoints:** `pipeline/agents/checkpoints/ner_checkpoint.jsonl`
- **Coverage report:** `pipeline/agents/output/ner_coverage_report.json`

---

## Running the NER Agent

### Prerequisites
1. `ANTHROPIC_API_KEY` set in `.env` at repo root
2. Fulltext files present in `data/fulltext/` (1,031 files available)
3. `communities.json` exists in `pipeline/agents/output/` (Phase 2 complete)

### Calibration Run (recommended first)
```bash
# Process 2 docs from one community to verify output quality
python3 -m pipeline.cli build-multiplex-graph \
  --agents ner \
  --fulltext-dir data/fulltext \
  --community <community_id> \
  --limit 2
```

### Full Run
```bash
python3 -m pipeline.cli build-multiplex-graph \
  --agents ner \
  --fulltext-dir data/fulltext
```

### Resume After Interruption
Same command — checkpointed docs are automatically skipped.

### Coverage Report
After a run, call `generate_coverage_report()` from `ner_agent.py` to get aggregated stats.

---

## Outputs

### entities.jsonl (primary output)
One JSON object per line, per document:
```json
{
  "agora_id": "1234",
  "organizations": [{"name": "DARPA", "acronym": "DARPA", "context": "..."}],
  "offices": [{"name": "Office of the CTO", "parent_org": "DOD", "context": "..."}],
  "roles": [{"title": "Secretary of Defense", "org": "DOD", "context": "..."}],
  "legislation_refs": [{"name": "AI Act of 2024", "citation": "...", "ref_type": "cites", "context": "..."}],
  "named_docs": [{"name": "National AI Strategy", "doc_type": "strategy", "owner_org": "OSTP", "context": "..."}],
  "disambiguation_updates": {"the Department": "Department of Defense"},
  "new_parsing_rule": null,
  "oddity": null,
  "model": "claude-haiku-4-5-20251001",
  "prompt_tokens": 4200,
  "completion_tokens": 850,
  "chunks_processed": 3,
  "extracted_at": "2026-03-18T..."
}
```

### Graph Layer 3 (downstream)
The graph builder reads `entities.jsonl` and creates:
- **Nodes:** `org:department_of_defense`, `role:secretary_of_defense`, etc.
- **Edges:** `doc:1234 --MENTIONS_ORG--> org:department_of_defense`

---

## Safeguards

- **Rate delay:** 0.65s enforced in `llm_client.py` — violating causes silent NER corruption
- **Generic filter:** Terms <5 chars or matching known stems ("federal agencies", "the committee") are dropped
- **Canonical lookup:** Common acronyms (DOD, NIST, DARPA, etc.) mapped to full names for deduplication
- **Parsing rule cap:** Max 7 active rules; older rules archived to prevent prompt bloat
- **Two-pass JSON parsing:** If first parse fails, retries with strict "return only JSON" prefix
- **Validation:** Output must contain all 5 required entity type keys with list values
