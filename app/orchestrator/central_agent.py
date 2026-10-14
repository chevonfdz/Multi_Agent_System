"""Central router agent: the single entry point for customer messages.

plan -> call the domain agents in parallel -> combine into one reply -> save the turn.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import BaseAgent
from app.db.models import AgentReply, Task, TaskPlan
from app.history.history_repository import HistoryRepository
from app.orchestrator.answer_combiner import AnswerCombiner
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
        past = self.history.load_recent(conversation_id, last_n=self.context_messages)
        try:
            plan = await self.planner.plan(message, past)
            results: list[AgentReply] = []
            if plan.needs_agents:
                results = await self._call_agents(plan)
                combos = None
                if plan.total_budget and len(results) > 1:
                    combos = solve_budget(results, plan.total_budget)
                reply = await self.combiner.combine(message, plan, results, combos)
            else:
                reply = self._non_task_reply(plan)
            meta = self._meta(plan, results)
            categories = [t.domain for t in plan.tasks] if plan.needs_agents else []
        except Exception:  # never fail the request; log and answer politely
            log.exception("Central agent failed for conversation %s", conversation_id)
            plan, results, reply, categories = TaskPlan(), [], ERROR_REPLY, []
            meta = {"error": True}

        calls = [{"agent": r.agent, "sub_question": r.query, "filters": r.filters, "status": r.status,
                  "products_found": len(r.products), "latency_ms": r.latency_ms, "error": r.error}
                 for r in results]
        _, assistant_id = self.history.save_turn(conversation_id, message, reply, categories, meta, calls)
        return ChatResult(reply=reply, categories=categories, meta=meta, message_id=assistant_id)

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
            reply = await asyncio.wait_for(agent.answer(task, limit=limit), timeout=self.agent_timeout)
            return reply
        except Exception as exc:  # one failing agent never sinks the others (FR-12)
            latency = int((time.perf_counter() - started) * 1000)
            error = "timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc) or type(exc).__name__
            log.warning("%s agent failed: %s", task.domain, error)
            return AgentReply(task.domain, "failed", [], "", None, query=task.query,
                              filters=task.filters, error=error[:500], latency_ms=latency)

    @staticmethod
    def _non_task_reply(plan: TaskPlan) -> str:
        if plan.clarify:
            return plan.clarify
        if plan.greeting:
            return GREETING_REPLY
        return OUT_OF_SCOPE_REPLY

    @staticmethod
    def _meta(plan: TaskPlan, results: list[AgentReply]) -> dict[str, Any]:
        meta: dict[str, Any] = {"planner": plan.source}
        if plan.needs_agents:
            meta["tasks"] = [t.to_dict() for t in plan.tasks]
            meta["results"] = {r.agent: {"status": r.status,
                                         "product_ids": [p.product_id for p in r.products],
                                         "prices": [p.price for p in r.products]} for r in results}
        if plan.total_budget:
            meta["total_budget"] = plan.total_budget
        if plan.pending:
            meta["pending"] = plan.pending
        if plan.clarify:
            meta["clarify"] = True
        return meta
