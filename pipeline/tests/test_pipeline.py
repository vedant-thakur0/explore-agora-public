from __future__ import annotations

from pathlib import Path
import csv
import json
import shutil
import tempfile
import unittest

from agora.pipeline.congress import build_records
from agora.pipeline.ranker import RankConfig, TfidfCentroid, rank_records
from agora.pipeline.store import reviewed_decisions_index


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agora_pipeline_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_records_from_fixture_shape(self) -> None:
        fixture = Path("agora/pipeline/fixtures/sample_bills.json")
        bills = json.loads(fixture.read_text(encoding="utf-8"))
        records = build_records(bills)
        self.assertEqual(2, len(records))
        self.assertEqual("118-hr-9999", records[0].source_id)
        self.assertTrue(records[0].title.lower().startswith("artificial intelligence"))

    def test_build_records_from_bill_texts_shape(self) -> None:
        fixture = Path("agora/pipeline/fixtures/bill_texts.json")
        bills = json.loads(fixture.read_text(encoding="utf-8"))
        records = build_records(bills[:1])
        self.assertEqual(1, len(records))
        self.assertEqual("119-hr-144", records[0].source_id)
        self.assertEqual("hr", records[0].bill_type)
        self.assertEqual("144", records[0].bill_number)
        self.assertEqual("full", records[0].extraction_quality)
        self.assertIn("SECTION 1. SHORT TITLE.", records[0].text)

    def test_ranker_scores_ai_doc_higher(self) -> None:
        from agora.pipeline.models import DocumentRecord

        rec_ai = DocumentRecord(
            source_id="118-hr-1",
            source_url="https://example.com/1",
            title="AI Safety",
            bill_type="hr",
            committees=["House Committee on Science, Space, and Technology"],
            text="This bill establishes artificial intelligence risk management standards and external audit requirements.",
        )
        rec_non = DocumentRecord(
            source_id="118-s-2",
            source_url="https://example.com/2",
            title="Road Repair",
            bill_type="s",
            committees=["Transportation"],
            text="This bill funds bridge maintenance and highway resurfacing projects.",
        )

        vec = TfidfCentroid.fit([
            "artificial intelligence standards for risk management and federal transparency",
            "machine learning evaluation safety and security practices",
        ])
        ranked = rank_records("run1", [rec_non, rec_ai], vec, RankConfig(min_score_for_export=0.0))
        self.assertGreaterEqual(ranked[0].candidate_score, ranked[1].candidate_score)
        self.assertEqual("118-hr-1", ranked[0].source_id)

    def test_ranker_uses_title_in_scoring(self) -> None:
        from agora.pipeline.models import DocumentRecord

        rec_title_ai = DocumentRecord(
            source_id="118-hr-3",
            source_url="https://example.com/3",
            title="Artificial Intelligence Accountability Act",
            bill_type="hr",
            text="General appropriations and administration language.",
        )
        rec_plain = DocumentRecord(
            source_id="118-hr-4",
            source_url="https://example.com/4",
            title="General Appropriations Act",
            bill_type="hr",
            text="General appropriations and administration language.",
        )
        vec = TfidfCentroid.fit(
            [
                "artificial intelligence accountability safety transparency",
                "machine learning governance and oversight",
            ]
        )
        ranked = rank_records("run1", [rec_plain, rec_title_ai], vec, RankConfig(min_score_for_export=0.0))
        self.assertEqual("118-hr-3", ranked[0].source_id)

    def test_reviewed_index_reads_only_decided_rows(self) -> None:
        from agora.pipeline import store

        review_dir = self.temp_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_csv = review_dir / "sample.csv"
        with review_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["source_id", "text_sha256", "decision"],
            )
            writer.writeheader()
            writer.writerow({"source_id": "118-hr-1", "text_sha256": "abc", "decision": "include"})
            writer.writerow({"source_id": "118-hr-2", "text_sha256": "def", "decision": ""})

        original = store.REVIEW_EXPORTS_DIR
        store.REVIEW_EXPORTS_DIR = review_dir
        try:
            idx = reviewed_decisions_index()
            self.assertIn(("118-hr-1", "abc"), idx)
            self.assertNotIn(("118-hr-2", "def"), idx)
        finally:
            store.REVIEW_EXPORTS_DIR = original


if __name__ == "__main__":
    unittest.main()
