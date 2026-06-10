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

from ..config import (
    CANONICALIZED_ENTITIES_PATH,
    ENTITY_DICTIONARY_PATH,
    MANUAL_ANNOTATIONS_DIR,
    SUPABASE_BATCH_SIZE,
)

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
# Load from entities_canonicalized.jsonl
# ---------------------------------------------------------------------------

# Prefix map for generating synthetic entity_ids from entity type + canonical name
_TYPE_PREFIX: dict[str, str] = {
    "organizations": "org",
    "offices": "office",
    "roles": "role",
    "legislation_refs": "legislation",
    "named_docs": "doc",
}

# Name field per entity type (matches NER output schema)
_NAME_FIELD: dict[str, str] = {
    "organizations": "name",
    "offices": "name",
    "roles": "title",
    "legislation_refs": "name",
    "named_docs": "name",
}


def _make_entity_id(entity_type: str, name: str) -> str:
    """Generate a deterministic entity_id from type + name, matching registry convention."""
    import re
    prefix = _TYPE_PREFIX.get(entity_type, entity_type)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_")
    return f"{prefix}:{slug}"


def _load_canonicalized_entities(
    path: Path,
    existing_entity_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load entities_canonicalized.jsonl and derive ner_entities + doc_entities rows.

    Returns (new_entity_rows, doc_entity_rows).
    new_entity_rows: entities not already in existing_entity_ids.
    doc_entity_rows: one row per (agora_id, entity_id) unique mention.
    """
    if not path.exists():
        log.warning("Canonicalized entities file not found at %s", path)
        return [], []

    # Accumulate entity dict by entity_id (to deduplicate across docs)
    entity_map: dict[str, dict[str, Any]] = {}
    # (agora_id, entity_id) → doc_entity row
    doc_entity_map: dict[tuple[int, str], dict[str, Any]] = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                log.warning("Skipped malformed line: %s", e)
                continue

            agora_id_raw = row.get("agora_id")
            try:
                agora_id = int(agora_id_raw)
            except (ValueError, TypeError):
                log.warning("Invalid agora_id: %s", agora_id_raw)
                continue

            for entity_type, name_field in _NAME_FIELD.items():
                for entity in row.get(entity_type, []):
                    name = entity.get(name_field, "").strip()
                    if not name:
                        continue

                    # Use _canonicalized_from name if present (resolved bare alias)
                    canonical_name = entity.get("_canonicalized_from") or name
                    entity_id = _make_entity_id(entity_type, canonical_name)

                    # Accumulate entity dictionary entry if not already known
                    if entity_id not in existing_entity_ids and entity_id not in entity_map:
                        entity_map[entity_id] = {
                            "entity_id": entity_id,
                            "entity_type": entity_type,
                            "canonical_name": canonical_name,
                            "acronym": entity.get("acronym"),
                            "aliases": [],
                            "soft_aliases": [],
                            "metadata": {},
                            "mention_count": 0,
                            "first_seen": str(agora_id),
                            "created_at": row.get("extracted_at"),
                            "updated_at": row.get("extracted_at"),
                        }

                    # Accumulate doc_entity mention
                    key = (agora_id, entity_id)
                    if key not in doc_entity_map:
                        doc_entity_map[key] = {
                            "agora_id": agora_id,
                            "entity_id": entity_id,
                            "entity_type": entity_type,
                            "mention_count": 0,
                            "char_positions": [],
                            "contexts": [],
                        }
                    de = doc_entity_map[key]
                    de["mention_count"] += 1
                    if "char_start" in entity and "char_end" in entity:
                        de["char_positions"].append({
                            "start": entity["char_start"],
                            "end": entity["char_end"],
                        })
                    if "context" in entity:
                        de["contexts"].append(entity["context"])

    return list(entity_map.values()), list(doc_entity_map.values())


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
    canonicalized_path: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Sync NER entities and document-entity mappings to Supabase.

    Sources (merged):
    - entity_dictionary.jsonl  → ner_entities (canonical registry)
    - entities_canonicalized.jsonl → ner_entities (new entities) + doc_entities
    - manual_annotations/       → doc_entities (legacy, used if present)
    """
    entity_dict_path = entity_dict_path or ENTITY_DICTIONARY_PATH
    annotations_dir = annotations_dir or MANUAL_ANNOTATIONS_DIR
    canonicalized_path = canonicalized_path or CANONICALIZED_ENTITIES_PATH

    client = None if dry_run else _get_supabase_client()
    totals: dict[str, int] = {}

    print("\n[1/2] Loading NER data …")

    # 1a. Load canonical entity dictionary
    entity_rows = _load_entity_dictionary(entity_dict_path)
    print(f"  Entity dictionary: {len(entity_rows):,} entities")
    existing_ids = {e["entity_id"] for e in entity_rows}

    # 1b. Load entities_canonicalized.jsonl — new entities + doc_entities
    new_entity_rows, canon_doc_entity_rows = _load_canonicalized_entities(
        canonicalized_path, existing_ids
    )
    print(f"  Canonicalized entities (new): {len(new_entity_rows):,} entities, "
          f"{len(canon_doc_entity_rows):,} doc-entity mappings")

    # 1c. Load legacy manual annotations (if present)
    legacy_doc_rows = _load_doc_entities(annotations_dir)
    if legacy_doc_rows:
        print(f"  Legacy manual annotations: {len(legacy_doc_rows):,} mentions")

    # Merge entity rows: dictionary first, then new-from-canonicalized
    all_entity_rows = entity_rows + new_entity_rows

    print("\n[2/2] Upserting to Supabase …")

    # Upsert ner_entities first (dictionary + newly derived)
    totals["ner_entities"] = _upsert_table(
        client, "ner_entities", all_entity_rows, "entity_id", dry_run
    )

    # Resolve legacy annotations against full entity set
    if legacy_doc_rows and all_entity_rows:
        entity_lookup = _build_entity_lookup(all_entity_rows)
        resolved_legacy = _resolve_doc_entity_ids(legacy_doc_rows, entity_lookup)
    else:
        resolved_legacy = []

    # Merge doc_entity rows: canonicalized primary, legacy fallback (deduplicated by key)
    doc_entity_by_key: dict[tuple, dict] = {
        (r["agora_id"], r["entity_id"]): r for r in canon_doc_entity_rows
    }
    for r in resolved_legacy:
        key = (r["agora_id"], r["entity_id"])
        if key not in doc_entity_by_key:
            doc_entity_by_key[key] = r
    all_doc_entity_rows = list(doc_entity_by_key.values())

    # Upsert doc_entities
    totals["doc_entities"] = _upsert_table(
        client, "doc_entities", all_doc_entity_rows, "agora_id,entity_id", dry_run
    )

    # Summary
    suffix = " (dry-run)" if dry_run else ""
    print(f"\nSync complete{suffix}")
    for table in ("ner_entities", "doc_entities"):
        if table in totals:
            print(f"  {table:<20} {totals[table]:>10,} rows")
