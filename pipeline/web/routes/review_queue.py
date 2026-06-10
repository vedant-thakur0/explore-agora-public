"""Review queue triage — accept/dismiss bare-alias entities flagged by canonicalize."""

from __future__ import annotations

import json
import os
import tempfile

from flask import Blueprint, jsonify, render_template, request

from pipeline.config import AGENTS_OUTPUT_DIR, REVIEW_QUEUE_PATH
from pipeline.models import read_jsonl, utc_now_iso

bp = Blueprint("review_queue", __name__)

# Entity name field per type (mirrors canonicalize.py)
NAME_FIELD: dict[str, str] = {
    "organizations": "name",
    "offices": "name",
    "roles": "title",
    "legislation_refs": "name",
    "named_docs": "name",
}

ENTITIES_PATH = AGENTS_OUTPUT_DIR / "entities.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_review_queue() -> list[dict]:
    return read_jsonl(REVIEW_QUEUE_PATH)


def _save_review_queue(entries: list[dict]) -> None:
    REVIEW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=REVIEW_QUEUE_PATH.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
        os.replace(tmp_path, REVIEW_QUEUE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _apply_canonical(
    agora_id: str,
    entity_name: str,
    entity_type: str,
    canonical_name: str,
) -> bool:
    """Update entity name in entities.jsonl. Returns True if entity found and updated."""
    if not ENTITIES_PATH.exists():
        return False

    rows = read_jsonl(ENTITIES_PATH)
    field = NAME_FIELD.get(entity_type, "name")
    updated = False

    for row in rows:
        if str(row.get("agora_id", "")) != str(agora_id):
            continue
        entities = row.get("entities", {})
        type_list = entities.get(entity_type, [])
        for entity in type_list:
            if entity.get(field, "") == entity_name:
                entity["_canonicalized_from"] = entity_name
                entity[field] = canonical_name
                updated = True

    if not updated:
        return False

    # Atomic rewrite
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=ENTITIES_PATH.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        os.replace(tmp_path, ENTITIES_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return True


def _remove_from_queue(
    queue: list[dict],
    agora_id: str,
    entity_name: str,
    entity_type: str,
) -> list[dict]:
    """Return new list with the matching entry removed."""
    return [
        e for e in queue
        if not (
            str(e.get("agora_id", "")) == str(agora_id)
            and e.get("entity_name", "") == entity_name
            and e.get("entity_type", "") == entity_type
        )
    ]


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@bp.route("/review")
def review_page():
    return render_template("review_queue.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@bp.route("/api/review")
def api_list():
    queue = _load_review_queue()
    type_filter = request.args.get("type", "").strip()
    source_filter = request.args.get("source", "").strip()
    search = request.args.get("search", "").strip().lower()

    results = []
    for entry in queue:
        if type_filter and entry.get("entity_type") != type_filter:
            continue
        if source_filter and entry.get("suggestion_source") != source_filter:
            continue
        if search:
            searchable = (
                entry.get("entity_name", "").lower()
                + " " + entry.get("suggested_canonical", "").lower()
                + " " + entry.get("community_id", "").lower()
                + " " + entry.get("agora_id", "").lower()
            )
            if search not in searchable:
                continue
        results.append(entry)

    return jsonify(results)


@bp.route("/api/review/accept", methods=["POST"])
def api_accept():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    agora_id = str(data.get("agora_id", "")).strip()
    entity_name = data.get("entity_name", "").strip()
    entity_type = data.get("entity_type", "").strip()
    canonical_name = data.get("canonical_name", "").strip()

    if not all([agora_id, entity_name, entity_type, canonical_name]):
        return jsonify({"error": "agora_id, entity_name, entity_type, canonical_name required"}), 400

    _apply_canonical(agora_id, entity_name, entity_type, canonical_name)

    queue = _load_review_queue()
    queue = _remove_from_queue(queue, agora_id, entity_name, entity_type)
    _save_review_queue(queue)

    return jsonify({"status": "accepted", "canonical_name": canonical_name})


@bp.route("/api/review/dismiss", methods=["POST"])
def api_dismiss():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    agora_id = str(data.get("agora_id", "")).strip()
    entity_name = data.get("entity_name", "").strip()
    entity_type = data.get("entity_type", "").strip()

    if not all([agora_id, entity_name, entity_type]):
        return jsonify({"error": "agora_id, entity_name, entity_type required"}), 400

    queue = _load_review_queue()
    queue = _remove_from_queue(queue, agora_id, entity_name, entity_type)
    _save_review_queue(queue)

    return jsonify({"status": "dismissed"})


@bp.route("/api/review/bulk-accept", methods=["POST"])
def api_bulk_accept():
    data = request.get_json()
    if not data or "entries" not in data:
        return jsonify({"error": "entries array required"}), 400

    queue = _load_review_queue()
    accepted = 0
    errors = []

    for item in data["entries"]:
        agora_id = str(item.get("agora_id", "")).strip()
        entity_name = item.get("entity_name", "").strip()
        entity_type = item.get("entity_type", "").strip()
        canonical_name = item.get("canonical_name", "").strip()

        if not all([agora_id, entity_name, entity_type, canonical_name]):
            errors.append(f"Skipped incomplete entry: {item}")
            continue

        _apply_canonical(agora_id, entity_name, entity_type, canonical_name)
        queue = _remove_from_queue(queue, agora_id, entity_name, entity_type)
        accepted += 1

    _save_review_queue(queue)
    return jsonify({"status": "bulk-accepted", "accepted": accepted, "errors": errors})


@bp.route("/api/review/bulk-dismiss", methods=["POST"])
def api_bulk_dismiss():
    data = request.get_json()
    if not data or "entries" not in data:
        return jsonify({"error": "entries array required"}), 400

    queue = _load_review_queue()
    dismissed = 0

    for item in data["entries"]:
        agora_id = str(item.get("agora_id", "")).strip()
        entity_name = item.get("entity_name", "").strip()
        entity_type = item.get("entity_type", "").strip()

        if not all([agora_id, entity_name, entity_type]):
            continue

        queue = _remove_from_queue(queue, agora_id, entity_name, entity_type)
        dismissed += 1

    _save_review_queue(queue)
    return jsonify({"status": "bulk-dismissed", "dismissed": dismissed})
