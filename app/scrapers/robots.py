"""robots.txt rules with wildcard support (Python's urllib.robotparser ignores "*" and "$")."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RobotsRules:
    rules: list[tuple[bool, str]] = field(default_factory=list)   # (allow, pattern)
    crawl_delay: float | None = None
    disallow_everything: bool = False

    @classmethod
    def allow_all(cls) -> "RobotsRules":
        return cls()

    @classmethod
    def deny_all(cls) -> "RobotsRules":
        return cls(disallow_everything=True)

    def allowed(self, path: str) -> bool:
        if self.disallow_everything:
            return False
        path = path or "/"
        best_len = -1
        best_allow = True
        for allow, pattern in self.rules:
            if not pattern:
                continue  # an empty Disallow means "allow everything"
            if _pattern_matches(pattern, path):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow


def _pattern_matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "^" + re.escape(body).replace(r"\*", ".*") + ("$" if anchored else "")
    return re.match(regex, path) is not None


def parse_robots(text: str, agent_token: str) -> RobotsRules:
    """Return the rules of the group that applies to agent_token (falling back to "*")."""
    if text.lstrip().startswith("<"):
        return RobotsRules.allow_all()  # an HTML page, not a robots file
    groups: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or current["has_rules"]:
                current = {"agents": [], "rules": [], "delay": None, "has_rules": False}
                groups.append(current)
            current["agents"].append(value.lower())
        elif current is not None and key in ("allow", "disallow"):
            current["has_rules"] = True
            current["rules"].append((key == "allow", value))
        elif current is not None and key == "crawl-delay":
            current["has_rules"] = True
            try:
                current["delay"] = float(value)
            except ValueError:
                pass

    token = agent_token.lower()
    specific = [g for g in groups if any(a != "*" and a in token for a in g["agents"])]
    chosen = specific or [g for g in groups if "*" in g["agents"]]
    rules = RobotsRules()
    for group in chosen:
        rules.rules.extend(group["rules"])
        if group["delay"] is not None:
            rules.crawl_delay = max(rules.crawl_delay or 0, group["delay"])
    return rules
