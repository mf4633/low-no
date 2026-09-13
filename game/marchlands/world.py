"""The map: your settlements, the foreign towns, and the roads between them.

A foreign town is not simulated building-by-building. It is a market with a
net flow -- what its own hinterland makes and eats each day -- plus a pull back
toward equilibrium standing in for its trade with everyone who is not you.
A town with a surplus sits above its target, so its price is low and it is a
place to buy. Sell into it hard enough and you push it the other way.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from . import config as C
from .goods import ALL_KEYS, good
from .market import Market
from .settlement import Settlement


@dataclass
class Shock:
    label: str
    town: str
    good: str
    flow_delta: float          # added to daily net flow while it lasts
    target_mult: float         # multiplies the appetite while it lasts
    days_left: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ForeignTown:
    key: str
    name: str
    x: float
    y: float
    market: Market
    flow: Dict[str, float] = field(default_factory=dict)   # units/day, signed
    base_target: Dict[str, float] = field(default_factory=dict)
    lawlessness: float = 0.01     # banditry on roads leading here
    wealth: float = 1.0           # scales its appetite
    blurb: str = ""
    shocks: List[Shock] = field(default_factory=list)
    # --- the lord and his stones -------------------------------------------
    lord: str = ""                # who holds it
    owner: str = ""               # '' free, 'player', or another town's key
    hostility: float = 0.0        # 0-100 toward you; at 100 a host marches
    ambition: float = 0.0         # 0-100 toward its neighbours
    aggression: float = 1.0       # how fast that ambition builds
    truce_days: int = 0           # days of bought peace left
    favour: float = 0.0           # goodwill your gifts have bought
    garrison: Dict[str, float] = field(default_factory=dict)
    wall_hp: float = 0.0
    wall_max: float = 0.0
    wall_base: float = 0.0
    muster: float = 1.0           # how big a host this town can put in the field
    temper: float = 1.0           # how quickly this lord takes offence
    prosperity: float = 1.0       # grows in peace, falls when stormed

    @property
    def mine(self) -> bool:
        return self.owner == "player"

    @property
    def free(self) -> bool:
        return self.owner == ""

    def tribute(self) -> float:
        return (C.TRIBUTE_BASE + C.TRIBUTE_PER_WEALTH * self.wealth) * self.prosperity

    def rebuild_walls(self, share: float = 0.02) -> None:
        self.wall_hp = min(self.wall_max, self.wall_hp + self.wall_max * share)

    def target_garrison(self) -> Dict[str, float]:
        scale = self.muster * self.prosperity
        return {"spearman": 11 * scale, "archer": 8 * scale, "man_at_arms": 4 * scale}

    def grow(self, rng: random.Random, besieged: bool = False) -> None:
        """A year of quiet makes a town richer, higher-walled and better held.

        This is the difference between a map that is scenery and a map that is
        playing against you: leave Ostmark alone for three years and Ostmark
        will not be the same problem it was.
        """
        if besieged:
            self.prosperity = max(0.4, self.prosperity - 0.004)
            return
        self.prosperity = min(2.2, self.prosperity + 0.00055)
        self.wall_max = self.wall_base * (1.0 + 0.55 * (self.prosperity - 1.0))
        self.rebuild_walls(0.006)
        want = self.target_garrison()
        for k, n in want.items():
            have = self.garrison.get(k, 0.0)
            if have < n:
                self.garrison[k] = min(n, have + 0.09 * self.muster)
        for k in list(self.garrison):
            if self.garrison[k] < 0.5:
                del self.garrison[k]

    def specialties(self) -> List[str]:
        return [k for k, v in sorted(self.flow.items(), key=lambda kv: -kv[1]) if v > 0]

    def wants(self) -> List[str]:
        return [k for k, v in sorted(self.flow.items(), key=lambda kv: kv[1]) if v < 0]

    def tick(self, rng: random.Random) -> None:
        # Restore targets, then re-apply live shocks.
        for k in ALL_KEYS:
            self.market.target[k] = self.base_target.get(k, 0.0)
        flow = dict(self.flow)
        for s in list(self.shocks):
            s.days_left -= 1
            if s.days_left <= 0:
                self.shocks.remove(s)
                continue
            flow[s.good] = flow.get(s.good, 0.0) + s.flow_delta
            self.market.target[s.good] = self.market.target.get(s.good, 0.0) * s.target_mult
        for k in ALL_KEYS:
            net = flow.get(k, 0.0)
            tgt = self.market.target.get(k, 0.0)
            stock = self.market.stock.get(k, 0.0)
            # Own production/consumption, then the rest of the world leaning back.
            stock += net
            stock += C.STOCK_REVERSION * (tgt - stock)
            stock -= stock * good(k).spoilage * 0.5
            self.market.stock[k] = max(0.0, stock)
        self.market.settle_day()

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "x": self.x, "y": self.y,
                "market": self.market.to_dict(), "flow": dict(self.flow),
                "base_target": dict(self.base_target),
                "lawlessness": self.lawlessness, "wealth": self.wealth,
                "blurb": self.blurb, "shocks": [s.to_dict() for s in self.shocks],
                "lord": self.lord, "owner": self.owner, "hostility": self.hostility,
                "ambition": self.ambition, "aggression": self.aggression,
                "truce_days": self.truce_days, "favour": self.favour,
                "garrison": dict(self.garrison), "wall_hp": self.wall_hp,
                "wall_max": self.wall_max, "wall_base": self.wall_base,
                "muster": self.muster, "temper": self.temper,
                "prosperity": self.prosperity}

    @classmethod
    def from_dict(cls, d: dict) -> "ForeignTown":
        t = cls(key=d["key"], name=d["name"], x=d["x"], y=d["y"],
                market=Market.from_dict(d["market"]), flow=dict(d["flow"]),
                base_target=dict(d["base_target"]), lawlessness=d["lawlessness"],
                wealth=d["wealth"], blurb=d.get("blurb", ""))
        t.shocks = [Shock(**s) for s in d.get("shocks", [])]
        t.lord = d.get("lord", "")
        t.owner = d.get("owner", "")
        t.hostility = d.get("hostility", 0.0)
        t.garrison = dict(d.get("garrison", {}))
        t.wall_hp = d.get("wall_hp", 0.0)
        t.wall_max = d.get("wall_max", 0.0)
        for name in ("ambition", "aggression", "truce_days", "favour", "muster",
                     "temper", "prosperity", "wall_base"):
            if name in d:
                setattr(t, name, d[name])
        return t


@dataclass
class Site:
    """Unclaimed land you may settle, at a price."""
    key: str
    name: str
    x: float
    y: float
    terrain: Dict[str, int]
    coin_cost: float
    blurb: str = ""
    deposits: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["terrain"] = dict(self.terrain)
        d["deposits"] = dict(self.deposits)
        return d


@dataclass
class World:
    settlements: Dict[str, Settlement] = field(default_factory=dict)
    towns: Dict[str, ForeignTown] = field(default_factory=dict)
    coords: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    sites: Dict[str, "Site"] = field(default_factory=dict)

    # ------------------------------------------------------------- geography
    def place(self, key: str, x: float, y: float) -> None:
        self.coords[key] = (x, y)

    def distance(self, a: str, b: str) -> float:
        (ax, ay), (bx, by) = self.coords[a], self.coords[b]
        return math.hypot(ax - bx, ay - by)

    def danger(self, a: str, b: str) -> float:
        """Chance per travelling day that a caravan meets trouble."""
        law = 0.0
        for node in (a, b):
            t = self.towns.get(node)
            law += t.lawlessness if t else 0.004
        return max(0.0, law / 2.0 * (0.6 + self.distance(a, b) / 220.0))

    # ---------------------------------------------------------------- lookup
    def market_of(self, key: str) -> Optional[Market]:
        if key in self.settlements:
            return self.settlements[key].market
        if key in self.towns:
            return self.towns[key].market
        return None

    def node_name(self, key: str) -> str:
        if key in self.settlements:
            return self.settlements[key].name
        if key in self.towns:
            return self.towns[key].name
        return key

    def is_mine(self, key: str) -> bool:
        """Your own settlement -- somewhere goods move without coin changing hands."""
        return key in self.settlements

    def is_friendly(self, key: str) -> bool:
        """Yours or sworn to you: no tolls, no danger of being turned away."""
        return key in self.settlements or (key in self.towns and self.towns[key].mine)

    def vassals(self, liege: str = "player") -> List[str]:
        return [k for k, t in self.towns.items() if t.owner == liege]

    def liege_of(self, key: str) -> str:
        return self.towns[key].owner if key in self.towns else "player"

    def nearest(self, key: str, among: Iterable[str]) -> Optional[str]:
        pool = [k for k in among if k != key]
        return min(pool, key=lambda k: self.distance(key, k)) if pool else None

    def all_nodes(self) -> List[str]:
        return list(self.settlements.keys()) + list(self.towns.keys())

    def resolve(self, prefix: str) -> str:
        p = prefix.strip().lower().replace(" ", "_")
        nodes = self.all_nodes()
        if p in nodes:
            return p
        hits = [n for n in nodes if n.startswith(p)]
        if not hits:
            hits = [n for n in nodes if self.node_name(n).lower().startswith(p)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise KeyError(f"no place matches {prefix!r}")
        raise KeyError(f"{prefix!r} is ambiguous: {', '.join(hits)}")

    def tariff_for(self, node: str, home: Optional[Settlement]) -> float:
        """Toll charged at `node`, after any relief your trading posts bought."""
        if node in self.settlements:
            return 0.0
        if self.towns[node].mine:
            return 0.0                     # a vassal does not toll its lord
        base = self.towns[node].market.tariff_rate
        relief = max((s.tariff_relief for s in self.settlements.values()), default=0.0)
        return base * (1.0 - relief)

    # --------------------------------------------------------- arbitrage aid
    def spreads(self, key: str, limit: int = 6) -> List[Tuple[str, str, float, float]]:
        """Best (buy-here, sell-there, margin per unit, margin per cart unit)."""
        rows: List[Tuple[str, str, float, float]] = []
        nodes = self.all_nodes()
        for a in nodes:
            ma = self.market_of(a)
            for b in nodes:
                if a == b:
                    continue
                mb = self.market_of(b)
                if not (ma and mb and ma.sells(key) and mb.sells(key)):
                    continue
                margin = mb.bid(key) - ma.ask(key)
                if margin <= 0:
                    continue
                rows.append((a, b, margin, margin / max(good(key).weight, 1e-6)))
        rows.sort(key=lambda r: -r[3])
        return rows[:limit]

    def to_dict(self) -> dict:
        return {"settlements": {k: s.to_dict() for k, s in self.settlements.items()},
                "towns": {k: t.to_dict() for k, t in self.towns.items()},
                "coords": {k: list(v) for k, v in self.coords.items()},
                "sites": {k: v.to_dict() for k, v in self.sites.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        w = cls()
        w.settlements = {k: Settlement.from_dict(v) for k, v in d["settlements"].items()}
        w.towns = {k: ForeignTown.from_dict(v) for k, v in d["towns"].items()}
        w.coords = {k: tuple(v) for k, v in d["coords"].items()}
        w.sites = {k: Site(**v) for k, v in d.get("sites", {}).items()}
        return w


def make_town(key: str, name: str, x: float, y: float, *, produces: Dict[str, float],
              consumes: Dict[str, float], appetite: float = 1.0,
              lawlessness: float = 0.01, tariff: float = C.BASE_TARIFF,
              wealth: float = 1.0, blurb: str = "",
              trades: Optional[Iterable[str]] = None,
              lord: str = "", walls: float = 500.0, muster: float = 1.0,
              garrison: Optional[Dict[str, float]] = None) -> ForeignTown:
    """Build a foreign town from a surplus/deficit sketch.

    Targets are set so that the town's own flow leaves it visibly long of what
    it makes and short of what it eats -- which is the whole reason to sail
    there.
    """
    flow: Dict[str, float] = {}
    target: Dict[str, float] = {}
    tradeable = tuple(trades) if trades is not None else ALL_KEYS
    for k in ALL_KEYS:
        p = produces.get(k, 0.0)
        c = consumes.get(k, 0.0)
        flow[k] = p - c
        base = 40.0 * appetite * wealth
        scale = base + 12.0 * (p + c)
        target[k] = scale if (p or c) else base * 0.5
    m = Market(name=name, stock={}, target=dict(target), tariff_rate=tariff,
               tradeable=tradeable)
    for k in ALL_KEYS:
        # Start each town at its steady state: stock where flow and the pull
        # back toward target cancel.
        m.stock[k] = max(1.0, target[k] + flow[k] / C.STOCK_REVERSION)
        m.posted[k] = m.curve(k, m.stock[k])
    return ForeignTown(key=key, name=name, x=x, y=y, market=m, flow=flow,
                       base_target=dict(target), lawlessness=lawlessness,
                       wealth=wealth, blurb=blurb, lord=lord,
                       garrison=dict(garrison or {
                           "spearman": round(11 * muster), "archer": round(8 * muster),
                           "man_at_arms": round(4 * muster)}),
                       wall_hp=walls, wall_max=walls, wall_base=walls, muster=muster)
