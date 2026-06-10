# AGORA Knowledge Graph

Knowledge graph development project over the AGORA corpus of AI policy documents.
Prototype scope: **United States Congress** documents only.

**Note:** `graph_data/` contains filtered Congress-only datasets; the full AGORA corpus (including `data/fulltext/` with ~1,016 plaintext bill files) lives at the repo root.

## Data Sources

Filtered data lives in `data/`. Source CSVs are in the parent directory (`../`).

### Prototype Scope

| Asset | Count |
|---|---|
| `data/documents.csv` | 622 documents (Authority = "United States Congress") |
| `data/segments.csv` | 4,087 segments for those documents |
| `data/fulltext/` | 619 plain-text files (3 documents have no retrieved full text) |

### Full Text

- **`../fulltext/`** — 1,016 plain-text files, one per document, named `<agora_id>.txt`
  - Example: `../fulltext/1.txt`, `../fulltext/42.txt`

### CSVs

| File | Rows | Description |
|---|---|---|
| `../documents.csv` | ~10,990 | One row per AGORA document. Includes official name, casual name, authority, collections, taxonomy columns, summaries, tags, activity dates, and annotation status. |
| `../segments.csv` | ~143,294 | Text segments extracted from documents, with per-segment tags, summaries, topic annotations, and flags (non-operative, not AI-related). Keyed by `Document ID` + `Segment position`. |
| `../authorities.csv` | ~105 | Issuing authorities (government bodies, agencies, orgs). Fields: Name, Jurisdiction, Parent authority. |
| `../collections.csv` | ~15 | Thematic collections grouping documents. Fields: Name, Description. |

### Key Join Fields

- `documents.csv` → `AGORA ID` links to filename in `fulltext/<agora_id>.txt`
- `segments.csv` → `Document ID` is the same as `AGORA ID` in documents
- `documents.csv` → `Authority` matches `Name` in authorities
- `documents.csv` → `Collections` (semicolon-delimited) matches `Name` in collections

## Cosponsor Data (NEW)

Starting March 2026, cosponsor information extends the sponsor network:

| File | Rows | Description |
|---|---|---|
| `../graph_data/agora_cosponsors_long.csv` | ~3,500 | One row per (document, cosponsor) pair. Includes bioguide ID, party, state, district, sponsorship date, withdrawal tracking. |
| `../graph_data/agora_comprehensive_data_with_cosponsor_lists.csv` | ~622 | Enriched documents CSV (replaces `agora_with_sponsors.csv`) with cosponsor counts and JSON-encoded lists. Primary input for sponsor/cosponsor graph building. |

See [COSPONSOR_LAYERS.md](./COSPONSOR_LAYERS.md) for details on the knowledge graph Layer 1b (active) and Layer 1.75 (withdrawn) cosponsor networks.

## Notes

- `segments.csv` taxonomy columns use a `Category: Subcategory` naming convention.
- Not all documents in `documents.csv` have a corresponding file in `fulltext/` (~1,016 of ~10,990 have retrieved plaintext).
- The `documents.csv` `Annotated?` and `Validated?` fields track human review status.
- Cosponsor data sourced from Congress.gov API (pulled 2026-03-13 per `bill_sponsors_README.md`).
