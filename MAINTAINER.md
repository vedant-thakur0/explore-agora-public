# MAINTAINER.md — AGORA Operations

This document covers operational tasks for repository maintainers and analysts.

## Provisioning analysts

Each analyst receives:
- A copy of the repository folder (checked into your team's source control or shared directly)
- A `.env` file handed over separately (never committed, never posted in shared channels)

The `.env` file must contain the following keys (see README.md Configuration section for where to obtain them):
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

**Unsafe option (`--execute`):**
The `--execute` flag re-runs the embedded Jupyter notebooks but is **currently UNSAFE** due to known bugs in `notebooks/REVIEW.md`:
- **Notebook 01** (`01_sponsor_profiling.ipynb`): Cell 10 crashes with a NameError (uses undefined variable `cosponsors_df`).
- **Notebook 02** (`02_policy_networks.ipynb`): Cell 12 has a severe performance bug (recomputes betweenness centrality on every iteration, turning minutes into hours).

Until these bugs are fixed, report bundle notebook pages will show "pending regeneration."

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
See `notebooks/REVIEW.md` for the full bug list, ordered by severity. Key blockers:
1. **01_sponsor_profiling.ipynb · Cell 10** — NameError; crashes on first run
2. **02_policy_networks.ipynb · Cell 12** — betweenness centrality recomputed in loop; severe perf degradation
3. **03_coalitions.ipynb · Cell 3** — inconsistent chamber inference; produces wrong numbers
4. **03_coalitions.ipynb · Cell 7** — bridge legislators filter includes isolated nodes; wrong rankings

### Pipeline runtime
- `pipeline/runs/` is created at runtime and may not exist in a freshly cloned repository. It will be created automatically on first pipeline execution.

### NER evaluation
- NER agent F1 score ≈ 0.17 (see `pipeline/agents/output/ner_eval_report.json`).
- This is documented as expected behavior; entity canonicalization and soft-alias strategy take priority over maximizing raw F1 (see CLAUDE.md feedback notes on NER soft alias strategy).

## Deeper operations

For advanced pipeline tuning and NER agent details, refer to:
- **Pipeline tuning runbook:** `pipeline/TUNING_RUNBOOK.md`
- **Tuning changelog:** `pipeline/TUNING_CHANGELOG.md`
- **NER agent design:** `NER_AGENT.md`
