# Congress API Session Ingestion Playbook

This playbook follows the exact tooling pattern used in `automatedingestion.ipynb`:

- `pull_info(url)` for list/session pulls
- `build_text_url(congress, bill_type, number)` for per-bill text endpoints
- `fetch_bill_text(congress, bill_type, number)` for text hydration
- `process_and_save(hr_119, output_file)` for session-level JSON output

## Goal

1. Pull all bill titles for one API session (list endpoint).
2. Iterate each bill and call bill-specific text APIs.
3. Save a single session artifact with title + full text for ranking.

## Prerequisites

- Python 3
- `requests`
- `api_key` set in your notebook/session

## Step 1: Pull all bill titles for a session

Use the notebook helper:

```python
import requests

def pull_info(url):
  params = {
    "format": "json",
    "api_key": api_key,
  }
  response = requests.get(url, params=params)
  return response.json()
```

Example session pull (119th Congress House bills):

```python
hr_119 = pull_info('https://api.congress.gov/v3/bill/119/hr?format=json')
```

Expected shape includes:

- `bills[]`
- `bills[i].congress`
- `bills[i].type`
- `bills[i].number`
- `bills[i].title`

## Step 2: Build per-bill text URLs

Use:

```python
API_KEY = api_key
BASE_URL = "https://api.congress.gov/v3/bill"

def build_text_url(congress, bill_type, number):
    return (
        f"{BASE_URL}/{congress}/{bill_type.lower()}/{number}"
        f"/text?format=json&api_key={API_KEY}"
    )
```

This generates URLs like:

`https://api.congress.gov/v3/bill/119/hr/144/text?format=json&api_key=...`

## Step 3: Fetch full text bill-by-bill

Use:

```python
def fetch_bill_text(congress, bill_type, number):
    url = build_text_url(congress, bill_type, number)
    response = requests.get(url)

    if response.status_code != 200:
        print(f"Failed request for {bill_type} {number}")
        return None

    data = response.json()

    text_versions = data.get("textVersions", [])
    if not text_versions:
        print(f"No text available for {bill_type} {number}")
        return None

    latest_version = text_versions[0]
    formats = latest_version.get("formats", [])

    for fmt in formats:
        if fmt.get("type") == "Formatted Text":
            text_url = fmt.get("url")
            text_response = requests.get(text_url)
            return text_response.text

    return None
```

Notes:

- Prefer `Formatted Text` when available.
- Return `None` if text is unavailable.
- Add a short delay per bill to reduce rate-limit risk.

## Step 4: Save session output for ranking

Use:

```python
import json
import time

def process_and_save(hr_119, output_file="bill_texts.json"):
    results = []

    for bill in hr_119.get("bills", []):
        congress = bill["congress"]
        bill_type = bill["type"]
        number = bill["number"]

        print(f"Fetching {bill_type} {number}...")
        full_text = fetch_bill_text(congress, bill_type, number)

        results.append({
            "congress": congress,
            "bill_number": f"{bill_type} {number}",
            "title": bill.get("title"),
            "full_text": full_text
        })

        time.sleep(0.5)

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved to {output_file}")
```

Recommended output path in this repo:

- `pipeline/fixtures/bill_texts.json`

## Step 5: Run ranking pipeline on saved session output

From repo root:

```bash
PYTHONPATH=/Users/vthakur/Documents/auto python3 -m agora.pipeline.cli fetch \
  --since 2025-01-01 \
  --limit 250 \
  --fixture-json /Users/vthakur/Documents/auto/agora/pipeline/fixtures/bill_texts.json \
  --run-id session_run

PYTHONPATH=/Users/vthakur/Documents/auto python3 -m agora.pipeline.cli rank-candidates \
  --run-id session_run \
  --reference-csv /Users/vthakur/Documents/auto/agora/documents_us_federal_with_fulltext.csv
```

## Output Contract

Each row in `bill_texts.json` should look like:

```json
{
  "congress": 119,
  "bill_number": "HR 144",
  "title": "Tennessee Valley Authority Salary Transparency Act",
  "full_text": "<html>...or plain text...</html>"
}
```

This format is now supported directly by the ingestion/ranking pipeline.

## After Ingestion: Evaluate Tuning Candidates

Once you have run ingestion and ranking:

1. Review candidate outputs in `pipeline/runs/<run_id>_candidates.jsonl`.
2. Export reviewer sheet and inspect include/reject patterns.
3. Identify match gaps and false positives for config/ranker tuning.

Use the dedicated tuning docs:

- [TUNING_RUNBOOK.md](/Users/vthakur/Documents/auto/agora/pipeline/TUNING_RUNBOOK.md) for the tuning process and guardrails.
- [TUNING_CHANGELOG.md](/Users/vthakur/Documents/auto/agora/pipeline/TUNING_CHANGELOG.md) to record every behavior-changing update.
