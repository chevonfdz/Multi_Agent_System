"""Small text helpers shared by the task planner and product search."""
from __future__ import annotations

import re
from datetime import datetime, timezone

STOPWORDS = {
    "a", "an", "the", "some", "any", "me", "my", "i", "im", "we", "us", "you", "your", "our",
    "show", "find", "get", "give", "need", "needs", "want", "wants", "looking", "look", "search",
    "buy", "purchase", "please", "pls", "can", "could", "would", "should", "will", "do", "does",
    "is", "are", "was", "be", "there", "have", "has", "had", "for", "of", "to", "in", "on", "at",
    "by", "with", "what", "which", "whats", "who", "how", "much", "many", "cheap", "cheapest",
    "cheaper", "best", "good", "nice", "great", "price", "prices", "priced", "cost", "costs",
    "under", "below", "over", "above", "than", "less", "more", "and", "or", "also", "plus",
    "available", "sell", "sells", "selling", "recommend", "suggest", "option", "options", "item",
    "items", "product", "products", "thing", "things", "something", "stuff", "one", "ones", "it",
    "them", "those", "these", "that", "this", "like", "kind", "type", "about", "around", "rs",
    "lkr", "usd", "dollar", "dollars", "bucks", "total", "each", "both", "all", "just", "only",
    "really", "very", "hi", "hello", "hey", "thanks", "thank", "up", "upto", "max", "maximum",
    "min", "minimum", "least", "most", "within", "budget", "from", "between", "lowest",
    "highest", "rated", "rating", "top", "expensive", "pricier", "premium", "other", "others",
    "another", "similar", "else", "alternative", "alternatives", "anything", "ok", "okay",
    "want", "wanted", "still", "too", "so", "if", "but", "as", "well", "along", "per", "price",
    "size", "sizes", "under", "no", "not", "am", "pick", "choose", "got", "show",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(text: str) -> str:
    """Lower-case, unify quotes and hyphenated words, collapse whitespace."""
    text = (text or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", "", text)    # t-shirt -> tshirt (keeps 100-300)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)     # 200,000 -> 200000
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def stem(word: str) -> str:
    """Very small plural stemmer: jackets -> jacket, dresses -> dress, batteries -> battery."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in ("sses", "shes", "ches", "xes", "zes"):
        if len(word) > 4 and word.endswith(suffix):
            return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss") and not word.endswith("us"):
        return word[:-1]
    return word


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", normalize(text))


def content_terms(text: str, extra_stopwords: set[str] | None = None) -> list[str]:
    """Meaningful search terms, stemmed and without stopwords or bare numbers."""
    stop = STOPWORDS | (extra_stopwords or set())
    terms: list[str] = []
    for w in words(text):
        w = w.strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) < 2 or w in stop or re.fullmatch(r"\d+(\.\d+)?", w):
            continue
        s = stem(w)
        if s not in terms:
            terms.append(s)
    return terms


def format_price(price: float, currency: str) -> str:
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get((currency or "").upper())
    amount = f"{price:,.2f}"
    return f"{symbol}{amount}" if symbol else f"{currency} {amount}".strip()


def format_timestamp(iso: str | None) -> str:
    if not iso:
        return "not yet scraped"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")
