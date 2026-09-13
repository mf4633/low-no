"""Headless runs, for balance work rather than play.

A bot that plays adequately is the cheapest balance test there is: if a naive
policy starves by month four the numbers are wrong, and if it wins the game
without ever reading a price they are wrong in the other direction.
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional

from . import config as C
from .advisor import route_from, scan
from .engine import GameState
from .goods import good
from .scenario import new_game
from .trade import Order, Stop

# Feed the town, then work up the chain. Order is a preference, not a queue --
# the bot takes the first thing it can actually afford and has land for.
HOME_PLAN = [
    "farm", "mill", "bakery", "orchard", "granary", "woodcutter", "farm",
    "mill", "bakery", "quarry", "trading_post", "sawmill", "cottage",
    "clay_pit", "kiln", "market", "cottage", "sheep_farm", "weaver", "hop_farm", "brewery",
    "inn", "townhouse", "charcoal_burner", "iron_mine",
    "smelter", "guardhouse", "townhouse", "warehouse", "blacksmith",
    "stable", "chapel", "townhouse", "trading_post", "dairy", "armoury",
    "townhouse", "wall_tower", "townhouse", "cottage",
]
COLONY_PLAN = [
    "woodcutter", "cottage", "farm", "quarry", "saltworks", "clay_pit",
    "orchard", "cottage", "mill", "bakery", "granary", "iron_mine",
    "charcoal_burner", "smelter", "cottage", "market", "townhouse",
]


class Bot:
    """Greedy but not clever: build what it can, keep carts on the best route."""

    def __init__(self, game: GameState, verbose: bool = False) -> None:
        self.game = game
        self.plans: Dict[str, List[str]] = {}
        self.verbose = verbose
        self.home = next(iter(game.world.settlements))
        self.supply_cart: Optional[int] = None

    def plan_for(self, key: str) -> List[str]:
        if key not in self.plans:
            self.plans[key] = list(HOME_PLAN if key == self.home else COLONY_PLAN)
        return self.plans[key]

    # ------------------------------------------------------------------ play
    def step(self) -> None:
        g = self.game
        self._build()
        self._settle()
        for s in g.world.settlements.values():
            self._govern(s)
            self._shutter(s)
        self._carts()

    def _build(self) -> None:
        g = self.game
        buffer = 900.0 + 40.0 * len(g.caravans)
        for key, s in g.world.settlements.items():
            plan = self.plan_for(key)
            if g.treasury <= buffer:
                return
            # Take the first affordable item rather than stalling on a blocked one.
            for i, b in enumerate(plan[:5]):
                if "begun" in g.build(key, b):
                    plan.pop(i)
                    break

    def _settle(self) -> None:
        g = self.game
        if not g.world.sites or g.treasury < 9000:
            return
        key = min(g.world.sites, key=lambda k: g.world.sites[k].coin_cost)
        g.found(key)

    def _govern(self, s) -> None:
        from .goods import RATION_GOODS, nourishment
        food = nourishment({k: s.market.stock[k] for k in RATION_GOODS})
        days = food / max(0.2 * s.population, 1e-6)
        s.ration_level = 3 if days > 30 else (2 if days > 10 else 1)
        s.tax_level = 2 if s.popularity > 30 else 1

    def _shutter(self, s) -> None:
        """Close works whose output is piled up and worthless; open them again
        when the glut clears. Wages do not stop for an unsold barrel."""
        for b in s.buildings:
            if not b.complete or not b.spec.outputs:
                continue
            rel = [s.market.price(k) / good(k).base_price for k in b.spec.outputs]
            if b.enabled and max(rel) < 0.55:
                b.enabled = False          # the yard is full and the price is on the floor
            elif not b.enabled and max(rel) > 0.95:
                b.enabled = True

    def _carts(self) -> None:
        g = self.game
        if len(g.caravans) < g.caravan_limit and g.treasury > 1200:
            g.new_caravan(self.home)
        colonies = [k for k in g.world.settlements if k != self.home]
        idle: List = []
        for c in g.caravans:
            # One cart runs food out to the newest colony until it feeds itself.
            if colonies and (self.supply_cart in (None, c.uid)):
                col = g.world.settlements[colonies[-1]]
                if col.market.stock["bread"] + col.market.stock["apples"] < 150:
                    self.supply_cart = c.uid
                    if not c.running:
                        c.set_route([
                            Stop(node=self.home,
                                 buy=[Order("bread", 60), Order("apples", 40)]),
                            Stop(node=colonies[-1],
                                 sell=[Order("bread", -1), Order("apples", -1)]),
                        ])
                        c.start()
                    continue
                if self.supply_cart == c.uid:
                    self.supply_cart = None
                    c.halt()
            if c.running and c.route:
                continue
            idle.append(c)
        if idle:
            # Shop once for the whole fleet and hand each cart a different
            # trade: three carts on one route is three carts crushing one price.
            opts = scan(g.world, self.home, capacity=idle[0].capacity,
                        speed=idle[0].speed, budget=max(0.0, g.treasury * 0.5),
                        top=3 + len(idle))
            taken = {tuple(sorted((s.node for s in c.route))) for c in g.caravans
                     if c.running and c.route}
            for c in idle:
                for opp in opts:
                    sig = tuple(sorted((opp.frm, opp.to)))
                    if sig in taken or opp.per_day <= 0:
                        continue
                    c.set_route(route_from(opp))
                    c.start()
                    taken.add(sig)
                    break
        # Re-shop every three weeks; an edge does not keep.
        if g.day % 21 == 0:
            for c in g.caravans:
                # Only re-shop an empty cart: a route change mid-load strands
                # whatever it is carrying.
                if c.uid != self.supply_cart and not c.cargo:
                    c.halt()

    def run(self, days: int) -> List[dict]:
        out = []
        for _ in range(days):
            self.step()
            self.game.tick()
            out.append(self.game.history[-1])
            if self.game.over:
                break
        return out


def report(game: GameState) -> str:
    lines = [f"day {game.day} ({game.date_str()})",
             f"  treasury  {game.treasury:>12,.0f}c",
             f"  net worth {game.net_worth():>12,.0f}c",
             f"  souls     {game.population:>12,.0f}   caravans {len(game.caravans)}"
             f"   trade {sum(c.total_profit for c in game.caravans):>10,.0f}c"]
    for s in game.world.settlements.values():
        stock = sorted(((v, k) for k, v in s.market.stock.items() if v > 1), reverse=True)
        lines.append(f"  {s.name:<10} pop {s.population:>5,.0f} mood {s.popularity:>3.0f}"
                     f" roofs {s.housing:>5,.0f} works {len(s.buildings):>3}"
                     f"  | " + ", ".join(f"{k} {v:.0f}" for v, k in stock[:6]))
    if game.over:
        lines.append(f"  ENDING    {game.over}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="run Marchlands headless")
    ap.add_argument("--days", type=int, default=C.GOAL_DAYS)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--every", type=int, default=180, help="report interval")
    args = ap.parse_args(argv)
    game = new_game(seed=args.seed)
    bot = Bot(game)
    for _ in range(args.days):
        bot.step()
        game.tick()
        if game.day % args.every == 0:
            print(report(game), flush=True)
        if game.over:
            break
    print("-" * 60)
    print(report(game))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
