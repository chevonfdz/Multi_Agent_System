"""Builds and wires every component of the system from the settings."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

import yaml

from app.agents.base_agent import BaseAgent
from app.agents.clothes_agent import ClothesAgent
from app.agents.electronics_agent import ElectronicsAgent
from app.agents.food_agent import FoodAgent
from app.db.app_db import init_app_db
from app.db.product_repository import ProductRepository
from app.history.history_repository import HistoryRepository
from app.llm.client import LLMClient, build_llm
from app.orchestrator.answer_combiner import AnswerCombiner
from app.orchestrator.central_agent import CentralAgent
from app.orchestrator.task_planner import TaskPlanner
from app.scrapers.clothes_scraper import ClothesScraper
from app.scrapers.electronics_scraper import ElectronicsScraper
from app.scrapers.fetcher import PoliteFetcher
from app.scrapers.food_scraper import FoodScraper
from app.scrapers.media import MediaService
from app.users.audit_repository import AuditRepository
from app.users.user_repository import UserRepository
from config.settings import Settings

AGENT_CLASSES = {
    "food": (FoodAgent, FoodScraper),
    "clothes": (ClothesAgent, ClothesScraper),
    "electronics": (ElectronicsAgent, ElectronicsScraper),
}


@dataclass
class Services:
    settings: Settings
    users: UserRepository
    audit: AuditRepository
    history: HistoryRepository
    agents: dict[str, BaseAgent]
    llm: LLMClient
    central: CentralAgent
    media: MediaService


def load_websites(settings: Settings) -> dict[str, list[dict]]:
    with open(settings.websites_file, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {category: list(data.get(category) or []) for category in AGENT_CLASSES}


def build_agents(settings: Settings, fetch=None) -> dict[str, BaseAgent]:
    """One agent per category, each with its own website list, scraper and database."""
    if fetch is None:
        fetch = PoliteFetcher(settings.user_agent, settings.request_delay_seconds).get_text
    websites = load_websites(settings)
    agents: dict[str, BaseAgent] = {}
    for category, (agent_cls, scraper_cls) in AGENT_CLASSES.items():
        repo = ProductRepository(settings.product_db_path(category), category, agent_cls.EXTRA_FIELDS)
        scraper = scraper_cls(websites.get(category, []), fetch)
        agents[category] = agent_cls(repo, scraper, results_per_task=settings.results_per_category)
    return agents


def build_services(settings: Settings, agents: dict[str, BaseAgent] | None = None,
                   llm: LLMClient | None = None, media: MediaService | None = None) -> Services:
    init_app_db(settings.app_db_path)
    users = UserRepository(settings.app_db_path)
    audit = AuditRepository(settings.app_db_path)
    history = HistoryRepository(settings.app_db_path)
    # One polite fetcher shared by the scrapers and the photo service, so rate limits apply to both.
    fetch = PoliteFetcher(settings.user_agent, settings.request_delay_seconds).get_text
    agents = agents if agents is not None else build_agents(settings, fetch)
    media = media if media is not None else MediaService(fetch, load_websites(settings))
    llm = llm if llm is not None else build_llm(settings.llm_provider, settings.llm_model,
                                                 settings.llm_timeout_seconds)
    central = CentralAgent(agents, TaskPlanner(llm), AnswerCombiner(llm, settings.results_per_category), history,
                           agent_timeout=settings.agent_timeout_seconds,
                           context_messages=settings.history_context_messages)
    return Services(settings, users, audit, history, agents, llm, central, media)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_mas_handler", False) for h in root.handlers):
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(settings.log_dir / "app.log", maxBytes=2_000_000,
                                       backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler._mas_handler = True  # type: ignore[attr-defined]
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console._mas_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    root.addHandler(console)
    root.setLevel(logging.INFO)
