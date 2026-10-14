import re

from app.agents.base_agent import BaseAgent

COLOURS = ["black", "white", "red", "blue", "green", "yellow", "pink", "purple", "orange", "brown",
           "grey", "gray", "gold", "silver", "beige", "navy", "plum"]
MATERIALS = ["leather", "cotton", "denim", "wool", "silk", "polyester", "linen", "nylon", "fleece"]


class ClothesAgent(BaseAgent):
    name = "clothes"
    EXTRA_FIELDS = ["sizes", "colours", "gender", "material"]
    SYNONYMS = {
        "jacket": ["coat", "windbreaker", "raincoat", "parka"],
        "coat": ["jacket", "raincoat"],
        "rain": ["raincoat", "waterproof", "windbreaker"],
        "tshirt": ["t shirt", "tee", "tshirts"],
        "tee": ["tshirt", "t shirt"],
        "sneaker": ["trainer", "running shoe", "shoes"],
        "trainer": ["sneaker"],
        "shoe": ["sneaker", "trainer", "boot", "sandal", "heel", "slipper", "cleat"],
        "dress": ["gown", "frock"],
        "hat": ["beanie", "cap"],
        "women": ["womens", "woman", "girl", "ladies"],
        "men": ["mens", "man"],
        "kid": ["kids", "children", "child"],
        "boot": ["boots", "hiking"],
    }

    def extract_extras(self, raw: dict) -> dict:
        name = raw.get("name", "").lower()
        text = f"{name} {raw.get('description', '')}".lower()
        gender = raw.get("gender_hint")
        if re.search(r"\b(women|woman|womens|ladies|girl)", name):
            gender = "women"
        elif re.search(r"\b(men|mens|man)\b", name):
            gender = "men"
        elif re.search(r"\bkids?\b", name):
            gender = "kids"
        colours = [c for c in COLOURS if re.search(rf"\b{c}\b", text)]
        materials = [m for m in MATERIALS if re.search(rf"\b{m}\b", text)]
        return {
            "sizes": None,  # the current sources do not list sizes on their product listings
            "colours": ", ".join(colours) or None,
            "gender": gender,
            "material": ", ".join(materials) or None,
        }
