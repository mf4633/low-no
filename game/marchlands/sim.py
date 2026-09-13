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
from .goods import RATION_GOODS, good, nourishment
from .military import UNITS, host_strength
from .scenario import new_game
from .trade import Order, Stop

# Feed the town, then work up the chain. Order is a preference, not a queue --
# the bot takes the first thing it can actually afford and has land for.
HOME_PLAN = [
    # feed the town
    "farm", "mill", "bakery", "quarry", "orchard", "granary", "woodcutter",
    "farm", "mill", "bakery", "trading_post", "sawmill", "poleturner",
    "farm", "mill", "bakery", "orchard", "cottage", "guildhall",
    # make something worth carrying
    "clay_pit", "kiln", "cottage", "market", "farm", "mill", "bakery",
    "fletcher", "stone_wall", "sheep_farm", "weaver", "poleturner", "brewery",
    # grow, and start thinking about the walls
    "inn", "townhouse", "charcoal_burner", "iron_mine", "smelter",
    "stone_wall", "townhouse", "warehouse", "blacksmith", "wall_tower",
    "iron_mine", "smelter", "armoury", "armourer", "townhouse", "stable",
    "trading_post", "chapel",
    "fletcher", "townhouse", "wall_tower", "gatehouse", "garden",
    "guardhouse", "townhouse", "siege_yard", "townhouse", "cottage",
]
COLONY_PLAN = [
    "woodcutter", "cottage", "farm", "quarry", "saltworks", "clay_pit",
    "orchard", "cottage", "mill", "bakery", "granary", "iron_mine",
    "charcoal_burner", "smelter", "cottage", "market", "palisade",
    "townhouse", "barracks", "poleturner", "stone_wall", "townhouse",
]


class Bot:
    """A plain policy, used as a balance test rather than an opponent.

    It has one rule that matters: never spend the wage chest. Everything else
    is a priority ladder -- eat, defend, climb, build, learn, buy, expand --
    drawn from whatever is left after a month's payroll is set aside. Most of
    the ways a real player goes broke are ways this rule prevents.
    """

    def __init__(self, game: GameState, verbose: bool = False) -> None:
        self.game = game
        self.plans: Dict[str, List[str]] = {}
        self.verbose = verbose
        self.home = next(iter(game.world.settlements))
        self.supply_cart: Optional[int] = None
        self.errand: Optional[tuple] = None    # (cart uid, good, target stock)

    def plan_for(self, key: str) -> List[str]:
        if key not in self.plans:
            self.plans[key] = list(HOME_PLAN if key == self.home else COLONY_PLAN)
        return self.plans[key]

    # ------------------------------------------------------------- the purse
    #: The wage chest. Flat on purpose: a reserve that grows with the payroll
    #: throttles the very growth that pays the payroll, and the town stalls.
    RESERVE_BASE = 900.0
    RESERVE_PER_CART = 40.0

    @property
    def reserve(self) -> float:
        return self.RESERVE_BASE + self.RESERVE_PER_CART * len(self.game.caravans)

    def spendable(self) -> float:
        return self.game.treasury - self.reserve

    # ------------------------------------------------------------------ play
    def step(self) -> None:
        # Order matters more than any ladder. Capital first -- a town that arms
        # before it has anything worth defending never grows one -- and the
        # carts last, so they trade with whatever the day left in the chest.
        g = self.game
        self._climb()
        self._build()
        self._learn()
        self._settle()
        for s in g.world.settlements.values():
            self._govern(s)
            self._shutter(s)
        self._defend()
        self._carts()

    # -------------------------------------------------------------- the town
    def _govern(self, s) -> None:
        food = nourishment({k: s.market.stock[k] for k in RATION_GOODS})
        days = food / max(0.2 * s.population, 1e-6)
        s.ration_level = 3 if days > 30 else (2 if days > 10 else 1)
        s.tax_level = 2 if s.popularity > 30 else 1

    def _shutter(self, s) -> None:
        """Close works whose output is piled up and worthless; open them when
        the glut clears. Wages do not stop for an unsold barrel."""
        for b in s.buildings:
            if not b.complete or not b.spec.outputs:
                continue
            rel = [s.market.price(k) / good(k).base_price for k in b.spec.outputs]
            if b.enabled and max(rel) < 0.55:
                b.enabled = False
            elif not b.enabled and max(rel) > 0.95:
                b.enabled = True

    def _build(self) -> None:
        g = self.game
        buffer = self.reserve
        nxt = g.progress.next_age()
        if nxt and not g.progress.advancing:
            buffer = max(buffer, nxt.cost.get("coin", 0.0) * 1.15)
        if g.treasury <= buffer:
            return
        home = g.world.settlements[self.home]
        # A thrown-down keep is not just a ruin: without one there is no way
        # into the later ages at all. Put it back before anything else.
        if not home.count("keep") and "begun" in g.build(self.home, "keep"):
            return
        # One thing raised in each settlement each day: a colony that waits its
        # turn behind the capital never gets off the ground.
        for key in list(g.world.settlements):
            if g.treasury <= buffer:
                return
            plan = self.plan_for(key)
            for i, b in enumerate(plan[:6]):
                if "begun" in g.build(key, b):
                    plan.pop(i)
                    break

    def _settle(self) -> None:
        g = self.game
        if not g.world.sites or g.treasury < 9000:
            return
        g.found(min(g.world.sites, key=lambda k: g.world.sites[k].coin_cost))

    # ------------------------------------------------------------ the ladder
    def _climb(self) -> None:
        g, p = self.game, self.game.progress
        nxt = p.next_age()
        if p.advancing or not nxt:
            return
        if g.treasury < nxt.cost.get("coin", 0.0) + self.reserve:
            return
        msg = g.begin_age()
        if "needs" in msg:
            self._hoard(nxt)
            self._procure(nxt)

    def _learn(self) -> None:
        g, p = self.game, self.game.progress
        if p.researching:
            return
        for t in p.available():
            if g.treasury > t.cost.get("coin", 0.0) + self.reserve * 1.5:
                if "takes up" in g.research(t.key):
                    return

    def _hoard(self, age) -> None:
        """Stop spending the very thing the next age is waiting on.

        A blacksmith quietly eating three iron a day will hold a house in the
        same age for years. Shut it while the pile builds, open it after.
        """
        home = self.game.world.settlements[self.home]
        short = {k for k, q in age.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q * 1.4}
        for b in home.buildings:
            if not b.complete or not b.spec.inputs:
                continue
            if short & set(b.spec.inputs) and not short & set(b.spec.outputs):
                b.enabled = False
            elif not short and not b.enabled:
                b.enabled = True

    def _procure(self, age) -> None:
        """Buy what the next age wants and your own land will not give you.

        Iron under somebody else's hill is still iron -- this is the trade
        layer doing the thing it exists for.
        """
        g = self.game
        if self.errand is not None:
            return
        home = g.world.settlements[self.home]
        short = [(k, q * 1.4 - home.market.stock.get(k, 0.0))
                 for k, q in age.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q * 1.4]
        if not short:
            return
        key, need = max(short, key=lambda kv: kv[1])
        ceiling = good(key).base_price * 2.2      # dear, but not at any price
        need = min(need, max(0.0, g.treasury - 2 * self.reserve) * 0.3 / ceiling)
        if need < 5:
            return
        cart = next((c for c in g.caravans if not c.running and c.load < 5), None)
        if cart is None:
            return
        sellers = [(n, m.ask(key)) for n in g.world.towns
                   for m in [g.world.market_of(n)] if m and m.sells(key)]
        if not sellers:
            return
        where = min(sellers, key=lambda s: s[1])[0]
        cart.set_route([
            Stop(node=where, buy=[Order(key, min(need, cart.capacity), ceiling)]),
            Stop(node=self.home, sell=[Order(key, -1)]),
        ])
        cart.start()
        self.errand = (cart.uid, key, home.market.stock.get(key, 0.0) + need * 0.9)

    # ----------------------------------------------------------------- the wall
    def _defend(self) -> None:
        """Enough men on the wall to make a siege not worth a lord's time --
        and not one more, because every soldier is a field nobody is working."""
        g = self.game
        home = g.world.settlements[self.home]
        if not home.effect("muster") or g.treasury < 2 * self.reserve:
            return
        coming = [a for a in g.armies if a.owner != "player"]
        urgent = bool(coming)
        cap = int((0.35 if urgent else 0.22) * home.population)
        if home.soldiers >= cap:
            return
        # Judge the wall by the biggest host the march could send at it, not by
        # the quiet of this particular morning. Walls and towers are worth
        # roughly double, so parity is not the target -- half of it is.
        # Arm to the temper of the march, not to its worst imaginable day: a
        # garrison raised in a quiet year is a year of fields not worked.
        worst = max((host_strength(g.likely_host(k))
                     * (0.15 + 0.85 * (t.hostility / C.HOSTILITY_WAR) ** 1.5)
                     for k, t in g.world.towns.items() if not t.mine), default=0.0)
        threat = max(0.55 * worst,
                     0.9 * sum(host_strength(a.units) for a in coming))
        if host_strength(home.units) >= threat:
            return
        # A wall of archers loses the moment the gate goes: fill a mix, and
        # take whichever part of it is furthest behind.
        want = {"spearman": 0.35, "man_at_arms": 0.20, "archer": 0.30,
                "crossbowman": 0.15}
        have = max(1.0, float(home.soldiers))
        order = sorted(want, key=lambda k: home.units.get(k, 0.0) / have - want[k])
        for batch in (8 if urgent else 4, 3, 1):
            for key in order + ["militia"]:
                if "muster at" in g.recruit(self.home, key, batch):
                    return

    # ---------------------------------------------------------------- the road
    def _trim(self, stops):
        """Never carry food out of a town down to its last fortnight."""
        home = self.game.world.settlements[self.home]
        food = nourishment({k: home.market.stock[k] for k in RATION_GOODS})
        if food / max(0.2 * home.population, 1e-6) > 12:
            return stops
        for st in stops:
            if st.node in self.game.world.settlements:
                st.buy = [o for o in st.buy if o.good not in RATION_GOODS]
        return stops

    def _errand_cart(self) -> Optional[int]:
        return self.errand[0] if self.errand else None

    def _carts(self) -> None:
        g = self.game
        if len(g.caravans) < g.caravan_limit and g.treasury > C.CARAVAN_COST * 4:
            cart, _why = g.new_caravan(self.home)
            if cart:
                cart.guards = 3
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
            if c.uid == getattr(self, "arms_cart", None) and c.running:
                continue
            if c.uid == self._errand_cart():
                # An errand is one journey, not a standing route: once the pile
                # is home the cart goes back on the books.
                uid, key, target = self.errand
                home = g.world.settlements[self.home]
                if home.market.stock.get(key, 0.0) >= target or not c.running:
                    self.errand = None
                    c.halt()
                else:
                    continue
            if c.running and c.route:
                continue
            idle.append(c)
        if idle:
            # Shop once for the whole fleet and hand each cart a different
            # trade: three carts on one route is three carts crushing one price.
            # Trading capital is not capital spending: a cart spends and
            # recovers within the trip, so it draws on the whole treasury.
            opts = scan(g.world, self.home, capacity=idle[0].capacity,
                        speed=idle[0].speed, budget=max(0.0, g.treasury * 0.5),
                        top=3 + len(idle))
            taken = {tuple(sorted(s.node for s in c.route)) for c in g.caravans
                     if c.running and c.route}
            for c in idle:
                for opp in opts:
                    sig = tuple(sorted((opp.frm, opp.to)))
                    if sig in taken or opp.per_day <= 0:
                        continue
                    c.set_route(self._trim(route_from(opp, carrying=c.cargo)))
                    c.start()
                    taken.add(sig)
                    break
        # Re-shop every three weeks; an edge does not keep.
        if g.day % 21 == 0:
            for c in g.caravans:
                if c.uid not in (self.supply_cart, self._errand_cart()) \
                        and c.load < 0.15 * c.capacity:
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


class Conqueror(Bot):
    """The other way to play: build enough of an economy to arm a host, then
    take the march one town at a time.

    Kept alongside the trading bot because a victory condition nobody can reach
    is decoration. If this one stops taking towns, the conquest path is broken.
    """

    WAR_PLAN = [
        "farm", "mill", "bakery", "quarry", "orchard", "granary", "woodcutter",
        "farm", "mill", "bakery", "poleturner", "sawmill", "trading_post",
        "farm", "mill", "bakery", "cottage", "guildhall", "poleturner",
        "charcoal_burner", "iron_mine", "smelter", "cottage", "market",
        "fletcher", "stone_wall", "armoury", "armourer", "clay_pit", "kiln",
        "townhouse", "siege_yard", "blacksmith", "fletcher", "armourer",
        "townhouse", "wall_tower", "stable", "inn", "townhouse", "armoury",
    ]

    arms_cart: Optional[int] = None

    def plan_for(self, key: str) -> List[str]:
        if key not in self.plans:
            self.plans[key] = list(self.WAR_PLAN if key == self.home else COLONY_PLAN)
        return self.plans[key]

    #: An army is bought with an economy. Campaigning before there is one to
    #: spend is how a war bot ends the game with two towns and no treasury.
    WAR_CHEST = 9000.0
    WAR_SOULS = 240.0

    _at_war = False

    @property
    def warlike(self) -> bool:
        """Once a house turns to war it does not quietly turn back: an army
        half-raised and then abandoned is the worst of both plans."""
        if not self._at_war:
            g = self.game
            self._at_war = (g.population >= self.WAR_SOULS
                            and g.treasury >= self.WAR_CHEST)
        return self._at_war

    def step(self) -> None:
        if not self.warlike:
            super().step()
            return
        # On a war footing the ladder changes: no more ages, no more research,
        # every spare coin into the muster and the arms trade.
        g = self.game
        self._build()
        self._settle()
        for s in g.world.settlements.values():
            self._govern(s)
            self._shutter(s)
        self._defend()
        self._buy_arms()
        self._carts()
        self._campaign()

    def _buy_arms(self) -> None:
        """One cart kept permanently on the arms trade.

        Aldworth has two hills. You cannot mine, smelt, forge and plate an army
        out of that, so a war economy buys half its kit from the towns it means
        to march on -- which is the joke at the centre of this game.
        """
        g = self.game
        if self.arms_cart is not None:
            cart = g.caravan(self.arms_cart)
            if cart is None:
                self.arms_cart = None
            elif cart.running:
                return
        home = g.world.settlements[self.home]
        # Iron first: it is the neck of the whole war economy -- rams, plate
        # and swords all come out of it, and two hills will not supply them.
        wants = [k for k, floor in (("iron", 90), ("armour", 40), ("weapons", 40),
                                    ("bows", 40))
                 if home.market.stock.get(k, 0.0) < floor]
        if not wants:
            return
        key = wants[0]
        sellers = [(n, m.ask(key)) for n in g.world.towns
                   for m in [g.world.market_of(n)] if m and m.sells(key)]
        if not sellers:
            return
        where, price = min(sellers, key=lambda s: s[1])
        cart = (g.caravan(self.arms_cart) if self.arms_cart is not None
                else next((c for c in g.caravans if not c.running), None))
        if cart is None or g.treasury < 2500:
            return
        cart.set_route([
            Stop(node=where, buy=[Order(key, 90 if key == "iron" else 60,
                                        price * 1.6)]),
            Stop(node=self.home, sell=[Order(key, -1)]),
        ])
        cart.start()
        self.arms_cart = cart.uid

    def _campaign(self) -> None:
        g = self.game
        home = g.world.settlements[self.home]
        host = next((a for a in g.armies if a.owner == "player"), None)
        if host is not None:
            if host.state != "garrison":
                return
            # A host that has just taken a town stays put a while: an oath is
            # held by whoever is standing in the square.
            target = self._next_target(host.units, frm=host.at)
            if target:
                g.march(host.uid, target)
            elif host.at in g.world.settlements:
                g.disband_host(host.uid)
            elif g.world.towns.get(host.at) and g.world.towns[host.at].mine:
                if host_strength(host.units) < 200:
                    g.march(host.uid, host.home)   # go home and be made whole
            return
        # Muster at home until the garrison can crack somebody, then set out.
        pooled_all: Dict[str, float] = {}
        for s in g.world.settlements.values():
            for k, n in s.units.items():
                pooled_all[k] = pooled_all.get(k, 0.0) + n
        target = self._next_target(pooled_all)
        if target is None:
            return
        # Bring the colonies' men in to the capital first.
        for key, s in g.world.settlements.items():
            if key == self.home or not s.units:
                continue
            a, _why = g.raise_host(key, {k: int(v) for k, v in s.units.items()
                                         if int(v) > 0})
            if a:
                g.march(a.uid, self.home)
                return
        # Draw the host from every garrison, not just the capital's.
        pooled: Dict[str, float] = {}
        for s in g.world.settlements.values():
            for k, n in s.units.items():
                pooled[k] = pooled.get(k, 0.0) + n
        marching = {k: int(v) for k, v in home.units.items() if int(v) > 0}
        keep_back = {"archer": min(marching.get("archer", 0), 8),
                     "spearman": min(marching.get("spearman", 0), 8)}
        for k, n in keep_back.items():
            marching[k] = marching.get(k, 0) - n
        marching = {k: n for k, n in marching.items() if n > 0}
        if not marching:
            return
        a, _why = g.raise_host(self.home, marching)
        if a:
            g.march(a.uid, target)

    def _next_target(self, units: Dict[str, float],
                     frm: Optional[str] = None) -> Optional[str]:
        """The weakest town this host could actually take, if any."""
        g = self.game
        frm = frm or self.home
        strength = host_strength(units)
        siege = sum(UNITS[k].siege_power * n for k, n in units.items())
        if siege <= 0:
            return None
        best, best_cost = None, 0.0
        for key, t in g.world.towns.items():
            if t.mine or key == frm:
                continue
            defence = host_strength(t.garrison) + t.wall_hp / 14.0
            if strength < defence * 2.0:
                continue
            score = 1.0 / (1.0 + g.world.distance(frm, key) / 60.0)
            if score > best_cost:
                best, best_cost = key, score
        return best

    def _defend(self) -> None:
        """A conqueror musters to a target, not to a threat -- and musters in
        every town that has a barracks, not only the capital."""
        if not self.warlike:
            return super()._defend()
        g = self.game
        if g.treasury < self.reserve:
            return
        # No engines, no conquest: a siege train comes before another spearman,
        # because without one every wall in the march is simply a wall.
        home = g.world.settlements[self.home]
        rams = sum(s.units.get("ram", 0.0) for s in g.world.settlements.values())
        rams += sum(a.units.get("ram", 0.0) for a in g.armies if a.owner == "player")
        if rams < 4 and home.effect("muster"):
            for unit_key in ("ram", "engineer"):
                if "muster at" in g.recruit(self.home, unit_key, 2):
                    return
        want = {"spearman": 0.28, "man_at_arms": 0.22, "archer": 0.20,
                "engineer": 0.12, "ram": 0.10, "crossbowman": 0.08}
        for key, s in g.world.settlements.items():
            if not s.effect("muster") or s.soldiers >= int(0.34 * s.population):
                continue
            have = max(1.0, float(s.soldiers))
            order = sorted(want, key=lambda k: s.units.get(k, 0.0) / have - want[k])
            for batch in (4, 2, 1):
                for unit_key in order + ["militia"]:
                    if "muster at" in g.recruit(key, unit_key, batch):
                        return


def report(game: GameState) -> str:
    p = game.progress
    lines = [f"day {game.day} ({game.date_str()})  --  {p.age_name()}",
             f"  treasury  {game.treasury:>12,.0f}c",
             f"  net worth {game.net_worth():>12,.0f}c",
             f"  souls     {game.population:>12,.0f}   caravans {len(game.caravans)}"
             f"   trade {sum(c.total_profit for c in game.caravans):>10,.0f}c",
             f"  soldiers  {game.soldiers:>12}   sworn towns "
             f"{len(game.world.vassals())}   known {len(p.researched) - 1}"]
    for s in game.world.settlements.values():
        stock = sorted(((v, k) for k, v in s.market.stock.items() if v > 1), reverse=True)
        lines.append(f"  {s.name:<10} pop {s.population:>5,.0f} mood {s.popularity:>3.0f}"
                     f" roofs {s.housing(p):>5,.0f} wall {s.wall_hp:>5,.0f}"
                     f" works {len(s.buildings):>3}"
                     f"  | " + ", ".join(f"{k} {v:.0f}" for v, k in stock[:5]))
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
