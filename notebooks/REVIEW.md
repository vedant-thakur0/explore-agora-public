# Notebook Review

Evaluation of `01_sponsor_profiling.ipynb`, `02_policy_networks.ipynb`, `03_coalitions.ipynb`, `04_taxonomy.ipynb` and shared `analysis_utils.py`. Ordered by severity.

## Bugs (will break or produce wrong numbers)

### 01_sponsor_profiling.ipynb · Cell 10 — NameError
```python
au.sponsor_taxonomy_profile(docs_df, cosponsors_df, group="Strategies")
```
The loaded variable is `cosp_df`, not `cosponsors_df`. Cell crashes on first run.

### 02_policy_networks.ipynb · Cell 12 — severe perf bug in t-SNE loop
```python
for node in nodes_list:
    betweenness = nx.betweenness_centrality(G_area).get(node, 0)
```
`betweenness_centrality` is recomputed for the whole graph on every iteration. Call once outside the loop and index into the result. For ~14 policy areas this turns minutes into hours.

### 03_coalitions.ipynb · Cell 3 — chamber inference inconsistent with module 1
```python
lambda x: "Senate" if str(x).startswith("Sen.") else "House"
```
Module 1 uses three-way Senate/House/Unknown. Here, Delegates (`Del.`) and Resident Commissioners are silently misclassified as House, biasing per-community Senate/House counts in `profiles_df`.

### 03_coalitions.ipynb · Cell 7 — bridge legislators include isolated nodes
`G_cross` is built with `add_nodes_from(G.nodes(data=True))` then only cross-party edges added. Every node in `G_cc` ends up in `G_cross`, including isolated nodes with no cross-party links. `bridge_df.head(15)` and the "Top 100" scatter mix in zero-betweenness, zero-cross-degree members. Filter to `n for n in G_cross.nodes() if G_cross.degree(n) > 0` before ranking.

## Misleading analyses

### 01 · Cell 8 — chamber averages
`doc_chamber["House"].mean()` averages House cosponsors across all bills including Senate-only bills, so the value is biased downward by Senate-origin bills with 0 House cosponsors (and vice versa). Either condition on the primary sponsor's chamber, or relabel as "average per bill in dataset" rather than "by chamber".

### 02 · Cell 12 — t-SNE on 3 features
t-SNE on a 3-dim feature vector (degree, betweenness, clustering) isn't doing what readers think — there's no high-dim manifold to unfold. PCA, or just scatter-plotting two of the three features, would be more honest.

### 04 · Cells 3 / 5 — "top-level" filter is fragile
```python
top_level = [c for c in comm_strat_norm.columns if ":" not in c and len(c) > 2]
```
`taxonomy_vector` already strips the group prefix, so `:` only survives if a sub-category label itself contains one. If AGORA naming changes (flat labels), this filter silently keeps everything; if labels use `:` inconsistently across groups, top-level/sub-level membership is wrong. Drive this from the source column names before stripping.

### 04 · Cell 7 — community radar has no min-size filter
A 3-member community with one bill on biometrics spikes to 100% on that application and visually dominates the radar against a 50-member community with diversified focus. Add a `len(aids) >= N` gate or normalize differently.

### 04 · Cell 11 — risk treemap hierarchy is mostly flat
`parent` is inferred by `rf.split(": ", 1)`, but since `taxonomy_vector` strips the prefix, most labels have no `:` and default to the synthetic parent `"Risk Factors"`. The hierarchy is essentially flat except where sub-labels happen to embed a colon. Build parent from the original column-name prefix before stripping.

## Smaller issues

- **01 · Cell 12** — `cosp_df.loc[cosp_df["Cosponsor_BioguideId"] == bios[i], …].iloc[0]` inside an O(N²) loop. Build `bio_party` once (as 03/04 do) and look up.
- **02 · Cells 7 / 9** — `build_taxonomy_cooccurrence_graph` uses stripped labels as node IDs. If two groups share a stripped label (e.g. "Privacy" in both Harms and Risk Factors), the `group` attribute is overwritten by whichever is added last and the matrix mis-routes.
- **01 · Cell 11** — fingerprint heatmap uses `sponsor_degrees.head(30)`, which may include sponsors with zero taxonomy tags (blank row). Filter to `fingerprint.sum(axis=1) > 0` first.
- **All four** — `load_communities` is assumed to return `[{"id": ..., "members": [...]}]`. None of the notebooks validate this shape; schema drift would produce opaque errors.
- **analysis_utils · `build_cosponsor_cosponsor_graph`** — O(S²) with set intersections per pair. Fine at current scale; will hurt past a few thousand sponsors. A bill→sponsors inversion with per-bill pair enumeration is faster.

## Fix priority

1. `01 · Cell 10` — crashes
2. `02 · Cell 12` — betweenness recompute (perf)
3. `03 · Cell 3` — chamber inference (wrong numbers)
4. `03 · Cell 7` — bridge filter (wrong rankings)
