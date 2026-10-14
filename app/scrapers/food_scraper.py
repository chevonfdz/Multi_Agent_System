from app.scrapers.base_scraper import BaseScraper


class FoodScraper(BaseScraper):
    category = "food"
    SUB_CATEGORY_KEYWORDS = [
        ("pet food", ["cat food", "dog food", "pet food"]),
        ("household", ["tissue"]),
        ("sweets", ["chocolate", "candy", "honey", "ice cream"]),
        ("drinks", ["juice", "water", "soft drink", "coffee", "tea", "potion", "energy drink", "milk"]),
        ("fruit", ["apple", "kiwi", "lemon", "strawberr", "mulberr", "banana", "orange", "mango"]),
        ("vegetables", ["cucumber", "pepper", "onion", "potato", "tomato", "carrot"]),
        ("meat and fish", ["beef", "chicken", "fish", "steak", "pork", "lamb"]),
        ("pantry", ["rice", "oil", "flour", "sugar", "salt", "pasta", "protein", "egg"]),
    ]
