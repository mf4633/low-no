"""Shocks, rival companies, and raids -- the reasons prices are not a table.

Two different pressures live here. Shocks move a town's appetite (a siege eats
weapons, a blight eats grain) and create the spread. Rival companies close it
again, a little every day, so an edge you found last month is worth less this
month. Between them, the map is never solved.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from . import config as C
from .goods import ALL_KEYS, good
from .world import Shock, World


@dataclass
class RivalCompany:
    """An AI trading house. It does not carry goods; it closes spreads."""
    name: str
    reach: float = 1.0        # how much volume it can shift per deal
    nerve: float = 0.12       # margin it needs before it moves

    def act(self, world: World, rng: random.Random) -> Optional[str]:
        keys = [k for k in ALL_KEYS if rng.random() < 0.45]
        best = None
        for k in keys:
            towns = [t for t in world.towns.values() if t.market.sells(k)]
            if len(towns) < 2:
                continue
            cheap = min(towns, key=lambda t: t.market.ask(k))
            dear = max(towns, key=lambda t: t.market.bid(k))
            if cheap is dear:
                continue
            margin = dear.market.bid(k) - cheap.market.ask(k)
            rel = margin / max(cheap.market.ask(k), 1e-6)
            if rel < self.nerve:
                continue
            score = margin / max(good(k).weight, 1e-6)
            if best is None or score > best[0]:
                best = (score, k, cheap, dear, rel)
        if best is None:
            return None
        _score, k, cheap, dear, rel = best
        volume = 6.0 * self.reach * (0.5 + rng.random()) * min(3.0, 1.0 + rel)
        fill = cheap.market.buy_from(k, volume)
        if fill.quantity <= 0:
            return None
        dear.market.sell_to(k, fill.quantity)
        if rel > 0.45:
            return (f"{self.name} is running {good(k).name} from {cheap.name} "
                    f"to {dear.name}")
        return None


SHOCK_TABLE = [
    # (label, good, flow_delta, target_mult, min_days, max_days, weight)
    ("is arming for war",        "weapons", -6.0, 0.45, 60, 140, 3),
    ("is arming for war",        "iron",    -5.0, 0.60, 60, 140, 2),
    ("has soldiers to feed",     "bread",   -8.0, 0.55, 40, 90, 3),
    ("suffers a blight",         "wheat",  -10.0, 0.70, 30, 70, 3),
    ("has a bumper harvest",     "wheat",  +14.0, 1.40, 30, 60, 3),
    ("is struck by cattle fever","cheese",  -6.0, 0.55, 30, 70, 2),
    ("follows a new fashion",    "silk",    -3.0, 0.40, 40, 110, 2),
    ("follows a new fashion",    "cloth",   -6.0, 0.50, 40, 110, 2),
    ("is rebuilding after fire", "planks",  -8.0, 0.50, 30, 80, 3),
    ("is rebuilding after fire", "stone",   -9.0, 0.55, 30, 80, 2),
    ("opened a new mine",        "iron_ore",+12.0, 1.35, 50, 120, 2),
    ("lost its salt fleet",      "salt",    -5.0, 0.45, 40, 100, 2),
    ("sits on a glut of ale",    "ale",    +10.0, 1.40, 25, 60, 2),
    ("is short of tools",        "tools",   -4.0, 0.45, 40, 100, 3),
    ("has spice ships in",       "spice",  +10.0, 1.50, 20, 50, 2),
]


@dataclass
class EventEngine:
    rivals: List[RivalCompany] = field(default_factory=list)
    shock_chance: float = 0.10      # per day, somewhere in the world
    log: List[str] = field(default_factory=list)

    def tick(self, world: World, day: int, rng: random.Random) -> List[str]:
        msgs: List[str] = []
        if world.towns and rng.random() < self.shock_chance:
            msgs.append(self._roll_shock(world, rng))
        for r in self.rivals:
            m = r.act(world, rng)
            if m:
                msgs.append(m)
        msgs += self._raids(world, day, rng)
        msgs = [m for m in msgs if m]
        self.log += msgs
        if len(self.log) > 200:
            del self.log[:-200]
        return msgs

    def _roll_shock(self, world: World, rng: random.Random) -> str:
        town = rng.choice(list(world.towns.values()))
        pool: List[tuple] = []
        for row in SHOCK_TABLE:
            pool += [row] * row[6]
        label, key, delta, mult, dmin, dmax, _w = rng.choice(pool)
        if any(s.good == key for s in town.shocks):
            return ""
        days = rng.randint(dmin, dmax)
        town.shocks.append(Shock(label=label, town=town.key, good=key,
                                 flow_delta=delta, target_mult=mult, days_left=days))
        direction = "wants" if delta < 0 else "is long of"
        return (f"News: {town.name} {label} -- it {direction} "
                f"{good(key).name} for the next {days} days")

    def _raids(self, world: World, day: int, rng: random.Random) -> List[str]:
        out: List[str] = []
        pressure = 1.0 + day / float(C.DAYS_PER_YEAR)
        for s in world.settlements.values():
            if rng.random() > C.RAID_BASE_CHANCE * pressure:
                continue
            strength = 12.0 + 9.0 * pressure * rng.random()
            if s.defense >= strength:
                out.append(f"Raiders probed {s.name} and were turned away at the wall")
                continue
            loot = C.RAID_LOOT_FRACTION * (1.0 - s.defense / max(strength, 1.0))
            value = 0.0
            for k in ALL_KEYS:
                taken = s.market.stock[k] * loot
                s.market.stock[k] -= taken
                value += taken * s.market.bid(k)
            s.popularity = max(0.0, s.popularity - 8.0)
            out.append(f"RAID on {s.name}: {value:.0f}c of stores carried off "
                       f"(defence {s.defense:.0f} vs {strength:.0f})")
        return out

    def to_dict(self) -> dict:
        return {"rivals": [r.__dict__.copy() for r in self.rivals],
                "shock_chance": self.shock_chance, "log": self.log[-40:]}

    @classmethod
    def from_dict(cls, d: dict) -> "EventEngine":
        return cls(rivals=[RivalCompany(**r) for r in d["rivals"]],
                   shock_chance=d["shock_chance"], log=list(d.get("log", [])))
