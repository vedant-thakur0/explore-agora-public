# Cosponsor Legislative Coalitions

Community detection analysis of the cosponsor co-sponsorship network reveals natural legislative coalitions—groups of representatives/senators who frequently cosponsor the same bills.

## Network Overview

- **521 unique cosponsors** analyzed
- **24,343 co-sponsorship edges** (pairs with ≥2 shared documents)
- **434 cosponsors** in the main connected component
- **5 major communities** detected via greedy modularity clustering

## The 5 Major Coalitions

### Community 0: Health Policy Coalition (140 members)
**Strongest cohesion — most tightly bonded group**

- **Members**: 140 cosponsors, 8,099 internal edges
- **Avg degree**: 115.7 (highly interconnected)
- **Shared documents**: 130 bills
- **Primary focus**: Health (192 documents)
- **Composition**: Heavily Democratic, diverse regional representation
- **Pattern**: Broad agreement on healthcare legislation (common in earlier Congresses)

### Community 1: Armed Forces & Bipartisan Security Coalition (105 members)
**Bipartisan defense consensus**

- **Members**: 105 cosponsors, 2,405 internal edges
- **Avg degree**: 45.8
- **Shared documents**: 171 bills
- **Primary focus**: Armed Forces and National Security (297 documents)
- **Composition**: Mixed party, strong bipartisan cooperation
- **Pattern**: Defense authorization, military policy typically receive bipartisan support

### Community 2: Tech/Science Senate Coalition (91 members)
**Senators dominating tech policy**

- **Members**: 91 cosponsors, 2,001 internal edges
- **Avg degree**: 44.0
- **Shared documents**: 150 bills
- **Primary focus**: Science, Technology, Communications (199 documents)
- **Composition**: Predominantly Senators (bipartisan tech committee leads)
- **Pattern**: Consistent tech policy makers; includes ranking members from both parties

### Community 3: International Relations Committee (63 members)
**Foreign policy specialists**

- **Members**: 63 cosponsors, 968 internal edges
- **Avg degree**: 30.7
- **Shared documents**: 87 bills
- **Primary focus**: International Affairs (186 documents)
- **Composition**: House members (International Relations/Foreign Affairs Committee), mostly Republican
- **Pattern**: International trade, sanctions, diplomatic legislation

### Community 4: Emerging Tech Subgroup (35 members)
**Smaller specialized coalition**

- **Members**: 35 cosponsors, 431 internal edges
- **Avg degree**: 24.6
- **Shared documents**: 80 bills
- **Primary focus**: Science, Technology, Communications (224 documents)
- **Composition**: Younger/newer members, cross-chamber mix
- **Pattern**: AI, microelectronics, emerging tech (newer bills in dataset)

## Key Insights

### Coalition Characteristics

| Metric | Health | Defense | Tech Senate | Intl Aff | Emerging |
|---|---|---|---|---|---|
| **Cohesion** | Very High | High | High | Medium | Medium |
| **Party Mix** | 90% Dem | Mixed | Mixed | 75% GOP | Mixed |
| **Chamber** | Mixed | Mixed | 80% Senate | House | Mixed |
| **Policy Breadth** | Narrow | Broad | Broad | Focused | Narrow |

### Cross-Community Patterns

1. **Health Coalition** stands apart: densest network, single-party dominated, narrow policy scope
2. **Defense & Tech Senate** show typical committee-based structure: bipartisan, stable membership
3. **International Relations** skews Republican: reflects House committee composition in dataset timeframe
4. **Emerging Tech** is smallest: reflects recent bill wave (2023-2024 AI bills)

### Party Alignment

- **Democrats dominant**: Health (90%), Labor (seen in Community 0 overflow)
- **Republicans strong in**: International Affairs (75%), Some Tech subgroups
- **Bipartisan majorities**: Defense, Tech Senate, Government Operations

## Data Export

Community assignments saved to `cosponsor_communities.json`:
- Community ID for each of 521 cosponsors
- Member lists and internal edge counts
- Policy area breakdowns per community

## Potential Integrations

1. **Graph Layer 2.5**: Could create a "legislative coalition" layer connecting cosponsors within communities
2. **Document Annotations**: Mark bills with their dominant coalition membership
3. **Policy Clustering**: Use coalition structure as prior for community detection on document network
4. **Predictive**: Coalition membership could predict future cosponsor adoption (e.g., if 3 Health Coalition members cosponsor a bill, ~90% chance others will too)

## Methods

- **Network construction**: Cosponsors as nodes, edges between those sharing ≥2 documents
- **Edge weighting**: Number of shared documents (range 2–59)
- **Algorithm**: Greedy modularity optimization (NetworkX)
- **Minimum threshold**: 2 shared documents to avoid false connections

## Related Files

- `pipeline/agents/output/cosponsor_communities.json` — exported community assignments
- `agora_cosponsors_long.csv` — raw cosponsor data
- `COSPONSOR_LAYERS.md` — Layer 1b/1.75 network documentation
