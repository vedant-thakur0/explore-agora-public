# AGORA Notebooks

Exploration and analysis notebooks. Rendered outputs and figure artifacts in `notebooks/outputs/` are committed and kept up to date — you can read the latest results without re-running. To refresh them after a pipeline change, run `python3 -m pipeline.cli reports --execute`.

## Setup

```bash
pip install -r ../requirements.txt
python3 -m ipykernel install --user --name agora --display-name "AGORA"
jupyter lab
```

Notebooks expect the repo root as the working directory and read from `data/` and the pipeline modules under `pipeline/`.

## Notebooks

| Notebook | Purpose |
|---|---|
| `01_sponsor_profiling.ipynb` | Sponsor-level activity profiles and party/committee breakdowns |
| `02_policy_networks.ipynb` | Co-sponsorship and topic networks |
| `03_coalitions.ipynb` | Community detection over the cosponsor graph |
| `04_taxonomy.ipynb` | AI policy taxonomy exploration |
| `agora_data_explorer.ipynb` | Browse the AGORA dataset slice |
| `congress_api_explorer.ipynb` | Examples of Congress.gov API queries |
| `graph_exploration.ipynb` | Interactive knowledge graph exploration |
| `pipeline_demos.ipynb` | End-to-end pipeline walkthrough |

## Data dependencies

Most notebooks read from `data/documents.csv` and `data/segments.csv`. See [`../knowledge_graph/README.md`](../knowledge_graph/README.md) for the schema.

Some cells call the Congress.gov API and require `CONGRESS_API_KEY` set in the repo-root `.env`.
