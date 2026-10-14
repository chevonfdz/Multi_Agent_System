"""JSON product APIs (free demo data services). Image fields in the responses are ignored."""
from __future__ import annotations

import json
from typing import Callable
from urllib.parse import quote

from app.scrapers.parsers.common import clean, parse_price, short

# Ask DummyJSON for text fields only, so no image URLs are even downloaded.
DUMMYJSON_FIELDS = "title,price,brand,description,rating,stock,availabilityStatus,tags,warrantyInformation,sku"


def parse_dummyjson(site: dict, fetch: Callable[[str], str]) -> list[dict]:
    base = site["base_url"].rstrip("/")
    items: list[dict] = []
    for cat in site.get("categories", []):
        url = f"{base}/products/category/{quote(cat['name'])}?limit=0&select={DUMMYJSON_FIELDS}"
        data = json.loads(fetch(url))
        for p in data.get("products", []):
            price = parse_price(p.get("price"))
            if price is None or "id" not in p:
                continue
            status = str(p.get("availabilityStatus") or "").lower()
            out_of_stock = status == "out of stock" or p.get("stock") == 0
            items.append({
                "name": clean(p.get("title")),
                "url": f"{base}/products/{p['id']}",
                "price": price,
                "currency": "USD",
                "description": short(p.get("description") or ""),
                "brand": clean(p.get("brand")),
                "rating": p.get("rating"),
                "availability": "out_of_stock" if out_of_stock else "in_stock",
                "tags": [str(t) for t in (p.get("tags") or [])],
                "warranty": clean(p.get("warrantyInformation")),
                "sku": clean(p.get("sku")),
                "sub_category_hint": cat.get("sub_category"),
                "gender_hint": cat.get("gender"),
            })
    return items


def parse_fakestore(site: dict, fetch: Callable[[str], str]) -> list[dict]:
    base = site["base_url"].rstrip("/")
    items: list[dict] = []
    for cat in site.get("categories", []):
        url = f"{base}/products/category/{quote(cat['name'])}"
        data = json.loads(fetch(url))
        for p in data if isinstance(data, list) else []:
            price = parse_price(p.get("price"))
            if price is None or "id" not in p:
                continue
            rating = (p.get("rating") or {}).get("rate") if isinstance(p.get("rating"), dict) else None
            items.append({
                "name": clean(p.get("title")),
                "url": f"{base}/products/{p['id']}",
                "price": price,
                "currency": "USD",
                "description": short(p.get("description") or ""),
                "rating": rating,
                "sub_category_hint": cat.get("sub_category"),
                "gender_hint": cat.get("gender"),
            })
    return items
