"""Product photos for the website, loaded live from the source sites.

Images are never written to the databases (FR-8). When the website shows a product, this
service looks up the picture on the product's source site and keeps the link in memory only.
API sources (DummyJSON, Fake Store API) return the photo links of all their products in a
single request; HTML sites need one product-page request per product. All requests go
through the polite fetcher (robots.txt and rate limits).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.db.models import Product

log = logging.getLogger(__name__)

CACHE_SECONDS = 6 * 3600


class MediaService:
    def __init__(self, fetch: Callable[[str], str], websites: dict[str, list[dict]]):
        self.fetch = fetch
        self.sites = {(category, site["name"]): site
                      for category, sites in websites.items() for site in sites}
        self._bulk: dict[str, tuple[float, dict[str, list[str]]]] = {}
        self._pages: dict[str, tuple[float, list[str]]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def images_for(self, product: Product) -> list[str]:
        site = self.sites.get((product.category, product.source_site))
        if site is None:
            return []
        try:
            parser = site.get("parser")
            if parser in ("dummyjson", "fakestore"):
                return self._bulk_index(site).get(product.product_url, [])
            if parser in ("web_scraping_dev", "webscraper_io"):
                return self._page_images(product.product_url, parser)
        except Exception as exc:  # the product view still works without a photo
            log.warning("No photo for %s: %s", product.product_url, exc)
        return []

    # ------------------------------------------------------------- API sources
    def _bulk_index(self, site: dict) -> dict[str, list[str]]:
        base = site["base_url"].rstrip("/")
        with self._lock(base):
            cached = self._bulk.get(base)
            if cached and time.time() - cached[0] < CACHE_SECONDS:
                return cached[1]
            index: dict[str, list[str]] = {}
            if site["parser"] == "dummyjson":
                data = json.loads(self.fetch(f"{base}/products?limit=0&select=thumbnail,images"))
                for p in data.get("products", []):
                    images = [p.get("thumbnail")] + list(p.get("images") or [])
                    index[f"{base}/products/{p['id']}"] = _unique(images)
            else:  # fakestore
                for p in json.loads(self.fetch(f"{base}/products")):
                    index[f"{base}/products/{p['id']}"] = _unique([p.get("image")])
            self._bulk[base] = (time.time(), index)
            return index

    # ------------------------------------------------------------- HTML sites
    def _page_images(self, url: str, parser: str) -> list[str]:
        cached = self._pages.get(url)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1]
        with self._lock(url):
            cached = self._pages.get(url)
            if cached and time.time() - cached[0] < CACHE_SECONDS:
                return cached[1]
            soup = BeautifulSoup(self.fetch(url), "html.parser")
            if parser == "web_scraping_dev":
                tags = soup.select(".product-images img.product-img") or soup.select(".product-images img")
            else:
                tags = soup.select(".product-wrapper img.image") or soup.select(".product-wrapper img")
            images = _unique([urljoin(url, t.get("src", "")) for t in tags if t.get("src")])
            self._pages[url] = (time.time(), images)
            return images


def _unique(items: list) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item and isinstance(item, str) and item not in seen:
            seen.append(item)
    return seen
