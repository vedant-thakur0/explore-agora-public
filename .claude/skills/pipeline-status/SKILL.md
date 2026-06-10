---
name: pipeline-status
description: Read-only summary of the AGORA pipeline state. Shows latest run manifests, available agent outputs, and generated reports. No data is modified or deleted. Safe for non-technical analysts to run at any time.
---

# Skill: pipeline-status

**Audience:** Non-technical analysts who want to understand the current state of the system without touching anything.

## What this does

Inspects three locations and gives a plain-English summary:

1. **`pipeline/runs/`** — timestamped manifests of every pipeline run (audit trail, never modified)
2. **`pipeline/agents/output/`** — artifacts produced by pipeline agents (communities, NER entities, graph files)
3. **`reports/generated/`** — HTML report bundles previously generated

Nothing is run, modified, or deleted. This is purely read-only.

## How to run this skill

Ask Claude: "What is the pipeline status?" or "Run pipeline-status."

Claude will:
1. List files in `pipeline/runs/` and report the most recent manifest with its timestamp.
2. List files in `pipeline/agents/output/` and summarize what is present (e.g., communities detected, entities found, graph files ready).
3. List directories in `reports/generated/` and report the latest report bundle date.

## Commands used (read-only, no side effects)

```bash
[ -d pipeline/runs ] && ls -lt pipeline/runs/ || echo "No run manifests yet (pipeline/runs/ is created on first pipeline run)"
ls pipeline/agents/output/
ls reports/generated/
```

Note: `pipeline/runs/` may not exist until the pipeline has been run at least once in this environment. A missing directory means "never run here" — it is not an error.

## Explaining results in plain English

- **Run manifests:** Each file in `pipeline/runs/` records what was run and when. The most recent file tells you when the pipeline was last executed. If the directory is empty or does not exist yet, the pipeline has never been run in this environment.
- **Agent outputs:** These are the processed results — community groupings, named entities extracted from legislation, and the graph structure. If a file is missing, that pipeline stage has not been run yet.
- **Report bundles:** Each dated folder in `reports/generated/` corresponds to one report generation. If the folder is empty or missing, reports have not been generated yet.

## What "stale" looks like

If the most recent run manifest is more than a few weeks old and the underlying data has changed, the current outputs may not reflect the latest dataset. In that case, contact the maintainer (Vedant) about re-running the pipeline.

## On failure

If any listing command fails with a permissions error or unexpected output, capture the message and contact Vedant (vedantt2210@gmail.com).
