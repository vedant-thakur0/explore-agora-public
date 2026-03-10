from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agora.pipeline.graph_query import get_neighborhood, run


class GraphQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agora_graph_query_test_"))
        self.graph_dir = self.temp_dir / "graph"
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.nodes_path = self.graph_dir / "nodes.csv"
        self.edges_path = self.graph_dir / "edges.csv"

        self._write_csv(
            self.nodes_path,
            ["node_id", "node_type", "label"],
            [
                {"node_id": "document:1", "node_type": "Document", "label": "Doc 1"},
                {"node_id": "segment:1_1", "node_type": "Segment", "label": "Seg 1"},
                {"node_id": "topic:ai", "node_type": "Topic", "label": "AI"},
                {"node_id": "tag:education", "node_type": "Tag", "label": "Education"},
                {"node_id": "authority:us_federal", "node_type": "Authority", "label": "US Federal"},
                {"node_id": "collection:policy", "node_type": "Collection", "label": "Policy"},
            ],
        )
        self._write_csv(
            self.edges_path,
            ["src_id", "relation", "dst_id"],
            [
                {"src_id": "document:1", "relation": "HAS_SEGMENT", "dst_id": "segment:1_1"},
                {"src_id": "document:1", "relation": "UNDER_AUTHORITY", "dst_id": "authority:us_federal"},
                {"src_id": "document:1", "relation": "IN_COLLECTION", "dst_id": "collection:policy"},
                {"src_id": "segment:1_1", "relation": "HAS_TOPIC", "dst_id": "topic:ai"},
                {"src_id": "segment:1_1", "relation": "HAS_TAG", "dst_id": "tag:education"},
            ],
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_returns_all_one_hop_neighbors(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=1,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["segment:1_1", "collection:policy", "authority:us_federal"], ids)
        self.assertEqual({"1": 3}, out["counts_by_hop"])
        self.assertTrue(out["ranking"]["enabled"])

    def test_returns_two_hop_without_duplicates(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("topic:ai", ids)
        self.assertIn("tag:education", ids)
        self.assertEqual({"1": 3, "2": 2}, out["counts_by_hop"])

    def test_honors_relation_filter(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            relation_filter={"HAS_SEGMENT", "HAS_TOPIC"},
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["segment:1_1", "topic:ai"], ids)

    def test_honors_node_type_filter(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            node_type_filter={"Topic"},
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["topic:ai"], ids)

    def test_missing_seed_node_errors(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            get_neighborhood(
                seed_node_id="document:missing",
                nodes_path=self.nodes_path,
                edges_path=self.edges_path,
            )
        self.assertIn("seed node not found", str(ctx.exception))

    def test_deterministic_ordering_and_limit(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            limit=2,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["segment:1_1", "collection:policy"], ids)

    def test_ranking_prefers_higher_weight_same_hop(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=1,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["segment:1_1", "collection:policy", "authority:us_federal"], ids)
        scores = {r["node_id"]: r["rank_score"] for r in out["neighbors"]}
        self.assertGreater(scores["segment:1_1"], scores["collection:policy"])
        self.assertGreater(scores["collection:policy"], scores["authority:us_federal"])

    def test_hop_decay_reduces_two_hop_score(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        one_hop = next(r for r in out["neighbors"] if r["node_id"] == "segment:1_1")
        two_hop = next(r for r in out["neighbors"] if r["node_id"] == "topic:ai")
        self.assertGreater(one_hop["rank_score"], two_hop["rank_score"])

    def test_unranked_restores_legacy_order(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=1,
            ranked=False,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["authority:us_federal", "collection:policy", "segment:1_1"], ids)
        self.assertFalse(out["ranking"]["enabled"])
        self.assertEqual("out", out["direction"])

    def test_inbound_direction_from_authority_finds_document(self) -> None:
        out = get_neighborhood(
            seed_node_id="authority:us_federal",
            max_hops=1,
            direction="in",
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertEqual(["document:1"], ids)
        self.assertEqual("in", out["direction"])

    def test_both_direction_expands_in_and_out(self) -> None:
        out = get_neighborhood(
            seed_node_id="authority:us_federal",
            max_hops=2,
            direction="both",
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        ids = [r["node_id"] for r in out["neighbors"]]
        self.assertIn("document:1", ids)
        self.assertIn("segment:1_1", ids)

    def test_path_explanation_shape(self) -> None:
        out = get_neighborhood(
            seed_node_id="document:1",
            max_hops=2,
            nodes_path=self.nodes_path,
            edges_path=self.edges_path,
        )
        topic_row = next(r for r in out["neighbors"] if r["node_id"] == "topic:ai")
        self.assertEqual(
            [
                {"from": "document:1", "relation": "HAS_SEGMENT", "to": "segment:1_1"},
                {"from": "segment:1_1", "relation": "HAS_TOPIC", "to": "topic:ai"},
            ],
            topic_row["path"],
        )
        json.dumps(out)  # must be JSON-serializable

    def test_run_wrapper_uses_graph_dir(self) -> None:
        out = run(
            graph_dir=self.graph_dir,
            seed_node_id="document:1",
            max_hops=1,
        )
        self.assertEqual("document:1", out["seed_node_id"])


class GraphQuerySmokeTests(unittest.TestCase):
    def test_smoke_real_graph_non_empty(self) -> None:
        graph_dir = Path("pipeline/graph")
        nodes_path = graph_dir / "nodes.csv"
        edges_path = graph_dir / "edges.csv"
        if not (nodes_path.exists() and edges_path.exists()):
            self.skipTest("pipeline/graph exports are not present")

        seed = None
        with nodes_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if (row.get("node_type") or "") == "Document":
                    seed = row.get("node_id")
                    break
        if not seed:
            self.skipTest("no Document node found in pipeline/graph/nodes.csv")

        out = run(graph_dir=graph_dir, seed_node_id=seed, max_hops=1, limit=50)
        self.assertGreater(len(out["neighbors"]), 0)
        self.assertIn("rank_score", out["neighbors"][0])
        scores = [r["rank_score"] for r in out["neighbors"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
