# Ranking Tuning Changelog

Append-only record of tuning changes to `pipeline/config.py` and `pipeline/ranker.py`.

## Entry Template

### YYYY-MM-DD - <short change title>

- Trigger/context:
- Files changed:
- Parameter diffs (before -> after):
- Validation evidence (tests and run outputs):
- Observed impact:
- Risks/follow-ups:

## Entries

### 2026-02-25 - Initial `.docx` intake and hybrid profile matching

- Trigger/context:
  - Add first-class `.docx` intake path to score incoming external documents against AGORA positive profile.
- Files changed:
  - `pipeline/docx_matcher.py`
  - `pipeline/cli.py`
  - `pipeline/tests/test_docx_matcher.py`
  - `pipeline/README.md`
  - `pipeline/TUNING_RUNBOOK.md`
- Parameter diffs (before -> after):
  - Added new hybrid scoring path for `.docx`:
    - `candidate_score = 0.70 * semantic_score + 0.30 * keyword_score`
  - Added CLI command:
    - `match-docx` with profile and threshold controls
- Validation evidence (tests and run outputs):
  - Added `.docx` matcher unit tests for extraction handling, score bounds, top-match ordering, and output schema.
  - CLI route emits run summary (`docs_discovered`, `docs_parsed`, `docs_ranked`, `out_json`).
- Observed impact:
  - Pipeline can now score non-congressional `.docx` sources against AGORA profile without model training.
- Risks/follow-ups:
  - Precision may vary by `.docx` genre; monitor false positives and tune aliases/weights.
  - Keep `python-docx` dependency available in runtime environment.

### 2026-02-25 - Keyword schema refactor and boundary-safe matching

- Trigger/context:
  - Need better control as text richness and term variants increase.
  - Reduce substring false positives (e.g., `ai` matching inside unrelated words).
- Files changed:
  - `pipeline/config.py`
  - `pipeline/ranker.py`
  - `pipeline/tests/test_pipeline.py`
- Parameter diffs (before -> after):
  - `KEYWORD_GROUPS`:
    - flat `weight + terms[str]` -> structured groups with:
      - `group_weight`
      - `min_hits_for_full_credit`
      - `max_credit`
      - `terms[]` objects (`term`, `aliases`, `match_type`, `weight`, `polarity`)
  - `metadata_prior()` title AI check:
    - substring check -> boundary-safe regex match
- Validation evidence (tests and run outputs):
  - Added tests:
    - alias + boundary behavior check
    - title AI boundary check
  - Existing and new pipeline tests run with expected behavior for ranker-related cases.
- Observed impact:
  - Improved alias coverage (e.g., `LLM` matches intended AI term).
  - Reduced accidental short-token substring matches in ranking logic.
- Risks/follow-ups:
  - Continue monitoring precision/recall tradeoff as aliases expand.
  - Add explicit negative-polarity test cases if negative rules are introduced.
