# MAINTAINER.md — AGORA Operations

> **Canonical counts, paths, and commands:** See [`FACTS.md`](../FACTS.md) — do not duplicate those numbers here.

This document covers operational tasks for repository maintainers and analysts.

## Provisioning analysts

Each analyst receives:
- A copy of the repository folder (checked into your team's source control or shared directly)
- A `.env` file handed over separately (never committed, never posted in shared channels)

The `.env` file must contain the following keys (see ../README.md Configuration section for where to obtain them):
- `CONGRESS_API_KEY` — API key from https://api.congress.gov/sign-up/
- `ANTHROPIC_API_KEY` — API key from https://console.anthropic.com/

Optional keys (only if using Supabase sync for hosted review workflows):
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_KEY` — Supabase anon or service role key

**Key rotation and revocation:** When an analyst leaves the team, revoke or rotate all API keys associated with their `.env` file to prevent unauthorized access.

## Regenerating and publishing reports

**Standard workflow:**
```bash
python3 -m pipeline.cli reports
```

This runs the full report generation pipeline. The output bundle lands in `reports/generated/<YYYY-MM-DD>/`. Copy that folder to your internal share.

**Executing notebooks (`--execute`):**
The `--execute` flag re-runs the embedded Jupyter notebooks so the rendered pages carry fresh figures (instead of "pending regeneration" placeholders). The known notebook bugs have been fixed; a full `--execute` run takes roughly 30 minutes:

```bash
python3 -m pipeline.cli reports --execute --timeout 900
```

Run without `--execute` for a fast bundle refresh that reuses the most recent notebook renders.

## Permissions model

### Shared settings (team-wide)
File: `.claude/settings.json` — checked into the repository.
- Contains the minimal allowlist of Bash and MCP tool calls (read-only operations for common analysis tasks).
- Contains deny guardrails:
  - Denies reading `.env` files (protects API keys from accidental exposure)
  - Denies writes to `pipeline/runs/` and `pipeline/agents/checkpoints/` (protects generated data)
  - Denies destructive operations (`rm -rf /`, `git push --force`, `git reset --hard`)

### Personal settings (per-machine, local override)
File: `.claude/settings.local.json` — gitignored, per-machine.
- Use this file for broad permissions that should not be added to the shared `.claude/settings.json`.
- Example: `Bash(python3 -:*)` (permitting all Python invocations) belongs in `.local.json`, not the shared file.
- Each team member maintains their own `.local.json` on their machine.

## Known issues

### Notebook bugs
All bugs that produced **incorrect output numbers** are now resolved:
- Priority-4 items (crash in 01, betweenness perf in 02, wrong chamber inference in 03, bridge filter in 03) — **fixed** in an earlier pass.
- Chamber-average bias in 01 Cell 8 — **fixed 2026-06-14** (by relabel): the comprehensive CSV has no primary-sponsor chamber field, so the metric was relabeled to the dataset-wide average Senate/House *cosponsors* per bill (no longer implying a per-sponsoring-chamber comparison) rather than conditioned on sponsor chamber.

Remaining open notebook items are **performance or display issues only** — they do not affect any numbers shipped into reports.

### Pipeline runtime
- `pipeline/runs/` is created at runtime and may not exist in a freshly cloned repository. It will be created automatically on first pipeline execution.

### NER evaluation
- NER agent F1 score ≈ 0.17 (see `pipeline/agents/output/ner_eval_report.json`).
- This is documented as expected behavior; entity canonicalization and soft-alias strategy take priority over maximizing raw F1 (see ../CLAUDE.md feedback notes on NER soft alias strategy).

## Deeper operations

For NER agent details, refer to:
- **NER agent design:** `NER_AGENT.md`
