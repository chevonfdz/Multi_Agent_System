"""Daily refresh at the start of the day (FR-7): one independent job per agent."""
from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app.agents.base_agent import BaseAgent
from config.settings import Settings

log = logging.getLogger(__name__)


def start_scheduler(agents: dict[str, BaseAgent], settings: Settings) -> BackgroundScheduler:
    kwargs = {"timezone": settings.timezone} if settings.timezone else {}
    scheduler = BackgroundScheduler(**kwargs)
    for agent in agents.values():
        scheduler.add_job(agent.refresh_data, "cron", hour=settings.scrape_hour,
                          minute=settings.scrape_minute, id=f"refresh_{agent.name}",
                          max_instances=1, coalesce=True, misfire_grace_time=3600)
    scheduler.start()
    log.info("Daily refresh scheduled at %02d:%02d for: %s", settings.scrape_hour,
             settings.scrape_minute, ", ".join(agents))
    return scheduler


def startup_refresh(agents: dict[str, BaseAgent], mode: str) -> list[str]:
    """Run a first scrape in the background so a fresh install has data to search."""
    started = []
    for agent in agents.values():
        if mode == "always" or (mode == "if_empty" and agent.repo.count(include_unavailable=True) == 0):
            threading.Thread(target=agent.refresh_data, name=f"startup-refresh-{agent.name}",
                             daemon=True).start()
            started.append(agent.name)
    if started:
        log.info("Startup scrape running in the background for: %s", ", ".join(started))
    return started
