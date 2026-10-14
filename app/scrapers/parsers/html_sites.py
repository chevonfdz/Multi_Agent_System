"""HTML parsers for the two scraping practice sites."""
from __future__ import annotations

from typing import Callable
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from app.scrapers.parsers.common import clean, parse_price, short


def parse_web_scraping_dev(site: dict, fetch: Callable[[str], str]) -> list[dict]:
    """web-scraping.dev/products?category=...&page=N  (cards: div.product)."""
    base = site["base_url"].rstrip("/")
    category = site.get("category", "")
    max_pages = int(site.get("max_pages", 10))
    items: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"{base}/products?category={quote(category)}&page={page}"
        soup = BeautifulSoup(fetch(url), "html.parser")
        cards = soup.select("div.product")
        new_on_page = 0
        for card in cards:
            link = card.select_one("h3 a")
            price_el = card.select_one(".price")
            if link is None or price_el is None:
                continue
            price = parse_price(price_el.get_text())
            href = urljoin(base + "/", link.get("href", ""))
            if price is None or href in seen_urls:
                continue
            seen_urls.add(href)
            new_on_page += 1
            desc = card.select_one(".short-description")
            items.append({
                "name": clean(link.get_text()),
                "url": href,
                "price": price,
                "currency": "USD",
                "description": short(desc.get_text() if desc else ""),
            })
        if not cards or new_on_page == 0:
            break
    return items


def parse_webscraper_io(site: dict, fetch: Callable[[str], str]) -> list[dict]:
    """webscraper.io/test-sites/e-commerce/allinone/...  (cards: div.thumbnail)."""
    base = site["base_url"].rstrip("/")
    items: list[dict] = []
    for listing in site.get("listing_pages", []):
        page_url = urljoin(base + "/", listing["path"].lstrip("/"))
        soup = BeautifulSoup(fetch(page_url), "html.parser")
        for card in soup.select("div.thumbnail"):
            title = card.select_one("a.title")
            price_el = card.select_one("[itemprop=price]") or card.select_one(".price")
            if title is None or price_el is None:
                continue
            price = parse_price(price_el.get_text())
            if price is None:
                continue
            desc = card.select_one(".description")
            rating_el = card.select_one("[data-rating]")
            rating = None
            if rating_el is not None:
                try:
                    rating = float(rating_el.get("data-rating"))
                except (TypeError, ValueError):
                    rating = None
            items.append({
                "name": clean(title.get("title") or title.get_text()),
                "url": urljoin(base + "/", title.get("href", "").lstrip("/")),
                "price": price,
                "currency": "USD",
                "description": short(desc.get_text() if desc else ""),
                "rating": rating,
                "sub_category_hint": listing.get("sub_category"),
            })
    return items
