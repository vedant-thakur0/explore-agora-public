# AGORA Pipeline

Core Python pipeline for building and analyzing the AGORA knowledge graph of AI-related
U.S. legislation. Run as a module from the repository root:

```bash
python3 -m pipeline.cli --help    # list all commands
```

All path constants and LLM/threshold settings live in [`config.py`](config.py); data classes are in
[`models.py`](models.py). Run `--help` on any subcommand for its arguments.

## Pipeline stages

The corpus CSVs in `data/` feed a multi-stage build:

```bash
# 1. Build the knowledge graph (nodes/edges) from the AGORA CSV sources
python3 -m pipeline.cli build-knowledge-graph

# 2. Detect document communities via Louvain clustering
python3 -m pipeline.cli detect-communities

# 3. Assemble the multiplex graph (sponsor / cosponsor / entity layers) from agent outputs
python3 -m pipeline.cli build-multiplex-graph

# 4. Build a self-contained dated HTML report bundle
python3 -m pipeline.cli reports
```

## Other commands

| Command | Purpose |
|---|---|
| `query-neighborhood --seed-node-id <id>` | Query the neighborhood around a seed node in a graph export |
| `eval-ner` | Evaluate NER output against the manual annotations |
| `seed-registry` | Seed or rebuild the global canonical entity registry |
| `canonicalize` | Flag bare entity aliases in the review queue with resolution context |
| `sync-supabase` | Download the latest Zenodo release and upsert into Supabase (writes to a live DB) |
| `sync-ner-entities` | Sync the NER entity dictionary and document-entity mappings to Supabase |

`sync-supabase` and `sync-ner-entities` need Supabase credentials in `.env` and write to a hosted
database (see the repo-root `README.md` for configuration). Pass `--dry-run` to validate without writing.

## Components

- **`agents/`** — NER and graph-construction agents (see [`../NER_AGENT.md`](../NER_AGENT.md)).
- **`web/`** — Flask annotation/review UI: `python3 -m pipeline.web.app` (see [`web/README.md`](web/README.md)).
- **`supabase/`** — Optional sync layer for hosted review workflows.
- **`multiplex_graph/`, `graph/`** — Generated graph exports (GraphML, node/edge CSVs, stats).
- **`tests/`** — Unit tests: `python3 -m pytest pipeline/tests` (see [`../CONTRIBUTING.md`](../CONTRIBUTING.md)).

## Reference

- Knowledge-graph schema and join keys: [`../knowledge_graph/README.md`](../knowledge_graph/README.md)
- Cosponsor layers: [`../knowledge_graph/COSPONSOR_LAYERS.md`](../knowledge_graph/COSPONSOR_LAYERS.md)
- Canonical counts, paths, and commands: [`../FACTS.md`](../FACTS.md)
