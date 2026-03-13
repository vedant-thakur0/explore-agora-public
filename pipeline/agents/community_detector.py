"""Phase 2: Community detection via Louvain on multi-signal document similarity.

Deterministic — no LLM calls. Produces communities.json.

Signals:
1. Taxonomy tag Jaccard (80+ binary columns)
2. Summary TF-IDF cosine (computed from Short/Long summary + Tags text)
3. Collections Jaccard
4. Cosponsor overlap (optional — requires API fetch)
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path
from typing import Any

import networkx as nx

from pipeline.config import (
    AGENTS_OUTPUT_DIR,
    COMMUNITY_SIMILARITY_WEIGHTS,
    LOUVAIN_RESOLUTION,
    SIMILARITY_THRESHOLD,
    SUBCLUSTERING_RESOLUTION,
    SUBCLUSTERING_SIZE_THRESHOLD,
)
from pipeline.agents.models_agent import CommunityRecord
from pipeline.docx_matcher import fit_profile_vectorizer

log = logging.getLogger(__name__)

# Column prefixes that identify binary taxonomy columns
TAXONOMY_PREFIXES = (
    "Applications:",
    "Harms:",
    "Incentives:",
    "Risk factors:",
    "Strategies:",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_docs_csv(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _get_taxonomy_columns(row: dict[str, Any]) -> list[str]:
    """Return sorted list of taxonomy column names from a sample row."""
    return sorted(k for k in row if any(k.startswith(p) for p in TAXONOMY_PREFIXES))


def _taxonomy_vector(row: dict[str, Any], columns: list[str]) -> set[str]:
    """Return set of taxonomy columns that are True for this row."""
    return {col for col in columns if row.get(col, "").strip() == "True"}


# ---------------------------------------------------------------------------
# Bill grouping
# ---------------------------------------------------------------------------

def group_bills_by_url(
    rows: list[dict[str, Any]],
    doc_url_map: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Group AGORA IDs by their Link to document URL.

    Returns {url: [agora_id, ...]} for URLs with multiple sections.
    """
    url_to_ids: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        url = row.get("Link to document", "").strip()
        if agora_id and url:
            url_to_ids[url].append(agora_id)
    return dict(url_to_ids)


def build_bill_groups(url_to_ids: dict[str, list[str]]) -> list[list[str]]:
    """Return list of bill groups (lists of agora_ids sharing a URL)."""
    return [ids for ids in url_to_ids.values() if len(ids) > 1]


# ---------------------------------------------------------------------------
# Similarity signals
# ---------------------------------------------------------------------------

def compute_taxonomy_jaccard(
    rows: list[dict[str, Any]],
    tax_columns: list[str],
) -> dict[str, set[str]]:
    """Compute taxonomy vectors for each doc. Returns {agora_id: set_of_active_tags}."""
    vectors: dict[str, set[str]] = {}
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        if agora_id:
            vectors[agora_id] = _taxonomy_vector(row, tax_columns)
    return vectors


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def compute_summary_tfidf(rows: list[dict[str, Any]]) -> dict[str, tuple[dict[str, float], float]]:
    """Build per-document TF-IDF vectors from summaries and tags.

    Returns {agora_id: (tfidf_vec, norm)}.
    """
    texts: list[str] = []
    ids: list[str] = []
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        if not agora_id:
            continue
        parts = [
            row.get("Short summary", ""),
            row.get("Long summary", ""),
            row.get("Tags", ""),
        ]
        profile_text = " ".join(p for p in parts if p)
        texts.append(profile_text)
        ids.append(agora_id)

    if not texts:
        return {}

    vectorizer = fit_profile_vectorizer(texts)
    result: dict[str, tuple[dict[str, float], float]] = {}
    for i, agora_id in enumerate(ids):
        if i < len(vectorizer.doc_vecs):
            result[agora_id] = (vectorizer.doc_vecs[i], vectorizer.doc_norms[i])
    return result


def compute_summary_dense(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Compute unit-normalized sentence embeddings for each doc's summary+tags.

    Returns {agora_id: embedding_vector} using sentence-transformers.
    Falls back gracefully if sentence-transformers is not installed.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.warning("sentence-transformers not installed; skipping dense embeddings.")
        return {}

    from pipeline.config import DENSE_EMBEDDING_MODEL

    model = SentenceTransformer(DENSE_EMBEDDING_MODEL)
    ids: list[str] = []
    texts: list[str] = []

    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        if not agora_id:
            continue
        parts = [
            row.get("Short summary", ""),
            row.get("Long summary", ""),
            row.get("Tags", ""),
        ]
        text = " ".join(p for p in parts if p)
        ids.append(agora_id)
        texts.append(text)

    if not texts:
        return {}

    embeddings = model.encode(texts, normalize_embeddings=True)
    return {aid: emb.tolist() for aid, emb in zip(ids, embeddings)}


def cosine_similarity(
    vec_a: dict[str, float], norm_a: float,
    vec_b: dict[str, float], norm_b: float,
) -> float:
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(va * vec_b.get(tok, 0.0) for tok, va in vec_a.items())
    denom = norm_a * norm_b
    if denom == 0:
        return 0.0
    return max(0.0, min(1.0, dot / denom))


def compute_collections_sets(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Parse semicolon-delimited Collections field into sets."""
    result: dict[str, set[str]] = {}
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        raw = row.get("Collections", "").strip()
        if agora_id:
            result[agora_id] = {
                c.strip() for c in raw.split(";") if c.strip()
            }
    return result


def compute_gov_applicability(rows: list[dict[str, Any]]) -> dict[str, bool]:
    """Extract 'Primarily applies to the government' boolean."""
    result: dict[str, bool] = {}
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        val = str(row.get("Primarily applies to the government", "")).strip().lower()
        if agora_id:
            result[agora_id] = val in ("true", "1", "yes")
    return result


# ---------------------------------------------------------------------------
# Combined similarity and community detection
# ---------------------------------------------------------------------------

def compute_pairwise_similarity(
    doc_ids: list[str],
    tax_vectors: dict[str, set[str]],
    tfidf_vectors: dict[str, tuple[dict[str, float], float]],
    dense_vectors: dict[str, list[float]] | None = None,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, str, float]]:
    """Compute pairwise similarity for all doc pairs above threshold.

    Returns list of (id_a, id_b, similarity_score) triples.
    Combines taxonomy Jaccard, summary TF-IDF cosine, and dense embeddings.
    """
    w = weights or COMMUNITY_SIMILARITY_WEIGHTS
    w_tax = w.get("jaccard_taxonomy", 0.50)
    w_cos = w.get("cosine_summary", 0.25)
    w_dense = w.get("dense_cosine", 0.20)
    # cosponsor_jaccard is w.get("cosponsor_jaccard", 0.05) — deferred for now

    edges: list[tuple[str, str, float]] = []
    n = len(doc_ids)

    for i in range(n):
        a = doc_ids[i]
        tax_a = tax_vectors.get(a, set())
        tfidf_a = tfidf_vectors.get(a, ({}, 1.0))
        dense_a = dense_vectors.get(a) if dense_vectors else None

        for j in range(i + 1, n):
            b = doc_ids[j]
            tax_b = tax_vectors.get(b, set())
            tfidf_b = tfidf_vectors.get(b, ({}, 1.0))
            dense_b = dense_vectors.get(b) if dense_vectors else None

            score = (
                w_tax * jaccard(tax_a, tax_b)
                + w_cos * cosine_similarity(tfidf_a[0], tfidf_a[1], tfidf_b[0], tfidf_b[1])
            )

            if w_dense > 0 and dense_a and dense_b:
                dense_sim = sum(x * y for x, y in zip(dense_a, dense_b))
                score += w_dense * dense_sim

            if score > SIMILARITY_THRESHOLD:
                edges.append((a, b, score))

    return edges


def run_louvain(
    doc_ids: list[str],
    edges: list[tuple[str, str, float]],
    resolution: float = LOUVAIN_RESOLUTION,
) -> list[set[str]]:
    """Run Louvain community detection on the similarity graph.

    Returns list of communities (each a set of agora_ids).
    """
    G = nx.Graph()
    G.add_nodes_from(doc_ids)
    for a, b, w in edges:
        G.add_edge(a, b, similarity=w)

    communities = nx.community.louvain_communities(
        G, weight="similarity", resolution=resolution, seed=42,
    )
    return [set(c) for c in communities]


def sub_cluster_large_communities(
    communities: list[set[str]],
    G: nx.Graph,
    size_threshold: int = SUBCLUSTERING_SIZE_THRESHOLD,
    sub_resolution: float = SUBCLUSTERING_RESOLUTION,
    max_depth: int = 2,
) -> list[set[str]]:
    """Re-cluster communities that exceed size_threshold using higher resolution.

    Uses the existing graph edges (no signal recomputation).
    Recurses up to max_depth times.
    """
    result: list[set[str]] = []
    for comm in communities:
        if len(comm) <= size_threshold:
            result.append(comm)
            continue

        sub = G.subgraph(comm)
        sub_communities = nx.community.louvain_communities(
            sub, weight="similarity", resolution=sub_resolution, seed=42,
        )
        sub_sets = [set(c) for c in sub_communities]

        log.info(
            "Sub-clustered community of %d docs into %d sub-communities (resolution=%.1f).",
            len(comm), len(sub_sets), sub_resolution,
        )

        if max_depth > 1:
            sub_sets = sub_cluster_large_communities(
                sub_sets, G, size_threshold, sub_resolution * 1.5, max_depth - 1,
            )

        result.extend(sub_sets)

    return result


def compute_doc_centrality(
    community_ids: set[str],
    G: nx.Graph,
) -> dict[str, float]:
    """Compute weighted degree centrality within a community subgraph."""
    sub = G.subgraph(community_ids)
    n = len(community_ids)
    if n <= 1:
        return {nid: 1.0 for nid in community_ids}
    centrality: dict[str, float] = {}
    for node in community_ids:
        weighted_deg = sum(
            sub[node][nbr].get("similarity", 0.0) for nbr in sub.neighbors(node)
        )
        centrality[node] = weighted_deg / (n - 1)
    return centrality


def label_community(
    member_ids: set[str],
    tax_vectors: dict[str, set[str]],
) -> tuple[str, list[str]]:
    """Generate a label and taxonomy signature for a community.

    Returns (label_string, taxonomy_signature_list).
    """
    tag_counts: Counter[str] = Counter()
    for mid in member_ids:
        for tag in tax_vectors.get(mid, set()):
            tag_counts[tag] += 1

    n = len(member_ids)
    # Signature: tags shared by >= 40% of members
    signature = [tag for tag, count in tag_counts.most_common() if count >= 0.4 * n]
    # Label: top-3 tags, shortened
    top3 = [tag for tag, _ in tag_counts.most_common(3)]
    label = " | ".join(top3) if top3 else "General"
    return label, signature


def get_dominant_party(
    member_ids: set[str],
    rows: list[dict[str, Any]],
) -> str:
    """Return the most common party among sponsors in the community."""
    party_counts: Counter[str] = Counter()
    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        party = row.get("Sponsor_Party", "").strip()
        if agora_id in member_ids and party:
            party_counts[party] += 1
    if not party_counts:
        return ""
    return party_counts.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def detect_communities(
    rows: list[dict[str, Any]],
    output_dir: Path | None = None,
    resolution: float = LOUVAIN_RESOLUTION,
) -> list[CommunityRecord]:
    """Run the full community detection pipeline.

    Returns list of CommunityRecord.
    """
    output_dir = output_dir or AGENTS_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Identify taxonomy columns from first row
    if not rows:
        log.warning("No rows to process.")
        return []
    tax_columns = _get_taxonomy_columns(rows[0])
    log.info("Found %d taxonomy columns.", len(tax_columns))

    # Pre-step: bill grouping
    url_to_ids = group_bills_by_url(rows)
    bill_groups = build_bill_groups(url_to_ids)
    log.info(
        "Bill grouping: %d unique URLs, %d multi-section groups.",
        len(url_to_ids),
        len(bill_groups),
    )

    # For community detection, represent each bill group by union of taxonomy tags
    # Use first section as canonical row, but merge tags from all sections
    canonical_rows: list[dict[str, Any]] = []
    group_members: dict[str, list[str]] = {}  # canonical_id -> all ids in group
    seen_urls: set[str] = set()

    for row in rows:
        agora_id = row.get("AGORA ID", "").strip()
        url = row.get("Link to document", "").strip()

        if not agora_id:
            continue

        if url and url in seen_urls:
            # This is a non-canonical member of a multi-section bill
            # Find its group and add to members
            for canonical_id, members in group_members.items():
                for r in canonical_rows:
                    if r.get("AGORA ID") == canonical_id and r.get("Link to document") == url:
                        members.append(agora_id)
                        break
            continue

        if url:
            seen_urls.add(url)

        canonical_rows.append(row)
        group_members[agora_id] = [agora_id]

    # For grouped bills, merge taxonomy tags from all member rows
    agora_id_to_row = {r.get("AGORA ID", "").strip(): r for r in rows}
    for canonical_id, members in group_members.items():
        if len(members) <= 1:
            continue
        canonical_row = agora_id_to_row.get(canonical_id, {})
        for member_id in members[1:]:
            member_row = agora_id_to_row.get(member_id, {})
            for col in tax_columns:
                if member_row.get(col, "").strip() == "True":
                    canonical_row[col] = "True"

    # Compute signals on canonical rows
    canonical_ids = [r.get("AGORA ID", "").strip() for r in canonical_rows]
    tax_vectors = compute_taxonomy_jaccard(canonical_rows, tax_columns)
    tfidf_vectors = compute_summary_tfidf(canonical_rows)
    dense_vectors = compute_summary_dense(canonical_rows)

    log.info("Computing pairwise similarity for %d canonical documents...", len(canonical_ids))

    edges = compute_pairwise_similarity(
        canonical_ids, tax_vectors, tfidf_vectors, dense_vectors,
    )
    log.info("Similarity graph: %d edges above threshold %.2f.", len(edges), SIMILARITY_THRESHOLD)

    # Build the full graph for centrality computation later
    G = nx.Graph()
    G.add_nodes_from(canonical_ids)
    for a, b, w in edges:
        G.add_edge(a, b, similarity=w)

    # Run Louvain (pass 1)
    raw_communities = run_louvain(canonical_ids, edges, resolution=resolution)
    log.info("Louvain pass 1: %d communities.", len(raw_communities))

    # Expand communities: each canonical ID maps back to its full group
    expanded_communities: list[set[str]] = []
    for comm in raw_communities:
        expanded = set()
        for cid in comm:
            expanded.update(group_members.get(cid, [cid]))
        expanded_communities.append(expanded)

    # Pass 2: sub-cluster large communities (check expanded size,
    # but operate on canonical subgraph since that's where edges live)
    final_communities: list[set[str]] = []
    for expanded in expanded_communities:
        if len(expanded) <= SUBCLUSTERING_SIZE_THRESHOLD:
            final_communities.append(expanded)
            continue

        # Get canonical IDs in this community for sub-clustering
        canonical_in = {cid for cid in canonical_ids if cid in expanded
                        or any(m in expanded for m in group_members.get(cid, []))}
        sub_comms = sub_cluster_large_communities([canonical_in], G)
        log.info(
            "Sub-clustered community of %d expanded docs (%d canonical) into %d sub-communities.",
            len(expanded), len(canonical_in), len(sub_comms),
        )

        # Re-expand each sub-community
        for sub_comm in sub_comms:
            sub_expanded = set()
            for cid in sub_comm:
                sub_expanded.update(group_members.get(cid, [cid]))
            final_communities.append(sub_expanded)

    expanded_communities = final_communities
    log.info("After sub-clustering: %d communities.", len(expanded_communities))

    # Build CommunityRecord for each community
    # Also compute taxonomy vectors for ALL rows (not just canonical) for labeling
    all_tax_vectors = compute_taxonomy_jaccard(rows, tax_columns)

    records: list[CommunityRecord] = []
    for idx, members in enumerate(sorted(expanded_communities, key=len, reverse=True)):
        community_id = f"community:{idx + 1:03d}"

        label, signature = label_community(members, all_tax_vectors)
        dominant_party = get_dominant_party(members, rows)

        # Centrality: use canonical IDs that belong to this community
        canonical_in_comm = {
            cid for cid in canonical_ids if cid in members
            or any(m in members for m in group_members.get(cid, []))
        }
        centrality_canonical = compute_doc_centrality(canonical_in_comm, G)

        # Expand centrality to all member docs (inherit from canonical)
        centrality_all: dict[str, float] = {}
        for cid, score in centrality_canonical.items():
            for member in group_members.get(cid, [cid]):
                centrality_all[member] = score

        # Bill groups within this community
        comm_bill_groups = [
            group for cid, group in group_members.items()
            if cid in canonical_in_comm and len(group) > 1
        ]

        record = CommunityRecord(
            community_id=community_id,
            label=label,
            taxonomy_signature=signature,
            dominant_party=dominant_party,
            member_agora_ids=sorted(members),
            bill_groups=comm_bill_groups,
            doc_centrality={k: round(v, 4) for k, v in centrality_all.items()},
        )
        records.append(record)

    # Write output
    output_path = output_dir / "communities.json"
    output_path.write_text(
        json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    log.info("Communities written to %s", output_path)

    return records


def inspect_communities(records: list[CommunityRecord]) -> str:
    """Generate a human-readable summary table for community quality inspection."""
    lines = [
        f"{'Community':<16} {'Size':>5}  {'Dominant':>8}  {'Top Tags'}",
        "-" * 80,
    ]
    singletons = 0
    for r in records:
        if len(r.member_agora_ids) == 1:
            singletons += 1
            continue
        top_tags = r.label[:60] if r.label else "(no tags)"
        lines.append(
            f"{r.community_id:<16} {len(r.member_agora_ids):>5}  "
            f"{r.dominant_party:>8}  {top_tags}"
        )
    lines.append(f"\nSingletons: {singletons}")
    lines.append(f"Total communities (size > 1): {len(records) - singletons}")
    return "\n".join(lines)


def run(
    csv_path: Path,
    output_dir: Path | None = None,
    resolution: float = LOUVAIN_RESOLUTION,
    inspect: bool = False,
) -> list[CommunityRecord]:
    """Entry point: load CSV, detect communities, optionally inspect."""
    rows = load_docs_csv(csv_path)
    records = detect_communities(rows, output_dir, resolution)
    if inspect:
        print(inspect_communities(records))
    return records
