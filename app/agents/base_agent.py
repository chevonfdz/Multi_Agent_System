"""Base class for the three domain agents.

A domain agent owns its website list, its scraper and its product database (FR-5, FR-6).
It answers tasks from the central agent using only its own data (FR-4) and refreshes
that data every day (FR-7).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from typing import Any

from app.catalog_keywords import KEYWORDS
from app.db.models import AgentReply, Product, Task
from app.db.product_repository import ProductRepository
from app.scrapers.base_scraper import BaseScraper
from app.text_utils import format_price, normalize, stem

log = logging.getLogger(__name__)


def make_id(source_site: str, url: str) -> str:
    return hashlib.sha1(f"{source_site}|{url}".encode("utf-8")).hexdigest()


class BaseAgent:
    name: str = ""
    EXTRA_FIELDS: list[str] = []
    # Query term -> alternatives that mean the same thing in product data.
    SYNONYMS: dict[str, list[str]] = {}

    def __init__(self, repo: ProductRepository, scraper: BaseScraper, results_per_task: int = 5):
        self.repo = repo
        self.scraper = scraper
        self.results_per_task = results_per_task
        self._refresh_lock = threading.Lock()

    # ------------------------------------------------------------------ answering
    async def answer(self, task: Task, limit: int | None = None) -> AgentReply:
        started = time.perf_counter()
        products = await asyncio.to_thread(
            self.repo.search, task.query, task.filters, limit or self.results_per_task, self.SYNONYMS,
            self.product_types())
        last_updated = await asyncio.to_thread(self.repo.last_updated)
        latency = int((time.perf_counter() - started) * 1000)
        if not products:
            return AgentReply(self.name, "empty", [], "No matching products found.", last_updated,
                              query=task.query, filters=task.filters, latency_ms=latency)
        return AgentReply(self.name, "ok", products, self.summarize(products), last_updated,
                          query=task.query, filters=task.filters, latency_ms=latency)

    def product_types(self) -> set[str]:
        """Search terms that name a kind of product in this agent's category ("jacket", "power bank")."""
        words = KEYWORDS.get(self.name, [])
        return {normalize(w) for w in words if " " in w} | {stem(w) for w in words if " " not in w}

    def summarize(self, products: list[Product]) -> str:
        cheapest = min(products, key=lambda p: p.price)
        sites = sorted({p.source_site for p in products})
        return (f"{len(products)} matching product(s) from {', '.join(sites)}; the cheapest is "
                f"{cheapest.name} at {format_price(cheapest.price, cheapest.currency)}.")

    # ------------------------------------------------------------------ daily refresh
    def refresh_data(self) -> dict[str, Any]:
        """Scrape every site in this agent's list and update its database. A failing site
        keeps its previous data and does not stop the other sites."""
        if not self._refresh_lock.acquire(blocking=False):
            return {"agent": self.name, "skipped": "a refresh is already running"}
        summary: dict[str, Any] = {"agent": self.name, "sites": []}
        try:
            for site in self.scraper.sites:
                run_id = self.repo.start_run(site["name"])
                try:
                    raw_items = self.scraper.scrape(site)
                    products = [self.normalize(raw) for raw in raw_items]
                    self.repo.upsert_many(products)
                    self.repo.mark_missing_unavailable(site["name"], [p.product_id for p in products])
                    self.repo.finish_run(run_id, "ok", len(products))
                    summary["sites"].append({"site": site["name"], "status": "ok", "products": len(products)})
                    log.info("%s agent: scraped %d products from %s", self.name, len(products), site["name"])
                except Exception as exc:  # keep previous data, log and continue
                    self.repo.finish_run(run_id, "failed", 0, error=str(exc)[:500])
                    summary["sites"].append({"site": site["name"], "status": "failed", "error": str(exc)})
                    log.warning("%s agent: scrape of %s failed: %s", self.name, site["name"], exc)
        finally:
            self._refresh_lock.release()
        summary["total_products"] = self.repo.count()
        return summary

    def normalize(self, raw: dict) -> Product:
        return Product(
            product_id=make_id(raw["source_site"], raw["url"]),
            name=raw["name"],
            category=self.name,
            price=float(raw["price"]),
            currency=raw.get("currency") or "USD",
            product_url=raw["url"],
            source_site=raw["source_site"],
            availability=raw.get("availability") or "in_stock",
            sub_category=raw.get("sub_category") or "",
            brand=raw.get("brand") or "",
            description=raw.get("description") or "",
            rating=raw.get("rating"),
            extras=self.extract_extras(raw),
        )

    def extract_extras(self, raw: dict) -> dict[str, Any]:
        return {}
