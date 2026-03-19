# CLAUDE.md — AGORA Project

**MANDATORY FIRST ACTION: Read `README_AGENTS.md` in full before doing anything else.**
It is the authoritative quick-start reference for this project and contains directory structure,
data flow, CLI commands, agent architecture, and progress log. All other work assumes you have read it.

## Project in one sentence
AGORA discovers, ranks, and analyzes U.S. Congress AI policy documents using a multi-stage pipeline
(Congress.gov ingestion → TF-IDF ranking → knowledge graph → NER agents).

## After significant changes
Append an entry to the **Progress Log** section of `README_AGENTS.md` using the template in that file.
Update the "Last Updated" timestamp at the top.

## DO NOT
- Use `pipeline/fixtures/` or `pipeline/runs/demo_run*` paths in live operations — offline/test only.
- Bypass `ANTHROPIC_RATE_DELAY_SECONDS` (0.65s) in any loop calling the Claude API. Violating this causes silent NER corruption.
- Hard-code absolute paths (e.g. `/Users/vthakur/...`). Use path constants from `pipeline/config.py` instead.
- Commit or modify `.env`. It holds `CONGRESS_API_KEY` and must stay out of version control.
