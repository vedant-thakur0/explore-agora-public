from __future__ import annotations

from pathlib import Path
import csv
import shutil
import tempfile
import unittest

from pipeline.knowledge_graph import run


class KnowledgeGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agora_kg_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_run_builds_nodes_and_edges(self) -> None:
        docs = self.temp_dir / "documents.csv"
        segs = self.temp_dir / "segments.csv"
        auth = self.temp_dir / "authorities.csv"
        cols = self.temp_dir / "collections.csv"
        out = self.temp_dir / "graph"

        self._write_csv(
            docs,
            fieldnames=[
                "AGORA ID",
                "Official name",
                "Casual name",
                "Authority",
                "Collections",
                "Tags",
                "Applications: Education",
            ],
            rows=[
                {
                    "AGORA ID": "1",
                    "Official name": "AI in Schools Act",
                    "Casual name": "Schools AI",
                    "Authority": "US Federal",
                    "Collections": "Education;AI Policy",
                    "Tags": "ai;education",
                    "Applications: Education": "TRUE",
                }
            ],
        )
        self._write_csv(
            segs,
            fieldnames=[
                "Document ID",
                "Segment position",
                "Text",
                "Tags",
                "Summary",
                "Strategies: Evaluation",
            ],
            rows=[
                {
                    "Document ID": "1",
                    "Segment position": "1",
                    "Text": "Segment text",
                    "Tags": "pilot;evaluation",
                    "Summary": "Summary text",
                    "Strategies: Evaluation": "TRUE",
                }
            ],
        )
        self._write_csv(
            auth,
            fieldnames=["Name", "Jurisdiction", "Parent authority"],
            rows=[{"Name": "US Federal", "Jurisdiction": "United States", "Parent authority": ""}],
        )
        self._write_csv(
            cols,
            fieldnames=["Name", "Description"],
            rows=[
                {"Name": "Education", "Description": "Education policies"},
                {"Name": "AI Policy", "Description": "AI policy collection"},
            ],
        )

        payload = run(docs, segs, auth, cols, out)

        self.assertGreater(payload["node_count"], 0)
        self.assertGreater(payload["edge_count"], 0)
        self.assertTrue((out / "nodes.csv").exists())
        self.assertTrue((out / "edges.csv").exists())
        self.assertTrue((out / "stats.json").exists())

        nodes_text = (out / "nodes.csv").read_text(encoding="utf-8")
        edges_text = (out / "edges.csv").read_text(encoding="utf-8")
        self.assertIn("Document", nodes_text)
        self.assertIn("Authority", nodes_text)
        self.assertIn("Collection", nodes_text)
        self.assertIn("Topic", nodes_text)
        self.assertIn("UNDER_AUTHORITY", edges_text)
        self.assertIn("IN_COLLECTION", edges_text)
        self.assertIn("HAS_SEGMENT", edges_text)
        self.assertIn("HAS_TOPIC", edges_text)


if __name__ == "__main__":
    unittest.main()
