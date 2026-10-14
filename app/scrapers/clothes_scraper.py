from app.scrapers.base_scraper import BaseScraper


class ClothesScraper(BaseScraper):
    category = "clothes"
    SUB_CATEGORY_KEYWORDS = [
        ("jackets", ["jacket", "coat", "raincoat", "windbreaker", "parka", "hoodie"]),
        ("shirts", ["tshirt", "t shirt", "shirt", "tee"]),
        ("dresses", ["dress", "gown", "frock", "skirt", "corset", "suit"]),
        ("tops", ["top", "blouse", "boat neck", "short sleeve"]),
        ("shoes", ["shoe", "sneaker", "trainer", "boot", "sandal", "heel", "slipper", "cleat",
                   "jordan"]),
        ("hats", ["beanie", "hat", "cap"]),
        ("bags", ["backpack", "bag"]),
        ("trousers", ["pant", "trouser", "jean", "short", "slim fit"]),
    ]
