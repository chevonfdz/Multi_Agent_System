"""Product search, the answer combiner and the budget solver (FR-4, FR-9, FR-11..FR-14)."""
import asyncio

from app.db.models import AgentReply, Task, TaskPlan
from app.llm.client import LLMClient, LLMError
from app.orchestrator.answer_combiner import AnswerCombiner, links_are_valid, template_reply
from app.orchestrator.budget_solver import solve_budget
from tests.conftest import SEED, product


def test_search_handles_plurals_synonyms_and_filters(agents):
    electronics = agents["electronics"]
    names = [p.name for p in electronics.repo.search("power banks", {}, 5, electronics.SYNONYMS)]
    assert "Apple MagSafe Battery Pack" in names and "Budget Power Bank 10000mAh" in names
    assert "Apple iPhone Charger" not in names

    laptops = electronics.repo.search("laptop 16gb", {}, 5, electronics.SYNONYMS)
    assert laptops[0].name == "Dell XPS 13"          # matches both terms, ranks first

    cheap = electronics.repo.search("laptop", {"max_price": 500}, 5, electronics.SYNONYMS)
    assert [p.name for p in cheap] == ["Lenovo V110-15ISK"]

    by_price = electronics.repo.search("power bank", {"sort": "price_asc"}, 5, electronics.SYNONYMS)
    assert [p.price for p in by_price] == sorted(p.price for p in by_price)

    clothes = agents["clothes"]
    jackets = [p.name for p in clothes.repo.search("rain jacket", {}, 5, clothes.SYNONYMS)]
    assert jackets[0].startswith(("Rain Jacket", "Lightweight Rain Jacket"))
    excluded = clothes.repo.search("jacket", {"exclude_ids": [p.product_id for p in SEED["clothes"][:2]]}, 5,
                                   clothes.SYNONYMS)
    assert [p.name for p in excluded] == ["Lightweight Rain Jacket"]


def test_unavailable_products_are_not_suggested(agents):
    repo = agents["food"].repo
    gone = product("food", "Discontinued Rice", 1.0, "dummyjson.com", "pantry", availability="unavailable")
    repo.upsert_many([gone])
    assert "Discontinued Rice" not in [p.name for p in repo.search("rice", {}, 10)]


def reply(agent, status, products=(), query="q", filters=None, last_updated="2026-10-14T00:12:00+00:00"):
    return AgentReply(agent, status, list(products), "", last_updated, query=query, filters=filters or {})


def test_template_reply_sections_and_failures():
    jacket = SEED["clothes"][0]
    results = [reply("clothes", "ok", [jacket], "rain jacket"), reply("electronics", "failed", query="power bank")]
    text = template_reply(TaskPlan(tasks=[Task("clothes", "rain jacket"), Task("electronics", "power bank")]), results)
    assert "### Clothes · rain jacket" in text and "### Electronics · power bank" in text
    assert jacket.product_url in text and "$39.99" in text
    assert "couldn't check electronics right now" in text                    # FR-12

    empty = template_reply(TaskPlan(), [reply("electronics", "empty", query="laptop", filters={"max_price": 1000})])
    assert "No matching electronics products found under $1,000.00" in empty    # TC-14
    assert "### Electronics · laptop · under $1,000.00" in empty

    all_failed = template_reply(TaskPlan(), [reply("food", "failed"), reply("clothes", "failed")])
    assert "couldn't check the shops" in all_failed


def test_freshness_footer_is_added():                                         # TC-15
    text = asyncio.run(AnswerCombiner(LLMClient()).combine(
        "rice", TaskPlan(), [reply("food", "ok", [SEED["food"][0]], "rice")]))
    assert text.strip().endswith("_Data last updated: food 14 Oct 2026 00:12 UTC_")


class InventingLLM(LLMClient):
    @property
    def enabled(self):
        return True

    async def complete(self, system, user, max_tokens=4000):
        return "Try this: [Fake](https://made-up.example/product)"


class OfflineLLM(LLMClient):
    @property
    def enabled(self):
        return True

    async def complete(self, *args, **kwargs):
        raise LLMError("offline")


def test_combiner_rejects_invented_links_and_survives_llm_failure():         # FR-13
    results = [reply("food", "ok", [SEED["food"][0]], "rice")]
    for llm in (InventingLLM(), OfflineLLM()):
        text = asyncio.run(AnswerCombiner(llm).combine("rice", TaskPlan(), results))
        assert "made-up.example" not in text and SEED["food"][0].product_url in text
    assert links_are_valid("see https://a/1", {"https://a/1"})
    assert not links_are_valid("see https://b/2", {"https://a/1"})
    assert not links_are_valid("no links at all", {"https://a/1"})


def test_budget_solver_finds_combinations_within_budget():                   # FR-14
    shoes = [product("clothes", "Shoe A", 49.99, "s", "shoes"), product("clothes", "Shoe B", 120.0, "s", "shoes")]
    phones = [product("electronics", "Earphone A", 49.99, "s", "audio"),
              product("electronics", "Earphone B", 129.99, "s", "audio")]
    combos = solve_budget([reply("clothes", "ok", shoes), reply("electronics", "ok", phones)], 150)
    assert combos and all(total <= 150 for _, total in combos)
    assert {p.name for p in combos[0][0]} == {"Shoe A", "Earphone A"}
    assert solve_budget([reply("clothes", "ok", shoes), reply("electronics", "ok", phones)], 50) == []
    assert solve_budget([reply("clothes", "ok", shoes), reply("electronics", "failed")], 500) == []


def test_results_must_match_the_requested_product_type(agents):
    clothes = agents["clothes"]
    boots = product("clothes", "Hiking Boots for Outdoor Adventures", 89.99, "web-scraping.dev", "shoes",
                    description="Boots with a waterproof upper.")
    clothes.repo.upsert_many([boots])
    loose = clothes.repo.search("rain jacket", {}, 10, clothes.SYNONYMS)
    strict = clothes.repo.search("rain jacket", {}, 10, clothes.SYNONYMS, clothes.product_types())
    assert boots.name in [p.name for p in loose]
    assert boots.name not in [p.name for p in strict]
    assert strict and all("jacket" in p.name.lower() for p in strict)

    electronics = agents["electronics"]
    names = [p.name for p in electronics.repo.search("wireless earphones", {}, 10, electronics.SYNONYMS,
                                                     electronics.product_types())]
    assert names == ["Beats Flex Wireless Earphones"]
