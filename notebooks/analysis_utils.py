"""
Shared graph utilities for AGORA sponsor analysis modules.

Graph-first design: all queries expressed as NetworkX operations.
Computational minimalism: lazy loading, no redundant copies.
"""

import csv
import json
from pathlib import Path
from itertools import combinations
from collections import defaultdict

import networkx as nx
import pandas as pd

# ── Path constants ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
GRAPH_DATA = ROOT / "knowledge_graph" / "graph_data"
MULTIPLEX_DIR = ROOT / "pipeline" / "multiplex_graph"
AGENTS_OUTPUT = ROOT / "pipeline" / "agents" / "output"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"

COSPONSORS_CSV = GRAPH_DATA / "agora_cosponsors_long.csv"
COMPREHENSIVE_CSV = GRAPH_DATA / "agora_comprehensive_data_with_cosponsor_lists.csv"
COSPONSOR_NODES_CSV = AGENTS_OUTPUT / "cosponsor_nodes.csv"
COSPONSOR_EDGES_CSV = AGENTS_OUTPUT / "cosponsor_edges.csv"
SPONSOR_NODES_CSV = AGENTS_OUTPUT / "sponsor_nodes.csv"
SPONSOR_EDGES_CSV = AGENTS_OUTPUT / "sponsor_edges.csv"
COMMUNITIES_JSON = AGENTS_OUTPUT / "cosponsor_communities.json"

# ── AGORA taxonomy column groups ────────────────────────────────────────────

TAXONOMY_GROUPS = {
    "Applications": "Applications:",
    "Harms": "Harms:",
    "Risk Factors": "Risk factors:",
    "Strategies": "Strategies:",
    "Incentives": "Incentives:",
}


# ── Data loading ────────────────────────────────────────────────────────────

def load_comprehensive_df() -> pd.DataFrame:
    """Load the enriched documents CSV with all taxonomy columns."""
    return pd.read_csv(COMPREHENSIVE_CSV, low_memory=False)


def load_cosponsors_df() -> pd.DataFrame:
    """Load the long-format cosponsor CSV."""
    return pd.read_csv(COSPONSORS_CSV)


def load_communities() -> list[dict]:
    """Load pre-computed cosponsor communities."""
    with open(COMMUNITIES_JSON) as f:
        return json.load(f)


def load_graphml(name: str) -> nx.MultiDiGraph:
    """Load a multiplex layer by name (e.g. 'layer_1b_cosponsor')."""
    path = MULTIPLEX_DIR / f"{name}.graphml"
    return nx.read_graphml(path)


# ── Taxonomy helpers ────────────────────────────────────────────────────────

def get_taxonomy_columns(df: pd.DataFrame, group: str) -> list[str]:
    """Return column names belonging to a taxonomy group.

    Args:
        group: One of 'Applications', 'Harms', 'Risk Factors', 'Strategies', 'Incentives'
    """
    prefix = TAXONOMY_GROUPS[group]
    return [c for c in df.columns if c.startswith(prefix)]


def taxonomy_vector(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """Extract a binary taxonomy matrix for a group, with short column labels."""
    cols = get_taxonomy_columns(df, group)
    prefix = TAXONOMY_GROUPS[group]
    matrix = df[cols].fillna(0).astype(int)
    matrix.columns = [c.replace(prefix, "").strip().lstrip(": ") for c in cols]
    return matrix


def sponsor_taxonomy_profile(docs_df: pd.DataFrame, cosponsors_df: pd.DataFrame,
                              group: str) -> pd.DataFrame:
    """Build a sponsor × taxonomy-tag frequency matrix.

    For each sponsor (by bioguide), sums the taxonomy binary flags across
    all documents they co-sponsored.
    """
    tax = taxonomy_vector(docs_df, group)
    tax["AGORA ID"] = docs_df["AGORA ID"].values

    merged = cosponsors_df[["AGORA ID", "Cosponsor_BioguideId"]].merge(
        tax, on="AGORA ID", how="inner"
    )
    profile = merged.groupby("Cosponsor_BioguideId").sum(numeric_only=True)
    return profile


# ── Graph construction ──────────────────────────────────────────────────────

def build_sponsor_document_bigraph(docs_df: pd.DataFrame,
                                    cosponsors_df: pd.DataFrame) -> nx.Graph:
    """Build a bipartite graph: sponsor nodes ↔ document nodes.

    Sponsor nodes prefixed 'sponsor:', document nodes prefixed 'doc:'.
    Edge attributes: party, state, is_original.
    Document attributes: Policy_Area, Cosponsor_Count, Official name.
    """
    B = nx.Graph()

    # Add document nodes
    for _, row in docs_df.iterrows():
        aid = f"doc:{row['AGORA ID']}"
        B.add_node(aid, bipartite=0,
                   policy_area=str(row.get("Policy_Area", "")),
                   cosponsor_count=int(row.get("Cosponsor_Count", 0) or 0),
                   name=str(row.get("Casual name", row.get("Official name", ""))))

    # Add sponsor-document edges
    for _, row in cosponsors_df.iterrows():
        sid = f"sponsor:{row['Cosponsor_BioguideId']}"
        aid = f"doc:{row['AGORA ID']}"
        if not B.has_node(sid):
            B.add_node(sid, bipartite=1,
                       party=row.get("Cosponsor_Party", ""),
                       state=row.get("Cosponsor_State", ""),
                       name=row.get("Cosponsor_FullName", ""))
        B.add_edge(sid, aid,
                   is_original=row.get("Cosponsor_IsOriginal", ""),
                   party=row.get("Cosponsor_Party", ""))
    return B


def bipartite_projection(B: nx.Graph, node_type: int, weight_attr: str = "weight") -> nx.Graph:
    """Project a bipartite graph onto one node set.

    Args:
        node_type: 0 for documents, 1 for sponsors
        weight_attr: attribute name for shared-neighbor count
    """
    nodes = {n for n, d in B.nodes(data=True) if d.get("bipartite") == node_type}
    return nx.bipartite.weighted_projected_graph(B, nodes)


def build_cosponsor_cosponsor_graph(cosponsors_df: pd.DataFrame,
                                     min_shared: int = 2) -> nx.Graph:
    """Build sponsor-sponsor graph weighted by shared documents.

    Only includes edges where sponsors share >= min_shared documents.
    """
    sponsor_docs = defaultdict(set)
    sponsor_info = {}

    for _, row in cosponsors_df.iterrows():
        bio = row["Cosponsor_BioguideId"]
        sponsor_docs[bio].add(row["AGORA ID"])
        if bio not in sponsor_info:
            sponsor_info[bio] = {
                "name": row.get("Cosponsor_FullName", ""),
                "party": row.get("Cosponsor_Party", ""),
                "state": row.get("Cosponsor_State", ""),
            }

    G = nx.Graph()
    for bio, info in sponsor_info.items():
        G.add_node(bio, **info)

    bios = list(sponsor_docs.keys())
    for i, b1 in enumerate(bios):
        for b2 in bios[i + 1:]:
            shared = len(sponsor_docs[b1] & sponsor_docs[b2])
            if shared >= min_shared:
                G.add_edge(b1, b2, weight=shared)

    return G


def build_policy_cooccurrence_graph(docs_df: pd.DataFrame,
                                     cosponsors_df: pd.DataFrame) -> nx.Graph:
    """Build policy-area co-occurrence graph weighted by shared sponsors.

    Nodes = policy areas, edge weight = sponsors active in both areas.
    """
    sponsor_areas = defaultdict(set)
    for _, row in cosponsors_df.iterrows():
        aid = row["AGORA ID"]
        bio = row["Cosponsor_BioguideId"]
        pa = docs_df.loc[docs_df["AGORA ID"] == aid, "Policy_Area"]
        if not pa.empty and pd.notna(pa.values[0]):
            sponsor_areas[bio].add(pa.values[0])

    area_sponsors = defaultdict(set)
    for bio, areas in sponsor_areas.items():
        for area in areas:
            area_sponsors[area].add(bio)

    G = nx.Graph()
    areas = list(area_sponsors.keys())
    for area in areas:
        G.add_node(area, sponsor_count=len(area_sponsors[area]))

    for a1, a2 in combinations(areas, 2):
        shared = len(area_sponsors[a1] & area_sponsors[a2])
        if shared > 0:
            G.add_edge(a1, a2, weight=shared)

    return G


def build_taxonomy_cooccurrence_graph(docs_df: pd.DataFrame,
                                       group1: str, group2: str) -> nx.Graph:
    """Build a co-occurrence graph between two taxonomy groups.

    Nodes are taxonomy tags from group1 and group2.
    Edge weight = number of documents where both tags are present.
    """
    cols1 = get_taxonomy_columns(docs_df, group1)
    cols2 = get_taxonomy_columns(docs_df, group2)
    prefix1 = TAXONOMY_GROUPS[group1]
    prefix2 = TAXONOMY_GROUPS[group2]

    G = nx.Graph()
    for c1 in cols1:
        label1 = c1.replace(prefix1, "").strip().lstrip(": ")
        for c2 in cols2:
            label2 = c2.replace(prefix2, "").strip().lstrip(": ")
            mask = (docs_df[c1].fillna(0).astype(bool)) & (docs_df[c2].fillna(0).astype(bool))
            count = mask.sum()
            if count > 0:
                G.add_node(label1, group=group1)
                G.add_node(label2, group=group2)
                G.add_edge(label1, label2, weight=count)

    return G


# ── Graph query helpers ─────────────────────────────────────────────────────

def ego_network(G: nx.Graph, node: str, radius: int = 1) -> nx.Graph:
    """Extract ego network around a node up to given radius."""
    return nx.ego_graph(G, node, radius=radius)


def top_nodes_by_centrality(G: nx.Graph, measure: str = "degree",
                             top_n: int = 20) -> list[tuple[str, float]]:
    """Return top-N nodes by centrality measure.

    Measures: 'degree', 'betweenness', 'eigenvector', 'closeness'
    """
    funcs = {
        "degree": nx.degree_centrality,
        "betweenness": nx.betweenness_centrality,
        "eigenvector": nx.eigenvector_centrality_numpy,
        "closeness": nx.closeness_centrality,
    }
    centrality = funcs[measure](G)
    return sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]


def subgraph_by_attribute(G: nx.Graph, attr: str, value) -> nx.Graph:
    """Extract subgraph of nodes matching an attribute value."""
    nodes = [n for n, d in G.nodes(data=True) if d.get(attr) == value]
    return G.subgraph(nodes).copy()


def cross_party_subgraph(G: nx.Graph) -> nx.Graph:
    """Extract subgraph containing only cross-party edges."""
    cross_edges = []
    for u, v in G.edges():
        p1 = G.nodes[u].get("party", "")
        p2 = G.nodes[v].get("party", "")
        if p1 and p2 and p1 != p2:
            cross_edges.append((u, v))
    H = nx.Graph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v in cross_edges:
        H.add_edge(u, v, **G.edges[u, v])
    return H


def bipartisanship_index(doc_cosponsors: pd.DataFrame) -> float:
    """Compute bipartisanship index for a set of cosponsors.

    Returns min(D, R) / total. Higher = more bipartisan.
    """
    parties = doc_cosponsors["Cosponsor_Party"].value_counts()
    d = parties.get("D", 0)
    r = parties.get("R", 0)
    total = d + r
    if total == 0:
        return 0.0
    return min(d, r) / total


# ── Export helpers ──────────────────────────────────────────────────────────

def save_graph(G: nx.Graph, name: str, fmt: str = "graphml"):
    """Save graph to outputs directory."""
    path = OUTPUTS_DIR / f"{name}.{fmt}"
    if fmt == "graphml":
        nx.write_graphml(G, str(path))
    elif fmt == "gexf":
        nx.write_gexf(G, str(path))
    return path


def save_df(df: pd.DataFrame, name: str):
    """Save DataFrame to outputs directory as CSV."""
    path = OUTPUTS_DIR / f"{name}.csv"
    df.to_csv(path, index=True)
    return path
