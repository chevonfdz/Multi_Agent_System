"""Task planner: decides which agents to call for a message (FR-2, FR-3).

Order of work for each message:
1. If the previous reply asked a clarifying question, try to resolve the answer.
2. Plan the message with the LLM (if configured) or with the keyword rules.
3. Resolve follow-ups ("show me cheaper ones") against the previous tasks and results.
   After a combined answer, a follow-up that names no category gets a question back
   asking which category is meant, and no agent is called.
"""
from __future__ import annotations

import logging
from statistics import median
from typing import Any

from app.db.models import CATEGORIES, Task, TaskPlan
from app.history.history_repository import Message
from app.llm.client import LLMClient, LLMError
from app.orchestrator.keyword_fallback import (AMBIGUOUS_QUESTIONS, categories_in_reply,
                                              detect_modifier, plan_with_rules)
from app.orchestrator.prompts import PLANNER_PROMPT, PLANNER_SCHEMA
from app.text_utils import content_terms

log = logging.getLogger(__name__)

LABELS = {"food": "food", "clothes": "clothes", "electronics": "electronics"}


class TaskPlanner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def plan(self, message: str, past: list[Message]) -> TaskPlan:
        last_reply = next((m for m in reversed(past) if m.sender == "assistant"), None)

        resolved = self._resolve_pending(message, last_reply, past)
        if resolved is not None:
            return resolved

        plan: TaskPlan | None = None
        if self.llm.enabled:
            try:
                plan = await self._plan_with_llm(message, past)
            except LLMError as exc:
                log.warning("LLM planning failed, using keyword rules: %s", exc)
        if plan is None:
            plan = plan_with_rules(message)
        return self._resolve_followup(plan, past)

    # ------------------------------------------------------------------ LLM
    async def _plan_with_llm(self, message: str, past: list[Message]) -> TaskPlan:
        lines = []
        for m in past[-6:]:
            who = "Customer" if m.sender == "customer" else "Assistant"
            text = " ".join(m.content.split())[:400]
            lines.append(f"{who}: {text}")
        user = ("Recent conversation:\n" + ("\n".join(lines) or "(none)") +
                f"\n\nLatest customer message:\n{message}")
        data = await self.llm.complete_json(PLANNER_PROMPT, user, PLANNER_SCHEMA)
        plan = TaskPlan(source="llm")
        sort = data.get("sort") if data.get("sort") in ("price_asc", "price_desc", "rating") else None
        for t in data.get("tasks", [])[:3]:
            if t.get("domain") not in CATEGORIES:
                continue
            filters: dict[str, Any] = {}
            if float(t.get("max_price") or 0) > 0:
                filters["max_price"] = float(t["max_price"])
            if float(t.get("min_price") or 0) > 0:
                filters["min_price"] = float(t["min_price"])
            if (t.get("size") or "").strip():
                filters["size"] = t["size"].strip().upper()
            if sort:
                filters["sort"] = sort
            if t["domain"] not in [x.domain for x in plan.tasks]:
                plan.tasks.append(Task(t["domain"], (t.get("query") or "").strip(), filters))
        plan.followup = bool(data.get("followup"))
        plan.categories_named = [c for c in data.get("categories_named", []) if c in CATEGORIES]
        modifier = data.get("modifier")
        plan.modifier = modifier if modifier in ("cheaper", "pricier", "more") else None
        if plan.followup and not plan.modifier:
            plan.modifier = detect_modifier(message)
        plan.clarify = (data.get("clarify") or "").strip() or None
        plan.out_of_scope = bool(data.get("out_of_scope")) and not plan.tasks
        plan.greeting = bool(data.get("greeting")) and not plan.tasks
        if float(data.get("total_budget") or 0) > 0 and len(plan.tasks) > 1:
            plan.total_budget = float(data["total_budget"])
            for task in plan.tasks:
                task.filters["max_price"] = plan.total_budget
        if plan.clarify:
            plan.tasks = []
        if plan.followup and not plan.tasks:
            plan.followup_filters = {"sort": sort} if sort else {}
        return plan

    # ------------------------------------------------------------------ clarification
    def _resolve_pending(self, message: str, last_reply: Message | None,
                         past: list[Message]) -> TaskPlan | None:
        pending = (last_reply.meta or {}).get("pending") if last_reply else None
        if not pending:
            return None
        options = [o for o in pending.get("options", []) if o in CATEGORIES]
        chosen = categories_in_reply(message, options)
        if not chosen:
            return None  # not an answer to our question: plan the message normally

        if pending.get("type") == "ambiguous":
            term = pending.get("term", "")
            extra = [t for t in content_terms(message) if t not in {"fruit", "brand", "food", "electronic",
                                                                    "electronics", "the"}]
            filters = dict(pending.get("filters") or {})
            if pending.get("sort"):
                filters["sort"] = pending["sort"]
            plan = TaskPlan(source="rules", categories_named=chosen[:1])
            plan.tasks = [Task(chosen[0], " ".join([term] + [e for e in extra if e != term]), filters)]
            return plan

        if pending.get("type") == "followup_category":
            previous = previous_tasks(past)
            plan = TaskPlan(source="rules", followup=True, categories_named=chosen,
                            modifier=pending.get("modifier"))
            for domain in chosen:
                base = previous["tasks"].get(domain)
                if base is None:
                    continue
                plan.tasks.append(apply_modifier(base, previous["results"].get(domain, {}),
                                                 pending.get("modifier"), pending.get("filters") or {}))
            return plan if plan.tasks else None
        return None

    # ------------------------------------------------------------------ follow-ups
    def _resolve_followup(self, plan: TaskPlan, past: list[Message]) -> TaskPlan:
        if not plan.followup:
            return plan
        previous = previous_tasks(past)
        prev_tasks: dict[str, Task] = previous["tasks"]

        if not plan.categories_named and not plan.tasks:
            if not prev_tasks:
                return TaskPlan(source=plan.source, clarify=(
                    "What would you like me to look for? I can search food, clothes and electronics."))
            if len(prev_tasks) > 1:
                # FR-3: after a combined answer, ask which category instead of guessing.
                question = which_category_question(prev_tasks, plan.modifier)
                return TaskPlan(source=plan.source, clarify=question, pending={
                    "type": "followup_category", "options": list(prev_tasks),
                    "modifier": plan.modifier, "filters": plan.followup_filters})
            domain = next(iter(prev_tasks))
            plan.tasks = [apply_modifier(prev_tasks[domain], previous["results"].get(domain, {}),
                                         plan.modifier, plan.followup_filters)]
            plan.categories_named = [domain]
            return plan

        # Follow-up that names its categories, e.g. "cheaper laptops".
        updated = []
        for task in plan.tasks:
            base = prev_tasks.get(task.domain)
            if base is None:
                updated.append(task)
                continue
            merged = Task(task.domain, task.query or base.query,
                          {k: v for k, v in task.filters.items()})
            updated.append(apply_modifier(merged, previous["results"].get(task.domain, {}),
                                          plan.modifier, {}))
        plan.tasks = updated
        return plan


def previous_tasks(past: list[Message]) -> dict[str, Any]:
    """Tasks and results of the most recent reply that called agents."""
    for m in reversed(past):
        if m.sender != "assistant":
            continue
        tasks = (m.meta or {}).get("tasks") or []
        if tasks:
            return {"tasks": {t["domain"]: Task.from_dict(t) for t in tasks},
                    "results": (m.meta or {}).get("results") or {}}
    return {"tasks": {}, "results": {}}


def apply_modifier(base: Task, result: dict[str, Any], modifier: str | None,
                   extra_filters: dict[str, Any]) -> Task:
    filters = {k: v for k, v in base.filters.items() if k not in ("exclude_ids",)}
    filters.update(extra_filters or {})
    prices = [float(p) for p in result.get("prices", [])]
    shown = list(result.get("product_ids", []))
    # "Cheaper" = products not shown yet that cost less than the middle price of those shown.
    if modifier == "cheaper" and prices:
        filters["max_price"] = round(median(prices) - 0.01, 2)
        filters.pop("min_price", None)
        filters["sort"] = "price_asc"
        filters["exclude_ids"] = shown
    elif modifier == "pricier" and prices:
        filters["min_price"] = round(median(prices) + 0.01, 2)
        filters.pop("max_price", None)
        filters["sort"] = "price_asc"
        filters["exclude_ids"] = shown
    elif modifier == "more":
        filters["exclude_ids"] = shown
    return Task(base.domain, base.query, filters)


def which_category_question(prev_tasks: dict[str, Task], modifier: str | None) -> str:
    adjective = {"cheaper": "cheaper ", "pricier": "more expensive ", "more": "more "}.get(modifier or "", "")
    options = [f"{adjective}{t.query or 'products'} ({LABELS[d]})" for d, t in prev_tasks.items()]
    if len(options) == 2:
        joined = f"{options[0]} or {options[1]}"
    else:
        joined = ", ".join(options[:-1]) + f" or {options[-1]}"
    return f"Which category do you mean: {joined}?"


__all__ = ["TaskPlanner", "previous_tasks", "apply_modifier", "which_category_question",
           "AMBIGUOUS_QUESTIONS"]
