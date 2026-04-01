"""Entity dictionary CRUD and export."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, render_template, request

from pipeline.config import AGENTS_OUTPUT_DIR, ENTITY_DICTIONARY_PATH
from pipeline.models import read_jsonl, utc_now_iso

bp = Blueprint("dictionary", __name__)


def _load_dictionary() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    if ENTITY_DICTIONARY_PATH.exists():
        for row in read_jsonl(ENTITY_DICTIONARY_PATH):
            entries[row["entity_id"]] = row
    return entries


def _save_dictionary(entries: dict[str, dict]) -> None:
    ENTITY_DICTIONARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ENTITY_DICTIONARY_PATH.open("w", encoding="utf-8") as fh:
        for entry in entries.values():
            fh.write(json.dumps(entry, ensure_ascii=True) + "\n")


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@bp.route("/dictionary")
def dictionary_page():
    return render_template("dictionary.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@bp.route("/api/dictionary")
def api_list():
    entries = _load_dictionary()
    type_filter = request.args.get("type", "").strip()
    search = request.args.get("search", "").strip().lower()

    results = []
    for entry in entries.values():
        if type_filter and entry.get("entity_type") != type_filter:
            continue
        if search:
            searchable = (
                entry.get("canonical_name", "").lower()
                + " " + entry.get("acronym", "").lower()
                + " " + " ".join(entry.get("aliases", []))
                + " " + " ".join(entry.get("soft_aliases", []))
            ).lower()
            if search not in searchable:
                continue
        results.append(entry)

    results.sort(key=lambda e: e.get("mention_count", 0), reverse=True)
    return jsonify(results)


@bp.route("/api/dictionary/<path:entity_id>")
def api_get(entity_id: str):
    entries = _load_dictionary()
    entry = entries.get(entity_id)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@bp.route("/api/dictionary", methods=["POST"])
def api_upsert():
    data = request.get_json()
    if not data or "entity_id" not in data:
        return jsonify({"error": "entity_id required"}), 400

    entries = _load_dictionary()
    eid = data["entity_id"]
    now = utc_now_iso()

    if eid in entries:
        entries[eid].update(data)
        entries[eid]["updated_at"] = now
    else:
        data.setdefault("created_at", now)
        data["updated_at"] = now
        entries[eid] = data

    _save_dictionary(entries)
    return jsonify({"status": "saved", "entity_id": eid})


@bp.route("/api/dictionary/<path:entity_id>", methods=["DELETE"])
def api_delete(entity_id: str):
    entries = _load_dictionary()
    if entity_id not in entries:
        return jsonify({"error": "Not found"}), 404
    del entries[entity_id]
    _save_dictionary(entries)
    return jsonify({"status": "deleted"})


@bp.route("/api/dictionary/merge", methods=["POST"])
def api_merge():
    data = request.get_json()
    keep_id = data.get("keep_id", "")
    merge_id = data.get("merge_id", "")
    if not keep_id or not merge_id:
        return jsonify({"error": "keep_id and merge_id required"}), 400

    entries = _load_dictionary()
    if keep_id not in entries or merge_id not in entries:
        return jsonify({"error": "One or both entries not found"}), 404

    keep = entries[keep_id]
    merge = entries[merge_id]

    # Merge aliases
    all_aliases = set(keep.get("aliases", []))
    all_aliases.add(merge.get("canonical_name", ""))
    all_aliases.update(merge.get("aliases", []))
    all_aliases.discard(keep.get("canonical_name", ""))
    keep["aliases"] = sorted(all_aliases)

    # Merge seen_in
    seen = set(keep.get("seen_in", []))
    seen.update(merge.get("seen_in", []))
    keep["seen_in"] = sorted(seen)

    # Sum mentions
    keep["mention_count"] = keep.get("mention_count", 0) + merge.get("mention_count", 0)
    keep["updated_at"] = utc_now_iso()

    del entries[merge_id]
    _save_dictionary(entries)
    return jsonify({"status": "merged", "kept": keep_id, "removed": merge_id})


@bp.route("/api/dictionary/export")
def api_export():
    entries = _load_dictionary()
    canonical_map: dict[str, str] = {}
    for entry in entries.values():
        eid = entry["entity_id"]
        canonical_map[entry.get("canonical_name", "").lower().strip()] = eid
        for alias in entry.get("aliases", []):
            canonical_map[alias.lower().strip()] = eid
        acronym = entry.get("acronym", "").strip()
        if acronym:
            canonical_map[acronym.lower()] = eid

    out_path = AGENTS_OUTPUT_DIR / "canonical_entity_map.json"
    out_path.write_text(
        json.dumps(canonical_map, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return jsonify({
        "status": "exported",
        "path": str(out_path),
        "entries": len(canonical_map),
    })
