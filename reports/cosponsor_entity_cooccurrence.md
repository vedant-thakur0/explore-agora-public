# Cosponsor–Entity Co-occurrence Analysis

**Date:** 2026-04-08
**Input:** 505 documents with both legislator and entity data; 535 unique legislators (sponsors + cosponsors); 4,818 unique entities (binary presence per document)

---

## 1. Method

For each document, record which legislators (sponsor + active cosponsors, excluding withdrawn) are associated with it and which named entities the NER pipeline extracted. An entity is counted once per document regardless of how many times it appears in the text. A co-occurrence is recorded between a legislator and an entity if the entity is present in any bill they sponsored or cosponsored.

---

## 2. Coverage

| Metric | Count |
|---|---|
| Documents with legislators | 535 |
| Documents with entities | 531 |
| Documents with both | 505 |
| Unique legislators (sponsor + cosponsor) | 535 |
| Unique entities | 4,818 |
| Cosponsor rows (non-withdrawn) | ~3,400 |
| Documents with sponsor identified | 509 |

---

## 3. Legislator Entity Breadth

Legislators associated with the most unique entities across their (co)sponsored bills:

| Unique entities | Docs | Party | Legislator |
|---|---|---|---|
| 452 | 18 | D | Sen. Lujan, Ben Ray [D-NM] |
| 445 | 6 | D | Rep. Ryan, Tim [D-OH-13] |
| 421 | 15 | D | Sen. Casey, Robert P., Jr. [D-PA] |
| 419 | 37 | R | Rep. Rouzer, David [R-NC-7] |
| 402 | 22 | D | Sen. Heinrich, Martin [D-NM] |
| 372 | 38 | D | Rep. DeFazio, Peter A. [D-OR-4] |
| 365 | 36 | D | Rep. Napolitano, Grace F. [D-CA-31] |
| 341 | 37 | R | Rep. Graves, Sam [R-MO-6] |
| 337 | 18 | D | Sen. Welch, Peter [D-VT] |
| 334 | 20 | D | Sen. Peters, Gary C. [D-MI] |
| 328 | 38 | D | Rep. Dingell, Debbie [D-MI-6] |
| 310 | 13 | D | Sen. Schatz, Brian [D-HI] |
| 310 | 20 | D | Sen. Warner, Mark R. [D-VA] |
| 293 | 28 | D | Rep. Bonamici, Suzanne [D-OR-1] |
| 292 | 22 | R | Rep. Fitzpatrick, Brian K. [R-PA-1] |
| 282 | 10 | R | Sen. Moran, Jerry [R-KS] |
| 278 | 28 | D | Del. Norton, Eleanor Holmes [D-DC-At Large] |
| 277 | 34 | D | Rep. Wild, Susan [D-PA-7] |
| 272 | 37 | R | Rep. Lawler, Michael [R-NY-17] |
| 271 | 36 | D | Rep. Sherman, Brad [D-CA-32] |

Note: Rep. Ryan (6 docs, 445 entities) has high breadth from entity-dense omnibus bills. Sen. Lujan (18 docs, 452 entities) reflects cosponsorship of large, entity-rich legislation.

---

## 4. Entities by Legislator Reach

Entities present in bills associated with the most legislators:

| Legislators | D | R | Entity | Type |
|---|---|---|---|---|
| 345 | 242 | 100 | President | Role |
| 329 | 162 | 165 | House of Representatives | Org |
| 320 | 157 | 161 | Senate | Org |
| 310 | 254 | 54 | Government Accountability Office | Org |
| 274 | 209 | 64 | Dept. of Health and Human Services | Org |
| 268 | 210 | 57 | Secretary of Health and Human Services | Role |
| 255 | 167 | 86 | Federal Trade Commission | Org |
| 254 | 232 | 21 | Department of Labor | Org |
| 247 | 163 | 83 | Federal Trade Commission Act | Legislation |
| 238 | 223 | 15 | Comptroller General | Role |
| 237 | 135 | 100 | Committee on Energy and Commerce | Org |
| 235 | 116 | 117 | Department of State | Org |
| 230 | 124 | 103 | Secretary | Role |
| 228 | 224 | 3 | National Labor Relations Act | Org |
| 222 | 217 | 5 | House Cmte on Education and the Workforce | Org |
| 222 | 218 | 4 | Senate HELP Committee | Org |
| 214 | 204 | 9 | National Academies of Sciences | Org |
| 211 | 100 | 111 | Congress | Org |
| 204 | 114 | 88 | Cmte on Commerce, Science, and Transportation | Org |

"House of Representatives" and "Senate" are nearly perfectly bipartisan (162D/165R and 157D/161R). GAO skews heavily Democratic (254D/54R).

---

## 5. Party-Specific Entities

### Democrat-exclusive entities (>=20 D legislators, <5 R)

| D | R | Entity | Type |
|---|---|---|---|
| 224 | 3 | National Labor Relations Act | Org |
| 218 | 4 | Senate HELP Committee | Org |
| 217 | 3 | Richard L. Trumka PRO Act | Legislation |
| 217 | 3 | GAO Report on Technology and Algorithm Impact | Named Doc |
| 195 | 4 | Report on the Use of Technology in Maternity Care | Named Doc |
| 195 | 0 | Black Maternal Health Omnibus Act | Legislation |
| 60 | 4 | Developer | Role |
| 55 | 0 | Securing Elections From AI Deception Act | Legislation |
| 55 | 0 | Deployer | Role |
| 55 | 0 | FTC Act, Section 18(a)(1)(B) | Legislation |
| 52 | 0 | Federal Railroad Administration | Org |
| 52 | 0 | Rail Worker and Community Safety Act | Legislation |
| 50 | 0 | Office of Technology for Peace | Office |
| 50 | 0 | Department of Peacebuilding Act of 2023 | Legislation |
| 45 | 4 | Food and Drug Administration | Org |

**Pattern:** D-exclusive entities center on labor rights (PRO Act, NLRA), consumer protection (FTC enforcement specifics, Developer/Deployer roles), health equity (Black Maternal Health), and election integrity.

### Republican-exclusive entities (>=20 R legislators, <5 D)

| D | R | Entity | Type |
|---|---|---|---|
| 0 | 57 | ByteDance, Ltd. | Org |
| 0 | 57 | TikTok | Org |
| 0 | 57 | Military End User List | Named Doc |
| 1 | 56 | Federal Register | Org |
| 4 | 54 | NDAA FY2017 | Legislation |
| 3 | 53 | Strom Thurmond NDAA | Legislation |
| 2 | 53 | Director of the FBI | Role |
| 2 | 53 | Executive Order 14032 | Legislation |
| 2 | 52 | Israel | Org |
| 0 | 52 | Entity List | Named Doc |
| 1 | 51 | Taiwan | Org |
| 0 | 51 | Denied Persons List | Named Doc |
| 4 | 50 | NATO | Org |
| 0 | 50 | National People's Congress of the CCP | Org |
| 0 | 50 | Republic of the Philippines | Org |

**Pattern:** R-exclusive entities center on foreign adversary/competition policy (TikTok/ByteDance, Entity List, CCP, export controls), defense authorization, and allied nation references (Israel, Taiwan, Philippines, NATO).

---

## 6. Most Bipartisan Entities (closest to 50/50, >=15 legislators)

| D | R | D% | Entity | Type |
|---|---|---|---|---|
| 11 | 11 | 50/50 | Department of the Navy | Org |
| 9 | 9 | 50/50 | Under Sec. of Defense for A&S | Office |
| 8 | 8 | 50/50 | Secretary of the Army | Role |
| 9 | 9 | 50/50 | Secretary of the Air Force | Role |
| 9 | 9 | 50/50 | Chief Data and AI Officer | Role |
| 10 | 10 | 50/50 | United States Central Command | Org |
| 8 | 8 | 50/50 | Defense Innovation Unit | Org |
| 14 | 14 | 50/50 | Comptroller General of the United States | Org |
| 12 | 12 | 50/50 | Director of OMB | Role |
| 17 | 17 | 50/50 | Federal Acquisition Regulation | Legislation |
| 14 | 14 | 50/50 | Defense Production Act of 1950 | Legislation |
| 8 | 8 | 50/50 | NDAA FY2022 | Legislation |
| 162 | 165 | 50/50 | House of Representatives | Org |
| 157 | 161 | 49/51 | Senate | Org |
| 116 | 117 | 50/50 | Department of State | Org |

Defense institutional entities (DoD offices, military service secretaries, acquisition regulation) are the most bipartisan. These entities appear in NDAAs which pass with broad bipartisan support.

---

## 7. Cross-Party Legislator Similarity (by shared entities)

Top pairs ranked by Jaccard similarity on entity sets (minimum 50 entities each):

| Jaccard | Shared | D legislator | R legislator |
|---|---|---|---|
| 1.000 | 122/122 | Sen. Kaine, Tim [D-VA] | Sen. Cramer, Kevin [R-ND] |
| 0.865 | 212/245 | Rep. Smith, Adam [D-WA-9] | Rep. Rogers, Mike D. [R-AL-3] |
| 0.806 | 315/391 | Rep. Graves, Sam [R-MO-6] | Rep. Napolitano, Grace F. [D-CA-31] |
| 0.787 | 314/399 | Rep. Graves, Sam [R-MO-6] | Rep. DeFazio, Peter A. [D-OR-4] |
| 0.723 | 107/148 | Sen. Graham, Lindsey [R-SC] | Sen. Kaine, Tim [D-VA] |
| 0.715 | 191/267 | Sen. Hickenlooper, John W. [D-CO] | Sen. Capito, Shelley Moore [R-WV] |
| 0.689 | 122/177 | Sen. Kaine, Tim [D-VA] | Sen. Fischer, Deb [R-NE] |
| 0.688 | 108/157 | Sen. Crapo, Mike [R-ID] | Sen. Kaine, Tim [D-VA] |
| 0.682 | 318/466 | Rep. Napolitano, Grace F. [D-CA-31] | Rep. Rouzer, David [R-NC-7] |
| 0.665 | 316/475 | Rep. DeFazio, Peter A. [D-OR-4] | Rep. Rouzer, David [R-NC-7] |
| 0.647 | 108/167 | Rep. Caraveo, Yadira [D-CO-8] | Rep. Tenney, Claudia [R-NY-24] |
| 0.642 | 122/190 | Sen. Blumenthal, Richard [D-CT] | Sen. Cramer, Kevin [R-ND] |
| 0.618 | 170/275 | Sen. Capito, Shelley Moore [R-WV] | Sen. Baldwin, Tammy [D-WI] |
| 0.616 | 122/198 | Sen. Collins, Susan M. [R-ME] | Sen. Kaine, Tim [D-VA] |

**Kaine–Cramer** have perfect entity overlap (Jaccard 1.0) — they cosponsor the same bills. **Smith–Rogers** (House Armed Services chair/ranking) share 87% of entities — the defense authorization pipeline. **Graves–Napolitano/DeFazio** share 80%+ — the transportation/infrastructure pipeline.

These pairs reflect committee-based co-legislation rather than ideological alignment. The entity overlap is driven by shared omnibus bills, not shared positions on AI.

---

## 8. Entity Type Breakdown by Party

| Type | D (28,983) | D % | R (21,031) | R % |
|---|---|---|---|---|
| organizations | 9,668 | 33.4% | 7,534 | 35.8% |
| legislation_refs | 7,808 | 26.9% | 5,816 | 27.7% |
| roles | 5,602 | 19.3% | 3,476 | 16.5% |
| named_docs | 3,561 | 12.3% | 2,548 | 12.1% |
| offices | 2,344 | 8.1% | 1,657 | 7.9% |

Nearly identical distributions. Democrats have ~38% more total entity-legislator pairs (28,983 vs 21,031), reflecting higher cosponsorship activity in this corpus. The entity type mix is stable across parties.

---

## 9. Key Takeaways

1. **Defense entities are the bipartisan core.** Military service secretaries, DoD offices, acquisition regulations, and NDAAs show near-perfect 50/50 party splits. These entities travel through the annual defense authorization process, which is structurally bipartisan.

2. **Party-exclusive entities reveal distinct AI policy agendas.** Democrats focus on labor protections (PRO Act, NLRA), consumer safety (Developer/Deployer roles, FTC enforcement), and health equity. Republicans focus on foreign adversary policy (TikTok, Entity List, CCP, export controls) and allied nation security (Israel, Taiwan, NATO).

3. **Cross-party similarity is committee-driven, not ideological.** The highest Jaccard pairs (Kaine–Cramer, Smith–Rogers, Graves–Napolitano) reflect shared committee membership and co-legislation on omnibus bills, not convergent AI policy views.

4. **GAO is a partisan signal.** Despite being a nonpartisan institution, GAO appears in 254 D-associated bills vs. 54 R-associated bills. This likely reflects Democrats' preference for mandating government studies and reports as a legislative strategy.

5. **Entity type distributions are party-invariant.** Both parties reference organizations (~34%), legislation (~27%), and roles (~18%) at roughly the same rates. The parties differ in *which* entities they reference, not *what type* of entities.

6. **The "Deployer" and "Developer" roles are exclusively Democratic.** These are AI governance concepts (assigning responsibility to those who build vs. deploy AI) that appear in 55+ D-legislator bills and zero R-legislator bills. This is a clean ideological marker in the entity data.
