from __future__ import annotations

import argparse
import os
from pathlib import Path
import json

from dotenv import load_dotenv

# Load .env from repo root (or from alongside cli.py)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # adjust parents[] if needed
load_dotenv(dotenv_path=ENV_PATH)

from .config import AGENTS_OUTPUT_DIR, MULTIPLEX_GRAPH_DIR, LOUVAIN_RESOLUTION
from .graph_query import run as run_graph_query
from .knowledge_graph import run as run_knowledge_graph



if load_dotenv is not None:
    load_dotenv()


def _get_supabase_client_if_enabled():
    """Return a Supabase client if env vars are set, else None."""
    from .supabase.client import supabase_enabled, get_client
    if supabase_enabled():
        return get_client()
    return None


def cmd_build_knowledge_graph(args: argparse.Namespace) -> int:
    sb_client = _get_supabase_client_if_enabled()
    payload = run_knowledge_graph(
        documents_csv=Path(args.documents_csv),
        segments_csv=Path(args.segments_csv),
        authorities_csv=Path(args.authorities_csv),
        collections_csv=Path(args.collections_csv),
        out_dir=Path(args.out_dir),
        supabase_client=sb_client,
    )
    print(json.dumps(payload))
    return 0


def cmd_detect_communities(args: argparse.Namespace) -> int:
    from .agents.community_detector import run as run_communities, inspect_communities

    csv_path = Path(args.sponsors_csv)
    output_dir = Path(args.out_dir) if args.out_dir else AGENTS_OUTPUT_DIR
    resolution = args.resolution
    sb_client = _get_supabase_client_if_enabled()

    records = run_communities(csv_path, output_dir, resolution, inspect=False, supabase_client=sb_client)

    if args.inspect:
        print(inspect_communities(records))
    else:
        summary = {
            "communities": len(records),
            "total_docs": sum(len(r.member_agora_ids) for r in records),
            "output": str(output_dir / "communities.json"),
        }
        print(json.dumps(summary))
    return 0


def cmd_build_multiplex_graph(args: argparse.Namespace) -> int:
    import csv as csv_mod
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    agents_output_dir = Path(args.agents_output_dir) if args.agents_output_dir else AGENTS_OUTPUT_DIR
    graph_output_dir = Path(args.out_dir) if args.out_dir else MULTIPLEX_GRAPH_DIR
    agents_filter = args.agents if args.agents != "all" else None

    # Phase 1: sponsor graph (if requested or all)
    if args.agents in ("all", "sponsor") and args.sponsors_csv:
        from .agents.sponsor_graph import run as run_sponsor
        run_sponsor(Path(args.sponsors_csv), agents_output_dir)

    # Phase 1b: cosponsor graph (if requested or all)
    if args.agents in ("all", "sponsor", "cosponsor") and args.cosponsors_csv:
        from .agents.sponsor_graph import run_cosponsor
        run_cosponsor(Path(args.cosponsors_csv), agents_output_dir)

    # Phase 2: community detection (if requested or all)
    if args.agents in ("all", "community") and args.sponsors_csv:
        from .agents.community_detector import run as run_community
        sb_client = _get_supabase_client_if_enabled()
        run_community(Path(args.sponsors_csv), agents_output_dir, args.resolution, supabase_client=sb_client)

    # Phase 3: NER (if requested or all)
    if args.agents in ("all", "ner") and args.sponsors_csv:
        from .agents.community_detector import load_docs_csv
        from .agents.models_agent import CommunityRecord
        from .agents.ner_agent import run as run_ner

        communities_path = agents_output_dir / "communities.json"
        if communities_path.exists():
            raw = json.loads(communities_path.read_text(encoding="utf-8"))
            communities = [CommunityRecord.from_dict(c) for c in raw]

            # Build doc metadata from sponsors CSV
            csv_path = Path(args.sponsors_csv)
            rows = load_docs_csv(csv_path)
            doc_metadata = {}
            for row in rows:
                aid = row.get("AGORA ID", "").strip()
                if aid:
                    doc_metadata[aid] = {
                        "official_name": row.get("Official name", ""),
                        "short_summary": row.get("Short summary", ""),
                    }

            fulltext_dir = Path(args.fulltext_dir) if args.fulltext_dir else Path("fulltext")

            run_ner(
                communities, doc_metadata, fulltext_dir,
                agents_output_dir,
                community_filter=args.community,
                limit=args.limit,
            )

    # Phase 5: graph assembly
    from .agents.graph_builder import run as run_graph_build
    stats = run_graph_build(agents_output_dir, graph_output_dir, agents_filter)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_sync_supabase(args: argparse.Namespace) -> int:
    from .supabase.sync import run as run_sync
    tables = [t.strip() for t in args.tables.split(",")] if args.tables else None
    run_sync(
        tables=tables,
        dry_run=args.dry_run,
        record_id=args.record_id or "",
    )
    return 0


def cmd_query_neighborhood(args: argparse.Namespace) -> int:
    payload = run_graph_query(
        graph_dir=Path(args.graph_dir),
        seed_node_id=args.seed_node_id,
        max_hops=args.max_hops,
        relation_filter=set(args.relation or []),
        node_type_filter=set(args.node_type or []),
        limit=args.limit,
        ranked=not args.unranked,
        direction=args.direction,
    )
    print(json.dumps(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest", description="Congress.gov candidate discovery pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("build-knowledge-graph", help="Build AGORA knowledge graph nodes/edges from CSV sources")
    kg.add_argument("--documents-csv", default="documents.csv")
    kg.add_argument("--segments-csv", default="segments.csv")
    kg.add_argument("--authorities-csv", default="authorities.csv")
    kg.add_argument("--collections-csv", default="collections.csv")
    kg.add_argument("--out-dir", default="pipeline/graph")
    kg.set_defaults(func=cmd_build_knowledge_graph)

    dc = sub.add_parser("detect-communities", help="Detect document communities via Louvain clustering")
    dc.add_argument("--sponsors-csv", default="knowledge_graph/data/agora_with_sponsors.csv")
    dc.add_argument("--out-dir", default="")
    dc.add_argument("--resolution", type=float, default=LOUVAIN_RESOLUTION)
    dc.add_argument("--inspect", action="store_true", help="Print human-readable community summary")
    dc.set_defaults(func=cmd_detect_communities)

    mpx = sub.add_parser("build-multiplex-graph", help="Build multiplex knowledge graph from agent outputs")
    mpx.add_argument("--sponsors-csv", default="knowledge_graph/graph_data/agora_comprehensive_data_with_cosponsor_lists.csv")
    mpx.add_argument("--cosponsors-csv", default="knowledge_graph/graph_data/agora_cosponsors_long.csv")
    mpx.add_argument("--fulltext-dir", default="fulltext")
    mpx.add_argument("--agents-output-dir", default="")
    mpx.add_argument("--out-dir", default="")
    mpx.add_argument("--agents", default="all", choices=["all", "sponsor", "cosponsor", "community", "ner"],
                     help="Which agent phases to run")
    mpx.add_argument("--community", default="", help="Filter NER to single community_id")
    mpx.add_argument("--limit", type=int, default=0, help="Limit docs per community (for calibration)")
    mpx.add_argument("--resolution", type=float, default=LOUVAIN_RESOLUTION)
    mpx.set_defaults(func=cmd_build_multiplex_graph)

    ss = sub.add_parser("sync-supabase", help="Download latest Zenodo release and upsert into Supabase")
    ss.add_argument("--tables", default="", help="Comma-separated subset of tables (default: all)")
    ss.add_argument("--dry-run", action="store_true", help="Parse and validate only, no writes")
    ss.add_argument("--record-id", default="", help="Override ZENODO_RECORD_ID from config")
    ss.set_defaults(func=cmd_sync_supabase)

    nq = sub.add_parser("query-neighborhood", help="Query neighborhood around a seed node in graph export")
    nq.add_argument("--graph-dir", default="pipeline/graph")
    nq.add_argument("--seed-node-id", required=True)
    nq.add_argument("--max-hops", type=int, default=2)
    nq.add_argument("--relation", action="append", default=[])
    nq.add_argument("--node-type", action="append", default=[])
    nq.add_argument("--limit", type=int, default=200)
    nq.add_argument("--unranked", action="store_true")
    nq.add_argument("--direction", choices=["out", "in", "both"], default="out")
    nq.set_defaults(func=cmd_query_neighborhood)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
