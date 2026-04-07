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
    CANONICAL_ENTITY_MAP_PATH,
    CONFIDENCE_REVIEW_THRESHOLD,
    CONTEXT_BUDGET_CHARS,
    ENTITY_DICTIONARY_PATH,
    GLOBAL_REGISTRY_PATH,
    GRADUATION_THRESHOLD,
    MANUAL_ANNOTATIONS_DIR,
    MEMORY_DIR,
    NER_CHUNK_SIZE,
    NER_MAX_PARSING_RULES,
    NER_MEMORY_TOP_N,
    REVIEW_QUEUE_PATH,
    TYPE_AUTHORITY_PATH,
)
from pipeline.agents.llm_client import call_claude_json
from pipeline.agents.models_agent import CommunityMemory, CommunityRecord, EntityRecord
from pipeline.agents.canonical_registry import (
    GlobalCanonicalRegistry,
    seed_registry,
    make_entity_id,
)
from pipeline.models import append_jsonl, read_jsonl, utc_now_iso

log = logging.getLogger(__name__)


def _read_fulltext(agora_id: str, fulltext_dir: Path) -> str | None:
    """Read fulltext for agora_id from Supabase Storage or local file.

    Returns the text string, or None if not found anywhere.
    """
    from pipeline.supabase.client import supabase_enabled, fetch_fulltext as sb_fetch
    if supabase_enabled():
        text = sb_fetch(agora_id)
        if text is not None:
            return text
    txt_path = fulltext_dir / f"{agora_id}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8", errors="replace")
    return None


# ---------------------------------------------------------------------------
# Global Canonical Registry (replaces former CANONICAL_ORGS dict)
# ---------------------------------------------------------------------------

_registry: GlobalCanonicalRegistry | None = None


def get_registry() -> GlobalCanonicalRegistry:
    """Load or seed the global canonical registry (singleton per process)."""
    global _registry
    if _registry is not None:
        return _registry

    if GLOBAL_REGISTRY_PATH.exists():
        _registry = GlobalCanonicalRegistry.load(GLOBAL_REGISTRY_PATH)
    else:
        log.info("No existing registry found. Seeding from available data sources.")
        _registry = seed_registry(
            entity_dictionary_path=ENTITY_DICTIONARY_PATH,
            canonical_map_path=CANONICAL_ENTITY_MAP_PATH,
            manual_annotations_dir=MANUAL_ANNOTATIONS_DIR,
            type_authority_path=TYPE_AUTHORITY_PATH,
        )
        _registry.save(GLOBAL_REGISTRY_PATH)

    return _registry

# ---------------------------------------------------------------------------
# Generic term filter
# ---------------------------------------------------------------------------
#TODO: eliminate, deprecated -> include new annotations
GENERIC_STEMS = frozenset({
    "federal agencies", "relevant stakeholders", "program agencies",
    "appropriate entities", "the committee", "the program",
})

#TODO: remove
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
#TODO: improve system prompt!!
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


def _build_memory_context(memory: CommunityMemory, registry: GlobalCanonicalRegistry | None = None) -> str:
    """Build the community context prefix from memory, with budget-aware pruning.

    Tier 1 (always): Global disambiguation rules relevant to this community
    Tier 2 (compact): Registry entities in community roster, one-line format
    Tier 3 (fill):    Community-specific entities by mention count
    Tier 4 (if room): Parsing rules + oddities
    """
    budget = CONTEXT_BUDGET_CHARS
    parts: list[str] = []

    header = f'COMMUNITY CONTEXT: This document belongs to the "{memory.label}" legislative cluster.\n'
    parts.append(header)
    budget -= len(header)

    if registry is None:
        registry = get_registry()

    # --- Tier 1: Disambiguation rules (always include) ---
    tier1_lines: list[str] = []
    # Global disambiguation rules from registry
    for rule in registry.disambiguation_rules:
        if rule.scope == "global" or rule.scope == memory.community_id:
            entity = registry.entities.get(rule.resolved_entity_id)
            resolved_name = entity.canonical_name if entity else rule.resolved_entity_id
            tier1_lines.append(f'"{rule.pattern}" = {resolved_name}')
    # Community-level disambiguation rules
    for phrase, resolved in memory.disambiguation_rules.items():
        # Skip if already covered by registry rules
        if not any(r.pattern.lower() == phrase.lower() for r in registry.disambiguation_rules):
            tier1_lines.append(f'"{phrase}" = {resolved}')

    if tier1_lines:
        disambig_block = "Disambiguation rules: " + "; ".join(tier1_lines)
        if len(disambig_block) <= budget:
            parts.append(disambig_block)
            budget -= len(disambig_block) + 1

    # --- Tier 2: Registry entities in community roster (compact format) ---
    tier2_lines: list[str] = []
    for entity_type in NER_MEMORY_TOP_N:
        roster = memory.entity_roster.get(entity_type, [])
        for entry in roster:
            name = entry.get("name") or entry.get("title", "")
            if not name:
                continue
            resolved = registry.resolve(name, entity_type)
            if resolved:
                acronym_part = f" ({resolved.acronym})" if resolved.acronym else ""
                type_short = resolved.entity_type.replace("_", " ").rstrip("s")
                line = f"{resolved.canonical_name}{acronym_part} [{type_short}]"
                if line not in tier2_lines:
                    tier2_lines.append(line)

    if tier2_lines:
        tier2_header = "\nKnown entities (canonical):"
        tier2_block = tier2_header + "\n" + "\n".join(f"- {l}" for l in tier2_lines)
        if len(tier2_block) <= budget:
            parts.append(tier2_block)
            budget -= len(tier2_block) + 1
        else:
            # Truncate to fit budget
            parts.append(tier2_header)
            budget -= len(tier2_header) + 1
            for line in tier2_lines:
                entry = f"- {line}"
                if len(entry) + 1 > budget:
                    break
                parts.append(entry)
                budget -= len(entry) + 1

    # --- Tier 3: Community-specific entities NOT in registry, by mention count ---
    tier3_entries: list[tuple[str, str, int]] = []  # (name, type_label, mentions)
    for entity_type, top_n in NER_MEMORY_TOP_N.items():
        entries = memory.entity_roster.get(entity_type, [])
        for entry in entries:
            name = entry.get("name") or entry.get("title", "")
            if not name:
                continue
            # Skip if already covered in tier 2
            if registry.resolve(name, entity_type):
                continue
            mentions = entry.get("mentions", 0)
            type_label = entity_type.replace("_", " ").title()
            tier3_entries.append((name, type_label, mentions))

    tier3_entries.sort(key=lambda x: x[2], reverse=True)
    if tier3_entries:
        tier3_header = "\nCommunity-specific entities:"
        parts.append(tier3_header)
        budget -= len(tier3_header) + 1
        for name, type_label, mentions in tier3_entries:
            line = f"- {name} [{type_label}, {mentions} mentions]"
            if len(line) + 1 > budget:
                break
            parts.append(line)
            budget -= len(line) + 1

    # --- Tier 4: Parsing rules + oddities (if room) ---
    active_rules = memory.parsing_rules[:NER_MAX_PARSING_RULES]
    if active_rules and budget > 100:
        rules_header = "\nParsing patterns:"
        parts.append(rules_header)
        budget -= len(rules_header) + 1
        for rule in active_rules:
            line = f"- {rule}"
            if len(line) + 1 > budget:
                break
            parts.append(line)
            budget -= len(line) + 1

    recent_oddities = memory.oddities[-3:] if memory.oddities else []
    if recent_oddities and budget > 80:
        parts.append("\nKnown oddities:")
        for o in recent_oddities:
            note = o.get("note", "")
            line = f"- {note}"
            if len(line) + 1 > budget:
                break
            parts.append(line)
            budget -= len(line) + 1

    parts.append("\nNew entities not already listed above are especially valuable — extract them carefully.")

    return "\n".join(parts)


def _build_user_prompt(
    official_name: str,
    short_summary: str,
    text_chunk: str,
    in_progress_entities: list[str] | None = None,
    doc_disambiguations: dict[str, str] | None = None,
) -> str:
    """Build the user prompt for a single chunk."""
    parts = [f"Document title: {official_name}"]
    if short_summary:
        parts.append(f"Summary: {short_summary}")

    if doc_disambiguations:
        lines = [f'  "{phrase}" → {resolved}' for phrase, resolved in doc_disambiguations.items()]
        parts.append(f"\nDisambiguations established in earlier sections of this document:\n" + "\n".join(lines))

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

def compute_is_new(entity_name: str, entity_type: str, memory: CommunityMemory, registry: GlobalCanonicalRegistry | None = None) -> bool:
    """Determine if entity is new to the community memory."""
    roster = memory.entity_roster.get(entity_type, [])
    name_lower = entity_name.lower().strip()
    for existing in roster:
        existing_name = (existing.get("name") or existing.get("title", "")).lower().strip()
        if existing_name == name_lower:
            return False

    # Check global registry for canonical resolution
    if registry is None:
        registry = get_registry()
    resolved = registry.resolve(entity_name, entity_type)
    if resolved:
        canonical_lower = resolved.canonical_name.lower().strip()
        for existing in roster:
            existing_name = (existing.get("name") or existing.get("title", "")).lower().strip()
            if existing_name == canonical_lower:
                return False
    return True


# ---------------------------------------------------------------------------
# Merge chunk results
# ---------------------------------------------------------------------------

def _get_entity_name(entity: dict, entity_type: str) -> str:
    if entity_type == "roles":
        return entity.get("title", "")
    return entity.get("name", "")


def merge_chunk_results(
    chunk_results: list[dict[str, Any]],
    doc_disambiguations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Merge entity lists from multiple chunks, deduplicating by name.

    Uses doc_disambiguations to collapse soft aliases (e.g. "Secretary" is
    treated as a duplicate of "Secretary of Agriculture" if disambiguated).
    """
    merged: dict[str, list[dict]] = {k: [] for k in REQUIRED_KEYS}
    seen: dict[str, set[str]] = {k: set() for k in REQUIRED_KEYS}
    disambiguation_updates: dict[str, str] = {}
    parsing_rules: list[str] = []
    oddities: list[str] = []

    # Build set of soft alias phrases (lowercased) from doc disambiguations.
    _alias_phrases: set[str] = set()
    if doc_disambiguations:
        for phrase in doc_disambiguations:
            _alias_phrases.add(phrase.lower().strip())

    for result in chunk_results:
        for entity_type in REQUIRED_KEYS:
            for entity in result.get(entity_type, []):
                name = _get_entity_name(entity, entity_type).lower().strip()
                if not name:
                    continue
                if name in seen[entity_type]:
                    continue

                # If this name is a known soft alias (e.g. "secretary") and a
                # longer canonical form containing it is already seen (e.g.
                # "secretary of agriculture"), skip the bare alias.
                if name in _alias_phrases:
                    if any(name in s and s != name for s in seen[entity_type]):
                        continue

                # Reverse: if a bare alias that is a substring of this name
                # was already added, replace it with this canonical form.
                for alias in list(_alias_phrases):
                    if alias in seen[entity_type] and alias in name and alias != name:
                        merged[entity_type] = [
                            e for e in merged[entity_type]
                            if _get_entity_name(e, entity_type).lower().strip() != alias
                        ]
                        seen[entity_type].discard(alias)

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
    registry: GlobalCanonicalRegistry | None = None,
) -> EntityRecord | None:
    """Run NER on a single document using community memory and global registry.

    Pre-resolves known entities via registry before LLM extraction.
    Returns EntityRecord on success, None on failure.
    """
    if registry is None:
        registry = get_registry()

    chunks = chunk_text(fulltext)
    if not chunks:
        log.warning("No text to process for doc %s", agora_id)
        return None

    chunk_results: list[dict[str, Any]] = []
    in_progress_entities: list[str] = []
    total_pt = 0
    total_ct = 0

    memory_context = _build_memory_context(memory, registry)

    # Pre-resolve known entities from the full document text
    pre_resolved = registry.pre_resolve(fulltext, community_id=memory.community_id)
    pre_resolved_names = [pr["canonical_name"] for pr in pre_resolved]

    doc_disambiguations: dict[str, str] = {}  # accumulates across chunks

    for i, chunk in enumerate(chunks):
        # Combine pre-resolved names with in-progress entities for context
        all_known = list(set(pre_resolved_names + (in_progress_entities if i > 0 else [])))

        user_prompt = _build_user_prompt(
            official_name, short_summary, chunk,
            all_known if all_known else None,
            doc_disambiguations if doc_disambiguations else None,
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

        # Filter generic terms — include doc-level disambiguations as resolved
        resolved = set(memory.disambiguation_rules.keys()) | set(doc_disambiguations.keys())
        for entity_type in REQUIRED_KEYS:
            parsed[entity_type] = [
                e for e in parsed[entity_type]
                if not is_generic(_get_entity_name(e, entity_type), resolved)
            ]

        # Apply type authority corrections from registry
        for entity_type in REQUIRED_KEYS:
            for entity in parsed[entity_type]:
                name = _get_entity_name(entity, entity_type)
                if name:
                    correct_type = registry.resolve_type(name)
                    if correct_type and correct_type != entity_type:
                        log.debug("Type correction: '%s' is %s not %s", name, correct_type, entity_type)

        chunk_results.append(parsed)

        # Accumulate disambiguation from this chunk for subsequent chunks
        for k, v in parsed.get("disambiguation_updates", {}).items():
            if k not in doc_disambiguations:
                doc_disambiguations[k] = v

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
    merged = merge_chunk_results(chunk_results, doc_disambiguations=doc_disambiguations)

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

def update_memory(
    memory: CommunityMemory,
    record: EntityRecord,
    registry: GlobalCanonicalRegistry | None = None,
) -> None:
    """Update community memory with entities from a processed document.

    Also tracks LLM disambiguation decisions for potential rule graduation.
    """
    if registry is None:
        registry = get_registry()

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
            new = compute_is_new(name, type_key, memory, registry)
            memory.merge_entity(type_key, name, entity, new)

    # Disambiguation — track LLM decisions for graduation
    for phrase, resolved in record.disambiguation_updates.items():
        memory.add_disambiguation(phrase, resolved)
        memory.llm_disambiguation_log.append({
            "phrase": phrase,
            "resolved": resolved,
            "doc_id": record.agora_id,
            "community_id": memory.community_id,
        })

    # Check for graduation candidates
    _check_graduation_candidates(memory, registry)

    # Parsing rule
    if record.new_parsing_rule:
        memory.add_parsing_rule(record.new_parsing_rule, NER_MAX_PARSING_RULES)

    # Oddity
    if record.oddity:
        memory.add_oddity(record.agora_id, record.oddity)


def _check_graduation_candidates(
    memory: CommunityMemory,
    registry: GlobalCanonicalRegistry,
) -> None:
    """Check if any LLM disambiguation patterns should graduate to rules.

    If HALLUCINATION_PROBE_ENABLED, runs an adversarial high-temperature probe
    before graduating to verify the rule is robust.
    """
    from collections import Counter
    from pipeline.config import (
        HALLUCINATION_PROBE_ENABLED,
        HALLUCINATION_TEMPERATURE,
        HALLUCINATION_PASS_THRESHOLD,
    )

    phrase_counts: Counter[str] = Counter()
    for entry in memory.llm_disambiguation_log:
        key = f"{entry['phrase'].lower().strip()}||{entry['resolved']}"
        phrase_counts[key] += 1

    for key, count in phrase_counts.items():
        if count < GRADUATION_THRESHOLD:
            continue

        phrase, resolved = key.split("||", 1)
        # Check if already a rule in registry
        existing = registry.resolve(phrase, community_id=memory.community_id)
        if existing:
            continue

        # Try to find the resolved entity in registry
        resolved_entity = registry.resolve(resolved)
        if not resolved_entity:
            continue

        # Adversarial hallucination probe
        if HALLUCINATION_PROBE_ENABLED:
            probe_pass = _run_hallucination_probe(
                phrase, resolved, memory,
                temperature=HALLUCINATION_TEMPERATURE,
                pass_threshold=HALLUCINATION_PASS_THRESHOLD,
            )
            if probe_pass is False:
                log.info(
                    "Hallucination probe REJECTED: '%s' -> '%s' (community %s)",
                    phrase, resolved, memory.community_id,
                )
                continue
            elif probe_pass is None:
                log.info(
                    "Hallucination probe flagged for REVIEW: '%s' -> '%s' (community %s)",
                    phrase, resolved, memory.community_id,
                )
                # Write to review queue instead of graduating
                from pipeline.agents.canonical_registry import CandidateRule
                candidate = CandidateRule(
                    phrase=phrase,
                    resolved_name=resolved,
                    resolved_entity_id=resolved_entity.entity_id,
                    community_id=memory.community_id,
                    occurrences=count,
                    source="llm_observed",
                    status="review",
                    created_at=utc_now_iso(),
                )
                append_jsonl(REVIEW_QUEUE_PATH, [candidate.to_dict()])
                continue

        from pipeline.agents.canonical_registry import DisambiguationRule

        log.info(
            "Graduating disambiguation rule: '%s' -> '%s' (community %s, %d occurrences)",
            phrase, resolved, memory.community_id, count,
        )
        registry.add_disambiguation_rule(DisambiguationRule(
            pattern=phrase,
            resolved_entity_id=resolved_entity.entity_id,
            scope=memory.community_id,
            confidence=min(0.95, 0.6 + count * 0.05),
            source="llm_graduated",
        ))


def _run_hallucination_probe(
    phrase: str,
    candidate_resolution: str,
    memory: CommunityMemory,
    temperature: float = 1.0,
    pass_threshold: float = 0.8,
) -> bool | None:
    """Run adversarial high-temperature probe to validate a disambiguation rule.

    Returns:
        True  — candidate resolution dominates (>=pass_threshold), safe to graduate
        None  — alternatives surfaced (flag for human review)
        False — candidate resolution absent from probe output, reject graduation
    """
    from pipeline.agents.llm_client import call_claude

    system = (
        "You are analyzing ambiguous phrases in U.S. federal legislative documents. "
        "Given an ambiguous phrase and the document context, list ALL plausible entity "
        "interpretations with confidence scores (0-1). Be exhaustive — consider every "
        "possible referent."
    )

    context_info = f'Legislative cluster: "{memory.label}"\n'
    if memory.taxonomy_signature:
        context_info += f"Topics: {', '.join(memory.taxonomy_signature[:5])}\n"

    user = (
        f"{context_info}\n"
        f'The phrase "{phrase}" appears in documents from this cluster.\n\n'
        f"List all plausible entities this phrase could refer to, with confidence scores:\n"
        f"Format: ENTITY_NAME (confidence: 0.X)\n"
    )

    try:
        response_text, _, _ = call_claude(
            system, user,
            temperature=temperature,
            max_tokens=512,
        )
    except Exception as exc:
        log.warning("Hallucination probe failed for '%s': %s. Skipping probe.", phrase, exc)
        return True  # Don't block graduation on probe failure

    # Parse response: check if candidate_resolution appears
    response_lower = response_text.lower()
    candidate_lower = candidate_resolution.lower()

    if candidate_lower in response_lower:
        # Candidate appears — check if it dominates
        # Simple heuristic: if the candidate is mentioned first or is the only one,
        # it passes. Count how many distinct entity interpretations appear.
        lines = [l.strip() for l in response_text.split("\n") if l.strip() and "confidence" in l.lower()]
        if len(lines) <= 1:
            return True  # Only one interpretation found
        # Check if candidate is in the first/highest-confidence line
        if lines and candidate_lower in lines[0].lower():
            return True
        # Multiple interpretations exist — flag for review
        return None
    else:
        # Candidate not even mentioned — reject
        return False


# ---------------------------------------------------------------------------
# Confidence scoring (rule-based, no API cost)
# ---------------------------------------------------------------------------

def compute_entity_confidence(
    entity_name: str,
    entity_type: str,
    memory: CommunityMemory,
    registry: GlobalCanonicalRegistry,
) -> float:
    """Compute confidence score for an extracted entity.

    Heuristic scoring (no LLM calls):
      +0.3 if in global registry
      +0.1 if in community memory (not new)
      +0.1 if has acronym
      -0.2 if name < 8 chars
      -0.3 if type conflicts with registry
      Base: 0.5
    """
    score = 0.5

    resolved = registry.resolve(entity_name, entity_type)
    if resolved:
        score += 0.3
    else:
        # Check if it's in registry but with a different type (type conflict)
        any_match = registry.resolve(entity_name)
        if any_match and any_match.entity_type != entity_type:
            score -= 0.3

    if not compute_is_new(entity_name, entity_type, memory, registry):
        score += 0.1

    # Check for acronym in the entity dict or registry
    if resolved and resolved.acronym:
        score += 0.1

    if len(entity_name.strip()) < 8:
        score -= 0.2

    return max(0.0, min(1.0, score))


def score_and_queue_entities(
    record: EntityRecord,
    memory: CommunityMemory,
    registry: GlobalCanonicalRegistry,
) -> None:
    """Score all entities in a record and queue low-confidence ones for review."""
    low_confidence: list[dict[str, Any]] = []

    for entity_type in REQUIRED_KEYS:
        for entity in getattr(record, entity_type, []):
            name = _get_entity_name(entity, entity_type)
            if not name:
                continue
            conf = compute_entity_confidence(name, entity_type, memory, registry)
            entity_id = make_entity_id(name, entity_type)
            memory.entity_confidence[entity_id] = conf

            if conf < CONFIDENCE_REVIEW_THRESHOLD:
                low_confidence.append({
                    "agora_id": record.agora_id,
                    "entity_name": name,
                    "entity_type": entity_type,
                    "confidence": round(conf, 3),
                    "reason": _explain_low_confidence(name, entity_type, registry),
                    "ts": utc_now_iso(),
                })

    if low_confidence:
        append_jsonl(REVIEW_QUEUE_PATH, low_confidence)
        log.info("Queued %d low-confidence entities from doc %s for review.", len(low_confidence), record.agora_id)


def _explain_low_confidence(name: str, entity_type: str, registry: GlobalCanonicalRegistry) -> str:
    """Generate a brief explanation for why an entity scored low."""
    reasons = []
    if len(name.strip()) < 8:
        reasons.append("short_name")
    any_match = registry.resolve(name)
    if any_match and any_match.entity_type != entity_type:
        reasons.append(f"type_conflict({any_match.entity_type})")
    if not registry.resolve(name, entity_type):
        reasons.append("not_in_registry")
    return ", ".join(reasons) if reasons else "low_base_score"


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

    registry = get_registry()
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
        fulltext = _read_fulltext(agora_id, fulltext_dir)
        if fulltext is None:
            log.warning("No fulltext for doc %s, skipping.", agora_id)
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason="no_fulltext")
            failed += 1
            continue

        if not fulltext.strip():
            save_checkpoint(agora_id, "failed", checkpoint_dir, reason="empty_fulltext")
            failed += 1
            continue

        try:
            record = process_document(
                agora_id, official_name, short_summary, fulltext, memory, model,
                registry=registry,
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

        # Update memory and score entities
        update_memory(memory, record, registry=registry)
        score_and_queue_entities(record, memory, registry)
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

    # Persist registry after community completes (captures graduated rules)
    if processed > 0:
        registry.save(GLOBAL_REGISTRY_PATH)

    stats = {
        "community_id": community.community_id,
        "docs_total": len(ordered_ids),
        "docs_processed": processed,
        "docs_failed": failed,
        "docs_skipped": len(ordered_ids) - processed - failed,
        "memory_orgs": len(memory.entity_roster.get("organizations", [])),
        "memory_rules": len(memory.parsing_rules),
        "registry_entities": len(registry.entities),
        "registry_rules": len(registry.disambiguation_rules),
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
