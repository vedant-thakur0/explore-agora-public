"""NER Evaluation Framework.

Compares NER agent output (entities.jsonl) against manual annotations
(manual_annotations/*.json) to compute precision, recall, F1 per entity type,
type correctness, and span-level metrics.

CLI: python3 -m pipeline.cli eval-ner --gold-dir pipeline/agents/output/manual_annotations/
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config import AGENTS_OUTPUT_DIR, MANUAL_ANNOTATIONS_DIR
from pipeline.models import read_jsonl

log = logging.getLogger(__name__)

ENTITY_TYPES = ["organizations", "offices", "roles", "legislation_refs", "named_docs"]


@dataclass
class TypeMetrics:
    """Precision/Recall/F1 for a single entity type."""
    tp: int = 0
    fp: int = 0
    fn: int = 0
    partial_matches: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "partial_matches": self.partial_matches,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class DocEvalResult:
    """Evaluation result for a single document."""
    agora_id: str
    by_type: dict[str, TypeMetrics] = field(default_factory=dict)
    type_correct: int = 0
    type_total: int = 0

    @property
    def type_accuracy(self) -> float:
        return self.type_correct / self.type_total if self.type_total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agora_id": self.agora_id,
            "by_type": {et: m.to_dict() for et, m in self.by_type.items()},
            "type_accuracy": round(self.type_accuracy, 4),
        }


# ---------------------------------------------------------------------------
# Name normalization for matching
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Normalize entity name for matching: lowercase, strip punctuation."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _levenshtein_ratio(a: str, b: str) -> float:
    """Compute Levenshtein similarity ratio between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Simple DP implementation
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(dp[j], dp[j - 1], prev)
            prev = temp
    max_len = max(m, n)
    return 1.0 - dp[n] / max_len if max_len > 0 else 1.0


def _extract_names(entities: list[dict], entity_type: str) -> list[str]:
    """Extract normalized names from an entity list."""
    names = []
    for e in entities:
        if entity_type == "roles":
            name = e.get("title", "")
        else:
            name = e.get("name", "")
        if name:
            names.append(_normalize(name))
    return names


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate_document(
    predicted: dict[str, Any],
    gold: dict[str, Any],
    partial_threshold: float = 0.85,
) -> DocEvalResult:
    """Evaluate NER output for a single document against gold annotations."""
    agora_id = gold.get("agora_id", predicted.get("agora_id", "unknown"))
    result = DocEvalResult(agora_id=agora_id)

    for entity_type in ENTITY_TYPES:
        pred_names = _extract_names(predicted.get(entity_type, []), entity_type)
        gold_names = _extract_names(gold.get(entity_type, []), entity_type)

        metrics = TypeMetrics()
        matched_gold: set[int] = set()

        for pname in pred_names:
            found = False
            for gi, gname in enumerate(gold_names):
                if gi in matched_gold:
                    continue
                if pname == gname:
                    metrics.tp += 1
                    matched_gold.add(gi)
                    found = True
                    break
                elif _levenshtein_ratio(pname, gname) >= partial_threshold:
                    metrics.tp += 1
                    metrics.partial_matches += 1
                    matched_gold.add(gi)
                    found = True
                    break
            if not found:
                metrics.fp += 1

        metrics.fn = len(gold_names) - len(matched_gold)
        result.by_type[entity_type] = metrics

    # Type correctness: check if entities that exist in gold are typed correctly
    # Use the predicted entities and see if they match gold type
    for entity_type in ENTITY_TYPES:
        gold_names_set = set(_extract_names(gold.get(entity_type, []), entity_type))
        for et in ENTITY_TYPES:
            pred_names = _extract_names(predicted.get(et, []), et)
            for pname in pred_names:
                if pname in gold_names_set:
                    result.type_total += 1
                    if et == entity_type:
                        result.type_correct += 1

    return result


def evaluate(
    predicted_path: Path | None = None,
    gold_dir: Path | None = None,
    partial_threshold: float = 0.85,
) -> dict[str, Any]:
    """Evaluate NER output against all manual annotations.

    Returns aggregate metrics across all annotated documents.
    """
    predicted_path = predicted_path or (AGENTS_OUTPUT_DIR / "entities.jsonl")
    gold_dir = gold_dir or MANUAL_ANNOTATIONS_DIR

    if not gold_dir.exists():
        log.error("Gold annotations directory not found: %s", gold_dir)
        return {"error": "Gold directory not found"}

    # Load gold annotations
    gold_ids: dict[str, dict] = {}
    for ann_file in sorted(gold_dir.glob("*.json")):
        try:
            ann = json.loads(ann_file.read_text(encoding="utf-8"))
            aid = ann.get("agora_id", ann_file.stem)
            gold_ids[str(aid)] = ann
        except (json.JSONDecodeError, OSError):
            continue

    if not gold_ids:
        log.warning("No gold annotations found in %s", gold_dir)
        return {"error": "No gold annotations found"}

    # Load predictions
    predicted: dict[str, dict] = {}
    if predicted_path.exists():
        for row in read_jsonl(predicted_path):
            aid = str(row.get("agora_id", ""))
            if aid in gold_ids:
                predicted[aid] = row

    # Evaluate each document
    doc_results: list[DocEvalResult] = []
    for aid, gold in gold_ids.items():
        pred = predicted.get(aid, {})
        result = evaluate_document(pred, gold, partial_threshold)
        doc_results.append(result)

    # Aggregate
    agg_by_type: dict[str, TypeMetrics] = {}
    total_type_correct = 0
    total_type_total = 0

    for result in doc_results:
        total_type_correct += result.type_correct
        total_type_total += result.type_total
        for et, metrics in result.by_type.items():
            if et not in agg_by_type:
                agg_by_type[et] = TypeMetrics()
            agg_by_type[et].tp += metrics.tp
            agg_by_type[et].fp += metrics.fp
            agg_by_type[et].fn += metrics.fn
            agg_by_type[et].partial_matches += metrics.partial_matches

    # Compute macro-averaged F1
    type_f1s = [m.f1 for m in agg_by_type.values() if (m.tp + m.fp + m.fn) > 0]
    macro_f1 = sum(type_f1s) / len(type_f1s) if type_f1s else 0.0

    report = {
        "docs_evaluated": len(doc_results),
        "docs_with_predictions": len(predicted),
        "macro_f1": round(macro_f1, 4),
        "type_accuracy": round(total_type_correct / total_type_total, 4) if total_type_total > 0 else 0.0,
        "by_type": {et: m.to_dict() for et, m in agg_by_type.items()},
        "per_document": [r.to_dict() for r in doc_results],
    }

    # Write report
    report_path = AGENTS_OUTPUT_DIR / "ner_eval_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    log.info("Eval report written to %s (macro F1: %.4f)", report_path, macro_f1)

    return report
