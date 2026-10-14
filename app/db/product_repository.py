"""Product database for one domain agent (food.db, clothes.db or electronics.db).

Only the owning agent uses its repository (FR-6). Products are text-only:
there is no image column and no image data is stored (FR-8, NFR-15).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.db.connection import connect, init_schema
from app.db.models import Product
from app.text_utils import content_terms, normalize, utc_now

COMMON_COLUMNS = [
    "product_id", "name", "category", "sub_category", "brand", "price", "currency",
    "description", "availability", "rating", "product_url", "source_site",
    "first_seen_at", "scraped_at",
]

# Field weights used to rank search results.
FIELD_WEIGHTS = {"name": 3, "sub_category": 3, "brand": 2, "extras": 1, "description": 1}


class ProductRepository:
    def __init__(self, db_path: Path, category: str, extra_fields: Iterable[str] = ()):
        self.db_path = Path(db_path)
        self.category = category
        self.extra_fields = list(extra_fields)
        self.init_schema()

    # ------------------------------------------------------------------ schema
    def init_schema(self) -> None:
        extra_cols = "".join(f",\n    {name} TEXT" for name in self.extra_fields)
        schema = f"""
        CREATE TABLE IF NOT EXISTS products (
            product_id    TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            category      TEXT NOT NULL,
            sub_category  TEXT,
            brand         TEXT,
            price         REAL NOT NULL,
            currency      TEXT NOT NULL,
            description   TEXT,
            availability  TEXT NOT NULL,
            rating        REAL,
            product_url   TEXT NOT NULL UNIQUE,
            source_site   TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            scraped_at    TEXT NOT NULL{extra_cols}
        );
        CREATE INDEX IF NOT EXISTS idx_products_site ON products(source_site);
        CREATE TABLE IF NOT EXISTS scrape_runs (
            run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            source_site    TEXT NOT NULL,
            started_at     TEXT NOT NULL,
            finished_at    TEXT,
            status         TEXT NOT NULL DEFAULT 'running',
            products_found INTEGER NOT NULL DEFAULT 0,
            error          TEXT
        );
        """
        init_schema(self.db_path, schema)

    # ------------------------------------------------------------------ writes
    def upsert_many(self, products: Iterable[Product]) -> int:
        now = utc_now()
        columns = COMMON_COLUMNS + self.extra_fields
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns
                            if c not in ("product_id", "first_seen_at"))
        sql = (f"INSERT INTO products ({', '.join(columns)}) VALUES ({placeholders}) "
               f"ON CONFLICT(product_id) DO UPDATE SET {updates}")
        count = 0
        with connect(self.db_path) as conn:
            for p in products:
                row = [p.product_id, p.name, self.category, p.sub_category, p.brand, float(p.price),
                       p.currency, p.description, p.availability, p.rating, p.product_url,
                       p.source_site, p.first_seen_at or now, now]
                for name in self.extra_fields:
                    value = p.extras.get(name)
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    row.append(None if value in (None, "") else str(value))
                # product_url is unique too; replace an older row that used a different id.
                conn.execute("DELETE FROM products WHERE product_url = ? AND product_id != ?",
                             (p.product_url, p.product_id))
                conn.execute(sql, row)
                count += 1
        return count

    def mark_missing_unavailable(self, source_site: str, seen_ids: Iterable[str]) -> int:
        """Products from a site that were not seen in its latest successful scrape."""
        seen = list(seen_ids)
        with connect(self.db_path) as conn:
            if seen:
                marks = ", ".join("?" for _ in seen)
                cur = conn.execute(
                    f"UPDATE products SET availability = 'unavailable' WHERE source_site = ? "
                    f"AND product_id NOT IN ({marks}) AND availability != 'unavailable'",
                    [source_site, *seen])
            else:
                cur = conn.execute(
                    "UPDATE products SET availability = 'unavailable' WHERE source_site = ? "
                    "AND availability != 'unavailable'", (source_site,))
            return cur.rowcount

    def start_run(self, source_site: str) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute("INSERT INTO scrape_runs (source_site, started_at) VALUES (?, ?)",
                               (source_site, utc_now()))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, products_found: int, error: str | None = None) -> None:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE scrape_runs SET finished_at = ?, status = ?, products_found = ?, "
                         "error = ? WHERE run_id = ?",
                         (utc_now(), status, products_found, error, run_id))

    def close_interrupted_runs(self) -> int:
        """Runs still marked "running" when the server starts were cut off by a shutdown."""
        with connect(self.db_path) as conn:
            cur = conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = ?, "
                               "error = 'interrupted: the server stopped during the scrape' "
                               "WHERE status = 'running'", (utc_now(),))
            return cur.rowcount

    # ------------------------------------------------------------------ reads
    def last_updated(self) -> str | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT MAX(finished_at) AS t FROM scrape_runs WHERE status = 'ok'").fetchone()
        return row["t"] if row else None

    def count(self, include_unavailable: bool = False) -> int:
        sql = "SELECT COUNT(*) AS n FROM products"
        if not include_unavailable:
            sql += " WHERE availability != 'unavailable'"
        with connect(self.db_path) as conn:
            return int(conn.execute(sql).fetchone()["n"])

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM scrape_runs ORDER BY run_id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get(self, product_id: str) -> Product | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        return self._to_product(row) if row else None

    def column_names(self) -> list[str]:
        with connect(self.db_path) as conn:
            return [r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()]

    def _to_product(self, row) -> Product:
        data = dict(row)
        extras = {name: data.get(name) for name in self.extra_fields if data.get(name) not in (None, "")}
        return Product(
            product_id=data["product_id"], name=data["name"], category=data["category"],
            price=float(data["price"]), currency=data["currency"], product_url=data["product_url"],
            source_site=data["source_site"], availability=data["availability"],
            sub_category=data.get("sub_category") or "", brand=data.get("brand") or "",
            description=data.get("description") or "", rating=data.get("rating"), extras=extras,
            first_seen_at=data.get("first_seen_at"), scraped_at=data.get("scraped_at"),
        )

    # ------------------------------------------------------------------ search
    def search(self, query: str, filters: dict[str, Any] | None = None, limit: int = 5,
               synonyms: dict[str, list[str]] | None = None,
               product_types: set[str] | None = None) -> list[Product]:
        """Keyword search with price filters. Products matching more query terms rank first.
        If the query names a product type (e.g. "jacket" in "rain jacket"), results must match it."""
        filters = filters or {}
        sql = "SELECT * FROM products WHERE availability != 'unavailable'"
        args: list[Any] = []
        if filters.get("max_price") is not None:
            sql += " AND price <= ?"
            args.append(float(filters["max_price"]))
        if filters.get("min_price") is not None:
            sql += " AND price >= ?"
            args.append(float(filters["min_price"]))
        with connect(self.db_path) as conn:
            rows = conn.execute(sql, args).fetchall()

        excluded = set(filters.get("exclude_ids") or [])
        groups = build_term_groups(query, synonyms or {})
        types = product_types or set()
        required = [g for g in groups if g[0] in types]
        size = str(filters.get("size") or "").upper()
        scored: list[tuple[int, int, Product]] = []
        for row in rows:
            product = self._to_product(row)
            if product.product_id in excluded:
                continue
            if size and not _size_ok(product, size):
                continue
            matched, score = score_product(product, groups)
            if groups and matched == 0:
                continue
            if required and score_product(product, required)[0] == 0:
                continue
            scored.append((matched, score, product))

        sort = filters.get("sort") or "relevance"

        def sort_key(item: tuple[int, int, Product]):
            matched, score, p = item
            if sort == "price_asc":
                tail: tuple = (p.price,)
            elif sort == "price_desc":
                tail = (-p.price,)
            else:  # "relevance" and "rating": best rated first, then cheaper
                tail = (-(p.rating or 0), p.price)
            return (-matched, -score, *tail, p.name)

        scored.sort(key=sort_key)
        return [p for _, _, p in scored[:limit]]


def build_term_groups(query: str, synonyms: dict[str, list[str]]) -> list[list[str]]:
    """Each group is one query term plus its synonyms; a product matches a group if any
    alternative appears in it. Multi-word synonyms (e.g. "power bank") are kept as phrases."""
    text = normalize(query)
    groups: list[list[str]] = []
    used_phrase_words: set[str] = set()
    for key, alternatives in synonyms.items():
        key_norm = normalize(key)
        if " " in key_norm and re.search(rf"\b{re.escape(key_norm)}", text):
            groups.append([key_norm] + [normalize(a) for a in alternatives])
            used_phrase_words.update(content_terms(key_norm))
    for term in content_terms(text):
        if term in used_phrase_words:
            continue
        group = [term]
        for key, alternatives in synonyms.items():
            key_terms = content_terms(key)
            if " " not in normalize(key) and key_terms and key_terms[0] == term:
                group += [normalize(a) for a in alternatives]
        groups.append(group)
    return groups


def _product_fields(product: Product) -> dict[str, str]:
    extras_text = " ".join(str(v) for v in product.extras.values())
    return {
        "name": normalize(product.name),
        "sub_category": normalize(product.sub_category),
        "brand": normalize(product.brand),
        "extras": normalize(extras_text),
        "description": normalize(product.description),
    }


def _matches(alternative: str, text: str) -> bool:
    if not text:
        return False
    if " " in alternative:
        return alternative in text
    return re.search(rf"\b{re.escape(alternative)}", text) is not None


def score_product(product: Product, groups: list[list[str]]) -> tuple[int, int]:
    fields = _product_fields(product)
    matched = 0
    score = 0
    for group in groups:
        best = 0
        for field_name, weight in FIELD_WEIGHTS.items():
            if any(_matches(alt, fields[field_name]) for alt in group):
                best = max(best, weight)
        if best:
            matched += 1
            score += best
    return matched, score


def _size_ok(product: Product, size: str) -> bool:
    sizes = str(product.extras.get("sizes") or "")
    if not sizes:
        return True  # most sources do not list sizes; do not hide those products
    return size in [s.strip().upper() for s in sizes.split(",")]
