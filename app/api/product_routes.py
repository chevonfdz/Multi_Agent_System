"""/api/products: product details for the in-page product view, and /api/system/status for the
live architecture page. Photos are looked up live from the source site and never stored."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user, get_services
from app.services import Services
from app.text_utils import format_price
from app.users.user_repository import User

router = APIRouter(prefix="/api", tags=["products"])

# Sources that are JSON APIs: their product link is raw data, not a page for people.
API_PARSERS = {"dummyjson", "fakestore"}

DETAIL_LABELS = {
    "weight": "Weight", "ingredients": "Ingredients", "calories": "Calories", "dietary_tags": "Dietary",
    "sizes": "Sizes", "colours": "Colours", "gender": "For", "material": "Material",
    "model_number": "Model / SKU", "warranty": "Warranty",
    "memory_or_storage": "Memory / storage", "storage": "Storage", "screen_inches": "Screen (inches)",
}


def _details(extras: dict) -> list[dict]:
    rows = []
    for key, value in extras.items():
        if key == "specs" and value:
            try:
                specs = json.loads(value)
            except (TypeError, ValueError):
                specs = {}
            for spec_key, spec_value in specs.items():
                text = ", ".join(spec_value) if isinstance(spec_value, list) else str(spec_value)
                rows.append({"label": DETAIL_LABELS.get(spec_key, spec_key.replace("_", " ").title()), "value": text})
        elif value:
            rows.append({"label": DETAIL_LABELS.get(key, key.replace("_", " ").title()), "value": str(value).title()
                         if key == "gender" else str(value)})
    return rows


def _find(services: Services, category: str, product_id: str):
    agent = services.agents.get(category)
    product = agent.repo.get(product_id) if agent else None
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return agent, product


@router.get("/products/{category}/{product_id}")
def product_detail(category: str, product_id: str, user: User = Depends(get_current_user),
                   services: Services = Depends(get_services)) -> dict:
    agent, product = _find(services, category, product_id)
    site = next((s for s in agent.scraper.sites if s.get("name") == product.source_site), {})
    return {
        **{k: v for k, v in product.to_dict().items() if k != "extras"},
        "price_text": format_price(product.price, product.currency),
        "images": services.media.images_for(product),
        "details": _details(product.extras),
        "is_api_source": site.get("parser") in API_PARSERS,
        "last_updated": agent.repo.last_updated(),
    }


@router.get("/products/{category}/{product_id}/image")
def product_image(category: str, product_id: str, user: User = Depends(get_current_user),
                  services: Services = Depends(get_services)) -> dict:
    _, product = _find(services, category, product_id)
    images = services.media.images_for(product)
    return {"image": images[0] if images else None}


@router.get("/system/status")
def system_status(user: User = Depends(get_current_user), services: Services = Depends(get_services)) -> dict:
    settings = services.settings
    return {
        "planner": (f"Claude ({services.llm.model})" if services.llm.enabled else "keyword rules (no LLM)"),
        "daily_refresh": f"{settings.scrape_hour:02d}:{settings.scrape_minute:02d}",
        "scheduler_enabled": settings.enable_scheduler,
        "agents": [{"agent": name, "db": f"{name}.db", "products": agent.repo.count(),
                    "last_updated": agent.repo.last_updated(),
                    "sites": [s.get("name") for s in agent.scraper.sites]}
                   for name, agent in services.agents.items()],
        "server_time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
