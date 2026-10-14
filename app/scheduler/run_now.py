"""Run the daily refresh on demand.

    python -m app.scheduler.run_now            (all agents)
    python -m app.scheduler.run_now food       (one agent)
"""
from __future__ import annotations

import sys

from app.services import build_agents, setup_logging
from config.settings import Settings


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    setup_logging(settings)
    agents = build_agents(settings)
    targets = argv[1:] or ["all"]
    names = list(agents) if "all" in targets else targets
    unknown = [n for n in names if n not in agents]
    if unknown:
        print(f"Unknown agent(s): {', '.join(unknown)}. Choose from: all, {', '.join(agents)}")
        return 2
    exit_code = 0
    for name in names:
        print(f"Refreshing the {name} agent ...")
        summary = agents[name].refresh_data()
        for site in summary.get("sites", []):
            if site["status"] == "ok":
                print(f"  {site['site']}: {site['products']} products")
            else:
                exit_code = 1
                print(f"  {site['site']}: FAILED - {site.get('error')}")
        print(f"  {name}.db now has {summary.get('total_products', 0)} available products")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
