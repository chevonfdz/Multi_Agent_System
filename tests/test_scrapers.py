"""Scrapers, robots.txt handling and the daily refresh (FR-5, FR-7, FR-8, NFR-3, NFR-11)."""
import json

import pytest

from app.agents.electronics_agent import ElectronicsAgent
from app.agents.food_agent import FoodAgent
from app.db.product_repository import ProductRepository
from app.scrapers.electronics_scraper import ElectronicsScraper
from app.scrapers.fetcher import PoliteFetcher
from app.scrapers.food_scraper import FoodScraper
from app.scrapers.parsers import PARSERS
from app.scrapers.robots import parse_robots

WSD_PAGE_1 = """<html><body>
<div class="row product"><div class="col-2 thumbnail"><img src="https://web-scraping.dev/a.webp"></div>
 <div class="col-8 description"><h3 class="mb-0"><a href="https://web-scraping.dev/product/1">Box of Chocolate Candy</a></h3>
 <div class="short-description">Rich chocolates.</div></div>
 <div class="col-2 price-wrap"><div class="price">24.99</div></div></div>
<div class="row product"><div class="col-8 description"><h3><a href="https://web-scraping.dev/product/2">Red Energy Potion</a></h3>
 <div class="short-description">Energy drink.</div></div><div class="price">4.99</div></div>
</body></html>"""
WSD_PAGE_2 = """<div class="row product"><h3><a href="https://web-scraping.dev/product/13">Box of Chocolate Candy</a></h3>
<div class="price">24.99</div></div>"""
WSD_EMPTY = "<html><body><p>No products</p></body></html>"

WS_IO = """<div class="col-md-4"><div class="card thumbnail"><div class="product-wrapper card-body">
<img class="img-fluid" src="/images/cart2.png"><div class="caption">
<h4 class="price float-end"><span itemprop="price">$295.99</span></h4>
<h4><a class="title" href="/test-sites/e-commerce/allinone/product/60" title="Asus VivoBook X441NA-GA190">Asus VivoBook...</a></h4>
<p class="description">Asus VivoBook X441NA-GA190 Chocolate Black, 14", Celeron N3450, 4GB, 128GB SSD</p></div>
<div class="ratings"><p data-rating="3"></p></div></div></div></div>"""

DUMMY = json.dumps({"products": [
    {"id": 38, "title": "Rice", "price": 5.99, "description": "White rice.", "rating": 3.2,
     "stock": 10, "availabilityStatus": "In Stock", "tags": ["groceries"], "thumbnail": "https://x/t.png"},
    {"id": 99, "title": "Cat Food", "price": 8.99, "description": "Cat food.", "stock": 0,
     "availabilityStatus": "Out of Stock"}]})
FAKESTORE = json.dumps([{"id": 17, "title": "Rain Jacket Women Windbreaker", "price": 39.99,
                         "description": "Rain jacket.", "image": "https://x/i.jpg", "rating": {"rate": 3.8}}])


def fake_fetch(pages):
    def fetch(url):
        for key, body in pages.items():
            if key in url:
                return body
        return WSD_EMPTY
    return fetch


def test_robots_wildcards_and_crawl_delay():
    rules = parse_robots("User-agent: *\nDisallow: /ecommerce/*", "MultiAgentShopBot/1.0")
    assert not rules.allowed("/ecommerce/")                 # scrapingcourse.com is excluded (NFR-11)
    assert not rules.allowed("/ecommerce/page/2/")
    assert rules.allowed("/about")

    rules = parse_robots("User-agent: *\nDisallow: /test-sites/product/\nDisallow: /test-sites/pagination*?page=\n",
                         "MultiAgentShopBot/1.0")
    assert rules.allowed("/test-sites/e-commerce/allinone/computers/laptops")
    assert not rules.allowed("/test-sites/pagination/x?page=2")

    rules = parse_robots("User-agent: *\nDisallow: /robots-disallowed\nCrawl-delay: 2\n"
                         "User-agent: Googlebot\nDisallow: /api/\n", "MultiAgentShopBot/1.0")
    assert rules.crawl_delay == 2 and rules.allowed("/api/products")

    rules = parse_robots("User-agent: *\nDisallow: /shop\nAllow: /shop/public$", "bot")
    assert rules.allowed("/shop/public") and not rules.allowed("/shop/public/x")
    assert parse_robots("<!doctype html><html></html>", "bot").allowed("/anything")


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, robots):
        self.headers, self.robots, self.calls = {}, robots, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return self.robots
        return FakeResponse(200, "ok")


def test_fetcher_respects_robots_and_identifies_itself(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.scrapers.fetcher.time.sleep", lambda s: sleeps.append(s))
    session = FakeSession(FakeResponse(200, "User-agent: *\nDisallow: /private\nCrawl-delay: 2"))
    fetcher = PoliteFetcher("MultiAgentShopBot/1.0 (student project)", default_delay=0.0, session=session)
    assert "MultiAgentShopBot" in session.headers["User-Agent"]
    assert fetcher.get_text("https://shop.test/products") == "ok"
    with pytest.raises(PermissionError):
        fetcher.get_text("https://shop.test/private/page")
    fetcher.get_text("https://shop.test/products?page=2")
    assert sleeps and max(sleeps) > 1.0          # crawl-delay of 2 s respected

    missing = PoliteFetcher("bot", 0.0, session=FakeSession(FakeResponse(404)))
    assert missing.allowed("https://other.test/x")       # no robots.txt: allowed
    broken = PoliteFetcher("bot", 0.0, session=FakeSession(FakeResponse(503)))
    assert not broken.allowed("https://down.test/x")     # server error: conservative


def test_parsers_read_text_fields_only():
    items = PARSERS["web_scraping_dev"]({"base_url": "https://web-scraping.dev", "category": "consumables"},
                                        fake_fetch({"page=1": WSD_PAGE_1, "page=2": WSD_PAGE_2}))
    assert [i["name"] for i in items] == ["Box of Chocolate Candy", "Red Energy Potion", "Box of Chocolate Candy"]
    assert items[0]["price"] == 24.99 and items[0]["url"] == "https://web-scraping.dev/product/1"

    items = PARSERS["webscraper_io"]({"base_url": "https://webscraper.io", "listing_pages": [
        {"path": "/test-sites/e-commerce/allinone/computers/laptops", "sub_category": "laptops"}]},
        fake_fetch({"laptops": WS_IO}))
    assert items[0]["name"] == "Asus VivoBook X441NA-GA190" and items[0]["price"] == 295.99
    assert items[0]["rating"] == 3.0
    assert items[0]["url"] == "https://webscraper.io/test-sites/e-commerce/allinone/product/60"

    items = PARSERS["dummyjson"]({"base_url": "https://dummyjson.com", "categories": [{"name": "groceries"}]},
                                 fake_fetch({"groceries": DUMMY}))
    assert items[0]["url"] == "https://dummyjson.com/products/38"
    assert items[1]["availability"] == "out_of_stock"

    items = PARSERS["fakestore"]({"base_url": "https://fakestoreapi.com", "categories": [{"name": "women's clothing"}]},
                                 fake_fetch({"clothing": FAKESTORE}))
    assert items[0]["rating"] == 3.8

    for item in items:
        assert not any("image" in key or "thumbnail" in key for key in item)   # FR-8


def test_scraper_dedupes_and_infers_sub_category():
    scraper = FoodScraper([], fake_fetch({"page=1": WSD_PAGE_1, "page=2": WSD_PAGE_2}))
    items = scraper.scrape({"name": "web-scraping.dev", "parser": "web_scraping_dev",
                            "base_url": "https://web-scraping.dev", "category": "consumables"})
    assert [i["name"] for i in items] == ["Box of Chocolate Candy", "Red Energy Potion"]
    assert items[0]["sub_category"] == "sweets" and items[1]["sub_category"] == "drinks"


SITE_A = {"name": "web-scraping.dev", "parser": "web_scraping_dev", "base_url": "https://web-scraping.dev",
          "category": "consumables"}
SITE_B = {"name": "dummyjson.com", "parser": "dummyjson", "base_url": "https://dummyjson.com",
          "categories": [{"name": "groceries", "sub_category": "groceries"}]}


def make_food_agent(tmp_path, pages, sites=(SITE_A, SITE_B)):
    repo = ProductRepository(tmp_path / "food.db", "food", FoodAgent.EXTRA_FIELDS)
    return FoodAgent(repo, FoodScraper(list(sites), fake_fetch(pages)))


def test_refresh_stores_products_and_runs(tmp_path):                     # TC-16
    agent = make_food_agent(tmp_path, {"page=1": WSD_PAGE_1, "groceries": DUMMY})
    summary = agent.refresh_data()
    assert [s["status"] for s in summary["sites"]] == ["ok", "ok"]
    assert agent.repo.count() == 4
    assert agent.repo.last_updated() is not None
    runs = agent.repo.recent_runs()
    assert len(runs) == 2 and all(r["status"] == "ok" for r in runs)


def test_missing_products_become_unavailable(tmp_path):
    agent = make_food_agent(tmp_path, {"page=1": WSD_PAGE_1, "groceries": DUMMY})
    agent.refresh_data()
    agent.scraper.fetch = fake_fetch({"page=1": WSD_PAGE_2, "groceries": DUMMY})  # the potion disappeared
    agent.refresh_data()
    names = [p.name for p in agent.repo.search("", {}, limit=20)]
    assert "Red Energy Potion" not in names and "Box of Chocolate Candy" in names


def test_failing_site_keeps_previous_data(tmp_path):                    # TC-17, NFR-3
    agent = make_food_agent(tmp_path, {"page=1": WSD_PAGE_1, "groceries": DUMMY})
    agent.refresh_data()
    before = agent.repo.count()

    def broken(url):
        if "dummyjson" in url:
            raise ConnectionError("site offline")
        return WSD_PAGE_1 if "page=1" in url else WSD_EMPTY
    agent.scraper.fetch = broken
    summary = agent.refresh_data()
    assert [s["status"] for s in summary["sites"]] == ["ok", "failed"]
    assert agent.repo.count() == before
    assert agent.repo.recent_runs(1)[0]["error"] == "site offline"


def test_new_site_needs_no_code_change(tmp_path):                       # TC-18
    extra = {"name": "another-shop", "parser": "dummyjson", "base_url": "https://another-shop.test",
             "categories": [{"name": "groceries"}]}
    agent = make_food_agent(tmp_path, {"page=1": WSD_PAGE_1, "groceries": DUMMY}, sites=(SITE_A, extra))
    agent.refresh_data()
    assert {p.source_site for p in agent.repo.search("", {}, limit=20)} == {"web-scraping.dev", "another-shop"}


def test_product_tables_have_no_image_columns(tmp_path):               # TC-19, NFR-15
    for cls, scraper in ((FoodAgent, FoodScraper), (ElectronicsAgent, ElectronicsScraper)):
        repo = ProductRepository(tmp_path / f"{cls.name}.db", cls.name, cls.EXTRA_FIELDS)
        assert not [c for c in repo.column_names() if "image" in c or "thumb" in c]


def test_electronics_extras(tmp_path):
    repo = ProductRepository(tmp_path / "e.db", "electronics", ElectronicsAgent.EXTRA_FIELDS)
    agent = ElectronicsAgent(repo, ElectronicsScraper([], fake_fetch({})))
    p = agent.normalize({"name": "Asus VivoBook", "price": 295.99, "url": "https://x/1", "source_site": "x",
                         "description": 'Asus VivoBook 14", Celeron, 4GB, 128GB SSD'})
    specs = json.loads(p.extras["specs"])
    assert specs["storage"] == "128GB SSD" and specs["screen_inches"] == "14"


def test_interrupted_runs_are_closed(tmp_path):
    repo = ProductRepository(tmp_path / "food.db", "food", FoodAgent.EXTRA_FIELDS)
    repo.start_run("web-scraping.dev")                     # never finished: server stopped
    assert repo.close_interrupted_runs() == 1
    run = repo.recent_runs(1)[0]
    assert run["status"] == "failed" and "interrupted" in run["error"]
