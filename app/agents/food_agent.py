import re

from app.agents.base_agent import BaseAgent

DIETARY = {"vegan": "vegan", "vegetarian": "vegetarian", "gluten free": "gluten-free",
           "organic": "organic", "sugar free": "sugar-free"}


class FoodAgent(BaseAgent):
    name = "food"
    EXTRA_FIELDS = ["weight", "ingredients", "calories", "dietary_tags"]
    SYNONYMS = {
        "soda": ["soft drink"],
        "soft drink": ["soda", "cola"],
        "drink": ["juice", "water", "soft drink", "potion", "coffee", "milk"],
        "energy drink": ["energy potion", "potion"],
        "sweet": ["chocolate", "candy", "honey", "ice cream"],
        "snack": ["chocolate", "candy"],
        "fruit": ["apple", "kiwi", "lemon", "strawberry", "mulberry"],
        "vegetable": ["cucumber", "pepper", "onion", "potato"],
        "veg": ["cucumber", "pepper", "onion", "potato"],
        "meat": ["beef", "chicken", "steak"],
        "coffee": ["nescafe"],
        "grocery": ["groceries"],
    }

    def extract_extras(self, raw: dict) -> dict:
        text = f"{raw.get('name', '')} {raw.get('description', '')}".lower()
        weight = re.search(r"\b(\d+(?:\.\d+)?)\s?(kg|g|ml|l|oz|lb)\b", text)
        tags = {DIETARY[k] for k in DIETARY if k in text}
        tags.update(t for t in raw.get("tags", []) if t in DIETARY.values())
        return {
            "weight": f"{weight.group(1)} {weight.group(2)}" if weight else None,
            "ingredients": None,
            "calories": None,
            "dietary_tags": ", ".join(sorted(tags)) or None,
        }
