"""Global Canonical Registry for NER entity resolution.

Three-tier memory hierarchy:
  GlobalCanonicalRegistry (singleton, persisted)
    -> Rule Engine (deterministic canonicalization + disambiguation)
    -> CommunityMemory (per-community, enhanced)
    -> Document Context (ephemeral, per-chunk)

Seeds from: CANONICAL_ORGS, entity_dictionary.jsonl, canonical_entity_map.json,
manual_annotations/*.json, type_authority.json.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipeline.models import utc_now_iso

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CanonicalEntity:
    """A single canonical entity in the global registry."""
    entity_id: str               # e.g. "org:department_of_defense"
    entity_type: str             # "organizations", "offices", "roles", etc.
    canonical_name: str          # "Department of Defense"
    acronym: str = ""            # "DOD"
    aliases: list[str] = field(default_factory=list)
    type_constraints: list[str] = field(default_factory=list)
    source: str = "seed"         # "seed" | "manual_annotation" | "llm_graduated" | "promoted"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CanonicalEntity:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DisambiguationRule:
    """A rule for resolving ambiguous phrases to canonical entities."""
    pattern: str                 # "the Department"
    resolved_entity_id: str      # "org:department_of_defense"
    scope: str = "global"        # "global" | community_id
    confidence: float = 1.0
    source: str = "seed"         # "seed" | "manual" | "llm_graduated"
    context_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DisambiguationRule:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CandidateRule:
    """A candidate disambiguation rule pending validation."""
    phrase: str
    resolved_name: str
    resolved_entity_id: str = ""
    community_id: str = ""
    occurrences: int = 0
    source: str = "llm_observed"
    status: str = "pending"      # "pending" | "graduated" | "rejected" | "review"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helper: generate entity_id from name + type
# ---------------------------------------------------------------------------

def make_entity_id(name: str, entity_type: str) -> str:
    """Generate a slug-style entity_id from name and type."""
    type_prefix = {
        "organizations": "org",
        "offices": "office",
        "roles": "role",
        "legislation_refs": "legislation",
        "named_docs": "named_doc",
    }.get(entity_type, "entity")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_")
    return f"{type_prefix}:{slug}"


# ---------------------------------------------------------------------------
# Global Canonical Registry
# ---------------------------------------------------------------------------

ENTITY_TYPES = frozenset({
    "organizations", "offices", "roles", "legislation_refs", "named_docs",
})


class GlobalCanonicalRegistry:
    """Singleton registry for canonical entity resolution.

    Provides O(1) lookup via inverted index, deterministic resolution
    before LLM is consulted, and persistence to JSON.
    """

    def __init__(self) -> None:
        self.entities: dict[str, CanonicalEntity] = {}       # entity_id -> entity
        self.disambiguation_rules: list[DisambiguationRule] = []
        self._index: dict[str, list[str]] = {}               # lowercase text -> [entity_id]
        self._acronym_index: dict[str, str] = {}             # lowercase acronym -> entity_id
        self._regex_pattern: re.Pattern | None = None         # compiled pattern for pre-resolution

    # ---- Persistence ----

    def save(self, path: Path) -> None:
        """Persist registry to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
            "disambiguation_rules": [r.to_dict() for r in self.disambiguation_rules],
            "saved_at": utc_now_iso(),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        log.info("Registry saved: %d entities, %d rules -> %s", len(self.entities), len(self.disambiguation_rules), path)

    @classmethod
    def load(cls, path: Path) -> GlobalCanonicalRegistry:
        """Load registry from JSON file."""
        registry = cls()
        if not path.exists():
            log.warning("No registry file at %s, returning empty registry.", path)
            return registry
        data = json.loads(path.read_text(encoding="utf-8"))
        for eid, edict in data.get("entities", {}).items():
            entity = CanonicalEntity.from_dict(edict)
            registry.entities[eid] = entity
        for rdict in data.get("disambiguation_rules", []):
            registry.disambiguation_rules.append(DisambiguationRule.from_dict(rdict))
        registry._rebuild_index()
        log.info("Registry loaded: %d entities, %d rules from %s", len(registry.entities), len(registry.disambiguation_rules), path)
        return registry

    # ---- Index management ----

    def _rebuild_index(self) -> None:
        """Rebuild inverted index from all entities."""
        self._index.clear()
        self._acronym_index.clear()
        self._regex_pattern = None
        for eid, entity in self.entities.items():
            self._index_entity(eid, entity)

    def _index_entity(self, entity_id: str, entity: CanonicalEntity) -> None:
        """Add a single entity to the inverted index."""
        # Canonical name
        key = entity.canonical_name.lower().strip()
        self._index.setdefault(key, [])
        if entity_id not in self._index[key]:
            self._index[key].append(entity_id)

        # Acronym
        if entity.acronym:
            acr = entity.acronym.lower().strip()
            self._acronym_index[acr] = entity_id
            self._index.setdefault(acr, [])
            if entity_id not in self._index[acr]:
                self._index[acr].append(entity_id)

        # Aliases
        for alias in entity.aliases:
            akey = alias.lower().strip()
            if not akey:
                continue
            self._index.setdefault(akey, [])
            if entity_id not in self._index[akey]:
                self._index[akey].append(entity_id)

        # Invalidate compiled regex
        self._regex_pattern = None

    # ---- Registration ----

    def register(self, entity: CanonicalEntity) -> None:
        """Register or update a canonical entity."""
        existing = self.entities.get(entity.entity_id)
        if existing:
            # Merge: keep higher confidence, merge aliases
            if entity.confidence >= existing.confidence:
                existing.canonical_name = entity.canonical_name
                existing.entity_type = entity.entity_type
                existing.source = entity.source
                existing.confidence = entity.confidence
            if entity.acronym and not existing.acronym:
                existing.acronym = entity.acronym
            for alias in entity.aliases:
                if alias not in existing.aliases:
                    existing.aliases.append(alias)
            if entity.type_constraints:
                existing.type_constraints = entity.type_constraints
            existing.metadata.update(entity.metadata)
            self._index_entity(entity.entity_id, existing)
        else:
            self.entities[entity.entity_id] = entity
            self._index_entity(entity.entity_id, entity)

    def add_disambiguation_rule(self, rule: DisambiguationRule) -> None:
        """Add a disambiguation rule, deduplicating by (pattern, scope)."""
        pattern_lower = rule.pattern.lower().strip()
        for existing in self.disambiguation_rules:
            if existing.pattern.lower().strip() == pattern_lower and existing.scope == rule.scope:
                # Update if higher confidence
                if rule.confidence > existing.confidence:
                    existing.resolved_entity_id = rule.resolved_entity_id
                    existing.confidence = rule.confidence
                    existing.source = rule.source
                return
        self.disambiguation_rules.append(rule)

    # ---- Resolution ----

    def resolve(self, text: str, entity_type: str | None = None, community_id: str | None = None) -> CanonicalEntity | None:
        """Resolve text to a canonical entity.

        Resolution order:
        1. Exact match on canonical name / alias (case-insensitive)
        2. Acronym match
        3. Disambiguation rules (scoped)

        If entity_type is provided, filters results to matching type.
        """
        key = text.lower().strip()

        # 1. Direct index lookup
        candidates = self._index.get(key, [])
        if candidates:
            result = self._pick_best(candidates, entity_type)
            if result:
                return result

        # 2. Disambiguation rules
        for rule in self.disambiguation_rules:
            if rule.pattern.lower().strip() == key:
                if rule.scope == "global" or rule.scope == community_id:
                    entity = self.entities.get(rule.resolved_entity_id)
                    if entity and (entity_type is None or entity.entity_type == entity_type):
                        return entity

        return None

    def _pick_best(self, entity_ids: list[str], entity_type: str | None) -> CanonicalEntity | None:
        """Pick the best entity from candidates, optionally filtering by type."""
        matches = [self.entities[eid] for eid in entity_ids if eid in self.entities]
        if entity_type:
            typed = [e for e in matches if e.entity_type == entity_type]
            if typed:
                return max(typed, key=lambda e: e.confidence)
        if matches:
            return max(matches, key=lambda e: e.confidence)
        return None

    def resolve_type(self, name: str) -> str | None:
        """Check type_authority constraints for a name. Returns the correct type or None."""
        key = name.lower().strip()
        for entity in self.entities.values():
            if entity.canonical_name.lower().strip() == key and entity.type_constraints:
                return entity.type_constraints[0]
        return None

    # ---- Pre-resolution regex ----

    def build_regex_pattern(self) -> re.Pattern | None:
        """Build a compiled regex for scanning text for known entities.

        Returns a pattern that matches any known canonical name, acronym, or alias
        as whole words. Sorted longest-first to prefer longer matches.
        """
        if self._regex_pattern is not None:
            return self._regex_pattern

        terms: set[str] = set()
        for entity in self.entities.values():
            terms.add(entity.canonical_name)
            if entity.acronym and len(entity.acronym) >= 2:
                terms.add(entity.acronym)
            for alias in entity.aliases:
                if alias and len(alias) >= 3:
                    terms.add(alias)

        if not terms:
            return None

        # Sort longest first for greedy matching
        sorted_terms = sorted(terms, key=len, reverse=True)
        escaped = [re.escape(t) for t in sorted_terms]
        pattern_str = r"\b(?:" + "|".join(escaped) + r")\b"

        try:
            self._regex_pattern = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            log.warning("Failed to compile pre-resolution regex with %d terms.", len(terms))
            return None

        return self._regex_pattern

    def pre_resolve(self, text: str, community_id: str | None = None) -> list[dict[str, Any]]:
        """Scan text for known entities using compiled regex.

        Returns list of dicts: {entity_id, canonical_name, entity_type, acronym, match_text}
        """
        pattern = self.build_regex_pattern()
        if pattern is None:
            return []

        seen_ids: set[str] = set()
        results: list[dict[str, Any]] = []

        for match in pattern.finditer(text):
            match_text = match.group()
            entity = self.resolve(match_text, community_id=community_id)
            if entity and entity.entity_id not in seen_ids:
                seen_ids.add(entity.entity_id)
                results.append({
                    "entity_id": entity.entity_id,
                    "canonical_name": entity.canonical_name,
                    "entity_type": entity.entity_type,
                    "acronym": entity.acronym,
                    "match_text": match_text,
                })

        return results

    # ---- Stats ----

    def stats(self) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        for e in self.entities.values():
            type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1
        return {
            "total_entities": len(self.entities),
            "total_rules": len(self.disambiguation_rules),
            "index_keys": len(self._index),
            "by_type": type_counts,
        }


# ---------------------------------------------------------------------------
# Seeding: build registry from existing data sources
# ---------------------------------------------------------------------------

# Hardcoded canonical orgs (migrated from ner_agent.py CANONICAL_ORGS)
_SEED_ORGS: dict[str, str] = {
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

# Extract canonical name -> acronym from the seed
_SEED_ACRONYMS: dict[str, str] = {}
for _acr, _name in _SEED_ORGS.items():
    if len(_acr) <= 5 and _acr == _acr.lower() and "." not in _acr:
        _SEED_ACRONYMS.setdefault(_name, _acr.upper())


def seed_registry(
    entity_dictionary_path: Path | None = None,
    canonical_map_path: Path | None = None,
    manual_annotations_dir: Path | None = None,
    type_authority_path: Path | None = None,
) -> GlobalCanonicalRegistry:
    """Build a fresh registry from all available seed data sources.

    Sources (in order, later sources can override/merge):
    1. _SEED_ORGS (hardcoded acronym -> canonical name)
    2. entity_dictionary.jsonl (existing curated entities)
    3. canonical_entity_map.json (text variation -> entity_id)
    4. manual_annotations/*.json (human-annotated entities)
    5. type_authority.json (type constraint overrides)
    """
    registry = GlobalCanonicalRegistry()

    # --- Stage 1: Seed orgs ---
    _seed_from_canonical_orgs(registry)

    # --- Stage 2: Entity dictionary ---
    if entity_dictionary_path and entity_dictionary_path.exists():
        _seed_from_entity_dictionary(registry, entity_dictionary_path)

    # --- Stage 3: Canonical entity map ---
    if canonical_map_path and canonical_map_path.exists():
        _seed_from_canonical_map(registry, canonical_map_path)

    # --- Stage 4: Manual annotations ---
    if manual_annotations_dir and manual_annotations_dir.exists():
        ingest_manual_annotations(registry, manual_annotations_dir)

    # --- Stage 5: Type authority overrides ---
    if type_authority_path and type_authority_path.exists():
        _apply_type_authority(registry, type_authority_path)

    registry._rebuild_index()
    log.info("Registry seeded: %s", registry.stats())
    return registry


def _seed_from_canonical_orgs(registry: GlobalCanonicalRegistry) -> None:
    """Seed from the hardcoded CANONICAL_ORGS mapping."""
    # Group aliases by canonical name
    name_aliases: dict[str, list[str]] = {}
    for alias, canonical in _SEED_ORGS.items():
        name_aliases.setdefault(canonical, []).append(alias)

    for canonical_name, aliases in name_aliases.items():
        entity_id = make_entity_id(canonical_name, "organizations")
        acronym = _SEED_ACRONYMS.get(canonical_name, "")
        # Filter out the acronym from aliases (it goes in the acronym field)
        non_acronym_aliases = [a for a in aliases if a.upper() != acronym]
        registry.register(CanonicalEntity(
            entity_id=entity_id,
            entity_type="organizations",
            canonical_name=canonical_name,
            acronym=acronym,
            aliases=non_acronym_aliases,
            source="seed",
            confidence=1.0,
        ))


def _seed_from_entity_dictionary(registry: GlobalCanonicalRegistry, path: Path) -> None:
    """Seed from entity_dictionary.jsonl."""
    from pipeline.models import read_jsonl
    for row in read_jsonl(path):
        entity_id = row.get("entity_id", "")
        entity_type = row.get("entity_type", "")
        canonical_name = row.get("canonical_name", "")
        if not entity_id or not canonical_name:
            continue

        aliases = row.get("aliases", [])
        soft_aliases = row.get("soft_aliases", [])
        acronym = row.get("acronym", "")

        # NOTE: soft_aliases are document-scoped (e.g. "the Secretary" -> "Secretary
        # of Defense" in one doc, "Secretary of Homeland Security" in another). They
        # must NOT be promoted to registry-level aliases or disambiguation rules.
        # Only explicit aliases (full-name variations) go into the registry.

        registry.register(CanonicalEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            acronym=acronym,
            aliases=list(set(aliases)),
            source="entity_dictionary",
            confidence=0.9,
            metadata={k: v for k, v in row.get("metadata", {}).items() if v},
        ))


def _seed_from_canonical_map(registry: GlobalCanonicalRegistry, path: Path) -> None:
    """Seed aliases from canonical_entity_map.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    # data is {text_variation: entity_id}
    for text_variation, entity_id in data.items():
        entity = registry.entities.get(entity_id)
        if entity:
            alias = text_variation.strip()
            if alias.lower() != entity.canonical_name.lower() and alias not in entity.aliases:
                entity.aliases.append(alias)
        # If entity doesn't exist yet, we skip — it should come from entity_dictionary


def ingest_manual_annotations(
    registry: GlobalCanonicalRegistry,
    annotations_dir: Path,
) -> None:
    """Ingest manual annotations into the registry.

    Extracts entities and soft_aliases from annotation JSONs.
    Manual annotations have confidence=1.0 (human-verified).
    """
    count = 0
    for ann_file in sorted(annotations_dir.glob("*.json")):
        try:
            ann = json.loads(ann_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Skipping invalid annotation file: %s", ann_file)
            continue

        entity_type_fields = {
            "organizations": "name",
            "offices": "name",
            "roles": "title",
            "legislation_refs": "name",
            "named_docs": "name",
        }

        for entity_type, name_field in entity_type_fields.items():
            for entity in ann.get(entity_type, []):
                name = entity.get(name_field, "").strip()
                if not name:
                    continue
                entity_id = make_entity_id(name, entity_type)
                acronym = entity.get("acronym", "")
                registry.register(CanonicalEntity(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    canonical_name=name,
                    acronym=acronym,
                    source="manual_annotation",
                    confidence=1.0,
                    metadata={
                        k: v for k, v in entity.items()
                        if k not in (name_field, "acronym", "context", "char_start", "char_end")
                        and v
                    },
                ))
                count += 1

        # NOTE: soft_aliases are intentionally NOT ingested as disambiguation rules.
        # Soft aliases are document-scoped: "the Secretary" -> "Secretary of Defense"
        # in one document, but "Secretary of Homeland Security" in another. Promoting
        # them to global rules would create incorrect disambiguation. They remain in
        # the annotation files and are only used by CommunityMemory.disambiguation_rules
        # when the LLM discovers the pattern in community context.

    log.info("Ingested %d entities from manual annotations in %s", count, annotations_dir)


def _apply_type_authority(registry: GlobalCanonicalRegistry, path: Path) -> None:
    """Apply type authority overrides to fix misclassifications.

    type_authority.json format:
    {
        "role_not_org": ["Secretary of Defense", ...],
        "org_not_role": ["Department of Defense", ...]
    }
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    type_corrections = {
        "role_not_org": ("roles", "organizations"),  # should be role, not org
        "org_not_role": ("organizations", "roles"),   # should be org, not role
    }

    for rule_key, (correct_type, wrong_type) in type_corrections.items():
        for name in data.get(rule_key, []):
            name_lower = name.lower().strip()
            wrong_id = make_entity_id(name, wrong_type)
            correct_id = make_entity_id(name, correct_type)

            # If a wrongly-typed entry exists, migrate it
            if wrong_id in registry.entities:
                wrong_entity = registry.entities.pop(wrong_id)
                # Merge into correct entity or create it
                correct_entity = registry.entities.get(correct_id)
                if correct_entity:
                    # Merge aliases from wrong into correct
                    for alias in wrong_entity.aliases:
                        if alias not in correct_entity.aliases:
                            correct_entity.aliases.append(alias)
                    if wrong_entity.acronym and not correct_entity.acronym:
                        correct_entity.acronym = wrong_entity.acronym
                else:
                    # Re-register under correct type
                    wrong_entity.entity_id = correct_id
                    wrong_entity.entity_type = correct_type
                    wrong_entity.type_constraints = [correct_type]
                    registry.entities[correct_id] = wrong_entity

            # Ensure the correct entity has type_constraints set
            if correct_id in registry.entities:
                registry.entities[correct_id].type_constraints = [correct_type]

    corrections = sum(len(data.get(k, [])) for k in type_corrections)
    log.info("Applied %d type authority corrections from %s", corrections, path)
