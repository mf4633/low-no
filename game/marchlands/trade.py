"""Caravans: the only way value moves between markets.

A caravan runs a standing route -- a ring of stops, each with sell and buy
orders -- and repeats it until told otherwise. Distance costs days, days cost
wages, and every league of road carries a chance of losing the load. Those
three frictions are what keep prices apart; without them every market in the
world would be the same market.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .goods import cargo_weight, good
from .market import Market

IDLE = "idle"
MOVING = "moving"
TRADING = "trading"


@dataclass
class Order:
    good: str
    quantity: float          # -1 means "everything you can"
    limit_price: float = 0.0 # max to pay when buying, min to accept when selling

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Stop:
    node: str
    sell: List[Order] = field(default_factory=list)
    buy: List[Order] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"node": self.node, "sell": [o.to_dict() for o in self.sell],
                "buy": [o.to_dict() for o in self.buy]}

    @classmethod
    def from_dict(cls, d: dict) -> "Stop":
        return cls(node=d["node"], sell=[Order(**o) for o in d["sell"]],
                   buy=[Order(**o) for o in d["buy"]])

    def describe(self) -> str:
        bits = []
        for o in self.sell:
            q = "all" if o.quantity < 0 else f"{o.quantity:g}"
            bits.append(f"sell {q} {o.good}" + (f" @>={o.limit_price:g}" if o.limit_price else ""))
        for o in self.buy:
            q = "max" if o.quantity < 0 else f"{o.quantity:g}"
            bits.append(f"buy {q} {o.good}" + (f" @<={o.limit_price:g}" if o.limit_price else ""))
        return f"{self.node}: " + ("; ".join(bits) if bits else "call only")


@dataclass
class Caravan:
    uid: int
    name: str
    home: str
    guards: int = 1
    cargo: Dict[str, float] = field(default_factory=dict)
    route: List[Stop] = field(default_factory=list)
    leg: int = 0
    state: str = IDLE
    at: str = ""              # node it is standing in, '' while moving
    bound_for: str = ""
    days_left: float = 0.0
    running: bool = False
    capacity: float = C.CARAVAN_BASE_CAPACITY
    speed: float = C.CARAVAN_BASE_SPEED
    trip_profit: float = 0.0
    total_profit: float = 0.0
    spent: float = 0.0        # coins laid out on the current load
    dry_stops: int = 0        # consecutive calls where no business was done
    log: List[str] = field(default_factory=list)

    # ---------------------------------------------------------------- basics
    @property
    def load(self) -> float:
        return cargo_weight(self.cargo)

    @property
    def free_space(self) -> float:
        return max(0.0, self.capacity - self.load)

    @property
    def daily_cost(self) -> float:
        return C.CARAVAN_UPKEEP + C.GUARD_COST * self.guards

    def note(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 40:
            del self.log[:-40]

    def manifest(self) -> str:
        if not self.cargo:
            return "empty"
        return ", ".join(f"{q:.0f} {good(k).name}" for k, q in sorted(self.cargo.items())
                         if q > 0.05) or "empty"

    def where(self) -> str:
        if self.state == MOVING:
            return f"{self.days_left:.1f}d from {self.bound_for}"
        return self.at or self.home

    # ------------------------------------------------------------- route ops
    def set_route(self, stops: List[Stop]) -> None:
        self.route = stops
        # Start from where the cart is standing if the route passes through it,
        # rather than sending it out empty to the far end first.
        here = self.at or self.home
        self.leg = next((i for i, s in enumerate(stops) if s.node == here), 0)

    def start(self) -> None:
        self.running = bool(self.route)

    def halt(self) -> None:
        self.running = False


class TradeEngine:
    """Moves caravans and settles their deals against the world's markets."""

    def __init__(self, world, rng: random.Random) -> None:
        self.world = world
        self.rng = rng

    # ------------------------------------------------------------------ day
    def tick(self, caravans: List[Caravan], treasury: float) -> Tuple[float, List[str]]:
        """Advance every caravan a day. Returns (new treasury, messages)."""
        msgs: List[str] = []
        for c in caravans:
            treasury -= c.daily_cost
            self._refresh_stats(c)
            if c.state == MOVING:
                treasury, m = self._travel(c, treasury)
                msgs += m
            if c.state in (IDLE, TRADING) and c.running:
                treasury, m = self._at_stop(c, treasury)
                msgs += m
        return treasury, msgs

    def _refresh_stats(self, c: Caravan) -> None:
        home = self.world.settlements.get(c.home)
        if home:
            c.capacity = C.CARAVAN_BASE_CAPACITY + home.effect("caravan_capacity")
            c.speed = C.CARAVAN_BASE_SPEED + home.effect("caravan_speed")

    def _travel(self, c: Caravan, treasury: float) -> Tuple[float, List[str]]:
        msgs: List[str] = []
        c.days_left -= 1.0
        origin = c.at or c.home
        risk = self.world.danger(origin, c.bound_for)
        risk *= max(0.0, 1.0 - C.GUARD_PROTECTION * c.guards)
        if self.rng.random() < risk:
            lost_value = 0.0
            take = 0.25 + 0.35 * self.rng.random()
            for k in list(c.cargo):
                lost = c.cargo[k] * take
                c.cargo[k] -= lost
                mk = self.world.market_of(c.bound_for)
                lost_value += lost * (mk.bid(k) if mk else good(k).base_price)
            purse = 60.0 * self.rng.random() * c.guards
            treasury -= purse
            msg = (f"{c.name} was set upon on the road to "
                   f"{self.world.node_name(c.bound_for)}: "
                   f"{lost_value:.0f}c of goods gone")
            c.note(msg)
            msgs.append(msg)
        if c.days_left <= 0:
            c.at = c.bound_for
            c.bound_for = ""
            c.state = TRADING
        return treasury, msgs

    def _at_stop(self, c: Caravan, treasury: float) -> Tuple[float, List[str]]:
        """Do the day's business where the cart is standing, then set off."""
        msgs: List[str] = []
        if not c.route:
            c.running = False
            return treasury, msgs
        here = c.at or c.home
        c.at = here
        stop = c.route[c.leg % len(c.route)]
        if stop.node == here:
            treasury, m = self._do_business(c, stop, treasury)
            msgs += m
            c.leg = (c.leg + 1) % len(c.route)
        nxt = c.route[c.leg % len(c.route)]
        if nxt.node == here:
            c.state = IDLE          # standing orders: it works this stop again tomorrow
            return treasury, msgs
        dist = self.world.distance(here, nxt.node)
        c.bound_for = nxt.node
        c.days_left = max(1.0, dist / max(c.speed, 1.0))
        c.state = MOVING
        return treasury, msgs

    def _do_business(self, c: Caravan, stop: Stop, treasury: float) -> Tuple[float, List[str]]:
        msgs: List[str] = []
        market: Optional[Market] = self.world.market_of(stop.node)
        if market is None:
            return treasury, msgs
        moved_qty = 0.0
        mine = self.world.is_mine(stop.node)
        tariff = self.world.tariff_for(stop.node, None)
        market.tariff_rate = 0.0 if mine else tariff
        gross = 0.0

        for o in stop.sell:
            have = c.cargo.get(o.good, 0.0)
            qty = have if o.quantity < 0 else min(have, o.quantity)
            if qty <= 1e-6:
                continue
            if mine:
                # Unloading into your own stores: no coin changes hands.
                moved_qty += qty
                market.transfer_in(o.good, qty)
                c.cargo[o.good] = have - qty
                c.note(f"unloaded {qty:.0f} {good(o.good).name} at {market.name}")
                continue
            fill = market.sell_to(o.good, qty, min_price=o.limit_price or None)
            if fill.quantity <= 1e-6:
                continue
            moved_qty += fill.quantity
            c.cargo[o.good] = have - fill.quantity
            proceeds = fill.value - fill.tariff
            treasury += proceeds
            gross += proceeds
            c.note(f"sold {fill.quantity:.0f} {good(o.good).name} at {market.name} "
                   f"for {proceeds:.0f}c ({fill.avg_price:.2f}/u)")

        for o in stop.buy:
            space = c.free_space / max(good(o.good).weight, 1e-6)
            qty = space if o.quantity < 0 else min(o.quantity, space)
            if qty <= 1e-6:
                continue
            if mine:
                # The limit price is your standing order not to strip your own
                # stores: once the good is dear at home, the cart leaves without it.
                moved = market.transfer_out(o.good, qty, o.limit_price or None)
                moved_qty += moved
                if moved > 1e-6:
                    c.cargo[o.good] = c.cargo.get(o.good, 0.0) + moved
                    c.note(f"loaded {moved:.0f} {good(o.good).name} at {market.name}")
                elif o.limit_price:
                    c.note(f"{good(o.good).name} too dear at {market.name} to carry off")
                continue
            fill = market.buy_from(o.good, qty, max_price=o.limit_price or None,
                                   budget=max(0.0, treasury))
            if fill.quantity <= 1e-6:
                continue
            moved_qty += fill.quantity
            c.cargo[o.good] = c.cargo.get(o.good, 0.0) + fill.quantity
            outlay = fill.value + fill.tariff
            treasury -= outlay
            gross -= outlay
            c.spent += outlay
            c.note(f"bought {fill.quantity:.0f} {good(o.good).name} at {market.name} "
                   f"for {outlay:.0f}c ({fill.avg_price:.2f}/u)")

        c.dry_stops = 0 if moved_qty > 1e-6 else c.dry_stops + 1
        if c.dry_stops >= 2 * max(1, len(c.route)):
            c.running = False
            c.dry_stops = 0
            msgs.append(f"{c.name} has nothing left to trade on its route "
                        f"and is standing idle at {market.name}")
        c.trip_profit += gross
        c.total_profit += gross
        if abs(gross) > 1:
            msgs.append(f"{c.name} at {market.name}: {gross:+.0f}c")
        # Tidy dust so the manifest stays readable.
        for k in list(c.cargo):
            if c.cargo[k] <= 1e-4:
                del c.cargo[k]
        return treasury, msgs


def caravan_to_dict(c: Caravan) -> dict:
    d = {k: v for k, v in c.__dict__.items() if k not in ("route", "cargo", "log")}
    d["route"] = [s.to_dict() for s in c.route]
    d["cargo"] = dict(c.cargo)
    d["log"] = list(c.log[-10:])
    return d


def caravan_from_dict(d: dict) -> Caravan:
    route = [Stop.from_dict(s) for s in d.pop("route", [])]
    cargo = dict(d.pop("cargo", {}))
    log = list(d.pop("log", []))
    c = Caravan(**d)
    c.route, c.cargo, c.log = route, cargo, log
    return c
