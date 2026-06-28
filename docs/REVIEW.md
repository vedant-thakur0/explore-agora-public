# Notebook Review — Current State Ledger

Last updated: 2026-06-14

Tracks correctness bugs and misleading analyses across `01_sponsor_profiling.ipynb`, `02_policy_networks.ipynb`, `03_coalitions.ipynb`, `04_taxonomy.ipynb`, and shared `analysis_utils.py`. Items are marked with their current status.

---

## Bugs (crash or wrong numbers)

### [FIXED] 01 · Cell 10 — NameError
```python
au.sponsor_taxonomy_profile(docs_df, cosponsors_df, group="Strategies")
```
Variable was `cosp_df`, not `cosponsors_df`. Fixed: corrected variable name.

### [FIXED — perf, numbers unaffected] 02 · Cell 12 — betweenness recomputed in loop
`betweenness_centrality` was recomputed for the whole graph on every node iteration. Fixed: called once outside the loop and indexed into the result.

### [FIXED] 03 · Cell 3 — chamber inference inconsistent with module 1
`Del.` and Resident Commissioners were silently misclassified as House. Fixed: aligned with the three-way Senate/House/Unknown pattern from module 1.

### [FIXED] 03 · Cell 7 — bridge legislators included isolated nodes
`G_cross` was built with all nodes from `G_cc`, including zero-degree isolated nodes. Fixed: filtered to `degree > 0` before ranking.

---

## Misleading analyses

### [FIXED — 2026-06-14] 01 · Cell 8 — chamber averages biased by cross-chamber bills
**Was:** `doc_chamber["House"].mean()` averaged House cosponsors across ALL bills, including Senate-originated bills (which contribute 0 House cosponsors). This biased the per-chamber average downward.

**Fix applied (relabel, not conditioning):** Conditioning on the *primary sponsor's* chamber
is **not possible** — the comprehensive CSV (`agora_comprehensive_data_with_cosponsor_lists.csv`,
loaded via `au.load_comprehensive_df()`) carries no primary-sponsor name or chamber column. So the
metric is relabeled honestly instead: it now reports the **dataset-wide average number of Senate /
House cosponsors per bill** (averaged over every bill, including 0s), with an inline note that it is
NOT a per-sponsoring-chamber comparison. The misleading "by chamber" framing (which implied sponsor
chamber) is removed; the section header is updated to match. Variables used (`cosp_df`, `docs_df`,
`doc_chamber`) are all defined earlier in the notebook.

### [STILL-LIVE — perf-only, numbers unaffected] analysis_utils · `build_cosponsor_cosponsor_graph` — O(S²)
Set intersections per sponsor pair. Fine at current scale; will hurt past a few thousand sponsors. A bill→sponsors inversion with per-bill pair enumeration would be faster. Does not affect any output numbers.

### [STILL-LIVE — display only] 02 · Cell 12 — t-SNE on 3 features
t-SNE on a 3-dim feature vector (degree, betweenness, clustering) does not unfold a high-dim manifold. PCA or a direct scatter of two features would be more interpretable. Does not affect underlying data or numbers output elsewhere.

### [STILL-LIVE — display only] 04 · Cells 3 / 5 — "top-level" filter is fragile
`:` filter on taxonomy column names is fragile against AGORA naming changes. Does not corrupt existing output given current label conventions; risk is future label drift.

### [STILL-LIVE — display only] 04 · Cell 7 — community radar has no min-size filter
Small communities spike to 100% on narrow tags and visually dominate the radar. Cosmetic; underlying data is correct.

### [STILL-LIVE — display only] 04 · Cell 11 — risk treemap hierarchy is mostly flat
Parent inferred from `: ` split, but stripped labels rarely contain `:`. Hierarchy is essentially flat. Cosmetic; underlying data is correct.

---

## Smaller issues

| Item | Status |
|------|--------|
| 01 · Cell 12 — O(N²) bio lookup inside loop | STILL-LIVE (perf-only) |
| 02 · Cells 7/9 — stripped label node ID collision | STILL-LIVE (low risk at current label set) |
| 01 · Cell 11 — fingerprint heatmap may include blank rows | STILL-LIVE (cosmetic) |
| All four — `load_communities` shape not validated | STILL-LIVE (schema drift risk) |

---

## Original fix priority (historical)

1. `01 · Cell 10` — crash → **FIXED**
2. `02 · Cell 12` — betweenness perf → **FIXED**
3. `03 · Cell 3` — chamber inference wrong numbers → **FIXED**
4. `03 · Cell 7` — bridge filter wrong rankings → **FIXED**
5. `01 · Cell 8` — chamber average biased → **FIXED 2026-06-14**

All items that produce incorrect output numbers are now resolved. Remaining open items are performance or display issues only.
