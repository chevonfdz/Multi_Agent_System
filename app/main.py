"""FastAPI application factory.

Run with:  python run.py
      or:  uvicorn app.main:create_app --factory
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import chat_routes
from app.auth import auth_routes
from app.history import history_routes
from app.scheduler.daily_jobs import start_scheduler, startup_refresh
from app.services import Services, build_services, setup_logging
from app.users import admin_routes
from config.settings import Settings

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    setup_logging(settings)
    services = services or build_services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        for agent in services.agents.values():
            agent.repo.close_interrupted_runs()
        if settings.enable_scheduler:
            scheduler = start_scheduler(services.agents, settings)
        startup_refresh(services.agents, settings.scrape_on_startup)
        mode = (f"LLM ({services.llm.provider}, {services.llm.model})" if services.llm.enabled
                else "rule-based (no LLM)")
        log.info("Multi-agent shopping assistant ready - planner mode: %s", mode)
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Multi-Agent Shopping Assistant", version="1.0.0", lifespan=lifespan)
    app.state.services = services

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "llm": services.llm.provider if services.llm.enabled else "none",
                "agents": {name: agent.repo.count() for name, agent in services.agents.items()}}

    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(history_routes.router)
    app.include_router(admin_routes.router)
    # The website itself (login, register, chat and admin pages).
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app
