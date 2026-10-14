from app.scrapers.base_scraper import BaseScraper


class ElectronicsScraper(BaseScraper):
    category = "electronics"
    SUB_CATEGORY_KEYWORDS = [
        ("power banks", ["battery pack", "power bank", "powerbank"]),
        ("chargers", ["charger", "airpower"]),
        ("audio", ["earphone", "airpods", "headphone", "earbud", "speaker", "echo", "homepod"]),
        ("accessories", ["case", "monopod", "selfie", "pedestal", "stand", "cable"]),
        ("wearables", ["watch"]),
        ("storage", ["ssd", "hard drive", "hdd", "gaming drive", "usb drive"]),
        ("monitors", ["monitor", "full hd", "display"]),
        ("tablets", ["tablet", "ipad", "galaxy tab", "tab "]),
        ("laptops", ["laptop", "notebook", "macbook", "matebook", "zenbook", "vivobook", "thinkpad",
                     "chromebook", "ideapad", "aspire", "yoga", "xps", "latitude", "probook"]),
        ("phones", ["phone", "iphone", "smartphone", "galaxy", "oppo", "realme", "vivo", "nokia"]),
    ]
