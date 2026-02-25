from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from .config import DEFAULT_API_URL
from .models import DocumentRecord, file_safe_id


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "\n".join(p.strip() for p in self._parts if p.strip())


@dataclass
class FetchResult:
    run_id: str
    raw_path: Path
    normalized_path: Path
    fetched: int


def _http_get_json(url: str, params: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    query = urlencode(params)
    sep = "&" if "?" in url else "?"
    req = Request(f"{url}{sep}{query}", headers={"Accept": "application/json", "User-Agent": "agora-candidate-pipeline/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "agora-candidate-pipeline/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    if "<html" in body.lower():
        parser = _HTMLStripper()
        parser.feed(body)
        return parser.get_text()
    return body


def _build_source_id(bill: dict[str, Any]) -> str:
    congress = str(bill.get("congress") or "")

    bill_type = str(bill.get("type") or "").lower()
    number = str(bill.get("number") or "")
    if (not bill_type or not number) and bill.get("bill_number"):
        bill_number = str(bill.get("bill_number") or "").strip().replace(".", " ")
        parts = [p for p in bill_number.split() if p]
        if len(parts) >= 2:
            bill_type = bill_type or parts[0].lower()
            number = number or parts[1]

    return f"{congress}-{bill_type}-{number}".strip("-")


def _normalize_bill_item(item: dict[str, Any]) -> DocumentRecord:
    bill_raw = item.get("bill", item)
    bill = bill_raw if isinstance(bill_raw, dict) else {}

    source_id = _build_source_id(bill)
    source_url = bill.get("url") or ""

    latest_title = bill.get("latestTitle")
    latest_title_dict = latest_title if isinstance(latest_title, dict) else {}
    title = bill.get("title") or latest_title_dict.get("title") or source_id

    latest_action_raw = bill.get("latestAction")
    latest_action = latest_action_raw if isinstance(latest_action_raw, dict) else {}

    sponsors = []
    sponsor_raw = bill.get("sponsors")
    sponsor_list = sponsor_raw if isinstance(sponsor_raw, list) else []
    for sp in sponsor_list:
        if isinstance(sp, dict):
            nm = sp.get("fullName") or sp.get("name")
            if nm:
                sponsors.append(str(nm))

    committees = []
    comm_raw = bill.get("committees")
    comm_list = comm_raw if isinstance(comm_raw, list) else []
    for cm in comm_list:
        if isinstance(cm, dict):
            nm = cm.get("name")
            if nm:
                committees.append(str(nm))

    text_versions_raw = bill.get("textVersions")
    text_versions = text_versions_raw if isinstance(text_versions_raw, list) else []
    text_url = ""
    text_source_type = ""
    if text_versions:
        latest = text_versions[0] if isinstance(text_versions[0], dict) else {}
        formats_raw = latest.get("formats")
        formats = formats_raw if isinstance(formats_raw, list) else []
        for fmt in formats:
            if not isinstance(fmt, dict):
                continue
            typ = str(fmt.get("type") or "").lower()
            if typ == "formatted text":
                text_url = str(fmt.get("url") or text_url)
                text_source_type = "plain"
                break
            if typ in ("formatted xml", "xml") and not text_url:
                text_url = str(fmt.get("url") or text_url)
                text_source_type = "xml"
            if typ in ("pdf",) and not text_url:
                text_url = str(fmt.get("url") or text_url)
                text_source_type = "pdf"
        if not text_url:
            text_url = str(latest.get("url") or "")
            text_source_type = "html"

    source_parts = source_id.split("-")
    source_bill_type = source_parts[1] if len(source_parts) >= 2 else ""
    source_bill_number = source_parts[2] if len(source_parts) >= 3 else ""

    record = DocumentRecord(
        source_id=source_id,
        source_url=source_url,
        title=title,
        congress=str(bill.get("congress") or ""),
        bill_type=str(bill.get("type") or "").lower() or source_bill_type,
        bill_number=str(bill.get("number") or "") or source_bill_number,
        latest_action_text=str(latest_action.get("text") or ""),
        latest_action_date=str(latest_action.get("actionDate") or ""),
        update_date=str(bill.get("updateDate") or ""),
        sponsors=sponsors,
        committees=committees,
        text_source_url=text_url,
        text_source_type=text_source_type,
    )
    # Test/fixture convenience: allow inline text when no network call is desired.
    fixture_text = bill.get("mockText") or item.get("mockText")
    if fixture_text:
        record.text = str(fixture_text)
        record.extraction_quality = "full"
        record.text_source_type = "fixture"
    fixture_full_text = bill.get("full_text") or item.get("full_text")
    if fixture_full_text:
        parser = _HTMLStripper()
        parser.feed(str(fixture_full_text))
        parsed = parser.get_text()
        record.text = parsed if parsed else str(fixture_full_text)
        record.extraction_quality = "full"
        record.text_source_type = "fixture_full_text"
    return record


def fetch_bills(
    since: str,
    limit: int,
    api_key: str,
    api_url: str = DEFAULT_API_URL,
    fixture_path: str | None = None,
) -> list[dict[str, Any]]:
    if fixture_path:
        return json.loads(Path(fixture_path).read_text(encoding="utf-8"))

    if not api_key:
        raise ValueError("CONGRESS_API_KEY is required unless --fixture-json is provided")

    payload = _http_get_json(
        api_url,
        {
            "api_key": api_key,
            "format": "json",
            "fromDateTime": f"{since}T00:00:00Z",
            "limit": str(limit),
        },
    )
    bills = payload.get("bills") or payload.get("items") or []
    return bills


def hydrate_text(record: DocumentRecord) -> DocumentRecord:
    if record.text:
        return record
    if not record.text_source_url:
        record.text = ""
        record.extraction_quality = "missing"
        return record

    try:
        text = _http_get_text(record.text_source_url)
    except Exception:
        text = ""

    if text:
        record.text = text
        record.extraction_quality = "full"
    else:
        record.text = ""
        record.extraction_quality = "failed"
    return record


def build_records(bills: list[dict[str, Any]]) -> list[DocumentRecord]:
    records = []
    for item in bills:
        rec = _normalize_bill_item(item)
        records.append(rec)
    return records


def fulltext_filename(source_id: str) -> str:
    return f"{file_safe_id(source_id)}.txt"


def new_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
