# FAQ — AGORA Toolkit

## What does the pipeline actually do?

AGORA runs four core steps:

1. **Ingestion** — Downloads current bills from Congress.gov.
2. **Ranking** — Uses AI to score which bills are most relevant to AI policy.
3. **Entity extraction** — Identifies and names key AI concepts mentioned in each bill.
4. **Knowledge graph** — Builds a database of legislators, bills, co-sponsorships, and policy topics to power the interactive reports.

## What does each report show?

- **Sponsor profiling** — Which legislators sponsor AI bills and what policy areas they focus on.
- **Policy networks** — How policy topics (e.g., algorithmic bias, surveillance) connect to each other through bills that are co-sponsored by multiple legislators.
- **Coalitions** — Groups of legislators who repeatedly co-sponsor bills together, including which coalitions bridge across party lines.
- **Taxonomy** — How all bills in the dataset distribute across AGORA's AI policy categories.

## How current is the data?

Reports are snapshots taken on a specific date. Always check the date shown on `index.html`. If the data is older than you need, ask Claude to run `/refresh-data` (with the project maintainer's approval) to ingest the latest bills from Congress.

## Does running things cost money?

- Generating reports from existing data: **Free.**
- Ranking bills (`/run-ranking`): **Costs money.** Will ask for confirmation.
- Refreshing data from Congress (`/refresh-data`): **Costs money.** Will ask for confirmation.

Report generation itself is free; costs only apply if you're bringing in new data or re-ranking.

## Something looks wrong in a chart — what do I do?

1. Note which report and which chart.
2. Check the date on `index.html` to see if the data is stale.
3. Open a GitHub issue with the details.

## Who maintains this?

This project is maintained by its contributors. To report bugs or ask questions, open a GitHub issue in this repository.
