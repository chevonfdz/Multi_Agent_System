"""Polite HTTP fetcher: checks robots.txt, identifies itself and rate-limits per host (NFR-11)."""
from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlsplit

import requests

from app.scrapers.robots import RobotsRules, parse_robots

log = logging.getLogger(__name__)


class PoliteFetcher:
    def __init__(self, user_agent: str, default_delay: float = 1.0, timeout: float = 20.0,
                 session: requests.Session | None = None):
        self.user_agent = user_agent
        self.default_delay = default_delay
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent,
                                     "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        self._robots: dict[str, RobotsRules] = {}
        self._last_request: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _wait(self, host: str) -> None:
        rules = self._robots.get(host)
        delay = max(self.default_delay, (rules.crawl_delay or 0) if rules else 0)
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request[host] = time.monotonic()

    def _load_robots(self, scheme: str, host: str) -> RobotsRules:
        if host in self._robots:
            return self._robots[host]
        url = f"{scheme}://{host}/robots.txt"
        try:
            response = self.session.get(url, timeout=self.timeout)
            self._last_request[host] = time.monotonic()
            if response.status_code == 200:
                rules = parse_robots(response.text, self.user_agent)
            elif 400 <= response.status_code < 500:
                rules = RobotsRules.allow_all()      # no robots.txt: no restrictions
            else:
                rules = RobotsRules.deny_all()       # server error: be conservative
        except requests.RequestException as exc:
            log.warning("Could not read %s: %s", url, exc)
            rules = RobotsRules.deny_all()
        self._robots[host] = rules
        return rules

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        with self._lock_for(parts.netloc):
            rules = self._load_robots(parts.scheme, parts.netloc)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return rules.allowed(path)

    def get_text(self, url: str) -> str:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        host = urlsplit(url).netloc
        with self._lock_for(host):
            self._wait(host)
            response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text
