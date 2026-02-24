from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv

from .config import FULLTEXT_DIR, NORMALIZED_DIR, RAW_DIR, REVIEW_EXPORTS_DIR, RUNS_DIR
from .congress import fulltext_filename
from .models import CandidateRecord, DocumentRecord, append_jsonl, read_json, read_jsonl, write_json


def ensure_dirs() -> None:
    for path in [RAW_DIR, NORMALIZED_DIR, FULLTEXT_DIR, RUNS_DIR, REVIEW_EXPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def manifest_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def candidates_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}_candidates.jsonl"


def save_fetch_run(run_id: str, raw_payload: dict, records: list[DocumentRecord]) -> dict:
    ensure_dirs()
    raw_path = RAW_DIR / f"{run_id}_bills.json"
    normalized_path = NORMALIZED_DIR / f"{run_id}_documents.jsonl"

    write_json(raw_path, raw_payload)
    append_jsonl(normalized_path, [r.to_dict() for r in records])

    for rec in records:
        if rec.text:
            (FULLTEXT_DIR / fulltext_filename(rec.source_id)).write_text(rec.text, encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_path": str(raw_path),
        "normalized_path": str(normalized_path),
        "records_fetched": len(records),
        "records_with_text": sum(1 for r in records if r.text),
        "status": "fetched",
    }
    write_json(manifest_path(run_id), manifest)
    return manifest


def load_run_documents(run_id: str) -> list[DocumentRecord]:
    mf = read_json(manifest_path(run_id))
    rows = read_jsonl(Path(mf["normalized_path"]))
    return [DocumentRecord.from_dict(r) for r in rows]


def save_candidates(run_id: str, candidates: list[CandidateRecord], skipped_reviewed: int) -> dict:
    cpath = candidates_path(run_id)
    if cpath.exists():
        cpath.unlink()
    append_jsonl(cpath, [c.to_dict() for c in candidates])

    mf_path = manifest_path(run_id)
    mf = read_json(mf_path)
    mf.update(
        {
            "candidates_path": str(cpath),
            "records_ranked": len(candidates),
            "records_skipped_reviewed": skipped_reviewed,
            "status": "ranked",
        }
    )
    write_json(mf_path, mf)
    return mf


def load_candidates(run_id: str) -> list[CandidateRecord]:
    rows = read_jsonl(candidates_path(run_id))
    out = []
    for r in rows:
        out.append(
            CandidateRecord(
                run_id=r["run_id"],
                source_id=r["source_id"],
                source_url=r["source_url"],
                title=r["title"],
                candidate_score=float(r["candidate_score"]),
                candidate_tier=r["candidate_tier"],
                evidence_snippets=r.get("evidence_snippets", ""),
                matched_signals=r.get("matched_signals", ""),
                text_sha256=r["text_sha256"],
                review_decision=r.get("review_decision", ""),
                review_notes=r.get("review_notes", ""),
                reviewed_by=r.get("reviewed_by", ""),
                reviewed_at=r.get("reviewed_at", ""),
            )
        )
    return out


def reviewed_decisions_index() -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    for path in REVIEW_EXPORTS_DIR.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                decision = (row.get("decision") or "").strip().lower()
                if decision in {"include", "reject", "unsure"}:
                    source_id = (row.get("source_id") or "").strip()
                    sha = (row.get("text_sha256") or "").strip()
                    if source_id and sha:
                        seen.add((source_id, sha))
    return seen


def export_review_csv(run_id: str, out_path: Path | None = None) -> Path:
    ensure_dirs()
    candidates = load_candidates(run_id)

    if out_path is None:
        out_path = REVIEW_EXPORTS_DIR / f"{run_id}_review.csv"

    fields = [
        "run_id",
        "source_id",
        "source_url",
        "title",
        "candidate_score",
        "candidate_tier",
        "matched_signals",
        "evidence_snippets",
        "text_sha256",
        "decision",
        "notes",
        "reviewed_by",
        "reviewed_at",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for c in candidates:
            writer.writerow(
                {
                    "run_id": c.run_id,
                    "source_id": c.source_id,
                    "source_url": c.source_url,
                    "title": c.title,
                    "candidate_score": round(c.candidate_score, 6),
                    "candidate_tier": c.candidate_tier,
                    "matched_signals": c.matched_signals,
                    "evidence_snippets": c.evidence_snippets,
                    "text_sha256": c.text_sha256,
                    "decision": "",
                    "notes": "",
                    "reviewed_by": "",
                    "reviewed_at": "",
                }
            )

    mf = read_json(manifest_path(run_id))
    mf.update({"review_export_path": str(out_path), "status": "exported"})
    write_json(manifest_path(run_id), mf)
    return out_path
