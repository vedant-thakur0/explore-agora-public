from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from pathlib import Path

DEFAULT_RELATION_WEIGHTS: dict[str, float] = {
    "HAS_TOPIC": 1.0,
    "HAS_TAG": 0.85,
    "HAS_SEGMENT": 0.75,
    "IN_COLLECTION": 0.65,
    "UNDER_AUTHORITY": 0.55,
}
DEFAULT_HOP_DECAY = 0.7


def _load_nodes(nodes_path: Path) -> dict[str, dict[str, str]]:
    nodes: dict[str, dict[str, str]] = {}
    with nodes_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            node_id = (row.get("node_id") or "").strip()
            if not node_id:
                continue
            nodes[node_id] = row
    return nodes


def _load_adjacency(edges_path: Path) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with edges_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            src = (row.get("src_id") or "").strip()
            rel = (row.get("relation") or "").strip()
            dst = (row.get("dst_id") or "").strip()
            if not src or not rel or not dst:
                continue
            adjacency[src].append((rel, dst))
    return adjacency


def _load_reverse_adjacency(edges_path: Path) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with edges_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            src = (row.get("src_id") or "").strip()
            rel = (row.get("relation") or "").strip()
            dst = (row.get("dst_id") or "").strip()
            if not src or not rel or not dst:
                continue
            adjacency[dst].append((rel, src))
    return adjacency


def get_neighborhood(
    seed_node_id: str,
    max_hops: int = 2,
    relation_filter: set[str] | None = None,
    node_type_filter: set[str] | None = None,
    limit: int = 200,
    ranked: bool = True,
    relation_weights: dict[str, float] | None = None,
    hop_decay: float = DEFAULT_HOP_DECAY,
    direction: str = "out",
    nodes_path: Path = Path("pipeline/graph/nodes.csv"),
    edges_path: Path = Path("pipeline/graph/edges.csv"),
) -> dict:
    if max_hops < 1:
        raise ValueError("max_hops must be >= 1")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if hop_decay < 0:
        raise ValueError("hop_decay must be >= 0")
    if direction not in {"out", "in", "both"}:
        raise ValueError("direction must be one of: out, in, both")

    nodes = _load_nodes(nodes_path)
    adjacency_out = _load_adjacency(edges_path)
    adjacency_in = _load_reverse_adjacency(edges_path)

    if seed_node_id not in nodes:
        raise ValueError(f"seed node not found: {seed_node_id}")

    rel_filter = {r.strip() for r in (relation_filter or set()) if r.strip()}
    type_filter = {t.strip() for t in (node_type_filter or set()) if t.strip()}
    weights = dict(DEFAULT_RELATION_WEIGHTS)
    if relation_weights:
        weights.update(relation_weights)

    queue: deque[str] = deque([seed_node_id])
    dist: dict[str, int] = {seed_node_id: 0}
    pred: dict[str, tuple[str, str]] = {}  # node -> (prev_node, via_relation)

    while queue:
        current = queue.popleft()
        current_dist = dist[current]
        if current_dist >= max_hops:
            continue

        neighbors: list[tuple[str, str]] = []
        if direction in {"out", "both"}:
            neighbors.extend(adjacency_out.get(current, []))
        if direction in {"in", "both"}:
            neighbors.extend(adjacency_in.get(current, []))

        for rel, nxt in neighbors:
            if rel_filter and rel not in rel_filter:
                continue
            if nxt in dist:
                continue
            dist[nxt] = current_dist + 1
            pred[nxt] = (current, rel)
            queue.append(nxt)

    rows: list[dict] = []
    counts_by_hop: dict[str, int] = {}

    for node_id, hop in dist.items():
        if node_id == seed_node_id:
            continue
        node = nodes.get(node_id, {})
        node_type = (node.get("node_type") or "").strip()
        if type_filter and node_type not in type_filter:
            continue

        path_steps: list[dict[str, str]] = []
        cursor = node_id
        while cursor in pred:
            prev, via_rel = pred[cursor]
            path_steps.append({"from": prev, "relation": via_rel, "to": cursor})
            cursor = prev
        path_steps.reverse()

        via_relation = path_steps[0]["relation"] if path_steps else ""
        base_weight = weights.get(via_relation, 0.5)
        rank_score = base_weight * (hop_decay ** (hop - 1))
        rows.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "label": (node.get("label") or "").strip(),
                "hop_distance": hop,
                "via_relation": via_relation,
                "rank_score": round(rank_score, 8),
                "path": path_steps,
            }
        )

    if ranked:
        rows.sort(key=lambda r: (-r["rank_score"], r["hop_distance"], r["node_type"], r["node_id"]))
    else:
        rows.sort(key=lambda r: (r["hop_distance"], r["node_type"], r["node_id"]))
    rows = rows[:limit]

    for r in rows:
        k = str(r["hop_distance"])
        counts_by_hop[k] = counts_by_hop.get(k, 0) + 1

    return {
        "seed_node_id": seed_node_id,
        "max_hops": max_hops,
        "neighbors": rows,
        "counts_by_hop": counts_by_hop,
        "ranking": {
            "enabled": ranked,
            "hop_decay": hop_decay,
            "relation_weights": weights,
        },
        "direction": direction,
    }


def run(
    graph_dir: Path,
    seed_node_id: str,
    max_hops: int = 2,
    relation_filter: set[str] | None = None,
    node_type_filter: set[str] | None = None,
    limit: int = 200,
    ranked: bool = True,
    direction: str = "out",
) -> dict:
    return get_neighborhood(
        seed_node_id=seed_node_id,
        max_hops=max_hops,
        relation_filter=relation_filter,
        node_type_filter=node_type_filter,
        limit=limit,
        ranked=ranked,
        direction=direction,
        nodes_path=graph_dir / "nodes.csv",
        edges_path=graph_dir / "edges.csv",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query neighborhood on AGORA graph export")
    parser.add_argument("--graph-dir", default="pipeline/graph")
    parser.add_argument("--seed-node-id", required=True)
    parser.add_argument("--max-hops", type=int, default=2)
    parser.add_argument("--relation", action="append", default=[])
    parser.add_argument("--node-type", action="append", default=[])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--unranked", action="store_true")
    parser.add_argument("--direction", choices=["out", "in", "both"], default="out")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run(
        graph_dir=Path(args.graph_dir),
        seed_node_id=args.seed_node_id,
        max_hops=args.max_hops,
        relation_filter=set(args.relation or []),
        node_type_filter=set(args.node_type or []),
        limit=args.limit,
        ranked=not args.unranked,
        direction=args.direction,
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
