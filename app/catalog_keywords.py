"""Product-type keywords per category, shared by the task planner and the domain agents."""
from __future__ import annotations

# Keywords are written in singular form; a word matches if it equals the keyword or its stem does.
KEYWORDS: dict[str, list[str]] = {
    "food": [
        "food", "grocery", "groceries", "rice", "bread", "milk", "egg", "cheese", "butter", "yogurt",
        "chocolate", "candy", "sweet", "snack", "biscuit", "cookie", "cake", "coffee", "tea",
        "juice", "water", "soda", "soft drink", "drink", "beverage", "energy drink", "potion",
        "honey", "oil", "cooking oil", "sugar", "salt", "flour", "pasta", "noodle", "cereal",
        "fruit", "banana", "kiwi", "lemon", "strawberry", "mulberry", "mango", "grape",
        "vegetable", "veg", "veggie", "potato", "onion", "cucumber", "pepper", "chili", "chilli",
        "tomato", "carrot", "meat", "beef", "steak", "chicken", "fish", "pork", "lamb", "mutton",
        "protein", "protein powder", "ice cream", "dessert", "pet food", "cat food", "dog food",
        "tissue", "nescafe",
    ],
    "clothes": [
        "clothes", "clothing", "apparel", "outfit", "fashion", "jacket", "coat", "raincoat",
        "windbreaker", "parka", "hoodie", "sweatshirt", "sweater", "jumper", "cardigan", "shirt",
        "tshirt", "tee", "tops", "blouse", "dress", "gown", "frock", "skirt", "suit", "corset",
        "pant", "trouser", "jean", "denim", "shorts", "legging", "shoe", "sneaker", "trainer",
        "boot", "sandal", "heel", "high heel", "slipper", "cleat", "footwear", "hat", "beanie",
        "cap", "scarf", "glove", "sock", "backpack", "blazer", "polo", "kurta", "saree",
    ],
    "electronics": [
        "electronics", "electronic", "gadget", "device", "laptop", "notebook", "computer", "pc",
        "desktop", "macbook", "chromebook", "tablet", "ipad", "phone", "smartphone", "mobile",
        "iphone", "android", "galaxy", "charger", "charging", "power bank", "powerbank",
        "battery pack", "battery", "cable", "earbud", "earphone", "headphone", "headset",
        "airpods", "speaker", "smart speaker", "echo", "homepod", "smartwatch", "watch", "camera",
        "tv", "television", "monitor", "keyboard", "mouse", "ssd", "hdd", "hard drive", "usb",
        "router", "console", "playstation", "xbox", "phone case", "selfie stick", "monopod",
        "ram", "processor",
    ],
}
