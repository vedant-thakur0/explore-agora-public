from __future__ import annotations

import unittest

from agora.pipeline.session_pull import (
    _extract_bill_list,
    _pick_text_url,
    build_list_url,
    build_text_url,
    fetch_bill_text,
    pull_bill_names,
    SessionPullConfig,
)
from unittest.mock import patch


class SessionPullTests(unittest.TestCase):
    def test_build_list_url_shape(self) -> None:
        url = build_list_url("https://api.congress.gov/v3/bill", 118, "HR")
        self.assertEqual("https://api.congress.gov/v3/bill/118/hr", url)

    def test_build_list_url_normalizes_base_and_whitespace(self) -> None:
        url = build_list_url("https://api.congress.gov/v3/bill/", " 118 ", " HR ")
        self.assertEqual("https://api.congress.gov/v3/bill/118/hr", url)

    def test_build_text_url_shape(self) -> None:
        url = build_text_url("https://api.congress.gov/v3/bill", 118, "HR", 144)
        self.assertEqual("https://api.congress.gov/v3/bill/118/hr/144/text", url)

    def test_build_text_url_normalizes_base_and_whitespace(self) -> None:
        url = build_text_url("https://api.congress.gov/v3/bill/", " 118 ", " HR ", " 144 ")
        self.assertEqual("https://api.congress.gov/v3/bill/118/hr/144/text", url)

    def test_extract_bill_list_from_bills_key(self) -> None:
        payload = {"bills": [{"number": "1"}, {"number": "2"}, "x"]}
        out = _extract_bill_list(payload)
        self.assertEqual(2, len(out))
        self.assertEqual("1", out[0]["number"])

    def test_extract_bill_list_from_items_key(self) -> None:
        payload = {"items": [{"number": "9"}]}
        out = _extract_bill_list(payload)
        self.assertEqual(1, len(out))
        self.assertEqual("9", out[0]["number"])

    def test_pick_text_url_prefers_formatted_text(self) -> None:
        payload = {
            "textVersions": [
                {
                    "formats": [
                        {"type": "PDF", "url": "https://example.com/a.pdf"},
                        {"type": "Formatted Text", "url": "https://example.com/a.txt"},
                    ]
                }
            ]
        }
        url, typ = _pick_text_url(payload)
        self.assertEqual("https://example.com/a.txt", url)
        self.assertEqual("plain", typ)

    def test_pick_text_url_fallback_latest_url(self) -> None:
        payload = {
            "textVersions": [
                {
                    "url": "https://example.com/version",
                    "formats": [],
                }
            ]
        }
        url, typ = _pick_text_url(payload)
        self.assertEqual("https://example.com/version", url)
        self.assertEqual("html", typ)

    @patch("agora.pipeline.session_pull._http_get_text")
    @patch("agora.pipeline.session_pull._http_get_json")
    def test_fetch_bill_text_calls_expected_text_endpoint(self, mock_json, mock_text) -> None:
        mock_json.return_value = {
            "textVersions": [
                {
                    "formats": [
                        {"type": "Formatted Text", "url": "https://example.com/bill.txt"},
                    ]
                }
            ]
        }
        mock_text.return_value = "bill body"

        text, text_url, source_type = fetch_bill_text(
            congress=118,
            bill_type="HR",
            number=144,
            api_key="k",
            api_url_base="https://api.congress.gov/v3/bill",
        )
        self.assertEqual("bill body", text)
        self.assertEqual("https://example.com/bill.txt", text_url)
        self.assertEqual("plain", source_type)
        mock_json.assert_called_once_with(
            "https://api.congress.gov/v3/bill/118/hr/144/text",
            {"api_key": "k", "format": "json"},
        )

    @patch("agora.pipeline.session_pull._http_get_json")
    def test_pull_bill_names_calls_expected_list_endpoint(self, mock_json) -> None:
        mock_json.return_value = {"bills": [{"number": "1", "type": "HR", "congress": 118}]}
        cfg = SessionPullConfig(congress=118, bill_type="HR", limit=1, api_key="k")
        out = pull_bill_names(cfg)
        self.assertEqual(1, len(out))
        mock_json.assert_called_once_with(
            "https://api.congress.gov/v3/bill/118/hr",
            {"api_key": "k", "format": "json", "limit": "1", "offset": "0"},
        )


if __name__ == "__main__":
    unittest.main()
