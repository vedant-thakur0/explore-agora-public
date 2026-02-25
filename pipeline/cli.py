from __future__ import annotations

import argparse
import os
from pathlib import Path
import json

from .congress import build_records, fetch_bills, hydrate_text, new_run_id
from .ranker import RankConfig, TfidfCentroid, load_reference_texts, rank_records
from .store import export_review_csv, load_run_documents, reviewed_decisions_index, save_candidates, save_fetch_run
from .trial_one_call_hr import run_trial, print_report


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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
