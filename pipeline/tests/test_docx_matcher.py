from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile

from agora.pipeline.docx_matcher import (
    extract_docx_text,
    fit_profile_vectorizer,
    hybrid_score,
    load_positive_profile,
    run_docx_match,
    score_docx_against_profile,
)
from agora.pipeline.ranker import RankConfig


def _write_minimal_docx(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)


class DocxMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agora_docx_matcher_test_"))
        self.profile_path = self.temp_dir / "profile.jsonl"
        self.docx_dir = self.temp_dir / "docx"
        self.out_json = self.temp_dir / "out.json"

        rows = [
            {"agora_id": "p1", "profile_text": "artificial intelligence safety standards for federal procurement"},
            {"agora_id": "p2", "profile_text": "housing finance program and urban development grants"},
        ]
        self.profile_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_docx_text_success_from_fixture(self) -> None:
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx not installed")
        p = self.docx_dir / "a.docx"
        _write_minimal_docx(p, "AI policy and safety")
        txt = extract_docx_text(p)
        self.assertIn("AI policy and safety", txt)

    def test_extract_docx_invalid_file_raises(self) -> None:
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx not installed")
        p = self.docx_dir / "bad.docx"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not a real docx", encoding="utf-8")
        with self.assertRaises(Exception):
            extract_docx_text(p)

    def test_semantic_score_bounds_and_ordering(self) -> None:
        profile_rows = load_positive_profile(self.profile_path)
        vec = fit_profile_vectorizer([r["profile_text"] for r in profile_rows])
        score, top = score_docx_against_profile(
            "This bill sets artificial intelligence safety standards for agencies",
            profile_rows,
            vec,
            max_profile_matches=2,
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertEqual("p1", top[0]["agora_id"])
        if len(top) > 1:
            self.assertGreaterEqual(float(top[0]["similarity"]), float(top[1]["similarity"]))

    def test_hybrid_score_composition_and_clamp(self) -> None:
        cfg = RankConfig(min_score_for_export=0.0, high_threshold=0.7, medium_threshold=0.4)
        score, keyword_score, _ = hybrid_score(
            "artificial intelligence machine learning oversight standards",
            "ai policy",
            semantic_score=1.0,
            cfg=cfg,
        )
        self.assertGreaterEqual(keyword_score, 0.0)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_run_docx_match_output_schema(self) -> None:
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx not installed")
        _write_minimal_docx(self.docx_dir / "good.docx", "AI governance and federal procurement safety standards.")
        (self.docx_dir / "good_text.txt").write_text("Artificial intelligence standards for agency procurement", encoding="utf-8")
        (self.docx_dir / "bad.docx").write_text("not a zip", encoding="utf-8")

        payload = run_docx_match(
            docx_dir=self.docx_dir,
            profile_jsonl=self.profile_path,
            out_json=self.out_json,
            top_k=50,
            cfg=RankConfig(min_score_for_export=0.0, high_threshold=0.7, medium_threshold=0.4),
            max_profile_matches=5,
        )
        self.assertTrue(self.out_json.exists())
        self.assertIn("summary", payload)
        self.assertIn("results", payload)
        self.assertIn("skipped", payload)
        self.assertGreaterEqual(payload["summary"]["docs_discovered"], 3)
        self.assertGreaterEqual(payload["summary"]["docs_parsed"], 2)
        self.assertGreaterEqual(payload["summary"]["docs_skipped"], 1)
        row = payload["results"][0]
        expected_keys = {
            "doc_id",
            "source_path",
            "text_sha256",
            "semantic_score",
            "keyword_score",
            "candidate_score",
            "candidate_tier",
            "matched_signals",
            "evidence_snippets",
            "top_profile_matches",
        }
        self.assertEqual(expected_keys, set(row.keys()))

    def test_run_docx_match_accepts_txt_only_directory(self) -> None:
        self.docx_dir.mkdir(parents=True, exist_ok=True)
        (self.docx_dir / "one.txt").write_text("AI policy and federal standards for risk management", encoding="utf-8")
        (self.docx_dir / "two.txt").write_text("General office schedule update", encoding="utf-8")
        payload = run_docx_match(
            docx_dir=self.docx_dir,
            profile_jsonl=self.profile_path,
            out_json=self.out_json,
            top_k=50,
            cfg=RankConfig(min_score_for_export=0.0, high_threshold=0.7, medium_threshold=0.4),
            max_profile_matches=3,
        )
        self.assertEqual(2, payload["summary"]["docs_discovered"])
        self.assertEqual(2, payload["summary"]["docs_parsed"])
        self.assertEqual(0, payload["summary"]["docs_skipped"])
        self.assertIn("supported_extensions", payload["params"])


if __name__ == "__main__":
    unittest.main()
