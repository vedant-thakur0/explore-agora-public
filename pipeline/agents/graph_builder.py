"""Phase 5: Build multiplex graph from all agent outputs.

Reads:
- sponsor_nodes.csv, sponsor_edges.csv (Phase 1)
- communities.json (Phase 2)
- entities.jsonl, canonical_entity_map.json (Phase 3/4)

Produces per-layer GraphML files + combined multiplex + stats JSON.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

import networkx as nx

from pipeline.config import AGENTS_OUTPUT_DIR, MULTIPLEX_GRAPH_DIR
from pipeline.models import read_jsonl, write_json

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Turn a name into a filesystem/node-id-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80] or "unknown"


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        assert ImportWarning(f"Path Not Found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Layer 1: Sponsor graph
# ---------------------------------------------------------------------------

def build_layer1_sponsor(agents_output_dir: Path,) -> nx.MultiDiGraph:
    """Build Layer 1 sponsor graph from sponsor_nodes.csv and sponsor_edges.csv."""
    G = nx.MultiDiGraph()

    nodes = _load_csv(agents_output_dir / "sponsor_nodes.csv")
    for row in nodes:
        node_id = row.get("node_id", "")
        if not node_id:
            continue
        G.add_node(
            node_id,
            node_type="Sponsor",
            label=row.get("full_name", ""),
            layer=1,
            bioguide_id=row.get("bioguide_id", ""),
            party=row.get("party", ""),
            state=row.get("state", ""),
            district=row.get("district", ""),
            chamber=row.get("chamber", ""),
        )

    edges = _load_csv(agents_output_dir / "sponsor_edges.csv")
    for row in edges:
        src = row.get("src_id", "")
        dst = row.get("dst_id", "")
        relation = row.get("relation", "")
        if not src or not dst:
            continue

        # Ensure document nodes exist
        for nid in (src, dst):
            if nid not in G and nid.startswith("document:"):
                G.add_node(nid, node_type="Document", label=nid, layer=1)

        G.add_edge(
            src, dst,
            relation=relation,
            layer=1,
            **{k: v for k, v in row.items() if k not in ("src_id", "dst_id", "relation", "layer")},
        )

    log.info("Layer 1: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# ---------------------------------------------------------------------------
# Layer 1b: Active Cosponsor graph
# ---------------------------------------------------------------------------

def build_layer1b_cosponsor(agents_output_dir: Path,) -> nx.MultiDiGraph:
    """Build Layer 1b active cosponsor graph from cosponsor_nodes.csv and cosponsor_edges.csv."""
    G = nx.MultiDiGraph()

    nodes_path = agents_output_dir / "cosponsor_nodes.csv"
    if not nodes_path.exists():
        log.warning("cosponsor_nodes.csv not found, skipping Layer 1b.")
        return G

    nodes = _load_csv(nodes_path)
    for row in nodes:
        node_id = row.get("node_id", "")
        if not node_id:
            continue
        G.add_node(
            node_id,
            node_type="Cosponsor",
            label=row.get("full_name", ""),
            layer=2,
            bioguide_id=row.get("bioguide_id", ""),
            party=row.get("party", ""),
            state=row.get("state", ""),
            district=row.get("district", ""),
            chamber=row.get("chamber", ""),
        )

    edges_path = agents_output_dir / "cosponsor_edges.csv"
    if edges_path.exists():
        edges = _load_csv(edges_path)
        for row in edges:
            src = row.get("src_id", "")
            dst = row.get("dst_id", "")
            relation = row.get("relation", "")
            if not src or not dst:
                continue

            # Ensure document nodes exist
            for nid in (src, dst):
                if nid not in G and nid.startswith("document:"):
                    G.add_node(nid, node_type="Document", label=nid, layer=2)

            G.add_edge(
                src, dst,
                relation=relation,
                layer=2,
                **{k: v for k, v in row.items() if k not in ("src_id", "dst_id", "relation", "layer")},
            )

    log.info("Layer 1b: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# ---------------------------------------------------------------------------
# Layer 1.75: Withdrawn Cosponsor graph
# ---------------------------------------------------------------------------

def build_layer175_withdrawn_cosponsor(agents_output_dir: Path,) -> nx.MultiDiGraph:
    """Build Layer 1.75 withdrawn cosponsor graph."""
    G = nx.MultiDiGraph()

    nodes_path = agents_output_dir / "withdrawn_cosponsor_nodes.csv"
    if not nodes_path.exists():
        log.warning("withdrawn_cosponsor_nodes.csv not found, skipping Layer 1.75.")
        return G

    nodes = _load_csv(nodes_path)
    for row in nodes:
        node_id = row.get("node_id", "")
        if not node_id:
            continue
        G.add_node(
            node_id,
            node_type="WithdrawnCosponsor",
            label=row.get("full_name", ""),
            layer=2,
            bioguide_id=row.get("bioguide_id", ""),
            party=row.get("party", ""),
            state=row.get("state", ""),
            district=row.get("district", ""),
            chamber=row.get("chamber", ""),
        )

    edges_path = agents_output_dir / "withdrawn_cosponsor_edges.csv"
    if edges_path.exists():
        edges = _load_csv(edges_path)
        for row in edges:
            src = row.get("src_id", "")
            dst = row.get("dst_id", "")
            relation = row.get("relation", "")
            if not src or not dst:
                continue

            # Ensure document nodes exist
            for nid in (src, dst):
                if nid not in G and nid.startswith("document:"):
                    G.add_node(nid, node_type="Document", label=nid, layer=2)

            G.add_edge(
                src, dst,
                relation=relation,
                layer=2,
                **{k: v for k, v in row.items() if k not in ("src_id", "dst_id", "relation", "layer")},
            )

    log.info("Layer 1.75: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# ---------------------------------------------------------------------------
# Layer 2: Community graph
# ---------------------------------------------------------------------------

def build_layer2_community(
    agents_output_dir: Path,
) -> nx.MultiDiGraph:
    """Build Layer 2 community graph from communities.json."""
    G = nx.MultiDiGraph()

    communities_path = agents_output_dir / "communities.json"
    if not communities_path.exists():
        log.warning("communities.json not found, skipping Layer 2.")
        return G

    communities = json.loads(communities_path.read_text(encoding="utf-8"))

    for comm in communities:
        comm_id = comm.get("community_id", "")
        if not comm_id:
            continue

        G.add_node(
            comm_id,
            node_type="Community",
            label=comm.get("label", ""),
            layer=2,
            dominant_party=comm.get("dominant_party", ""),
            size=len(comm.get("member_agora_ids", [])),
        )

        for agora_id in comm.get("member_agora_ids", []):
            doc_id = f"document:{agora_id}"
            if doc_id not in G:
                G.add_node(doc_id, node_type="Document", label=doc_id, layer=2)

            centrality = comm.get("doc_centrality", {}).get(agora_id, 0.0)
            G.add_edge(
                doc_id, comm_id,
                relation="IN_COMMUNITY",
                layer=2,
                centrality=str(centrality),
            )

    log.info("Layer 2: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# ---------------------------------------------------------------------------
# Layer 3: Entity graph
# ---------------------------------------------------------------------------

def build_layer3_entity(
    agents_output_dir: Path,
) -> nx.MultiDiGraph:
    """Build Layer 3 entity graph from entities.jsonl and canonical_entity_map.json."""
    G = nx.MultiDiGraph()

    entities = read_jsonl(agents_output_dir / "entities.jsonl")
    if not entities:
        log.warning("entities.jsonl not found or empty, skipping Layer 3.")
        return G

    # Load canonical map if available
    canonical_map: dict[str, str] = {}
    canonical_path = agents_output_dir / "canonical_entity_map.json"
    if canonical_path.exists():
        canonical_map = json.loads(canonical_path.read_text(encoding="utf-8"))

    # Entity type → (relation, name_field, node_type_prefix)
    ENTITY_CONFIG = {
        "organizations": ("MENTIONS_ORG", "name", "org"),
        "offices": ("MENTIONS_OFFICE", "name", "office"),
        "roles": ("INVOLVES_ROLE", "title", "role"),
        "legislation_refs": ("REFERENCES_LEGISLATION", "name", "legislation"),
        "named_docs": ("INVOLVES_NAMED_DOC", "name", "named_doc"),
    }

    for rec in entities:
        agora_id = rec.get("agora_id", "")
        if not agora_id:
            continue
        doc_id = f"document:{agora_id}"
        if doc_id not in G:
            G.add_node(doc_id, node_type="Document", label=doc_id, layer=3)

        for entity_type, (relation, name_field, prefix) in ENTITY_CONFIG.items():
            for entity in rec.get(entity_type, []):
                raw_name = entity.get(name_field, "")
                if not raw_name:
                    continue

                # Apply canonical mapping
                canonical_id = canonical_map.get(raw_name.lower().strip())
                if canonical_id:
                    node_id = canonical_id
                else:
                    node_id = f"{prefix}:{_slugify(raw_name)}"

                if node_id not in G:
                    node_attrs: dict[str, Any] = {
                        "node_type": prefix.replace("_", " ").title(),
                        "label": raw_name,
                        "layer": 3,
                    }
                    # Add type-specific properties
                    if entity_type == "organizations":
                        node_attrs["acronym"] = entity.get("acronym", "")
                    elif entity_type == "offices":
                        node_attrs["parent_org"] = entity.get("parent_org", "")
                    elif entity_type == "roles":
                        node_attrs["org"] = entity.get("org", "")
                    elif entity_type == "legislation_refs":
                        node_attrs["citation"] = entity.get("citation", "")
                    elif entity_type == "named_docs":
                        node_attrs["doc_type"] = entity.get("doc_type", "")
                        node_attrs["owner_org"] = entity.get("owner_org", "")
                    G.add_node(node_id, **node_attrs)

                # Add edge
                edge_attrs: dict[str, Any] = {"relation": relation, "layer": 3}
                context = entity.get("context", "")
                if context:
                    edge_attrs["context"] = context[:200]  # cap for GraphML
                if entity_type == "legislation_refs":
                    edge_attrs["ref_type"] = entity.get("ref_type", "")
                G.add_edge(doc_id, node_id, **edge_attrs)

        # Entity-to-entity relationships
        for rel in rec.get("relationships", []):
            src_type = rel.get("source_type", "")
            src_name = rel.get("source_name", "")
            tgt_type = rel.get("target_type", "")
            tgt_name = rel.get("target_name", "")
            rel_type = rel.get("relation_type", "")

            if not all([src_type, src_name, tgt_type, tgt_name, rel_type]):
                continue

            src_cfg = ENTITY_CONFIG.get(src_type)
            tgt_cfg = ENTITY_CONFIG.get(tgt_type)
            if not src_cfg or not tgt_cfg:
                continue
            src_prefix = src_cfg[2]
            tgt_prefix = tgt_cfg[2]

            src_canonical = canonical_map.get(src_name.lower().strip())
            src_node_id = src_canonical or f"{src_prefix}:{_slugify(src_name)}"

            tgt_canonical = canonical_map.get(tgt_name.lower().strip())
            tgt_node_id = tgt_canonical or f"{tgt_prefix}:{_slugify(tgt_name)}"

            if src_node_id not in G or tgt_node_id not in G:
                log.warning(
                    "Skipping relationship %s -[%s]-> %s: node not in graph",
                    src_node_id, rel_type, tgt_node_id,
                )
                continue

            rel_edge_attrs: dict[str, Any] = {
                "relation": rel_type,
                "layer": 3,
                "source_doc": agora_id,
            }
            rel_context = rel.get("context", "")
            if rel_context:
                rel_edge_attrs["context"] = rel_context[:200]

            G.add_edge(src_node_id, tgt_node_id, **rel_edge_attrs)

    log.info("Layer 3: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# ---------------------------------------------------------------------------
# Combine layers
# ---------------------------------------------------------------------------

def combine_layers(
    *layers: nx.MultiDiGraph,
) -> nx.MultiDiGraph:
    """Merge multiple layer graphs into a single multiplex graph."""
    combined = nx.MultiDiGraph()
    for layer_graph in layers:
        for node, attrs in layer_graph.nodes(data=True):
            if node not in combined:
                combined.add_node(node, **attrs)
            else:
                # Merge attributes (prefer existing, but add missing)
                for k, v in attrs.items():
                    if k not in combined.nodes[node]:
                        combined.nodes[node][k] = v
        for u, v, attrs in layer_graph.edges(data=True):
            combined.add_edge(u, v, **attrs)
    return combined


def compute_stats(
    layers: dict[str, nx.MultiDiGraph],
    combined: nx.MultiDiGraph,
) -> dict[str, Any]:
    """Compute summary statistics for the multiplex graph."""
    layer_stats: dict[str, Any] = {}
    for name, G in layers.items():
        node_types: dict[str, int] = {}
        for _, attrs in G.nodes(data=True):
            nt = attrs.get("node_type", "Unknown")
            node_types[nt] = node_types.get(nt, 0) + 1

        edge_types: dict[str, int] = {}
        for _, _, attrs in G.edges(data=True):
            rel = attrs.get("relation", "Unknown")
            edge_types[rel] = edge_types.get(rel, 0) + 1

        layer_stats[name] = {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
        }

    return {
        "layers": layer_stats,
        "combined": {
            "nodes": combined.number_of_nodes(),
            "edges": combined.number_of_edges(),
        },
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_graphml(G: nx.MultiDiGraph, path: Path) -> None:
    """Write a MultiDiGraph to GraphML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # GraphML doesn't handle None well; convert to empty strings
    for _, attrs in G.nodes(data=True):
        for k, v in list(attrs.items()):
            if v is None:
                attrs[k] = ""
            elif not isinstance(v, (str, int, float, bool)):
                attrs[k] = str(v)
    for _, _, attrs in G.edges(data=True):
        for k, v in list(attrs.items()):
            if v is None:
                attrs[k] = ""
            elif not isinstance(v, (str, int, float, bool)):
                attrs[k] = str(v)
    nx.write_graphml(G, str(path))
    log.info("Exported %s (%d nodes, %d edges)", path.name, G.number_of_nodes(), G.number_of_edges())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_multiplex_graph(
    agents_output_dir: Path | None = None,
    graph_output_dir: Path | None = None,
    agents_filter: str | None = None,
) -> dict[str, Any]:
    """Build the full multiplex graph from all agent outputs.

    Args:
        agents_output_dir: where agent outputs live (sponsor_nodes.csv, etc.)
        graph_output_dir: where to write GraphML files
        agents_filter: "sponsor", "community", "ner", or "all"

    Returns stats dict.
    """
    agents_output_dir = agents_output_dir or AGENTS_OUTPUT_DIR
    graph_output_dir = graph_output_dir or MULTIPLEX_GRAPH_DIR
    graph_output_dir.mkdir(parents=True, exist_ok=True)

    run_all = agents_filter is None or agents_filter == "all"
    layers: dict[str, nx.MultiDiGraph] = {}

    if run_all or agents_filter == "sponsor":
        layer1 = build_layer1_sponsor(agents_output_dir)
        layers["layer_1_sponsor"] = layer1
        export_graphml(layer1, graph_output_dir / "layer_1_sponsor.graphml")

    if run_all or agents_filter in ("sponsor", "cosponsor"):
        layer1b = build_layer1b_cosponsor(agents_output_dir)
        layers["layer_1b_cosponsor"] = layer1b
        export_graphml(layer1b, graph_output_dir / "layer_1b_cosponsor.graphml")

        layer175 = build_layer175_withdrawn_cosponsor(agents_output_dir)
        layers["layer_175_withdrawn_cosponsor"] = layer175
        export_graphml(layer175, graph_output_dir / "layer_175_withdrawn_cosponsor.graphml")

    if run_all or agents_filter == "community":
        layer2 = build_layer2_community(agents_output_dir)
        layers["layer_2_community"] = layer2
        export_graphml(layer2, graph_output_dir / "layer_2_community.graphml")

    if run_all or agents_filter == "ner":
        layer3 = build_layer3_entity(agents_output_dir)
        layers["layer_3_entity"] = layer3
        export_graphml(layer3, graph_output_dir / "layer_3_entity.graphml")

    if layers:
        combined = combine_layers(*layers.values())
        export_graphml(combined, graph_output_dir / "multiplex_combined.graphml")
        stats = compute_stats(layers, combined)
    else:
        stats = {"layers": {}, "combined": {"nodes": 0, "edges": 0}}

    stats_path = graph_output_dir / "multiplex_stats.json"
    write_json(stats_path, stats)
    log.info("Stats written to %s", stats_path)

    return stats


def run(
    agents_output_dir: Path | None = None,
    graph_output_dir: Path | None = None,
    agents_filter: str | None = None,
) -> dict[str, Any]:
    """Entry point alias."""
    return build_multiplex_graph(agents_output_dir, graph_output_dir, agents_filter)
