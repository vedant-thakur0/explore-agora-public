from __future__ import annotations

import argparse
import os
from pathlib import Path
import json

from dotenv import load_dotenv

# Load .env from repo root (or from alongside cli.py)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # adjust parents[] if needed
load_dotenv(dotenv_path=ENV_PATH)

from .config import (
    AGENTS_OUTPUT_DIR, MULTIPLEX_GRAPH_DIR, LOUVAIN_RESOLUTION, REPORTS_GENERATED_DIR,
    DOCUMENTS_CSV_PATH, SEGMENTS_CSV_PATH, AUTHORITIES_CSV_PATH, COLLECTIONS_CSV_PATH,
)
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


def cmd_sync_ner_entities(args: argparse.Namespace) -> int:
    from .supabase.ner_sync import run as run_ner_sync
    run_ner_sync(
        entity_dict_path=Path(args.entity_dict) if args.entity_dict else None,
        annotations_dir=Path(args.annotations_dir) if args.annotations_dir else None,
        canonicalized_path=Path(args.canonicalized) if args.canonicalized else None,
        dry_run=args.dry_run,
    )
    return 0


def cmd_eval_ner(args: argparse.Namespace) -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from .agents.ner_eval import evaluate
    predicted_path = Path(args.predicted) if args.predicted else None
    gold_dir = Path(args.gold_dir) if args.gold_dir else None
    report = evaluate(predicted_path=predicted_path, gold_dir=gold_dir)
    print(json.dumps(report, indent=2))
    return 0


def cmd_seed_registry(args: argparse.Namespace) -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from .agents.canonical_registry import seed_registry
    from .config import (
        ENTITY_DICTIONARY_PATH,
        CANONICAL_ENTITY_MAP_PATH,
        MANUAL_ANNOTATIONS_DIR,
        TYPE_AUTHORITY_PATH,
        GLOBAL_REGISTRY_PATH,
    )

    registry = seed_registry(
        entity_dictionary_path=ENTITY_DICTIONARY_PATH,
        canonical_map_path=CANONICAL_ENTITY_MAP_PATH,
        manual_annotations_dir=MANUAL_ANNOTATIONS_DIR,
        type_authority_path=TYPE_AUTHORITY_PATH if not args.no_type_authority else None,
    )
    out_path = Path(args.output) if args.output else GLOBAL_REGISTRY_PATH
    registry.save(out_path)
    print(json.dumps(registry.stats(), indent=2))
    return 0


def cmd_canonicalize(args: argparse.Namespace) -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from .agents.canonicalize import run as run_canonicalize

    report = run_canonicalize()
    print(json.dumps(report, indent=2))
    return 0


def cmd_reports(args: argparse.Namespace) -> int:
    from .reports import build_report
    out_root = REPORTS_GENERATED_DIR
    index_path = build_report(
        out_root=out_root,
        execute=args.execute,
        allow_errors=args.allow_errors,
        nb_timeout=args.timeout,
    )
    print(f"Report index: {index_path}")
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
    kg.add_argument("--documents-csv", default=str(DOCUMENTS_CSV_PATH))
    kg.add_argument("--segments-csv", default=str(SEGMENTS_CSV_PATH))
    kg.add_argument("--authorities-csv", default=str(AUTHORITIES_CSV_PATH))
    kg.add_argument("--collections-csv", default=str(COLLECTIONS_CSV_PATH))
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

    ner = sub.add_parser("sync-ner-entities", help="Sync NER entity dictionary and document-entity mappings to Supabase")
    ner.add_argument("--entity-dict", default="", help="Path to entity_dictionary.jsonl")
    ner.add_argument("--annotations-dir", default="", help="Path to manual_annotations directory")
    ner.add_argument("--canonicalized", default="", help="Path to entities_canonicalized.jsonl (default: agents/output/entities_canonicalized.jsonl)")
    ner.add_argument("--dry-run", action="store_true", help="Parse and validate only, no writes")
    ner.set_defaults(func=cmd_sync_ner_entities)

    ev = sub.add_parser("eval-ner", help="Evaluate NER output against manual annotations")
    ev.add_argument("--predicted", default="", help="Path to entities.jsonl (default: agents/output/entities.jsonl)")
    ev.add_argument("--gold-dir", default="", help="Path to manual_annotations directory")
    ev.set_defaults(func=cmd_eval_ner)

    sr = sub.add_parser("seed-registry", help="Seed or rebuild the global canonical entity registry")
    sr.add_argument("--output", default="", help="Output path for registry JSON")
    sr.add_argument("--no-type-authority", action="store_true", help="Skip type authority corrections")
    sr.set_defaults(func=cmd_seed_registry)

    cn = sub.add_parser("canonicalize", help="Flag bare aliases in review queue with resolution context")
    cn.set_defaults(func=cmd_canonicalize)

    rp = sub.add_parser("reports", help="Build a self-contained dated HTML report bundle for the internal team")
    rp.add_argument("--execute", action="store_true",
                    help="Execute notebooks before rendering (off by default; notebooks have known bugs)")
    rp.add_argument("--allow-errors", action="store_true",
                    help="Continue notebook execution past cell errors (only relevant with --execute)")
    rp.add_argument("--timeout", type=int, default=300,
                    help="Per-notebook execution timeout in seconds (default: 300; only relevant with --execute)")
    rp.set_defaults(func=cmd_reports)

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
