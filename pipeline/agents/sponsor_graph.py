"""Phase 1: Build sponsor graph from agora_with_sponsors.csv.

Deterministic — no LLM calls. Produces:
- sponsor_nodes.csv
- sponsor_edges.csv
- doc_sponsor_matrix.json
"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pipeline.config import AGENTS_OUTPUT_DIR
from pipeline.agents.models_agent import SponsorRecord

log = logging.getLogger(__name__)


def _parse_chamber(name: str) -> str:
    """Extract chamber from sponsor name prefix."""
    if name.startswith("Rep."):
        return "Rep"
    if name.startswith("Sen."):
        return "Sen"
    if name.startswith("Del."):
        return "Del"
    return ""


def _parse_name_parts(full_name: str) -> tuple[str, str]:
    """Parse 'Rep. Graves, Sam [R-MO-6]' into (last_name, first_name)."""
    # Strip prefix and bracketed suffix
    clean = re.sub(r"^(Rep\.|Sen\.|Del\.)\s*", "", full_name)
    clean = re.sub(r"\s*\[.*\]\s*$", "", clean).strip()
    parts = clean.split(",", 1)
    last_name = parts[0].strip()
    first_name = parts[1].strip() if len(parts) > 1 else ""
    return last_name, first_name


def _clean_district(raw: str) -> str:
    """Convert '6.0' to '6', handle empty/nan."""
    if not raw or raw.lower() == "nan":
        return ""
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return str(raw).strip()


def load_sponsor_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Load agora_with_sponsors.csv and return list of row dicts."""
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_sponsor_graph(
    rows: list[dict[str, Any]],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Build sponsor nodes, edges, and doc-sponsor matrix.

    Returns stats dict.
    """
    output_dir = output_dir or AGENTS_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    sponsors: dict[str, SponsorRecord] = {}
    edges: list[dict[str, str]] = []
    doc_sponsor_map: dict[str, list[str]] = defaultdict(list)
    doc_url_map: dict[str, str] = {}  # agora_id -> Link to document

    skipped_no_sponsor = 0

    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        bioguide = row.get("Sponsor_bioguideId", "").strip()
        full_name = row.get("Sponsor_Name", "").strip()
        url = row.get("Link to document", "").strip()

        if not agora_id:
            continue

        doc_url_map[agora_id] = url

        if not bioguide:
            skipped_no_sponsor += 1
            continue

        # Build or update sponsor record
        if bioguide not in sponsors:
            last_name, first_name = _parse_name_parts(full_name)
            sponsors[bioguide] = SponsorRecord(
                bioguide_id=bioguide,
                full_name=full_name,
                last_name=last_name,
                first_name=first_name,
                party=row.get("Sponsor_Party", "").strip(),
                state=row.get("Sponsor_State", "").strip(),
                district=_clean_district(row.get("Sponsor_District", "")),
                chamber=_parse_chamber(full_name),
            )

        # SPONSORED_BY edge
        edges.append({
            "src_id": f"document:{agora_id}",
            "relation": "SPONSORED_BY",
            "dst_id": f"sponsor:{bioguide}",
            "layer": "1",
        })
        doc_sponsor_map[agora_id].append(bioguide)

    # Derive SHARES_SPONSOR edges (doc pairs sharing the same primary sponsor)
    sponsor_to_docs: dict[str, list[str]] = defaultdict(list)
    for agora_id, bio_ids in doc_sponsor_map.items():
        for bio_id in bio_ids:
            sponsor_to_docs[bio_id].append(agora_id)

    shares_edges = []
    for bio_id, doc_ids in sponsor_to_docs.items():
        if len(doc_ids) < 2:
            continue
        # Only create edges within the same sponsor group
        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                shares_edges.append({
                    "src_id": f"document:{doc_ids[i]}",
                    "relation": "SHARES_SPONSOR",
                    "dst_id": f"document:{doc_ids[j]}",
                    "layer": "1",
                    "sponsor_bioguide": bio_id,
                })

    # Write sponsor nodes CSV
    nodes_path = output_dir / "sponsor_nodes.csv"
    node_fields = ["node_id", "bioguide_id", "full_name", "last_name", "first_name",
                    "party", "state", "district", "chamber"]
    with nodes_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=node_fields)
        writer.writeheader()
        for s in sorted(sponsors.values(), key=lambda x: x.bioguide_id):
            writer.writerow(s.to_dict())

    # Write edges CSV (SPONSORED_BY + SHARES_SPONSOR)
    edges_path = output_dir / "sponsor_edges.csv"
    all_edges = edges + shares_edges
    if all_edges:
        edge_fields = list(all_edges[0].keys())
        # Ensure all fields are captured
        for e in all_edges:
            for k in e:
                if k not in edge_fields:
                    edge_fields.append(k)
        with edges_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=edge_fields, extrasaction="ignore")
            writer.writeheader()
            for e in all_edges:
                writer.writerow(e)

    # Write doc-sponsor matrix JSON
    matrix_path = output_dir / "doc_sponsor_matrix.json"
    matrix_path.write_text(
        json.dumps(dict(doc_sponsor_map), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    # Write doc-url mapping for bill grouping in Phase 2
    url_path = output_dir / "doc_url_map.json"
    url_path.write_text(
        json.dumps(doc_url_map, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    stats = {
        "total_docs": len(rows),
        "docs_with_sponsor": len(rows) - skipped_no_sponsor,
        "docs_without_sponsor": skipped_no_sponsor,
        "unique_sponsors": len(sponsors),
        "sponsored_by_edges": len(edges),
        "shares_sponsor_edges": len(shares_edges),
        "unique_urls": len(set(doc_url_map.values())),
    }

    log.info(
        "Sponsor graph: %d sponsors, %d SPONSORED_BY edges, %d SHARES_SPONSOR edges",
        stats["unique_sponsors"],
        stats["sponsored_by_edges"],
        stats["shares_sponsor_edges"],
    )
    return stats


def build_cosponsor_graph(
    rows: list[dict[str, Any]],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Build cosponsor graph (active + withdrawn) from agora_cosponsors_long.csv.

    Produces:
    - cosponsor_nodes.csv, cosponsor_edges.csv (active cosponsors, layer 1b)
    - withdrawn_cosponsor_nodes.csv, withdrawn_cosponsor_edges.csv (layer 1.75)

    Returns stats dict.
    """
    output_dir = output_dir or AGENTS_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    active_cosponsors: dict[str, SponsorRecord] = {}
    withdrawn_cosponsors: dict[str, SponsorRecord] = {}
    active_edges: list[dict[str, str]] = []
    withdrawn_edges: list[dict[str, str]] = []
    doc_cosponsor_map: dict[str, list[str]] = defaultdict(list)  # for SHARES_COSPONSOR

    skipped_no_cosponsor = 0
    active_count = 0
    withdrawn_count = 0

    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        bioguide = row.get("Cosponsor_BioguideId", "").strip()
        full_name = row.get("Cosponsor_FullName", "").strip()
        is_withdrawn = row.get("Cosponsor_IsWithdrawn", "").strip().lower() == "true"
        withdrawn_date = row.get("Cosponsor_WithdrawnDate", "").strip() if is_withdrawn else ""
        is_original = row.get("Cosponsor_IsOriginal", "").strip().lower() == "true"

        if not agora_id:
            continue

        if not bioguide:
            skipped_no_cosponsor += 1
            continue

        # Parse cosponsor details
        last_name, first_name = _parse_name_parts(full_name)
        cosponsor_rec = SponsorRecord(
            bioguide_id=bioguide,
            full_name=full_name,
            last_name=last_name,
            first_name=first_name,
            party=row.get("Cosponsor_Party", "").strip(),
            state=row.get("Cosponsor_State", "").strip(),
            district=_clean_district(row.get("Cosponsor_District", "")),
            chamber=_parse_chamber(full_name),
        )

        # Bucket into active vs withdrawn
        if is_withdrawn:
            withdrawn_cosponsors[bioguide] = cosponsor_rec
            edge = {
                "src_id": f"document:{agora_id}",
                "relation": "WITHDREW_COSPONSOR",
                "dst_id": f"sponsor:{bioguide}",
                "layer": "1.75",
                "withdrawn_date": withdrawn_date,
            }
            withdrawn_edges.append(edge)
            withdrawn_count += 1
        else:
            active_cosponsors[bioguide] = cosponsor_rec
            edge = {
                "src_id": f"document:{agora_id}",
                "relation": "COSPONSORED_BY",
                "dst_id": f"sponsor:{bioguide}",
                "layer": "1b",
                "is_original": str(is_original),
            }
            active_edges.append(edge)
            doc_cosponsor_map[agora_id].append(bioguide)
            active_count += 1

    # Derive SHARES_COSPONSOR edges for active cosponsors
    cosponsor_to_docs: dict[str, list[str]] = defaultdict(list)
    for agora_id, bio_ids in doc_cosponsor_map.items():
        for bio_id in bio_ids:
            cosponsor_to_docs[bio_id].append(agora_id)

    shares_edges = []
    for bio_id, doc_ids in cosponsor_to_docs.items():
        if len(doc_ids) < 2:
            continue
        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                shares_edges.append({
                    "src_id": f"document:{doc_ids[i]}",
                    "relation": "SHARES_COSPONSOR",
                    "dst_id": f"document:{doc_ids[j]}",
                    "layer": "1b",
                    "cosponsor_bioguide": bio_id,
                })

    # Write active cosponsor nodes and edges
    nodes_path = output_dir / "cosponsor_nodes.csv"
    node_fields = ["node_id", "bioguide_id", "full_name", "last_name", "first_name",
                    "party", "state", "district", "chamber"]
    with nodes_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=node_fields)
        writer.writeheader()
        for s in sorted(active_cosponsors.values(), key=lambda x: x.bioguide_id):
            writer.writerow(s.to_dict())

    edges_path = output_dir / "cosponsor_edges.csv"
    active_all_edges = active_edges + shares_edges
    if active_all_edges:
        edge_fields = list(active_all_edges[0].keys())
        for e in active_all_edges:
            for k in e:
                if k not in edge_fields:
                    edge_fields.append(k)
        with edges_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=edge_fields, extrasaction="ignore")
            writer.writeheader()
            for e in active_all_edges:
                writer.writerow(e)

    # Write withdrawn cosponsor nodes and edges
    withdrawn_nodes_path = output_dir / "withdrawn_cosponsor_nodes.csv"
    with withdrawn_nodes_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=node_fields)
        writer.writeheader()
        for s in sorted(withdrawn_cosponsors.values(), key=lambda x: x.bioguide_id):
            writer.writerow(s.to_dict())

    withdrawn_edges_path = output_dir / "withdrawn_cosponsor_edges.csv"
    if withdrawn_edges:
        edge_fields = list(withdrawn_edges[0].keys())
        for e in withdrawn_edges:
            for k in e:
                if k not in edge_fields:
                    edge_fields.append(k)
        with withdrawn_edges_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=edge_fields, extrasaction="ignore")
            writer.writeheader()
            for e in withdrawn_edges:
                writer.writerow(e)

    stats = {
        "total_rows": len(rows),
        "rows_without_cosponsor": skipped_no_cosponsor,
        "active_cosponsors": len(active_cosponsors),
        "withdrawn_cosponsors": len(withdrawn_cosponsors),
        "active_edges": len(active_all_edges),
        "withdrawn_edges": len(withdrawn_edges),
        "shares_cosponsor_edges": len(shares_edges),
    }

    log.info(
        "Cosponsor graph: %d active cosponsors (%d edges), %d withdrawn (%d edges)",
        stats["active_cosponsors"],
        stats["active_edges"],
        stats["withdrawn_cosponsors"],
        stats["withdrawn_edges"],
    )
    return stats


def run(csv_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Entry point: load CSV and build sponsor graph."""
    rows = load_sponsor_csv(csv_path)
    return build_sponsor_graph(rows, output_dir)


def run_cosponsor(csv_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Entry point: load CSV and build cosponsor graph."""
    rows = load_sponsor_csv(csv_path)
    return build_cosponsor_graph(rows, output_dir)
