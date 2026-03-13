from __future__ import annotations

import argparse
import os
from pathlib import Path
import json

from dotenv import load_dotenv

# Load .env from repo root (or from alongside cli.py)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # adjust parents[] if needed
load_dotenv(dotenv_path=ENV_PATH)

from .config import RUNS_DIR, AGENTS_OUTPUT_DIR, MULTIPLEX_GRAPH_DIR, LOUVAIN_RESOLUTION
from .congress import build_records, fetch_bills, hydrate_text, new_run_id
from .docx_matcher import run_docx_match
from .graph_query import run as run_graph_query
from .knowledge_graph import run as run_knowledge_graph
from .ranker import RankConfig, TfidfCentroid, load_reference_texts, rank_records
from .session_pull import SessionPullConfig, process_and_save
from .store import export_review_csv, load_run_documents, reviewed_decisions_index, save_candidates, save_fetch_run
from .trial_one_call_hr import run_trial, print_report


if load_dotenv is not None:
    load_dotenv()



def cmd_fetch(args: argparse.Namespace) -> int:
    run_id = args.run_id or new_run_id()
    bills = fetch_bills(
        since=args.since,
        limit=args.limit,
        api_key=args.api_key or os.getenv("CONGRESS_API_KEY", ""),
        api_url=args.api_url,
        fixture_path=args.fixture_json,
    )

    records = [hydrate_text(r) for r in build_records(bills)]
    raw_payload = {"run_id": run_id, "since": args.since, "limit": args.limit, "count": len(bills), "items": bills}
    manifest = save_fetch_run(run_id, raw_payload, records)
    print(json.dumps({"run_id": run_id, "records_fetched": manifest["records_fetched"], "records_with_text": manifest["records_with_text"]}))
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    docs = load_run_documents(args.run_id)

    reviewed = reviewed_decisions_index()
    filtered_docs = [d for d in docs if (d.source_id, d.text_sha256) not in reviewed]
    skipped = len(docs) - len(filtered_docs)

    ref_path = Path(args.reference_csv)
    ref_texts = load_reference_texts(ref_path)
    vectorizer = TfidfCentroid.fit(ref_texts)
    cfg = RankConfig(
        min_score_for_export=args.min_score,
        high_threshold=args.high_threshold,
        medium_threshold=args.medium_threshold,
    )

    candidates = rank_records(args.run_id, filtered_docs, vectorizer, cfg)
    manifest = save_candidates(args.run_id, candidates, skipped_reviewed=skipped)
    print(json.dumps({"run_id": args.run_id, "records_ranked": manifest["records_ranked"], "skipped_reviewed": skipped}))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    out = export_review_csv(args.run_id, Path(args.out) if args.out else None)
    print(json.dumps({"run_id": args.run_id, "review_export": str(out)}))
    return 0


def cmd_trial_one_call_hr(args: argparse.Namespace) -> int:
    report = run_trial(args)
    print_report(report)
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"\nWROTE_JSON\n{out_path}")
    return 0


def cmd_match_docx(args: argparse.Namespace) -> int:
    out_json = Path(args.out_json) if args.out_json else (RUNS_DIR / f"docx_match_{new_run_id()}.json")
    cfg = RankConfig(
        min_score_for_export=args.min_score,
        high_threshold=args.high_threshold,
        medium_threshold=args.medium_threshold,
    )
    payload = run_docx_match(
        docx_dir=Path(args.docx_dir),
        profile_jsonl=Path(args.profile_jsonl),
        out_json=out_json,
        top_k=args.top_k,
        cfg=cfg,
        max_profile_matches=args.max_profile_matches,
    )
    print(
        json.dumps(
            {
                "docs_discovered": payload["summary"]["docs_discovered"],
                "docs_parsed": payload["summary"]["docs_parsed"],
                "docs_ranked": payload["summary"]["docs_ranked"],
                "out_json": str(out_json),
            }
        )
    )
    return 0


def cmd_pull_session_texts(args: argparse.Namespace) -> int:
    cfg = SessionPullConfig(
        congress=args.congress,
        bill_type=args.bill_type,
        limit=args.limit,
        delay_sec=args.delay_sec,
        api_url_base=args.api_url_base,
        api_key=args.api_key or os.getenv("CONGRESS_API_KEY", ""),
    )
    out_json = Path(args.out_json) if args.out_json else (RUNS_DIR / f"session_text_pull_{new_run_id()}.json")
    payload = process_and_save(cfg, out_json)
    print(
        json.dumps(
            {
                "bills_fetched": payload["summary"]["bills_fetched"],
                "rows_with_text": payload["summary"]["rows_with_text"],
                "rows_failed": payload["summary"]["rows_failed"],
                "out_json": str(out_json),
            }
        )
    )
    return 0


def cmd_build_knowledge_graph(args: argparse.Namespace) -> int:
    payload = run_knowledge_graph(
        documents_csv=Path(args.documents_csv),
        segments_csv=Path(args.segments_csv),
        authorities_csv=Path(args.authorities_csv),
        collections_csv=Path(args.collections_csv),
        out_dir=Path(args.out_dir),
    )
    print(json.dumps(payload))
    return 0


def cmd_detect_communities(args: argparse.Namespace) -> int:
    from .agents.community_detector import run as run_communities, inspect_communities

    csv_path = Path(args.sponsors_csv)
    output_dir = Path(args.out_dir) if args.out_dir else AGENTS_OUTPUT_DIR
    resolution = args.resolution

    records = run_communities(csv_path, output_dir, resolution, inspect=False)

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

    # Phase 2: community detection (if requested or all)
    if args.agents in ("all", "community") and args.sponsors_csv:
        from .agents.community_detector import run as run_community
        run_community(Path(args.sponsors_csv), agents_output_dir, args.resolution)

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

            fulltext_dir = Path(args.fulltext_dir) if args.fulltext_dir else Path("knowledge_graph/data/fulltext")

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

    fetch = sub.add_parser("fetch", help="Fetch congressional documents and hydrate text")
    fetch.add_argument("--since", required=True, help="Start date YYYY-MM-DD")
    fetch.add_argument("--limit", type=int, default=100)
    fetch.add_argument("--api-key", default="")
    fetch.add_argument("--api-url", default="https://api.congress.gov/v3/bill")
    fetch.add_argument("--fixture-json", default="", help="Local JSON fixture file for offline runs")
    fetch.add_argument("--run-id", default="")
    fetch.set_defaults(func=cmd_fetch)

    rank = sub.add_parser("rank-candidates", help="Rank fetched docs for AI-policy inclusion")
    rank.add_argument("--run-id", required=True)
    rank.add_argument(
        "--reference-csv",
        default="agora/documents_us_federal_with_fulltext.csv",
        help="Reference corpus with Extracted full text column",
    )
    rank.add_argument("--min-score", type=float, default=0.35)
    rank.add_argument("--high-threshold", type=float, default=0.7)
    rank.add_argument("--medium-threshold", type=float, default=0.4)
    rank.set_defaults(func=cmd_rank)

    export = sub.add_parser("export-review", help="Export ranked candidates to review CSV")
    export.add_argument("--run-id", required=True)
    export.add_argument("--out", default="")
    export.set_defaults(func=cmd_export)

    trial = sub.add_parser("trial-one-call-hr", help="Single list call + optional per-bill hydration, then HR ranking")
    trial.add_argument("--since", default="2026-01-01", help="Start date YYYY-MM-DD")
    trial.add_argument("--limit", type=int, default=250)
    trial.add_argument("--top-k", type=int, default=50)
    trial.add_argument("--min-text-chars", type=int, default=200)
    trial.add_argument("--reference-csv", default="agora/documents_us_federal_with_fulltext.csv")
    trial.add_argument("--high-threshold", type=float, default=0.7)
    trial.add_argument("--medium-threshold", type=float, default=0.4)
    trial.add_argument("--min-score", type=float, default=0.0)
    trial.add_argument("--api-url", default="https://api.congress.gov/v3/bill")
    trial.add_argument("--api-key", default="")
    trial.add_argument("--fixture-json", default="")
    trial.add_argument("--hydrate-details", action="store_true", help="Fetch per-bill detail records before text hydration")
    trial.add_argument("--detail-delay-sec", type=float, default=0.1)
    trial.add_argument("--detail-max-retries", type=int, default=2)
    trial.add_argument("--detail-timeout", type=int, default=30)
    trial.add_argument("--progress-every", type=int, default=25)
    trial.add_argument("--max-error-samples", type=int, default=5)
    trial.add_argument("--quiet", action="store_true")
    trial.add_argument("--out-json", default="")
    trial.set_defaults(func=cmd_trial_one_call_hr)

    match_docx = sub.add_parser("match-docx", help="Match incoming .docx/.txt files to AGORA positive profile")
    match_docx.add_argument("--docx-dir", required=True, help="Directory containing .docx and/or .txt files")
    match_docx.add_argument(
        "--profile-jsonl",
        default="agora/pipeline/datasets/agora_positive_profile_v1.jsonl",
        help="Positive profile JSONL",
    )
    match_docx.add_argument("--out-json", default="", help="Output JSON path (default under pipeline/runs)")
    match_docx.add_argument("--top-k", type=int, default=50)
    match_docx.add_argument("--min-score", type=float, default=0.0)
    match_docx.add_argument("--high-threshold", type=float, default=0.7)
    match_docx.add_argument("--medium-threshold", type=float, default=0.4)
    match_docx.add_argument("--max-profile-matches", type=int, default=5)
    match_docx.set_defaults(func=cmd_match_docx)

    pull = sub.add_parser("pull-session-texts", help="Pull bill names for a congress/type, then fetch each bill text")
    pull.add_argument("--congress", type=int, required=True)
    pull.add_argument("--bill-type", default="hr")
    pull.add_argument("--limit", type=int, default=250)
    pull.add_argument("--delay-sec", type=float, default=0.2)
    pull.add_argument("--api-url-base", default="https://api.congress.gov/v3/bill")
    pull.add_argument("--api-key", default="")
    pull.add_argument("--out-json", default="")
    pull.set_defaults(func=cmd_pull_session_texts)

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
    mpx.add_argument("--sponsors-csv", default="knowledge_graph/data/agora_with_sponsors.csv")
    mpx.add_argument("--fulltext-dir", default="")
    mpx.add_argument("--agents-output-dir", default="")
    mpx.add_argument("--out-dir", default="")
    mpx.add_argument("--agents", default="all", choices=["all", "sponsor", "community", "ner"],
                     help="Which agent phases to run")
    mpx.add_argument("--community", default="", help="Filter NER to single community_id")
    mpx.add_argument("--limit", type=int, default=0, help="Limit docs per community (for calibration)")
    mpx.add_argument("--resolution", type=float, default=LOUVAIN_RESOLUTION)
    mpx.set_defaults(func=cmd_build_multiplex_graph)

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
