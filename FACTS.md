# FACTS.md — AGORA Canonical Reference

**This is the single source of truth for counts, paths, and commands in this repo.**
Other docs point here instead of duplicating these numbers. Do not update counts elsewhere without updating this file first.

---

## CLI Invocation

| Form | Works? | Notes |
|---|---|---|
| `python3 -m pipeline.cli <command>` | ✅ canonical | Run from the repository root. |

Run `python3 -m pipeline.cli --help` from the repository root to list available commands.

---

## Corpus Counts

| Scope | Asset | Count |
|---|---|---|
| Full repo corpus | `data/documents.csv` (repo root) | **1,035** rows |
| Congress-only filter | Authority = "United States Congress" | **622** documents |
| Congress docs with retrieved fulltext | Congress docs that have a `.txt` file | **619** (3 of 622 missing) |
| Retrieved plaintext files | `data/fulltext/` (repo root) | **1,031** `.txt` files |
| Community detection output | `communities.json` | **243** communities / **535** docs |

Note: there is a single `documents.csv`, at the repo root (`data/documents.csv`, 1,035 rows). The "622 Congress" figure is a **filter result** (Authority = "United States Congress"), not a separate file on disk. `knowledge_graph/graph_data/` holds derived sponsor/cosponsor CSVs, not a filtered `documents.csv`.

---

## Fulltext File Convention

| Property | Value |
|---|---|
| Directory | `data/fulltext/` (from repo root) |
| Filename pattern | `<agora_id>.txt` |
| Total files present | **1,031** |
| Join key | AGORA ID → `data/fulltext/<agora_id>.txt` → `segments.csv` Document ID |

---

## Cosponsor Layer Stats

Source: `knowledge_graph/COSPONSOR_LAYERS.md`

| Layer | Description | Nodes | COSPONSORED_BY edges | SHARES_COSPONSOR edges |
|---|---|---|---|---|
| Layer 1b | Active cosponsor relationships | **520** cosponsor nodes | **3,460** | **20,250** |
| Layer 1.75 | Withdrawn cosponsor relationships | — | **2** withdrawn | — |

---

## NER Status

| Property | Value |
|---|---|
| Phase | **3 — COMPLETE** |
| Output file | `agents/output/entities.jsonl` |
| Documents processed | **531** |
| Eval report | `agents/output/ner_eval_report.json` — macro_f1 ≈ **0.17** |
| Memory files | **239** in `agents/memory/` when populated — generated at runtime, **gitignored** (not in a fresh clone) |
| Checkpoints | `agents/checkpoints/` — generated at runtime, **gitignored** (not in a fresh clone) |

---

## Pipeline Phase Status

| Phase | Name | Status | Key Output |
|---|---|---|---|
| 1 | Sponsor Graph | Done | `sponsor_nodes.csv`, `sponsor_edges.csv` |
| 2 | Community Detection | Done | `communities.json` (243 communities) |
| 3 | NER Agent | Done | `entities.jsonl` (531 docs, macro_f1 ~0.17) |
| 4 | Entity Graph Layer | Pending | Layer 3 entity graph (GraphML) |

---

## Key Paths

| Asset | Path (from repo root) |
|---|---|
| Full corpus CSV (1,035 rows) | `data/documents.csv` |
| Congress-only docs (622) | filter of `data/documents.csv`, not a separate file |
| Fulltext directory | `data/fulltext/` |
| Segments CSV | `data/segments.csv` |
| Sponsor/cosponsor CSVs | `knowledge_graph/graph_data/` |
| Communities JSON | `pipeline/agents/output/communities.json` |
| NER entities | `pipeline/agents/output/entities.jsonl` |
| NER eval report | `pipeline/agents/output/ner_eval_report.json` |
| Agent memory | `pipeline/agents/memory/` (runtime-generated, gitignored) |
| Agent checkpoints | `pipeline/agents/checkpoints/` (runtime-generated, gitignored) |
| Pipeline config | `pipeline/config.py` (all path constants) |
