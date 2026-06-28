# Congress.gov Candidate Discovery Pipeline

Manual-run ingestion pipeline for discovering likely AI-policy documents from congress.gov.

## Commands

Run from project root:

```bash
python3 -m pipeline.cli fetch --since 2025-01-01 --limit 100
python3 -m pipeline.cli rank-candidates --run-id <RUN_ID>
python3 -m pipeline.cli export-review --run-id <RUN_ID> --out agora/pipeline/review_exports/<RUN_ID>_review.csv
```

Offline fixture run:

```bash
python3 -m pipeline.cli fetch --since 2025-01-01 --limit 10 --fixture-json agora/pipeline/fixtures/sample_bills.json --run-id localtest
```

One-call HR trial (live, list-only):

```bash
export CONGRESS_API_KEY='YOUR_KEY'
python3 -m pipeline.trial_one_call_hr --since 2026-01-01 --limit 250 --top-k 50
```

One-call list + per-bill detail hydration (recommended):

```bash
python3 -m pipeline.cli trial-one-call-hr \
  --since 2026-01-01 \
  --limit 251 \
  --top-k 50 \
  --hydrate-details \
  --detail-delay-sec 0.1 \
  --detail-max-retries 2
```

Match incoming `.docx` files against AGORA positive profile:

```bash
python3 -m pipeline.cli match-docx \
  --docx-dir /path/to/docx \
  --profile-jsonl pipeline/datasets/agora_positive_profile_v1.jsonl \
  --top-k 50 \
  --min-score 0.0 \
  --max-profile-matches 5
```

## Data flow

- `raw/`: source payload snapshots.
- `normalized/`: normalized document JSONL.
- `fulltext/`: hydrated plaintext by source ID.
- `runs/`: run manifests and candidate JSONL.
- `review_exports/`: reviewer CSVs with decision fields (`include`, `reject`, `unsure`).
- `datasets/`: generated training/reference artifacts.
- `runs/docx_match_<timestamp>.json`: `.docx` match runs and scored results.

## Positive profile dataset (v1)

Build the positive-only AGORA profile from `documents.csv`:

```bash
python3 -m pipeline.build_positive_profile
```

Optional flags:

```bash
python3 -m pipeline.build_positive_profile \
  --input-csv documents.csv \
  --out-prefix pipeline/datasets/agora_positive_profile_v1
```

Generated artifacts:

- `pipeline/datasets/agora_positive_profile_v1.jsonl`
- `pipeline/datasets/agora_positive_profile_v1.csv`
- `pipeline/datasets/agora_positive_profile_v1_report.json`
- `pipeline/datasets/agora_positive_profile_v1_lineage.json`

Core fields:

- `agora_id`, `official_name`, `casual_name`, `link_to_document`, `authority`
- `collections`, `most_recent_activity`, `most_recent_activity_date`
- `short_summary`, `long_summary`, `tags`
- `official_plaintext_retrieved`, `official_plaintext_source`
- `profile_text`, `profile_text_sha256`
- `label_agora_fit` (always `1`), `label_source` (always `documents_csv`)
- `snapshot_date`, `record_origin`

Known limitations:

- This is a positive-only reference dataset (no negatives).
- It is intended for similarity matching of incoming `.docx` in a later step.
- No classifier training occurs in this step.

## Ranking Tuning Docs

Use these docs for iterative tuning of `pipeline/config.py` and `pipeline/ranker.py`:

- [TUNING_RUNBOOK.md](TUNING_RUNBOOK.md): process, guardrails, evaluation, and rollback.
- [TUNING_CHANGELOG.md](TUNING_CHANGELOG.md): append-only history of tuning changes and observed impact.

## Notes

- No AGORA label prediction is performed.
- Candidate ranking uses keyword signals + semantic similarity to existing federal AGORA corpus + metadata priors.
- `.docx` matching uses a hybrid score: `0.70 * semantic_similarity + 0.30 * keyword_score`.
- Dedup skips unchanged docs that were already reviewed in prior exports.
