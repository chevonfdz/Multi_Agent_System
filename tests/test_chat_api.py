"""End-to-end chat through the API with seeded product data (FR-1..FR-4, FR-9..FR-14)."""
import re

from tests.conftest import SEED, chat


def calls_for(services, conversation_id):
    messages = services.history.messages(conversation_id, include_calls=True)
    return [m.agent_calls for m in messages if m.sender == "assistant"]


def test_single_category_question(client, customer, services):            # TC-01, TC-21
    data = chat(client, customer, "Cheapest rice?")
    assert data["categories"] == ["food"]
    assert "### Food · rice" in data["reply"] and "**Rice**" in data["reply"]
    calls = calls_for(services, data["conversation_id"])[-1]
    assert len(calls) == 1 and calls[0]["agent"] == "food" and calls[0]["status"] == "ok"


def test_price_filter_is_applied(client, customer):                         # TC-03
    data = chat(client, customer, "Laptops under 500 with 8GB RAM")
    assert "Lenovo V110-15ISK" in data["reply"] and "Dell XPS 13" not in data["reply"]


def test_combined_answer(client, customer, services):                       # TC-07
    data = chat(client, customer, "A rain jacket and a power bank")
    assert data["categories"] == ["clothes", "electronics"]
    reply = data["reply"]
    assert reply.index("### Clothes · rain jacket") < reply.index("### Electronics · power bank")
    assert len(calls_for(services, data["conversation_id"])[-1]) == 2


def test_three_categories(client, customer):                                 # TC-08
    data = chat(client, customer, "Rice, a T-shirt and a phone charger")
    assert data["categories"] == ["food", "clothes", "electronics"]
    assert data["reply"].count("### ") == 3


def test_links_in_replies_come_from_the_databases(client, customer):        # TC-12, FR-4
    reply = chat(client, customer, "A rain jacket and a power bank")["reply"]
    known = {p.product_url for products in SEED.values() for p in products}
    links = re.findall(r"\((https?://[^)]+)\)", reply)
    assert links and set(links) <= known


def test_partial_failure(client, customer, services, monkeypatch):          # TC-09, FR-12
    async def broken(task, limit=None):
        raise RuntimeError("database locked")
    monkeypatch.setattr(services.agents["electronics"], "answer", broken)
    data = chat(client, customer, "A rain jacket and a power bank")
    assert "### Clothes · rain jacket" in data["reply"]
    assert "couldn't check electronics right now" in data["reply"]
    statuses = {c["agent"]: c["status"] for c in calls_for(services, data["conversation_id"])[-1]}
    assert statuses == {"clothes": "ok", "electronics": "failed"}


def test_agent_timeout_is_handled(client, customer, services, monkeypatch):
    import asyncio
    services.central.agent_timeout = 0.05

    async def slow(task, limit=None):
        await asyncio.sleep(1)
    monkeypatch.setattr(services.agents["food"], "answer", slow)
    data = chat(client, customer, "rice and a shirt")
    assert "couldn't check food right now" in data["reply"]
    calls = calls_for(services, data["conversation_id"])[-1]
    assert [c["error"] for c in calls if c["agent"] == "food"] == ["timed out"]


def test_cheaper_after_combined_answer_asks_which_category(client, customer, services):   # TC-10, TC-11
    first = chat(client, customer, "A rain jacket and a power bank")
    cid = first["conversation_id"]
    question = chat(client, customer, "Show me cheaper ones", cid)
    assert question["reply"].startswith("Which category do you mean")
    assert "clothes" in question["reply"] and "electronics" in question["reply"]
    assert question["categories"] == []
    assert calls_for(services, cid)[-1] == []          # no agent called for the question

    answer = chat(client, customer, "power banks", cid)
    assert answer["categories"] == ["electronics"]
    calls = calls_for(services, cid)[-1]
    assert [c["agent"] for c in calls] == ["electronics"]
    shown = sorted(p.price for p in SEED["electronics"] if p.sub_category == "power banks")
    assert calls[0]["filters"]["max_price"] == round(shown[len(shown) // 2] - 0.01, 2)
    assert "There are no other cheaper power bank options" in answer["reply"]


def test_cheaper_after_single_category_answer(client, customer, services):  # TC-06
    first = chat(client, customer, "laptops")
    cid = first["conversation_id"]
    data = chat(client, customer, "Show me cheaper ones", cid)
    assert data["categories"] == ["electronics"]
    assert "Which category" not in data["reply"]


def test_clarifying_question_for_ambiguous_word(client, customer):          # TC-04
    first = chat(client, customer, "Apple")
    assert "fruit" in first["reply"] and first["categories"] == []
    data = chat(client, customer, "the fruit", first["conversation_id"])
    assert data["categories"] == ["food"] and "**Apple**" in data["reply"]


def test_out_of_scope_and_greeting(client, customer):                        # TC-05
    assert "only help with" in chat(client, customer, "What's the weather today?")["reply"]
    assert "food" in chat(client, customer, "hello")["reply"].lower()


def test_no_match_and_freshness(client, customer):                           # TC-14, TC-15
    data = chat(client, customer, "laptop under 100")
    assert "No matching electronics products found under $100.00" in data["reply"]
    assert "_Data last updated: electronics" in data["reply"]


def test_total_budget_combinations(client, customer):                        # TC-22, FR-14
    data = chat(client, customer, "running shoes and earphones under 150 in total")
    assert "Combinations within your total budget of $150.00" in data["reply"]
    assert "Running Shoes for Men" in data["reply"] and "Beats Flex Wireless Earphones" in data["reply"]


def test_history_is_saved_and_listed(client, customer):                      # FR-1
    first = chat(client, customer, "Cheapest rice?")
    chat(client, customer, "and milk", first["conversation_id"])
    convs = client.get("/api/conversations", headers=customer).json()
    assert convs[0]["conversation_id"] == first["conversation_id"]
    assert convs[0]["title"] == "Cheapest rice?"
    detail = client.get(f"/api/conversations/{first['conversation_id']}", headers=customer).json()
    assert [m["sender"] for m in detail["messages"]] == ["customer", "assistant", "customer", "assistant"]


def test_central_agent_never_returns_500(client, customer, services, monkeypatch):
    async def explode(message, past):
        raise ValueError("bug")
    monkeypatch.setattr(services.central.planner, "plan", explode)
    data = chat(client, customer, "rice")
    assert "something went wrong" in data["reply"]

