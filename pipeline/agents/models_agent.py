"""Data models for the agentic multiplex knowledge graph pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from pipeline.models import utc_now_iso


# ---------------------------------------------------------------------------
# Phase 1: Sponsor Graph
# ---------------------------------------------------------------------------

@dataclass
class SponsorRecord:
    bioguide_id: str
    full_name: str
    last_name: str = ""
    first_name: str = ""
    party: str = ""          # R / D / I
    state: str = ""          # two-letter abbreviation
    district: str = ""       # number or empty for senators
    chamber: str = ""        # Rep / Sen

    @property
    def node_id(self) -> str:
        return f"sponsor:{self.bioguide_id}"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["node_id"] = self.node_id
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SponsorRecord:
        d = dict(d)
        d.pop("node_id", None)
        return cls(**d)


# ---------------------------------------------------------------------------
# Phase 2: Community Detection
# ---------------------------------------------------------------------------

@dataclass
class CommunityRecord:
    community_id: str
    label: str
    taxonomy_signature: list[str] = field(default_factory=list)
    dominant_party: str = ""
    member_agora_ids: list[str] = field(default_factory=list)
    bill_groups: list[list[str]] = field(default_factory=list)
    doc_centrality: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommunityRecord:
        return cls(**d)


# ---------------------------------------------------------------------------
# Phase 3: NER Agent
# ---------------------------------------------------------------------------

@dataclass
class EntityRecord:
    """One document's full NER extraction output."""
    agora_id: str
    organizations: list[dict] = field(default_factory=list)
    offices: list[dict] = field(default_factory=list)
    roles: list[dict] = field(default_factory=list)
    legislation_refs: list[dict] = field(default_factory=list)
    named_docs: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    disambiguation_updates: dict[str, str] = field(default_factory=dict)
    new_parsing_rule: str | None = None
    oddity: str | None = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    chunks_processed: int = 0
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityRecord:
        return cls(**d)


@dataclass
class CommunityMemory:
    """Persistent memory for a community's NER agent."""
    community_id: str
    label: str = ""
    taxonomy_signature: list[str] = field(default_factory=list)
    entity_roster: dict[str, list[dict]] = field(default_factory=lambda: {
        "organizations": [],
        "offices": [],
        "roles": [],
        "legislation_refs": [],
        "named_docs": [],
    })
    disambiguation_rules: dict[str, str] = field(default_factory=dict)
    parsing_rules: list[str] = field(default_factory=list)
    archived_rules: list[str] = field(default_factory=list)
    oddities: list[dict] = field(default_factory=list)
    docs_processed: int = 0
    docs_total: int = 0
    last_doc_id: str = ""
    # Shared memory system additions
    llm_disambiguation_log: list[dict] = field(default_factory=list)
    entity_confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommunityMemory:
        return cls(**d)

    def merge_entity(self, entity_type: str, name: str, entity_dict: dict, is_new: bool) -> None:
        """Merge an entity into the roster."""
        roster = self.entity_roster.setdefault(entity_type, [])
        if is_new:
            entry = dict(entity_dict)
            entry["mentions"] = 1
            entry["first_seen"] = self.last_doc_id
            roster.append(entry)
        else:
            # Increment mentions for existing entry
            name_lower = name.lower().strip()
            for existing in roster:
                if existing.get("name", existing.get("title", "")).lower().strip() == name_lower:
                    existing["mentions"] = existing.get("mentions", 1) + 1
                    break

    def add_disambiguation(self, phrase: str, resolved: str) -> None:
        """Add a disambiguation rule (only if not already set)."""
        key = phrase.lower().strip()
        if key not in self.disambiguation_rules:
            self.disambiguation_rules[key] = resolved

    def add_parsing_rule(self, rule: str, max_active: int = 7) -> None:
        """Add a parsing rule with dedup by token overlap."""
        if not rule:
            return
        rule_tokens = set(rule.lower().split())
        for existing in self.parsing_rules:
            existing_tokens = set(existing.lower().split())
            union = rule_tokens | existing_tokens
            if not union:
                continue
            overlap = len(rule_tokens & existing_tokens) / len(union)
            if overlap > 0.70:
                # Update existing rule if new one is more specific (longer)
                if len(rule) > len(existing):
                    idx = self.parsing_rules.index(existing)
                    self.parsing_rules[idx] = rule
                return
        self.parsing_rules.append(rule)
        # Cap active rules
        while len(self.parsing_rules) > max_active:
            archived = self.parsing_rules.pop(0)
            self.archived_rules.append(archived)

    def add_oddity(self, agora_id: str, note: str) -> None:
        if note:
            self.oddities.append({"agora_id": agora_id, "note": note})


# ---------------------------------------------------------------------------
# Graph Builder: Layered Node / Edge
# ---------------------------------------------------------------------------

@dataclass
class LayeredNode:
    node_id: str
    node_type: str
    label: str
    layer: int
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayeredEdge:
    src_id: str
    relation: str
    dst_id: str
    layer: int
    properties: dict[str, Any] = field(default_factory=dict)
    agent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
