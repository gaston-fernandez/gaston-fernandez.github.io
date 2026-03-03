#!/usr/bin/env python3
"""Update per-paper Google Scholar citation counts for the research page."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

SCHOLAR_BASE_URL = "https://scholar.google.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class ScholarProfileParser(HTMLParser):
    """Extract title and citation count rows from a Google Scholar profile page."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[Dict[str, object]] = []
        self._in_publication_row = False
        self._capture_field: Optional[str] = None
        self._current_row: Dict[str, object] = {}
        self._text_buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_map = dict(attrs)
        classes = set(attrs_map.get("class", "").split())

        if tag == "tr" and "gsc_a_tr" in classes:
            self._in_publication_row = True
            self._current_row = {
                "title": "",
                "citations": 0,
                "scholar_url": None,
            }
            self._capture_field = None
            self._text_buffer = []
            return

        if not self._in_publication_row or tag != "a":
            return

        href = attrs_map.get("href")

        if "gsc_a_at" in classes:
            self._capture_field = "title"
            self._text_buffer = []
            if href:
                self._current_row["scholar_url"] = urljoin(SCHOLAR_BASE_URL, href)
            return

        if "gsc_a_ac" in classes:
            self._capture_field = "citations"
            self._text_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._text_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field and tag == "a":
            text = " ".join(part.strip() for part in self._text_buffer).strip()
            if self._capture_field == "title":
                self._current_row["title"] = text
            elif self._capture_field == "citations":
                if text:
                    digits = re.sub(r"[^0-9]", "", text)
                    self._current_row["citations"] = int(digits) if digits else 0
            self._capture_field = None
            self._text_buffer = []
            return

        if tag == "tr" and self._in_publication_row:
            title = str(self._current_row.get("title", "")).strip()
            if title:
                self.rows.append(self._current_row)
            self._in_publication_row = False
            self._capture_field = None
            self._text_buffer = []
            self._current_row = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Google Scholar citation counts for selected papers."
    )
    parser.add_argument(
        "--config",
        default="data/scholar_publications.json",
        help="Path to publications config JSON.",
    )
    parser.add_argument(
        "--output",
        default="data/scholar_citations.json",
        help="Path to output citations JSON.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum number of profile pages to scan (100 entries per page).",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=1.5,
        help="Delay between requests to reduce block risk.",
    )
    return parser.parse_args()


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_config(config_path: Path) -> Dict[str, object]:
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    if "profile_user_id" not in config:
        raise ValueError("Config is missing required key: profile_user_id")
    if "publications" not in config or not isinstance(config["publications"], list):
        raise ValueError("Config must contain a publications array")

    return config


def build_profile_url(user_id: str, start: int, page_size: int = 100) -> str:
    query = urlencode(
        {
            "user": user_id,
            "hl": "en",
            "cstart": start,
            "pagesize": page_size,
        }
    )
    return f"{SCHOLAR_BASE_URL}/citations?{query}"


def fetch_page(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def scrape_profile(user_id: str, max_pages: int, request_delay_seconds: float) -> List[Dict[str, object]]:
    all_rows: List[Dict[str, object]] = []
    page_size = 100

    for page in range(max_pages):
        start = page * page_size
        url = build_profile_url(user_id=user_id, start=start, page_size=page_size)
        html = fetch_page(url)

        lowered = html.lower()
        if "unusual traffic" in lowered or "not a robot" in lowered:
            raise RuntimeError(
                "Google Scholar blocked the request (possible CAPTCHA or anti-bot challenge)."
            )

        parser = ScholarProfileParser()
        parser.feed(html)

        if not parser.rows:
            break

        all_rows.extend(parser.rows)
        if len(parser.rows) < page_size:
            break

        if page < max_pages - 1 and request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    return all_rows


def choose_match(
    publication: Dict[str, object],
    profile_index: Dict[str, Dict[str, object]],
    normalized_titles: Iterable[str],
) -> Optional[Dict[str, object]]:
    title = str(publication.get("title", "")).strip()
    aliases = publication.get("aliases") or []

    candidates = [title]
    if isinstance(aliases, list):
        candidates.extend(str(alias) for alias in aliases)

    for candidate in candidates:
        normalized_candidate = normalize_title(candidate)
        if normalized_candidate and normalized_candidate in profile_index:
            return profile_index[normalized_candidate]

    if not title:
        return None

    normalized_title = normalize_title(title)
    if not normalized_title:
        return None

    fuzzy = difflib.get_close_matches(
        normalized_title,
        list(normalized_titles),
        n=1,
        cutoff=0.9,
    )
    if fuzzy:
        return profile_index[fuzzy[0]]

    return None


def build_output(
    config: Dict[str, object],
    profile_rows: List[Dict[str, object]],
) -> Dict[str, object]:
    publications = config["publications"]
    profile_index: Dict[str, Dict[str, object]] = {}

    for row in profile_rows:
        title = str(row.get("title", "")).strip()
        if not title:
            continue
        normalized = normalize_title(title)
        if not normalized:
            continue

        existing = profile_index.get(normalized)
        if existing is None or int(row.get("citations", 0)) > int(existing.get("citations", 0)):
            profile_index[normalized] = row

    normalized_titles = list(profile_index.keys())
    output_publications: Dict[str, Dict[str, object]] = {}

    matches = 0
    for publication in publications:
        key = str(publication.get("key", "")).strip()
        title = str(publication.get("title", "")).strip()
        if not key or not title:
            raise ValueError("Each publication in config must have non-empty 'key' and 'title'.")

        matched = choose_match(publication, profile_index, normalized_titles)

        if matched is not None:
            matches += 1
            output_publications[key] = {
                "title": title,
                "citations": int(matched.get("citations", 0)),
                "scholar_url": matched.get("scholar_url"),
                "matched_title": matched.get("title"),
            }
        else:
            output_publications[key] = {
                "title": title,
                "citations": None,
                "scholar_url": None,
                "matched_title": None,
            }

    if matches == 0:
        raise RuntimeError(
            "No configured publications were matched in the Scholar profile. "
            "Check titles in data/scholar_publications.json."
        )

    profile_user_id = str(config["profile_user_id"])
    return {
        "source": "Google Scholar",
        "profile_user_id": profile_user_id,
        "profile_url": (
            f"{SCHOLAR_BASE_URL}/citations?user={profile_user_id}&hl=en&oi=ao"
        ),
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "publications": output_publications,
    }


def write_output(output_path: Path, payload: Dict[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    output_path = Path(args.output)

    try:
        config = load_config(config_path)
        user_id = str(config["profile_user_id"]).strip()
        if not user_id:
            raise ValueError("profile_user_id must be a non-empty string")

        rows = scrape_profile(
            user_id=user_id,
            max_pages=args.max_pages,
            request_delay_seconds=args.request_delay_seconds,
        )
        if not rows:
            raise RuntimeError("No publication rows were parsed from Google Scholar.")

        payload = build_output(config=config, profile_rows=rows)
        write_output(output_path=output_path, payload=payload)

        total = len(payload["publications"])
        matched = sum(
            1
            for publication in payload["publications"].values()
            if publication.get("citations") is not None
        )
        print(
            f"Wrote {output_path} with {matched}/{total} matched publications "
            f"(rows parsed: {len(rows)})."
        )
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
