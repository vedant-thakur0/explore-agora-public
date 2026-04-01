from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


def _csv_get(row: dict[str, str], key: str) -> str:
    if key in row:
        return (row.get(key) or "").strip()
    bom_key = f"\ufeff{key}"
    return (row.get(bom_key) or "").strip()


def _normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "x"}


def _safe_id(value: str) -> str:
    clean = []
    for ch in (value or "").lower():
        if ch.isalnum() or ch in ("_", "-", "."):
            clean.append(ch)
        else:
            clean.append("_")
    return "".join(clean).strip("_") or "unknown"


def _node_id(kind: str, key: str) -> str:
    return f"{kind}:{_safe_id(key)}"


@dataclass
class GraphData:
    nodes: list[dict[str, str]]
    edges: list[dict[str, str]]
    stats: dict[str, object]


def _taxonomy_columns(fieldnames: list[str], skip: set[str]) -> list[str]:
    return [name for name in fieldnames if name not in skip and ":" in name]


def _build_graph_from_supabase(client) -> GraphData:
    """Build graph by fetching rows directly from Supabase tables."""
    from .supabase.client import fetch_authorities, fetch_collections, fetch_documents, fetch_segments

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_seen: set[str] = set()
    edge_seen: set[tuple[str, str, str]] = set()
    stats = Counter()

    def add_node(node_id: str, node_type: str, label: str, **props: str) -> None:
        if node_id in node_seen:
            return
        row = {"node_id": node_id, "node_type": node_type, "label": _normalize_space(label)}
        for k, v in props.items():
            row[k] = str(v)
        nodes.append(row)
        node_seen.add(node_id)
        stats[f"nodes_{node_type.lower()}"] += 1

    def add_edge(src: str, rel: str, dst: str, **props: str) -> None:
        key = (src, rel, dst)
        if key in edge_seen:
            return
        row = {"src_id": src, "relation": rel, "dst_id": dst}
        for k, v in props.items():
            row[k] = str(v)
        edges.append(row)
        edge_seen.add(key)
        stats[f"edges_{rel.lower()}"] += 1

    for row in fetch_authorities():
        name = (row.get("name") or "").strip()
        if not name:
            continue
        add_node(
            _node_id("authority", name), "Authority", name,
            jurisdiction=row.get("jurisdiction") or "",
            parent_authority=row.get("parent_authority") or "",
        )

    for row in fetch_collections():
        name = (row.get("name") or "").strip()
        if not name:
            continue
        add_node(_node_id("collection", name), "Collection", name,
                 description=row.get("description") or "")

    for row in fetch_segments():
        document_id = str(row.get("document_id") or "").strip()
        seg_pos = str(row.get("segment_position") or "").strip()
        if not document_id or not seg_pos:
            continue
        seg_key = f"{document_id}:{seg_pos}"
        segment_id = _node_id("segment", seg_key)
        add_node(
            segment_id, "Segment", f"Segment {seg_pos}",
            document_id=document_id,
            segment_position=seg_pos,
            summary=row.get("summary") or "",
            non_operative=str(row.get("non_operative") or ""),
            not_ai_related=str(row.get("not_ai_related") or ""),
        )
        doc_id = _node_id("document", document_id)
        add_edge(doc_id, "HAS_SEGMENT", segment_id, segment_position=seg_pos)

        for tag in (row.get("tags") or "").split(";"):
            tag = tag.strip()
            if tag:
                tag_id = _node_id("tag", tag)
                add_node(tag_id, "Tag", tag)
                add_edge(segment_id, "HAS_TAG", tag_id)

        for topic in row.get("taxonomy_tags") or []:
            topic_id = _node_id("topic", topic)
            add_node(topic_id, "Topic", topic, source_column=topic)
            add_edge(segment_id, "HAS_TOPIC", topic_id)

    for row in fetch_documents():
        agora_id = str(row.get("agora_id") or "").strip()
        if not agora_id:
            continue
        doc_id = _node_id("document", agora_id)
        add_node(
            doc_id, "Document",
            row.get("official_name") or f"AGORA {agora_id}",
            agora_id=agora_id,
            casual_name=row.get("casual_name") or "",
            link_to_document=row.get("link_to_document") or "",
            most_recent_activity=row.get("most_recent_activity") or "",
            most_recent_activity_date=row.get("most_recent_activity_date") or "",
        )

        authority = (row.get("authority_name") or "").strip()
        if authority:
            authority_id = _node_id("authority", authority)
            add_node(authority_id, "Authority", authority)
            add_edge(doc_id, "UNDER_AUTHORITY", authority_id)

        for coll in (row.get("collections_raw") or "").split(";"):
            coll = coll.strip()
            if coll:
                collection_id = _node_id("collection", coll)
                add_node(collection_id, "Collection", coll)
                add_edge(doc_id, "IN_COLLECTION", collection_id)

        for tag in (row.get("tags") or "").split(";"):
            tag = tag.strip()
            if tag:
                tag_id = _node_id("tag", tag)
                add_node(tag_id, "Tag", tag)
                add_edge(doc_id, "HAS_TAG", tag_id)

        for topic in row.get("taxonomy_tags") or []:
            topic_id = _node_id("topic", topic)
            add_node(topic_id, "Topic", topic, source_column=topic)
            add_edge(doc_id, "HAS_TOPIC", topic_id)

    payload_stats = dict(stats)
    payload_stats["node_count"] = len(nodes)
    payload_stats["edge_count"] = len(edges)
    return GraphData(nodes=nodes, edges=edges, stats=payload_stats)


def build_graph(
    documents_csv: Path,
    segments_csv: Path,
    authorities_csv: Path,
    collections_csv: Path,
    supabase_client=None,
) -> GraphData:
    if supabase_client is not None:
        return _build_graph_from_supabase(supabase_client)

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_seen: set[str] = set()
    edge_seen: set[tuple[str, str, str]] = set()
    stats = Counter()

    def add_node(node_id: str, node_type: str, label: str, **props: str) -> None:
        if node_id in node_seen:
            return
        row = {"node_id": node_id, "node_type": node_type, "label": _normalize_space(label)}
        for k, v in props.items():
            row[k] = str(v)
        nodes.append(row)
        node_seen.add(node_id)
        stats[f"nodes_{node_type.lower()}"] += 1

    def add_edge(src: str, rel: str, dst: str, **props: str) -> None:
        key = (src, rel, dst)
        if key in edge_seen:
            return
        row = {"src_id": src, "relation": rel, "dst_id": dst}
        for k, v in props.items():
            row[k] = str(v)
        edges.append(row)
        edge_seen.add(key)
        stats[f"edges_{rel.lower()}"] += 1

    with authorities_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = _csv_get(row, "Name")
            if not name:
                continue
            node_id = _node_id("authority", name)
            add_node(
                node_id,
                "Authority",
                name,
                jurisdiction=_csv_get(row, "Jurisdiction"),
                parent_authority=_csv_get(row, "Parent authority"),
            )

    with collections_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = _csv_get(row, "Name")
            if not name:
                continue
            node_id = _node_id("collection", name)
            add_node(node_id, "Collection", name, description=_csv_get(row, "Description"))

    segment_taxonomy_cols: list[str] = []
    with segments_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            segment_taxonomy_cols = _taxonomy_columns(
                reader.fieldnames,
                skip={
                    "\ufeffDocument ID",
                    "Document ID",
                    "Segment position",
                    "Text",
                    "Tags",
                    "Summary",
                    "Non-operative",
                    "Not AI-related",
                    "Segment annotated",
                    "Segment validated",
                    "Summaries and tags may include unreviewed machine output",
                },
            )
        for row in reader:
            document_id = _csv_get(row, "Document ID")
            seg_pos = _csv_get(row, "Segment position")
            if not document_id or not seg_pos:
                continue
            seg_key = f"{document_id}:{seg_pos}"
            segment_id = _node_id("segment", seg_key)
            add_node(
                segment_id,
                "Segment",
                f"Segment {seg_pos}",
                document_id=document_id,
                segment_position=seg_pos,
                summary=_csv_get(row, "Summary"),
                non_operative=_csv_get(row, "Non-operative"),
                not_ai_related=_csv_get(row, "Not AI-related"),
            )
            doc_id = _node_id("document", document_id)
            add_edge(doc_id, "HAS_SEGMENT", segment_id, segment_position=seg_pos)

            tags = [t.strip() for t in _csv_get(row, "Tags").split(";") if t.strip()]
            for tag in tags:
                tag_id = _node_id("tag", tag)
                add_node(tag_id, "Tag", tag)
                add_edge(segment_id, "HAS_TAG", tag_id)

            for col in segment_taxonomy_cols:
                if not _truthy(_csv_get(row, col)):
                    continue
                topic_id = _node_id("topic", col)
                add_node(topic_id, "Topic", col, source_column=col)
                add_edge(segment_id, "HAS_TOPIC", topic_id)

    doc_taxonomy_cols: list[str] = []
    with documents_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            doc_taxonomy_cols = _taxonomy_columns(
                reader.fieldnames,
                skip={
                    "\ufeffAGORA ID",
                    "AGORA ID",
                    "Official name",
                    "Casual name",
                    "Link to document",
                    "Authority",
                    "Collections",
                    "Most recent activity",
                    "Most recent activity date",
                    "Proposed date",
                    "Annotated?",
                    "Validated?",
                    "Short summary",
                    "Long summary",
                    "Tags",
                    "Official plaintext retrieved",
                    "Official plaintext source",
                    "Official plaintext unavailable/infeasible",
                    "Official pdf source",
                    "Official pdf retrieved",
                    "Number of segments created",
                    "Summaries and tags may include unreviewed machine output",
                },
            )
        for row in reader:
            agora_id = _csv_get(row, "AGORA ID")
            if not agora_id:
                continue
            doc_id = _node_id("document", agora_id)
            add_node(
                doc_id,
                "Document",
                _csv_get(row, "Official name") or f"AGORA {agora_id}",
                agora_id=agora_id,
                casual_name=_csv_get(row, "Casual name"),
                link_to_document=_csv_get(row, "Link to document"),
                most_recent_activity=_csv_get(row, "Most recent activity"),
                most_recent_activity_date=_csv_get(row, "Most recent activity date"),
            )

            authority = _csv_get(row, "Authority")
            if authority:
                authority_id = _node_id("authority", authority)
                add_node(authority_id, "Authority", authority)
                add_edge(doc_id, "UNDER_AUTHORITY", authority_id)

            collections = [c.strip() for c in _csv_get(row, "Collections").split(";") if c.strip()]
            for collection in collections:
                collection_id = _node_id("collection", collection)
                add_node(collection_id, "Collection", collection)
                add_edge(doc_id, "IN_COLLECTION", collection_id)

            tags = [t.strip() for t in _csv_get(row, "Tags").split(";") if t.strip()]
            for tag in tags:
                tag_id = _node_id("tag", tag)
                add_node(tag_id, "Tag", tag)
                add_edge(doc_id, "HAS_TAG", tag_id)

            for col in doc_taxonomy_cols:
                if not _truthy(_csv_get(row, col)):
                    continue
                topic_id = _node_id("topic", col)
                add_node(topic_id, "Topic", col, source_column=col)
                add_edge(doc_id, "HAS_TOPIC", topic_id)

    payload_stats = dict(stats)
    payload_stats["node_count"] = len(nodes)
    payload_stats["edge_count"] = len(edges)
    return GraphData(nodes=nodes, edges=edges, stats=payload_stats)


def write_graph(data: GraphData, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = out_dir / "nodes.csv"
    edges_path = out_dir / "edges.csv"
    stats_path = out_dir / "stats.json"

    with nodes_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "node_id",
            "node_type",
            "label",
            "agora_id",
            "casual_name",
            "link_to_document",
            "most_recent_activity",
            "most_recent_activity_date",
            "jurisdiction",
            "parent_authority",
            "description",
            "document_id",
            "segment_position",
            "summary",
            "non_operative",
            "not_ai_related",
            "source_column",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data.nodes)

    with edges_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["src_id", "relation", "dst_id", "segment_position"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data.edges)

    stats_path.write_text(json.dumps(data.stats, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {"nodes": str(nodes_path), "edges": str(edges_path), "stats": str(stats_path)}


def run(
    documents_csv: Path,
    segments_csv: Path,
    authorities_csv: Path,
    collections_csv: Path,
    out_dir: Path,
    supabase_client=None,
) -> dict[str, object]:
    graph = build_graph(
        documents_csv=documents_csv,
        segments_csv=segments_csv,
        authorities_csv=authorities_csv,
        collections_csv=collections_csv,
        supabase_client=supabase_client,
    )
    out_paths = write_graph(graph, out_dir)
    return {
        "out_dir": str(out_dir),
        "nodes": out_paths["nodes"],
        "edges": out_paths["edges"],
        "stats": out_paths["stats"],
        "node_count": graph.stats["node_count"],
        "edge_count": graph.stats["edge_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build AGORA knowledge graph node/edge exports")
    parser.add_argument("--documents-csv", default="documents.csv")
    parser.add_argument("--segments-csv", default="segments.csv")
    parser.add_argument("--authorities-csv", default="authorities.csv")
    parser.add_argument("--collections-csv", default="collections.csv")
    parser.add_argument("--out-dir", default="pipeline/graph")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = run(
        documents_csv=Path(args.documents_csv),
        segments_csv=Path(args.segments_csv),
        authorities_csv=Path(args.authorities_csv),
        collections_csv=Path(args.collections_csv),
        out_dir=Path(args.out_dir),
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
