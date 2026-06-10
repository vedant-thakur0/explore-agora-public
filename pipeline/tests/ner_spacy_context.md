# spaCy vs. Pipeline NER — Domain Context

**Why the low match rates are structurally expected, not a quality failure.**

Test results (20-doc sample, `en_core_web_lg`, seed=42):

| Type | Pipeline | spaCy | Exact match |
|---|---|---|---|
| Orgs + Offices | 160 | 409 | 19 (11.9%) |
| Legislation refs | 104 | 89 | 2 (1.9%) |
| Roles | 80 | 38 | 0 (0.0%) |

---

## 1. Entity Type Coverage

spaCy `en_core_web_lg` was trained on OntoNotes 5 (newswire, web text, broadcast news). Its 18 labels include `ORG`, `LAW`, `PERSON`, `GPE` — and nothing else relevant. The pipeline extracts five domain-specific types, three of which have no spaCy analogue:

| Pipeline type | spaCy equivalent | Gap |
|---|---|---|
| organizations | `ORG` / `GPE` | Partial |
| legislation_refs | `LAW` | Partial |
| offices | none | Full gap |
| roles | `PERSON` | Structural mismatch (see §5) |
| named_docs | `WORK_OF_ART` at best | Full gap |

`offices` ("Office of the Under Secretary of Defense for Research and Engineering") and `named_docs` ("National AI Risk Management Framework", "Military End User List") are simply outside OntoNotes vocabulary. spaCy cannot extract them regardless of model size.

---

## 2. Legislative Text Is Not Prose

spaCy was trained on news and web text. US statutory language uses nested subsection references (`(a)(1)(A)(ii)`), enacting clauses, section headers in all-caps, and statutory cross-references (`as defined in section 3(b)(1)(G)`). These are spaCy failure modes. The test output showed it directly:

spaCy tagged these spans as `ORG`:
- `"shall--"`
- `"PREDISPUTE JOINT-ACTION WAIVER.—The"`
- `"10)(A)(i)(II"`
- `"GENERAL.—The Research"`
- `"the Committee on Commerce, Science"` (truncated mid-name)

The pipeline chunks on `SEC.`/`SECTION.` boundaries (`NER_CHUNK_SIZE = 6000` chars) and uses the section structure as a semantic signal. The section boundary is where new entities are introduced. spaCy sees the same text as an undifferentiated character stream.

---

## 3. Disambiguation Is the Core Differentiator

"Secretary" appears 88 times across the corpus. It refers to 14 different cabinet officials depending on which bill is being processed. spaCy returns the literal token "Secretary" with no resolution. The pipeline maintains per-community memory files (`pipeline/agents/memory/`) with keyed disambiguation rules that are learned incrementally and then injected into every subsequent LLM prompt within that community:

```
community:001  "director"  →  Director of National Intelligence
community:010  "director"  →  Director of NIST
community:100  "director"  →  Director of the National Science Foundation
```

This is not post-processing. The resolved form is embedded in the prompt context before the LLM reads the next document, so the model sees "Director of National Intelligence" where the document text said "the Director." spaCy has no mechanism for cross-document state of any kind.

Across all 239 community memory files: 255 unique disambiguation keys, 44 keys resolved differently across multiple communities, 41 communities independently disambiguating "secretary" to the correct official.

---

## 4. Canonical Form vs. Surface Form

spaCy returns whatever text span appeared in the source. The pipeline normalizes to canonical government names. Examples from the 20-doc sample:

| spaCy output | Pipeline output |
|---|---|
| "the Committee on Commerce, Science" | "Committee on Commerce, Science, and Transportation" |
| "the House of Representatives" | "House of Representatives" |
| "National Intelligence" | "Director of National Intelligence" |
| "the Department of Defense" | "Department of Defense" |
| "SEC" | "Securities and Exchange Commission" |
| "NOAA" | (matched to "National Oceanic and Atmospheric Administration" via acronym) |

Canonical forms are required for graph construction: two documents referencing the same entity must produce the same node in the knowledge graph. Surface forms cannot do this reliably. The entity graph (`layer_3_entity.graphml`) has 5,366 nodes precisely because the pipeline enforces canonical identity — spaCy surface spans would produce thousands of duplicates.

---

## 5. Role Titles Are Not People

The 0% match rate on roles is by design, not error. spaCy's `PERSON` label fires on named individuals: "Avril Haines", "Gen. Milley", "Mark Warner". The pipeline's `roles` field captures institutional titles: "Secretary of Defense", "Comptroller General of the United States", "Chief Digital and Artificial Intelligence Officer".

These are structurally different entities:
- A **person** is a one-time occurrence tied to an administration
- A **role** persists across administrations and carries statutory authority independent of its holder

For AI governance research, the role is the correct unit. When the NDAA mandates that "the Secretary of Defense shall submit a report," that obligation belongs to the office, not the individual. The pipeline extracts 759 unique role titles across the corpus. spaCy extracted 38 person names in the 20-doc sample, with 0 overlap — because they are measuring different things.

---

## 6. Community Context Propagation

The pipeline processes documents in community order (Louvain cluster), sorted by graph centrality within each community. Entities from hub documents seed the community memory and are available as resolved referents when later documents use abbreviated or anaphoric references. A niche entity like "Joint Artificial Intelligence Center" mentioned in document:77 (the hub with 230 edges) is carried forward so that when document:213 says "the Center," the model resolves it correctly — without an additional LLM call.

spaCy processes each document independently with no cross-document state. In this corpus, where 81% of entities appear in only one community and disambiguation is heavily context-dependent, document-independent processing produces the surface-form noise visible in the test output.

---

## 7. What the Comparison Is Useful For

**spaCy-only hits worth examining:**
- Informal abbreviations the pipeline missed: `NOAA`, `FEMA`, `CBP` as standalone tokens
- Generic collective references: "the Federal Government", "Federal Agencies" — outside pipeline scope by design but sometimes meaningful

**Pipeline-only entities (the valuable output):**
- Full formal committee names with chamber specification
- Office names with parent-org structure
- Role titles with institutional context
- Legislation citations with section-level specificity
- Named policy documents referenced across bills

**spaCy noise (not fixable by model size):**
- Section headers tagged as `ORG` — OntoNotes has no statutory training data
- Truncated names from subsection numbering breaking tokenization
- Possessive and prepositional fragments: "the Secretary of", "the Committee on"

---

## Summary

spaCy is an appropriate baseline for general-purpose NER on news text. For US AI policy legislation it produces: wrong entity types (no offices, no roles, no named docs), surface-form spans that cannot merge across documents, and structured noise from section syntax it was never trained on. The pipeline addresses these by using an LLM with legislative domain knowledge, community-scoped disambiguation memory, section-boundary chunking, and a five-type schema designed for the actual entities that appear in AI governance documents. The 12% org match rate reflects the canonical-vs-surface-form gap, not extraction quality.
