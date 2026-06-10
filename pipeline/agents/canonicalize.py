"""Post-processing: canonicalize bare aliases in entities.jsonl.

Uses disambiguation rules collected at doc-level and community-level
to resolve bare aliases ("Secretary", "Director", etc.) to their
canonical forms. No LLM calls — purely deterministic string matching.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pipeline.agents.canonical_registry import GlobalCanonicalRegistry
from pipeline.config import (
    AGENTS_OUTPUT_DIR,
    COMMUNITIES_PATH,
    GLOBAL_REGISTRY_PATH,
    MEMORY_DIR,
    REVIEW_QUEUE_PATH,
)
from pipeline.models import read_jsonl, utc_now_iso

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known bare alias terms
# ---------------------------------------------------------------------------

BARE_TERMS: frozenset[str] = frozenset({
    "secretary", "director", "chair", "chairman", "chairwoman",
    "speaker", "senator", "administrator", "commission", "committee",
    "department", "agency", "council", "board", "house",
    "officer", "bureau", "center", "office", "judge",
    "sponsor", "chief", "cochair", "partner", "agent",
    "the secretary", "the director", "the administrator",
    "the commission", "the department", "the committee",
    "the council", "the board", "the agency",
    "under secretary", "assistant secretary",
})

# Entity name field per type
NAME_FIELD: dict[str, str] = {
    "organizations": "name",
    "offices": "name",
    "roles": "title",
    "legislation_refs": "name",
    "named_docs": "name",
}

# ---------------------------------------------------------------------------
# Regex patterns for extracting canonical names from LLM descriptions
# ---------------------------------------------------------------------------

# Preamble prefixes to strip (order matters — longest first)
_PREAMBLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^Explicitly\s+defined\s+as\s+", re.IGNORECASE),
    re.compile(r"^Extracted\s+in\s+context\s+of\s+", re.IGNORECASE),
    re.compile(r"^Resolved\s+to\s+", re.IGNORECASE),
    re.compile(r"^Confirmed\s+as\s+", re.IGNORECASE),
    re.compile(r"^Identified\s+as\s+", re.IGNORECASE),
    re.compile(r"^Refers\s+to\s+(the\s+)?", re.IGNORECASE),
]

# Truncation boundaries — split and keep only the part before
_TRUNCATION_PATTERNS: list[str] = [
    " per SEC", " per Section", " per subsection", " per document",
    " per context", " per explicit", " per (",
    " in SEC.", " in context of", " in this section",
    " inferred from", " based on context", " based on jurisdiction",
    " as the ", " as established", " as explicitly",
    " (context-dependent)", " (standard ", " (distinct from",
    " (established ", " (defined ", " (per ",
    " (inferred ", " (consistent ",
    " — ", " – ", " - confirmed", " - inferred",
    "; ", " already established",
    ", appointed by", ", acting through",
    " with specific authorit", " responsible for",
    " under the ", " under this ",
]

# Noise pattern: "(used N times in text)" etc.
_NOISE_PAREN = re.compile(r"\s*\(used\s+\d+\s+times.*?\)\s*$", re.IGNORECASE)

# "refers to" pattern: extract the part after "refers to"
_REFERS_TO = re.compile(
    r".*?[''\"].*?[''\"].*?\brefers\s+to\s+(.+)",
    re.IGNORECASE,
)

# Ambiguity: "X or Y" between two capitalized phrases
_AMBIGUOUS = re.compile(r"[A-Z][a-z]+(?:\s+[A-Za-z]+)*\s+or\s+[A-Z][a-z]+")


def extract_canonical_name(description: str) -> str | None:
    """Extract a clean canonical entity name from a messy LLM disambiguation description.

    Returns None if the description is ambiguous or extraction fails.
    """
    if not description or not description.strip():
        return None

    text = description.strip()

    # Skip non-entity descriptions (meta-notes, not actual resolutions)
    skip_phrases = [
        "not referenced",
        "already established",
        "defined in subsection",
        "defined in sec",
    ]
    text_lower = text.lower()
    if any(text_lower.startswith(p) for p in skip_phrases):
        return None

    # Try "refers to" pattern first: "In SEC. X, 'Y' refers to Z"
    m = _REFERS_TO.match(text)
    if m:
        text = m.group(1).strip()
    else:
        # Strip preamble
        for pat in _PREAMBLE_PATTERNS:
            text = pat.sub("", text, count=1)

    # Strip leading quotes
    text = re.sub(r"^['\"\u2018\u2019\u201c\u201d]+", "", text)

    # Truncate at noise boundaries
    for boundary in _TRUNCATION_PATTERNS:
        idx = text.lower().find(boundary.lower())
        if idx > 0:
            text = text[:idx]

    # Strip noise parentheticals
    text = _NOISE_PAREN.sub("", text)

    # Strip trailing quotes, commas, periods, dashes
    text = re.sub(r"['\"\u2018\u2019\u201c\u201d,.\-\s]+$", "", text)
    text = text.strip()

    if not text:
        return None

    # Check for ambiguity
    if _AMBIGUOUS.search(text):
        return None

    # Validation: must be at least 4 chars and contain an uppercase letter
    if len(text) < 4:
        return None
    if not any(c.isupper() for c in text):
        return None

    # Reject descriptions that don't look like entity names
    # Entity names typically start with a capital letter or "the"
    description_starts = [
        "enforcement", "authority", "role ", "refers ", "confirmed ",
        "explicitly ", "identified ", "not ", "received ", "receives ",
    ]
    if any(text.lower().startswith(p) for p in description_starts):
        return None

    return text


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def build_agora_to_community(communities_path: Path) -> dict[str, str]:
    """Build {agora_id: community_id} mapping from communities.json."""
    if not communities_path.exists():
        log.warning("No communities file at %s", communities_path)
        return {}
    data = json.loads(communities_path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for comm in data:
        cid = comm.get("community_id", "")
        for aid in comm.get("member_agora_ids", []):
            mapping[str(aid)] = cid
    log.info("Loaded agora→community mapping: %d docs across %d communities", len(mapping), len(data))
    return mapping


def load_community_disambiguations(memory_dir: Path) -> dict[str, dict[str, str]]:
    """Load disambiguation rules from all community memory files.

    Returns {community_id: {lowercase_phrase: description}}.
    Filters out internal keys (containing '_in_sec_', '_in_SEC_').
    """
    result: dict[str, dict[str, str]] = {}
    if not memory_dir.exists():
        return result
    for f in memory_dir.glob("*_memory.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cid = data.get("community_id", f.stem.replace("_memory", ""))
        rules = data.get("disambiguation_rules", {})
        # Filter internal keys
        filtered = {
            k: v for k, v in rules.items()
            if "_in_sec_" not in k and "_in_SEC_" not in k
        }
        if filtered:
            result[cid] = filtered
    log.info("Loaded community disambiguations: %d communities, %d total rules",
             len(result), sum(len(v) for v in result.values()))
    return result


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------

def is_bare_alias(name: str, doc_disambig_keys: set[str] | None = None) -> bool:
    """Check if an entity name is a bare alias that needs resolution."""
    lower = name.lower().strip()
    if lower in BARE_TERMS:
        return True
    # Single word, not an acronym (all-caps short strings are acronyms, keep them)
    if " " not in name.strip() and not name.isupper() and len(name) <= 15:
        if lower in (doc_disambig_keys or set()):
            return True
    # Also match "the X" patterns in doc disambiguations
    if doc_disambig_keys and lower in doc_disambig_keys:
        return True
    return False


def resolve_entity(
    bare_name: str,
    entity_type: str,
    doc_disambig: dict[str, str],
    community_disambig: dict[str, str],
    registry: GlobalCanonicalRegistry,
) -> tuple[str | None, str]:
    """Resolve a bare alias using the three-tier cascade.

    Returns (canonical_name, source) or (None, "unresolved").
    """
    key = bare_name.lower().strip()

    # Tier 1: doc-level disambiguation
    for dk, dv in doc_disambig.items():
        if dk.lower().strip() == key:
            canonical = extract_canonical_name(dv)
            if canonical and canonical.lower() != key:
                return canonical, "doc"
            break

    # Tier 2: community-level disambiguation
    if community_disambig:
        for ck, cv in community_disambig.items():
            if ck.lower().strip() == key:
                canonical = extract_canonical_name(cv)
                if canonical and canonical.lower() != key:
                    return canonical, "community"
                break

    # Tier 3: global registry
    entity = registry.resolve(bare_name, entity_type=entity_type)
    if entity and entity.canonical_name.lower() != key:
        return entity.canonical_name, "registry"

    return None, "unresolved"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    entities_path: Path | None = None,
    communities_path: Path | None = None,
    memory_dir: Path | None = None,
    registry_path: Path | None = None,
    review_queue_path: Path | None = None,
) -> dict[str, Any]:
    """Flag bare aliases in the review queue with resolution context for human review.

    Does NOT modify entities.jsonl. Replaces review_queue.jsonl with enriched
    entries containing suggested canonical names, disambiguation source, and
    community context.

    Returns stats dict.
    """
    entities_path = entities_path or (AGENTS_OUTPUT_DIR / "entities.jsonl")
    communities_path = communities_path or COMMUNITIES_PATH
    memory_dir = memory_dir or MEMORY_DIR
    registry_path = registry_path or GLOBAL_REGISTRY_PATH
    review_queue_path = review_queue_path or REVIEW_QUEUE_PATH

    # Load data
    registry = GlobalCanonicalRegistry.load(registry_path)
    agora_to_community = build_agora_to_community(communities_path)
    community_disambig = load_community_disambiguations(memory_dir)

    stats: dict[str, Any] = {
        "total_entities": 0,
        "bare_aliases_found": 0,
        "with_suggestion": 0,
        "unresolved": 0,
        "by_source": {"doc": 0, "community": 0, "registry": 0},
        "by_type": {},
    }
    review_entries: list[dict[str, Any]] = []
    ts = utc_now_iso()

    # Process each document
    rows = list(read_jsonl(entities_path))
    for row in rows:
        agora_id = str(row.get("agora_id", ""))
        doc_disambig = row.get("disambiguation_updates", {})
        doc_disambig_keys = {k.lower().strip() for k in doc_disambig}

        community_id = agora_to_community.get(agora_id, "")
        comm_disambig = community_disambig.get(community_id, {})

        for entity_type, name_field in NAME_FIELD.items():
            for entity in row.get(entity_type, []):
                stats["total_entities"] += 1
                name = entity.get(name_field, "")
                if not name:
                    continue

                if not is_bare_alias(name, doc_disambig_keys):
                    continue

                stats["bare_aliases_found"] += 1
                canonical, source = resolve_entity(
                    name, entity_type, doc_disambig, comm_disambig, registry,
                )

                # Build the review entry with full context
                entry: dict[str, Any] = {
                    "agora_id": agora_id,
                    "entity_name": name,
                    "entity_type": entity_type,
                    "community_id": community_id,
                    "entity_context": entity.get("context", ""),
                    "reason": "bare_alias",
                    "ts": ts,
                }

                # Add the raw disambiguation rule that produced the suggestion
                key_lower = name.lower().strip()
                if key_lower in {k.lower().strip() for k in doc_disambig}:
                    for dk, dv in doc_disambig.items():
                        if dk.lower().strip() == key_lower:
                            entry["doc_disambiguation_rule"] = dv
                            break
                if key_lower in {k.lower().strip() for k in comm_disambig}:
                    for ck, cv in comm_disambig.items():
                        if ck.lower().strip() == key_lower:
                            entry["community_disambiguation_rule"] = cv
                            break

                if canonical:
                    entry["suggested_canonical"] = canonical
                    entry["suggestion_source"] = source
                    stats["with_suggestion"] += 1
                    stats["by_source"][source] += 1
                else:
                    entry["suggested_canonical"] = None
                    entry["suggestion_source"] = "unresolved"
                    stats["unresolved"] += 1

                stats["by_type"][entity_type] = stats["by_type"].get(entity_type, 0) + 1
                review_entries.append(entry)

    # Write review queue atomically
    review_queue_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(review_queue_path.parent), suffix=".jsonl.tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            for entry in review_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp_path, str(review_queue_path))
    except Exception:
        os.unlink(tmp_path)
        raise

    stats["review_queue_entries"] = len(review_entries)
    log.info("Wrote %d review entries to %s", len(review_entries), review_queue_path)

    return stats
