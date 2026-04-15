"""Document listing and fulltext API."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from pipeline.config import AGENTS_OUTPUT_DIR, DOCUMENTS_CSV_PATH, FULLTEXT_DIR, MANUAL_ANNOTATIONS_DIR
from pipeline.models import read_jsonl

bp = Blueprint("documents", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_communities_cache: list[dict] | None = None
_doc_metadata_cache: dict[str, dict] | None = None


def _load_communities() -> list[dict]:
    global _communities_cache
    if _communities_cache is None:
        path = AGENTS_OUTPUT_DIR / "communities.json"
        if path.exists():
            _communities_cache = json.loads(path.read_text(encoding="utf-8"))
        else:
            _communities_cache = []
    return _communities_cache


def _load_doc_metadata() -> dict[str, dict]:
    """Load document metadata keyed by AGORA ID.

    Fetches from Supabase when enabled, falls back to local CSV.
    """
    global _doc_metadata_cache
    if _doc_metadata_cache is not None:
        return _doc_metadata_cache
    _doc_metadata_cache = {}

    from pipeline.supabase.client import supabase_enabled, fetch_documents
    if supabase_enabled():
        for row in fetch_documents():
            aid = str(row.get("agora_id") or "").strip()
            if not aid:
                continue
            _doc_metadata_cache[aid] = {
                "title": row.get("official_name") or "",
                "casual_name": row.get("casual_name") or "",
                "short_summary": row.get("short_summary") or "",
                "activity": row.get("most_recent_activity") or "",
                "activity_date": row.get("most_recent_activity_date") or "",
                "proposed_date": row.get("proposed_date") or "",
                "congress_url": row.get("link_to_document") or "",
            }
        return _doc_metadata_cache

    if not DOCUMENTS_CSV_PATH.exists():
        return _doc_metadata_cache
    with DOCUMENTS_CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aid = row.get("AGORA ID", "").strip()
            if not aid:
                continue
            _doc_metadata_cache[aid] = {
                "title": row.get("Official name", "").strip(),
                "casual_name": row.get("Casual name", "").strip(),
                "short_summary": row.get("Short summary", "").strip(),
                "activity": row.get("Most recent activity", "").strip(),
                "activity_date": row.get("Most recent activity date", "").strip(),
                "proposed_date": row.get("Proposed date", "").strip(),
                "congress_url": row.get("Link to document", "").strip(),
            }
    return _doc_metadata_cache


def _get_doc_meta(agora_id: str) -> dict:
    """Return metadata dict for a given agora_id (empty dict if not found)."""
    return _load_doc_metadata().get(agora_id, {})


def _build_doc_community_map() -> dict[str, dict]:
    """Map agora_id -> {community_id, label}."""
    mapping: dict[str, dict] = {}
    for c in _load_communities():
        cid = c.get("community_id", "")
        label = c.get("label", "")
        for aid in c.get("member_agora_ids", []):
            mapping[aid] = {"community_id": cid, "community_label": label}
    return mapping


def _annotation_status(agora_id: str) -> str:
    """Return 'reviewed', 'auto', or 'none'."""
    manual_path = MANUAL_ANNOTATIONS_DIR / f"{agora_id}.json"
    if manual_path.exists():
        return "reviewed"
    entities = read_jsonl(AGENTS_OUTPUT_DIR / "entities.jsonl")
    for e in entities:
        if e.get("agora_id") == agora_id:
            return "auto"
    return "none"


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@bp.route("/documents")
def document_list():
    return render_template("document_list.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@bp.route("/api/documents")
def api_documents():
    community_filter = request.args.get("community", "").strip()
    search = request.args.get("search", "").strip().lower()
    status_filter = request.args.get("status", "").strip()

    doc_community = _build_doc_community_map()

    from pipeline.supabase.client import supabase_enabled
    if supabase_enabled():
        # Build doc list from metadata cache (already fetched from Supabase)
        all_meta = _load_doc_metadata()
        agora_ids = sorted(all_meta.keys())

    # Fall back to local fulltext files if Supabase is disabled or returned nothing
    if not supabase_enabled() or not agora_ids:
        if not FULLTEXT_DIR.exists():
            return jsonify([])
        agora_ids = [f.stem for f in sorted(FULLTEXT_DIR.iterdir()) if f.suffix == ".txt"]

    docs = []
    for agora_id in agora_ids:
        info = doc_community.get(agora_id, {})
        cid = info.get("community_id", "")
        clabel = info.get("community_label", "")

        if community_filter and cid != community_filter:
            continue

        status = _annotation_status(agora_id)
        if status_filter and status != status_filter:
            continue

        meta = _get_doc_meta(agora_id)
        title = meta.get("title", "")

        if search and search not in agora_id.lower() and search not in clabel.lower() and search not in title.lower():
            continue

        docs.append({
            "agora_id": agora_id,
            "title": title,
            "casual_name": meta.get("casual_name", ""),
            "community_id": cid,
            "community_label": clabel,
            "status": status,
        })

    return jsonify(docs)


@bp.route("/api/documents/<agora_id>")
def api_document_detail(agora_id: str):
    from pipeline.supabase.client import supabase_enabled, fetch_fulltext as sb_fetch_fulltext

    fulltext: str | None = None

    # Try Supabase Storage first
    if supabase_enabled():
        fulltext = sb_fetch_fulltext(agora_id)

    # Fall back to local file
    if fulltext is None:
        path = FULLTEXT_DIR / f"{agora_id}.txt"
        if path.exists():
            fulltext = path.read_text(encoding="utf-8", errors="replace")

    if fulltext is None:
        return jsonify({"error": "Document not found"}), 404

    doc_community = _build_doc_community_map()
    info = doc_community.get(agora_id, {})
    meta = _get_doc_meta(agora_id)

    return jsonify({
        "agora_id": agora_id,
        "fulltext": fulltext,
        "community_id": info.get("community_id", ""),
        "community_label": info.get("community_label", ""),
        "status": _annotation_status(agora_id),
        **meta,
    })


@bp.route("/api/documents/<agora_id>/entities")
def api_document_entities(agora_id: str):
    entities = read_jsonl(AGENTS_OUTPUT_DIR / "entities.jsonl")
    for e in entities:
        if e.get("agora_id") == agora_id:
            return jsonify(e)
    return jsonify(None)
