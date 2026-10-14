"""Rule-based task planner.

Used whenever no LLM is configured (the default) or the LLM is unavailable. It detects the
product categories in a message, splits multi-category messages into one task per category
(FR-2), extracts price/size filters, and recognises follow-ups, greetings, ambiguous words
and out-of-scope questions (FR-3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.catalog_keywords import KEYWORDS
from app.db.models import Task, TaskPlan
from app.text_utils import content_terms, normalize, stem

CATEGORY_LABELS = {"food": "food", "clothes": "clothes", "electronics": "electronics"}

# Words that only name the category; they select the agent but are not search terms.
GENERIC_WORDS = {
    "food": {"food", "grocery", "groceries", "foods"},
    "clothes": {"clothes", "clothing", "apparel", "outfit", "fashion", "wear"},
    "electronics": {"electronics", "electronic", "gadget", "device", "tech"},
}

AMBIGUOUS: dict[str, list[str]] = {"apple": ["food", "electronics"]}
AMBIGUOUS_QUESTIONS = {
    "apple": "Do you mean apples the fruit (food) or Apple the brand (electronics)?",
}
HINTS: dict[str, set[str]] = {
    "food": {"fruit", "fruits", "food", "eat", "eating", "grocery", "groceries", "fresh",
             "snack", "edible", "healthy", "the fruit"},
    "electronics": {"brand", "iphone", "phone", "mac", "macbook", "laptop", "device", "electronics",
                    "electronic", "tech", "gadget", "computer", "airpods", "watch", "ipad",
                    "company", "the brand"},
    "clothes": {"clothes", "clothing", "wear", "fashion"},
}

NUM = r"(\d+(?:\.\d+)?)\s*(k\b)?"
CUR = r"(?:rs\.?|lkr|usd|\$|€|£)?\s*"
RANGE_PATTERNS = [
    re.compile(rf"\bbetween\s*{CUR}{NUM}\s*(?:and|to|-)\s*{CUR}{NUM}"),
    re.compile(rf"\bfrom\s*{CUR}{NUM}\s*(?:to|-)\s*{CUR}{NUM}"),
    re.compile(rf"(?<![\w.]){CUR}{NUM}\s*-\s*{CUR}{NUM}(?!\w)"),
]
MAX_PATTERN = re.compile(
    rf"(?:\b(?:under|below|less than|cheaper than|lower than|max(?:imum)?(?: of)?|up to|upto|"
    rf"within|no more than|not more than|at most|budget(?: of| is)?)|<)\s*{CUR}{NUM}"
    rf"(?:\s*(?:dollars?|usd|rs|lkr|bucks))?")
MIN_PATTERN = re.compile(
    rf"(?:\b(?:over|above|more than|at least|minimum(?: of)?|min|starting at|starting from)|>)"
    rf"\s*{CUR}{NUM}(?:\s*(?:dollars?|usd|rs|lkr|bucks))?")
SIZE_PATTERN = re.compile(r"\bsize\s*(xxs|xs|s|m|l|xl|xxl|xxxl|\d{1,2})\b")
TOTAL_PATTERN = re.compile(r"\b(in total|total|altogether|combined|for both|together)\b")
EACH_PATTERN = re.compile(r"\beach\b")
SORT_PATTERNS = [
    (re.compile(r"\b(cheapest|cheap|lowest price|least expensive|budget|affordable|inexpensive)\b"), "price_asc"),
    (re.compile(r"\b(most expensive|priciest|highest price|luxury)\b"), "price_desc"),
    (re.compile(r"\b(best rated|top rated|highest rated|best reviewed|best)\b"), "rating"),
]
MODIFIER_PATTERNS = [
    (re.compile(r"\b(cheaper|less expensive|lower price|lower priced|more affordable|budget friendly)\b"), "cheaper"),
    (re.compile(r"\b(more expensive|pricier|higher end|high end|premium|fancier|better quality)\b"), "pricier"),
    (re.compile(r"\b(more|other|others|another|else|similar|alternatives?|different ones?|next)\b"), "more"),
]
REFERENTIAL = re.compile(r"\b(them|those|these|ones|that one|this one|it)\b")
GREETING = re.compile(
    r"^\s*(hi|hello|hey|hiya|good (morning|afternoon|evening)|help|what can you do|"
    r"who are you|how does this work|thanks|thank you|thx)\b")
SPLIT_PATTERN = re.compile(r"\s(?:and|plus|also|as well as|along with|then)\s|[,;+&/]")


@dataclass
class Segment:
    text: str
    hits: list[tuple[str, str]] = field(default_factory=list)   # (category, keyword)
    filters: dict[str, Any] = field(default_factory=dict)
    terms: list[str] = field(default_factory=list)


def _amount(value: str, k: str | None) -> float:
    number = float(value)
    return number * 1000 if k else number


def extract_filters(text: str) -> tuple[dict[str, Any], str]:
    """Pull price ranges, limits and sizes out of the text. Returns (filters, remaining text)."""
    filters: dict[str, Any] = {}

    def take(pattern: re.Pattern, handler) -> None:
        nonlocal text
        match = pattern.search(text)
        while match:
            handler(match)
            text = text[: match.start()] + " " + text[match.end():]
            match = pattern.search(text)

    def on_range(m: re.Match) -> None:
        low, high = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
        filters["min_price"], filters["max_price"] = min(low, high), max(low, high)

    for pattern in RANGE_PATTERNS:
        take(pattern, on_range)
    take(MAX_PATTERN, lambda m: filters.__setitem__("max_price", _amount(m.group(1), m.group(2))))
    take(MIN_PATTERN, lambda m: filters.__setitem__("min_price", _amount(m.group(1), m.group(2))))
    take(SIZE_PATTERN, lambda m: filters.__setitem__("size", m.group(1).upper()))
    return filters, " ".join(text.split())


def detect_sort(text: str) -> str | None:
    for pattern, sort in SORT_PATTERNS:
        if pattern.search(text):
            return sort
    return None


def detect_modifier(text: str) -> str | None:
    without_filters = extract_filters(text)[1]
    for pattern, modifier in MODIFIER_PATTERNS:
        if pattern.search(without_filters):
            return modifier
    return None


def _tokens(text: str) -> list[tuple[str, str]]:
    raw_words = re.findall(r"[a-z0-9']+", text)
    tokens = []
    for w in raw_words:
        w = w.strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if w:
            tokens.append((w, stem(w)))
    return tokens


def find_hits(text: str) -> list[tuple[str, str]]:
    """Category keyword hits in order of appearance: (category, keyword)."""
    tokens = _tokens(text)
    hits: list[tuple[int, str, str]] = []
    used: set[int] = set()
    # Multi-word keywords first ("power bank", "soft drink").
    for category, keywords in KEYWORDS.items():
        for kw in keywords:
            parts = kw.split()
            if len(parts) < 2:
                continue
            n = len(parts)
            for i in range(len(tokens) - n + 1):
                window = tokens[i:i + n]
                if all(p == raw or p == st for p, (raw, st) in zip(parts, window)) and not used & set(range(i, i + n)):
                    hits.append((i, category, kw))
                    used.update(range(i, i + n))
    for i, (raw, st) in enumerate(tokens):
        if i in used:
            continue
        for category, keywords in KEYWORDS.items():
            if raw in keywords or st in keywords:
                hits.append((i, category, raw if raw in keywords else st))
                used.add(i)
                break
    hits.sort()
    return [(category, kw) for _, category, kw in hits]


def _ambiguous_terms(text: str) -> list[str]:
    return [raw if raw in AMBIGUOUS else st for raw, st in _tokens(text)
            if raw in AMBIGUOUS or st in AMBIGUOUS]


def _hint_category(text: str, options: list[str]) -> str | None:
    norm = normalize(text)
    found = []
    for category in options:
        for hint in HINTS.get(category, set()):
            if re.search(rf"\b{re.escape(hint)}\b", norm):
                found.append(category)
                break
    return found[0] if len(found) == 1 else None


def _query_for(segment_text: str, category: str, other_keywords: set[str]) -> str:
    generic = GENERIC_WORDS.get(category, set())
    terms = [t for t in content_terms(segment_text) if t not in generic and t not in other_keywords]
    return " ".join(terms)


def plan_with_rules(message: str) -> TaskPlan:
    """Build a plan for a fresh message. Follow-up resolution against history happens later."""
    text = normalize(message)
    global_filters: dict[str, Any] = {}
    # Ranges first, so "between 100 and 300" is not split at "and".
    for pattern in RANGE_PATTERNS:
        match = pattern.search(text)
        if match:
            low, high = _amount(match.group(1), match.group(2)), _amount(match.group(3), match.group(4))
            global_filters["min_price"], global_filters["max_price"] = min(low, high), max(low, high)
            text = text[: match.start()] + " " + text[match.end():]
    sort = detect_sort(text)
    total_wanted = bool(TOTAL_PATTERN.search(text))
    each_wanted = bool(EACH_PATTERN.search(text))

    segments: list[Segment] = []
    for part in SPLIT_PATTERN.split(text):
        part = part.strip()
        if not part:
            continue
        filters, rest = extract_filters(part)
        segments.append(Segment(text=rest, hits=find_hits(rest), filters=filters))

    all_hits = [h for s in segments for h in s.hits]
    modifier = detect_modifier(normalize(message))
    plan = TaskPlan(source="rules")

    if not all_hits:
        filters = dict(global_filters)
        for s in segments:
            filters.update(s.filters)
        ambiguous = _ambiguous_terms(text)
        if ambiguous:
            term = ambiguous[0]
            options = AMBIGUOUS[term]
            chosen = _hint_category(text, options)
            if chosen:
                plan.tasks = [Task(chosen, term, _with_sort(filters, sort))]
                plan.categories_named = [chosen]
                return plan
            plan.clarify = AMBIGUOUS_QUESTIONS.get(term, "Which category do you mean?")
            plan.pending = {"type": "ambiguous", "term": term, "options": options,
                            "filters": filters, "sort": sort}
            return plan
        if modifier or REFERENTIAL.search(text) or filters:
            plan.followup = True
            plan.modifier = modifier
            plan.followup_filters = _with_sort(filters, sort)
            return plan
        if GREETING.search(text):
            plan.greeting = True
            return plan
        plan.out_of_scope = True
        return plan

    # Group segments by category, in the order the customer mentioned them.
    order: list[str] = []
    queries: dict[str, list[str]] = {}
    filters_by_cat: dict[str, dict[str, Any]] = {}
    keyword_sets = {cat: {stem(k) for k in KEYWORDS[cat] if " " not in k} | set(KEYWORDS[cat])
                    for cat in KEYWORDS}
    last_category: str | None = None
    priced_segments = 0
    for s in segments:
        categories = list(dict.fromkeys(cat for cat, _ in s.hits))
        if s.filters.get("max_price") is not None or s.filters.get("min_price") is not None:
            priced_segments += 1
        if not categories:
            # e.g. "..., under 50" or "..., the red one": attach to the previous category.
            if s.filters and not content_terms(s.text):
                global_filters.update(s.filters)
            elif last_category:
                queries[last_category].append(_query_for(s.text, last_category, set()))
                filters_by_cat[last_category].update(s.filters)
            continue
        for cat in categories:
            if cat not in order:
                order.append(cat)
                queries[cat] = []
                filters_by_cat[cat] = {}
            others = set().union(*(keyword_sets[o] for o in categories if o != cat)) if len(categories) > 1 else set()
            queries[cat].append(_query_for(s.text, cat, others))
            filters_by_cat[cat].update(s.filters)
        last_category = categories[-1]

    # A price limit written once at the end ("a shirt and a charger under 50") applies to all.
    if len(order) > 1 and priced_segments == 1 and not each_wanted:
        last = order[-1]
        shared = {k: v for k, v in filters_by_cat[last].items() if k in ("max_price", "min_price")}
        if shared and segments and segments[-1].hits and segments[-1].hits[-1][0] == last:
            for cat in order:
                for key, value in shared.items():
                    filters_by_cat[cat].setdefault(key, value)

    for cat in order:
        filters = {**global_filters, **filters_by_cat[cat]}
        query = " ".join(q for q in queries[cat] if q).strip()
        plan.tasks.append(Task(cat, query, _with_sort(filters, sort)))
    plan.categories_named = list(order)

    if total_wanted and len(plan.tasks) > 1:
        limits = [t.filters.get("max_price") for t in plan.tasks if t.filters.get("max_price")]
        if limits:
            plan.total_budget = max(limits)
            for task in plan.tasks:
                task.filters["max_price"] = plan.total_budget
    if modifier in ("cheaper", "pricier", "more"):
        plan.followup = True
        plan.modifier = modifier
    return plan


def _with_sort(filters: dict[str, Any], sort: str | None) -> dict[str, Any]:
    result = dict(filters)
    if sort:
        result["sort"] = sort
    return result


def categories_in_reply(text: str, options: list[str]) -> list[str]:
    """Which of the offered categories a short answer refers to ("power banks", "both")."""
    norm = normalize(text)
    if re.search(r"\b(both|all|either|everything|all of them)\b", norm):
        return list(options)
    chosen = [cat for cat, _ in find_hits(norm) if cat in options]
    for cat in options:
        if re.search(rf"\b{cat}\b", norm) and cat not in chosen:
            chosen.append(cat)
    hinted = _hint_category(norm, options)
    if hinted and hinted not in chosen:
        chosen.append(hinted)
    return list(dict.fromkeys(chosen))
