"""Central router agent: the single entry point for customer messages.

plan -> call the domain agents in parallel -> combine into one reply -> save the turn.
Every turn also records a trace of what happened (planner decision, each agent's database
search, timings), which the website's live architecture view replays step by step.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base_agent import BaseAgent
from app.db.models import AgentReply, Task, TaskPlan
from app.history.history_repository import HistoryRepository
from app.orchestrator.answer_combiner import AnswerCombiner, CombinedReply
from app.orchestrator.budget_solver import solve_budget
from app.orchestrator.task_planner import TaskPlanner

log = logging.getLogger(__name__)

GREETING_REPLY = (
    "Hi! I'm a shopping assistant with three specialist agents for **food**, **clothes** and "
    "**electronics**. I search several online shops and combine the answers for you.\n\n"
    "Try asking:\n"
    "- Cheapest rice?\n"
    "- Laptops under $500 with 8GB RAM\n"
    "- A rain jacket and a power bank\n"
    "- Running shoes and earphones under $150 in total"
)
OUT_OF_SCOPE_REPLY = (
    "Sorry, I can only help with **food**, **clothes** and **electronics** products. "
    "For example, try \"wireless earphones\", \"women's dresses under $60\" or \"cheapest rice\"."
)
ERROR_REPLY = "Sorry, something went wrong while handling that. Please try again."


@dataclass
class ChatResult:
    reply: str
    categories: list[str]
    meta: dict[str, Any]
    message_id: int | None = None
    trace: dict[str, Any] = field(default_factory=dict)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class CentralAgent:
    def __init__(self, agents: dict[str, BaseAgent], planner: TaskPlanner, combiner: AnswerCombiner,
                 history: HistoryRepository, agent_timeout: float = 10.0, context_messages: int = 10):
        self.agents = agents
        self.planner = planner
        self.combiner = combiner
        self.history = history
        self.agent_timeout = agent_timeout
        self.context_messages = context_messages

    async def handle(self, user_id: int, conversation_id: int, message: str) -> ChatResult:
        started = time.perf_counter()
        trace: dict[str, Any] = {"message": message}
        past = self.history.load_recent(conversation_id, last_n=self.context_messages)
        trace["history"] = {"loaded": len(past)}
        combined: CombinedReply | None = None
        try:
            t = time.perf_counter()
            plan = await self.planner.plan(message, past)
            trace["planner"] = self._plan_trace(plan, _ms(t))
            results: list[AgentReply] = []
            if plan.needs_agents:
                results = await self._call_agents(plan)
                trace["agents"] = [self._agent_trace(r) for r in results]
                combos = None
                if plan.total_budget and len(results) > 1:
                    combos = solve_budget(results, plan.total_budget)
                    trace["budget"] = {"budget": plan.total_budget, "combinations": len(combos)}
                t = time.perf_counter()
                combined = await self.combiner.combine(message, plan, results, combos)
                trace["combiner"] = {"mode": combined.mode, "ms": _ms(t), "sections": len(combined.sections)}
                reply = combined.text
            else:
                reply = self._non_task_reply(plan)
                trace["agents"] = []
            meta = self._meta(plan, results, combined)
            categories = [t.domain for t in plan.tasks] if plan.needs_agents else []
        except Exception as exc:  # never fail the request; log and answer politely
            log.exception("Central agent failed for conversation %s", conversation_id)
            plan, results, reply, categories = TaskPlan(), [], ERROR_REPLY, []
            meta = {"error": True}
            trace["error"] = type(exc).__name__

        calls = [{"agent": r.agent, "sub_question": r.query, "filters": r.filters, "status": r.status,
                  "products_found": len(r.products), "latency_ms": r.latency_ms, "error": r.error}
                 for r in results]
        trace["total_ms"] = _ms(started)
        trace["saved"] = {"agent_call_rows": len(calls)}
        meta["trace"] = trace
        _, assistant_id = self.history.save_turn(conversation_id, message, reply, categories, meta, calls)
        trace["saved"]["message_id"] = assistant_id
        return ChatResult(reply=reply, categories=categories, meta=meta, message_id=assistant_id, trace=trace)

    async def _call_agents(self, plan: TaskPlan) -> list[AgentReply]:
        limit = 10 if plan.total_budget else None
        calls = [self._call(task, limit) for task in plan.tasks]
        return list(await asyncio.gather(*calls))      # all agents at the same time (FR-11)

    async def _call(self, task: Task, limit: int | None) -> AgentReply:
        started = time.perf_counter()
        agent = self.agents.get(task.domain)
        try:
            if agent is None:
                raise RuntimeError(f"No agent for '{task.domain}'")
            return await asyncio.wait_for(agent.answer(task, limit=limit), timeout=self.agent_timeout)
        except Exception as exc:  # one failing agent never sinks the others (FR-12)
            latency = int((time.perf_counter() - started) * 1000)
            error = "timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc) or type(exc).__name__
            log.warning("%s agent failed: %s", task.domain, error)
            return AgentReply(task.domain, "failed", [], "", None, query=task.query,
                              filters=task.filters, error=error[:500], latency_ms=latency)

    @staticmethod
    def _plan_trace(plan: TaskPlan, ms: float) -> dict[str, Any]:
        if plan.clarify:
            outcome = "clarify"
        elif plan.greeting:
            outcome = "greeting"
        elif plan.out_of_scope or not plan.tasks:
            outcome = "out_of_scope"
        else:
            outcome = "tasks"
        return {
            "mode": plan.source, "ms": ms, "outcome": outcome,
            "tasks": [{"domain": t.domain, "query": t.query,
                       "filters": {k: v for k, v in t.filters.items() if k != "exclude_ids"},
                       "excluded": len(t.filters.get("exclude_ids") or [])} for t in plan.tasks]
            if plan.needs_agents else [],
            "clarify": plan.clarify, "followup": plan.followup, "modifier": plan.modifier,
            "total_budget": plan.total_budget,
        }

    def _agent_trace(self, r: AgentReply) -> dict[str, Any]:
        return {"agent": r.agent, "query": r.query, "status": r.status, "latency_ms": r.latency_ms,
                "filters": {k: v for k, v in r.filters.items() if k != "exclude_ids"},
                "db": f"{r.agent}.db", "scanned": r.scanned, "matched": r.matched,
                "returned": len(r.products), "top": [p.name for p in r.products[:3]], "error": r.error}

    @staticmethod
    def _non_task_reply(plan: TaskPlan) -> str:
        if plan.clarify:
            return plan.clarify
        if plan.greeting:
            return GREETING_REPLY
        return OUT_OF_SCOPE_REPLY

    @staticmethod
    def _meta(plan: TaskPlan, results: list[AgentReply], combined: CombinedReply | None) -> dict[str, Any]:
        meta: dict[str, Any] = {"planner": plan.source}
        if plan.needs_agents:
            meta["tasks"] = [t.to_dict() for t in plan.tasks]
            meta["results"] = {r.agent: {"status": r.status,
                                         "product_ids": [p.product_id for p in r.products],
                                         "prices": [p.price for p in r.products]} for r in results}
        if combined is not None:
            meta["intro"] = combined.intro
            meta["sections"] = combined.sections
            meta["budget"] = combined.budget
            meta["footer"] = combined.footer
        if plan.total_budget:
            meta["total_budget"] = plan.total_budget
        if plan.pending:
            meta["pending"] = plan.pending
        if plan.clarify:
            meta["clarify"] = True
        return meta
