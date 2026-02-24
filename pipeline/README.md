# Congress.gov Candidate Discovery Pipeline

Manual-run ingestion pipeline for discovering likely AI-policy documents from congress.gov.

## Commands

Run from project root:

```bash
python3 -m agora.pipeline.cli fetch --since 2025-01-01 --limit 100
python3 -m agora.pipeline.cli rank-candidates --run-id <RUN_ID>
python3 -m agora.pipeline.cli export-review --run-id <RUN_ID> --out agora/pipeline/review_exports/<RUN_ID>_review.csv
```

Offline fixture run:

```bash
python3 -m agora.pipeline.cli fetch --since 2025-01-01 --limit 10 --fixture-json agora/pipeline/fixtures/sample_bills.json --run-id localtest
```

## Data flow

- `raw/`: source payload snapshots.
- `normalized/`: normalized document JSONL.
- `fulltext/`: hydrated plaintext by source ID.
- `runs/`: run manifests and candidate JSONL.
- `review_exports/`: reviewer CSVs with decision fields (`include`, `reject`, `unsure`).

## Notes

- No AGORA label prediction is performed.
- Candidate ranking uses keyword signals + semantic similarity to existing federal AGORA corpus + metadata priors.
- Dedup skips unchanged docs that were already reviewed in prior exports.
