"""Base scraper shared by the three domain agents."""
from __future__ import annotations

from typing import Callable

from app.scrapers.parsers import PARSERS
from app.text_utils import normalize


class BaseScraper:
    category: str = ""
    # Ordered: the first sub-category whose keyword appears in the product name wins.
    SUB_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = []

    def __init__(self, sites: list[dict], fetch: Callable[[str], str]):
        self.sites = sites
        self.fetch = fetch

    def scrape(self, site: dict) -> list[dict]:
        parser = PARSERS.get(site.get("parser", ""))
        if parser is None:
            raise ValueError(f"Unknown parser '{site.get('parser')}' for site {site.get('name')}")
        raw_items = parser(site, self.fetch)
        items: list[dict] = []
        seen: set[tuple[str, float]] = set()
        for item in raw_items:
            if not item.get("name") or not item.get("url"):
                continue
            key = (normalize(item["name"]), float(item["price"]))
            if key in seen:  # some practice sites repeat the same product under several ids
                continue
            seen.add(key)
            item["source_site"] = site["name"]
            item["sub_category"] = self.infer_sub_category(item)
            items.append(item)
        return items

    def infer_sub_category(self, item: dict) -> str:
        name = normalize(item.get("name", ""))
        for sub_category, keywords in self.SUB_CATEGORY_KEYWORDS:
            if any(_has_word(name, normalize(k)) for k in keywords):
                return sub_category
        return item.get("sub_category_hint") or self.category


def _has_word(text: str, keyword: str) -> bool:
    import re
    return re.search(rf"\b{re.escape(keyword)}", text) is not None
