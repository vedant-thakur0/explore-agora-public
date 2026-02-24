from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def file_safe_id(value: str) -> str:
    clean = []
    for ch in value.lower():
        if ch.isalnum() or ch in ("_", "-", "."):
            clean.append(ch)
        else:
            clean.append("_")
    return "".join(clean).strip("_") or "unknown"


def text_sha(text: str) -> str:
    return sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class DocumentRecord:
    source_id: str
    source_url: str
    title: str
    congress: str = ""
    bill_type: str = ""
    bill_number: str = ""
    latest_action_text: str = ""
    latest_action_date: str = ""
    update_date: str = ""
    sponsors: list[str] = field(default_factory=list)
    committees: list[str] = field(default_factory=list)
    text: str = ""
    text_source_url: str = ""
    text_source_type: str = ""
    extraction_quality: str = "missing"

    @property
    def text_sha256(self) -> str:
        return text_sha(self.text)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["text_sha256"] = self.text_sha256
        return out

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentRecord":
        data = dict(payload)
        data.pop("text_sha256", None)
        return cls(**data)


@dataclass
class CandidateRecord:
    run_id: str
    source_id: str
    source_url: str
    title: str
    candidate_score: float
    candidate_tier: str
    evidence_snippets: str
    matched_signals: str
    text_sha256: str
    review_decision: str = ""
    review_notes: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_score"] = round(self.candidate_score, 6)
        return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out
