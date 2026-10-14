"""Website pages, health check, scheduler and response time (UM-9, FR-7, NFR-1, NFR-2)."""
import time

from app.scheduler.daily_jobs import start_scheduler, startup_refresh
from tests.conftest import chat


def test_pages_are_served(client):                                              # TC-23, TC-24
    login = client.get("/login.html")
    assert login.status_code == 200 and "Log in" in login.text
    register = client.get("/register.html")
    assert "Privacy notice" in register.text and "administrators can view them" in register.text
    index = client.get("/")
    # The chat page is hidden until the server confirms the login token.
    assert 'class="guarded"' in index.text and "/js/chat.js" in index.text
    assert "requireLogin" in client.get("/js/chat.js").text
    assert "adminOnly: true" in client.get("/js/admin.js").text
    assert client.get("/css/style.css").status_code == 200


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok" and data["llm"] == "none"
    assert data["agents"] == {"food": 5, "clothes": 6, "electronics": 7}


def test_scheduler_has_one_daily_job_per_agent(services, settings):            # FR-7
    settings.scrape_hour, settings.scrape_minute = 0, 0
    scheduler = start_scheduler(services.agents, settings)
    try:
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert set(jobs) == {"refresh_food", "refresh_clothes", "refresh_electronics"}
        for job in jobs.values():
            fields = {f.name: str(f) for f in job.trigger.fields}
            assert fields["hour"] == "0" and fields["minute"] == "0"
    finally:
        scheduler.shutdown(wait=False)


def test_startup_refresh_only_for_empty_agents(services, monkeypatch):
    started = startup_refresh(services.agents, "if_empty")
    assert started == []                                   # every agent already has data
    assert startup_refresh(services.agents, "never") == []


def test_admin_can_trigger_a_refresh(client, admin, services, monkeypatch):
    called = []
    for name, agent in services.agents.items():
        monkeypatch.setattr(agent, "refresh_data", lambda n=name: called.append(n) or {})
    res = client.post("/api/admin/refresh?agent=all", headers=admin)
    assert res.status_code == 202
    time.sleep(0.2)
    assert sorted(called) == ["clothes", "electronics", "food"]
    sources = client.get("/api/admin/sources", headers=admin).json()
    assert {s["agent"] for s in sources} == {"food", "clothes", "electronics"}


def test_response_times(client, customer):                                       # TC-38, TC-39
    single = ["Cheapest rice?", "laptops", "rain jacket", "power bank", "milk"] * 4
    combined = ["A rain jacket and a power bank", "rice and a shirt", "milk, shoes and a charger",
                "juice and earphones"] * 5
    for messages, limit in ((single, 10.0), (combined, 15.0)):
        timings = []
        for m in messages:
            start = time.perf_counter()
            chat(client, customer, m)
            timings.append(time.perf_counter() - start)
        timings.sort()
        assert timings[int(len(timings) * 0.95) - 1] <= limit
