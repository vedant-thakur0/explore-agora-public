# CLAUDE.md — pipeline/

## Pipeline-specific notes
- All path constants are in `config.py`. Never hard-code paths.
- CLI entry point is `cli.py`. Run as `python3 -m pipeline.cli <command>`.
- Tuning changes go to `config.py` (thresholds, weights). Document every change in `TUNING_CHANGELOG.md`.
- NER agent runs must respect `ANTHROPIC_RATE_DELAY_SECONDS`. Do not parallelize LLM calls without checking `agents/llm_client.py`.
- Agent outputs → `agents/output/`, checkpoints → `agents/checkpoints/`, memory → `agents/memory/`.
- Do not delete or overwrite files in `runs/` — they are the audit trail for all ranking decisions.
