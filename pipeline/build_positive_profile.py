from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


TOKEN_RE = re.compile(r"[a-z][a-z0-9_\-]{2,}")


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def text_sha(text: str) -> str:
    return sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _as_bool_or_text(raw: str) -> str | bool:
    val = (raw or "").strip().lower()
    if val == "true":
        return True
    if val == "false":
        return False
    return (raw or "").strip()


def _csv_get(row: dict[str, str], key: str) -> str:
    if key in row:
        return (row.get(key) or "").strip()
    bom_key = f"\ufeff{key}"
    return (row.get(bom_key) or "").strip()


def build_profile_text(
    official_name: str,
    casual_name: str,
    short_summary: str,
    long_summary: str,
    tags: str,
    collections: list[str],
    most_recent_activity: str,
) -> str:
    ordered_parts = [
        official_name,
        casual_name,
        short_summary,
        long_summary,
        tags,
        "; ".join(collections),
        most_recent_activity,
    ]
    return normalize_space(" ".join([p for p in ordered_parts if p]))


@dataclass
class ProfileRow:
    agora_id: str
    official_name: str
    casual_name: str
    link_to_document: str
    authority: str
    collections: list[str]
    most_recent_activity: str
    most_recent_activity_date: str
    short_summary: str
    long_summary: str
    tags: str
    official_plaintext_retrieved: str | bool
    official_plaintext_source: str
    profile_text: str
    profile_text_sha256: str
    label_agora_fit: int
    label_source: str
    snapshot_date: str
    record_origin: str

    def as_json_dict(self) -> dict:
        return asdict(self)

    def as_csv_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["collections"] = ";".join(self.collections)
        return payload


def load_rows(input_csv: Path, snapshot_date: str) -> tuple[list[ProfileRow], dict]:
    exclusions = Counter()
    by_agora_id: dict[str, ProfileRow] = {}
    duplicate_drops = 0

    with input_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            agora_id = _csv_get(raw, "AGORA ID")
            official_name = _csv_get(raw, "Official name")
            casual_name = _csv_get(raw, "Casual name")
            short_summary = _csv_get(raw, "Short summary")
            long_summary = _csv_get(raw, "Long summary")
            tags = _csv_get(raw, "Tags")

            if not agora_id:
                exclusions["missing_agora_id"] += 1
                continue

            if not any([official_name, casual_name, short_summary, long_summary, tags]):
                exclusions["missing_text_fields"] += 1
                continue

            collections = [normalize_space(c) for c in _csv_get(raw, "Collections").split(";") if normalize_space(c)]
            profile_text = build_profile_text(
                official_name=official_name,
                casual_name=casual_name,
                short_summary=short_summary,
                long_summary=long_summary,
                tags=tags,
                collections=collections,
                most_recent_activity=_csv_get(raw, "Most recent activity"),
            )

            if not profile_text:
                exclusions["empty_profile_text"] += 1
                continue

            row = ProfileRow(
                agora_id=agora_id,
                official_name=official_name,
                casual_name=casual_name,
                link_to_document=_csv_get(raw, "Link to document"),
                authority=_csv_get(raw, "Authority"),
                collections=collections,
                most_recent_activity=_csv_get(raw, "Most recent activity"),
                most_recent_activity_date=_csv_get(raw, "Most recent activity date"),
                short_summary=short_summary,
                long_summary=long_summary,
                tags=tags,
                official_plaintext_retrieved=_as_bool_or_text(_csv_get(raw, "Official plaintext retrieved")),
                official_plaintext_source=_csv_get(raw, "Official plaintext source"),
                profile_text=profile_text,
                profile_text_sha256=text_sha(profile_text),
                label_agora_fit=1,
                label_source="documents_csv",
                snapshot_date=snapshot_date,
                record_origin=str(input_csv),
            )

            existing = by_agora_id.get(agora_id)
            if existing is None:
                by_agora_id[agora_id] = row
                continue

            if len(row.profile_text) > len(existing.profile_text):
                by_agora_id[agora_id] = row
                duplicate_drops += 1
            else:
                duplicate_drops += 1

    rows = sorted(
        by_agora_id.values(),
        key=lambda r: (0, int(r.agora_id)) if r.agora_id.isdigit() else (1, r.agora_id),
    )
    stats = {
        "rows_kept": len(rows),
        "exclusions": dict(exclusions),
        "duplicate_rows_dropped": duplicate_drops,
    }
    return rows, stats


def top_tokens(texts: list[str], k: int = 50) -> list[dict[str, int]]:
    counts = Counter()
    for text in texts:
        counts.update(TOKEN_RE.findall((text or "").lower()))
    return [{"token": tok, "count": cnt} for tok, cnt in counts.most_common(k)]


def build_report(rows: list[ProfileRow], stats: dict, input_csv: Path, out_prefix: Path) -> dict:
    lengths = sorted(len(r.profile_text) for r in rows)
    median_len = lengths[len(lengths) // 2] if lengths else 0
    non_empty = sum(1 for r in rows if r.profile_text)
    non_empty_rate = (non_empty / len(rows)) if rows else 0.0
    uniq_ids = len({r.agora_id for r in rows})

    report = {
        "dataset": "agora_positive_profile_v1",
        "total_positive_documents": len(rows),
        "rows_kept": len(rows),
        "profile_text_non_empty_rate": round(non_empty_rate, 6),
        "median_profile_text_length_chars": median_len,
        "duplicate_agora_id_after_dedup": len(rows) - uniq_ids,
        "top_50_tokens": top_tokens([r.profile_text for r in rows], k=50),
        "exclusions": stats["exclusions"],
        "duplicate_rows_dropped": stats["duplicate_rows_dropped"],
        "quality_gates": {
            "rows_kept_gt_zero": len(rows) > 0,
            "profile_text_non_empty_rate_gte_0_99": non_empty_rate >= 0.99,
            "duplicate_agora_id_after_dedup_eq_zero": (len(rows) - uniq_ids) == 0,
        },
        "docx_readiness_note": "This positive-only artifact is ready for TF-IDF/embedding similarity against new DOCX files in Step 2.",
        "paths": {
            "input_csv": str(input_csv),
            "jsonl": str(out_prefix.with_suffix(".jsonl")),
            "csv": str(out_prefix.with_suffix(".csv")),
            "report": str(out_prefix.parent / f"{out_prefix.name}_report.json"),
            "lineage": str(out_prefix.parent / f"{out_prefix.name}_lineage.json"),
        },
    }
    return report


def build_lineage(input_csv: Path, rows: list[ProfileRow], report: dict) -> dict:
    return {
        "dataset": "agora_positive_profile_v1",
        "built_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_sources": [{"path": str(input_csv)}],
        "row_count": len(rows),
        "schema_version": 1,
        "label_policy": {
            "accepted_definition": "Any row present in documents.csv is treated as accepted.",
            "label_agora_fit": 1,
            "label_source": "documents_csv",
            "negatives_included": False,
        },
        "quality_gates": report["quality_gates"],
    }


def validate_quality_gates(report: dict) -> None:
    gates = report["quality_gates"]
    failed = [name for name, passed in gates.items() if not passed]
    if failed:
        raise ValueError(f"Quality gate failure: {', '.join(failed)}")


def write_outputs(rows: list[ProfileRow], out_prefix: Path, report: dict, lineage: dict) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_prefix.with_suffix(".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.as_json_dict(), ensure_ascii=True) + "\n")

    csv_path = out_prefix.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = list(rows[0].as_csv_dict().keys()) if rows else [
            "agora_id",
            "official_name",
            "casual_name",
            "link_to_document",
            "authority",
            "collections",
            "most_recent_activity",
            "most_recent_activity_date",
            "short_summary",
            "long_summary",
            "tags",
            "official_plaintext_retrieved",
            "official_plaintext_source",
            "profile_text",
            "profile_text_sha256",
            "label_agora_fit",
            "label_source",
            "snapshot_date",
            "record_origin",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())

    report_path = out_prefix.parent / f"{out_prefix.name}_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lineage_path = out_prefix.parent / f"{out_prefix.name}_lineage.json"
    lineage_path.write_text(json.dumps(lineage, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run(input_csv: Path, out_prefix: Path) -> dict:
    snapshot = utc_date()
    rows, stats = load_rows(input_csv=input_csv, snapshot_date=snapshot)
    report = build_report(rows=rows, stats=stats, input_csv=input_csv, out_prefix=out_prefix)
    validate_quality_gates(report)
    lineage = build_lineage(input_csv=input_csv, rows=rows, report=report)
    write_outputs(rows=rows, out_prefix=out_prefix, report=report, lineage=lineage)
    return {
        "rows_kept": report["rows_kept"],
        "jsonl": str(out_prefix.with_suffix(".jsonl")),
        "csv": str(out_prefix.with_suffix(".csv")),
        "report": str(out_prefix.parent / f"{out_prefix.name}_report.json"),
        "lineage": str(out_prefix.parent / f"{out_prefix.name}_lineage.json"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build positive-only AGORA profile dataset from documents.csv")
    default_input = Path(__file__).resolve().parents[1] / "documents.csv"
    default_out = Path(__file__).resolve().parent / "datasets" / "agora_positive_profile_v1"
    parser.add_argument("--input-csv", default=str(default_input), help="Path to documents.csv")
    parser.add_argument(
        "--out-prefix",
        default=str(default_out),
        help="Output prefix path without extension, e.g., pipeline/datasets/agora_positive_profile_v1",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run(input_csv=Path(args.input_csv), out_prefix=Path(args.out_prefix))
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
