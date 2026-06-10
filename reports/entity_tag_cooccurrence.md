# Entity–Tag Co-occurrence Analysis

**Date:** 2026-04-08
**Input:** 4,818 unique (entity, type) pairs across 593 entity records; 77 AGORA taxonomy tags across 594 documents

---

## 1. Method

For each entity that appears in a document, record a co-occurrence with every AGORA taxonomy tag active on that document. A single entity appearing in a document tagged with 5 tags produces 5 co-occurrences. This captures which entities are associated with which policy domains.

PMI (pointwise mutual information) is used to identify entity–tag pairs that co-occur more often than expected by chance: `PMI = log2(P(entity,tag) / (P(entity) * P(tag)))`. Higher PMI = stronger association beyond what frequency alone explains.

---

## 2. Tag Frequency (top 20 of 77)

| Docs | Tag |
|---|---|
| 301 | Strategies: Government study or report |
| 283 | Strategies: Evaluation |
| 257 | Strategies: Governance development |
| 238 | Strategies: Disclosure |
| 232 | Strategies: Convening |
| 229 | Strategies: Government support |
| 169 | Risk factors: Security |
| 162 | Applications: Government: military and public safety |
| 159 | Risk factors: Transparency |
| 147 | Strategies: Evaluation: Impact assessment |
| 147 | Risk factors: Safety |
| 146 | Harms: Violation of civil or human rights, including privacy |
| 144 | Strategies: Government support: For R&D |
| 137 | Strategies: New institution |
| 117 | Strategies: Disclosure: In deployment |
| 117 | Harms: Harm to health/safety |
| 116 | Risk factors: Privacy |
| 116 | Risk factors: Reliability |
| 116 | Strategies: Government support: AI workforce-related |
| 111 | Strategies: Disclosure: About evaluation |

Strategies tags dominate (6 of top 8). "Government study or report" appears in 51% of all docs.

---

## 3. Top Entities Per Tag

### Applications: Government: military and public safety (162 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 57 | Secretary of Defense | Role |
| 41 | Department of Defense | Org |
| 24 | James M. Inhofe NDAA FY2023 | Legislation |
| 18 | Director of National Intelligence | Role |
| 17 | William M. (Mac) Thornberry NDAA FY2021 | Legislation |

### Strategies: Government study or report (301 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 51 | Secretary of Defense | Role |
| 39 | House of Representatives | Org |
| 32 | Committee on Commerce, Science, and Transportation | Org |
| 32 | Department of Defense | Org |
| 30 | Senate | Org |

### Strategies: Evaluation (283 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 29 | Secretary of Defense | Role |
| 24 | Department of Defense | Org |
| 23 | House of Representatives | Org |
| 22 | National Institute of Standards and Technology | Org |
| 21 | Committee on Commerce, Science, and Transportation | Org |

### Strategies: Disclosure (238 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 24 | House of Representatives | Org |
| 22 | Federal Trade Commission | Org |
| 19 | National Institute of Standards and Technology | Org |
| 18 | Federal Trade Commission Act | Legislation |
| 17 | Senate | Org |

### Strategies: Government support: For R&D (144 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 21 | Department of Energy | Org |
| 19 | Secretary of Energy | Role |
| 17 | Committee on Commerce, Science, and Transportation | Org |
| 17 | Higher Education Act of 1965 | Legislation |
| 15 | Senate | Org |

### Risk factors: Security (169 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 20 | House of Representatives | Org |
| 17 | Secretary of Defense | Role |
| 16 | Senate | Org |
| 16 | National AI Initiative Act of 2020 | Legislation |
| 15 | Department of Defense | Org |

### Harms: Violation of civil or human rights (146 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 18 | House of Representatives | Org |
| 14 | Senate | Org |
| 12 | Federal Trade Commission | Org |
| 10 | National Institute of Standards and Technology | Org |
| 10 | Director | Role |

### Applications: Finance and investment (27 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 4 | Board of Governors of the Federal Reserve System | Org |
| 3 | Office of the Comptroller of the Currency | Org |
| 3 | Federal Deposit Insurance Corporation | Org |
| 3 | National Credit Union Administration | Org |
| 3 | Bureau of Consumer Financial Protection | Org |

### Applications: Transportation (28 docs)

| Co-oc | Entity | Type |
|---|---|---|
| 6 | Secretary of Transportation | Role |
| 6 | Federal Aviation Administration | Org |
| 3 | Infrastructure Investment and Jobs Act | Legislation |
| 3 | Department of Transportation | Org |

---

## 4. Highest PMI Entity–Tag Pairs (min 3 co-occurrences)

These are the most "surprising" associations — entities that concentrate in specific tags far more than base rates predict.

| PMI | Co-oc | Entity docs | Tag docs | Entity | Tag |
|---|---|---|---|---|---|
| 5.34 | 3 | 4 | 11 | [Role] attorney general | Arts, sports, leisure |
| 5.13 | 3 | 3 | 17 | [Leg] Scientific and Advanced-Technology Act of 1992 | Agriculture |
| 4.55 | 3 | 4 | 19 | [Leg] NSF Act of 1950 | Manufacturing |
| 4.36 | 3 | 3 | 29 | [Org] Committee on House Administration | Broadcasting and media |
| 4.31 | 3 | 5 | 18 | [Org] Cmte on Energy and Natural Resources (Senate) | Energy and utilities |
| 4.09 | 5 | 6 | 29 | [Org] Federal Election Commission | Broadcasting and media |
| 4.04 | 4 | 8 | 18 | [Office] Office of Science | Energy and utilities |
| 4.02 | 3 | 10 | 11 | [Leg] Title 18, United States Code | Imprisonment |
| 3.82 | 3 | 7 | 18 | [Office] Office of Electricity | Energy and utilities |
| 3.68 | 5 | 8 | 29 | [Leg] Federal Election Campaign Act of 1971 | Broadcasting and media |
| 3.53 | 6 | 11 | 28 | [Role] Secretary of Transportation | Transportation |
| 3.51 | 6 | 24 | 13 | [Role] Director of NSF | Subsidies |
| 3.41 | 6 | 12 | 28 | [Org] Federal Aviation Administration | Transportation |
| 3.22 | 4 | 15 | 17 | [Role] Secretary of Agriculture | Agriculture |
| 3.14 | 4 | 10 | 27 | [Org] Board of Governors, Federal Reserve | Finance and investment |
| 3.10 | 7 | 27 | 18 | [Org] National Laboratories | Energy and utilities |
| 2.93 | 5 | 23 | 17 | [Org] Department of Agriculture | Agriculture |
| 2.85 | 4 | 11 | 30 | [Leg] Elementary and Secondary Education Act | Education |

**Interpretation:** Domain-specific entities show strong PMI with their expected tags. Energy entities (National Labs, Office of Electricity, Office of Science) cluster tightly with "Energy and utilities." Financial regulators (Fed, OCC, FDIC, NCUA) cluster with "Finance and investment." The FEC and FECA cluster with "Broadcasting and media" — likely AI in elections/political ads legislation.

---

## 5. Tag-Specific Entities

Entities where >60% of their document appearances carry a single tag (min 5 docs):

| Concentration | Entity | Tag |
|---|---|---|
| 100% (6/6) | Office of Under Secretary of Defense for A&S | Military and public safety |
| 100% (6/6) | Congressional defense committees | Military and public safety |
| 100% (6/6) | Administrator of General Services | Government study or report |
| 100% (6/6) | Office of Chief Digital and AI Officer | Government study or report |
| 100% (6/6) | Director of DARPA | Government study or report |
| 100% (5/5) | Deputy Secretary of Defense | Military and public safety |
| 100% (5/5) | Vice Chairman, Joint Chiefs of Staff | Military and public safety |
| 100% (5/5) | Under Secretary of Defense for Policy | Military and public safety |
| 100% (5/5) | Under Secretary of Defense for Intel & Security | Military and public safety |
| 100% (5/5) | Nat'l AI Advisory Committee | Convening |
| 94% (17/18) | General Services Administration | Government study or report |
| 94% (15/16) | Under Secretary of Defense for A&S | Military and public safety |
| 92% (12/13) | NDAA FY2024 | Military and public safety |
| 88% (7/8) | Joint Chiefs of Staff | Military and public safety |
| 88% (7/8) | Department of the Navy | Military and public safety |
| 87% (13/15) | NDAA FY2022 | Military and public safety |
| 85% (11/13) | Cmte on Armed Services (Senate) | Government study or report |
| 85% (11/13) | Cmte on Armed Services (House) | Government study or report |
| 83% (5/6) | Federal Election Commission | Broadcasting and media |
| 83% (5/6) | Library of Congress | Disclosure |
| 82% (14/17) | Director of OSTP | Government study or report |
| 82% (14/17) | Servicemember NDAA FY2025 | Military and public safety |
| 82% (9/11) | Office of Science and Technology Policy | Government support |

Defense entities almost never appear outside the military/public-safety tag. This suggests clean taxonomic separation for the defense policy cluster.

---

## 6. Tag–Tag Co-occurrence (via shared entities)

The number of distinct entities shared between two tags:

| Shared entities | Tag 1 | Tag 2 |
|---|---|---|
| 1,408 | Governance development | Government study or report |
| 1,317 | Evaluation | Government study or report |
| 1,229 | Convening | Government study or report |
| 1,114 | Government support | Government study or report |
| 994 | For R&D | Government study or report |
| 994 | Military and public safety | Government study or report |
| 958 | Government support | For R&D |
| 926 | Governance development | Disclosure |
| 916 | Governance development | Government support |
| 858 | AI workforce-related | Government study or report |

"Government study or report" co-occurs with nearly every other tag — it is the hub of the tag network, reflecting its role as the most common legislative strategy.

---

## 7. Entity Type Dominance Per Tag Category

| Category | Orgs | Legislation | Roles | Named docs | Offices |
|---|---|---|---|---|---|
| Applications (8,904) | 36.4% | 20.4% | 20.0% | 14.8% | 8.4% |
| Harms (3,983) | 34.9% | 28.4% | 19.9% | 10.0% | 6.9% |
| Incentives (2,452) | 32.5% | 32.7% | 18.1% | 8.8% | 7.7% |
| Risk factors (9,272) | 34.3% | 24.8% | 21.2% | 11.9% | 7.8% |
| Strategies (33,935) | 34.9% | 23.5% | 20.5% | 13.0% | 8.2% |

Roughly consistent across categories: Orgs dominate (~35%), followed by Legislation (~24%), then Roles (~20%). Notable: **Incentives** tags have the highest legislation share (32.7%) — penalties and subsidies are defined in statute more than in organizational structure. **Harms** tags also skew toward legislation references (28.4%).

---

## 8. Key Takeaways

1. **"Government study or report"** is the most common tag (301 docs, 51%) and co-occurs with everything — it is not very discriminating for entity analysis. Consider filtering it out in downstream analyses to reveal sharper associations.

2. **Domain-specific entities have clean tag separation.** Defense entities (SecDef, DoD, NDAAs, Joint Chiefs) concentrate almost exclusively in "Military and public safety." Financial regulators concentrate in "Finance and investment." Energy entities in "Energy and utilities." The NER pipeline is producing entities that are taxonomically coherent.

3. **FTC is the cross-cutting regulatory entity.** It appears in Disclosure, Transparency, Safety, Privacy, and civil rights tags — not concentrated in any single application domain. It is the general-purpose AI enforcement entity in this corpus.

4. **NIST straddles Evaluation and Governance.** It co-occurs almost equally with "Evaluation," "Governance development," and "Disclosure" tags — reflecting its standards-setting role.

5. **Incentives tags are sparse** (2,452 total co-occurrences vs. 33,935 for Strategies) but have the highest legislation concentration. This is consistent — penalties, fines, and subsidies are defined in statutory text, not organizational structure.

6. **The PMI analysis surfaces niche but real associations** (FEC + Broadcasting/media, National Labs + Energy, Fed + Finance) that raw co-occurrence counts would bury under the DoD/Congress signal.
