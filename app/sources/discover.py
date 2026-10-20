"""Find the files to download for a source by reading its index pages."""
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import settings
from app.periods import parse_period
from app.sources.registry import SourceSpec


@dataclass
class DiscoveredFile:
    url: str
    text: str
    page_url: str
    via: str  # discovered | seed_url


@dataclass
class DiscoveryResult:
    files: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    links_seen: list = field(default_factory=list)  # diagnostics when nothing matches


def get_html(url: str) -> str:
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=settings.http_timeout)
    resp.raise_for_status()
    return resp.text


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        text = " ".join(a.get_text(" ", strip=True).split())
        out.append((href, text))
    return out


def _matches(spec: SourceSpec, href: str, text: str) -> bool:
    if not spec.link_href_re and not spec.link_text_re:
        return False
    if spec.link_href_re and not re.search(spec.link_href_re, href):
        return False
    if spec.link_text_re and not re.search(spec.link_text_re, text):
        return False
    return True


def override_urls(spec: SourceSpec) -> list[str]:
    """Hand-supplied file URLs: env var SEED_URLS_<KEY>, comma separated. Wins over scraping."""
    raw = os.getenv(f"SEED_URLS_{spec.key.upper()}", "")
    return [u.strip() for u in raw.split(",") if u.strip().startswith("http")]


def discover(spec: SourceSpec, fetch_html=get_html) -> DiscoveryResult:
    result = DiscoveryResult()
    forced = override_urls(spec)
    if forced:
        result.notes.append(f"using {len(forced)} URL(s) from SEED_URLS_{spec.key.upper()}")
        result.files = [DiscoveredFile(url=u, text="override", page_url="", via="override") for u in forced]
        return result
    pages = list(spec.index_urls)

    if spec.child_href_re:
        children = []
        for page in pages:
            try:
                for href, text in extract_links(fetch_html(page), page):
                    if re.search(spec.child_href_re, href):
                        children.append((href, text))
            except Exception as exc:  # noqa: BLE001 - record and carry on
                result.notes.append(f"index page failed: {page}: {exc}")
        if children:
            def key(c):
                p = parse_period(c[0]) or parse_period(c[1])
                return p.sort if p else 0

            best = max(children, key=key)
            pages = [best[0]]
            result.notes.append(f"latest publication page: {best[0]}")
        else:
            result.notes.append("no publication page matched child_href_re")
            pages = []

    seen = set()
    for page in pages:
        try:
            html = fetch_html(page)
            links = extract_links(html, page)
        except Exception as exc:  # noqa: BLE001
            result.notes.append(f"page failed: {page}: {exc}")
            continue
        result.links_seen.extend([f"{t} -> {h}" for h, t in links][:80])
        if not links:
            result.notes.append(f"page returned {len(html)} bytes with no links: {page}")
        for href, text in links:
            if href in seen or not _matches(spec, href, text):
                continue
            seen.add(href)
            result.files.append(DiscoveredFile(url=href, text=text, page_url=page, via="discovered"))

    if not result.files and spec.seed_urls:
        result.notes.append("discovery found no files; using seed URLs confirmed by hand on 20 October 2026")
        for url in spec.seed_urls:
            result.files.append(DiscoveredFile(url=url, text="seed", page_url="", via="seed_url"))
    return result
