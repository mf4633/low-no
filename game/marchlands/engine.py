"""The game: one state object, one tick, one ledger.

Everything the player sees is derived from `GameState`. The tick is
deliberately ordered -- produce before you feed, feed before you take the mood,
pay before you count the day's coin -- because several of the feedback loops
(hunger -> mood -> productivity -> hunger) are only stable if the order is
fixed.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import config as C
from .buildings import building
from .events import EventEngine
from .goods import ALL_KEYS
from .market import Market
from .trade import Caravan, TradeEngine, caravan_from_dict, caravan_to_dict
from .world import World

SAVE_VERSION = 1


@dataclass
class Ledger:
    taxes: float = 0.0
    trade: float = 0.0
    wages: float = 0.0
    upkeep: float = 0.0
    caravans: float = 0.0
    building: float = 0.0

    @property
    def income(self) -> float:
        return self.taxes + max(0.0, self.trade)

    @property
    def outgo(self) -> float:
        return self.wages + self.upkeep + self.caravans + self.building - min(0.0, self.trade)

    @property
    def net(self) -> float:
        return self.taxes + self.trade - self.wages - self.upkeep - self.caravans - self.building

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class GameState:
    world: World
    treasury: float = 1500.0
    day: int = 0
    caravans: List[Caravan] = field(default_factory=list)
    events: EventEngine = field(default_factory=EventEngine)
    seed: int = 7
    next_caravan_uid: int = 1
    messages: List[str] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)
    history: List[dict] = field(default_factory=list)
    over: str = ""              # '' while playing, else the ending

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.trade_engine = TradeEngine(self.world, self.rng)

    # ------------------------------------------------------------- calendar
    @property
    def _calendar_day(self) -> int:
        return self.day + (C.START_MONTH - 1) * C.DAYS_PER_MONTH

    @property
    def year(self) -> int:
        return C.START_YEAR + self._calendar_day // C.DAYS_PER_YEAR

    @property
    def month(self) -> int:
        return (self._calendar_day % C.DAYS_PER_YEAR) // C.DAYS_PER_MONTH + 1

    @property
    def day_of_month(self) -> int:
        return self._calendar_day % C.DAYS_PER_MONTH + 1

    @property
    def season(self) -> str:
        return C.SEASON_OF_MONTH[self.month]

    def date_str(self) -> str:
        return (f"day {self.day_of_month:>2} of month {self.month:>2}, "
                f"{self.year} ({self.season})")

    # ------------------------------------------------------------- economics
    def net_worth(self) -> float:
        worth = self.treasury
        for s in self.world.settlements.values():
            worth += s.net_worth()
        for c in self.caravans:
            m = self.world.market_of(c.at) or next(iter(self.world.settlements.values())).market
            worth += sum(q * m.bid(k) for k, q in c.cargo.items())
            worth += C.CARAVAN_COST * 0.5
        return worth

    @property
    def population(self) -> float:
        return sum(s.population for s in self.world.settlements.values())

    @property
    def caravan_limit(self) -> int:
        return 2 + sum(s.caravan_slots for s in self.world.settlements.values())

    # ------------------------------------------------------------------ tick
    def tick(self) -> List[str]:
        if self.over:
            return [self.over]
        self.day += 1
        msgs: List[str] = []
        led = Ledger()

        msgs += self.events.tick(self.world, self.day, self.rng)

        # 1. Settlements work, eat and are taxed.
        for s in self.world.settlements.values():
            before = {b.uid: b.complete for b in s.buildings}
            rep = s.tick(self.season, self.rng)
            for b in s.buildings:
                if b.complete and not before.get(b.uid, True):
                    msgs.append(f"{s.name}: {b.spec.name} finished")
            led.taxes += rep.taxes
            led.wages += rep.wages
            led.upkeep += rep.upkeep
            msgs += rep.notes

        # 2. Pay the wage bill; an unpaid day costs you the town's goodwill.
        payroll = led.wages + led.upkeep
        if self.treasury < payroll:
            for s in self.world.settlements.values():
                s.report.unpaid = True
            msgs.append("THE COFFERS ARE EMPTY -- wages went unpaid today")
        self.treasury += led.taxes - payroll

        # 3. Markets at home relax toward their fundamentals.
        for s in self.world.settlements.values():
            s.market.settle_day()

        # 4. The wider world produces, consumes and reprices.
        for t in self.world.towns.values():
            t.tick(self.rng)

        # 5. Caravans move and deal.
        before_trade = self.treasury
        caravan_cost = sum(c.daily_cost for c in self.caravans)
        self.treasury, tmsgs = self.trade_engine.tick(self.caravans, self.treasury)
        led.caravans = caravan_cost
        led.trade = (self.treasury - before_trade) + caravan_cost
        msgs += tmsgs

        # 6. Mood and migration settle last, on the day as it actually went.
        for s in self.world.settlements.values():
            s.update_mood()
            s.migrate(self.rng)
            if s.popularity < C.UNREST_THRESHOLD:
                msgs.append(f"{s.name} is in open unrest -- nobody is working")

        self.ledger = led
        self.history.append({
            "day": self.day, "treasury": self.treasury, "worth": self.net_worth(),
            "pop": self.population,
            "pop_mood": sum(s.popularity for s in self.world.settlements.values())
                        / max(1, len(self.world.settlements)),
            "net": led.net,
        })
        if len(self.history) > 2000:
            del self.history[:-2000]

        msgs += self._check_ending()
        self.messages = msgs
        return msgs

    def advance(self, days: int) -> List[str]:
        out: List[str] = []
        for _ in range(max(1, days)):
            out += self.tick()
            if self.over:
                break
        return out

    def _check_ending(self) -> List[str]:
        if self.treasury < C.BANKRUPTCY_FLOOR:
            self.over = "Ruined. Your debts outran your carts."
            return [self.over]
        if self.population < 5:
            self.over = "Deserted. The last family walked out of the gate."
            return [self.over]
        worth = self.net_worth()
        if worth >= C.GOAL_NET_WORTH and self.population >= C.GOAL_POPULATION:
            self.over = (f"Triumph. {worth:,.0f}c of house and holdings, "
                         f"{self.population:.0f} souls, in {self.day} days.")
            return [self.over]
        if self.day >= C.GOAL_DAYS:
            self.over = (f"Time called. You end with {worth:,.0f}c against a goal of "
                         f"{C.GOAL_NET_WORTH:,.0f}c and {self.population:.0f} of "
                         f"{C.GOAL_POPULATION} souls.")
            return [self.over]
        return []

    # ------------------------------------------------------------- caravans
    def new_caravan(self, home: str, name: str = "") -> Tuple[Optional[Caravan], str]:
        if home not in self.world.settlements:
            return None, f"{home} is not yours to outfit from"
        if len(self.caravans) >= self.caravan_limit:
            return None, (f"you can run {self.caravan_limit} caravans; "
                          f"build a trading post for another")
        if self.treasury < C.CARAVAN_COST:
            return None, f"outfitting costs {C.CARAVAN_COST:.0f}c"
        self.treasury -= C.CARAVAN_COST
        uid = self.next_caravan_uid
        self.next_caravan_uid += 1
        c = Caravan(uid=uid, name=name or f"Caravan {uid}", home=home, at=home)
        self.caravans.append(c)
        return c, ""

    def caravan(self, uid: int) -> Optional[Caravan]:
        return next((c for c in self.caravans if c.uid == uid), None)

    def disband(self, uid: int) -> str:
        c = self.caravan(uid)
        if not c:
            return f"no caravan {uid}"
        if c.state == "moving":
            return f"{c.name} is on the road; it must reach a town first"
        market = self.world.market_of(c.at)
        if market and c.cargo:
            for k, q in list(c.cargo.items()):
                market.add(k, q)
        self.caravans.remove(c)
        self.treasury += C.CARAVAN_COST * 0.4
        return f"{c.name} disbanded at {self.world.node_name(c.at)}"

    # -------------------------------------------------------------- building
    def build(self, settlement_key: str, building_key: str) -> str:
        s = self.world.settlements.get(settlement_key)
        if not s:
            return f"{settlement_key} is not one of your settlements"
        spec = building(building_key)
        coin = spec.build_cost.get("coin", 0.0)
        if self.treasury < coin:
            return f"{spec.name} costs {coin:.0f}c; you have {self.treasury:.0f}c"
        ok, why = s.can_build(building_key)
        if not ok:
            return why
        self.treasury -= coin
        self.ledger.building += coin
        s.start_build(building_key)
        return (f"{spec.name} begun at {s.name}; {spec.build_days} days, "
                f"{coin:.0f}c paid")

    def found(self, site_key: str) -> str:
        """Settle unclaimed land. Expensive, and the new town starts hungry."""
        site = self.world.sites.get(site_key)
        if not site:
            return f"no unclaimed site called {site_key!r}"
        if self.treasury < site.coin_cost:
            return (f"settling {site.name} costs {site.coin_cost:,.0f}c; "
                    f"you have {self.treasury:,.0f}c")
        self.treasury -= site.coin_cost
        self.ledger.building += site.coin_cost
        market = Market(name=site.name, stock={}, target={})
        from .settlement import Settlement
        s = Settlement(name=site.name, terrain=dict(site.terrain), market=market,
                       population=25.0, popularity=C.POPULARITY_START)
        s.update_market_targets()
        for k, q in (("bread", 40.0), ("apples", 30.0), ("wood", 120.0),
                     ("stone", 40.0), ("planks", 20.0)):
            market.add(k, q)
        for k in ALL_KEYS:
            market.posted[k] = market.curve(k, market.stock[k])
        self.world.settlements[site.key] = s
        self.world.place(site.key, site.x, site.y)
        del self.world.sites[site_key]
        return (f"{site.name} founded. 25 settlers, no roof over them yet -- "
                f"build hovels before they walk home.")

    # ------------------------------------------------------------ save/load
    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION, "day": self.day, "treasury": self.treasury,
            "seed": self.seed, "next_caravan_uid": self.next_caravan_uid,
            "over": self.over, "world": self.world.to_dict(),
            "caravans": [caravan_to_dict(c) for c in self.caravans],
            "events": self.events.to_dict(), "history": self.history[-400:],
            "rng": self.rng.getstate()[1][:8],
        }

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh)
        return f"saved to {path}"

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        g = cls(world=World.from_dict(d["world"]), treasury=d["treasury"],
                day=d["day"], seed=d["seed"])
        g.caravans = [caravan_from_dict(c) for c in d["caravans"]]
        g.events = EventEngine.from_dict(d["events"])
        g.next_caravan_uid = d["next_caravan_uid"]
        g.history = list(d.get("history", []))
        g.over = d.get("over", "")
        g.rng = random.Random(d["seed"] + d["day"])
        g.trade_engine = TradeEngine(g.world, g.rng)
        return g

    @classmethod
    def load(cls, path: str) -> "GameState":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
