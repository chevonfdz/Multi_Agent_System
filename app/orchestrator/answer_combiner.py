"""Merges the domain agents' results into one reply (FR-11, FR-12, FR-13, FR-9)."""
from __future__ import annotations

import json
import logging
import re

from app.db.models import AgentReply, Product, TaskPlan
from app.llm.client import LLMClient, LLMError
from app.orchestrator.prompts import COMBINER_PROMPT
from app.text_utils import format_price, format_timestamp

log = logging.getLogger(__name__)

LABELS = {"food": "Food", "clothes": "Clothes", "electronics": "Electronics"}
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


def describe_filters(filters: dict, currency: str = "USD") -> str:
    parts = []
    if filters.get("min_price") is not None and filters.get("max_price") is not None:
        parts.append(f"between {format_price(filters['min_price'], currency)} and "
                     f"{format_price(filters['max_price'], currency)}")
    elif filters.get("max_price") is not None:
        parts.append(f"under {format_price(filters['max_price'], currency)}")
    elif filters.get("min_price") is not None:
        parts.append(f"over {format_price(filters['min_price'], currency)}")
    if filters.get("size"):
        parts.append(f"in size {filters['size']}")
    return (" " + " ".join(parts)) if parts else ""


def product_line(index: int, p: Product) -> str:
    rating = f" · rated {p.rating:.1f}/5" if p.rating else ""
    return (f"{index}. **{p.name}** — {format_price(p.price, p.currency)} · {p.source_site}{rating} · "
            f"[View product]({p.product_url})")


def section_title(r: AgentReply) -> str:
    limits = describe_filters({k: v for k, v in r.filters.items() if k in ("max_price", "min_price", "size")})
    suffix = f" ·{limits}" if limits else ""
    return f"### {LABELS.get(r.agent, r.agent.title())} · {r.query or 'all products'}{suffix}"


def empty_message(r: AgentReply, modifier: str | None) -> str:
    label = LABELS.get(r.agent, r.agent).lower()
    what = r.query or f"{label} products"
    if modifier == "cheaper":
        return f"There are no other cheaper {what} options than the ones I already showed."
    if modifier == "pricier":
        return f"There are no other more expensive {what} options than the ones I already showed."
    if modifier == "more":
        return f"There are no more {what} options to show."
    return (f"No matching {label} products found{describe_filters(r.filters)}. "
            "Try a broader search or a different price limit.")


def template_reply(plan: TaskPlan, results: list[AgentReply],
                   combos: list[tuple[list[Product], float]] | None = None,
                   display_limit: int = 5) -> str:
    if results and all(r.status == "failed" for r in results):
        return ("Sorry, I couldn't check the shops right now. Please try again in a few minutes.")
    ok = [r for r in results if r.status == "ok"]
    if len(results) > 1:
        intro = f"Here's what I found for your {len(results)} requests:"
    elif ok:
        intro = "Here's what I found:"
    elif plan.modifier:
        intro = "That's everything I have for that search."
    else:
        intro = "I couldn't find a match for that."
    lines = [intro, ""]
    for r in results:
        lines.append(section_title(r))
        label = LABELS.get(r.agent, r.agent).lower()
        if r.status == "ok":
            lines += [product_line(i, p) for i, p in enumerate(r.products[:display_limit], 1)]
        elif r.status == "empty":
            lines.append(empty_message(r, plan.modifier))
        else:
            lines.append(f"Sorry, I couldn't check {label} right now. Please try again in a moment.")
        lines.append("")
    if plan.total_budget:
        budget = format_price(plan.total_budget, "USD")
        if combos:
            lines.append(f"### Combinations within your total budget of {budget}")
            for i, (products, total) in enumerate(combos, 1):
                parts = " + ".join(f"{p.name} ({format_price(p.price, p.currency)})" for p in products)
                lines.append(f"{i}. {parts} = **{format_price(total, 'USD')}**")
        elif all(r.status == "ok" for r in results):
            lines.append(f"No combination of these products fits within your total budget of {budget}.")
        lines.append("")
    return "\n".join(lines).strip()


def freshness_footer(results: list[AgentReply]) -> str:
    parts = [f"{r.agent} {format_timestamp(r.last_updated)}" for r in results if r.status != "failed"]
    return f"_Data last updated: {', '.join(parts)}_" if parts else ""


def links_are_valid(text: str, allowed: set[str]) -> bool:
    links = set(URL_PATTERN.findall(text))
    if allowed and not links:
        return False
    return links.issubset(allowed)


def format_results_for_llm(message: str, results: list[AgentReply],
                           combos: list[tuple[list[Product], float]] | None,
                           total_budget: float | None) -> str:
    payload = {
        "customer_message": message,
        "categories": [{
            "category": r.agent, "query": r.query, "status": r.status,
            "filters": {k: v for k, v in r.filters.items() if k != "exclude_ids"},
            "products": [{"name": p.name, "price": format_price(p.price, p.currency),
                          "site": p.source_site, "rating": p.rating, "link": p.product_url,
                          "description": p.description[:200]} for p in r.products[:5]],
        } for r in results],
    }
    if total_budget:
        payload["total_budget"] = total_budget
        payload["budget_combinations"] = [
            {"products": [p.name for p in products], "total": total} for products, total in (combos or [])]
    return json.dumps(payload, ensure_ascii=False, indent=1)


class AnswerCombiner:
    def __init__(self, llm: LLMClient, display_limit: int = 5):
        self.llm = llm
        self.display_limit = display_limit

    async def combine(self, message: str, plan: TaskPlan, results: list[AgentReply],
                      combos: list[tuple[list[Product], float]] | None = None) -> str:
        text: str | None = None
        allowed = {p.product_url for r in results for p in r.products}
        if self.llm.enabled and any(r.status == "ok" for r in results):
            try:
                candidate = await self.llm.complete(
                    COMBINER_PROMPT, format_results_for_llm(message, results, combos, plan.total_budget))
                if not links_are_valid(candidate, allowed):
                    raise LLMError("reply contains a link that no agent returned")
                text = candidate
            except LLMError as exc:
                log.warning("LLM combine failed, using the template reply: %s", exc)
        if text is None:
            text = template_reply(plan, results, combos, self.display_limit)
        footer = freshness_footer(results)
        return f"{text}\n\n{footer}" if footer else text
