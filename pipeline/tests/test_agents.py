"""Tests for the agentic multiplex knowledge graph pipeline.

Covers:
- Community detection (similarity, Louvain, labeling)
- NER agent (chunking, is_new, generic filter, merge, memory update, validation)
- Graph builder (layer assembly, combine, stats)
- Sponsor graph (parsing helpers)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Sponsor graph tests
# ---------------------------------------------------------------------------

from pipeline.agents.sponsor_graph import (
    _parse_chamber,
    _parse_name_parts,
    _clean_district,
    build_sponsor_graph,
)


class TestSponsorGraph:
    def test_parse_chamber_rep(self):
        assert _parse_chamber("Rep. Smith, John [R-TX-1]") == "Rep"

    def test_parse_chamber_sen(self):
        assert _parse_chamber("Sen. Cruz, Ted [R-TX]") == "Sen"

    def test_parse_chamber_unknown(self):
        assert _parse_chamber("John Smith") == ""

    def test_parse_name_parts(self):
        last, first = _parse_name_parts("Rep. Graves, Sam [R-MO-6]")
        assert last == "Graves"
        assert first == "Sam"

    def test_parse_name_parts_no_first(self):
        last, first = _parse_name_parts("Sen. Cruz [R-TX]")
        assert last == "Cruz"
        assert first == ""

    def test_clean_district(self):
        assert _clean_district("6.0") == "6"
        assert _clean_district("nan") == ""
        assert _clean_district("") == ""
        assert _clean_district("12") == "12"

    def test_build_sponsor_graph_basic(self, tmp_path):
        rows = [
            {
                "AGORA ID": "1",
                "Sponsor_bioguideId": "B001",
                "Sponsor_Name": "Rep. Smith, John [R-TX-1]",
                "Sponsor_Party": "R",
                "Sponsor_State": "TX",
                "Sponsor_District": "1",
                "Link to document": "http://example.com/bill1",
            },
            {
                "AGORA ID": "2",
                "Sponsor_bioguideId": "B001",
                "Sponsor_Name": "Rep. Smith, John [R-TX-1]",
                "Sponsor_Party": "R",
                "Sponsor_State": "TX",
                "Sponsor_District": "1",
                "Link to document": "http://example.com/bill2",
            },
            {
                "AGORA ID": "3",
                "Sponsor_bioguideId": "B002",
                "Sponsor_Name": "Sen. Jones, Jane [D-CA]",
                "Sponsor_Party": "D",
                "Sponsor_State": "CA",
                "Sponsor_District": "",
                "Link to document": "http://example.com/bill3",
            },
        ]
        stats = build_sponsor_graph(rows, output_dir=tmp_path)
        assert stats["unique_sponsors"] == 2
        assert stats["sponsored_by_edges"] == 3
        assert stats["shares_sponsor_edges"] == 1  # docs 1 and 2 share B001
        assert (tmp_path / "sponsor_nodes.csv").exists()
        assert (tmp_path / "sponsor_edges.csv").exists()
        assert (tmp_path / "doc_sponsor_matrix.json").exists()


# ---------------------------------------------------------------------------
# Community detection tests
# ---------------------------------------------------------------------------

from pipeline.agents.community_detector import (
    jaccard,
    compute_taxonomy_jaccard,
    compute_collections_sets,
    label_community,
    inspect_communities,
)
from pipeline.agents.models_agent import CommunityRecord


class TestCommunityDetection:
    def test_jaccard_identical(self):
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint(self):
        assert jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial(self):
        assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_jaccard_empty(self):
        assert jaccard(set(), set()) == 0.0

    def test_taxonomy_vectors(self):
        rows = [
            {"AGORA ID": "1", "Applications: Education": "True", "Harms: Discrimination": "False"},
            {"AGORA ID": "2", "Applications: Education": "False", "Harms: Discrimination": "True"},  # CSV uses exact "True"/"False"
        ]
        cols = ["Applications: Education", "Harms: Discrimination"]
        vectors = compute_taxonomy_jaccard(rows, cols)
        assert vectors["1"] == {"Applications: Education"}
        assert vectors["2"] == {"Harms: Discrimination"}

    def test_collections_sets(self):
        rows = [
            {"AGORA ID": "1", "Collections": "AI Policy; Ethics"},
            {"AGORA ID": "2", "Collections": "Defense"},
        ]
        sets = compute_collections_sets(rows)
        assert sets["1"] == {"AI Policy", "Ethics"}
        assert sets["2"] == {"Defense"}

    def test_label_community(self):
        tax_vecs = {
            "1": {"Applications: Education", "Strategies: Governance"},
            "2": {"Applications: Education", "Strategies: Evaluation"},
            "3": {"Applications: Education", "Harms: Discrimination"},
        }
        label, sig = label_community({"1", "2", "3"}, tax_vecs)
        assert "Applications: Education" in label
        assert "Applications: Education" in sig  # 100% prevalence

    def test_inspect_communities(self):
        records = [
            CommunityRecord(
                community_id="community:001",
                label="Education | Governance",
                member_agora_ids=["1", "2", "3"],
                dominant_party="R",
            ),
        ]
        output = inspect_communities(records)
        assert "community:001" in output
        assert "3" in output  # size


# ---------------------------------------------------------------------------
# NER agent tests
# ---------------------------------------------------------------------------

from pipeline.agents.ner_agent import (
    chunk_text,
    compute_is_new,
    is_generic,
    merge_chunk_results,
    validate_ner_output,
    update_memory,
    _build_memory_context,
)
from pipeline.agents.models_agent import CommunityMemory, EntityRecord


class TestNERChunking:
    def test_short_text_no_split(self):
        assert chunk_text("Hello world", max_chunk=100) == ["Hello world"]

    def test_empty_text(self):
        assert chunk_text("") == []

    def test_section_split(self):
        text = textwrap.dedent("""\
            SEC. 101. First section.
            Content of first section.

            SEC. 102. Second section.
            Content of second section.
        """)
        # max_chunk must be below the combined length so the section-split path runs;
        # text shorter than max_chunk returns a single chunk (see test_short_text_no_split).
        chunks = chunk_text(text, max_chunk=80)
        assert len(chunks) == 2
        assert "SEC. 101" in chunks[0]
        assert "SEC. 102" in chunks[1]

    def test_large_section_subsection_split(self):
        # Build a section larger than max_chunk
        text = "SEC. 1. Big section.\n" + ("x" * 100 + "\n") * 100
        chunks = chunk_text(text, max_chunk=500)
        assert len(chunks) > 1


class TestIsNew:
    def test_new_entity(self):
        mem = CommunityMemory(community_id="test")
        assert compute_is_new("New Org", "organizations", mem) is True

    def test_existing_entity(self):
        mem = CommunityMemory(community_id="test")
        mem.entity_roster["organizations"] = [{"name": "Department of Defense"}]
        assert compute_is_new("Department of Defense", "organizations", mem) is False

    def test_case_insensitive(self):
        mem = CommunityMemory(community_id="test")
        mem.entity_roster["organizations"] = [{"name": "Department of Defense"}]
        assert compute_is_new("department of defense", "organizations", mem) is False

    def test_canonical_match(self):
        mem = CommunityMemory(community_id="test")
        mem.entity_roster["organizations"] = [{"name": "Department of Defense"}]
        assert compute_is_new("dod", "organizations", mem) is False

    def test_role_uses_title(self):
        mem = CommunityMemory(community_id="test")
        mem.entity_roster["roles"] = [{"title": "Secretary of Defense"}]
        assert compute_is_new("Secretary of Defense", "roles", mem) is False


class TestGenericFilter:
    def test_generic_term(self):
        assert is_generic("federal agencies", set()) is True

    def test_short_term(self):
        assert is_generic("DOD", set()) is True  # len < 5

    def test_resolved_term_passes(self):
        assert is_generic("the committee", {"the committee"}) is False

    def test_normal_term_passes(self):
        assert is_generic("Department of Defense", set()) is False


class TestMergeChunks:
    def test_merge_deduplicates(self):
        chunk1 = {
            "organizations": [{"name": "DoD", "acronym": "DoD"}],
            "offices": [], "roles": [], "legislation_refs": [], "named_docs": [],
            "disambiguation_updates": {}, "new_parsing_rule": None, "oddity": None,
        }
        chunk2 = {
            "organizations": [{"name": "DoD", "acronym": "DoD"}, {"name": "NIST"}],
            "offices": [], "roles": [], "legislation_refs": [], "named_docs": [],
            "disambiguation_updates": {}, "new_parsing_rule": None, "oddity": None,
        }
        merged = merge_chunk_results([chunk1, chunk2])
        assert len(merged["organizations"]) == 2  # DoD + NIST


class TestValidation:
    def test_valid_output(self):
        data = {
            "organizations": [], "offices": [], "roles": [],
            "legislation_refs": [], "named_docs": [],
        }
        assert validate_ner_output(data) is True

    def test_missing_key(self):
        data = {"organizations": [], "offices": []}
        assert validate_ner_output(data) is False

    def test_wrong_type(self):
        data = {
            "organizations": "not a list", "offices": [], "roles": [],
            "legislation_refs": [], "named_docs": [],
        }
        assert validate_ner_output(data) is False


class TestMemoryUpdate:
    def test_update_adds_new_entity(self):
        mem = CommunityMemory(community_id="test")
        rec = EntityRecord(
            agora_id="1",
            organizations=[{"name": "DARPA", "acronym": "DARPA"}],
        )
        update_memory(mem, rec)
        assert len(mem.entity_roster["organizations"]) == 1
        assert mem.entity_roster["organizations"][0]["name"] == "DARPA"
        assert mem.docs_processed == 1

    def test_update_increments_mentions(self):
        mem = CommunityMemory(community_id="test")
        mem.entity_roster["organizations"] = [{"name": "DARPA", "mentions": 1}]
        rec = EntityRecord(
            agora_id="2",
            organizations=[{"name": "DARPA"}],
        )
        update_memory(mem, rec)
        assert mem.entity_roster["organizations"][0]["mentions"] == 2

    def test_disambiguation_update(self):
        mem = CommunityMemory(community_id="test")
        rec = EntityRecord(
            agora_id="1",
            disambiguation_updates={"the department": "Department of Defense"},
        )
        update_memory(mem, rec)
        assert mem.disambiguation_rules["the department"] == "Department of Defense"

    def test_parsing_rule_added(self):
        mem = CommunityMemory(community_id="test")
        rec = EntityRecord(
            agora_id="1",
            new_parsing_rule="NDAA sections use (A)-(K) items",
        )
        update_memory(mem, rec)
        assert len(mem.parsing_rules) == 1

    def test_oddity_added(self):
        mem = CommunityMemory(community_id="test")
        rec = EntityRecord(agora_id="1", oddity="Nested quotes style")
        update_memory(mem, rec)
        assert len(mem.oddities) == 1
        assert mem.oddities[0]["agora_id"] == "1"


class TestMemoryContext:
    def test_context_includes_label(self):
        mem = CommunityMemory(community_id="test", label="Defense & Military")
        ctx = _build_memory_context(mem)
        assert "Defense & Military" in ctx

    def test_context_includes_disambiguation(self):
        mem = CommunityMemory(
            community_id="test",
            disambiguation_rules={"the department": "DoD"},
        )
        ctx = _build_memory_context(mem)
        assert "the department" in ctx
        assert "DoD" in ctx


# ---------------------------------------------------------------------------
# Graph builder tests
# ---------------------------------------------------------------------------

from pipeline.agents.graph_builder import (
    build_layer1_sponsor,
    build_layer2_community,
    build_layer3_entity,
    combine_layers,
    compute_stats,
    export_graphml,
    _slugify,
)


class TestGraphBuilder:
    def test_slugify(self):
        assert _slugify("Department of Defense") == "department_of_defense"
        assert _slugify("NIST") == "nist"
        assert _slugify("") == "unknown"

    def test_layer1_from_files(self, tmp_path):
        # Write minimal sponsor files
        nodes_path = tmp_path / "sponsor_nodes.csv"
        nodes_path.write_text(
            "node_id,bioguide_id,full_name,last_name,first_name,party,state,district,chamber\n"
            "sponsor:B001,B001,Rep. Smith,Smith,John,R,TX,1,Rep\n"
        )
        edges_path = tmp_path / "sponsor_edges.csv"
        edges_path.write_text(
            "src_id,relation,dst_id,layer\n"
            "document:1,SPONSORED_BY,sponsor:B001,1\n"
        )
        G = build_layer1_sponsor(tmp_path)
        assert G.number_of_nodes() == 2  # sponsor + document
        assert G.number_of_edges() == 1

    def test_layer2_from_file(self, tmp_path):
        communities = [
            {
                "community_id": "community:001",
                "label": "Test",
                "taxonomy_signature": [],
                "dominant_party": "R",
                "member_agora_ids": ["1", "2"],
                "bill_groups": [],
                "doc_centrality": {"1": 0.8, "2": 0.5},
            },
        ]
        (tmp_path / "communities.json").write_text(json.dumps(communities))
        G = build_layer2_community(tmp_path)
        assert G.number_of_nodes() == 3  # community + 2 docs
        assert G.number_of_edges() == 2

    def test_layer3_from_entities(self, tmp_path):
        entities = [
            {
                "agora_id": "1",
                "organizations": [{"name": "DARPA", "acronym": "DARPA", "context": "test"}],
                "offices": [],
                "roles": [{"title": "Director", "org": "DARPA", "context": "test"}],
                "legislation_refs": [],
                "named_docs": [],
            },
        ]
        entities_path = tmp_path / "entities.jsonl"
        entities_path.write_text("\n".join(json.dumps(e) for e in entities) + "\n")
        G = build_layer3_entity(tmp_path)
        assert G.number_of_nodes() == 3  # doc + org + role
        assert G.number_of_edges() == 2

    def test_combine_layers(self):
        import networkx as nx
        g1 = nx.MultiDiGraph()
        g1.add_node("document:1", node_type="Document", layer=1)
        g1.add_node("sponsor:B001", node_type="Sponsor", layer=1)
        g1.add_edge("document:1", "sponsor:B001", relation="SPONSORED_BY")

        g2 = nx.MultiDiGraph()
        g2.add_node("document:1", node_type="Document", layer=2)
        g2.add_node("community:001", node_type="Community", layer=2)
        g2.add_edge("document:1", "community:001", relation="IN_COMMUNITY")

        combined = combine_layers(g1, g2)
        assert combined.number_of_nodes() == 3  # doc, sponsor, community
        assert combined.number_of_edges() == 2

    def test_export_graphml(self, tmp_path):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("n1", label="Test", layer=1, extra=None)
        G.add_edge("n1", "n1", relation="SELF")
        path = tmp_path / "test.graphml"
        export_graphml(G, path)
        assert path.exists()

    def test_compute_stats(self):
        import networkx as nx
        g1 = nx.MultiDiGraph()
        g1.add_node("a", node_type="Document")
        g1.add_edge("a", "a", relation="TEST")
        layers = {"layer_1": g1}
        combined = g1.copy()
        stats = compute_stats(layers, combined)
        assert stats["layers"]["layer_1"]["nodes"] == 1
        assert stats["combined"]["nodes"] == 1


# ---------------------------------------------------------------------------
# Models tests
# ---------------------------------------------------------------------------

from pipeline.agents.models_agent import CommunityMemory as CM


class TestCommunityMemoryModel:
    def test_add_parsing_rule_dedup(self):
        mem = CM(community_id="test")
        mem.add_parsing_rule("NDAA sections list members as A through K items")
        mem.add_parsing_rule("NDAA sections list members as A through K bulleted items")
        # Should dedup (>70% overlap) and keep longer
        assert len(mem.parsing_rules) == 1
        assert "bulleted" in mem.parsing_rules[0]

    def test_add_parsing_rule_different(self):
        mem = CM(community_id="test")
        mem.add_parsing_rule("Rule about section structure")
        mem.add_parsing_rule("Pattern for amendment formatting")
        assert len(mem.parsing_rules) == 2

    def test_parsing_rule_archiving(self):
        mem = CM(community_id="test")
        for i in range(10):
            mem.add_parsing_rule(f"Unique rule number {i} with distinct words_{i}")
        assert len(mem.parsing_rules) <= 7
        assert len(mem.archived_rules) > 0

    def test_roundtrip(self):
        mem = CM(
            community_id="test",
            label="Test",
            disambiguation_rules={"x": "y"},
        )
        d = mem.to_dict()
        mem2 = CM.from_dict(d)
        assert mem2.community_id == "test"
        assert mem2.disambiguation_rules == {"x": "y"}
