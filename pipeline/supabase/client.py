"""Shared Supabase client and typed fetch helpers.

Usage:
    from pipeline.supabase.client import supabase_enabled, get_client
    from pipeline.supabase.client import fetch_documents, fetch_fulltext
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from ..config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET_FULLTEXTS

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guard + client
# ---------------------------------------------------------------------------

def supabase_enabled() -> bool:
    """True when SUPABASE_URL and SUPABASE_KEY are both set in the environment."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


@lru_cache(maxsize=1)
def get_client():
    """Return a cached Supabase client. Raises if env vars are missing."""
    from supabase import create_client
    if not supabase_enabled():
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Paginated SELECT helper
# ---------------------------------------------------------------------------

_PAGE_SIZE = 1000


def _select_all(table: str, columns: str = "*", filters: dict | None = None) -> list[dict]:
    """Fetch all rows from a table using keyset pagination."""
    client = get_client()
    rows: list[dict] = []
    offset = 0
    while True:
        q = client.table(table).select(columns).range(offset, offset + _PAGE_SIZE - 1)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        resp = q.execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


# ---------------------------------------------------------------------------
# Typed fetch helpers
# ---------------------------------------------------------------------------

def fetch_authorities() -> list[dict[str, Any]]:
    """Fetch all rows from the authorities table."""
    return _select_all("authorities")


def fetch_collections() -> list[dict[str, Any]]:
    """Fetch all rows from the collections table."""
    return _select_all("collections")


def fetch_documents() -> list[dict[str, Any]]:
    """Fetch all rows from agora_documents."""
    return _select_all("agora_documents")


def fetch_segments(doc_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Fetch segments, optionally filtered to a set of document IDs.

    For large doc_id sets, fetches in batches to stay under URL length limits.
    """
    client = get_client()
    if doc_ids is None:
        return _select_all("segments")

    rows: list[dict] = []
    batch_size = 200
    for i in range(0, len(doc_ids), batch_size):
        chunk = doc_ids[i : i + batch_size]
        offset = 0
        while True:
            resp = (
                client.table("segments")
                .select("*")
                .in_("document_id", chunk)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
            batch = resp.data or []
            rows.extend(batch) # type: ignore
            if len(batch) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    return rows


def fetch_fulltext(agora_id: str | int) -> str | None:
    """Download fulltext from Supabase Storage.

    Returns the text content, or None if not found / Storage unavailable.
    Path convention: agora/{agora_id}.txt
    """
    try:
        client = get_client()
        path = f"agora/{agora_id}.txt"
        resp = client.storage.from_(SUPABASE_BUCKET_FULLTEXTS).download(path)
        if resp:
            return resp.decode("utf-8", errors="replace")
    except Exception as exc:
        log.debug("fetch_fulltext(%s) failed: %s", agora_id, exc)
    return None


# ---------------------------------------------------------------------------
# Taxonomy reconstruction helper
# ---------------------------------------------------------------------------

def expand_taxonomy_tags(row: dict[str, Any]) -> dict[str, Any]:
    """Add boolean-style taxonomy keys to a Supabase agora_documents row.

    Supabase stores taxonomy as TEXT[] in `taxonomy_tags`.
    community_detector expects flat keys like {"Strategies: Evaluation": "True"}.
    This mutates and returns the row.
    """
    for tag in row.get("taxonomy_tags") or []:
        row[tag] = "True"
    return row
