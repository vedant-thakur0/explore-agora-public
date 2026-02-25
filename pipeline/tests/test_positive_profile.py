from __future__ import annotations

from pathlib import Path
import csv
import json
import shutil
import tempfile
import unittest

from agora.pipeline.build_positive_profile import build_profile_text, run, text_sha


class PositiveProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agora_positive_profile_test_"))
        self.input_csv = self.temp_dir / "documents.csv"
        self.out_prefix = self.temp_dir / "datasets" / "agora_positive_profile_v1"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_rows(self, rows: list[dict[str, str]]) -> None:
        fields = [
            "AGORA ID",
            "Official name",
            "Casual name",
            "Link to document",
            "Authority",
            "Collections",
            "Most recent activity",
            "Most recent activity date",
            "Short summary",
            "Long summary",
            "Tags",
            "Official plaintext retrieved",
            "Official plaintext source",
        ]
        with self.input_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_profile_text_construction_order_and_normalization(self) -> None:
        txt = build_profile_text(
            official_name=" Official Name ",
            casual_name="Casual",
            short_summary="Short",
            long_summary="Long",
            tags="tag1;tag2",
            collections=["A", "B"],
            most_recent_activity="Enacted",
        )
        self.assertEqual("Official Name Casual Short Long tag1;tag2 A; B Enacted", txt)

    def test_run_builds_expected_schema_and_outputs(self) -> None:
        self._write_rows(
            [
                {
                    "AGORA ID": "1",
                    "Official name": "AI Act",
                    "Casual name": "AI Act",
                    "Link to document": "https://example.com/1",
                    "Authority": "Congress",
                    "Collections": "U.S. federal laws;AI",
                    "Most recent activity": "Enacted",
                    "Most recent activity date": "2025-01-01",
                    "Short summary": "A short summary",
                    "Long summary": "A long summary",
                    "Tags": "ai;governance",
                    "Official plaintext retrieved": "true",
                    "Official plaintext source": "https://example.com/txt1",
                }
            ]
        )

        result = run(self.input_csv, self.out_prefix)
        self.assertTrue(Path(result["jsonl"]).exists())
        self.assertTrue(Path(result["csv"]).exists())
        self.assertTrue(Path(result["report"]).exists())
        self.assertTrue(Path(result["lineage"]).exists())

        first = json.loads(Path(result["jsonl"]).read_text(encoding="utf-8").splitlines()[0])
        expected_keys = {
            "agora_id",
            "official_name",
            "casual_name",
            "link_to_document",
            "authority",
            "collections",
            "most_recent_activity",
            "most_recent_activity_date",
            "short_summary",
            "long_summary",
            "tags",
            "official_plaintext_retrieved",
            "official_plaintext_source",
            "profile_text",
            "profile_text_sha256",
            "label_agora_fit",
            "label_source",
            "snapshot_date",
            "record_origin",
        }
        self.assertEqual(expected_keys, set(first.keys()))
        self.assertEqual(1, first["label_agora_fit"])
        self.assertEqual("documents_csv", first["label_source"])

    def test_exclusion_logic_missing_id_and_missing_text(self) -> None:
        self._write_rows(
            [
                {
                    "AGORA ID": "",
                    "Official name": "Missing ID",
                    "Casual name": "",
                    "Link to document": "",
                    "Authority": "",
                    "Collections": "",
                    "Most recent activity": "",
                    "Most recent activity date": "",
                    "Short summary": "",
                    "Long summary": "",
                    "Tags": "",
                    "Official plaintext retrieved": "",
                    "Official plaintext source": "",
                },
                {
                    "AGORA ID": "2",
                    "Official name": "",
                    "Casual name": "",
                    "Link to document": "",
                    "Authority": "",
                    "Collections": "",
                    "Most recent activity": "",
                    "Most recent activity date": "",
                    "Short summary": "",
                    "Long summary": "",
                    "Tags": "",
                    "Official plaintext retrieved": "",
                    "Official plaintext source": "",
                },
                {
                    "AGORA ID": "3",
                    "Official name": "Valid",
                    "Casual name": "",
                    "Link to document": "",
                    "Authority": "",
                    "Collections": "",
                    "Most recent activity": "",
                    "Most recent activity date": "",
                    "Short summary": "",
                    "Long summary": "",
                    "Tags": "",
                    "Official plaintext retrieved": "",
                    "Official plaintext source": "",
                },
            ]
        )
        result = run(self.input_csv, self.out_prefix)
        report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
        self.assertEqual(1, report["rows_kept"])
        self.assertEqual(1, report["exclusions"]["missing_agora_id"])
        self.assertEqual(1, report["exclusions"]["missing_text_fields"])

    def test_dedup_keeps_longest_profile_text_for_same_agora_id(self) -> None:
        self._write_rows(
            [
                {
                    "AGORA ID": "7",
                    "Official name": "Short",
                    "Casual name": "",
                    "Link to document": "",
                    "Authority": "",
                    "Collections": "",
                    "Most recent activity": "",
                    "Most recent activity date": "",
                    "Short summary": "",
                    "Long summary": "",
                    "Tags": "",
                    "Official plaintext retrieved": "false",
                    "Official plaintext source": "",
                },
                {
                    "AGORA ID": "7",
                    "Official name": "Longer Official Name",
                    "Casual name": "With extra context",
                    "Link to document": "",
                    "Authority": "",
                    "Collections": "AI",
                    "Most recent activity": "Enacted",
                    "Most recent activity date": "",
                    "Short summary": "Extra summary",
                    "Long summary": "",
                    "Tags": "governance",
                    "Official plaintext retrieved": "true",
                    "Official plaintext source": "",
                },
            ]
        )
        result = run(self.input_csv, self.out_prefix)
        rows = [json.loads(line) for line in Path(result["jsonl"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(rows))
        self.assertIn("Longer Official Name", rows[0]["profile_text"])
        report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
        self.assertEqual(1, report["duplicate_rows_dropped"])
        self.assertEqual(0, report["duplicate_agora_id_after_dedup"])

    def test_profile_hash_is_stable(self) -> None:
        content = "some normalized text"
        self.assertEqual(text_sha(content), text_sha(content))
        self.assertNotEqual(text_sha(content), text_sha(content + " x"))


if __name__ == "__main__":
    unittest.main()
