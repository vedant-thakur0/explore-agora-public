---
name: run-ranking
description: Runs the AGORA document-ranking pipeline (build-multiplex-graph). COSTS MONEY — calls the Anthropic API for NER over legislative text. Requires explicit user confirmation before running. For non-technical analysts who need to re-index and re-rank the document graph after new data has been loaded.
---

# Skill: run-ranking

**Audience:** Non-technical analysts who have been told by the maintainer that a re-ranking run is needed.

## IMPORTANT: This command calls external APIs and costs money

Before running, Claude will ask you to confirm. The pipeline makes calls to:

- **Anthropic API** — for Named Entity Recognition (NER) over legislative documents. Each run processes hundreds of documents and consumes real API credits.

Do not run this unless you have budget approval or have confirmed with the maintainer (Vedant) that a run is needed.

## What this does

Runs the full multiplex graph pipeline, which includes:
1. Building sponsor and cosponsor graphs from CSV data
2. Detecting legislative communities (Louvain clustering — local, no API cost)
3. Running NER over community documents using Claude (Anthropic API — this is the costly step)
4. Assembling the multiplex knowledge graph

Outputs are written to `pipeline/agents/output/` and the multiplex graph directory.

## Command

```
python3 -m pipeline.cli build-multiplex-graph
```

Run from the repo root. Default inputs are picked up from `pipeline/config.py`.

### Common options

| Flag | Purpose |
|---|---|
| `--agents ner` | Run only the NER phase (Anthropic API calls) |
| `--agents community` | Run only community detection (no API cost) |
| `--limit N` | Process only N documents per community (useful for calibration) |
| `--community <id>` | Filter NER to a single community (reduces API cost) |

For a full run with all defaults:
```
python3 -m pipeline.cli build-multiplex-graph
```

## Expected runtime

- Community detection alone: 1–5 minutes
- Full run with NER: 30–90 minutes depending on corpus size and API rate limits. The pipeline respects `ANTHROPIC_RATE_DELAY_SECONDS` between calls.

## Before running — Claude will ask you to confirm

Claude will present this prompt before executing:

> "This command calls the Anthropic API to run NER over legislative documents, which will consume API credits. Are you sure you want to proceed? (yes/no)"

Type "yes" to continue. Any other response cancels the run.

## Explaining results in plain English

After the run completes, the command prints a JSON summary. Key fields:
- `nodes` / `edges`: size of the assembled graph
- `layers`: which graph layers were built (sponsor, cosponsor, ner, etc.)
- Check `pipeline/agents/output/entities.jsonl` for raw NER output
- Check `pipeline/agents/output/communities.json` for community membership

## On failure

Do not attempt to debug. Copy the full terminal output and contact Vedant (vedantt2210@gmail.com). Common issues: missing API key in environment, missing input CSV files, rate limit exhaustion.
