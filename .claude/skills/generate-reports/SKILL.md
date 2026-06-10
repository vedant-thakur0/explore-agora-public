---
name: generate-reports
description: Generate an HTML research report bundle from the current AGORA dataset and knowledge graph. Safe to run — no external API calls, no data modification. For non-technical analysts who need a shareable output of the latest analysis.
---

# Skill: generate-reports

**Audience:** Non-technical analysts who want a browsable HTML summary of the current AGORA data and graph state.

## What this does

Runs the AGORA report generator, which reads locally-cached data and knowledge graph outputs and produces a self-contained HTML bundle in `reports/generated/<YYYY-MM-DD>/`.

## Command

```
python3 -m pipeline.cli reports
```

Run from the repo root (`/Users/vthakur/Documents/auto/agora`).

## Expected output

The command prints the path to the generated bundle when it finishes. Look for a line like:

```
Report written to: reports/generated/2026-06-10/index.html
```

Open `index.html` in any browser to view the full report. Ask if you would like me to open it for you.

## Runtime

Typically under 2 minutes. It reads from already-processed artifacts — it does not re-run any pipeline steps or call any external APIs.

## Optional flag

`--execute` re-runs the analysis notebooks so the report pages carry freshly computed figures. It works but takes roughly 30 minutes — tell the user about the wait and confirm before running it (use `--timeout 900`). Without `--execute`, the bundle reuses the most recent notebook renders and finishes in under 2 minutes.

## Explaining results to stakeholders

- The HTML bundle is fully self-contained — you can email or share it without any extra files.
- Charts and tables inside the report reflect the last time the full pipeline was run. If data looks stale, see the `pipeline-status` skill to check when the pipeline last ran.
- Each section of the report corresponds to a pipeline stage (community detection, NER entities, graph topology).

## On failure

Do not attempt to debug the error yourself. Copy the full terminal output (including any traceback) and send it to the maintainer, Vedant (vedantt2210@gmail.com), with a note about what date and time you ran it.
