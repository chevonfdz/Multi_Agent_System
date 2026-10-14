"""Task planner: routing, filters, clarification and follow-ups (FR-2, FR-3, FR-14)."""
import asyncio

import pytest

from app.db.models import Task
from app.history.history_repository import Message
from app.llm.client import LLMClient, LLMError
from app.orchestrator.keyword_fallback import plan_with_rules
from app.orchestrator.task_planner import TaskPlanner


def domains(plan):
    return [t.domain for t in plan.tasks]


@pytest.mark.parametrize("message, expected", [
    ("Cheapest 5kg rice?", ["food"]),                                    # TC-01
    ("Men's denim jackets in size L?", ["clothes"]),                     # TC-02
    ("Laptops under 200,000 with 16GB RAM", ["electronics"]),            # TC-03
    ("A rain jacket and a power bank", ["clothes", "electronics"]),      # TC-07
    ("Rice, a T-shirt and a phone charger", ["food", "clothes", "electronics"]),  # TC-08
    ("wireless earphones", ["electronics"]),
    ("women's dresses under $60", ["clothes"]),
    ("apple juice", ["food"]),
    ("apple watch", ["electronics"]),
])
def test_routing(message, expected):
    assert domains(plan_with_rules(message)) == expected


def test_filters_are_extracted():
    plan = plan_with_rules("Laptops under 200,000 with 16GB RAM")
    assert plan.tasks[0].filters["max_price"] == 200000
    assert "16gb" in plan.tasks[0].query and "laptop" in plan.tasks[0].query

    plan = plan_with_rules("Men's denim jackets in size L?")
    assert plan.tasks[0].filters["size"] == "L"

    plan = plan_with_rules("phones between 200 and 400")
    assert plan.tasks[0].filters == {"min_price": 200, "max_price": 400}

    assert plan_with_rules("Cheapest rice?").tasks[0].filters["sort"] == "price_asc"


def test_trailing_price_limit_applies_to_every_category():
    plan = plan_with_rules("a shirt and a charger under 50")
    assert [t.filters.get("max_price") for t in plan.tasks] == [50, 50]


def test_total_budget_is_detected():
    plan = plan_with_rules("a jacket and earbuds under 100 in total")
    assert plan.total_budget == 100
    assert domains(plan) == ["clothes", "electronics"]


def test_unclear_and_out_of_scope():
    plan = plan_with_rules("Apple")                                       # TC-04
    assert plan.clarify and "fruit" in plan.clarify and not plan.tasks
    assert plan.pending["type"] == "ambiguous"

    plan = plan_with_rules("What's the weather today?")                  # TC-05
    assert plan.out_of_scope and not plan.tasks

    assert plan_with_rules("hello").greeting


def _assistant(tasks, results=None, pending=None, mid=2):
    meta = {}
    if tasks:
        meta["tasks"] = [t.to_dict() for t in tasks]
        meta["results"] = results or {}
    if pending:
        meta["pending"] = pending
    return Message(mid, 1, "assistant", "reply", [t.domain for t in tasks], meta, "2026-01-01T00:00:00+00:00")


def _customer(text, mid=1):
    return Message(mid, 1, "customer", text, [], {}, "2026-01-01T00:00:00+00:00")


def plan(message, past, llm=None):
    return asyncio.run(TaskPlanner(llm or LLMClient()).plan(message, past))


def test_followup_after_combined_answer_asks_which_category():   # TC-10
    past = [_customer("A rain jacket and a power bank"),
            _assistant([Task("clothes", "rain jacket"), Task("electronics", "power bank")],
                       {"clothes": {"prices": [25.0, 39.99], "product_ids": ["a", "b"]},
                        "electronics": {"prices": [19.99, 99.99], "product_ids": ["c", "d"]}})]
    result = plan("Show me cheaper ones", past)
    assert result.clarify and "clothes" in result.clarify and "electronics" in result.clarify
    assert not result.tasks
    assert result.pending["type"] == "followup_category"

    # TC-11: the answer "power banks" calls only the electronics agent, with a lower price limit.
    past += [_customer("Show me cheaper ones", 3), _assistant([], pending=result.pending, mid=4)]
    answer = plan("power banks", past)
    assert domains(answer) == ["electronics"]
    assert answer.tasks[0].filters["max_price"] == pytest.approx(59.98)     # middle of 19.99 and 99.99
    assert answer.tasks[0].filters["exclude_ids"] == ["c", "d"]


def test_followup_after_single_category_goes_straight_to_agent():  # TC-06
    past = [_customer("laptops"),
            _assistant([Task("electronics", "laptop")],
                       {"electronics": {"prices": [409.63, 899.0], "product_ids": ["x", "y"]}})]
    result = plan("Show me cheaper ones", past)
    assert not result.clarify
    assert domains(result) == ["electronics"]
    assert result.tasks[0].filters["max_price"] == pytest.approx(654.31, abs=0.01)
    assert result.tasks[0].filters["exclude_ids"] == ["x", "y"]


def test_more_excludes_products_already_shown():
    past = [_customer("laptops"),
            _assistant([Task("electronics", "laptop")], {"electronics": {"prices": [1], "product_ids": ["x"]}})]
    result = plan("any others?", past)
    assert result.tasks[0].filters["exclude_ids"] == ["x"]


def test_ambiguous_answer_is_resolved():
    first = plan_with_rules("apple")
    past = [_customer("apple"), _assistant([], pending=first.pending)]
    result = plan("the fruit", past)
    assert domains(result) == ["food"] and result.tasks[0].query == "apple"
    result = plan("I mean the brand", past)
    assert domains(result) == ["electronics"]


def test_unrelated_reply_to_a_question_is_planned_normally():
    past = [_customer("apple"), _assistant([], pending=plan_with_rules("apple").pending)]
    assert domains(plan("show me laptops", past)) == ["electronics"]


class FailingLLM(LLMClient):
    @property
    def enabled(self):
        return True

    async def complete_json(self, *args, **kwargs):
        raise LLMError("offline")


class FakeLLM(LLMClient):
    @property
    def enabled(self):
        return True

    async def complete_json(self, system, user, schema, max_tokens=4000):
        return {"tasks": [{"domain": "clothes", "query": "rain jacket", "max_price": 0, "min_price": 0, "size": ""},
                          {"domain": "electronics", "query": "power bank", "max_price": 50, "min_price": 0, "size": ""}],
                "followup": False, "categories_named": ["clothes", "electronics"], "modifier": "none",
                "clarify": "", "out_of_scope": False, "greeting": False, "total_budget": 0, "sort": "relevance"}


def test_llm_failure_falls_back_to_rules():
    result = plan("A rain jacket and a power bank", [], llm=FailingLLM())
    assert result.source == "rules" and domains(result) == ["clothes", "electronics"]


def test_llm_plan_is_used_when_available():
    result = plan("something", [], llm=FakeLLM())
    assert result.source == "llm"
    assert domains(result) == ["clothes", "electronics"]
    assert result.tasks[1].filters == {"max_price": 50.0}
