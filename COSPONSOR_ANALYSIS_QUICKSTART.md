# Cosponsor Analysis — Quick Start for Large-Scale Research

## What You Have

**Complete sponsor/cosponsor network** across 622 AI policy documents from U.S. Congress:
- 521 unique cosponsors
- 24,343 co-sponsorship relationships
- 5 natural legislative coalitions identified
- Policy area mapped to all 23 policy domains

## Quick Access Paths

### Load & Explore

```python
import json, csv, networkx as nx
from pathlib import Path

# Load community assignments
communities = json.load(open("pipeline/agents/output/cosponsor_communities.json"))

# Load cosponsor network
G = nx.read_graphml("pipeline/multiplex_graph/layer_1b_cosponsor.graphml")

# Load raw cosponsor data
cosponsors = list(csv.DictReader(open("knowledge_graph/graph_data/agora_cosponsors_long.csv")))

# Load documents with policy areas
docs = list(csv.DictReader(open("knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv")))
```

### Key Queries

```python
# Get all cosponsors in a specific community
comm_0_members = communities["communities"][0]["members"]  # Health coalition

# Find cosponsors active in specific policy area
health_docs = {d["AGORA ID"] for d in docs if d["Policy_Area"] == "Health"}
health_cosponsors = {c["Cosponsor_BioguideId"] for c in cosponsors 
                     if c["AGORA ID"] in health_docs}

# Find cosponsors who frequently work together
shared_doc_count = {}
for bio1, bio2 in G.edges():
    weight = G[bio1][bio2].get("weight", 1)  # Number of shared documents
    shared_doc_count[(bio1, bio2)] = weight

# Party composition of a community
members = communities["communities"][0]["members"]
member_info = {c["Cosponsor_BioguideId"]: c["Cosponsor_Party"] 
               for c in cosponsors if c["Cosponsor_BioguideId"] in members}
```

## Five Legislative Coalitions

| ID | Name | Size | Cohesion | Dominant Policy | Party Mix |
|----|------|------|----------|---|---|
| 0 | **Health** | 140 | ⭐⭐⭐⭐⭐ Very High | Health (192 docs) | 90% Dem |
| 1 | **Armed Forces** | 105 | ⭐⭐⭐⭐ High | Defense (297 docs) | Bipartisan |
| 2 | **Tech Senate** | 91 | ⭐⭐⭐⭐ High | Sci/Tech (199 docs) | Mixed, Senate-led |
| 3 | **Intl Affairs** | 63 | ⭐⭐⭐ Medium | International (186 docs) | 75% GOP, House-led |
| 4 | **Emerging Tech** | 35 | ⭐⭐ Lower | AI/Microtech (224 docs) | Mixed, newer members |

## Policy Engagement

Top sectors by unique cosponsor diversity:

1. **Health**: 313 unique sponsors (most cross-partisan)
2. **Science/Tech**: 260 sponsors (broadest coalition)
3. **Labor/Employment**: 249 sponsors
4. **Armed Forces**: 103 sponsors (concentrated)
5. **Government Ops**: 161 sponsors

## Research Angles

### Immediate
- **Committee correlation**: Do community members overlap with House/Senate committees?
- **Temporal patterns**: When do cosponsors join bills (early vs. bandwagon effect)?
- **Bill outcomes**: Do bills with denser cosponsor clusters pass more often?

### Medium-term
- **Ideology estimation**: Use cosponsor patterns to score sponsors on AI policy spectrum
- **Prediction model**: Given 2-3 early cosponsors, predict final cosponsor set
- **Alliance stability**: Do coalitions persist across bill categories?

### Long-term
- **Influence networks**: Identify opinion leaders (early signers who attract others)
- **Cross-chamber dynamics**: How do House/Senate coalitions differ?
- **AI policy specialization**: Is there a distinct "AI expert" subgroup?

## Data Quality Notes

- ✅ 581/622 documents have ≥1 cosponsor (93% coverage)
- ✅ All 521 cosponsors matched to Congress.gov BioGuide IDs
- ✅ Party/state/district standardized
- ⚠️ Only 2 withdrawals tracked (uncommon event)
- ⚠️ Congress-only scope (no state/local legislators)

## Files to Know

| File | Purpose | Rows |
|------|---------|------|
| `agora_cosponsors_long.csv` | Raw cosponsor data (one per doc-person pair) | 3,500 |
| `agora_comprehensive_data_with_cosponsor_lists.csv` | Documents with policy areas & cosponsor counts | 622 |
| `cosponsor_nodes.csv` | Unique cosponsors (SponsorRecord format) | 520 |
| `cosponsor_edges.csv` | Co-sponsorship relationships | 23,710 |
| `cosponsor_communities.json` | Detected coalitions & memberships | JSON |
| `layer_1b_cosponsor.graphml` | Full network in GraphML format | 959 nodes, 23K edges |

## Build/Rebuild

```bash
# Full cosponsor build (5-10 seconds)
python3 -m pipeline.cli build-multiplex-graph \
  --sponsors-csv knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv \
  --cosponsors-csv knowledge_graph/graph_data/agora_cosponsors_long.csv \
  --agents sponsor

# Check output
ls pipeline/agents/output/cosponsor*
ls pipeline/multiplex_graph/layer_1*.graphml
```

## For Opus: Suggested Analyses

**If tasked with large-scale systemic analysis**, prioritize:

1. **Community-to-committee mapping** (immediate ROI)
   - Validate that detected coalitions align with actual committees
   - Identify over/under-represented policy areas in each coalition

2. **Temporal evolution** (medium effort, high insight)
   - Track community membership changes across Congressional sessions
   - Identify stable vs. volatile alliance patterns

3. **Ideology inference** (moderate effort)
   - Use cosponsor patterns to create AI policy ideology scores
   - Compare with other indices (DW-NOMINATE, etc.)

4. **Prediction pipeline** (lower priority, nice-to-have)
   - Train model: given initial cosponsors → predict final set
   - Evaluate: do early cosponsors predict bill success?

---

**All code committed to `trial` branch. Data freshness: 2026-03-31. Network topology stable.**
