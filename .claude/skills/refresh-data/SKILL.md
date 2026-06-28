---
name: refresh-data
description: Refreshes the AGORA dataset by downloading the latest Zenodo release and upserting records into Supabase. COSTS / HAS SIDE EFFECTS — writes to the live Supabase database. Requires explicit user confirmation. For non-technical analysts acting on instruction from the maintainer.
---

# Skill: refresh-data

**Audience:** Non-technical analysts who have been explicitly told by the project maintainer to refresh the dataset.

## IMPORTANT: This command writes to an external database

Before running, Claude will ask you to confirm. The command:

- **Downloads the latest AGORA release from Zenodo** (a public data repository)
- **Upserts records into Supabase** (the live project database)

Writing to the live database without authorization can overwrite current data. Only run this if the maintainer has told you to.

## What this does

Fetches the latest tagged AGORA dataset from Zenodo (using the configured `ZENODO_RECORD_ID`) and upserts documents, segments, authorities, and other tables into the Supabase project database.

## Command

```
python3 -m pipeline.cli sync-supabase
```

Run from the repo root.

### Safe dry-run first (STRONGLY recommended)

Before a live sync, always run the dry-run to validate without writing:

```
python3 -m pipeline.cli sync-supabase --dry-run
```

This parses and validates all data but makes zero database writes. Review the output before proceeding with a live run.

### Other options

| Flag | Purpose |
|---|---|
| `--dry-run` | Validate only, no database writes |
| `--tables <list>` | Sync only specific tables (comma-separated, e.g. `documents,segments`) |
| `--record-id <id>` | Override the Zenodo record ID from config |

## Expected runtime

- Dry run: 1–3 minutes (download + parse only)
- Live sync: 5–20 minutes depending on dataset size and Supabase write throughput

## Before running — Claude will ask you to confirm

Claude will present this prompt before executing any live (non-dry-run) sync:

> "This command will download the latest Zenodo release and write to the live Supabase database. This action cannot be automatically undone. Are you sure you want to proceed? (yes/no)"

Type "yes" to continue. Any other response cancels the run. Claude will also suggest running `--dry-run` first if you have not already.

## Explaining results in plain English

After a successful sync, the command prints a summary of tables touched and records upserted. Look for lines like:
- `Upserted N documents` — new or updated document records
- `Skipped N` — records that were identical to what was already in the database

A dry-run output that shows zero errors means the data is valid and ready for a live sync.

## If data refresh is blocked or restricted

If the Zenodo record ID is not configured, or Supabase credentials are missing from the environment, the command will fail with a clear error. In that case, **do not attempt to configure credentials yourself**. Open a GitHub issue (or contact the project maintainer) and share the exact error message. Data refresh configuration is maintainer-only.

## On failure

Copy the full terminal output and open a GitHub issue (or contact the project maintainer). Do not retry a failed live sync without maintainer guidance — partial writes may need to be reviewed.
