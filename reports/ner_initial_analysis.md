# NER Pipeline — Initial Exploratory Analysis

**Date:** 2026-04-07
**Input:** 593 entity records from 532 AGORA AI policy documents
**Graph:** layer_3_entity.graphml (5,366 nodes, 10,943 edges)
**Communities:** 243 Louvain communities across 239 memory files

---

## 1. Entity Distribution

### Counts by type

| Type | Total mentions | Unique | Singletons | Singleton % |
|---|---|---|---|---|
| organizations | 3,832 | 1,084 | 647 | 60% |
| offices | 977 | 578 | 392 | 68% |
| roles | 2,144 | 759 | 529 | 70% |
| legislation_refs | 2,632 | 1,412 | 1,066 | 75% |
| named_docs | 1,357 | 1,177 | 1,036 | 88% |

All entity types show long-tail distributions. Named docs are the most sparse (88% appear once). Organizations are the densest.

### Per-document statistics

| Type | Mean/doc | Docs with any | Max in single doc |
|---|---|---|---|
| organizations | 6.5 | 573/593 (97%) | 91 |
| offices | 1.6 | 386/593 (65%) | 20 |
| roles | 3.6 | 562/593 (95%) | 30 |
| legislation_refs | 4.4 | 572/593 (96%) | 54 |
| named_docs | 2.3 | 452/593 (76%) | 67 |

### Top 15 organizations

| Mentions | Organization |
|---|---|
| 116 | House of Representatives |
| 103 | Senate |
| 79 | Committee on Commerce, Science, and Transportation |
| 73 | Department of Defense |
| 65 | Department of Energy |
| 62 | Department of Commerce |
| 61 | National Institute of Standards and Technology |
| 58 | Committee on Science, Space, and Technology |
| 56 | Congress |
| 50 | Federal Trade Commission |
| 48 | Committee on Energy and Commerce |
| 41 | Government Accountability Office |
| 40 | National Science Foundation |
| 39 | Department of State |
| 33 | People's Republic of China |

### Top 15 roles

| Mentions | Role |
|---|---|
| 97 | Secretary of Defense |
| 88 | Secretary |
| 74 | Director |
| 57 | Secretary of Commerce |
| 52 | Secretary of Energy |
| 43 | Comptroller General of the United States |
| 42 | Administrator |
| 40 | Director of National Intelligence |
| 40 | Secretary of State |
| 38 | Attorney General |
| 38 | Director of the National Institute of Standards and Technology |
| 34 | President |
| 33 | Secretary of Homeland Security |
| 27 | Director of the National Science Foundation |
| 26 | Secretary of Health and Human Services |

**Note on roles:** The roles field uses `title` (not `name`). "Secretary" (88), "Director" (74), and "Administrator" (42) are bare/unresolved role references — handled by community-level disambiguation rules (see section 4).

### Top 15 legislation references

| Mentions | Legislation |
|---|---|
| 56 | National Artificial Intelligence Initiative Act of 2020 |
| 48 | William M. (Mac) Thornberry National Defense Authorization Act for Fiscal Year 2021 |
| 48 | Higher Education Act of 1965 |
| 35 | John S. McCain National Defense Authorization Act for Fiscal Year 2019 |
| 35 | James M. Inhofe National Defense Authorization Act for Fiscal Year 2023 |
| 31 | Federal Trade Commission Act |
| 27 | Research and Development, Competition, and Innovation Act |
| 27 | Communications Act of 1934 |
| 23 | National Institute of Standards and Technology Act |
| 22 | Energy Policy Act of 2005 |
| 19 | Public Health Service Act |
| 17 | Servicemember Quality of Life Improvement and NDAA FY2025 |
| 16 | National Security Act of 1947 |
| 15 | National Defense Authorization Act for Fiscal Year 2022 |
| 14 | Stevenson-Wydler Technology Innovation Act of 1980 |

### Top 10 named documents

| Mentions | Document |
|---|---|
| 9 | Federal Participation in the Development and Use of Voluntary Consensus Standards and in Conformity Assessment Activities |
| 9 | Artificial Intelligence Risk Management Framework |
| 5 | memorandum of understanding |
| 4 | National Defense Strategy |
| 4 | Made in China 2025 |
| 4 | Advanced Research Directions on AI for Science, Energy, and Security |
| 4 | AI for Energy |
| 3 | Artificial Intelligence: An Accountability Framework for Federal Agencies and Other Entities |
| 3 | Common Vulnerabilities and Exposures Program |
| 3 | Agency Retrospective Review Plan |

---

## 2. Graph Structure

### Overview

| Metric | Value |
|---|---|
| Nodes | 5,366 |
| Edges | 10,943 |
| Directed | yes |
| Connected components (undirected) | 3 |
| Largest component | 5,355 nodes (99.8%) |
| 2nd component | 9 nodes |
| 3rd component | 2 nodes |

The graph is essentially one giant component. Near-universal connectivity.

### Node types in graph

| Count | Type |
|---|---|
| 1,352 | Legislation |
| 1,133 | Named Doc |
| 1,061 | Org |
| 723 | Role |
| 566 | Office |
| 531 | Document |

### Degree distribution

| Metric | Value |
|---|---|
| Max degree | 230 |
| Median degree | 1 |
| Mean degree | 4.1 |
| Degree 1 (leaf) | 3,436 (64%) |
| Degree 2–5 | 1,196 (22%) |
| Degree 6–10 | 275 (5%) |
| Degree 11–50 | 407 (8%) |
| Degree >50 | 52 (1%) |
| Degree >100 | 12 |

Highly skewed star topology. Most entity nodes are leaves connected to a single document. High-degree nodes are either hub documents or universal entities (House, Senate, DoD).

### Top 20 nodes by degree

| Degree | Type | Label |
|---|---|---|
| 230 | Document | document:77 |
| 182 | Document | document:75 |
| 147 | Document | document:457 |
| 136 | Document | document:1214 |
| 134 | Document | document:2367 |
| 131 | Document | document:1201 |
| 125 | Document | document:25 |
| 116 | Org | House of Representatives |
| 114 | Document | document:845 |
| 113 | Document | document:1690 |
| 109 | Document | document:860 |
| 103 | Org | Senate |
| 98 | Document | document:1219 |
| 97 | Role | Secretary of Defense |
| 93 | Document | document:902 |
| 92 | Document | document:485 |
| 92 | Document | document:1274 |
| 88 | Role | Secretary |
| 84 | Document | document:288 |
| 81 | Document | document:1358 |

### Top 20 nodes by betweenness centrality (largest component)

| Betweenness | Degree | Type | Label |
|---|---|---|---|
| 0.10237 | 88 | Role | Secretary |
| 0.08551 | 116 | Org | House of Representatives |
| 0.07692 | 230 | Document | document:77 |
| 0.06617 | 103 | Org | Senate |
| 0.06028 | 97 | Role | Secretary of Defense |
| 0.05938 | 62 | Org | Department of Commerce |
| 0.05430 | 76 | Role | Director |
| 0.05127 | 125 | Document | document:25 |
| 0.05047 | 182 | Document | document:75 |
| 0.04419 | 113 | Document | document:1690 |
| 0.04013 | 47 | Role | Attorney General |
| 0.03863 | 73 | Org | Department of Defense |
| 0.03758 | 92 | Document | document:485 |
| 0.03228 | 67 | Document | document:637 |
| 0.03151 | 136 | Document | document:1214 |
| 0.03013 | 42 | Role | Administrator |
| 0.02902 | 41 | Role | Director of National Intelligence |
| 0.02791 | 57 | Document | document:986 |
| 0.02761 | 57 | Role | Secretary of Commerce |
| 0.02706 | 61 | Org | National Institute of Standards and Technology |

"Secretary" (unresolved) has the highest betweenness — it bridges many otherwise-disconnected document clusters. This is a disambiguation artifact: the bare role appears in many communities but resolves to different officials.

### Top 15 hub documents (by entity count)

| Entities | Document | Breakdown |
|---|---|---|
| 230 | document:77 | 90 Org, 53 Legislation, 40 Named Doc, 24 Role, 21 Office |
| 182 | document:75 | 67 Named Doc, 55 Org, 27 Legislation, 19 Role, 14 Office |
| 147 | document:457 | 35 Legislation, 29 Org, 14 Role, 6 Office, 2 Named Doc |
| 136 | document:1214 | 37 Legislation, 21 Role, 18 Org, 9 Named Doc, 4 Office |
| 134 | document:2367 | 15 Org, 3 Role, 2 Legislation, 1 Office, 1 Named Doc |
| 131 | document:1201 | 26 Legislation, 21 Role, 18 Org, 11 Named Doc, 5 Office |
| 125 | document:25 | 54 Org, 22 Legislation, 19 Named Doc, 18 Role, 12 Office |
| 114 | document:845 | 27 Org, 17 Legislation, 10 Office, 10 Named Doc, 6 Role |
| 113 | document:1690 | 36 Legislation, 30 Role, 29 Org, 9 Office, 9 Named Doc |
| 109 | document:860 | 25 Org, 14 Role, 11 Legislation, 11 Named Doc, 6 Office |

document:2367 is anomalous — 134 edges but only 22 distinct entity types. Needs investigation (may be a large omnibus bill or extraction artifact).

---

## 3. Cross-Community Patterns

### Community size distribution (by document count)

| Bucket | Count |
|---|---|
| 1 doc | 204 (84%) |
| 2–3 docs | 30 (12%) |
| 4–10 docs | 4 (2%) |
| >10 docs | 5 (2%) |

Most communities are single-document communities. The 5 large communities likely correspond to omnibus bills (NDAAs, etc.).

### Entities spanning the most communities (top 25)

| Communities | Entity |
|---|---|
| 60 | House of Representatives |
| 59 | Senate |
| 46 | Committee on Commerce, Science, and Transportation |
| 44 | Department of Commerce |
| 38 | Department of Energy |
| 34 | National Institute of Standards and Technology |
| 34 | Committee on Science, Space, and Technology |
| 34 | Committee on Energy and Commerce |
| 30 | National Artificial Intelligence Initiative Act of 2020 |
| 29 | Department of State |
| 29 | Higher Education Act of 1965 |
| 27 | Government Accountability Office |
| 26 | Federal Trade Commission |
| 23 | People's Republic of China |
| 22 | National Science Foundation |
| 22 | Department of Health and Human Services |
| 21 | Department of the Treasury |
| 21 | Department of Agriculture |
| 21 | Committee on Homeland Security and Governmental Affairs |
| 21 | Federal Communications Commission |
| 20 | National Laboratories |
| 20 | Communications Act of 1934 |
| 19 | Congress |
| 19 | Committee on Banking, Housing, and Urban Affairs |
| 19 | Committee on Financial Services |

"Universal" entities: House (60), Senate (59), Commerce Committee (46), DoC (44) appear across >40 communities and are structural constants of AI legislation.

### Community-span distribution

| Span | Entity count | % |
|---|---|---|
| 1 community only | 3,047 | 81% |
| 2–5 communities | 566 | 15% |
| 6–10 communities | 83 | 2% |
| >10 communities | 53 | 1% |

3,749 unique entities across all community memory files.

---

## 4. Disambiguation Quality

### Overview

- 206/239 memory files contain disambiguation rules or oddities
- 255 unique disambiguation keys across all communities
- 44 keys used in multiple communities (expected — "secretary", "director", etc. resolve differently per legislative context)

### Most-disambiguated terms

| Communities | Term |
|---|---|
| 41 | "secretary" |
| 29 | "director" |
| 22 | "the secretary" |
| 18 | "administrator" |
| 14 | "commission" |
| 12 | "the director" |
| 12 | "the commission" |
| 10 | "attorney general" |
| 9 | "the department" |
| 8 | "under secretary" |

### Disambiguation assessment (sampled 10 communities)

**Correct and well-documented:**
- "secretary" resolved correctly per community context (Secretary of Agriculture in community:010, Secretary of HHS in community:200, etc.)
- "administrator" shows 18 distinct community-specific resolutions (EPA, NOAA, SBA, FAA, etc.) — all checked against statutory section references
- "commission" correctly resolves to FTC in 12 communities, NRC in 1, CFPB in 1, SEC in 1 — all with section citations
- "director" resolves to 29 different officials across communities with section-level citations

**Potential issues flagged:**
1. "Secretary" (bare) still appears 88 times in entity output as an unresolved role. Disambiguation rules exist per-community but are not being applied to the entity output. Either the resolution step is not running globally, or these are cross-community references that couldn't be resolved.
2. community:001 is heavily over-indexed — contains 30+ disambiguation rules with section-level granularity (director_in_sec_313, director_in_sec_314, etc.). This is a large omnibus bill community. The rules are correct but create noise at scale.

### Oddities

| Category | Count |
|---|---|
| Total oddities | 162 |
| Truncated/incomplete text | 66 (41%) |
| Other | 96 (59%) |

The dominant oddity pattern is **truncated source text**: the pipeline received only bill titles, enacting clauses, or section headers without substantive content. This affects entity extraction completeness for those documents.

Other oddity examples:
- Duplicate subsection labels in bill text (community:001/doc:215)
- Title-only fragments with no extractable entities (community:001/doc:1737)
- Summary-only documents where entities come from metadata rather than statutory language (community:001/doc:190)

---

## 5. Review Queue

### Overview

| Metric | Value |
|---|---|
| Total flagged entries | 207 |
| Unique reason | `short_name, not_in_registry` |
| All at confidence | 0.4 |

Every flagged entry has the same reason and confidence level. No variance.

### Flagged by entity type

| Count | Type |
|---|---|
| 135 | organizations |
| 53 | roles |
| 12 | legislation_refs |
| 4 | offices |
| 3 | named_docs |

### Top flagged entities

| Count | Entity | Assessment |
|---|---|---|
| 104 | Senate | **False positive** — well-known entity, should be in registry |
| 12 | Senator | Legitimate role, short name |
| 10 | Chair | Ambiguous — needs context to resolve |
| 7 | Speaker | Ambiguous — likely Speaker of the House |
| 3 | Canada | Country name, not org — type mismatch? |
| 3 | Israel | Country name, not org — type mismatch? |
| 3 | State | Too ambiguous to resolve |
| 3 | Board | Too ambiguous to resolve |
| 3 | AUKUS | Acronym, should be registered |
| 2 | Ukraine | Country name |
| 2 | China | Country name (vs. "People's Republic of China") |
| 2 | Taiwan | Country name |
| 2 | TikTok | Company, should be registered |
| 2 | S.4870 | Bill number — wrong entity type? |

### Key findings

1. **"Senate" is 50% of the queue** (104/207). Adding "Senate" to the global registry would cut the queue in half.
2. **Country names** (Canada, Israel, Ukraine, China, Taiwan) are being flagged as organizations. These may need a separate entity type or a country allowlist.
3. **Bill numbers** (S.4870) flagged as entities — likely a parsing issue where bare bill citations aren't matched to legislation_refs.
4. **Single-reason queue**: all entries share `short_name, not_in_registry` at confidence 0.4. The review queue is not differentiating between genuinely ambiguous entities and registry gaps. Consider splitting the confidence scoring for "known-short-name" vs. "unknown-entity."

---

## 6. Summary of Action Items

| Priority | Issue | Impact |
|---|---|---|
| High | Add "Senate" to global registry | Eliminates 104 review queue entries (50%) |
| High | 88 unresolved "Secretary" + 74 "Director" in entity output | Inflates graph betweenness; bridges unrelated docs |
| Medium | 66 documents with truncated source text | Missing entities from ~11% of corpus |
| Medium | Country names flagged as organizations | 13+ queue entries; need entity type or allowlist |
| Low | Review queue uses single reason/confidence | No triage signal; all entries look identical |
| Low | community:001 has 30+ fine-grained disambiguation rules | Correct but may need consolidation |
