"""LLM-assisted single-document NER extraction."""

from __future__ import annotations

import json
import time

from flask import Blueprint, jsonify

from pipeline.config import (
    AGENTS_OUTPUT_DIR,
    ANTHROPIC_MODEL_BULK,
    ANTHROPIC_RATE_DELAY_SECONDS,
    FULLTEXT_DIR,
    MEMORY_DIR,
)
from pipeline.agents.models_agent import CommunityMemory, CommunityRecord
from pipeline.agents.ner_agent import process_document

bp = Blueprint("auto_extract", __name__)

_last_extract_time: float = 0.0


def _load_communities() -> list[dict]:
    path = AGENTS_OUTPUT_DIR / "communities.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _find_community_for_doc(agora_id: str) -> dict | None:
    for c in _load_communities():
        if agora_id in c.get("member_agora_ids", []):
            return c
    return None


def _load_or_create_memory(community: dict) -> CommunityMemory:
    cid = community.get("community_id", "unknown")
    mem_path = MEMORY_DIR / f"{cid}_memory.json"
    if mem_path.exists():
        data = json.loads(mem_path.read_text(encoding="utf-8"))
        return CommunityMemory.from_dict(data)
    return CommunityMemory(
        community_id=cid,
        label=community.get("label", ""),
        taxonomy_signature=community.get("taxonomy_signature", []),
    )


@bp.route("/api/extract/<agora_id>", methods=["POST"])
def api_extract(agora_id: str):
    global _last_extract_time

    # Rate limit check
    elapsed = time.time() - _last_extract_time
    if elapsed < ANTHROPIC_RATE_DELAY_SECONDS:
        wait = ANTHROPIC_RATE_DELAY_SECONDS - elapsed
        return jsonify({"error": f"Rate limited. Wait {wait:.1f}s."}), 429

    # Load fulltext
    path = FULLTEXT_DIR / f"{agora_id}.txt"
    if not path.exists():
        return jsonify({"error": "Document not found"}), 404
    fulltext = path.read_text(encoding="utf-8", errors="replace")

    # Load community memory
    community = _find_community_for_doc(agora_id)
    if community:
        memory = _load_or_create_memory(community)
        official_name = community.get("label", agora_id)
        short_summary = ", ".join(community.get("taxonomy_signature", [])[:3])
    else:
        memory = CommunityMemory(community_id="unknown")
        official_name = agora_id
        short_summary = ""

    _last_extract_time = time.time()

    try:
        record = process_document(
            agora_id=agora_id,
            official_name=official_name,
            short_summary=short_summary,
            fulltext=fulltext,
            memory=memory,
            model=ANTHROPIC_MODEL_BULK,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if record is None:
        return jsonify({"error": "NER extraction returned no results"}), 500

    return jsonify(record.to_dict())


@bp.route("/api/extract/status")
def api_extract_status():
    elapsed = time.time() - _last_extract_time
    remaining = max(0.0, ANTHROPIC_RATE_DELAY_SECONDS - elapsed)
    return jsonify({
        "ready": remaining <= 0,
        "wait_seconds": round(remaining, 1),
    })
