"""Shared budget across categories (FR-14) as a small constraint satisfaction problem.

Variables: one product per category. Domains: each agent's results.
Constraint: the sum of the chosen prices must not exceed the budget.
Solved with backtracking search; products are tried cheapest first, so a branch is pruned
as soon as even the cheapest completion would exceed the budget.
"""
from __future__ import annotations

from app.db.models import AgentReply, Product


def solve_budget(results: list[AgentReply], budget: float, max_combos: int = 3,
                 max_solutions: int = 500) -> list[tuple[list[Product], float]]:
    domains = [sorted(r.products, key=lambda p: p.price) for r in results if r.status == "ok" and r.products]
    if len(domains) < 2 or len(domains) != len(results):
        return []
    # Cheapest possible total of the remaining categories, for pruning.
    min_rest = [0.0] * (len(domains) + 1)
    for i in range(len(domains) - 1, -1, -1):
        min_rest[i] = domains[i][0].price + min_rest[i + 1]

    solutions: list[tuple[list[Product], float]] = []
    chosen: list[Product] = []

    def backtrack(i: int, total: float) -> None:
        if len(solutions) >= max_solutions:
            return
        if i == len(domains):
            solutions.append((list(chosen), round(total, 2)))
            return
        for product in domains[i]:
            if total + product.price + min_rest[i + 1] > budget + 1e-9:
                break  # sorted by price: every later product is more expensive
            chosen.append(product)
            backtrack(i + 1, total + product.price)
            chosen.pop()

    backtrack(0, 0.0)
    # Prefer combinations that use the budget well and have good ratings.
    solutions.sort(key=lambda s: (-s[1], -sum((p.rating or 0) for p in s[0])))
    return solutions[:max_combos]
