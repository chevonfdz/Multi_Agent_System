"""Product view (details and live photos) and the execution trace used by the architecture page."""
import json

from app.db.models import Product
from app.scrapers.media import MediaService
from tests.conftest import SEED, chat

WSD_PRODUCT_PAGE = """<div class="row product-data"><div class="white-box text-center row product-images">
<img class="img-responsive product-img active" src="https://web-scraping.dev/assets/products/box-1.webp">
<img class="img-responsive product-img" src="https://web-scraping.dev/assets/products/box-2.webp"></div></div>
<div class="row product"><div class="col-2 thumbnail"><img class="img-thumbnail" src="https://web-scraping.dev/other.webp"></div></div>"""
WS_IO_PRODUCT_PAGE = """<div class="product-wrapper card-body"><div class="row"><div class="col-xl-2">
<img class="image img-fluid img-responsive" src="/images/test-sites/e-commerce/items/cart2.png"></div></div></div>"""
DUMMY_BULK = json.dumps({"products": [{"id": 38, "thumbnail": "https://cdn.dummyjson.com/rice/thumb.webp",
                                       "images": ["https://cdn.dummyjson.com/rice/1.webp"]}]})
FAKESTORE_BULK = json.dumps([{"id": 17, "image": "https://fakestoreapi.com/img/jacket.png"}])

WEBSITES = {
    "food": [{"name": "web-scraping.dev", "parser": "web_scraping_dev", "base_url": "https://web-scraping.dev"},
             {"name": "dummyjson.com", "parser": "dummyjson", "base_url": "https://dummyjson.com"}],
    "clothes": [{"name": "fakestoreapi.com", "parser": "fakestore", "base_url": "https://fakestoreapi.com"}],
    "electronics": [{"name": "webscraper.io", "parser": "webscraper_io", "base_url": "https://webscraper.io"}],
}


def make(category, site, url):
    return Product("id", "name", category, 1.0, "USD", url, site)


def test_media_service_finds_photos_for_every_source_type():
    calls = []

    def fetch(url):
        calls.append(url)
        if "dummyjson" in url:
            return DUMMY_BULK
        if "fakestoreapi" in url:
            return FAKESTORE_BULK
        if "webscraper.io" in url:
            return WS_IO_PRODUCT_PAGE
        return WSD_PRODUCT_PAGE

    media = MediaService(fetch, WEBSITES)
    assert media.images_for(make("food", "dummyjson.com", "https://dummyjson.com/products/38")) == [
        "https://cdn.dummyjson.com/rice/thumb.webp", "https://cdn.dummyjson.com/rice/1.webp"]
    assert media.images_for(make("clothes", "fakestoreapi.com", "https://fakestoreapi.com/products/17")) == [
        "https://fakestoreapi.com/img/jacket.png"]
    assert media.images_for(make("food", "web-scraping.dev", "https://web-scraping.dev/product/1")) == [
        "https://web-scraping.dev/assets/products/box-1.webp", "https://web-scraping.dev/assets/products/box-2.webp"]
    page = "https://webscraper.io/test-sites/e-commerce/allinone/product/60"
    assert media.images_for(make("electronics", "webscraper.io", page)) == [
        "https://webscraper.io/images/test-sites/e-commerce/items/cart2.png"]

    before = len(calls)
    media.images_for(make("food", "dummyjson.com", "https://dummyjson.com/products/38"))
    media.images_for(make("food", "web-scraping.dev", "https://web-scraping.dev/product/1"))
    assert len(calls) == before                       # cached in memory, not fetched again


def test_media_service_survives_failures_and_unknown_sites():
    def broken(url):
        raise ConnectionError("offline")
    media = MediaService(broken, WEBSITES)
    assert media.images_for(make("food", "dummyjson.com", "https://dummyjson.com/products/38")) == []
    assert media.images_for(make("food", "unknown-site", "https://x/1")) == []


def test_product_detail_endpoint(client, customer, media, monkeypatch):
    rice = SEED["food"][0]
    real_images_for = media.images_for
    monkeypatch.setattr(media, "images_for", lambda product: ["https://cdn.example/rice.webp"]
                        if product.category == "food" else real_images_for(product))
    res = client.get(f"/api/products/food/{rice.product_id}", headers=customer)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Rice" and data["price_text"] == "$5.99"
    assert data["images"] == ["https://cdn.example/rice.webp"]
    assert data["is_api_source"] is True                       # dummyjson.com is a JSON API
    assert data["last_updated"]
    image = client.get(f"/api/products/food/{rice.product_id}/image", headers=customer).json()
    assert image == {"image": "https://cdn.example/rice.webp"}

    laptop = SEED["electronics"][4]
    data = client.get(f"/api/products/electronics/{laptop.product_id}", headers=customer).json()
    assert data["images"] == []                                # no network in tests: no photo, still works
    assert data["is_api_source"] is False

    assert client.get("/api/products/food/does-not-exist", headers=customer).status_code == 404
    assert client.get("/api/products/toys/x", headers=customer).status_code == 404
    assert client.get(f"/api/products/food/{rice.product_id}").status_code == 401


def test_product_details_show_specs(client, customer, agents):
    electronics = agents["electronics"]
    product = electronics.normalize({"name": "Asus VivoBook", "price": 295.99, "url": "https://webscraper.io/p/60",
                                     "source_site": "webscraper.io",
                                     "description": 'Asus VivoBook 14", Celeron, 4GB, 128GB SSD'})
    electronics.repo.upsert_many([product])
    data = client.get(f"/api/products/electronics/{product.product_id}", headers=customer).json()
    labels = {row["label"]: row["value"] for row in data["details"]}
    assert labels["Storage"] == "128GB SSD" and labels["Screen (inches)"] == "14"


def test_chat_returns_sections_and_trace(client, customer):
    data = chat(client, customer, "A rain jacket and a power bank under 60")
    assert [s["agent"] for s in data["sections"]] == ["clothes", "electronics"]
    first = data["sections"][0]["products"][0]
    assert {"product_id", "category", "name", "price_text"} <= set(first)
    assert data["sections"][0]["limits"] == "under $60.00"

    trace = data["trace"]
    assert trace["planner"]["outcome"] == "tasks" and trace["planner"]["mode"] == "rules"
    assert [t["domain"] for t in trace["planner"]["tasks"]] == ["clothes", "electronics"]
    clothes = trace["agents"][0]
    assert clothes["db"] == "clothes.db" and clothes["scanned"] == len(SEED["clothes"])
    assert clothes["matched"] >= clothes["returned"] > 0 and clothes["top"]
    assert trace["combiner"]["sections"] == 2
    assert trace["saved"]["agent_call_rows"] == 2 and trace["total_ms"] >= 0


def test_trace_for_a_clarifying_question(client, customer):
    data = chat(client, customer, "Apple")
    assert data["sections"] is None
    assert data["trace"]["planner"]["outcome"] == "clarify" and data["trace"]["agents"] == []


def test_history_keeps_cards_and_trace(client, customer):
    data = chat(client, customer, "Cheapest rice?")
    detail = client.get(f"/api/conversations/{data['conversation_id']}", headers=customer).json()
    reply = detail["messages"][1]
    assert reply["sections"][0]["products"][0]["name"] == "Rice"
    assert reply["trace"]["agents"][0]["agent"] == "food"
    assert "sections" not in detail["messages"][0]           # customer messages stay plain


def test_system_status(client, customer):
    data = client.get("/api/system/status", headers=customer).json()
    assert data["planner"].startswith("keyword rules")
    assert {a["agent"]: a["products"] for a in data["agents"]} == {"food": 5, "clothes": 6, "electronics": 7}
    assert client.get("/api/system/status").status_code == 401
