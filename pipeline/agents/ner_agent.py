"""Phase 3: Community-aware NER agent with memory.

Processes documents per-community in centrality order.
Uses LLM (claude-haiku-4-5) for entity extraction.
Memory accumulates across documents within each community.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pipeline.config import (
    AGENTS_CHECKPOINT_DIR,
    AGENTS_OUTPUT_DIR,
    ANTHROPIC_MODEL_BULK,
    MEMORY_DIR,
    NER_CHUNK_SIZE,
    NER_MAX_PARSING_RULES,
    NER_MEMORY_TOP_N,
)
from pipeline.agents.llm_client import call_claude_json
from pipeline.agents.models_agent import CommunityMemory, CommunityRecord, EntityRecord
from pipeline.models import append_jsonl, read_jsonl, utc_now_iso

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical org lookup for is_new matching
# ---------------------------------------------------------------------------

CANONICAL_ORGS: dict[str, str] = {
    "dod": "Department of Defense",
    "dept. of defense": "Department of Defense",
    "nist": "National Institute of Standards and Technology",
    "nsf": "National Science Foundation",
    "darpa": "Defense Advanced Research Projects Agency",
    "fema": "Federal Emergency Management Agency",
    "nasa": "National Aeronautics and Space Administration",
    "noaa": "National Oceanic and Atmospheric Administration",
    "jaic": "Joint Artificial Intelligence Center",
    "ostp": "Office of Science and Technology Policy",
    "omb": "Office of Management and Budget",
    "faa": "Federal Aviation Administration",
    "dhs": "Department of Homeland Security",
    "ftc": "Federal Trade Commission",
    "doj": "Department of Justice",
    "hhs": "Department of Health and Human Services",
}

# ---------------------------------------------------------------------------
# Generic term filter
# ---------------------------------------------------------------------------

GENERIC_STEMS = frozenset({
    "federal agencies", "relevant stakeholders", "program agencies",
    "appropriate entities", "the committee", "the program",
})


def is_generic(name: str, resolved_phrases: set[str]) -> bool:
    normalized = name.lower().strip()
    if normalized in resolved_phrases:
        return False
    if normalized in GENERIC_STEMS:
        return True
    if len(normalized) < 5:
        return True
    return False


# ---------------------------------------------------------------------------
# Section-boundary chunking
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(
    r"^\s*(SEC(?:TION)?\.?\s+\d+[A-Z]?\.)", re.MULTILINE | re.IGNORECASE
)
SUBSECTION_RE = re.compile(r"^\s*\([a-z]\)", re.MULTILINE)


def chunk_text(text: str, max_chunk: int = NER_CHUNK_SIZE) -> list[str]:
    """Split text at section boundaries, falling back to subsection then char limit."""
    if not text or len(text) <= max_chunk:
        return [text] if text else []

    # Find section boundaries
    splits = [m.start() for m in SECTION_RE.finditer(text)]

    if not splits:
        # No section headers — single chunk (truncate if needed) or split by subsection
        return _split_by_size(text, max_chunk)

    # Ensure we start from 0
    if splits[0] != 0:
        splits.insert(0, 0)

    chunks: list[str] = []
    for i in range(len(splits)):
        start = splits[i]
        end = splits[i + 1] if i + 1 < len(splits) else len(text)
        section = text[start:end].strip()
        if not section:
            continue
        if len(section) <= max_chunk:
            chunks.append(section)
        else:
            # Split large section by subsection boundaries
            chunks.extend(_split_by_size(section, max_chunk))

    return [c for c in chunks if c.strip()]


def _split_by_size(text: str, max_chunk: int) -> list[str]:
    """Split by subsection boundaries, then hard char limit."""
    sub_splits = [m.start() for m in SUBSECTION_RE.finditer(text)]

    if sub_splits and sub_splits[0] != 0:
        sub_splits.insert(0, 0)

    if len(sub_splits) < 2:
        # No subsection structure — hard split
        parts = []
        for i in range(0, len(text), max_chunk):
            parts.append(text[i : i + max_chunk].strip())
        return [p for p in parts if p]

    chunks: list[str] = []
    current = ""
    for i in range(len(sub_splits)):
        start = sub_splits[i]
        end = sub_splits[i + 1] if i + 1 < len(sub_splits) else len(text)
        segment = text[start:end]
        if len(current) + len(segment) > max_chunk and current:
            chunks.append(current.strip())
            current = segment
        else:
            current += segment
    if current.strip():
        chunks.append(current.strip())

    return chunks


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a named entity extractor for U.S. federal legislative documents.
You have access to a community memory of entities already found in related documents.
Rules:
1. Return ONLY valid JSON. No prose, no markdown fences.
2. Use the community context to resolve ambiguous references ("the Department", "the Director").
3. Only extract explicitly named entities — skip generic terms like "federal agencies".
4. Add disambiguation_updates ONLY for phrases you resolved using this document's text.
5. Prefer full canonical names; put acronyms in the acronym field.
6. For roles: always include the associated agency.
7. Return empty lists for types with no entities found.
8. If you observe a new structural pattern, include it in new_parsing_rule.
9. If the document has unusual structure, describe it in oddity."""


def _build_memory_context(memory: CommunityMemory) -> str:
    """Build the community context prefix from memory, with pruning."""
    parts = [f'COMMUNITY CONTEXT: This document belongs to the "{memory.label}" legislative cluster.\n']

    # Entity roster (pruned to top-N by mentions)
    roster_lines: list[str] = []
    for entity_type, top_n in NER_MEMORY_TOP_N.items():
        entries = memory.entity_roster.get(entity_type, [])
        if not entries:
            continue
        sorted_entries = sorted(entries, key=lambda e: e.get("mentions", 0), reverse=True)[:top_n]
        names = []
        for e in sorted_entries:
            name = e.get("name") or e.get("title", "")
            acronym = e.get("acronym")
            if acronym:
                names.append(f"{name} ({acronym})")
            else:
                names.append(name)
        if names:
            label = entity_type.replace("_", " ").title()
            roster_lines.append(f"- {label}: {', '.join(names)}")

    if roster_lines:
        parts.append("Known entities from previous documents in this cluster:")
        parts.extend(roster_lines)

    # Disambiguation rules
    if memory.disambiguation_rules:
        rules = [f'"{k}" = {v}' for k, v in memory.disambiguation_rules.items()]
        parts.append(f"\nDisambiguation rules: {'; '.join(rules)}")

    # Parsing rules (capped)
    active_rules = memory.parsing_rules[:NER_MAX_PARSING_RULES]
    if active_rules:
        parts.append("\nParsing patterns observed in this cluster:")
        for rule in active_rules:
            parts.append(f"- {rule}")

    # Oddities (last 3)
    recent_oddities = memory.oddities[-3:] if memory.oddities else []
    if recent_oddities:
        parts.append("\nWatch out for (known oddities):")
        for o in recent_oddities:
            parts.append(f"- {o.get('note', '')}")

    parts.append("\nNew entities not already listed above are especially valuable — extract them carefully.")
    parts.append("If you observe a new structural pattern, include it in new_parsing_rule.")
    parts.append("If this document has unusual structure, describe it in oddity.")

    return "\n".join(parts)


def _build_user_prompt(
    official_name: str,
    short_summary: str,
    text_chunk: str,
    in_progress_entities: list[str] | None = None,
) -> str:
    """Build the user prompt for a single chunk."""
    parts = [f"Document title: {official_name}"]
    if short_summary:
        parts.append(f"Summary: {short_summary}")

    if in_progress_entities:
        parts.append(f"\nEntities already extracted from earlier sections of this document: {', '.join(in_progress_entities)}")

    parts.append(f"\nText:\n{text_chunk}")

    parts.append("""
Extract entities and return JSON with exactly this schema:
{
  "organizations": [{"name": "...", "acronym": "...", "context": "verbatim phrase ≤100 chars"}],
  "offices": [{"name": "...", "parent_org": "...", "context": "..."}],
  "roles": [{"title": "...", "org": "...", "context": "..."}],
  "legislation_refs": [{"name": "...", "citation": "...", "ref_type": "cites|amends|enacts|repeals|other", "context": "..."}],
  "named_docs": [{"name": "...", "doc_type": "strategy|report|plan|initiative|program|other", "owner_org": "...", "context": "..."}],
  "disambiguation_updates": {},
  "new_parsing_rule": null,
  "oddity": null
}""")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# NER output validation
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {"organizations", "offices", "roles", "legislation_refs", "named_docs"}


def validate_ner_output(data: dict[str, Any]) -> bool:
    """Check that the NER output has required keys and list values."""
    if not REQUIRED_KEYS.issubset(data.keys()):
        return False
    for key in REQUIRED_KEYS:
        if not isinstance(data[key], list):
            return False
    return True


# ---------------------------------------------------------------------------
# is_new computation
# ---------------------------------------------------------------------------

def compute_is_new(entity_name: str, entity_type: str, memory: CommunityMemory) -> bool:
    """Determine if entity is new to the community memory."""
    roster = memory.entity_roster.get(entity_type, [])
    name_lower = entity_name.lower().strip()
    for existing in roster:
        existing_name = (existing.get("name") or existing.get("title", "")).lower().strip()
        if existing_name == name_lower:
            return False
        canonical = CANONICAL_ORGS.get(name_lower)
        if canonical and canonical.lower() == existing_name:
            return False
    return True


# ---------------------------------------------------------------------------
# Merge chunk results
# ---------------------------------------------------------------------------

def _get_entity_name(entity: dict, entity_type: str) -> str:
    if entity_type == "roles":
        return entity.get("title", "")
    return entity.get("name", "")


def merge_chunk_results(chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge entity lists from multiple chunks, deduplicating by name."""
    merged: dict[str, list[dict]] = {k: [] for k in REQUIRED_KEYS}
    seen: dict[str, set[str]] = {k: set() for k in REQUIRED_KEYS}
    disambiguation_updates: dict[str, str] = {}
    parsing_rules: list[str] = []
    oddities: list[str] = []

    for result in chunk_results:
        for entity_type in REQUIRED_KEYS:
            for entity in result.get(entity_type, []):
                name = _get_entity_name(entity, entity_type).lower().strip()
                if name and name not in seen[entity_type]:
                    seen[entity_type].add(name)
                    merged[entity_type].append(entity)

        # Merge disambiguation (first wins)
        for k, v in result.get("disambiguation_updates", {}).items():
            if k not in disambiguation_updates:
                disambiguation_updates[k] = v

        rule = result.get("new_parsing_rule")
        if rule:
            parsing_rules.append(rule)

        oddity = result.get("oddity")
        if oddity:
            oddities.append(oddity)

    return {
        **merged,
        "disambiguation_updates": disambiguation_updates,
        "new_parsing_rule": parsing_rules[0] if parsing_rules else None,
        "oddity": oddities[0] if oddities else None,
    }


# ---------------------------------------------------------------------------
# Memory persistence
# ---------------------------------------------------------------------------

def load_memory(community_id: str, memory_dir: Path | None = None) -> CommunityMemory:
    memory_dir = memory_dir or MEMORY_DIR
    path = memory_dir / f"{community_id}_memory.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return CommunityMemory.from_dict(data)
    return CommunityMemory(community_id=community_id)


def save_memory(memory: CommunityMemory, memory_dir: Path | None = None) -> None:
    memory_dir = memory_dir or MEMORY_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / f"{memory.community_id}_memory.json"
    path.write_text(
        json.dumps(memory.to_dict(), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Checkpoint management
# ---------------------------------------------------------------------------

def load_checkpoint(checkpoint_dir: Path | None = None) -> set[str]:
    """Load set of agora_ids already processed."""
    checkpoint_dir = checkpoint_dir or AGENTS_CHECKPOINT_DIR
    path = checkpoint_dir / "ner_checkpoint.jsonl"
    done = set()
    for row in read_jsonl(path):
        if row.get("status") in ("done", "failed"):
            done.add(row["agora_id"])
    return done


def save_checkpoint(
    agora_id: str,
    status: str,
    checkpoint_dir: Path | None = None,
    **extra: Any,
) -> None:
    checkpoint_dir = checkpoint_dir or AGENTS_CHECKPOINT_DIR
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    row = {"agora_id": agora_id, "status": status, "ts": utc_now_iso(), **extra}
    append_jsonl(checkpoint_dir / "ner_checkpoint.jsonl", [row])


# ---------------------------------------------------------------------------
# Process a single document
# ---------------------------------------------------------------------------

def process_document(
    agora_id: str,
    official_name: str,
    short_summary: str,
    fulltext: str,
    memory: CommunityMemory,
    model: str = ANTHROPIC_MODEL_BULK,
) -> EntityRecord | None:
    """Run NER on a single document using community memory.

    Returns EntityRecord on success, None on failure.
    """
    chunks = chunk_text(fulltext)
    if not chunks:
        log.warning("No text to process for doc %s", agora_id)
        return None

    chunk_results: list[dict[str, Any]] = []
    in_progress_entities: list[str] = []
    total_pt = 0
    total_ct = 0

    memory_context = _build_memory_context(memory)

    for i, chunk in enumerate(chunks):
        user_prompt = _build_user_prompt(
            official_name, short_summary, chunk,
            in_progress_entities if i > 0 else None,
        )
        full_system = SYSTEM_PROMPT + "\n\n" + memory_context

        parsed, pt, ct = call_claude_json(
            full_system, user_prompt, model=model, max_tokens=2048,
        )
        total_pt += pt
        total_ct += ct

        if parsed is None or not validate_ner_output(parsed):
            log.warning("Invalid NER output for doc %s chunk %d, skipping chunk.", agora_id, i)
            continue

        # Filter generic terms
        resolved = set(memory.disambiguation_rules.keys())
        for entity_type in REQUIRED_KEYS:
            parsed[entity_type] = [
                e for e in parsed[entity_type]
                if not is_generic(_get_entity_name(e, entity_type), resolved)
            ]

        chunk_results.append(parsed)

        # Build in-progress entity names for next chunk
        for entity_type in REQUIRED_KEYS:
            for e in parsed[entity_type]:
                name = _get_entity_name(e, entity_type)
                if name and name not in in_progress_entities:
                    in_progress_entities.append(name)

    if not chunk_results:
        log.warning("All chunks failed for doc %s", agora_id)
        return None

    # Merge all chunks
    merged = merge_chunk_results(chunk_results)

    record = EntityRecord(
        agora_id=agora_id,
        organizations=merged["organizations"],
        offices=merged["offices"],
        roles=merged["roles"],
        legislation_refs=merged["legislation_refs"],
        named_docs=merged["named_docs"],
        disambiguation_updates=merged.get("disambiguation_updates", {}),
        new_parsing_rule=merged.get("new_parsing_rule"),
        oddity=merged.get("oddity"),
        model=model,
        prompt_tokens=total_pt,
        completion_tokens=total_ct,
        chunks_processed=len(chunk_results),
        extracted_at=utc_now_iso(),
    )
    return record


# ---------------------------------------------------------------------------
# Update memory after processing a document
# ---------------------------------------------------------------------------

def update_memory(memory: CommunityMemory, record: EntityRecord) -> None:
    """Update community memory with entities from a processed document."""
    memory.last_doc_id = record.agora_id
    memory.docs_processed += 1

    entity_type_map = {
        "organizations": "organizations",
        "offices": "offices",
        "roles": "roles",
        "legislation_refs": "legislation_refs",
        "named_docs": "named_docs",
    }

    for field_name, type_key in entity_type_map.items():
        for entity in getattr(record, field_name, []):
            name = _get_entity_name(entity, field_name)
            if not name:
                continue
            new = compute_is_new(name, type_key, memory)
            memory.merge_entity(type_key, name, entity, new)

    # Disambiguation
    for phrase, resolved in record.disambiguation_updates.items():
        memory.add_disambiguation(phrase, resolved)

    # Parsing rule
    if record.new_parsing_rule:
        memory.add_parsing_rule(record.new_parsing_rule, NER_MAX_PARSING_RULES)

    # Oddity
    if record.oddity:
        memory.add_oddity(record.agora_id, record.oddity)


# ---------------------------------------------------------------------------
# Run NER for a community
# ---------------------------------------------------------------------------

def run_community(
    community: CommunityRecord,
    doc_metadata: dict[str, dict[str, str]],
    fulltext_dir: Path,
    output_dir: Path | None = None,
    memory_dir: Path | None = None,
    checkpoint_dir: Path | None = None,
    model: str = ANTHROPIC_MODEL_BULK,
    limit: int | None = None,
) -> dict[str, Any]:
    """Process all documents in a community in centrality order.

    Args:
        community: CommunityRecord with member_agora_ids and doc_centrality.
        doc_metadata: {agora_id: {official_name, short_summary, ...}}
        fulltext_dir: directory containing {agora_id}.txt files.
        limit: if set, process only this many docs (for calibration).

    Returns stats dict.
    """
    output_dir = output_dir or AGENTS_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    done_ids = load_checkpoint(checkpoint_dir)
    memory = load_memory(community.community_id, memory_dir)
    memory.label = community.label
    memory.taxonomy_signature = community.taxonomy_signature
    memory.docs_total = len(community.member_agora_ids)

    # Sort by centrality descending
    ordered_ids = sorted(
        community.member_agora_ids,
        key=lambda aid: community.doc_centrality.get(aid, 0.0),
        reverse=True,
    )

    if limit:
        ordered_ids = ordered_ids[:limit]

    processed = 0
    failed = 0
    entities_path = output_dir / "entities.jsonl"
    errors_path = output_dir / "ner_errors.jsonl"

    for agora_id in ordered_ids:
        if agora_id in done_ids:
            continue

        meta = doc_metadata.get(agora_id, {})
        official_name = meta.get("official_name", meta.get("Official name", ""))
        short_summary = meta.get("short_summary", meta.get("Short summary", ""))

        # Load fulltext
        txt_path = fulltext_dir / f"{agora_id}.txt"
        if not txt_path.exists():
            log.warning("No fulltext for doc %s, skipping.", agora_id)
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason="no_fulltext")
            failed += 1
            continue

        fulltext = txt_path.read_text(encoding="utf-8", errors="replace")
        if not fulltext.strip():
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason="empty_fulltext")
            failed += 1
            continue

        try:
            record = process_document(
                agora_id, official_name, short_summary, fulltext, memory, model,
            )
        except Exception as exc:
            log.error("NER failed for doc %s: %s", agora_id, exc)
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason=str(exc))
            append_jsonl(errors_path, [{"agora_id": agora_id, "error": str(exc), "ts": utc_now_iso()}])
            failed += 1
            continue

        if record is None:
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason="no_output")
            failed += 1
            continue

        # Save output
        append_jsonl(entities_path, [record.to_dict()])
        save_checkpoint(agora_id, "done", checkpoint_dir, chunks=record.chunks_processed)

        # Update memory
        update_memory(memory, record)
        save_memory(memory, memory_dir)

        processed += 1
        if processed % 10 == 0:
            log.info(
                "Community %s: %d/%d processed, memory has %d orgs.",
                community.community_id,
                processed,
                len(ordered_ids),
                len(memory.entity_roster.get("organizations", [])),
            )

    stats = {
        "community_id": community.community_id,
        "docs_total": len(ordered_ids),
        "docs_processed": processed,
        "docs_failed": failed,
        "docs_skipped": len(ordered_ids) - processed - failed,
        "memory_orgs": len(memory.entity_roster.get("organizations", [])),
        "memory_rules": len(memory.parsing_rules),
    }
    log.info("Community %s complete: %s", community.community_id, stats)
    return stats


# ---------------------------------------------------------------------------
# Run NER across all communities
# ---------------------------------------------------------------------------

def run(
    communities: list[CommunityRecord],
    doc_metadata: dict[str, dict[str, str]],
    fulltext_dir: Path,
    output_dir: Path | None = None,
    memory_dir: Path | None = None,
    checkpoint_dir: Path | None = None,
    model: str = ANTHROPIC_MODEL_BULK,
    community_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Run NER for all (or filtered) communities.

    Args:
        community_filter: if set, only process this community_id.
        limit: if set, process only this many docs per community.
    """
    all_stats: list[dict[str, Any]] = []

    for community in communities:
        if community_filter and community.community_id != community_filter:
            continue

        log.info(
            "Starting NER for community %s (%d docs)",
            community.community_id,
            len(community.member_agora_ids),
        )

        stats = run_community(
            community, doc_metadata, fulltext_dir,
            output_dir, memory_dir, checkpoint_dir, model, limit,
        )
        all_stats.append(stats)

    return all_stats


# ---------------------------------------------------------------------------
# Coverage report generation
# ---------------------------------------------------------------------------

def generate_coverage_report(
    output_dir: Path | None = None,
    communities: list[CommunityRecord] | None = None,
) -> dict[str, Any]:
    """Generate NER coverage report from entities.jsonl output."""
    output_dir = output_dir or AGENTS_OUTPUT_DIR
    entities = read_jsonl(output_dir / "entities.jsonl")

    entity_types = ["organizations", "offices", "roles", "legislation_refs", "named_docs"]
    global_counts: dict[str, dict[str, Any]] = {}
    total_pt = 0
    total_ct = 0

    for et in entity_types:
        all_names: set[str] = set()
        total_mentions = 0
        docs_with = 0
        for rec in entities:
            items = rec.get(et, [])
            if items:
                docs_with += 1
            for item in items:
                name = item.get("name") or item.get("title", "")
                if name:
                    all_names.add(name.lower().strip())
                    total_mentions += 1
        global_counts[et] = {
            "unique": len(all_names),
            "total_mentions": total_mentions,
            "docs_with": docs_with,
        }

    for rec in entities:
        total_pt += rec.get("prompt_tokens", 0)
        total_ct += rec.get("completion_tokens", 0)

    report = {
        "total_docs_extracted": len(entities),
        "global_entity_counts": global_counts,
        "token_usage": {"prompt": total_pt, "completion": total_ct},
    }

    report_path = output_dir / "ner_coverage_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    log.info("Coverage report written to %s", report_path)
    return report
