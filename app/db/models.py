"""Core data structures passed between the agents."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CATEGORIES = ("food", "clothes", "electronics")


@dataclass
class Task:
    """One sub-question for one domain agent."""
    domain: str                                   # "food" | "clothes" | "electronics"
    query: str                                    # cleaned sub-question, e.g. "rain jacket"
    filters: dict[str, Any] = field(default_factory=dict)  # max_price, min_price, size, sort, exclude_ids

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "query": self.query, "filters": dict(self.filters)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(domain=data["domain"], query=data.get("query", ""),
                   filters=dict(data.get("filters") or {}))


@dataclass
class TaskPlan:
    """What the task planner decided to do with a message."""
    tasks: list[Task] = field(default_factory=list)
    followup: bool = False
    categories_named: list[str] = field(default_factory=list)
    clarify: str | None = None                    # question to ask instead of calling agents
    out_of_scope: bool = False
    greeting: bool = False
    total_budget: float | None = None             # shared budget across categories (FR-14)
    pending: dict[str, Any] | None = None         # clarification state saved with the reply
    modifier: str | None = None                   # follow-up: "cheaper" | "pricier" | "more"
    followup_filters: dict[str, Any] = field(default_factory=dict)
    source: str = "rules"                         # "rules" or "llm"

    @property
    def needs_agents(self) -> bool:
        return bool(self.tasks) and not self.clarify and not self.out_of_scope


@dataclass
class Product:
    """Text-only product record (no images are stored - FR-8)."""
    product_id: str
    name: str
    category: str
    price: float
    currency: str
    product_url: str
    source_site: str
    availability: str = "in_stock"
    sub_category: str = ""
    brand: str = ""
    description: str = ""
    rating: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    first_seen_at: str | None = None
    scraped_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReply:
    agent: str
    status: str                                   # "ok" | "empty" | "failed"
    products: list[Product]
    summary: str
    last_updated: str | None
    query: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0
    scanned: int = 0        # products in the agent's database that were checked
    matched: int = 0        # products that matched the query and filters
