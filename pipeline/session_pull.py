from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
import time


USER_AGENT = "agora-candidate-pipeline/1.0"


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
class SessionPullConfig:
    congress: int
    bill_type: str = "hr"
    limit: int = 250
    delay_sec: float = 0.2
    api_url_base: str = "https://api.congress.gov/v3/bill"
    api_key: str = ""


def _http_get_json(url: str, params: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    query = urlencode(params)
    sep = "&" if "?" in url else "?"
    req = Request(f"{url}{sep}{query}", headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    if "<html" in body.lower():
        parser = _HTMLStripper()
        parser.feed(body)
        return parser.get_text()
    return body


def _extract_bill_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    bills = payload.get("bills") or payload.get("items") or []
    return [b for b in bills if isinstance(b, dict)]


def _clean_segment(value: str | int) -> str:
    return quote(str(value).strip(), safe="")


def _clean_bill_type(value: str) -> str:
    return quote((value or "").strip().lower(), safe="")


def build_list_url(api_url_base: str, congress: str | int, bill_type: str) -> str:
    base = str(api_url_base or "").rstrip("/")
    return f"{base}/{_clean_segment(congress)}/{_clean_bill_type(bill_type)}"


def build_text_url(api_url_base: str, congress: str | int, bill_type: str, number: str | int) -> str:
    base = str(api_url_base or "").rstrip("/")
    return f"{base}/{_clean_segment(congress)}/{_clean_bill_type(bill_type)}/{_clean_segment(number)}/text"


def _pick_text_url(text_payload: dict[str, Any]) -> tuple[str, str]:
    text_versions = text_payload.get("textVersions") or []
    if not text_versions or not isinstance(text_versions[0], dict):
        return "", ""
    latest = text_versions[0]
    formats = latest.get("formats") or []
    preferred = ["formatted text", "formatted xml", "xml", "pdf"]
    for want in preferred:
        for fmt in formats:
            if not isinstance(fmt, dict):
                continue
            typ = str(fmt.get("type") or "").lower()
            if typ == want and fmt.get("url"):
                if want == "formatted text":
                    return str(fmt["url"]), "plain"
                if want in {"formatted xml", "xml"}:
                    return str(fmt["url"]), "xml"
                if want == "pdf":
                    return str(fmt["url"]), "pdf"
    fallback = str(latest.get("url") or "")
    return fallback, ("html" if fallback else "")


def pull_bill_names(cfg: SessionPullConfig) -> list[dict[str, Any]]:
    endpoint = build_list_url(cfg.api_url_base, cfg.congress, cfg.bill_type)
    out: list[dict[str, Any]] = []
    offset = 0
    per_page = min(250, max(1, cfg.limit))

    while len(out) < cfg.limit:
        payload = _http_get_json(
            endpoint,
            {
                "api_key": cfg.api_key,
                "format": "json",
                "limit": str(per_page),
                "offset": str(offset),
            },
        )
        page = _extract_bill_list(payload)
        if not page:
            break
        out.extend(page)
        offset += len(page)
        if len(page) < per_page:
            break
    return out[: cfg.limit]


def fetch_bill_text(congress: str | int, bill_type: str, number: str | int, api_key: str, api_url_base: str) -> tuple[str, str, str]:
    endpoint = build_text_url(api_url_base, congress, bill_type, number)
    payload = _http_get_json(endpoint, {"api_key": api_key, "format": "json"})
    text_url, source_type = _pick_text_url(payload)
    if not text_url:
        return "", "", ""
    text = _http_get_text(text_url)
    return text, text_url, source_type


def process_and_save(cfg: SessionPullConfig, output_file: Path) -> dict[str, Any]:
    if not cfg.api_key:
        raise ValueError("CONGRESS_API_KEY is required")

    bills = pull_bill_names(cfg)
    rows: list[dict[str, Any]] = []
    failed = 0
    with_text = 0

    for b in bills:
        congress = b.get("congress", cfg.congress)
        bill_type = str(b.get("type") or cfg.bill_type).lower()
        number = b.get("number") or ""
        title = b.get("title") or ""
        source_url = b.get("url") or ""
        err = ""
        full_text = ""
        text_source_url = ""
        text_source_type = ""
        try:
            full_text, text_source_url, text_source_type = fetch_bill_text(congress, bill_type, number, cfg.api_key, cfg.api_url_base)
        except Exception as exc:
            failed += 1
            err = f"{type(exc).__name__}: {exc}"
        if full_text:
            with_text += 1

        rows.append(
            {
                "congress": congress,
                "bill_type": bill_type,
                "number": str(number),
                "bill_number": f"{bill_type.upper()} {number}".strip(),
                "title": title,
                "source_url": source_url,
                "text_source_url": text_source_url,
                "text_source_type": text_source_type,
                "full_text": full_text,
                "fetch_error": err,
            }
        )
        if cfg.delay_sec > 0:
            time.sleep(cfg.delay_sec)

    payload = {
        "run_type": "session_text_pull",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "params": {
            "congress": cfg.congress,
            "bill_type": cfg.bill_type.lower(),
            "limit": cfg.limit,
            "delay_sec": cfg.delay_sec,
            "api_url_base": cfg.api_url_base,
        },
        "summary": {
            "bills_fetched": len(bills),
            "rows_output": len(rows),
            "rows_with_text": with_text,
            "rows_failed": failed,
        },
        "rows": rows,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload
