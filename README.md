# AGORA

> **Canonical counts, paths, and commands:** See [`FACTS.md`](FACTS.md) — do not duplicate those numbers here.

A computational toolkit for AI policy research. Discovers, ranks, and analyzes AI-related legislation from U.S. Congress using a multi-stage pipeline: ingestion → ranking → NER → knowledge graph.

Built on top of the [AGORA dataset](https://zenodo.org/records/15692257) (Zenodo). The toolkit adds: agent-driven NER and entity normalization, cosponsor and coalition graph construction, document similarity matching, and a Flask review UI.

## Who is this for?

**Analysts / non-technical users:** Start with [`GETTING_STARTED.md`](GETTING_STARTED.md). Reports are generated locally via `/generate-reports` and land in `reports/generated/<date>/index.html` — a fresh clone will not contain one yet.

**Developers:** Continue below with this README, [`CLAUDE.md`](CLAUDE.md), and [`FILETREE.md`](FILETREE.md).

## Components

- **`pipeline/`** — Core Python pipeline (ingestion, ranking, agents, knowledge graph)
- **`pipeline/web/`** — Flask annotation UI for human review
- **`pipeline/supabase/`** — Optional sync layer for hosted review workflows
- **`pipeline/FEC/`** — Federal Election Commission ingestion experiments (experimental placeholder, not wired into the main pipeline; see [`pipeline/FEC/README.md`](pipeline/FEC/README.md))
- **`knowledge_graph/`** — Data schema, cosponsor layer documentation, filtered datasets
- **`notebooks/`** — Jupyter notebooks for exploration and analysis

## Install

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file at the repo root with the required keys:

```
CONGRESS_API_KEY=<your-congress-gov-key>
ANTHROPIC_API_KEY=<your-anthropic-key>

# Optional (only if using supabase sync)
SUPABASE_URL=<your-project-url>
SUPABASE_KEY=<your-anon-or-service-key>
```

- Congress.gov API keys: https://api.congress.gov/sign-up/
- Anthropic API keys: https://console.anthropic.com/

## Quickstart

```bash
# List available pipeline commands
python3 -m pipeline.cli --help

# Run the document ranker over a session
python3 -m pipeline.cli rank --session <session-id>

# Launch the annotation web UI
python3 -m pipeline.web.app
```

## Documentation

- **Architecture and conventions:** [`CLAUDE.md`](CLAUDE.md)
- **File tree:** [`FILETREE.md`](FILETREE.md)
- **NER agent design:** [`NER_AGENT.md`](NER_AGENT.md)
- **Knowledge graph schema:** [`knowledge_graph/README.md`](knowledge_graph/README.md)
- **Cosponsor layers:** [`knowledge_graph/COSPONSOR_LAYERS.md`](knowledge_graph/COSPONSOR_LAYERS.md)
- **Tuning runbook:** [`pipeline/TUNING_RUNBOOK.md`](pipeline/TUNING_RUNBOOK.md)
- **Cosponsor analysis quickstart:** [`COSPONSOR_ANALYSIS_QUICKSTART.md`](COSPONSOR_ANALYSIS_QUICKSTART.md)

## Data licensing

Derived datasets in `knowledge_graph/graph_data/` are filtered subsets of the AGORA Zenodo corpus. See [`DATA_LICENSE.md`](DATA_LICENSE.md) for attribution and licensing terms of source data.

## License

Code is released under the [MIT License](LICENSE).

## Citation

If you use this toolkit, please cite both the underlying AGORA dataset and this repository.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).
