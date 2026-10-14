import json
import re

from app.agents.base_agent import BaseAgent


class ElectronicsAgent(BaseAgent):
    name = "electronics"
    EXTRA_FIELDS = ["model_number", "specs", "warranty"]
    SYNONYMS = {
        "power bank": ["battery pack", "powerbank", "magsafe battery"],
        "powerbank": ["battery pack", "power bank"],
        "phone charger": ["iphone charger", "charger"],
        "charger": ["charging", "airpower"],
        "phone": ["smartphone", "iphone", "galaxy"],
        "smartphone": ["phone", "iphone"],
        "mobile": ["phone", "smartphone"],
        "earbud": ["earphones", "airpods", "earphone"],
        "earphone": ["earbuds", "airpods"],
        "headphone": ["airpods max", "earphones"],
        "laptop": ["notebook", "macbook"],
        "notebook": ["laptop"],
        "tablet": ["ipad", "galaxy tab"],
        "speaker": ["echo", "homepod"],
        "tv": ["television", "monitor"],
        "computer": ["laptop", "notebook", "pc"],
        "storage": ["ssd", "hard drive"],
        "hard drive": ["hdd", "ssd", "gaming drive"],
        "ssd": ["solid state"],
        "smartwatch": ["watch"],
    }

    def extract_extras(self, raw: dict) -> dict:
        text = f"{raw.get('name', '')} {raw.get('description', '')}"
        specs = {}
        sizes = re.findall(r"\b(\d+)\s?GB\b", text, flags=re.I)
        if sizes:
            specs["memory_or_storage"] = sorted({f"{s}GB" for s in sizes}, key=lambda s: int(s[:-2]))
        storage = re.search(r"\b(\d+\s?(?:GB|TB))\s?(SSD|HDD|eMMC)\b", text, flags=re.I)
        if storage:
            specs["storage"] = f"{storage.group(1)} {storage.group(2).upper()}"
        screen = re.search(r"\b(\d{1,2}(?:\.\d)?)\s?(?:\"|inch|in\b|-inch)", text, flags=re.I)
        if screen:
            specs["screen_inches"] = screen.group(1)
        return {
            "model_number": raw.get("sku") or None,
            "specs": json.dumps(specs) if specs else None,
            "warranty": raw.get("warranty") or None,
        }
