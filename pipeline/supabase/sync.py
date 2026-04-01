from __future__ import annotations

import os
import tempfile
import zipfile
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests

from ..config import (
    SUPABASE_BATCH_SIZE,
    ZENODO_RECORD_ID,
    DATA_DIR,
    PROJECT_ROOT,
    COSPONSOR_CSV_PATH,
    SPONSORS_CSV_PATH,
)

# ---------------------------------------------------------------------------
# Local file defaults
# ---------------------------------------------------------------------------

LOCAL_PATHS: dict[str, Path] = {
    "documents":   DATA_DIR / "documents.csv",
    "segments":    DATA_DIR / "segments.csv",
    "authorities": DATA_DIR / "authorities.csv",
    "collections": DATA_DIR / "collections.csv",
    "sponsors":    SPONSORS_CSV_PATH,
    "cosponsors":  COSPONSOR_CSV_PATH,
}

# ---------------------------------------------------------------------------
# Taxonomy columns (77 booleans → TEXT[] array)
# ---------------------------------------------------------------------------

_TAXONOMY_PREFIXES = (
    "Applications:",
    "Harms:",
    "Incentives:",
    "Risk factors:",
    "Strategies:",
)


def _detect_taxonomy_cols(columns: list[str]) -> list[str]:
    """Return column names that are taxonomy booleans."""
    return [c for c in columns if c.startswith(_TAXONOMY_PREFIXES)]


def _row_taxonomy_tags(row: dict, tax_cols: list[str]) -> list[str]:
    """Convert boolean taxonomy columns to a list of active tag names."""
    return [col for col in tax_cols if str(row.get(col, "")).strip().lower() == "true"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _batched(iterable, n: int) -> Iterator[list]:
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def _get_supabase_client():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise SystemExit(
            "ERROR: SUPABASE_URL and SUPABASE_KEY must be set in your .env file."
        )
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Zenodo download
# ---------------------------------------------------------------------------

_ZENODO_FILENAMES: dict[str, str] = {
    "documents.csv":   "documents",
    "segments.csv":    "segments",
    "authorities.csv": "authorities",
    "collections.csv": "collections",
}


def _download_zenodo_zip(record_id: str, dest: Path) -> None:
    api_url = f"https://zenodo.org/api/records/{record_id}"
    print(f"  Fetching Zenodo metadata: {api_url}")
    resp = requests.get(api_url, timeout=30)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    zip_files = [f for f in files if f["key"].endswith(".zip")]
    if not zip_files:
        raise SystemExit("ERROR: No zip file found in Zenodo record.")
    url = zip_files[0]["links"]["self"]
    print(f"  Downloading {zip_files[0]['key']} …", end=" ", flush=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=65536):
                fh.write(chunk)
    size_mb = dest.stat().st_size // (1024 * 1024)
    print(f"{size_mb} MB")


def _extract_csvs_from_zip(zip_path: Path, tmp: Path) -> dict[str, Path]:
    """Extract recognised CSVs from zip into tmp, return {table: path}."""
    result: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            fname = Path(member).name
            if fname in _ZENODO_FILENAMES:
                table = _ZENODO_FILENAMES[fname]
                out = tmp / fname
                out.write_bytes(zf.read(member))
                result[table] = out
                print(f"  Extracted {fname}")
    return result


# ---------------------------------------------------------------------------
# Parse / normalize for new schema
# ---------------------------------------------------------------------------

def _load_authorities(path: Path) -> list[dict]:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "name": r.get("Name", ""),
            "jurisdiction": r.get("Jurisdiction", ""),
            "parent_authority": r.get("Parent authority", ""),
        })
    return rows


def _load_collections(path: Path) -> list[dict]:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "name": r.get("Name", ""),
            "description": r.get("Description", ""),
        })
    return rows


def _load_documents(path: Path, authority_lookup: dict[str, int]) -> list[dict]:
    """Load documents.csv → list of dicts for agora_documents table."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    tax_cols = _detect_taxonomy_cols(list(df.columns))
    rows = []
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        agora_id = row_dict.get("AGORA ID", "")
        if not agora_id:
            continue
        authority_name = row_dict.get("Authority", "")
        rows.append({
            "agora_id": int(agora_id),
            "official_name": row_dict.get("Official name", ""),
            "casual_name": row_dict.get("Casual name", ""),
            "link_to_document": row_dict.get("Link to document", ""),
            "authority_name": authority_name,
            "authority_id": authority_lookup.get(authority_name),
            "collections_raw": row_dict.get("Collections", ""),
            "most_recent_activity": row_dict.get("Most recent activity", ""),
            "most_recent_activity_date": row_dict.get("Most recent activity date", ""),
            "proposed_date": row_dict.get("Proposed date", ""),
            "annotated": row_dict.get("Annotated?", "").lower() == "true" or None,
            "validated": row_dict.get("Validated?", "").lower() == "true" or None,
            "primarily_applies_government": row_dict.get("Primarily applies to the government", "").lower() == "true" or None,
            "primarily_applies_private": row_dict.get("Primarily applies to the private sector", "").lower() == "true" or None,
            "short_summary": row_dict.get("Short summary", ""),
            "long_summary": row_dict.get("Long summary", ""),
            "tags": row_dict.get("Tags", ""),
            "number_of_segments": int(row_dict.get("Number of segments created", "0") or "0") or None,
            "official_plaintext_retrieved": row_dict.get("Official plaintext retrieved", ""),
            "official_plaintext_source": row_dict.get("Official plaintext source", ""),
            "official_plaintext_unavailable": row_dict.get("Official plaintext unavailable/infeasible", "").lower() == "true" or None,
            "official_pdf_source": row_dict.get("Official pdf source", ""),
            "official_pdf_retrieved": row_dict.get("Official pdf retrieved", ""),
            "taxonomy_tags": _row_taxonomy_tags(row_dict, tax_cols),
        })
    return rows


def _load_sponsors(path: Path, valid_doc_ids: set[int]) -> list[dict]:
    """Load sponsors CSV → list of dicts for bill_sponsors table."""
    import json
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    rows = []
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        agora_id_str = row_dict.get("AGORA ID", "")
        if not agora_id_str:
            continue
        try:
            agora_id = int(agora_id_str)
        except (ValueError, TypeError):
            continue
        if agora_id not in valid_doc_ids:
            continue
        cosponsor_list_raw = row_dict.get("Cosponsor_List_Current_JSON", "")
        try:
            cosponsor_list_json = json.loads(cosponsor_list_raw) if cosponsor_list_raw else None
        except (ValueError, TypeError):
            cosponsor_list_json = None
        rows.append({
            "agora_id": agora_id,
            "api_call_url": row_dict.get("api_callURL", ""),
            "party_code": row_dict.get("Party_Code", ""),
            "party_name": row_dict.get("Party_Name", ""),
            "policy_area": row_dict.get("Policy_Area", ""),
            "latest_action": row_dict.get("Latest_Action", ""),
            "cosponsor_count": int(row_dict.get("Cosponsor_Count", "0") or "0"),
            "cosponsor_count_all": int(row_dict.get("Cosponsor_Count_All_From_List", "0") or "0"),
            "cosponsor_count_current": int(row_dict.get("Cosponsor_Count_Current_From_List", "0") or "0"),
            "cosponsor_names_current": row_dict.get("Cosponsor_Names_Current_Str", ""),
            "cosponsor_list_json": cosponsor_list_json,
        })
    return rows


def _load_cosponsors(path: Path, valid_doc_ids: set[int]) -> list[dict]:
    """Load cosponsors CSV → list of dicts for bill_cosponsors table."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    rows = []
    skipped = 0
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        agora_id_str = row_dict.get("AGORA ID", "")
        bioguide_id = row_dict.get("Cosponsor_BioguideId", "").strip()
        if not agora_id_str or not bioguide_id:
            skipped += 1
            continue
        try:
            agora_id = int(agora_id_str)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if agora_id not in valid_doc_ids:
            skipped += 1
            continue
        rows.append({
            "agora_id": agora_id,
            "bioguide_id": bioguide_id,
            "full_name": row_dict.get("Cosponsor_FullName", ""),
            "first_name": row_dict.get("Cosponsor_FirstName", ""),
            "middle_name": row_dict.get("Cosponsor_MiddleName", ""),
            "last_name": row_dict.get("Cosponsor_LastName", ""),
            "party": row_dict.get("Cosponsor_Party", ""),
            "state": row_dict.get("Cosponsor_State", ""),
            "district": row_dict.get("Cosponsor_District", ""),
            "sponsorship_date": row_dict.get("Cosponsor_SponsorshipDate", "") or None,
            "is_original": row_dict.get("Cosponsor_IsOriginal", "").lower() == "true",
            "withdrawn_date": row_dict.get("Cosponsor_WithdrawnDate", "") or None,
            "is_withdrawn": row_dict.get("Cosponsor_IsWithdrawn", "").lower() == "true",
        })
    if skipped:
        print(f"  cosponsors: skipped {skipped:,} rows (missing ID or FK mismatch)")
    return rows


def _load_segments(path: Path, valid_doc_ids: set[int]) -> list[dict]:
    """Load segments.csv → list of dicts for segments table."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").where(pd.notna, "")
    tax_cols = _detect_taxonomy_cols(list(df.columns))
    rows = []
    skipped = 0
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        doc_id_str = row_dict.get("Document ID", "")
        if not doc_id_str:
            skipped += 1
            continue
        doc_id = int(doc_id_str)
        if doc_id not in valid_doc_ids:
            skipped += 1
            continue
        seg_pos = row_dict.get("Segment position", "")
        if not seg_pos:
            skipped += 1
            continue
        rows.append({
            "document_id": doc_id,
            "segment_position": int(seg_pos),
            "text": row_dict.get("Text", ""),
            "tags": row_dict.get("Tags", ""),
            "summary": row_dict.get("Summary", ""),
            "non_operative": row_dict.get("Non-operative", "").lower() == "true" or None,
            "not_ai_related": row_dict.get("Not AI-related", "").lower() == "true" or None,
            "segment_annotated": row_dict.get("Segment annotated", "").lower() == "true" or None,
            "segment_validated": row_dict.get("Segment validated", "").lower() == "true" or None,
            "taxonomy_tags": _row_taxonomy_tags(row_dict, tax_cols),
        })
    if skipped:
        print(f"  segments: skipped {skipped:,} rows (missing doc ID or FK mismatch)")
    return rows


def _build_document_collections(
    doc_rows: list[dict], collection_lookup: dict[str, int]
) -> list[dict]:
    """Build junction rows from documents' collections_raw field."""
    junctions = []
    for doc in doc_rows:
        raw = doc.get("collections_raw", "")
        if not raw:
            continue
        agora_id = doc["agora_id"]
        for coll_name in raw.split(";"):
            coll_name = coll_name.strip()
            coll_id = collection_lookup.get(coll_name)
            if coll_id is not None:
                junctions.append({"agora_id": agora_id, "collection_id": coll_id})
    return junctions


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

# Table name → on_conflict column(s)
ON_CONFLICT: dict[str, str] = {
    "authorities":           "name",
    "collections":           "name",
    "agora_documents":       "agora_id",
    "document_collections":  "agora_id,collection_id",
    "segments":              "document_id,segment_position",
    "bill_sponsors":         "agora_id",
    "bill_cosponsors":       "agora_id,bioguide_id",
}

# Order matters: authorities & collections first, then documents, then junctions & segments, then sponsors
TABLE_ORDER = ("authorities", "collections", "agora_documents", "document_collections", "segments", "bill_sponsors", "bill_cosponsors")


def _upsert_table(client, table: str, rows: list[dict], on_conflict: str, dry_run: bool) -> int:
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
    tables: list[str] | None = None,
    dry_run: bool = False,
    record_id: str = "",
) -> None:
    active_tables = set(tables) if tables else set(TABLE_ORDER)
    client = None if dry_run else _get_supabase_client()
    totals: dict[str, int] = {}

    # --- resolve file paths ---
    resolved: dict[str, Path] = {}
    needs_zenodo: list[str] = []

    # Map table names to source CSV keys
    csv_keys = {
        "authorities": "authorities",
        "collections": "collections",
        "agora_documents": "documents",
        "document_collections": "documents",  # derived from documents
        "segments": "segments",
        "bill_sponsors": "sponsors",
        "bill_cosponsors": "cosponsors",
    }

    print("\n[1/3] Resolving source files …")
    needed_csvs = set()
    for table in TABLE_ORDER:
        if table not in active_tables:
            continue
        needed_csvs.add(csv_keys[table])

    for csv_key in needed_csvs:
        local = LOCAL_PATHS.get(csv_key)
        if local and local.exists():
            print(f"  {csv_key}: using local {local.relative_to(PROJECT_ROOT)}")
            resolved[csv_key] = local
        else:
            needs_zenodo.append(csv_key)

    if needs_zenodo:
        rid = record_id or ZENODO_RECORD_ID
        if not rid:
            for t in needs_zenodo:
                print(f"  WARNING: no local file for '{t}' and ZENODO_RECORD_ID not set — skipping")
        else:
            print(f"\n  Fetching missing CSVs from Zenodo record {rid}: {needs_zenodo}")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                zip_path = tmp_path / "agora.zip"
                _download_zenodo_zip(rid, zip_path)
                extracted = _extract_csvs_from_zip(zip_path, tmp_path)
                for csv_key in needs_zenodo:
                    if csv_key in extracted:
                        resolved[csv_key] = extracted[csv_key]
                    else:
                        print(f"  WARNING: '{csv_key}' not found in Zenodo zip — skipping")

    # --- load & upsert ---
    print("\n[2/3] Loading and transforming data …")

    # Step 1: authorities
    authority_lookup: dict[str, int] = {}
    if "authorities" in active_tables and "authorities" in resolved:
        auth_rows = _load_authorities(resolved["authorities"])
        totals["authorities"] = _upsert_table(
            client, "authorities", auth_rows, ON_CONFLICT["authorities"], dry_run
        )
        # Fetch back the SERIAL ids for FK lookups
        if client:
            resp = client.table("authorities").select("id, name").execute()
            authority_lookup = {r["name"]: r["id"] for r in resp.data}
            print(f"  authority lookup: {len(authority_lookup)} entries")

    # Step 2: collections
    collection_lookup: dict[str, int] = {}
    if "collections" in active_tables and "collections" in resolved:
        coll_rows = _load_collections(resolved["collections"])
        totals["collections"] = _upsert_table(
            client, "collections", coll_rows, ON_CONFLICT["collections"], dry_run
        )
        if client:
            resp = client.table("collections").select("id, name").execute()
            collection_lookup = {r["name"]: r["id"] for r in resp.data}
            print(f"  collection lookup: {len(collection_lookup)} entries")

    # Step 3: documents
    doc_rows: list[dict] = []
    valid_doc_ids: set[int] = set()
    if "agora_documents" in active_tables and "documents" in resolved:
        doc_rows = _load_documents(resolved["documents"], authority_lookup)
        valid_doc_ids = {d["agora_id"] for d in doc_rows}
        totals["agora_documents"] = _upsert_table(
            client, "agora_documents", doc_rows, ON_CONFLICT["agora_documents"], dry_run
        )

    # Step 4: document_collections junction
    if "document_collections" in active_tables and doc_rows and collection_lookup:
        junction_rows = _build_document_collections(doc_rows, collection_lookup)
        totals["document_collections"] = _upsert_table(
            client, "document_collections", junction_rows,
            ON_CONFLICT["document_collections"], dry_run
        )

    # Step 5: segments
    if "segments" in active_tables and "segments" in resolved:
        # If we didn't load documents in this run, fetch valid IDs from DB
        if not valid_doc_ids and client:
            resp = client.table("agora_documents").select("agora_id").execute()
            valid_doc_ids = {r["agora_id"] for r in resp.data}
        seg_rows = _load_segments(resolved["segments"], valid_doc_ids)
        totals["segments"] = _upsert_table(
            client, "segments", seg_rows, ON_CONFLICT["segments"], dry_run
        )

    # Step 6: bill_sponsors
    if "bill_sponsors" in active_tables and "sponsors" in resolved:
        # If we didn't load documents in this run, fetch valid IDs from DB
        if not valid_doc_ids and client:
            resp = client.table("agora_documents").select("agora_id").execute()
            valid_doc_ids = {r["agora_id"] for r in resp.data}
        sponsor_rows = _load_sponsors(resolved["sponsors"], valid_doc_ids)
        totals["bill_sponsors"] = _upsert_table(
            client, "bill_sponsors", sponsor_rows, ON_CONFLICT["bill_sponsors"], dry_run
        )

    # Step 7: bill_cosponsors
    if "bill_cosponsors" in active_tables and "cosponsors" in resolved:
        # If we didn't load documents in this run, fetch valid IDs from DB
        if not valid_doc_ids and client:
            resp = client.table("agora_documents").select("agora_id").execute()
            valid_doc_ids = {r["agora_id"] for r in resp.data}
        cosponsor_rows = _load_cosponsors(resolved["cosponsors"], valid_doc_ids)
        totals["bill_cosponsors"] = _upsert_table(
            client, "bill_cosponsors", cosponsor_rows, ON_CONFLICT["bill_cosponsors"], dry_run
        )

    # --- summary ---
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    suffix = " (dry-run)" if dry_run else ""
    print(f"\n[3/3] Sync complete{suffix} — {ts}")
    for table in TABLE_ORDER:
        if table in totals:
            print(f"  {table:<25} {totals[table]:>10,} rows")
