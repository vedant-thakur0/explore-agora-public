from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .congress import build_records, fetch_bills, hydrate_text
from .ranker import RankConfig, TfidfCentroid, load_reference_texts, rank_records


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = int(round((len(values) - 1) * p))
    idx = max(0, min(len(values) - 1, idx))
    return values[idx]


def _count_signals(matched_signals: list[str]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for signal_blob in matched_signals:
        for sig in signal_blob.split(";"):
            sig = sig.strip()
            if sig:
                counter[sig] += 1
    return counter.most_common(12)


def _serialize_top(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": row["rank"],
            "source_id": row["source_id"],
            "title": row["title"],
            "score": row["score"],
            "tier": row["tier"],
            "matched_signals": row["matched_signals"],
        }
        for row in rows
    ]


def _log_stage(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"[stage] {msg}", flush=True)


def _log_progress(enabled: bool, phase: str, done: int, total: int, ok: int, failed: int, elapsed: float) -> None:
    if enabled:
        print(
            f"[progress][{phase}] {done}/{total} ok={ok} fail={failed} elapsed={elapsed:.1f}s",
            flush=True,
        )


def _log_error_sample(enabled: bool, phase: str, source_id: str, error_text: str) -> None:
    if enabled:
        print(f"[warn][{phase}] source={source_id} error={error_text}", flush=True)


def _http_get_json(url: str, params: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    query = urlencode(params)
    sep = "&" if "?" in url else "?"
    req = Request(f"{url}{sep}{query}", headers={"Accept": "application/json", "User-Agent": "agora-candidate-pipeline/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_detail_record(source_url: str, api_key: str, timeout: int) -> dict[str, Any]:
    return _http_get_json(source_url, {"api_key": api_key, "format": "json"}, timeout=timeout)


def _extract_detail_item(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported detail payload type: {type(payload).__name__}")

    if "bill" in payload:
        bill_val = payload.get("bill")
        if isinstance(bill_val, dict):
            return bill_val
        raise ValueError(f"Unsupported bill field type: {type(bill_val).__name__}")

    for key in ("bills", "items"):
        arr = payload.get(key)
        if isinstance(arr, list) and arr:
            first = arr[0]
            if isinstance(first, dict):
                if "bill" in first:
                    nested_bill = first.get("bill")
                    if isinstance(nested_bill, dict):
                        return nested_bill
                    raise ValueError(f"Unsupported nested bill field type: {type(nested_bill).__name__}")
                # Accept only objects that already look like a bill record.
                if all(k in first for k in ("congress", "type", "number")):
                    return first

    # Fallback only when payload itself looks like a bill object and has no nested bill key.
    if all(k in payload for k in ("congress", "type", "number")):
        return payload

    raise ValueError("Unsupported detail payload shape")


def _hydrate_details(
    records,
    api_key: str,
    max_retries: int,
    delay_sec: float,
    timeout: int,
    progress_every: int,
    max_error_samples: int,
    verbose: bool,
) -> tuple[list[Any], int, int]:
    detailed = []
    failed = 0
    success = 0
    printed_errors = 0
    suppressed_errors = 0
    total = len(records)
    start = time.time()

    for idx, rec in enumerate(records, start=1):
        upgraded = rec
        rec_failed = False

        if rec.source_url:
            for attempt in range(max_retries + 1):
                try:
                    payload = _fetch_detail_record(rec.source_url, api_key, timeout)
                    item = _extract_detail_item(payload)
                    items = [item]
                    upgraded = build_records(items)[0]
                    if not upgraded.source_url:
                        upgraded.source_url = rec.source_url
                    break
                except Exception as exc:
                    if attempt >= max_retries:
                        rec_failed = True
                        failed += 1
                        if printed_errors < max_error_samples:
                            _log_error_sample(verbose, "detail", rec.source_id, str(exc)[:220])
                            printed_errors += 1
                        else:
                            suppressed_errors += 1
                    else:
                        time.sleep(delay_sec)
        else:
            rec_failed = True
            failed += 1

        if not rec_failed:
            success += 1

        detailed.append(upgraded)

        if delay_sec > 0:
            time.sleep(delay_sec)

        if idx % max(1, progress_every) == 0 or idx == total:
            _log_progress(verbose, "details", idx, total, success, failed, time.time() - start)

    return detailed, failed, suppressed_errors


def _hydrate_texts_with_progress(records, progress_every: int, verbose: bool) -> tuple[list[Any], int, int]:
    hydrated = []
    with_text = 0
    missing_or_failed = 0
    total = len(records)
    start = time.time()

    for idx, rec in enumerate(records, start=1):
        out = hydrate_text(rec)
        hydrated.append(out)
        if out.text.strip():
            with_text += 1
        else:
            missing_or_failed += 1

        if idx % max(1, progress_every) == 0 or idx == total:
            _log_progress(verbose, "text", idx, total, with_text, missing_or_failed, time.time() - start)

    return hydrated, with_text, missing_or_failed


def run_trial(args: argparse.Namespace) -> dict[str, Any]:
    api_key = args.api_key or os.getenv("CONGRESS_API_KEY", "")
    verbose = not args.quiet

    if not api_key and not args.fixture_json:
        raise SystemExit("CONGRESS_API_KEY is required unless --fixture-json is supplied")

    _log_stage(verbose, f"fetching list since={args.since} limit={args.limit}")
    bills = fetch_bills(
        since=args.since,
        limit=args.limit,
        api_key=api_key,
        api_url=args.api_url,
        fixture_path=args.fixture_json,
    )
    _log_stage(verbose, f"list fetch complete fetched_total={len(bills)}")

    records = build_records(bills)
    hr_records = [r for r in records if r.bill_type.lower() == "hr"]
    _log_stage(verbose, f"filtered hr_total={len(hr_records)}")

    detail_failures = 0
    suppressed_detail_errors = 0
    if args.hydrate_details and not args.fixture_json:
        _log_stage(verbose, "starting per-bill detail hydration")
        hr_records, detail_failures, suppressed_detail_errors = _hydrate_details(
            hr_records,
            api_key=api_key,
            max_retries=args.detail_max_retries,
            delay_sec=args.detail_delay_sec,
            timeout=args.detail_timeout,
            progress_every=args.progress_every,
            max_error_samples=args.max_error_samples,
            verbose=verbose,
        )
        _log_stage(verbose, f"detail hydration complete failures={detail_failures}")

    _log_stage(verbose, "starting text hydration")
    hydrated, with_text_count, missing_or_failed_count = _hydrate_texts_with_progress(
        hr_records,
        progress_every=args.progress_every,
        verbose=verbose,
    )
    _log_stage(verbose, f"text hydration complete text_available={with_text_count}")

    scorable = [r for r in hydrated if len(r.text.strip()) >= args.min_text_chars]
    unscorable = [r for r in hydrated if len(r.text.strip()) < args.min_text_chars]

    _log_stage(verbose, "building semantic reference")
    ref_texts = load_reference_texts(Path(args.reference_csv))
    vectorizer = TfidfCentroid.fit(ref_texts)

    cfg = RankConfig(
        min_score_for_export=args.min_score,
        high_threshold=args.high_threshold,
        medium_threshold=args.medium_threshold,
    )

    _log_stage(verbose, f"ranking complete scorable={len(scorable)}")
    ranked = rank_records("trial_one_call_hr", scorable, vectorizer, cfg)

    tier_counts = Counter(c.candidate_tier for c in ranked)
    scores_sorted = sorted([c.candidate_score for c in ranked])
    signal_counts = _count_signals([c.matched_signals for c in ranked])

    top_rows = []
    for i, c in enumerate(ranked[: args.top_k], start=1):
        top_rows.append(
            {
                "rank": i,
                "source_id": c.source_id,
                "title": c.title,
                "score": round(c.candidate_score, 6),
                "tier": c.candidate_tier,
                "matched_signals": c.matched_signals,
                "evidence_snippets": c.evidence_snippets,
                "source_url": c.source_url,
            }
        )

    summary = {
        "fetched_total": len(bills),
        "hr_total": len(hr_records),
        "detail_failures": detail_failures,
        "suppressed_error_count": suppressed_detail_errors,
        "text_available": with_text_count,
        "scorable": len(scorable),
        "unscorable": len(unscorable),
        "missing_text_pct": round((len(hr_records) - with_text_count) / len(hr_records), 4) if hr_records else 0.0,
    }

    diagnostics = {
        "score_p25": round(_pct(scores_sorted, 0.25), 6),
        "score_p50": round(median(scores_sorted), 6) if scores_sorted else 0.0,
        "score_p75": round(_pct(scores_sorted, 0.75), 6),
        "top_signals": [{"signal": k, "count": v} for k, v in signal_counts],
    }

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "since": args.since,
            "limit": args.limit,
            "top_k": args.top_k,
            "min_text_chars": args.min_text_chars,
            "reference_csv": args.reference_csv,
            "high_threshold": args.high_threshold,
            "medium_threshold": args.medium_threshold,
            "min_score": args.min_score,
            "api_url": args.api_url,
            "fixture_json": args.fixture_json,
            "hydrate_details": args.hydrate_details,
            "detail_delay_sec": args.detail_delay_sec,
            "detail_max_retries": args.detail_max_retries,
            "detail_timeout": args.detail_timeout,
            "progress_every": args.progress_every,
            "max_error_samples": args.max_error_samples,
            "quiet": args.quiet,
        },
        "summary": summary,
        "tier_counts": dict(tier_counts),
        "top_k": _serialize_top(top_rows),
        "diagnostics": diagnostics,
        "top_k_with_evidence": top_rows,
    }


def print_report(report: dict[str, Any]) -> None:
    print("SUMMARY")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=True))

    print("\nTIER_COUNTS")
    print(json.dumps(report["tier_counts"], indent=2, ensure_ascii=True))

    print("\nTOP_K")
    for row in report["top_k"]:
        print(
            f"{row['rank']:>3} | {row['score']:.6f} | {row['tier']:<6} | {row['source_id']} | "
            f"{row['title'][:90]}"
        )
        if row["matched_signals"]:
            print(f"      signals: {row['matched_signals'][:220]}")

    print("\nDIAGNOSTICS")
    print(json.dumps(report["diagnostics"], indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-call congress.gov HR trial ranker")
    parser.add_argument("--since", default="2026-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--min-text-chars", type=int, default=200)
    parser.add_argument("--reference-csv", default="agora/documents_us_federal_with_fulltext.csv")
    parser.add_argument("--high-threshold", type=float, default=0.7)
    parser.add_argument("--medium-threshold", type=float, default=0.4)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--api-url", default="https://api.congress.gov/v3/bill")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--fixture-json", default="")
    parser.add_argument("--hydrate-details", action="store_true", help="Fetch per-bill detail records before text hydration")
    parser.add_argument("--detail-delay-sec", type=float, default=0.1, help="Delay between detail requests")
    parser.add_argument("--detail-max-retries", type=int, default=2, help="Retries per detail request")
    parser.add_argument("--detail-timeout", type=int, default=30, help="Timeout per detail request in seconds")
    parser.add_argument("--progress-every", type=int, default=25, help="Progress print interval")
    parser.add_argument("--max-error-samples", type=int, default=5, help="Max per-record error lines")
    parser.add_argument("--quiet", action="store_true", help="Suppress stage/progress logs")
    parser.add_argument("--out-json", default="", help="Optional JSON report output path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_trial(args)
    print_report(report)

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"\nWROTE_JSON\n{out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
