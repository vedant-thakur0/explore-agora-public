# Plan: Backfill `char_start`/`char_end` into `entities.jsonl`

**Input:** `pipeline/agents/output/entities.jsonl` + `data/fulltext/{agora_id}.txt` + `pipeline/agents/memory/{community_id}_memory.json`  
**Output:** `pipeline/agents/output/entities_with_offsets.jsonl`  
**No LLM calls. No new dependencies.**

---

## Step 1 — Build disambiguation reverse map

Load all community memory files. For each `alias → resolution_string` in `disambiguation_rules`:
- Parse the canonical name out of the resolution string using patterns like `"Resolved to X"`, `"Confirmed as X"`, `"Defined as X"`, `"Secretary of X"` etc.
- Store: `{community_id: {canonical_name_lower: [alias, alias, ...]}}`

Also record which `agora_id` belongs to which community (from `communities.json`) so the right community's rules are applied per document.

---

## Step 2 — Surface form resolution (per entity)

For each entity, build a prioritized candidate list of strings to search:

| Type | Candidates in order |
|---|---|
| `organizations` | `name` → `acronym` → disambiguation aliases |
| `offices` | `name` → disambiguation aliases |
| `roles` | `title` → disambiguation aliases |
| `legislation_refs` | `citation` → `name` (first 40 chars) → disambiguation aliases |
| `named_docs` | `name` → disambiguation aliases |

---

## Step 3 — Word-boundary match in fulltext

For each candidate surface form (in priority order), run case-insensitive `re.finditer` with `\b` guards. Stop at the first candidate that yields ≥1 match. If all candidates yield 0, leave `char_start`/`char_end` as `null`.

Quote-normalize the fulltext before matching (curly → straight quotes) to handle the mismatch between fulltext and context strings.

---

## Step 4 — Multi-occurrence assignment

If a surface form matches multiple positions in a document and multiple entities share that surface form, assign occurrences in document order (first entity → first match, second → second, etc.). Skip any match whose span is contained inside a longer already-assigned span (replicating the frontend's `isInsideLongerPhrase` guard).

---

## Step 5 — Write output + coverage report

- Write `entities_with_offsets.jsonl` — same schema, entities gain `char_start`, `char_end`, and `match_method` (`"name"`, `"acronym"`, `"citation"`, `"disambiguation_alias"`, or `null`)
- Print coverage breakdown by `match_method` and entity type so you can see where the remaining nulls concentrate
