# CLAUDE.md — AGORA Project

## Project synopsis
Explore-AGORA is a computational toolkit for AI policy research. Driven by accountability, transparency, and computational minimalism. Uses the AGORA dataset (key strengths: tags and identification of AI-related legislation).

## DO NOT
- Spin up explore agents or bash commands unless absolutely necessary. Use context in existing .md files and plan files first.

## Directory structure
ONLY IF NEEDED: See `FILETREE.md` for the full annotated file tree.

## Pipeline conventions
- All path constants live in `config.py`.
- CLI entry: `python3 -m agora.pipeline.cli <command>`
- Agent outputs → `agents/output/`, checkpoints → `agents/checkpoints/`, memory → `agents/memory/`.

## Key references
- **File tree:** `FILETREE.md`
- **Data schema:** `knowledge_graph/README.md`
- **Cosponsor layers:** `knowledge_graph/COSPONSOR_LAYERS.md` (Layer 1b: active, Layer 1.75: withdrawn)
- **NER agent docs:** `NER_AGENT.md`
- **Tuning guide:** `pipeline/TUNING_RUNBOOK.md`
- **Tuning history:** `pipeline/TUNING_CHANGELOG.md`
