from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import log, sqrt
from pathlib import Path
from typing import Iterable
import json
import re

from .models import normalize_space, read_jsonl, text_sha
from .ranker import RankConfig, evidence_snippets, keyword_signal, tier_from_score


TOKEN_RE = re.compile(r"[a-z][a-z0-9_\-]{2,}")


@dataclass
class DocxRecord:
    doc_id: str
    source_path: str
    title: str
    text: str
    text_sha256: str


@dataclass
class DocxMatchResult:
    doc_id: str
    source_path: str
    text_sha256: str
    semantic_score: float
    keyword_score: float
    candidate_score: float
    candidate_tier: str
    matched_signals: str
    evidence_snippets: str
    top_profile_matches: list[dict[str, float | str]]


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def load_positive_profile(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found: {path}")
    rows = read_jsonl(path)
    out = []
    for row in rows:
        agora_id = str(row.get("agora_id") or "").strip()
        profile_text = str(row.get("profile_text") or "").strip()
        if agora_id and profile_text:
            out.append({"agora_id": agora_id, "profile_text": profile_text})
    if not out:
        raise ValueError(f"No usable profile rows with agora_id/profile_text found in: {path}")
    return out


def extract_docx_text(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "python-docx is required for .docx extraction. Install with: "
            "python3 -m pip install --no-index --find-links ./wheelhouse python-docx"
        ) from exc

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if (p.text or "").strip()]
    return normalize_space("\n".join(parts))


def build_docx_records(input_paths: list[Path]) -> tuple[list[DocxRecord], list[dict[str, str]]]:
    records: list[DocxRecord] = []
    skipped: list[dict[str, str]] = []
    for p in input_paths:
        try:
            text = _extract_supported_text(p)
        except Exception as exc:
            skipped.append({"source_path": str(p), "reason": f"parse_error:{type(exc).__name__}"})
            continue
        if not text:
            skipped.append({"source_path": str(p), "reason": "empty_text"})
            continue
        records.append(
            DocxRecord(
                doc_id=p.stem,
                source_path=str(p),
                title=p.stem,
                text=text,
                text_sha256=text_sha(text),
            )
        )
    return records, skipped


def _extract_supported_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".txt":
        return normalize_space(path.read_text(encoding="utf-8", errors="ignore"))
    raise ValueError(f"Unsupported file extension: {suffix}")


@dataclass
class SparseTfidf:
    idf: dict[str, float]
    doc_vecs: list[dict[str, float]]
    doc_norms: list[float]


def fit_profile_vectorizer(profile_texts: Iterable[str], max_features: int = 50000) -> SparseTfidf:
    docs: list[list[str]] = []
    df = Counter()
    for text in profile_texts:
        toks = _tokenize(text)
        if not toks:
            continue
        docs.append(toks)
        df.update(set(toks))
    if not docs:
        return SparseTfidf({}, [], [])

    vocab = {t for t, _ in df.most_common(max_features)}
    n_docs = len(docs)
    idf = {t: log((n_docs + 1) / (df[t] + 1)) + 1.0 for t in vocab}

    doc_vecs: list[dict[str, float]] = []
    doc_norms: list[float] = []
    for toks in docs:
        tf = Counter(t for t in toks if t in vocab)
        vec = {t: c * idf[t] for t, c in tf.items()}
        norm = sqrt(sum(v * v for v in vec.values())) or 1.0
        doc_vecs.append(vec)
        doc_norms.append(norm)
    return SparseTfidf(idf=idf, doc_vecs=doc_vecs, doc_norms=doc_norms)


def _query_vec(text: str, idf: dict[str, float]) -> tuple[dict[str, float], float]:
    tf = Counter(t for t in _tokenize(text) if t in idf)
    if not tf:
        return {}, 1.0
    vec = {t: c * idf[t] for t, c in tf.items()}
    norm = sqrt(sum(v * v for v in vec.values())) or 1.0
    return vec, norm


def score_docx_against_profile(
    doc_text: str,
    profile_rows: list[dict],
    vectorizer: SparseTfidf,
    max_profile_matches: int = 5,
) -> tuple[float, list[dict[str, float | str]]]:
    if not vectorizer.idf or not vectorizer.doc_vecs:
        return 0.0, []

    qvec, qnorm = _query_vec(doc_text, vectorizer.idf)
    if not qvec:
        return 0.0, []

    scored: list[tuple[int, float]] = []
    for i, (dvec, dnorm) in enumerate(zip(vectorizer.doc_vecs, vectorizer.doc_norms)):
        dot = sum(qv * dvec.get(tok, 0.0) for tok, qv in qvec.items())
        sim = dot / (qnorm * dnorm)
        scored.append((i, max(0.0, min(1.0, sim))))
    scored.sort(key=lambda x: x[1], reverse=True)

    top = [
        {"agora_id": profile_rows[idx]["agora_id"], "similarity": round(score, 6)}
        for idx, score in scored[:max_profile_matches]
    ]
    return (top[0]["similarity"] if top else 0.0), top


def hybrid_score(doc_text: str, title: str, semantic_score: float, cfg: RankConfig) -> tuple[float, float, list[str]]:
    del title, cfg
    keyword_score, keyword_hits = keyword_signal(doc_text)
    score = (0.70 * semantic_score) + (0.30 * keyword_score)
    return max(0.0, min(1.0, score)), keyword_score, keyword_hits


def _score_distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0}
    return {
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(sum(values) / len(values), 6),
    }


def run_docx_match(
    docx_dir: Path,
    profile_jsonl: Path,
    out_json: Path,
    top_k: int,
    cfg: RankConfig,
    max_profile_matches: int,
) -> dict:
    if not docx_dir.exists() or not docx_dir.is_dir():
        raise FileNotFoundError(f"docx directory not found: {docx_dir}")

    input_paths = sorted(
        [p for p in docx_dir.iterdir() if p.is_file() and p.suffix.lower() in {".docx", ".txt"}]
    )
    if not input_paths:
        raise ValueError(f"No supported files (.docx/.txt) found in directory: {docx_dir}")

    profile_rows = load_positive_profile(profile_jsonl)
    vectorizer = fit_profile_vectorizer([r["profile_text"] for r in profile_rows])

    records, skipped = build_docx_records(input_paths)
    results: list[DocxMatchResult] = []
    for rec in records:
        semantic_score, top_matches = score_docx_against_profile(rec.text, profile_rows, vectorizer, max_profile_matches)
        candidate_score, keyword_score, keyword_hits = hybrid_score(rec.text, rec.title, semantic_score, cfg)
        if candidate_score < cfg.min_score_for_export:
            continue
        results.append(
            DocxMatchResult(
                doc_id=rec.doc_id,
                source_path=rec.source_path,
                text_sha256=rec.text_sha256,
                semantic_score=round(float(semantic_score), 6),
                keyword_score=round(float(keyword_score), 6),
                candidate_score=round(float(candidate_score), 6),
                candidate_tier=tier_from_score(candidate_score, cfg),
                matched_signals=";".join(keyword_hits[:16]),
                evidence_snippets=evidence_snippets(rec.text, keyword_hits),
                top_profile_matches=top_matches,
            )
        )

    results.sort(key=lambda r: r.candidate_score, reverse=True)
    if top_k > 0:
        results = results[:top_k]

    out_json.parent.mkdir(parents=True, exist_ok=True)
    profile_bytes = profile_jsonl.read_bytes()
    payload = {
        "run_type": "docx_match",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "params": {
            "docx_dir": str(docx_dir),
            "supported_extensions": [".docx", ".txt"],
            "profile_jsonl": str(profile_jsonl),
            "top_k": top_k,
            "min_score": cfg.min_score_for_export,
            "high_threshold": cfg.high_threshold,
            "medium_threshold": cfg.medium_threshold,
            "max_profile_matches": max_profile_matches,
            "hybrid_weights": {"semantic": 0.70, "keyword": 0.30},
        },
        "profile": {
            "path": str(profile_jsonl),
            "row_count": len(profile_rows),
            "sha256": sha256(profile_bytes).hexdigest(),
        },
        "summary": {
            "docs_discovered": len(input_paths),
            "docs_parsed": len(records),
            "docs_ranked": len(results),
            "docs_skipped": len(skipped),
            "tier_counts": dict(Counter(r.candidate_tier for r in results)),
            "candidate_score_distribution": _score_distribution([r.candidate_score for r in results]),
        },
        "results": [asdict(r) for r in results],
        "skipped": skipped,
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload
