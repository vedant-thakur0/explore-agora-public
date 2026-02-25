from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log, sqrt
from pathlib import Path
from typing import Iterable
import csv
import re
import sys

from .config import KEYWORD_GROUPS, METADATA_PRIOR_TERMS
from .models import CandidateRecord, DocumentRecord

TOKEN_RE = re.compile(r"[a-z][a-z0-9_\-]{2,}")
TITLE_AI_RE = re.compile(r"\b(ai|artificial intelligence)\b")


@dataclass
class RankConfig:
    min_score_for_export: float = 0.35
    high_threshold: float = 0.7
    medium_threshold: float = 0.4


class TfidfCentroid:
    def __init__(self, idf: dict[str, float], centroid: dict[str, float]) -> None:
        self.idf = idf
        self.centroid = centroid

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall((text or "").lower())

    @classmethod
    def fit(cls, texts: Iterable[str], max_features: int = 40000) -> "TfidfCentroid":
        docs = []
        df = Counter()
        for text in texts:
            toks = cls.tokenize(text)
            if not toks:
                continue
            docs.append(toks)
            df.update(set(toks))

        if not docs:
            return cls({}, {})

        vocab = {t for t, _ in df.most_common(max_features)}
        n_docs = len(docs)
        idf = {t: log((n_docs + 1) / (df[t] + 1)) + 1.0 for t in vocab}

        centroid_raw: Counter[str] = Counter()
        for toks in docs:
            tf = Counter(t for t in toks if t in vocab)
            vec = {t: c * idf[t] for t, c in tf.items()}
            norm = sqrt(sum(v * v for v in vec.values())) or 1.0
            for t, v in vec.items():
                centroid_raw[t] += v / norm

        norm_c = sqrt(sum(v * v for v in centroid_raw.values())) or 1.0
        centroid = {t: v / norm_c for t, v in centroid_raw.items()}
        return cls(idf, centroid)

    def similarity(self, text: str) -> float:
        if not self.idf or not self.centroid:
            return 0.0
        tf = Counter(t for t in self.tokenize(text) if t in self.idf)
        if not tf:
            return 0.0
        vec = {t: c * self.idf[t] for t, c in tf.items()}
        norm = sqrt(sum(v * v for v in vec.values())) or 1.0
        return max(0.0, min(1.0, sum((v / norm) * self.centroid.get(t, 0.0) for t, v in vec.items())))


def load_reference_texts(path: Path) -> list[str]:
    csv.field_size_limit(sys.maxsize)
    texts: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            text = (row.get("Extracted full text") or "").strip()
            if text:
                texts.append(text)
    return texts


def keyword_signal(text: str) -> tuple[float, list[str]]:
    txt = (text or "").lower()
    total = 0.0
    hits: list[str] = []

    for group_name, group in KEYWORD_GROUPS.items():
        group_weight = float(group.get("group_weight", group.get("weight", 0.0)))
        min_hits_for_full_credit = float(group.get("min_hits_for_full_credit", 2.0))
        max_credit = float(group.get("max_credit", 1.0))

        positive_weight_hit = 0.0
        negative_weight_hit = 0.0
        matched_labels: list[str] = []

        for term_cfg in group.get("terms", []):
            if isinstance(term_cfg, str):
                term = term_cfg
                aliases: list[str] = []
                match_type = "phrase"
                term_weight = 1.0
                polarity = "positive"
            else:
                term = str(term_cfg.get("term", "")).strip().lower()
                aliases = [str(a).strip().lower() for a in term_cfg.get("aliases", []) if str(a).strip()]
                match_type = str(term_cfg.get("match_type", "phrase"))
                term_weight = float(term_cfg.get("weight", 1.0))
                polarity = str(term_cfg.get("polarity", "positive")).lower()

            if not term:
                continue
            patterns = [term] + aliases
            matched = any(_pattern_matches(txt, p, match_type) for p in patterns)
            if not matched:
                continue

            if polarity == "negative":
                negative_weight_hit += term_weight
                matched_labels.append(f"{group_name}:!{term}")
            else:
                positive_weight_hit += term_weight
                matched_labels.append(f"{group_name}:{term}")

        if positive_weight_hit > 0:
            positive_credit = min(max_credit, positive_weight_hit / max(1.0, min_hits_for_full_credit))
            total += group_weight * positive_credit
        if negative_weight_hit > 0:
            negative_credit = min(max_credit, negative_weight_hit / max(1.0, min_hits_for_full_credit))
            total -= group_weight * negative_credit
        hits.extend(matched_labels[:3])
    return max(0.0, min(1.0, total)), hits


def _pattern_matches(text: str, pattern: str, match_type: str) -> bool:
    p = pattern.strip().lower()
    if not p:
        return False
    if match_type == "regex":
        return re.search(p, text) is not None
    escaped = re.escape(p)
    if match_type == "token":
        return re.search(rf"\b{escaped}\b", text) is not None
    if match_type == "phrase":
        return re.search(rf"\b{escaped}\b", text) is not None
    return p in text


def metadata_prior(record: DocumentRecord) -> tuple[float, list[str]]:
    score = 0.0
    hits: list[str] = []
    joined_committees = " ".join(record.committees).lower()

    for term in METADATA_PRIOR_TERMS["committee"]:
        if term in joined_committees:
            score += 0.03
            hits.append(f"committee:{term}")

    if record.bill_type.lower() in METADATA_PRIOR_TERMS["bill_type"]:
        score += 0.02
        hits.append(f"bill_type:{record.bill_type.lower()}")

    title_l = record.title.lower()
    if TITLE_AI_RE.search(title_l):
        score += 0.06
        hits.append("title:ai")

    return min(0.2, score), hits


def evidence_snippets(text: str, terms: list[str], max_snippets: int = 3) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""

    plain_terms = [t.split(":", 1)[-1].lstrip("!") for t in terms][:10]
    snippets = []
    for line in lines:
        ll = line.lower()
        if any(term in ll for term in plain_terms):
            snippets.append(line[:260])
        if len(snippets) >= max_snippets:
            break

    if not snippets:
        snippets = lines[:max_snippets]
    return " || ".join(snippets)


def tier_from_score(score: float, cfg: RankConfig) -> str:
    if score >= cfg.high_threshold:
        return "high"
    if score >= cfg.medium_threshold:
        return "medium"
    return "low"


def ranking_text(record: DocumentRecord) -> str:
    title = (record.title or "").strip()
    body = (record.text or "").strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body


def rank_records(
    run_id: str,
    records: list[DocumentRecord],
    vectorizer: TfidfCentroid,
    cfg: RankConfig,
) -> list[CandidateRecord]:
    out: list[CandidateRecord] = []
    for rec in records:
        combined_text = ranking_text(rec)
        kw_score, kw_hits = keyword_signal(combined_text)
        sim_score = vectorizer.similarity(combined_text)
        meta_score, meta_hits = metadata_prior(rec)

        score = (0.5 * kw_score) + (0.4 * sim_score) + (0.1 * min(1.0, meta_score / 0.2))
        score = max(0.0, min(1.0, score))
        tier = tier_from_score(score, cfg)
        hits = kw_hits + meta_hits + ([f"semantic:{round(sim_score, 3)}"] if sim_score > 0 else [])

        out.append(
            CandidateRecord(
                run_id=run_id,
                source_id=rec.source_id,
                source_url=rec.source_url,
                title=rec.title,
                candidate_score=score,
                candidate_tier=tier,
                evidence_snippets=evidence_snippets(combined_text, hits),
                matched_signals=";".join(hits[:16]),
                text_sha256=rec.text_sha256,
            )
        )

    out.sort(key=lambda c: c.candidate_score, reverse=True)
    return [c for c in out if c.candidate_score >= cfg.min_score_for_export]
