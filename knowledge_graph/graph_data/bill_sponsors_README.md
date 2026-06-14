# Bill Sponsors CSV - AGORA Dataset

## Overview
**File:** `bill_sponsors.csv`
**Location:** `knowledge_graph/graph_data/`
**Generated:** 2026-03-13
**Source Data:**
- `agora_with_sponsors.csv` (sponsor details from Congress.gov API)
- `agora_comprehensive_data.csv` (policy areas, cosponsor counts)
- `pulled_data.json` (committee information from Congress.gov API)

## Summary Statistics
- **205 unique sponsors** (109 Democrats, 94 Republicans, 2 Independents)
- **509 sponsored bills** across Congress documents
- **507 bills with committee information** (99.6% coverage)
- Policy areas tracked from Congress.gov classification system

## Column Descriptions

| Column | Type | Description |
|--------|------|-------------|
| `Sponsor Name` | String | Full sponsor name with chamber and district (e.g., "Rep. Smith, John [D-CA-5]") |
| `BioGuide ID` | String | Congress.gov BioGuide ID for unique sponsor identification (use for API lookups) |
| `Party` | String | Party affiliation: `D` (Democrat), `R` (Republican), `I` (Independent) |
| `State` | String | Two-letter state abbreviation (e.g., CA, NY) |
| `District` | String | Congressional district number (empty for Senators) |
| `Number of Bills Sponsored` | Integer | Total count of AGORA bills sponsored by this sponsor |
| `Top Policy Areas` | String | Most frequent policy areas for sponsor's bills (top 3, semicolon-delimited with counts) |
| `Bill Titles` | String | Official bill titles (pipe-delimited: \|) |
| `Bill Policy Areas` | String | Policy area classification per bill (pipe-delimited, matches bill order) |
| `Bill Cosponsors Count` | String | Number of cosponsors per bill (pipe-delimited) |
| `Bill Committee Count` | String | Number of committees assigned to each bill (pipe-delimited) |
| `Bill Committee Details URL` | String | Congress.gov API endpoint to fetch full committee details (pipe-delimited) |
| `Bill Statuses` | String | Current status: Enacted, Defunct, Pending, etc. (pipe-delimited) |
| `Bill Links` | String | Congress.gov bill page URLs (pipe-delimited) |

## Key Features

### 1. Sponsor Details
- Full congressional name with chamber and district
- BioGuide ID for Congress.gov API lookups
- Party affiliation and state representation
- Sortable and filterable by geography and party

### 2. Comprehensive Bill Information
- Official bill titles from Congress.gov
- Policy areas (e.g., "Armed Forces and National Security", "Finance and Financial Sector")
- Number of cosponsors per bill
- **Committee information**: both count and API URL to fetch details
- Bill status (Enacted, Defunct, Pending, etc.)
- Direct links to Congress.gov bill pages

### 3. Committee Information
- **Bill Committee Count**: Number of committees per bill
- **Bill Committee Details URL**: Congress.gov API endpoint returning full committee details
  - Example: `https://api.congress.gov/v3/bill/118/s/2281/committees?format=json`
  - Returns: Committee name, code, activity dates, and jurisdiction

### 4. Policy Area Analytics
- Top policy areas for each sponsor (useful for identifying legislative focus)
- Policy areas from Congress.gov's official classification system
- Enables analysis of sponsor expertise and priorities

## Usage Examples

### Find committees for a specific bill
1. Get the `Bill Committee Details URL` from this CSV
2. Fetch JSON from that URL to get committee details:
```bash
curl "https://api.congress.gov/v3/bill/118/s/2281/committees?format=json"
```
Returns committee name, code, activity dates, jurisdiction, etc.

### Find all bills from a California representative
Filter: `State` = "CA" AND `District` is not empty

### Find most active sponsors
Sort by `Number of Bills Sponsored` descending

### Analyze sponsor focus areas
Look at `Top Policy Areas` to find which policy domains each sponsor works in

### Find bills with the most committees
Parse `Bill Committee Count`, sort descending

## Data Coverage

### What's Included
✓ Sponsor identification and details
✓ Bills sponsored (official titles, status, links)
✓ Policy areas per bill
✓ Cosponsor counts
✓ Committee counts and API endpoints
✓ Committee assignment dates and jurisdiction info (via API URL)

### What's NOT Included (But Available via API)
- Full committee member lists — available from `Bill Committee Details URL`
- Cosponsor names — available at Congress.gov bill page (click "All cosponsors")
- Full committee jurisdiction text — available from Congress.gov API committees endpoint
- Sponsor historical service data — available from BioGuide profile

## Accessing Committee Details

### Option 1: Via Bill Committee URL (Recommended)
```bash
# Example for bill sponsored by Sen. Lummis
curl "https://api.congress.gov/v3/bill/118/s/2281/committees?format=json"

# Returns:
{
  "committees": [
    {
      "name": "Committee on Banking, Housing, and Urban Affairs",
      "code": "SSBK",
      "url": "https://api.congress.gov/v3/committee/senate/SSBK?format=json"
    }
  ]
}
```

### Option 2: Via Congress.gov Web Interface
Each `Bill Links` URL leads to a Congress.gov page where you can:
- Click "Committees" tab to see assigned committees
- See committee activity (referral dates, hearings, etc.)

### Option 3: Via BioGuide Member Profile
Use `BioGuide ID` to access member profile:
```
https://bioguide.congress.gov/search/bio/[BIOGUIDEID]
```
Includes committee memberships and historical assignments.

## File Format
- **Format:** CSV (RFC 4180)
- **Encoding:** UTF-8
- **Quote Character:** Minimal (only where needed for embedded pipes/commas)
- **Field Delimiter:** Comma (,) for columns
- **Repeated Values Delimiter:** Pipe (|) for matching bill-level data
- **Line Endings:** LF (Unix/Linux standard)

## Related Files

| File | Purpose |
|------|---------|
| `agora_with_sponsors.csv` | Raw data with Congress.gov sponsor JSON |
| `agora_comprehensive_data.csv` | Full taxonomy, policy areas, metadata |
| `pulled_data.json` | Complete Congress.gov API responses (committee details, sponsors, actions) |
| `documents.csv` | 622 Congress-only documents (join key: AGORA ID) |
| `bill_sponsors_README.md` | This file |

## Data Quality Notes

- **Committee coverage:** 507/509 bills (99.6%) have committee data
- **Sponsor validation:** All 205 sponsors matched to Congress.gov BioGuide IDs
- **Policy area consistency:** Derived from Congress.gov official classifications
- **Cosponsor counts:** From Congress.gov bill metadata

## Example Query Patterns

### Find all House members from CA sponsoring bills
```
Filter: State = "CA" AND District is not empty (contains integer)
```

### Find all bills with 2+ committees
```
Split Bill Committee Count by |, filter for count >= 2
```

### Find senators in the finance/economic policy area
```
Filter: District is empty (senators have no district)
Filter: Top Policy Areas contains "Finance" OR "Economic"
```

### Count bills by policy area across all sponsors
```
Parse Bill Policy Areas, aggregate by area, count occurrences
```

---

**For more info on the AGORA dataset, see:**
- [README_AGENTS.md](../../README_AGENTS.md) — Project overview and data flow
- [knowledge_graph/README.md](./README.md) — Knowledge graph schema and data sources
- [Congress.gov API Documentation](https://api.congress.gov/) — Full API reference
