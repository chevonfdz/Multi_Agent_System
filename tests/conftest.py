"""Shared fixtures: an isolated app with its own data folder and seeded product data.
No test touches the network."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.base_agent import make_id  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.db.models import Product  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.main import create_app  # noqa: E402
from app.scrapers.media import MediaService  # noqa: E402
from app.services import build_agents, build_services, load_websites  # noqa: E402
from config.settings import Settings  # noqa: E402

PASSWORD = "secret-pass-1"


def no_network(url: str) -> str:
    raise RuntimeError(f"network disabled in tests: {url}")


def product(category: str, name: str, price: float, site: str, sub: str, rating: float | None = 4.0,
            description: str = "", brand: str = "", availability: str = "in_stock") -> Product:
    slug = "-".join("".join(ch if ch.isalnum() else " " for ch in name.lower()).split())
    url = f"https://{site}/products/{slug}"
    return Product(product_id=make_id(site, url), name=name, category=category, price=price,
                   currency="USD", product_url=url, source_site=site, availability=availability,
                   sub_category=sub, brand=brand, description=description, rating=rating)


SEED = {
    "food": [
        product("food", "Rice", 5.99, "dummyjson.com", "pantry", 3.2, "Long grain white rice, 5kg bag."),
        product("food", "Apple", 1.99, "dummyjson.com", "fruit", 4.2, "Fresh and crisp apples."),
        product("food", "Box of Chocolate Candy", 24.99, "web-scraping.dev", "sweets", None,
                "Assorted chocolates."),
        product("food", "Juice", 3.99, "dummyjson.com", "drinks", 3.9, "Orange juice."),
        product("food", "Milk", 3.49, "dummyjson.com", "drinks", 4.1, "Fresh milk."),
    ],
    "clothes": [
        product("clothes", "Rain Jacket Women Windbreaker Striped Climbing Raincoats", 39.99,
                "fakestoreapi.com", "jackets", 3.8, "Lightweight waterproof rain jacket."),
        product("clothes", "Mens Cotton Jacket", 55.99, "fakestoreapi.com", "jackets", 4.7,
                "Great outerwear jacket for spring and autumn."),
        product("clothes", "Lightweight Rain Jacket", 25.00, "web-scraping.dev", "jackets", 4.0,
                "Packable rain jacket."),
        product("clothes", "Classic T-Shirt", 12.99, "dummyjson.com", "shirts", 4.3, "Cotton t-shirt."),
        product("clothes", "Men Check Shirt", 27.99, "dummyjson.com", "shirts", 4.0, "Check shirt."),
        product("clothes", "Running Shoes for Men", 49.99, "web-scraping.dev", "shoes", None,
                "Light running shoes."),
    ],
    "electronics": [
        product("electronics", "Apple MagSafe Battery Pack", 99.99, "dummyjson.com", "power banks", 4.5,
                "Portable battery pack.", brand="Apple"),
        product("electronics", "Budget Power Bank 10000mAh", 19.99, "dummyjson.com", "power banks", 3.9,
                "Compact power bank."),
        product("electronics", "Slim Power Bank 5000mAh", 29.99, "dummyjson.com", "power banks", 4.6,
                "Slim power bank."),
        product("electronics", "Apple iPhone Charger", 14.99, "dummyjson.com", "chargers", 4.0,
                "20W USB-C charger.", brand="Apple"),
        product("electronics", "Lenovo V110-15ISK", 409.63, "webscraper.io", "laptops", 3.0,
                'Lenovo V110-15ISK, 15.6" HD, Core i3, 8GB, 128GB SSD'),
        product("electronics", "Dell XPS 13", 899.00, "webscraper.io", "laptops", 4.5,
                'Dell XPS 13, 13.3", Core i7, 16GB, 512GB SSD'),
        product("electronics", "Beats Flex Wireless Earphones", 49.99, "dummyjson.com", "audio", 4.2,
                "Wireless earphones.", brand="Beats"),
    ],
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path / "data", log_dir=tmp_path / "logs", jwt_secret="test-secret-" + "x" * 40,
                 enable_scheduler=False, scrape_on_startup="never", request_delay_seconds=0)
    s.prepare()
    return s


@pytest.fixture
def agents(settings):
    agents = build_agents(settings, fetch=no_network)
    for category, products in SEED.items():
        repo = agents[category].repo
        run = repo.start_run("seed")
        repo.upsert_many(products)
        repo.finish_run(run, "ok", len(products))
    return agents


@pytest.fixture
def media(settings):
    return MediaService(no_network, load_websites(settings))


@pytest.fixture
def services(settings, agents, media):
    return build_services(settings, agents=agents, llm=LLMClient(), media=media)


@pytest.fixture
def client(settings, services):
    app = create_app(settings, services)
    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str, name: str = "Test User", password: str = PASSWORD) -> dict:
    res = client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert res.status_code == 201, res.text
    return res.json()


def login_headers(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture
def customer(client) -> dict:
    register(client, "alice@example.com", "Alice")
    return login_headers(client, "alice@example.com")


@pytest.fixture
def admin(client, services) -> dict:
    services.users.create("Admin", "admin@example.com", hash_password(PASSWORD), role="admin")
    return login_headers(client, "admin@example.com")


def chat(client: TestClient, headers: dict, message: str, conversation_id: int | None = None) -> dict:
    res = client.post("/api/chat", json={"message": message, "conversation_id": conversation_id},
                      headers=headers)
    assert res.status_code == 200, res.text
    return res.json()
