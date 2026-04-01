# Cosponsor Graph Layers

## Overview

The knowledge graph now includes two additional layers (1b and 1.75) that track cosponsors of congressional documents, extending the primary sponsor layer (Layer 1).

### Data Sources

- **`agora_cosponsors_long.csv`** — One row per (AGORA ID, cosponsor). Contains bioguide ID, party, state, district, sponsorship date, original status, and withdrawal tracking.
- **`agora_comprehensive_data_with_cosponsor_lists.csv`** — Enriched documents CSV (new primary sponsor input) with cosponsor counts and JSON-encoded cosponsor lists.

### Key Statistics (as of 2026-03-31)

| Layer | Node Type | Count | Edge Type | Count | Purpose |
|---|---|---|---|---|---|
| **1b** | Cosponsor | 520 | COSPONSORED_BY | 3,460 | Active cosponsors linked to documents |
| **1b** | — | — | SHARES_COSPONSOR | 20,250 | Document pairs sharing an active cosponsor |
| **1.75** | WithdrawnCosponsor | 2 | WITHDREW_COSPONSOR | 2 | Cosponsors who withdrew their names |

## Layer 1b: Active Cosponsors

**Purpose**: Represent the current cosponsorship network across documents.

**Nodes**:
- **Cosponsor** nodes (`sponsor:<bioguide_id>`) — reuse the same `sponsor:` namespace as primary sponsors, but marked `node_type="Cosponsor"` to distinguish them
- **Document** nodes (`document:<agora_id>`) — documents that have active cosponsors

**Edges**:

1. **`COSPONSORED_BY`** (document → cosponsor)
   - Attributes: `is_original` (bool), `layer="1b"`
   - Marks original vs. subsequent cosponsors

2. **`SHARES_COSPONSOR`** (document ↔ document)
   - Attributes: `cosponsor_bioguide`, `layer="1b"`
   - Derived: documents that share at least one active cosponsor
   - Weight signal for community detection (already integrated via `cosponsor_jaccard` in `config.py`)

**Output files**:
- `pipeline/agents/output/cosponsor_nodes.csv` — 520 records
- `pipeline/agents/output/cosponsor_edges.csv` — 23,710 records (3,460 COSPONSORED_BY + 20,250 SHARES_COSPONSOR)
- `pipeline/multiplex_graph/layer_1b_cosponsor.graphml` — GraphML export

## Layer 1.75: Withdrawn Cosponsors

**Purpose**: Track cosponsors who have withdrawn their support from specific documents.

**Nodes**:
- **WithdrawnCosponsor** nodes (`sponsor:<bioguide_id>`) — same bioguide as Layer 1b, but distinct node type
- **Document** nodes (`document:<agora_id>`) — documents with withdrawn cosponsors

**Edges**:

1. **`WITHDREW_COSPONSOR`** (document → withdrawn cosponsor)
   - Attributes: `withdrawn_date` (ISO 8601), `layer="1.75"`
   - Records when the cosponsor withdrew

**Output files**:
- `pipeline/agents/output/withdrawn_cosponsor_nodes.csv` — 2 records
- `pipeline/agents/output/withdrawn_cosponsor_edges.csv` — 2 records
- `pipeline/multiplex_graph/layer_175_withdrawn_cosponsor.graphml` — GraphML export

## Building the Cosponsor Layers

### Run cosponsor graph build only

```bash
python3 -m pipeline.cli build-multiplex-graph \
  --sponsors-csv knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv \
  --cosponsors-csv knowledge_graph/graph_data/agora_cosponsors_long.csv \
  --agents cosponsor
```

### Run sponsor + cosponsor phases

```bash
python3 -m pipeline.cli build-multiplex-graph \
  --sponsors-csv knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv \
  --cosponsors-csv knowledge_graph/graph_data/agora_cosponsors_long.csv \
  --agents sponsor
```

### Run full multiplex build (all phases)

```bash
python3 -m pipeline.cli build-multiplex-graph \
  --sponsors-csv knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv \
  --cosponsors-csv knowledge_graph/graph_data/agora_cosponsors_long.csv \
  --agents all
```

## Implementation Details

### Code locations

| Component | File | Function |
|---|---|---|
| Cosponsor graph builder | `pipeline/agents/sponsor_graph.py` | `build_cosponsor_graph()`, `run_cosponsor()` |
| Layer 1b assembly | `pipeline/agents/graph_builder.py` | `build_layer1b_cosponsor()` |
| Layer 1.75 assembly | `pipeline/agents/graph_builder.py` | `build_layer175_withdrawn_cosponsor()` |
| CLI integration | `pipeline/cli.py` | `cmd_build_multiplex_graph()` |
| Config paths | `pipeline/config.py` | `COSPONSOR_CSV_PATH`, `SPONSORS_CSV_PATH` |

### Reused patterns

- `_parse_chamber()`, `_parse_name_parts()`, `_clean_district()` — existing sponsor parsing helpers
- `SponsorRecord` data model — reused for all cosponsor nodes
- Graph assembly pattern — mirrors `build_layer1_sponsor()` for consistency

### Visualization

A sample visualization script is provided for manual inspection:

```bash
python3 pipeline/agents/viz_cosponsor_sample.py
```

This generates `pipeline/agents/output/cosponsor_sample_2.png` showing Document 2 (NDAA FY2022 §226) with:
- **Blue** — the document
- **Orange** — primary sponsor (Sen. Warner)
- **Green** — active cosponsors (Sens. Rubio, Padilla)
- **Red** (if any) — withdrawn cosponsors

## Integration with Community Detection

The `cosponsor_jaccard` weight (0.05 in `config.py::COMMUNITY_SIMILARITY_WEIGHTS`) already incorporates cosponsorship similarity in the Louvain clustering. The new Layer 1b edges support this weighting.

## Notes

- **Node namespace**: Cosponsor nodes reuse the `sponsor:` prefix (same as primary sponsors) to maintain a unified sponsor identity space. The node type attribute (`"Cosponsor"` vs. `"Sponsor"`) distinguishes them in graph analysis.
- **Layer numbering**: Layers 1b and 1.75 represent subdivisions of the sponsor layer, inserted before community (Layer 2) and entity (Layer 3) layers.
- **Data freshness**: Based on Congress.gov API data pulled 2026-03-13 (per `bill_sponsors_README.md`).
- **Withdrawn tracking**: Only 2 withdrawals in the dataset, but captured separately for future analysis of cosponsor commitment changes.

## Related Files

- `knowledge_graph/graph_data/agora_cosponsors_long.csv` — raw cosponsor data
- `knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv` — primary sponsors with cosponsor metadata
- `bill_sponsors_README.md` — data provenance and processing details
