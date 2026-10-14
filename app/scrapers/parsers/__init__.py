"""Site parsers. Each takes a site config (from websites.yaml) and a fetch(url) -> str
function, and returns raw product dicts with text fields only (images are never read)."""
from __future__ import annotations

from typing import Callable

from app.scrapers.parsers.apis import parse_dummyjson, parse_fakestore
from app.scrapers.parsers.html_sites import parse_web_scraping_dev, parse_webscraper_io

Parser = Callable[[dict, Callable[[str], str]], list[dict]]

PARSERS: dict[str, Parser] = {
    "web_scraping_dev": parse_web_scraping_dev,
    "webscraper_io": parse_webscraper_io,
    "dummyjson": parse_dummyjson,
    "fakestore": parse_fakestore,
}
