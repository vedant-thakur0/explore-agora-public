"""Sync NER entity dictionary and document-entity mappings to Supabase.

Usage:
    from pipeline.supabase.ner_sync import run as run_ner_sync
    run_ner_sync()
"""
from __future__ import annotations

import json
import logging
from itertools import islice
from pathlib import Path
from typing import Iterator, Any

from ..config import ENTITY_DICTIONARY_PATH, MANUAL_ANNOTATIONS_DIR, SUPABASE_BATCH_SIZE

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _batched(iterable, n: int) -> Iterator[list]:
    """Batch an iterable into chunks of size n."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def _get_supabase_client():
    """Get a Supabase client from environment."""
    import os
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise SystemExit(
            "ERROR: SUPABASE_URL and SUPABASE_KEY must be set in your .env file."
        )
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Load entity dictionary
# ---------------------------------------------------------------------------


def _load_entity_dictionary(path: Path) -> list[dict[str, Any]]:
    """Load entity_dictionary.jsonl and transform for ner_entities table."""
    rows = []
    if not path.exists():
        log.warning("Entity dictionary not found at %s", path)
        return rows

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entity = json.loads(line)
                rows.append({
                    "entity_id": entity.get("entity_id"),
                    "entity_type": entity.get("entity_type"),
                    "canonical_name": entity.get("canonical_name"),
                    "acronym": entity.get("acronym"),
                    "aliases": entity.get("aliases", []),
                    "soft_aliases": entity.get("soft_aliases", []),
                    "metadata": entity.get("metadata", {}),
                    "mention_count": entity.get("mention_count", 0),
                    "first_seen": entity.get("first_seen"),
                    "created_at": entity.get("created_at"),
                    "updated_at": entity.get("updated_at"),
                })
            except (json.JSONDecodeError, KeyError) as e:
                log.warning("Skipped malformed entity: %s", e)
    return rows


# ---------------------------------------------------------------------------
# Load document-entity mappings
# ---------------------------------------------------------------------------


def _load_doc_entities(annotations_dir: Path) -> list[dict[str, Any]]:
    """Load manual annotations and extract entity mentions per document."""
    rows = []
    if not annotations_dir.exists():
        log.warning("Annotations directory not found at %s", annotations_dir)
        return rows

    for json_file in sorted(annotations_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                annotation = json.load(f)

            agora_id = annotation.get("agora_id")
            if not agora_id:
                log.warning("No agora_id in %s", json_file.name)
                continue

            try:
                agora_id = int(agora_id)
            except (ValueError, TypeError):
                log.warning("Invalid agora_id in %s: %s", json_file.name, agora_id)
                continue

            # Extract entities by type and deduplicate by entity_type + name
            entity_mentions: dict[str, dict] = {}

            for entity_type in (
                "organizations",
                "offices",
                "roles",
                "legislation_refs",
                "named_docs",
            ):
                for entity in annotation.get(entity_type, []):
                    name = entity.get("name", "")
                    if not name:
                        continue

                    # Use (entity_type, name) as dedup key
                    key = (entity_type, name)
                    if key not in entity_mentions:
                        entity_mentions[key] = {
                            "agora_id": agora_id,
                            "entity_type": entity_type,
                            "name": name,
                            "char_positions": [],
                            "contexts": [],
                        }

                    # Collect char positions and contexts
                    if "char_start" in entity and "char_end" in entity:
                        entity_mentions[key]["char_positions"].append({
                            "start": entity["char_start"],
                            "end": entity["char_end"],
                        })
                    if "context" in entity:
                        entity_mentions[key]["contexts"].append(entity["context"])

            # Convert to rows: for each (entity_type, name), find canonical entity_id
            for (entity_type, name), mention in entity_mentions.items():
                # Entity ID is derived from the entity dictionary
                # For now, we store the name; actual lookup happens during upsert
                rows.append({
                    "agora_id": mention["agora_id"],
                    "entity_type": mention["entity_type"],
                    "entity_name": mention["name"],  # Will be mapped to entity_id later
                    "mention_count": len(mention["char_positions"]),
                    "char_positions": mention["char_positions"],
                    "contexts": mention["contexts"],
                })

        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Skipped malformed annotation %s: %s", json_file.name, e)

    return rows


# ---------------------------------------------------------------------------
# Name → entity_id lookup
# ---------------------------------------------------------------------------


def _build_entity_lookup(
    entity_rows: list[dict],
) -> dict[tuple[str, str], str]:
    """Build a lookup map from (entity_type, canonical_name) → entity_id."""
    lookup = {}
    for entity in entity_rows:
        key = (entity["entity_type"], entity["canonical_name"])
        lookup[key] = entity["entity_id"]
    return lookup


def _resolve_doc_entity_ids(
    doc_entity_rows: list[dict],
    entity_lookup: dict[tuple[str, str], str],
) -> list[dict]:
    """Resolve entity names to entity_ids using lookup."""
    resolved = []
    for row in doc_entity_rows:
        entity_type = row["entity_type"]
        entity_name = row["entity_name"]
        entity_id = entity_lookup.get((entity_type, entity_name))

        if entity_id:
            resolved.append({
                "agora_id": row["agora_id"],
                "entity_id": entity_id,
                "entity_type": row["entity_type"],
                "mention_count": row["mention_count"],
                "char_positions": row["char_positions"],
                "contexts": row["contexts"],
            })
        else:
            log.debug(
                "Unresolved entity: %s %s (not in dictionary)", entity_type, entity_name
            )

    return resolved


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def _upsert_table(
    client, table: str, rows: list[dict], on_conflict: str, dry_run: bool
) -> int:
    """Upsert rows to a table in batches."""
    if not rows:
        print(f"  {table}: 0 rows — skipping")
        return 0

    if dry_run:
        print(f"  {table}: {len(rows):,} rows would be upserted")
        return len(rows)

    total = len(rows)
    uploaded = 0
    for chunk in _batched(rows, SUPABASE_BATCH_SIZE):
        client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        uploaded += len(chunk)
        if total > SUPABASE_BATCH_SIZE:
            print(f"  {table}: {uploaded:,}/{total:,} rows …", flush=True)

    print(f"  {table}: {total:,} rows upserted")
    return total


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    entity_dict_path: Path | None = None,
    annotations_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Sync NER entities and document-entity mappings to Supabase."""
    entity_dict_path = entity_dict_path or ENTITY_DICTIONARY_PATH
    annotations_dir = annotations_dir or MANUAL_ANNOTATIONS_DIR

    client = None if dry_run else _get_supabase_client()
    totals: dict[str, int] = {}

    print("\n[1/2] Loading NER data …")
    entity_rows = _load_entity_dictionary(entity_dict_path)
    print(f"  Entity dictionary: {len(entity_rows):,} entities")

    doc_entity_rows = _load_doc_entities(annotations_dir)
    print(f"  Document annotations: {len(doc_entity_rows):,} mentions")

    print("\n[2/2] Upserting to Supabase …")

    # Upsert ner_entities first
    totals["ner_entities"] = _upsert_table(
        client, "ner_entities", entity_rows, "entity_id", dry_run
    )

    # Build lookup and resolve doc_entity entity_ids
    if entity_rows:
        entity_lookup = _build_entity_lookup(entity_rows)
        resolved_doc_entities = _resolve_doc_entity_ids(doc_entity_rows, entity_lookup)
    else:
        resolved_doc_entities = []

    # Upsert doc_entities
    totals["doc_entities"] = _upsert_table(
        client, "doc_entities", resolved_doc_entities, "agora_id,entity_id", dry_run
    )

    # Summary
    suffix = " (dry-run)" if dry_run else ""
    print(f"\nSync complete{suffix}")
    for table in ("ner_entities", "doc_entities"):
        if table in totals:
            print(f"  {table:<20} {totals[table]:>10,} rows")
