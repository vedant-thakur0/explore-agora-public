"""Manual annotation save/load routes."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from pipeline.config import AGENTS_OUTPUT_DIR, ENTITY_DICTIONARY_PATH, MANUAL_ANNOTATIONS_DIR
from pipeline.models import read_jsonl, utc_now_iso

bp = Blueprint("annotation", __name__)


def _slugify(name: str) -> str:
    slug = []
    for ch in name.lower().strip():
        if ch.isalnum():
            slug.append(ch)
        elif ch in (" ", "-", "_"):
            slug.append("_")
    return "_".join(part for part in "".join(slug).split("_") if part)


def _entity_id(entity_type: str, name: str) -> str:
    PREFIX = {
        "organizations": "org",
        "offices": "office",
        "roles": "role",
        "legislation_refs": "legislation",
        "named_docs": "named_doc",
    }
    prefix = PREFIX.get(entity_type, entity_type)
    return f"{prefix}:{_slugify(name)}"


def _name_field(entity_type: str) -> str:
    return "title" if entity_type == "roles" else "name"


# ---------------------------------------------------------------------------
# Dictionary upsert helper
# ---------------------------------------------------------------------------

def _upsert_dictionary(entities_by_type: dict, agora_id: str) -> None:
    """Update entity dictionary from a saved annotation."""
    # Load existing dictionary
    existing: dict[str, dict] = {}
    if ENTITY_DICTIONARY_PATH.exists():
        for row in read_jsonl(ENTITY_DICTIONARY_PATH):
            existing[row["entity_id"]] = row

    now = utc_now_iso()
    for entity_type, entities in entities_by_type.items():
        if entity_type not in ("organizations", "offices", "roles", "legislation_refs", "named_docs"):
            continue
        nf = _name_field(entity_type)
        for ent in entities:
            name = ent.get(nf, "").strip()
            if not name:
                continue
            eid = _entity_id(entity_type, name)
            if eid in existing:
                entry = existing[eid]
                entry["mention_count"] = entry.get("mention_count", 0) + 1
                if agora_id not in entry.get("seen_in", []):
                    entry.setdefault("seen_in", []).append(agora_id)
                entry["updated_at"] = now
                # Add alias if different from canonical
                if name not in entry.get("aliases", []) and name != entry.get("canonical_name"):
                    entry.setdefault("aliases", []).append(name)
            else:
                existing[eid] = {
                    "entity_id": eid,
                    "entity_type": entity_type,
                    "canonical_name": name,
                    "acronym": ent.get("acronym", ""),
                    "aliases": [],
                    "soft_aliases": [],
                    "metadata": {
                        k: ent.get(k, "")
                        for k in ("parent_org", "doc_type", "owner_org", "citation", "ref_type")
                    },
                    "mention_count": 1,
                    "seen_in": [agora_id],
                    "first_seen": agora_id,
                    "created_at": now,
                    "updated_at": now,
                }

    # Rewrite dictionary
    ENTITY_DICTIONARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ENTITY_DICTIONARY_PATH.open("w", encoding="utf-8") as fh:
        for entry in existing.values():
            fh.write(json.dumps(entry, ensure_ascii=True) + "\n")


# ---------------------------------------------------------------------------
# Upsert into entities.jsonl
# ---------------------------------------------------------------------------

def _upsert_entities_jsonl(agora_id: str, record: dict) -> None:
    """Replace or append this agora_id's entry in entities.jsonl."""
    path = AGENTS_OUTPUT_DIR / "entities.jsonl"
    rows = read_jsonl(path) if path.exists() else []
    rows = [r for r in rows if r.get("agora_id") != agora_id]
    rows.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@bp.route("/api/annotations/<agora_id>", methods=["GET"])
def api_get_annotation(agora_id: str):
    path = MANUAL_ANNOTATIONS_DIR / f"{agora_id}.json"
    if not path.exists():
        return jsonify(None)
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@bp.route("/api/annotations/<agora_id>", methods=["POST"])
def api_save_annotation(agora_id: str):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    now = utc_now_iso()
    record = {
        "agora_id": agora_id,
        "organizations": data.get("organizations", []),
        "offices": data.get("offices", []),
        "roles": data.get("roles", []),
        "legislation_refs": data.get("legislation_refs", []),
        "named_docs": data.get("named_docs", []),
        "relationships": data.get("relationships", []),
        "custom_relation_types": data.get("custom_relation_types", []),
        "soft_aliases": data.get("soft_aliases", []),
        "disambiguation_updates": data.get("disambiguation_updates", {}),
        "new_parsing_rule": data.get("new_parsing_rule"),
        "oddity": data.get("oddity"),
        "model": data.get("model", "manual"),
        "prompt_tokens": data.get("prompt_tokens", 0),
        "completion_tokens": data.get("completion_tokens", 0),
        "chunks_processed": data.get("chunks_processed", 0),
        "extracted_at": now,
        "source": "manual",
    }

    # 1. Save individual annotation file
    MANUAL_ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    ann_path = MANUAL_ANNOTATIONS_DIR / f"{agora_id}.json"
    ann_path.write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    # 2. Upsert into entities.jsonl
    _upsert_entities_jsonl(agora_id, record)

    # 3. Update entity dictionary
    _upsert_dictionary({
        "organizations": record["organizations"],
        "offices": record["offices"],
        "roles": record["roles"],
        "legislation_refs": record["legislation_refs"],
        "named_docs": record["named_docs"],
    }, agora_id)

    return jsonify({"status": "saved", "agora_id": agora_id})
