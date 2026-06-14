# Ranking Tuning Runbook

## Objectives

- Keep ranking quality stable as incoming text gets richer and more varied.
- Make `pipeline/config.py` and `pipeline/ranker.py` updates repeatable and auditable.
- Preserve reviewer trust through explainable ranking signals.

## Inputs

- Positive profile artifacts:
  - `pipeline/datasets/agora_positive_profile_v1.jsonl`
  - `pipeline/datasets/agora_positive_profile_v1_report.json`
- Ranking runs:
  - `pipeline/runs/<run_id>.json`
  - `pipeline/runs/<run_id>_candidates.jsonl`
- Review exports:
  - `pipeline/review_exports/*_review.csv`
- Optional fixture inputs:
  - `pipeline/fixtures/bill_texts.json`
  - `pipeline/fixtures/sample_bills.json` (when present)

## What Can Be Tuned

### Keyword config (`pipeline/config.py`)

Group schema:
- `group_weight`
- `min_hits_for_full_credit`
- `max_credit`
- `terms[]`

Term schema:
- `term`
- `aliases`
- `match_type` (`token`, `phrase`, `regex`)
- `weight`
- `polarity` (`positive`, `negative`)

Backward compatibility:
- Legacy string-only terms are still accepted in code as `phrase` positive terms with weight `1.0`.

### Ranker behavior (`pipeline/ranker.py`)

- `keyword_signal()` matching and score aggregation.
- Composite scoring formula weights:
  - keyword signal contribution
  - semantic similarity contribution
  - metadata prior contribution
- Score thresholds:
  - `min_score_for_export`
  - `high_threshold`
  - `medium_threshold`

## Guardrails

- Use boundary-safe matching for short tokens/acronyms (`\b...\b`).
- Avoid broad substring patterns that create false positives.
- Keep `matched_signals` stable and human-readable for review workflows.
- Keep evidence snippets understandable and tied to visible text.
- Prefer small, isolated changes over large multi-axis tuning in one pass.

## Evaluation Checklist

- Run unit tests:
  - `pipeline.tests.test_pipeline`
  - `pipeline.tests.test_positive_profile`
  - `pipeline.tests.test_docx_matcher`
- Run a representative ranking pass and inspect:
  - high-scoring false positives
  - missed obvious positives
  - signal explainability in `matched_signals`
- Track proxy metrics in the changelog entry:
  - candidate count by tier
  - include/reject ratio from review CSV sample
  - notable false-positive patterns

## DOCX-Specific Evaluation Loop

- Run `.docx` matching on a mixed sample by document genre (policy memo, legal text, technical brief, unrelated admin text).
- Review top profile matches to ensure nearest AGORA IDs are semantically plausible.
- Inspect recurring false positives by genre and tune:
  - aliases
  - term weights
  - thresholds
- Confirm `matched_signals` remain interpretable for reviewers.

## Decision Rules

### Add alias

Add an alias when:
- same concept appears in new phrasing/acronym frequently
- false negatives are due to vocabulary drift

Validation:
- add/adjust tests for alias hit
- verify no obvious precision regression in sample run

### Add/remove keyword

Add keyword when:
- repeated missed positives share a concrete term

Remove keyword when:
- it is a recurring source of false positives and not salvaged by boundaries/weights

Validation:
- run false-positive scan
- confirm target examples move in expected direction

### Change group/term weights

Change weights when:
- relative influence of groups is misaligned with review outcomes

Validation:
- compare pre/post candidate tier distribution
- verify explainability remains coherent

### Adjust score thresholds

Adjust thresholds when:
- review volume is too high/low at current quality level

Validation:
- compare pre/post export size and sampled quality

## Evidence Contract

- `matched_signals`:
  - Short, semantically stable signal identifiers.
  - Avoid renaming existing signal labels unless necessary.
- `evidence_snippets`:
  - Must point reviewers to plausible textual evidence.
  - If ranking behavior changes, verify snippets still reflect why a record ranked high.

## Trigger Conditions For Docs Updates (Ad Hoc)

Update docs whenever any of these happen:
- `KEYWORD_GROUPS` structure or weights change
- ranking equation/thresholds change
- metadata prior logic changes
- match behavior changes (`token`, `phrase`, `regex`, `polarity`)
- behavior-impacting ranking regression fix

Required updates by trigger:
- Always append `TUNING_CHANGELOG.md` entry
- Update this runbook if process or contract changed
- Update `README.md` if command usage changed
- Update `API_SESSION_INGESTION_PLAYBOOK.md` if ingestion assumptions changed

## Rollback Instructions

1. Identify last known-good change in `TUNING_CHANGELOG.md`.
2. Restore prior values in `pipeline/config.py` and/or `pipeline/ranker.py`.
3. Re-run pipeline tests and a representative ranking run.
4. Add rollback note to changelog with reason and effect.

## PR/Review Checklist

- Docs updated for any behavior-changing rank/config change?
- Tests updated to cover new matching/scoring behavior?
- Sample output sanity-checked (`matched_signals`, top candidates)?
- Rollback path documented in changelog entry?

## Done Criteria For A Tuning Cycle

- Code and docs are in sync.
- Required tests pass.
- Changelog entry captures what changed, why, and observed effect.
- Reviewers can understand ranking rationale from exported outputs.
