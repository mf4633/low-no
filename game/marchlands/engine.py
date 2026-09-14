"""The game: one state object, one tick, one ledger.

The tick is deliberately ordered -- produce before you feed, feed before you
take the mood, pay before you count the day's coin -- because several feedback
loops (hunger -> mood -> productivity -> hunger) are only stable if the order
is fixed. War is settled last, after the day's work, so a siege eats into
tomorrow rather than rewriting today.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import building
from .chronicle import MOMENTOUS, NOTABLE, ROUTINE, Chronicle
from .castle import INVEST, Works, choose, storms_now
from .economics import MONEY_BASE, Accounts, Economy
from . import estates as estates_mod
from . import feats as feats_mod
from .events import EventEngine
from .goods import ALL_KEYS, good
from . import lords as lordly
from . import lord as manly
from . import chancery as court
from . import culture as cultures
from . import keep as keeps
from .kin import POSTS, Kin, found as found_kin
from . import league as lg
from .league import League, PLAYER
from .lord import Lord
from .market import Market
from .military import (BESIEGING, GARRISON, MARCHING, RAIDING, RETURNING,
                       UNITS, Army,
                       Side, can_recruit, describe, fight, host_speed,
                       host_strength, raid_day, recruit_cost, siege_day, unit)
from .settlement import Settlement
from .tech import AGES, TECHS, Progress
from .trade import (CART, SHIP, Caravan, TradeEngine, caravan_from_dict,
                    caravan_to_dict)
from .world import World

SAVE_VERSION = 2
CATHEDRAL_HOLD = 180


@dataclass
class Goals:
    """What this game is played for. A scenario sets its own."""
    net_worth: float = C.GOAL_NET_WORTH
    population: int = C.GOAL_POPULATION
    towns: int = C.GOAL_TOWNS
    relics: int = C.GOAL_RELICS
    relic_days: int = C.RELIC_HOLD_DAYS
    mood: float = 0.0                 # popularity a 'commons' chapter wants
    mood_days: int = 0                # ...held for this long
    days: int = C.GOAL_DAYS
    bankruptcy: float = C.BANKRUPTCY_FLOOR
    wonder: bool = True               # may the cathedral win it?
    paths: Tuple[str, ...] = ("wealth", "dominion", "bells", "reliquary")

    @property
    def years(self) -> int:
        return max(1, round(self.days / C.DAYS_PER_YEAR))

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["paths"] = list(self.paths)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Goals":
        d = dict(d)
        d["paths"] = tuple(d.get("paths",
                                  ("wealth", "dominion", "bells", "reliquary")))
        return cls(**d)


@dataclass
class Ledger:
    taxes: float = 0.0
    trade: float = 0.0
    tribute: float = 0.0
    plunder: float = 0.0
    offerings: float = 0.0
    interest: float = 0.0
    wages: float = 0.0
    upkeep: float = 0.0
    caravans: float = 0.0
    building: float = 0.0
    war: float = 0.0

    @property
    def income(self) -> float:
        return (self.taxes + self.tribute + self.plunder + self.offerings
                + self.interest + max(0.0, self.trade))

    @property
    def net(self) -> float:
        return (self.taxes + self.trade + self.tribute + self.plunder
                + self.offerings + self.interest - self.wages - self.upkeep - self.caravans - self.building - self.war)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _ordinal(n: int) -> str:
    """`3rd of 9`, because `place 3` is not how anybody says it."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


@dataclass
class GameState:
    world: World
    treasury: float = 1500.0
    day: int = 0
    caravans: List[Caravan] = field(default_factory=list)
    armies: List[Army] = field(default_factory=list)
    events: EventEngine = field(default_factory=EventEngine)
    progress: Progress = field(default_factory=Progress)
    goals: Goals = field(default_factory=Goals)
    house: str = ""
    scenario: str = "marchlands"
    briefing: str = ""
    start_month: int = C.START_MONTH
    seed: int = 7
    next_caravan_uid: int = 1
    next_army_uid: int = 1
    messages: List[str] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)
    history: List[dict] = field(default_factory=list)
    battles: List[str] = field(default_factory=list)
    cathedral_days: int = 0
    relic_days: int = 0
    mood_days: int = 0
    lord: Lord = field(default_factory=Lord)
    #: Who he is, who is behind him, and what each of them has been doing.
    kin: Kin = field(default_factory=Kin)
    #: The march as a competition: a table, a schedule, and a draft.
    league: League = field(default_factory=League)
    #: Who is talking to whom, and why. Every reason anybody has to like or
    #: dislike you lives here, dated and decaying; see chancery.py.
    court: court.Chancery = field(default_factory=court.Chancery)
    #: The national accounts, and the mint. Measures everything, moves one
    #: thing: the price level, which is the only honest way for a debasement
    #: to be felt.
    economy: Economy = field(default_factory=Economy)
    #: The three men who actually run the march. Every dial in this game has
    #: cost coin or mood and none has ever cost you somebody powerful being
    #: annoyed about it.
    estates: estates_mod.Estates = field(default_factory=estates_mod.Estates)
    #: Things worth having done, which is not the same as things worth doing.
    #: A scenario's goal says what the game is for; these say what it can do.
    feats: feats_mod.Book = field(default_factory=feats_mod.Book)
    #: Tallies nothing else keeps, because a feat must be checked against a
    #: figure rather than instrumented into the thing it counts.
    _hosts_raised: int = 0
    _battles_won: int = 0
    _stormed: int = 0
    _towns_lost: int = 0
    _trade_profit: float = 0.0
    chronicle: Chronicle = field(default_factory=Chronicle)
    chapter: str = ""           # which chapter of a campaign, if any
    over: str = ""              # '' while playing, else the ending

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.trade_engine = TradeEngine(self.world, self.rng)
        self._outlay = 0.0        # coin spent between ticks, for the ledger
        self.accounts = Accounts(day=self.day)
        self._war_outlay = 0.0
        self._plunder = 0.0
        if self.lord.name == Lord.name and self.world.settlements:
            # A lord of your own, seated in whatever you hold -- and a wife,
            # and children of an age to be given something to do before the
            # campaign is over. See kin.found for why they start half-grown.
            self.lord.seat = next(iter(self.world.settlements))
        if not self.kin.people:
            seed = random.Random(self.seed * 104729)
            self.kin = found_kin(seed, seat=self.lord.seat,
                                 lord_name=None if self.lord.name == Lord.name
                                 else self.lord.name)
            self.lord.name = self.kin.lord.name
        self.kin.seat = self.lord.seat
        if not self.league.seed:
            self.league.seed = self.seed * 40507 + 13
            self.league.rng = random.Random(self.league.seed)
        if not self.court.seed:
            self.court.seed = self.seed * 15485863 + 7
            self.court.rng = random.Random(self.court.seed)
        # What a lord says when he declares is flavour and must stay flavour.
        # Drawn from the world's own stream it would not be: every line spoken
        # shifts the weather, the prices and the next battle behind it, and an
        # `ask` typed at the console -- or a browser polling once a second --
        # would quietly re-roll the campaign. Third time this bug has been
        # found in this codebase (kin, league, now this); a subsystem that
        # draws gets its own stream, without exception.
        self.voice = random.Random(self.seed * 7919 + 101)

    # ------------------------------------------------------------- calendar
    @property
    def _calendar_day(self) -> int:
        return self.day + (self.start_month - 1) * C.DAYS_PER_MONTH

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
        # No padding. The rule beside it takes up the slack, and `month  4`
        # with a hole in the middle of it is the sort of thing a reader sees.
        return (f"day {self.day_of_month} of month {self.month}, "
                f"{self.year} ({self.season})")

    # ------------------------------------------------------------- economics
    def net_worth(self) -> float:
        worth = self.treasury
        for s in self.world.settlements.values():
            worth += s.net_worth()
        fallback = next(iter(self.world.settlements.values())).market
        for c in self.caravans:
            m = self.world.market_of(c.at) or fallback
            worth += sum(q * m.bid(k) for k, q in c.cargo.items())
            worth += C.CARAVAN_COST * 0.5
        for a in self.armies:
            if a.owner == "player":
                worth += sum(UNITS[k].coin * n * 0.5 for k, n in a.units.items())
        return worth

    def real_worth(self) -> float:
        """Net worth in the coin of the first year, which is the only kind
        that can be a goal.

        The chest and the granary are both counted at today's prices, so a
        debasement raises net worth the instant it is struck -- twenty
        thousand coins of it, on a goal of a hundred and twenty. The target
        was therefore reachable by printing, which is not a strategy, it is a
        hole. Dividing the mint back out closes it: you cannot mint your way
        to a fortune, only to a larger number of smaller coins.

        Deliberately the price *level* and not the index. The index also
        carries how dear this particular town's basket is, which is a real
        fact about a place that grows wheat and buys everything else -- and
        deflating by it would have made every wealth goal in the game
        unreachable by a factor of four. The mint is the only thing that ought
        to be divided out, so the mint is the only thing that is.

        The divisor is the money you have *struck*, not the price level that
        has so far caught up with it. Prices lag by a year or two and that lag
        is the whole reason anybody debases -- but a goal measured against the
        lagging number could be crossed by minting on the last afternoon,
        before a single price had noticed. Measured against the money supply
        the debasement counts the moment the dies come down, which is when the
        decision was actually made.

        This does not make a debasement worthless, and it should not:
        seigniorage is a real tax really collected, and a lord who strikes
        light coin really is better off at the expense of everyone holding the
        old. It makes it *honest*, and gives it the shape it has in life --
        worth most to a poor house with nothing to lose, and a straight loss
        to a rich one, because a third more coin against a hundred thousand of
        holdings takes more than the twenty thousand it hands you.
        """
        return self.net_worth() / max(1.0, self.economy.money / MONEY_BASE)

    @property
    def population(self) -> float:
        return sum(s.population for s in self.world.settlements.values())

    @property
    def soldiers(self) -> int:
        return (sum(s.soldiers for s in self.world.settlements.values())
                + sum(a.size for a in self.armies if a.owner == "player"))

    @property
    def caravan_limit(self) -> int:
        return int(2 + sum(s.caravan_slots for s in self.world.settlements.values())
                   + self.progress.bonus("caravan_slots"))

    def home(self) -> Settlement:
        """The seat: wherever the keep stands, else your first settlement."""
        for s in self.world.settlements.values():
            if s.count("keep"):
                return s
        return next(iter(self.world.settlements.values()))

    def _key_of(self, s: Settlement) -> str:
        """The key a settlement is filed under, which posts are given against."""
        for key, other in self.world.settlements.items():
            if other is s:
                return key
        return ""

    # ------------------------------------------------------------------ tick
    def tick(self) -> List[str]:
        if self.over:
            return [self.over]
        self.day += 1
        msgs: List[str] = []
        led = Ledger()

        msgs += self.events.tick(self.world, self.day, self.rng, self.progress)

        # 1. Settlements work, eat and are taxed.
        for key, s in self.world.settlements.items():
            before = {b.uid: b.complete for b in s.buildings}
            rep = s.tick(self.season, self.rng, self.progress)
            for b in s.buildings:
                if b.complete and not before.get(b.uid, True):
                    msgs.append(f"{s.name}: {b.spec.name} finished")
            # A steward who knows the ground gets more out of the same ground.
            led.taxes += (rep.taxes * self.kin.mult("taxes", key)
                          * max(0.1, 1.0 + self.estates.effect("tax")))
            led.wages += rep.wages
            led.upkeep += rep.upkeep
            msgs += rep.notes
        # Your hosts, not the ones marching on you -- and a host bigger than
        # your holdings can reasonably keep costs more per man than the last.
        # Not a ceiling: a ceiling is a rule a player fights, a rising cost is
        # a decision a player makes, and it still ends runaway musters because
        # the last man on the roll eats like three.
        led.war = sum(a.upkeep for a in self.armies if a.owner == "player")
        led.war *= self.muster_cost()
        led.building, self._outlay = self._outlay, 0.0
        led.war += self._war_outlay
        self._war_outlay = 0.0
        led.plunder, self._plunder = self._plunder, 0.0

        # 2. Pay the wage bill; an unpaid day costs you the town's goodwill.
        payroll = led.wages + led.upkeep + led.war
        if self.treasury < payroll:
            for s in self.world.settlements.values():
                s.report.unpaid = True
            msgs.append("THE COFFERS ARE EMPTY -- wages went unpaid today")
        led.tribute = sum(t.tribute() for t in self.world.towns.values() if t.mine)
        led.offerings = self.relic_income()
        if self.treasury > 0:
            led.interest = self.treasury * self.progress.bonus("interest")
        self.treasury += (led.taxes + led.tribute + led.offerings + led.interest
                          - payroll)

        # 3. Markets at home relax toward their fundamentals.
        for s in self.world.settlements.values():
            s.market.settle_day()

        # 4. The wider world produces, consumes and reprices.
        for t in self.world.towns.values():
            t.tick(self.rng)

        # 5. Caravans move and deal.
        before_trade = self.treasury
        self.trade_engine.season = self.season
        caravan_cost = sum(c.daily_cost for c in self.caravans)
        self.treasury, tmsgs = self.trade_engine.tick(self.caravans, self.treasury)
        led.caravans = caravan_cost
        led.trade = (self.treasury - before_trade) + caravan_cost
        # Whoever has the carts. On a day the road paid, it paid a little more;
        # on a day it did not, no amount of skill invents a buyer.
        gain = self.treasury - before_trade
        if gain > 0:
            factored = gain * (self.kin.mult("trade")
                               * self.estates.mult("trade") - 1.0)
            self.treasury += factored
            led.trade += factored
            self._trade_profit += gain + factored
        msgs += tmsgs

        msgs += self._estates_day()
        msgs += self.feats.check(self._standing())

        # 6. Learning, and the slow climb between ages.
        msgs += self._study()

        # 7. War.
        msgs += self._military_day()

        # 8. The league: the turn of the year, the table, the draft.
        msgs += self._league_day()

        # 9. The mint, the assize, and the reckoning of what any of it was
        # worth. Prices walk toward what the money supply says they must be;
        # a legal maximum bites or does not; and the day is then measured.
        msgs += self._economy_day()

        # 10. Mood and migration settle last, on the day as it actually went.
        for s in self.world.settlements.values():
            s.update_mood(self.progress)
            s.migrate(self.rng, self.progress)
            if s.popularity < C.UNREST_THRESHOLD:
                msgs.append(f"{s.name} is in open unrest -- nobody is working")

        self.ledger = led
        self.accounts = self.economy.observe(self)
        self.history.append({
            "day": self.day, "treasury": self.treasury, "worth": self.net_worth(),
            "pop": self.population,
            "pop_mood": sum(s.popularity for s in self.world.settlements.values())
                        / max(1, len(self.world.settlements)),
            "net": led.net, "soldiers": self.soldiers, "age": self.progress.age,
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

    # ------------------------------------------------------- ages and techs
    def _study(self) -> List[str]:
        msgs: List[str] = []
        p = self.progress
        if p.advancing:
            p.advancing -= 1
            if p.advancing <= 0:
                p.age += 1
                msgs.append(self.note(f"*** The {AGES[p.age].name} begins ***",
                                      MOMENTOUS))
        if p.researching:
            p.research_left -= (p.mult("research_speed") * self._scholars()
                                * self.estates.mult("research"))
            if p.research_left <= 0:
                p.researched.add(p.researching)
                msgs.append(f"Learned: {TECHS[p.researching].name}")
                p.researching = ""
        return msgs

    def _scholars(self) -> float:
        """Guildhalls do the studying; without one, nothing is learned."""
        halls = sum(s.effect("research") for s in self.world.settlements.values())
        return min(2.0, halls) if halls else 0.0

    def begin_age(self) -> str:
        p = self.progress
        nxt = p.next_age()
        if p.advancing:
            return f"already climbing to the {AGES[p.age + 1].name} ({p.advancing}d)"
        if not nxt:
            return "there is no age beyond this one"
        home = self.home()
        for key in nxt.needs:
            if not any(s.count(key) for s in self.world.settlements.values()):
                return f"the {nxt.name} needs {building(key).name} first"
        coin = nxt.cost.get("coin", 0.0)
        if self.treasury < coin:
            return f"the {nxt.name} costs {coin:,.0f}c; you have {self.treasury:,.0f}c"
        short = [(k, q) for k, q in nxt.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{home.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short))
        self.treasury -= coin
        self._outlay += coin
        for k, q in nxt.cost.items():
            if k != "coin":
                home.market.take(k, q)
        p.advancing = nxt.days
        return f"Work begins toward the {nxt.name} -- {nxt.days} days"

    def research(self, key: str) -> str:
        p = self.progress
        if key not in TECHS:
            return f"no such craft as {key!r}"
        t = TECHS[key]
        if key in p.researched:
            return f"{t.name} is already known"
        if p.researching:
            return f"the guildhall is busy with {TECHS[p.researching].name}"
        if t.age > p.age:
            return f"{t.name} belongs to the {AGES[t.age].name}"
        if t.prereq and t.prereq not in p.researched:
            return f"{t.name} follows {TECHS[t.prereq].name}"
        if not self._scholars():
            return "you have no guildhall to study in"
        home = self.home()
        coin = t.cost.get("coin", 0.0)
        if self.treasury < coin:
            return f"{t.name} costs {coin:,.0f}c"
        short = [(k, q) for k, q in t.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{home.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short))
        self.treasury -= coin
        self._outlay += coin
        for k, q in t.cost.items():
            if k != "coin":
                home.market.take(k, q)
        p.researching = key
        p.research_left = float(t.days)
        return f"The guildhall takes up {t.name} -- about {t.days} days"

    # -------------------------------------------------------------- military
    def recruit(self, settlement_key: str, unit_key: str, count: int) -> str:
        s = self.world.settlements.get(settlement_key)
        if not s:
            return f"{settlement_key} is not yours"
        if not s.effect("muster"):
            return f"{s.name} has no barracks"
        ok, why = can_recruit(unit_key, self.progress)
        if not ok:
            return why
        u = unit(unit_key)
        count = max(1, int(count))
        coin, goods = recruit_cost(unit_key, count, self.progress)
        if self.treasury < coin:
            return f"{count} {u.name} cost {coin:,.0f}c; you have {self.treasury:,.0f}c"
        short = [(k, q) for k, q in goods.items() if s.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{s.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short) +
                " -- soldiers are armed from your own workshops")
        if u.unit_class != "siege" and s.workforce < count:
            return f"{s.name} has no spare hands; every soldier is one fewer worker"
        self.treasury -= coin
        self._war_outlay += coin
        for k, q in goods.items():
            s.market.take(k, q)
        # The knights hold the land the levies come off. Sulking, they send
        # word that the men could not be spared -- and you are out the coin
        # either way, which is the part that makes their loyalty matter.
        came = max(1, int(round(count * self.estates.mult("muster"))))
        s.units[unit_key] = s.units.get(unit_key, 0.0) + came
        if came < count:
            return (f"{came} {u.name} muster at {s.name} ({coin:,.0f}c) -- "
                    f"you paid for {count}; the knights spared what they chose")
        if came > count:
            return (f"{came} {u.name} muster at {s.name} ({coin:,.0f}c) -- "
                    f"more than you asked for; the knights are keen")
        return f"{count} {u.name} muster at {s.name} ({coin:,.0f}c)"

    def _standing(self) -> "feats_mod.Standing":
        """Every figure a feat may read, gathered once and from the game's
        own books rather than instrumented into the thing it counts."""
        seats = list(self.world.settlements.values())
        mine_towns = [t for t in self.world.towns.values() if t.mine]
        idioms = {t.culture for t in mine_towns if t.culture}
        idioms |= {getattr(s, "culture", "") for s in seats}
        wall = sum(len(s.plan().pieces) for s in seats if hasattr(s, "plan"))
        inside = 0
        for s in seats:
            if hasattr(s, "plan"):
                from . import keep as keeps
                inside = max(inside, len(keeps.enclosed(s.plan())))
        loyal = sum(1 for st in self.estates.by_key.values() if st.loyalty >= 60)
        grants = sum(len(st.privileges) for st in self.estates.by_key.values())
        return feats_mod.Standing(
            day=self.day, year=self.year,
            net_worth=self.net_worth(), treasury=self.treasury,
            population=int(sum(s.population for s in seats)),
            towns=len(mine_towns),
            relics=len([sh for sh in self.world.shrines.values()
                        if getattr(sh, "holder", "") == "player"]),
            age=self.progress.age, techs=len(self.progress.researched),
            battles_won=self._battles_won, hosts_raised=self._hosts_raised,
            coin_minted=float(getattr(self.economy, "minted", 0.0) or 0.0),
            allies=len(getattr(self.court, "allies", ())),
            coalition=len(getattr(self.court, "coalition", ())),
            marriages=sum(1 for p in self.kin.people if p.alive and p.married_to),
            wall_yards=wall, enclosed=inside,
            soldiers=int(sum(sum(s.units.values()) for s in seats)),
            trade_profit=self._trade_profit,
            idioms_seen=len([i for i in idioms if i]),
            estates_loyal=loyal, privileges=grants,
            worst_estate=min((st.loyalty for st in self.estates.by_key.values()),
                             default=100.0),
            mood=max((s.popularity for s in seats), default=0.0),
            took_by_storm=self._stormed, lost_towns=self._towns_lost)

    def raise_host(self, settlement_key: str, units: Dict[str, int],
                   name: str = "") -> Tuple[Optional[Army], str]:
        s = self.world.settlements.get(settlement_key)
        if not s:
            return None, f"{settlement_key} is not yours"
        take: Dict[str, float] = {}
        for k, n in units.items():
            have = s.units.get(k, 0.0)
            if have < n:
                return None, f"{s.name} has only {have:.0f} {unit(k).name}"
            take[k] = float(n)
        if not take:
            return None, "name some soldiers to march"
        for k, n in take.items():
            s.units[k] -= n
            if s.units[k] < 0.5:
                del s.units[k]
        a = Army(uid=self.next_army_uid, name=name or f"Host {self.next_army_uid}",
                 owner="player", units=take, at=settlement_key, home=settlement_key)
        self.next_army_uid += 1
        self.armies.append(a)
        self._hosts_raised += 1
        return a, ""

    def army(self, uid: int) -> Optional[Army]:
        return next((a for a in self.armies if a.uid == uid), None)

    def march(self, uid: int, node: str) -> str:
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if node not in self.world.coords:
            return f"nowhere called {node!r}"
        if a.at == node:
            return self._arrive(a)
        dist = self.world.distance(a.at or a.home, node)
        a.bound_for = node
        a.days_left = max(1.0, dist / max(host_speed(a.units), 1.0))
        a.state = MARCHING
        return (f"{a.name} marches on {self.world.node_name(node)} -- "
                f"{a.days_left:.0f} days")

    #: How long a march counts as the same war for the purpose of who takes
    #: offence at it. Sitting down, standing up and sitting down again is one
    #: quarrel, not three, and charging for it three times would make a long
    #: siege a diplomatic catastrophe by arithmetic rather than by judgement.
    WAR_MEMORY = 200

    def _declare(self, town) -> str:
        """Sitting down in front of a lord's walls, and who minds.

        The moment a war actually begins, which is not the order to march --
        a host can be turned round on the road and nobody on this march will
        have written a letter about it. What decides the cost is whether you
        had a reason anybody else accepts: with one, the rest of them shrug;
        without one, they all take note, and so does your own town, which has
        sons in the host and no idea what any of this is for.
        """
        key = town.key
        if self.day - self.court.declared.get(key, -9999) < self.WAR_MEMORY:
            return ""                        # the same quarrel, still running
        self.court.declared[key] = self.day
        ground = self.court.ground_for(key, self.day)
        if ground is not None:
            self.court.justified[key] = self.day
        # Everybody minds a siege. What a ground changes is how much.
        scale = 0.45 if ground else 1.0
        others = [k for k, t in self.world.towns.items()
                  if not t.mine and k != key]
        for other in others:
            near = self.world.distance(other, key)
            close = max(0.5, min(1.3, 90.0 / max(30.0, near)))
            self.court.write(other, "besieged",
                             -12.0 * scale * close * lordly.sort_of(other).temper,
                             self.day)
        self.court.write(key, "besieged", -45.0, self.day)
        if ground:
            return (f"\n    You have grounds: {ground.label}. The march will "
                    f"not much mind.")
        # No reason anybody accepts. Everyone takes it harder, and so does
        # your own hall.
        self.court.write_all(others, "unjust",
                             -14.0 * self.war_pressure(), self.day)
        cost = court.unjust_cost(len(others))
        for s in self.world.settlements.values():
            s.popularity = max(0.0, s.popularity - cost)
        self.kin.did("merciful", -0.12)
        return (f"\n    You have no grounds anybody will accept. "
                f"{len(others)} lord(s) take note, and your own towns lose "
                f"{cost:.0f} of mood over a war they cannot name.")

    def disband_host(self, uid: int) -> str:
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.state == MARCHING:
            return f"{a.name} is on the road"
        s = self.world.settlements.get(a.at)
        if not s:
            return f"{a.name} must be in one of your settlements to stand down"
        for k, n in a.units.items():
            s.units[k] = s.units.get(k, 0.0) + n
        self.armies.remove(a)
        return f"{a.name} stands down into the garrison of {s.name}"

    def _military_day(self) -> List[str]:
        msgs: List[str] = []
        for s in self.world.settlements.values():
            s.besieged = False
            s.blockaded = False
            s.raided = False
            s.raid_pressure = 0.0
        for a in list(self.armies):
            if a.owner != "player" and self.world.towns[a.owner].mine:
                msgs.append(f"{a.name} turns for home -- {self.world.node_name(a.owner)} "
                            f"is sworn to you now")
                self.armies.remove(a)
                continue
            if a.state == MARCHING:
                a.siege_days = 0
                a.days_left -= 1
                if a.days_left <= 0:
                    a.at, a.bound_for = a.bound_for, ""
                    msgs.append(self._arrive(a))
            elif a.state == BESIEGING:
                msgs += self._siege(a)
            elif a.state == RAIDING:
                msgs += self._raid(a)
            a.prune()
            if a.size <= 0 and a in self.armies:
                msgs.append(f"{a.name} is no more")
                self.armies.remove(a)
        self._look_around()
        msgs += self._lord_day()
        msgs += self._shrine_day()
        msgs += self._shrine_race()
        msgs += self._lords_and_hosts()
        msgs = [m for m in msgs if m]
        self.battles += [m for m in msgs if m]
        if len(self.battles) > 120:
            del self.battles[:-120]
        return msgs

    def _arrive(self, a: Army) -> str:
        """What happens when a host walks up to a place."""
        node = a.at
        if node in self.world.shrines:
            sh = self.world.shrines[node]
            a.state = GARRISON
            a.siege_days = 0
            if sh.taken:
                if a.owner != "player":
                    self.march(a.uid, a.home)
                return f"{a.name} reaches {sh.name}. The shrine is already stripped."
            return (f"{a.name} reaches {sh.name}. "
                    f"{C.RELIC_DAYS} days to lift {sh.relic}.")
        if a.owner == "player":
            if self.world.is_friendly(node):
                a.state = GARRISON
                return f"{a.name} reaches {self.world.node_name(node)}"
            town = self.world.towns[node]
            a.state = BESIEGING
            return (f"{a.name} sits down before {town.name} "
                    f"({town.wall_hp:.0f} of wall, {describe(town.garrison)} within)"
                    + self._declare(town))

        if node == a.home and node in self.world.towns:
            # A host that gets home stands down into its own town's garrison,
            # so the lord can call it out again another year.
            town = self.world.towns[node]
            for k, n in a.units.items():
                town.garrison[k] = town.garrison.get(k, 0.0) + n
            if a in self.armies:
                self.armies.remove(a)
            return ""
        s = self.world.settlements.get(node)
        if s is not None:
            # A captain who cannot carry the walls does not throw his men at
            # them: he burns the country instead and rides home richer. This
            # is the half of medieval war that actually happened.
            # A captain who cannot carry the walls does not throw his men at
            # them -- and some lords never mean to try the walls at all. The
            # Fox came for the harvest and said so a season ago.
            shy = 0.9 + 1.6 * lordly.sort_of(a.home).raids
            if host_strength(a.units) < host_strength(s.units) * shy:
                a.state = RAIDING
                s.raided = True
                return (f"Riders out of {self.world.node_name(a.home)} are loose "
                        f"in the country around {s.name}! {describe(a.units)}")
            a.state = BESIEGING
            s.besieged = True
            return (f"A host out of {self.world.node_name(a.home)} is before "
                    f"{s.name}! {describe(a.units)}")
        town = self.world.towns.get(node)
        if town is None or town.owner == a.owner:
            a.state = GARRISON
            return ""
        a.state = BESIEGING
        whose = " (sworn to you)" if town.mine else ""
        return (f"{self.world.node_name(a.home)} lays siege to {town.name}{whose}")

    SIEGE_PATIENCE = 21          # days a host will sit at a wall it cannot break
    MAX_RIVAL_WARS = 2           # wars between other lords running at once

    def _siege(self, a: Army) -> List[str]:
        a.siege_days += 1
        if a.siege_power <= 0 and a.siege_days > self.SIEGE_PATIENCE:
            # Hunger and boredom break more sieges than arrows do.
            a.siege_days = 0
            where = self.world.node_name(a.at)
            if a.owner == "player":
                self.march(a.uid, a.home)
                return [f"{a.name} has nothing to break the walls of {where} with "
                        f"and breaks up"]
            if a in self.armies:
                self.armies.remove(a)
            return [f"The host outside {where} breaks up and goes home"]
        if a.at in self.world.towns:
            return self._siege_town(a, self.world.towns[a.at])
        s = self.world.settlements.get(a.at)
        return self._siege_settlement(a, s) if s else []

    def _shrine_day(self) -> List[str]:
        """Hosts standing at a shrine lift what is in it, given long enough.

        There is no garrison to fight -- the contest is simply whether you
        were willing to send men somewhere that defends nothing.
        """
        msgs: List[str] = []
        for key, sh in self.world.shrines.items():
            if sh.taken:
                continue
            here = [a for a in self.armies if a.at == key and a.state == GARRISON]
            if not here:
                continue
            if len({a.owner for a in here}) > 1:
                # Two parties at one shrine and nobody is praying. Somebody has
                # to leave, and it is decided the usual way.
                here.sort(key=lambda x: host_strength(x.units), reverse=True)
                winner, loser = here[0], here[1]
                res = fight(Side(winner.units), Side(loser.units), rng=self.rng,
                            place=sh.name)
                winner.prune()
                if res.winner == "attacker":
                    beaten, kept = loser, winner
                else:
                    beaten, kept = winner, loser
                msgs.append(f"Men come to blows at {sh.name}; "
                            f"{beaten.name} is driven off")
                self.scored(kept.owner, won=True)
                self.scored(beaten.owner, won=False)
                if beaten.owner == "player":
                    self.march(beaten.uid, beaten.home)
                elif beaten in self.armies:
                    self.armies.remove(beaten)
                kept.siege_days = 0
                continue
            a = here[0]
            a.siege_days += 1
            if a.siege_days > C.RELIC_DAYS * 3 and a.owner != "player":
                # Nobody waits at a shrine for ever.
                self.march(a.uid, a.home)
                continue
            if a.siege_days < C.RELIC_DAYS:
                continue
            sh.holder = a.owner
            a.siege_days = 0
            who = "You have" if a.owner == "player" else \
                f"{self.world.node_name(a.owner)} has"
            # Somebody else's pilgrimage is not an event in your reign. It goes
            # in, because in the relic chapter it is the whole argument, but it
            # does not shoulder your own years out of the way.
            msgs.append(self.note(f"*** {who} lifted {sh.relic} from {sh.name}. ***",
                                  MOMENTOUS if a.owner == "player" else ROUTINE))
            # Everyone goes home afterwards. A party left standing at a shrine
            # is a lord who counts as having his host out for ever, and a lord
            # whose host is out never declares on anybody.
            self.march(a.uid, a.home)
        return msgs

    #: Chance per day that some lord remembers the shrines are unguarded.
    SHRINE_RACE_ODDS = 0.010     # measured: the five go between roughly day 120
                                 # and day 800, which leaves a real window to
                                 # contest rather than a scramble in the first
                                 # season and nothing afterwards
    SHRINE_COOLDOWN = 150        # days before one lord goes relic-hunting again
    SHRINE_GRACE = 90            # nobody thinks of the shrines before this

    def _shrine_race(self) -> List[str]:
        """Somebody else also wants the bones.

        Without this the shrines are a standing gift to whoever bothers, which
        is not a contest. A lord with ambition and no war on will send a small
        party, and a small party is enough -- there is nothing there to fight.
        """
        if self.day < self.SHRINE_GRACE:
            return []
        free = [k for k, sh in self.world.shrines.items() if not sh.taken]
        if not free or self.rng.random() > self.SHRINE_RACE_ODDS:
            return []
        busy = {a.owner for a in self.armies}
        # A pilgrimage is a party of spearmen, not a war: it must not spend the
        # ambition a lord has been saving to move on his neighbour, or the
        # march quietly stops rearranging itself.
        # And it must not be the lord who is about to move on a neighbour: a
        # party away at a shrine counts as his host being out, so choosing the
        # most ambitious man on the march would quietly keep the peace.
        lords = [t for k, t in self.world.towns.items()
                 if not t.mine and k not in busy
                 and 20.0 < t.ambition < C.HOSTILITY_WAR * 0.6
                 and self.day - t.last_pilgrimage > self.SHRINE_COOLDOWN]
        if not lords:
            return []
        town = lords[self.rng.randrange(len(lords))]
        # Do not send men where somebody is already standing: that is how a
        # march ends up with seven parties at one shrine and no lord at home.
        standing = {a.at for a in self.armies}
        open_ones = [k for k in free if k not in standing]
        if not open_ones:
            return []
        target = min(open_ones, key=lambda k: self.world.distance(town.key, k))
        party = {"spearman": max(6.0, 14.0 * town.muster)}
        a = Army(uid=self.next_army_uid, name=f"{town.lord}'s pilgrimage",
                 owner=town.key, units=party, at=town.key, home=town.key,
                 errand="pilgrimage")
        self.next_army_uid += 1
        self.armies.append(a)
        a.bound_for = target
        a.days_left = max(1.0, self.world.distance(town.key, target)
                          / max(host_speed(party), 1.0))
        a.state = MARCHING
        town.last_pilgrimage = self.day
        return [f"{town.lord} of {town.name} sends men to "
                f"{self.world.shrines[target].name}"]

    def lead(self, uid: int) -> str:
        """Send your lord out with a host, for what that is worth both ways."""
        if self.lord.gone:
            return f"{self.lord.name} is {self.lord.standing(self.world.node_name)}"
        if uid == 0:
            self.lord.riding = 0
            return f"{self.lord.name} returns to his hall"
        a = self.army(uid)
        if not a or a.owner != "player":
            return f"no host of yours numbered {uid}"
        self.lord.riding = uid
        return (f"{self.lord.name} rides with {a.name}. The men will fight "
                f"harder and stand longer, and he is where the arrows are.")

    def ransom_lord(self) -> str:
        if not self.lord.captured:
            return f"{self.lord.name} is {self.lord.standing(self.world.node_name)}"
        if self.treasury < self.lord.ransom:
            return (f"They want {self.lord.ransom:,.0f}c for {self.lord.name} "
                    f"and you have {self.treasury:,.0f}c")
        self.treasury -= self.lord.ransom
        self.ledger.war += self.lord.ransom
        self.lord.captured = False
        self.lord.ransom = 0.0
        return f"{self.lord.name} is bought back and rides in at the gate"

    def note(self, text: str, weight: int = NOTABLE) -> str:
        """Write a line in the chronicle and hand it back to be said aloud."""
        self.chronicle.record(day=self.day, year=self.year, season=self.season,
                              text=text, weight=weight, chapter=self.chapter)
        return text

    def _lord_fell(self) -> List[str]:
        """His host broke around him. Both halves of the man have to hear it.

        `Lord` holds where he is standing; `Kin` holds who he was and who has
        been training behind him. Keeping the two in step in one place is the
        only reason a succession can say `Osric takes the seat, 22 years old,
        trade 4` instead of picking a name out of a hat -- which is what the
        old call to `name_for` did, and it is why the heir was nobody.
        """
        self.lord.ransom = min(9000.0, 900.0 + 0.06 * self.net_worth())
        heir = self.kin.heir(self.day)
        msgs = self.lord.falls(self.rng, heir.name if heir else self.lord.name)
        if not self.lord.alive:
            who = self.kin.lord
            if who is not None:
                msgs += [self.note(ln, MOMENTOUS)
                         for ln in self.kin.bury(who, self.day)]
            for st in self.world.settlements.values():
                st.popularity = max(0.0, st.popularity - manly.MOURNING)
        return msgs

    def _lord_day(self) -> List[str]:
        msgs = self.lord.day()
        if self.lord.riding and self.army(self.lord.riding) is None:
            self.lord.riding = 0        # the host he rode with is gone
        seat = self.lord.seat or next(iter(self.world.settlements), "")
        self.kin.seat, self.kin.riding = seat, self.lord.riding

        # What the head of the house did today is what the head of the house
        # learned today. A lord who never leaves the hall is a good steward
        # and an unproven soldier, and the campaign will say so.
        riding = self.army(self.lord.riding) if self.lord.riding else None
        doing = ("siege" if riding is not None and riding.state == BESIEGING
                 else "field" if riding is not None else "hall")
        before = self.kin.head
        # A birth, a death and a succession are the three things a chronicle is
        # for. The house says them; this is where they get written down.
        for line in self.kin.day(self.day, head_doing=doing):
            msgs.append(self.note(line, MOMENTOUS) if line.startswith("***")
                        else line)
        if self.kin.head != before and self.lord.alive:
            # He died in his bed. The hall is as empty as if he had not.
            self.lord.alive = False
            self.lord.riding = 0
            self.lord.heir_days = manly.SUCCESSION_DAYS
            for st in self.world.settlements.values():
                st.popularity = max(0.0, st.popularity - manly.MOURNING)
        if self.kin.lord is not None:
            self.lord.name = self.kin.lord.name
        self.lord.heirs = self.kin.heirs_left(self.day)
        msgs += self._reputation_day()

        for key, st in self.world.settlements.items():
            st.lord_home = self.lord.at_home and key == seat
            st.lord_lost = self.lord.gone and key == seat
            st.steward_mood = self.kin.bonus("mood", key)
        return msgs

    def _reputation_day(self) -> List[str]:
        """The march's opinion of your lord, formed a little at a time.

        Nobody picks a trait off a list. You hold the tax low for two years and
        the word gets about; you keep him behind his own wall through a war and
        that gets about too. A day moves any of these by about a four-hundredth
        of the way to its extreme, which is the point: a reputation you can
        change in a week is not a reputation.
        """
        home = self.home()
        if home is not None:
            # The bands run -2 (largesse) to 4 (cruel), so the count of them is
            # not the worst of them. Normalising against the wrong one made
            # "none" read as half-way to cruel.
            tax = home.tax_level / max(C.TAX_LEVELS)
            self.kin.did("just", 0.008 * (0.45 - tax))
            if home.report.unpaid:
                self.kin.did("open", -0.02)
        at_war = any(a.owner != "player" for a in self.armies)
        if self.lord.in_the_field:
            self.kin.did("bold", 0.006)
        elif at_war and self.lord.at_home:
            self.kin.did("bold", -0.003)
        return []

    # ------------------------------------------------------------ the money
    ASSIZE_DRAIN = 0.85          # extra demand, as a share of a day's use
    ASSIZE_LEAK = 0.004          # of stock a day out of the back door besides
    ASSIZE_RELIEF = 13.0         # what cheap bread is worth while there is any
    ASSIZE_MOOD = 16.0           # ...and what queuing for it costs when there is not
    SMUGGLE_SHARE = 0.55         # of the drained goods that leave for a profit
    MINT_MOOD = 9.0              # what a debased penny costs you in goodwill

    def _economy_day(self) -> List[str]:
        """What the mint and the assize did today.

        Both of these are the textbook's two most famous results and neither
        is a special case bolted on: minting moves the price *level*, which
        every price in the game is already multiplied by, and a cap is a
        number the market may not post above, which the sheds that sell into
        it can feel in what they are paid.
        """
        msgs: List[str] = []
        econ = self.economy
        econ.settle()
        econ.smuggled = 0.0
        for s in self.world.settlements.values():
            s.market.level = econ.price_level
            s.market.caps = dict(econ.assize)
            s.assize_mood = 0.0
        # And every market your carts deal with, because there is one coin on
        # this march and it is yours. A debased penny buys less in Ostmark
        # too; leaving foreign prices alone would have made minting a standing
        # subsidy on imports, which is an arbitrage the mint itself printed.
        for t in self.world.towns.values():
            t.market.level = econ.price_level
        for key, cap in list(econ.assize.items()):
            bite = max(s.market.binding(key)
                       for s in self.world.settlements.values())
            econ.shortage[key] = bite
            if bite <= 0.01:
                continue
            # Both halves of it, which is the whole point of the lever. Cheap
            # bread is a real transfer to real people and they are grateful
            # for it -- right up until there is none, and then they are
            # standing in a queue that your proclamation put them in. A price
            # control that only ever hurt was not a decision, it was a trap;
            # this one is a month of goodwill bought against the granary.
            for s in self.world.settlements.values():
                want = max(1.0, s.market.target.get(key, 0.0) * 0.6)
                plenty = min(1.0, s.market.stock.get(key, 0.0) / want)
                relief = self.ASSIZE_RELIEF * bite * plenty
                queue = self.ASSIZE_MOOD * bite * (1.0 - plenty)
                s.assize_mood = min(s.assize_mood, relief - queue) \
                    if s.assize_mood else relief - queue
            for s in self.world.settlements.values():
                # A shelf empties from both ends: everyone wants more of it at
                # that price, and the back door is open to anyone who will pay
                # what it is really worth.
                taken = s.market.take(key, self._assize_drain(s, key, bite))
                econ.smuggled += (taken * self.SMUGGLE_SHARE
                                  * (s.market.fundamental(key) - cap))
            if self.day % 30 == 0:
                msgs.append(self.note(
                    f"The assize holds {good(key).name} at {cap:,.1f}c, which is "
                    f"{bite * 100:.0f}% under what it is worth. The shelves are "
                    f"emptying and some of it is going out the back door."))
        return msgs

    #: Which institution opens which lever. A tech tree that only multiplies
    #: what you were already doing describes your town; one that decides what
    #: you may do in it is a tree.
    OPENS = {
        "mint": ("coinage", "You have no coinage of your own -- you are using "
                            "somebody else's pennies, and a man cannot debase "
                            "another man's coin. `research coinage`."),
        "decree": ("assize_of_bread", "There is no assize here: no standard "
                                      "loaf, no legal maximum and no court to "
                                      "hear a complaint about either. "
                                      "`research assize_of_bread`."),
        "ally": ("chancery", "You have no chancery -- no clerks, no seal and "
                             "no copy of anything you have ever sent. Nobody "
                             "swears to a house that cannot write. "
                             "`research chancery`."),
    }

    def opened(self, lever: str) -> str:
        """'' if the institution stands, else why it does not."""
        want, why = self.OPENS.get(lever, ("", ""))
        if not want or self.progress.knows(want):
            return ""
        return why

    def mint(self, coin: float) -> str:
        """Strike more pennies out of the same silver.

        MV = PY. More pennies is not more bread, and everybody finds that out
        -- but not today, and the gap between today and finding out is the
        entire reason anybody has ever done this.
        """
        shut = self.opened("mint")
        if shut:
            return shut
        coin = max(0.0, float(coin))
        if coin <= 0:
            econ = self.economy
            return (f"the mint has struck {econ.minted:,.0f}c so far; prices "
                    f"stand at {econ.price_level * 100:.0f} of what they were")
        if coin > C.MINT_LIMIT:
            return f"the mint cannot strike more than {C.MINT_LIMIT:,.0f}c at once"
        self.treasury += coin
        self.economy.strike(coin, self.net_worth())
        self.kin.did("just", -0.25)
        for s in self.world.settlements.values():
            s.popularity = max(0.0, s.popularity
                               - self.MINT_MOOD * coin / C.MINT_LIMIT)
        want = self.economy.money / MONEY_BASE
        return self.note(
            f"{coin:,.0f}c struck. The coin in the march stands at "
            f"{self.economy.money:,.0f}c, so prices are bound for "
            f"{want * 100:.0f} of what they were, and the town can already "
            f"feel it.", MOMENTOUS)

    def decree(self, key: str, price: float) -> str:
        """The assize: a legal maximum on what a good may be sold for.

        The first thing a ceiling teaches is that one above the market price
        does nothing whatever, and the second is what one below it does.
        """
        shut = self.opened("decree")
        if shut:
            return shut
        # A chartered market is theirs to price. This is the privilege
        # actually holding rather than being described as holding: you gave
        # away the right, and here is where you find you no longer have it.
        if self.estates.granted("charter") and price > 0:
            return ("you chartered the market: prices are the guilds' to set "
                    "while it stands. `estates revoke charter` first, and they "
                    "will remember that you did")
        spec = good(key)
        home = self.home()
        worth = home.market.fundamental(key)
        if price <= 0:
            self.economy.set_cap(key, 0.0)
            for s in self.world.settlements.values():
                s.market.caps.pop(key, None)
            return f"the assize on {spec.name} is lifted; it finds its own price"
        self.economy.set_cap(key, float(price))
        for s in self.world.settlements.values():
            s.market.caps[key] = float(price)
        if price >= worth:
            return (f"{spec.name} is held at {price:,.1f}c, which is above the "
                    f"{worth:,.1f}c it fetches. A ceiling over the market is a "
                    f"proclamation and nothing else.")
        self.kin.did("just", 0.10)
        short = 100.0 * (1.0 - price / worth)
        return self.note(
            f"{spec.name} is held at {price:,.1f}c against the {worth:,.1f}c it "
            f"is worth -- {short:.0f}% under. Cheap for whoever gets to the "
            f"front, and {self._assize_days(key, price)} before the shelves "
            f"are bare.", MOMENTOUS)

    def _assize_drain(self, s, key: str, bite: float) -> float:
        """How much of it goes today that would not have gone at its own price.

        Excess demand is a *quantity*, not a fraction of the shelf. This used
        to take 3.5% of stock a day, which is not a shortage, it is a decay:
        a proportional drain simply settles the shelf at forty days' output
        and any town that bakes its own bread never queues at all. Measured on
        a grown save, a fully biting cap cost 2% of the granary over sixty
        days and the queue the lever exists to create never once formed --
        which made the assize a standing +12 to the mood for nothing, the same
        free lunch the mint was.

        What a ceiling actually does is make more people want the good than
        there is of it at that price, and "more people" is measured against
        how much the town gets through in a day. Plus the back door, which is
        a small share of the shelf and the reason smugglers exist.
        """
        use = (max(0.0, s.report.eaten.get(key, 0.0))
               + max(0.0, s.report.consumed.get(key, 0.0)))
        return bite * (use * self.ASSIZE_DRAIN
                       + s.market.stock.get(key, 0.0) * self.ASSIZE_LEAK)

    def _assize_days(self, key: str, price: float) -> str:
        """How long the goodwill lasts, which is the only thing worth knowing.

        A price control is a transfer out of a granary, so its whole life is
        however much is in the granary. Saying so at the moment of the decree
        is the difference between a decision and an ambush -- and for a good
        that is eaten every day, the honest answer is usually "a fortnight".
        """
        home = self.home()
        stock = home.market.stock.get(key, 0.0)
        # Both ways it leaves: eaten off the ration, and used up by the sheds.
        # Missing the first of those made a forecast for bread that ignored
        # the town eating the bread.
        gone = (max(0.0, home.report.eaten.get(key, 0.0))
                + max(0.0, home.report.consumed.get(key, 0.0)))
        worth = home.market.fundamental(key)
        bite = max(0.0, 1.0 - price / worth) if worth > 0 else 0.0
        made = max(0.0, home.report.produced.get(key, 0.0))
        net = gone - made + self._assize_drain(home, key, bite)
        if net <= 0.01:
            return "no sign of running out on today's trade"
        days = stock / net
        if days >= 90:
            return "a season or more"
        return f"about {days:.0f} days"

    # ------------------------------------------------------------ the league
    def _league_day(self) -> List[str]:
        """The turn of the year, and the table kept up to date inside it."""
        msgs: List[str] = []
        season = self.league.season
        year = self.year
        if not season.opened or season.year != year:
            msgs += self._open_season(year)
            season = self.league.season
        self._keep_the_table()
        return msgs

    def _open_season(self, year: int) -> List[str]:
        """Close last year's book, publish this year's, and hold the draft.

        Everything a league does at the turn of a year happens here: the table
        is frozen and remembered, the lords say who they mean to move on, and
        the men looking for a lord are set out in reverse order of finish.
        """
        msgs: List[str] = []
        old = self.league.season
        if old.opened and old.records:
            table = old.table()
            first = table[0]
            self.league.past.append({
                "year": old.year, "first": first.name or first.key,
                "table": [r.to_dict() for r in table]})
            del self.league.past[:-24]
            mine = old.records.get(PLAYER)
            if mine is not None:
                where = old.place(PLAYER)
                msgs.append(self.note(
                    f"*** The {old.year} season closes. {first.name or first.key} "
                    f"stands first of the march; you stand {_ordinal(where)} of "
                    f"{len(table)} on {mine.line()}. ***", MOMENTOUS))
                if mine.won and self.league.mark("a season's fields won",
                                                 mine.won, "you", old.year):
                    msgs.append(self.note(f"{mine.won} fields in a year is the "
                                          f"most anybody has managed."))
            order = [r.key for r in reversed(table)]
        else:
            # No table to reverse in the first spring, so it is drawn for.
            # Handing the player first pick of the first class would be a
            # head start the whole device exists to prevent.
            order = [PLAYER] + list(self.world.towns)
            self.league.rng.shuffle(order)
        season = lg.Season(year=year, opened=True, order=order)
        # The schedule. A lord who has been quietly building ambition all
        # winter says so in the spring, and you get to hear it.
        for key, t in self.world.towns.items():
            if t.mine:
                continue
            target = self._intent_of(t)
            if target:
                season.fixtures.append(lg.Fixture(who=key, target=target,
                                                  declared=self.day))
        season.prospects = lg.draft_class(self.league.rng, year)
        self.league.season = season
        self._keep_the_table()
        msgs.append(self.note(
            f"*** The {year} season opens. {len(season.fixtures)} lords have "
            f"said where they are going, and {len(season.prospects)} men are "
            f"looking for one. `season` · `draft` ***", MOMENTOUS))
        msgs += self._run_draft()
        return msgs

    def _intent_of(self, town) -> str:
        """Who a lord means to move on, given what he wants and who is near.

        The same reading the war engine makes when the hostility finally tips;
        making it early and saying it out loud is the whole schedule.
        """
        if town.truce_days > 0:
            return ""
        mine = self._nearest_of_mine(town.key)
        # Only a lord who has actually taken against you says he is coming for
        # you. Reading a flat nought as "hostility is at least ambition" put
        # every lord on the march down as marching on your gate in the first
        # spring, which is a schedule that tells you nothing.
        if mine and town.hostility >= max(35.0, town.ambition):
            return mine
        near = [k for k in self.world.towns
                if k != town.key and not self.world.towns[k].mine]
        if not near:
            return mine or ""
        near.sort(key=lambda k: self.world.distance(town.key, k))
        return near[0]

    def _keep_the_table(self) -> None:
        """The standings, recomputed from what is actually true today."""
        season = self.league.season
        vassals = set(self.world.vassals())
        mine = season.record(PLAYER)
        mine.name, mine.lord = "you", self.lord.name
        mine.towns = len(self.world.settlements) + len(vassals)
        mine.worth = self.net_worth()
        mine.muster = float(self.soldiers)
        for key, t in self.world.towns.items():
            r = season.record(key)
            r.name, r.lord = t.name, t.lord
            if t.mine:
                r.towns = 0
                continue
            r.towns = 1 + sum(1 for o in self.world.towns.values()
                              if o.owner == key)
            r.worth = 1000.0 * t.prosperity * t.wealth
            r.muster = t.muster * 60.0

    def scored(self, who: str, *, won: bool) -> None:
        """A field carried or lost, for the table."""
        r = self.league.season.record(who)
        if won:
            r.won += 1
        else:
            r.lost += 1

    def took_town(self, who: str, lost_by: str = "") -> None:
        r = self.league.season.record(who)
        r.taken += 1
        if lost_by:
            self.league.season.record(lost_by).given += 1

    # ------------------------------------------------------------- the draft
    def _run_draft(self) -> List[str]:
        """Reverse order of finish, and everybody ahead of you picks at once.

        The player's turn stops the clock; everyone else takes the best man
        left the moment it reaches them. Finishing last is worth something,
        which is the entire point and the reason a league has one.
        """
        msgs: List[str] = []
        season = self.league.season
        while season.picking < len(season.order):
            who = season.order[season.picking]
            if who == PLAYER:
                left = season.undrafted()
                if left:
                    msgs.append(f"You are on the clock: {len(left)} men to "
                                f"choose from. `draft` shows them, "
                                f"`draft <name>` takes one.")
                    return msgs
                season.picking += 1
                continue
            left = season.undrafted()
            if not left:
                break
            best = max(left, key=lambda p: p.grade)
            best.taken_by = who
            name = self.world.node_name(who)
            msgs.append(f"{name} takes {best.name} ({best.skill} {best.grade}).")
            season.picking += 1
        return msgs

    def draft(self, name: str = "") -> str:
        """Take one of the men looking for a lord, if it is your turn."""
        season = self.league.season
        if not season.prospects:
            return "nobody is looking for a lord this year"
        if season.on_the_clock() != PLAYER:
            who = season.on_the_clock()
            if not who:
                return "the draft is done for this year"
            return (f"{self.world.node_name(who)} is on the clock, not you")
        left = season.undrafted()
        if not left:
            return "there is nobody left to take"
        if not name:
            return f"{len(left)} to choose from -- `draft <name>` takes one"
        want = name.strip().lower()
        pick = next((p for p in left if p.name.lower().startswith(want)), None)
        if pick is None:
            pick = next((p for p in left if want in p.name.lower()), None)
        if pick is None:
            return f"nobody called {name!r} among them"
        pick.taken_by = PLAYER
        season.picking += 1
        person = self.kin.add(pick.name, "f" if pick.name.split()[0][-1] in "aey"
                              else "m", born=self.day - 26 * C.DAYS_PER_YEAR)
        person.sworn = True
        person.xp[pick.skill] = lg.STEEP_FOR[pick.grade]
        said = self.note(f"{pick.name} is sworn to you -- {pick.story}, and it "
                         f"shows: {pick.skill} {pick.grade}. `post` gives him "
                         f"something to do.")
        rest = self._run_draft()
        return "\n".join([said] + rest)

    def muster_cap(self) -> float:
        """How many soldiers your holdings keep at the ordinary price."""
        return lg.cap_for(len(self.world.settlements) + len(self.world.vassals()))

    def muster_cost(self) -> float:
        """The multiplier on what your soldiers cost, for being too many."""
        return lg.overage(float(self.soldiers),
                          len(self.world.settlements) + len(self.world.vassals()))

    def relics_held(self, owner: str = "player") -> int:
        return sum(1 for sh in self.world.shrines.values() if sh.holder == owner)

    def relic_income(self) -> float:
        """Pilgrims' offerings. A cathedral is where they are meant to rest."""
        held = self.relics_held()
        if not held:
            return 0.0
        housed = any(s.count("cathedral") for s in self.world.settlements.values())
        return C.RELIC_COIN * held * (1.6 if housed else 1.0)

    RAID_PATIENCE = 12           # days a host will work a country before going home

    def raid(self, uid: int) -> str:
        """Order a host of yours to burn the country instead of the walls."""
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != "player":
            return "that host is not yours to order"
        if a.state not in (BESIEGING, GARRISON, RAIDING):
            return f"{a.name} is on the road; it must arrive first"
        if self.world.is_friendly(a.at):
            return f"{a.name} stands in friendly country -- there is nothing to burn"
        a.state = RAIDING
        a.siege_days = 0
        return f"{a.name} looses on the country around {self.world.node_name(a.at)}"

    def _raid(self, a: Army) -> List[str]:
        a.siege_days += 1
        if a.siege_days > self.RAID_PATIENCE:
            a.siege_days = 0
            where = self.world.node_name(a.at)
            if a.owner == "player":
                self.march(a.uid, a.home)
                return [f"{a.name} has stripped the country round {where} and turns for home"]
            if a in self.armies:
                self.armies.remove(a)
            return [f"The raiders around {where} ride off with what they could carry"]
        if a.at in self.world.towns:
            return self._raid_town(a, self.world.towns[a.at])
        s = self.world.settlements.get(a.at)
        return self._raid_settlement(a, s) if s else []

    def _raid_settlement(self, a: Army, s: Settlement) -> List[str]:
        """Somebody burning *your* country. The walls do not enter into it."""
        msgs: List[str] = []
        s.raided = True
        raiders = Side(a.units)
        garrison = Side(s.units, attack_mult=self.progress.mult("attack"),
                        defense_mult=self.progress.mult("defense"))
        # Everything a settlement has outside its walls is what is at risk.
        outside = sum(b.spec.jobs for b in s.buildings
                      if b.complete and b.spec.terrain in ("fertile", "forest",
                                                           "hills", "clay", "coast"))
        worked, _hurt, lost, lines = raid_day(
            raiders, garrison, out_of_doors=6.0 * max(1.0, outside), rng=self.rng)
        s.raid_pressure = max(s.raid_pressure, worked)
        a.units = {k: v for k, v in raiders.units.items() if v >= 0.5}
        s.units = {k: v for k, v in garrison.units.items() if v >= 0.5}
        # Stores carried off, people driven off the land.
        for k in list(s.market.stock):
            s.market.take(k, s.market.stock[k] * C.RAID_LOOT * worked)
        s.population = max(4.0, s.population * (1.0 - C.RAID_FLIGHT * worked))
        # Raiders carry torches. This is the cheapest way there is to hurt a
        # town you cannot take, and the reason a stone town sleeps better.
        # Burning your fields is a reason anybody on the march will accept.
        self.court.give_ground(a.owner, "raided", self.day)
        if self.rng.random() < C.RAID_TORCH * worked:
            msgs.extend(s.kindle(self.rng, 1 + int(2 * worked)))
        if self.day % 4 == 0:
            msgs.append(f"{s.name} is being raided: {lines[0]}")
        if lost:
            msgs.append(f"Sortie from {s.name}: "
                        f"{describe({k: round(v) for k, v in lost.items()})} cut down")
        return msgs

    def _raid_town(self, a: Army, town) -> List[str]:
        """You, burning somebody else's country. Loot comes home as coin."""
        msgs: List[str] = []
        if a.owner == "player":
            self.kin.did("merciful", -0.05)
        raiders = Side(a.units,
                       attack_mult=(self.progress.mult("attack")
                                    * self.kin.mult("attack", a.uid))
                       if a.owner == "player" else 1.0)
        garrison = Side(dict(town.garrison))
        worked, _hurt, lost, lines = raid_day(
            raiders, garrison, out_of_doors=90.0 * town.prosperity, rng=self.rng)
        a.units = {k: v for k, v in raiders.units.items() if v >= 0.5}
        town.garrison = {k: v for k, v in garrison.units.items() if v >= 0.5}
        # A raid does not take a town; it makes the town poorer and the lord
        # angrier, which is the point of it.
        town.prosperity = max(0.35, town.prosperity - C.RAID_PROSPERITY * worked)
        town.hostility = min(C.HOSTILITY_WAR, town.hostility + 6.0 * worked)
        if a.owner == "player":
            loot = C.RAID_LOOT_COIN * worked * town.prosperity * town.wealth
            self.treasury += loot
            self._plunder += loot
            if self.day % 4 == 0:
                msgs.append(f"{a.name} strips the country round {town.name}: "
                            f"{loot:,.0f}c and {lines[0]}")
        if lost:
            msgs.append(f"{town.name}'s garrison sorties: "
                        f"{describe({k: round(v) for k, v in lost.items()})} lost raiding")
        return msgs

    def _siege_town(self, a: Army, town) -> List[str]:
        """Anyone besieging a foreign town -- you, or one lord besieging another."""
        msgs: List[str] = []
        player = a.owner == "player"
        besieger = Side(a.units,
                        attack_mult=(self.progress.mult("attack")
                                     * self.progress.mult("siege")
                                     * self.kin.mult("siege")
                                     * self.kin.mult("attack", a.uid)
                                     * manly.attack_bonus(self.lord, a.uid))
                        if player else 1.0,
                        defense_mult=self.progress.mult("defense") if player else 1.0)
        # Your own hosts standing in a sworn town fight for it.
        stationed = [x for x in self.armies
                     if x is not a and x.owner == "player" and x.at == town.key
                     and town.mine]
        defenders = dict(town.garrison)
        for x in stationed:
            for k, n in x.units.items():
                defenders[k] = defenders.get(k, 0.0) + n
        # An Ox on his own parapet is a different proposition from a
        # Magpie on his. What he takes, he keeps.
        holder = Side(defenders, battlement=8.0 * (
            1.0 if town.mine else lordly.sort_of(town.key).holds))
        works = town.works()
        if not player:
            a.siege.plan = choose(works, siege_power=a.siege_power,
                                  engineers=a.units.get("engineer", 0.0),
                                  host=a.size, garrison=sum(town.garrison.values()),
                                  wall=town.wall_hp, wall_max=town.wall_max,
                                  patient=a.siege_days > 8)
        wall, _la, _ld, lines = siege_day(besieger, holder, town.wall_hp, self.rng,
                                          town.name, wall_max=town.wall_max,
                                          works=works, state=a.siege,
                                          faith=town.faith())
        town.wall_hp = wall
        if player:
            town.hostility = C.HOSTILITY_WAR
        if self.day % 5 == 0 and lines and (player or town.mine):
            msgs.append(f"{a.name}: {lines[0]}")
        if storms_now(a.siege.plan, wall, holder.alive()):
            res = fight(besieger, holder, rng=self.rng, place=town.name)
            msgs.append(f"ASSAULT ON {town.name.upper()}: the {res.winner} holds "
                        f"the ground after {res.rounds} rounds")
            msgs.append(self._box_score(f"{a.name} storms {town.name}", res,
                                        a.owner, town.key))
            self.scored(a.owner, won=res.winner == "attacker")
            self.scored(town.key, won=res.winner != "attacker")
            a.siege_days = 0
            if res.winner == "attacker":
                self.took_town(a.owner, town.key)
                if player:
                    self.kin.did("merciful", -0.35)
                    self.kin.teach("engineering", 14.0, self.day, post="master")
                    self.kin.teach("tactics", 10.0, self.day, post="captain",
                                   target=str(a.uid))
                msgs.append(self._take_town(town, a))
                if not player:
                    line = lordly.says(a.owner, "takes", self.voice)
                    if line:
                        msgs.append(f'    {self.world.node_name(a.owner)}: '
                                    f'"{line}"')
                a.prune()
                return msgs        # the garrison is the victor's now, not the survivors'
            elif player:
                a.state = RETURNING
                msgs.append(f"{a.name} is thrown back from {town.name}")
                # He was standing where the arrows were. Sometimes that tells.
                if self.lord.riding == a.uid:
                    msgs += self._lord_fell()
                self.march(a.uid, a.home)
            else:
                a.state = RETURNING
                if a.owner in self.world.towns:
                    # A letter is easier to sign than to keep. Every host of
                    # theirs you break takes a bite out of the reason it was
                    # written, which is the one way out that is not money.
                    self.court.write(a.owner, "beaten", 22.0, self.day)
                    line = lordly.says(a.owner, "beaten", self.voice)
                    if line:
                        msgs.append(f'    {self.world.towns[a.owner].lord}: '
                                    f'"{line}"')
                self.march(a.uid, a.home)
            town.wall_hp = max(town.wall_hp, town.wall_max * 0.15)
        a.prune()
        # Casualties fall on the stationed hosts first, then on the town levy.
        survivors = dict(holder.units)
        for x in stationed:
            for k in list(x.units):
                share = min(x.units[k], survivors.get(k, 0.0))
                survivors[k] = survivors.get(k, 0.0) - share
                x.units[k] = share
            x.prune()
        town.garrison = {k: v for k, v in survivors.items() if v >= 0.5}
        return msgs

    def _siege_settlement(self, a: Army, s: Settlement) -> List[str]:
        msgs: List[str] = []
        s.besieged = True
        besieger = Side(a.units)
        at_home = self.lord.at_home and self.lord.seat in ("", s.name)
        # The wall as it was drawn, not as it was bought. A garrison is a
        # number of men and a wall is a number of yards, so what decides
        # whether the wall-walk is held is men to the yard -- which is the
        # whole price of enclosing more ground than you can man, and the
        # reason a small tight castle is an answer rather than a poor one.
        castle = s.plan()
        reading = keeps.read(castle)
        holder = Side(s.units, attack_mult=self.progress.mult("attack"),
                      defense_mult=self.progress.mult("defense"),
                      battlement=6.0 + s.effect("battlement")
                      + (manly.HOME_DEFENCE if at_home else 0.0)
                      + self.kin.bonus("defence")
                      + keeps.manning(reading.density(sum(s.units.values()))))
        works = Works.of([b.key for b in s.buildings
                          if b.complete and b.spec.terrain == "rampart"])
        # Counts come off the shopping list (an oil pot is over the gate
        # wherever the gate is); shape comes off the ground.
        drawn = Works.read(castle, reading)
        works.naked, works.depth = drawn.naked, drawn.depth
        if a.owner != "player":
            a.siege.plan = choose(works, siege_power=a.siege_power,
                                  engineers=a.units.get("engineer", 0.0),
                                  host=a.size, garrison=sum(s.units.values()),
                                  wall=s.wall_hp, wall_max=s.wall_max(self.progress),
                                  patient=a.siege_days > 8)
        wall, _la, _ld, lines = siege_day(besieger, holder, s.wall_hp, self.rng, s.name,
                                          wall_max=s.wall_max(self.progress),
                                          works=works, state=a.siege,
                                          have_pitch=s.market.stock.get("charcoal", 0) >= 5,
                                          faith=s.coverage("faith_reach"))
        if a.siege.plan == INVEST:
            s.blockaded = True
            self.court.give_ground(a.owner, "blockade", self.day)
        s.wall_hp = wall
        if self.day % 5 == 0 and lines:
            msgs.append(f"{s.name} under siege: {lines[0]}")
        s.units = {k: v for k, v in holder.units.items() if v >= 0.5}
        a.units = {k: v for k, v in besieger.units.items() if v >= 0.5}
        if storms_now(a.siege.plan, wall, holder.alive()):
            res = fight(besieger, holder, rng=self.rng, place=s.name)
            msgs.append(self._box_score(f"{a.name} storms {s.name}", res,
                                        a.owner, PLAYER))
            self.scored(a.owner, won=res.winner == "attacker")
            self.scored(PLAYER, won=res.winner != "attacker")
            if res.winner == "attacker":
                self.took_town(a.owner, PLAYER)
            msgs.append(f"ASSAULT ON {s.name.upper()}: the {res.winner} holds the "
                        f"ground after {res.rounds} rounds")
            # Men who get over a wall set light to what is behind it, whether
            # or not they end up holding the ground.
            msgs.extend(s.kindle(self.rng, self.rng.randrange(2, 6)))
            s.units = {k: v for k, v in holder.units.items() if v >= 0.5}
            a.units = {k: v for k, v in besieger.units.items() if v >= 0.5}
            if res.winner == "attacker":
                msgs.append(self._sack(s, a))
            else:
                msgs.append(f"The host is broken beneath the walls of {s.name}")
                if a in self.armies:
                    self.armies.remove(a)
                if a.home in self.world.towns:
                    self.world.towns[a.home].hostility = 25.0
            s.wall_hp = max(s.wall_hp, s.wall_max(self.progress) * 0.10)
        return msgs

    def _sack(self, s: Settlement, a: Army) -> str:
        """A storming is a catastrophe, not a trapdoor.

        The keep is thrown down and the town gutted, but so long as you hold
        ground anywhere you are still in the game -- which is the whole argument
        for founding a second settlement before you need one.
        """
        keep = next((b for b in s.buildings if b.key == "keep"), None)
        # Relics go where the strongbox goes.
        for sh in self.world.shrines.values():
            if sh.holder == "player":
                sh.holder = a.owner
        loot = 0.0
        share = 0.60 if keep else 0.45
        for k in ALL_KEYS:
            taken = s.market.stock[k] * share
            s.market.stock[k] -= taken
            loot += taken * s.market.bid(k)
        s.population *= 0.65 if keep else 0.75
        s.popularity = max(0.0, s.popularity - (35.0 if keep else 25.0))
        s.units = {}
        a.state = RETURNING
        self.march(a.uid, a.home)
        if not keep:
            return f"{s.name} is sacked -- {loot:,.0f}c of stores carried off"
        for b in list(s.buildings):
            if b.spec.terrain == "rampart":
                s.demolish(b.uid)
        s.wall_hp = 0.0
        return self.note(
            f"*** {s.name.upper()} IS STORMED. The keep is thrown down and "
            f"{loot:,.0f}c carried off. Raise another, or hold what is left "
            f"of the march from somewhere else. ***", MOMENTOUS)

    def _box_score(self, title: str, res, attacker: str, defender: str) -> str:
        """What a battle actually cost, both sides, in one line.

        The log said who held the ground and nothing else -- which is the
        result without the game. A box score is the least a competition owes
        anybody who was in it.
        """
        # Every battle in the game passes through here to be reported, which
        # makes it the one honest place to count them. Counting at each of the
        # four call sites is how a tally ends up missing the fifth.
        won = getattr(res, "winner", "")
        if attacker == PLAYER and won == "attacker":
            self._battles_won += 1
        elif defender == PLAYER and won == "defender":
            self._battles_won += 1
        lost = lambda d: sum(d.values())          # noqa: E731 - a local shorthand
        att = self.world.node_name(attacker) if attacker != PLAYER else "yours"
        deff = self.world.node_name(defender) if defender != PLAYER else "yours"
        return (f"    box  {title} · {res.rounds} rounds · "
                f"{att} lost {lost(res.attacker_losses):.0f}, "
                f"{deff} lost {lost(res.defender_losses):.0f}"
                + (f", wall {res.wall_damage:,.0f}" if res.wall_damage else ""))

    def _take_town(self, town, a: Army) -> str:
        was_mine = town.mine
        # Tallies for the feats. Kept here, at the moment a town changes
        # hands, because that is the only place that knows which way it went.
        if a.owner == "player":
            self._stormed += 1
        elif was_mine:
            self._towns_lost += 1
        # Whatever bones that lord had lifted are in his minster, and his
        # minster has just changed hands.
        taker = "player" if a.owner == "player" else a.owner
        for sh in self.world.shrines.values():
            if sh.holder == town.key:
                sh.holder = taker
        town.owner = "player" if a.owner == "player" else a.owner
        town.hostility = 0.0
        town.ambition = 0.0
        # A fifth of the host stays behind as a garrison. A town taken and then
        # walked away from is a town somebody else takes next month.
        town.garrison = {}
        for k, n in list(a.units.items()):
            if UNITS[k].unit_class in ("siege",):
                continue
            left = n * 0.3
            if left >= 1:
                a.units[k] = n - left
                town.garrison[k] = left
        town.wall_hp = town.wall_max * 0.45
        town.prosperity = max(0.5, town.prosperity - 0.25)
        a.state = GARRISON
        if a.owner == "player":
            # Aggressive expansion. The immediate shock is what it always was;
            # what is new is that the offence is written down with a date on
            # it, so it decays where a player can watch it decay -- and so
            # that it adds up across the march instead of only ever pointing
            # at you one lord at a time. Three towns is a different decision
            # from one, and this is the mechanism that says so.
            #
            # A town taken in a war the march accepted the reason for offends
            # less than one simply seized -- which is the second half of what
            # a marriage into that house is for, and the reason a claim is
            # worth a dowry years before anybody dies.
            just = self.day - self.court.justified.get(town.key, -99999)
            lawful = 0.6 if just < self.WAR_MEMORY else 1.0
            # And a town that revolted and was retaken is not a second
            # conquest. The march priced you as the man who took Caldmoor the
            # first time; charging it again every time the garrison wavered
            # ran one lord to two hundred of ill-will and a thousand days of
            # decay, which is not a decision, it is a spiral.
            again = town.key in self.court.taken
            self.court.taken.add(town.key)
            lawful *= 0.3 if again else 1.0
            for key, other in self.world.towns.items():
                if other.mine:
                    continue
                other.hostility = min(C.HOSTILITY_WAR, other.hostility + 18.0)
                near = self.world.distance(key, town.key)
                # Distances on this march run 30 to 190. A neighbour takes
                # it hardest; a lord four days' ride away has heard about it
                # and has other things on his mind.
                close = max(0.55, min(1.4, 90.0 / max(30.0, near)))
                self.court.write(key, "took_town",
                                 -34.0 * lawful * close
                                 * lordly.sort_of(key).temper,
                                 self.day)
            return self.note(
                f"*** {town.name} bends the knee. Its tolls are yours, and "
                f"{town.tribute():.0f}c a day with them. ***", MOMENTOUS)
        liege = self.world.node_name(a.owner)
        a.state = RETURNING
        self.march(a.uid, a.home)
        if was_mine:
            return self.note(f"*** {town.name} IS TAKEN FROM YOU by {liege}. "
                             f"Its tribute is theirs now. ***", MOMENTOUS)
        return f"{town.name} has fallen to {liege}"

    def _lords_and_hosts(self) -> List[str]:
        """The other lords take their turn.

        They grow their towns, they take offence at you at their own rates, and
        -- the part that makes the map a board rather than a backdrop -- they
        take offence at each other. A town that swallows its neighbours becomes
        a problem you did not create and will have to solve.
        """
        msgs: List[str] = []
        if not self.world.settlements:
            return msgs
        msgs += self._chancery_day()
        pressure = self.war_pressure()
        wealth_factor = min(2.5, self.net_worth() / 40000.0)
        besieged = {a.at for a in self.armies if a.state == BESIEGING}
        rival_wars = sum(1 for a in self.armies
                         if a.owner != "player" and a.bound_for in self.world.towns)

        for key, t in self.world.towns.items():
            t.grow(self.rng, besieged=key in besieged)
            if t.truce_days > 0:
                t.truce_days -= 1
            if t.mine:
                revolt = self._revolt(key, t)
                if revolt:
                    msgs.append(revolt)
                continue
            if any(a.owner == key and not a.errand for a in self.armies):
                continue      # its host is already out
            # A party of spearmen away at a shrine is not "his host": counting
            # it as one made relic-hunting a pressure valve on the whole war,
            # so tuning how often the lords went for bones quietly retuned how
            # often they declared on anybody.

            if key in self.court.allies:
                continue      # a man does not march on somebody he has sworn to
            # -- offence taken at you ---------------------------------------
            if t.truce_days <= 0:
                t.hostility += (C.HOSTILITY_DRIFT * pressure * t.temper
                                * (0.5 + wealth_factor)
                                * (0.6 + 0.8 * self.rng.random()))
                t.hostility = max(0.0, t.hostility - t.favour * 0.02
                                  - self.kin.bonus("cooling"))
            if t.hostility >= C.HOSTILITY_WAR:
                msgs.append(self._send_host(t, pressure, self._nearest_of_mine(key)))
                continue

            # -- offence taken at each other --------------------------------
            t.ambition += (C.AMBITION_DRIFT * t.aggression * pressure
                           * (0.5 + self.rng.random()))
            if t.ambition < C.HOSTILITY_WAR or rival_wars >= self.MAX_RIVAL_WARS:
                continue
            prey = self._prey_for(key)
            if prey is None:
                t.ambition = 60.0
                continue
            t.ambition = 0.0
            rival_wars += 1
            msgs.append(self._send_host(t, pressure, prey))
        return msgs

    # -------------------------------------------------------- the chancery
    #: How long an ally is given to answer a call before it counts as a no.
    CALL_DAYS = 12
    #: Chance a day that a foreign lord's line runs out. Over three years it
    #: is a thing that happens to about one house on the march.
    SUCCESSION_ODDS = 0.00035

    def _chancery_day(self) -> List[str]:
        """The letters. Who is talking to whom, and what they have agreed.

        Four things, in the order a chancellor would take them: the book is
        swept of what has worn out, the standing goodwill is re-read off it,
        the names on the letter are counted, and anybody waiting on an answer
        is told that no answer is an answer.
        """
        msgs: List[str] = []
        day = self.day
        c = self.court
        if day % 7 == 0:
            c.sweep(day)
        # Heralds: men whose whole trade is knowing who is angry with whom.
        # A grievance you can *name* is one you can still act on, so your own
        # grounds for war keep while theirs wear off at the usual rate.
        c.long_memory = self.progress.knows("heralds")
        # `favour` is not a number anybody sets any more. It is the sum of
        # what is in your favour, which is the only way a gift can be
        # forgotten -- and `wed` has claimed for a year that gifts are
        # forgotten while `favour` only ever went up.
        for key, t in self.world.towns.items():
            t.favour = c.goodwill(key, day)
            # And what his customs post charges, which is where the politics
            # stops being a screen and starts being money. See
            # World.toll_mood.
            t.regard = c.opinion(key, day)
            t.signed = key in c.coalition
            t.sworn_friend = key in c.allies
        # What the chancery's institutions actually do, applied once a day
        # where everything else about the march is. Each of these is a
        # mechanic rather than a percentage -- see tech.py on why that is the
        # difference between a tree that describes your town and one that
        # decides what you may do in it.
        self.world.safe_conduct = self.progress.knows("safe_conduct")
        msgs += self._drainage_day()
        msgs += self._coalition_day()
        msgs += self._alliance_day()
        msgs += self._succession_abroad()
        return msgs

    #: How fast a dyke turns fen into field, in slots a year. Slow on purpose:
    #: the drainage of the Fens and the Dutch polders took generations and the
    #: capital of whole cities, and a tech that converted a marsh overnight
    #: would make the wettest map the best one to start on.
    DRAIN_DAYS = 90

    def _drainage_day(self) -> List[str]:
        """Dykes, a cut and a wind-pump.

        The only tech in the tree that changes the *map*. Undrained fen is
        land you own and cannot work -- no building will stand on it -- which
        is exactly what made draining it worth a generation's money. One slot
        a quarter, and it is gone when it is gone.
        """
        if not self.progress.knows("drainage") or self.day % self.DRAIN_DAYS:
            return []
        out: List[str] = []
        for s in self.world.settlements.values():
            left = s.terrain.get("marsh", 0)
            if left <= 0:
                continue
            s.terrain["marsh"] = left - 1
            s.terrain["fertile"] = s.terrain.get("fertile", 0) + 1
            out.append(self.note(
                f"The cut at {s.name} is finished and the water is off "
                f"another field. {left - 1} of fen left."))
        return out

    def _coalition_day(self) -> List[str]:
        """When the lords stop quarrelling with each other and start writing.

        The signature of the thing this is borrowed from: conquest that is
        cheap once, dear twice and ruinous three times, not because any lord
        got stronger but because they started counting together. It is the
        game saying, in a way you can read in advance, that the third town is
        a different kind of decision from the first.
        """
        msgs: List[str] = []
        c, day = self.court, self.day
        theirs = [k for k, t in self.world.towns.items() if not t.mine]
        names = [k for k in c.signatories(theirs, day) if k not in c.allies]
        # Names come off as well as on. Without this a lord whose grievance
        # you had spent a year and a treasury cooling stayed on the letter
        # for as long as any three others were angry -- which made buying one
        # lord off pointless, and pointless is the one thing a lever must
        # never be.
        if c.coalition:
            still = [k for k in c.still_signed(day)
                     if k not in c.allies and not self.world.towns[k].mine]
            left = [k for k in c.coalition if k not in still]
            if len(still) < court.COALITION_NAMES:
                c.coalition = []
                c.coalition_day = -1
                msgs.append(self.note(
                    "The letter against you is not renewed. The march goes "
                    "back to quarrelling with itself.", MOMENTOUS))
            elif left:
                c.coalition = still
                msgs.append(self.note(
                    ", ".join(self.world.node_name(k) for k in left)
                    + " takes a name off the letter against you."))
        if len(names) >= court.COALITION_NAMES:
            new = [k for k in names if k not in c.coalition]
            if not c.coalition:
                c.coalition = names
                c.coalition_day = day
                msgs.append(self.note(
                    "*** The lords of the march have put their names to one "
                    "letter: " + ", ".join(self.world.node_name(k) for k in names)
                    + ". They will not treat with you one at a time while it "
                    "holds. ***", MOMENTOUS))
            elif new:
                c.coalition = sorted(set(c.coalition) | set(new))
                msgs.append(self.note(
                    ", ".join(self.world.node_name(k) for k in new)
                    + " adds a name to the letter against you.", MOMENTOUS))
        # A coalition marches together. When one of them is on the road for
        # you, the rest find their boots within the fortnight -- which is the
        # whole difference between eight quarrels and one war.
        if c.coalition and any(a.owner in c.coalition
                               and a.bound_for in self.world.settlements
                               for a in self.armies):
            for key in c.coalition:
                t = self.world.towns.get(key)
                if t is None or t.mine or t.truce_days > 0:
                    continue
                if any(a.owner == key and not a.errand for a in self.armies):
                    continue
                if c.rng.random() < 0.085:
                    msgs.append(self._send_host(t, self.war_pressure(),
                                                self._nearest_of_mine(key)))
        return msgs

    def _alliance_day(self) -> List[str]:
        """Friends, and the day you did not come.

        An ally who comes when you are attacked is an ally who calls when he
        is. Refusing is allowed and is meant to be: what it costs is that
        every other lord on the march now knows what your word is worth,
        which is a grudge that decays slower than anything else in the book.
        """
        msgs: List[str] = []
        c, day = self.court, self.day
        for key in list(c.allies):
            t = self.world.towns.get(key)
            if t is None or t.mine:
                c.allies.remove(key)
                continue
            if c.opinion(key, day) <= 0:
                c.allies.remove(key)
                c.write(key, "ally", -10.0, day)
                msgs.append(self.note(f"{t.lord} of {t.name} lets the "
                                      f"alliance lapse."))
        # Somebody marching on an ally is a call, and a call wants an answer.
        if c.called is None:
            for a in self.armies:
                if a.owner == "player" or a.bound_for not in c.allies:
                    continue
                who = a.bound_for
                c.called = (who, day)
                msgs.append(self.note(
                    f"*** {self.world.node_name(who)} calls you to the war. "
                    f"`call yes` sends what you have; `call no` does not, and "
                    f"the march will hear which. You have {self.CALL_DAYS} "
                    f"days. ***", MOMENTOUS))
                break
        elif day - c.called[1] > self.CALL_DAYS:
            # Saying nothing is saying no, and it has to go through the same
            # door as saying it: clearing `called` first and *then* asking
            # answer_call to act on it meant the clock ran out and absolutely
            # nothing happened -- no broken alliance, no grudge, no line in
            # the chronicle. A silence with no consequence is not a decision
            # the player was ever offered.
            msgs.append(self.answer_call(False))
        return msgs

    def answer_call(self, come: bool) -> str:
        """Yes or no to an ally who has called. No is a real option."""
        c = self.court
        who = c.called[0] if c.called else None
        if who is None:
            return "nobody has called you"
        c.called = None
        t = self.world.towns.get(who)
        name = self.world.node_name(who)
        if come:
            c.write(who, "came_when_called", 45.0, self.day)
            # Whoever is marching on them has now given you a reason to
            # march on him, which is the other half of what an ally is for.
            for a in self.armies:
                if a.bound_for == who and a.owner in self.world.towns:
                    c.give_ground(a.owner, "called", self.day)
            if t is not None:
                t.truce_days = max(t.truce_days, 120)
            return self.note(f"You answer {name}'s call. Whoever is at their "
                             f"gate is now your business too.", MOMENTOUS)
        if who in c.allies:
            c.allies.remove(who)
        c.write(who, "broke_word", -60.0, self.day)
        others = [k for k, x in self.world.towns.items() if not x.mine and k != who]
        c.write_all(others, "broke_word", -22.0, self.day)
        self.kin.did("open", -0.2)
        return self.note(f"You do not come when {name} calls. The alliance "
                         f"ends, and every lord on the march is told.",
                         MOMENTOUS)

    def ally(self, town_key: str) -> str:
        """Swear to come when they are attacked, and they to you."""
        t = self.world.towns.get(town_key)
        if t is None:
            return f"there is no {town_key!r} to treat with"
        if t.mine:
            return f"{t.name} is sworn to you already"
        shut = self.opened("ally")
        if shut:
            return shut
        c = self.court
        if town_key in c.allies:
            return f"you are allied with {t.name} already"
        view = c.opinion(town_key, self.day)
        if view < court.WARM:
            return (f"{t.lord} of {t.name} thinks of you as "
                    f"{court.temper(view)} ({view:+.0f}); he will not swear to "
                    f"anybody under {court.WARM:+.0f}. `court {town_key}` says "
                    f"what would move him.")
        c.allies.append(town_key)
        c.write(town_key, "ally", 30.0, self.day)
        t.truce_days = max(t.truce_days, 180)
        self.kin.teach("charm", 14.0, self.day, post="envoy")
        return self.note(f"{t.lord} of {t.name} is allied to you. He comes "
                         f"when you are attacked, and calls when he is.",
                         MOMENTOUS)

    def _succession_abroad(self) -> List[str]:
        """A house ends, and what it held has to go somewhere.

        The other reason to marry a daughter into Ostmark. It is rare and it
        is meant to be -- but it is the one way a town comes to you with
        nobody in the field, and it is the only thing in the game that makes
        a dowry look cheap in hindsight.
        """
        c = self.court
        for key, t in self.world.towns.items():
            if t.mine or c.rng.random() >= self.SUCCESSION_ODDS:
                continue
            if key not in c.claims:
                # Somebody else's cousin takes it. You hear about it and it
                # changes nothing, which is what most history is.
                t.prosperity = max(0.5, t.prosperity - 0.1)
                return [self.note(f"{t.lord} of {t.name} is dead. A cousin "
                                  f"takes the hall, and the market with it.")]
            t.owner = "player"
            t.hostility = 0.0
            t.ambition = 0.0
            c.claims.pop(key, None)
            others = [k for k, x in self.world.towns.items()
                      if not x.mine and k != key]
            c.write_all(others, "inherited", -16.0, self.day)
            return [self.note(
                f"*** {t.lord} of {t.name} is dead without an heir of his "
                f"body, and your house has the claim. {t.name} comes to you "
                f"with nobody in the field. ***", MOMENTOUS)]
        return []

    def _revolt(self, key: str, town) -> str:
        """A town holds its oath while the hand that took it is still visible.

        Conquest is not a purchase: a lord who takes five towns and then lets
        his host melt away will watch them leave one at a time.
        """
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self._muster_enemy(town, self.war_pressure(),
                                                  spread=False))
        if mine >= 0.45 * theirs:
            return ""
        if self.rng.random() > C.REVOLT_CHANCE:
            return ""
        town.owner = ""
        town.hostility = 65.0
        town.garrison = dict(town.target_garrison())
        return self.note(f"*** {town.name} throws off its oath -- you have "
                         f"nothing left nearby to hold it with. ***", MOMENTOUS)

    def _nearest_of_mine(self, key: str) -> str:
        return min(self.world.settlements,
                   key=lambda k: self.world.distance(key, k))

    def _prey_for(self, key: str) -> Optional[str]:
        """A weaker neighbour worth marching on -- your vassals included."""
        me = self.world.towns[key]
        mine_strength = host_strength(self._muster_enemy(me, self.war_pressure(),
                                                         spread=False))
        best, best_score = None, 0.0
        for other_key, other in self.world.towns.items():
            if other_key == key or other.owner == key:
                continue
            if self.world.liege_of(other_key) == me.owner and me.owner:
                continue                      # not your liege-brother
            defence = host_strength(other.garrison) + other.wall_hp / 12.0
            if defence >= mine_strength * 0.8:
                continue
            score = (mine_strength - defence) / max(
                40.0, self.world.distance(key, other_key))
            if score > best_score:
                best, best_score = other_key, score
        return best

    def _send_host(self, town, pressure: float, target: str) -> str:
        host = self._muster_enemy(town, pressure)
        a = Army(uid=self.next_army_uid, name=f"{town.lord}'s host", owner=town.key,
                 units=host, at=town.key, home=town.key)
        self.next_army_uid += 1
        self.armies.append(a)
        a.bound_for = target
        a.days_left = max(1.0, self.world.distance(town.key, target)
                          / max(host_speed(host), 1.0))
        a.state = MARCHING
        town.hostility = 0.0
        for other in self.world.towns.values():
            if other is not town:
                other.hostility = max(0.0, other.hostility - 45.0)
        if target in self.world.settlements:
            # Their host is on your land, which is the oldest reason there is.
            self.court.give_ground(town.key, "attacked", self.day)
            if town.truce_days > 0:
                self.court.give_ground(town.key, "broken_truce", self.day)
                self.court.write(town.key, "truce", -25.0, self.day)
        who = "WAR" if target in self.world.settlements else "The march"
        said = ""
        if target in self.world.settlements:
            line = lordly.says(town.key, "declares", self.voice)
            if line:
                said = f'\n    {town.lord}: "{line}"'
        return (f"{who}: {town.lord} of {town.name} marches on "
                f"{self.world.node_name(target)} with {describe(host)} -- "
                f"{a.days_left:.0f} days out" + said)

    def war_pressure(self) -> float:
        return min(2.6, 1.0 + self.day / (1.7 * C.DAYS_PER_YEAR))

    def _estates_day(self) -> List[str]:
        """What the three of them made of today.

        Every grievance here is a lever the player pulled, read off the state
        it left rather than hooked onto the command that pulled it -- so a tax
        rise set by a script, by the console or by a button all register, and
        none of them can be forgotten about when a fourth way of setting it
        is added.
        """
        e = self.estates
        seats = list(self.world.settlements.values())
        if not seats:
            return []
        # Tax. The knights pay it on their manors and the guilds on their
        # stalls; both notice, and the knights notice harder.
        tax = sum(s.tax_level for s in seats) / len(seats)
        e.note("knights", "the tax you take from their manors",
               (2.0 - tax) * 7.0, self.day)
        e.note("guilds", "the tax on the market", (2.0 - tax) * 5.0, self.day)
        # The assize is a price cap, which is a guild grievance by
        # construction: the economics layer already had the lever and simply
        # had nobody on the other end of it.
        capped = len(getattr(self.economy, "assize", {}) or {})
        if capped:
            e.note("guilds", f"you hold the price of {capped} good(s) down",
                   -9.0 * capped, self.day)
        elif not e.granted("charter"):
            e.note("guilds", "prices are theirs to set", 4.0, self.day)
        # Coin struck out of nothing is the chapter's oldest complaint.
        minted = float(getattr(self.economy, "minted", 0.0) or 0.0)
        if minted > 0:
            e.note("chapter", "you have struck coin out of nothing",
                   -min(22.0, minted / 900.0), self.day)
        # Chapels and minsters, which is the thing they actually want built.
        faith = sum(s.coverage("faith_reach") for s in seats) / len(seats)
        e.note("chapter", "the souls in your towns have somewhere to pray",
               -6.0 + 20.0 * faith, self.day)
        # Knights want a war, and grow restless without one. A greater levy
        # granted and then left idle is worse: you armed them for nothing.
        at_war = any(a.owner != "player" for a in self.armies)
        idle = self.day - getattr(self, "_last_war_day", 0)
        if at_war:
            self._last_war_day = self.day
            e.note("knights", "there is a war on, and they are in it", 10.0,
                   self.day)
        elif idle > 240:
            e.note("knights", "a long peace, and nothing to take",
                   -8.0 - (4.0 if e.granted("levy") else 0.0), self.day)
        return e.day(self.day)

    def _look_around(self) -> None:
        """Refresh what you know about the march.

        Your carts are your intelligence service, which is the right answer for
        this game in particular: the map you can see is the map you trade with,
        and a lord you have never sent a cart to is a lord you are guessing
        about. A host of yours standing somewhere sees it too, and a town sworn
        to you reports every day.
        """
        for t in self.world.towns.values():
            if t.mine:
                t.observe(self.day)
        for c in self.caravans:
            node = getattr(c, "at", "") or ""
            if node in self.world.towns:
                self.world.towns[node].observe(self.day)
        for a in self.armies:
            if a.owner == "player" and a.at in self.world.towns:
                self.world.towns[a.at].observe(self.day)
        self._sight_hosts()

    def _sight_hosts(self) -> None:
        """Which of their hosts you can actually see today.

        A field army is not a town: it moves, and there is nothing standing
        there to report. So you see one when it is close enough that you could
        not miss it -- sitting on something of yours, besieging or raiding it,
        marching for it -- or when one of yours is at the same place. Anything
        else is a memory with a date on it, which is what `seen_day` is for.

        Drawing every enemy host wherever it really is would quietly delete
        the fog of war, and the fog is most of what makes a march tense.
        """
        mine = set(self.world.settlements)
        mine |= {k for k, t in self.world.towns.items() if t.mine}
        standing = {a.at for a in self.armies if a.owner == "player" and a.at}
        for a in self.armies:
            if a.owner == "player":
                continue
            close = (a.at in mine or a.bound_for in mine or a.at in standing
                     or (a.state in (BESIEGING, RAIDING) and a.at in mine))
            if close:
                a.seen_day = self.day
                a.seen_at = a.at or a.bound_for
                a.seen_size = a.size

    def known(self, town_key: str) -> Tuple[Dict[str, float], int]:
        """What you believe about a town, and how many days old it is."""
        t = self.world.towns[town_key]
        if t.seen_day < 0:
            return {}, -1
        return dict(t.seen), self.day - t.seen_day

    def believed_host(self, town_key: str) -> Dict[str, float]:
        """The host you think that town could field, from what you last saw."""
        town = self.world.towns[town_key]
        if town.mine:
            return {}
        seen, age = self.known(town_key)
        if age < 0:
            return {}                      # you have no idea, and should not pretend
        pressure = self.war_pressure()
        scale = seen.get("muster", 1.0) * pressure * (
            0.6 + 0.5 * seen.get("prosperity", 1.0))
        return {"spearman": round(10 * scale), "archer": round(7 * scale)}

    def likely_host(self, town_key: str) -> Dict[str, float]:
        """The host that town could put in the field today. Look before you
        decide the wall is high enough."""
        town = self.world.towns[town_key]
        if town.mine:
            return {}
        return self._muster_enemy(town, self.war_pressure(), spread=False)

    def _muster_enemy(self, town, pressure: float, spread: bool = True) -> Dict[str, float]:
        scale = town.muster * pressure * (0.6 + 0.5 * town.prosperity)
        if spread:
            scale *= 0.7 + 0.6 * self.rng.random()
        host = {"spearman": round(10 * scale), "archer": round(7 * scale)}
        if self.progress.age >= 2 or pressure > 1.6:
            host["man_at_arms"] = round(5 * scale)
        if self.progress.age >= 3 or pressure > 2.4:
            host["knight"] = round(3 * scale)
            host["ram"] = max(1, round(1.4 * scale))
            host["engineer"] = round(3 * scale)
        if self.progress.age >= 4:
            host["trebuchet"] = max(1, round(0.8 * scale))
        return {k: float(v) for k, v in host.items() if v > 0}

    # ----------------------------------------------------------- the house
    def post(self, who: str, post: str = "", target: str = "") -> str:
        """Give one of yours a job, or call them home.

        The cost of a post is not coin, it is the person: everybody can only
        be in one place, so a son governing Aldworth is a son not riding with
        the host, and both the tax roll and the battle line know it.
        """
        person = self.kin.by_name(who)
        if person is None:
            return f"nobody of yours called {who!r}"
        spec = POSTS.get(post)
        if post and spec is None:
            return (f"there is no post called {post!r}; "
                    f"try {', '.join(sorted(POSTS))}")
        if spec and spec.needs == "town":
            key = self._resolve_town(target)
            if key is None:
                return f"{target!r} is no settlement of yours"
            target = key
        if spec and spec.needs == "host":
            if not target.isdigit() or self.army(int(target)) is None:
                return f"no host {target!r} of yours to ride with"
            a = self.army(int(target))
            if a.owner != "player":
                return "that host is not yours"
        return self.kin.give(person, post, target,
                             name_of=self.world.node_name)

    def _resolve_town(self, text: str) -> Optional[str]:
        want = (text or "").strip().lower()
        for key, s in self.world.settlements.items():
            if want in (key.lower(), s.name.lower()):
                return key
        for key, s in self.world.settlements.items():
            if s.name.lower().startswith(want) or key.lower().startswith(want):
                return key
        return None

    def dowry(self, town_key: str) -> float:
        """What a house of that standing expects to see before it says yes."""
        town = self.world.towns.get(town_key)
        if town is None:
            return 0.0
        return C.DOWRY_BASE * (0.7 + town.muster) * town.prosperity

    def wed(self, who: str, town_key: str) -> str:
        """Marry one of yours into a neighbouring house.

        This is the cheapest lasting peace in the game and the only one that
        cannot be un-bought: a truce runs out, a gift is forgotten as the
        favour decays, and a daughter married into Ostmark is still married
        into Ostmark in the fifth chapter. What it costs is a dowry now and a
        person you might have posted somewhere.
        """
        person = self.kin.by_name(who)
        if person is None:
            return f"nobody of yours called {who!r}"
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to treat with"
        if town.mine:
            return f"{town.name} is sworn to you already; there is nothing to buy"
        if any(p.alive and p.married_to == town_key for p in self.kin.people):
            return f"your house is tied to {town.name} already"
        cost = self.dowry(town_key)
        if self.treasury < cost:
            return (f"{town.lord} of {town.name} expects {cost:,.0f}c with the "
                    f"match; you have {self.treasury:,.0f}c")
        said, mate = self.kin.marry(person, town_key, town.name, self.day)
        if mate is None:
            return said
        self.treasury -= cost
        self._outlay += cost
        self.court.write(town_key, "marriage", C.MARRIAGE_FAVOUR, self.day)
        # And a claim, which is the other half of what a marriage is for. If
        # that house ends without an heir, what it holds can come to yours
        # without a single man in the field -- see `_succession_abroad`.
        self.court.claims[town_key] = self.day
        town.hostility = max(0.0, town.hostility - C.MARRIAGE_COOLING)
        town.truce_days = max(town.truce_days, C.MARRIAGE_TRUCE)
        self.kin.did("open", 0.15)
        self.kin.teach("charm", 20.0, self.day, post="envoy")
        return self.note(f"{said} {cost:,.0f}c goes with her, and "
                         f"{town.lord}'s temper falls to {town.hostility:.0f}.",
                         MOMENTOUS)

    # ------------------------------------------------------------ diplomacy
    def gift(self, town_key: str, coin: float) -> str:
        """Buy a lord's goodwill. Cheaper than a wall, and it does not last."""
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to send to"
        if town.mine:
            return f"{town.name} is already sworn to you"
        coin = max(0.0, float(coin))
        if self.treasury < coin:
            return f"you have {self.treasury:,.0f}c"
        self.treasury -= coin
        self._outlay += coin
        before = town.hostility
        town.hostility = max(0.0, town.hostility - coin * C.GIFT_PER_COIN)
        # "a gift is forgotten as the favour decays" is what `wed` has said
        # about this since it was written, and until the ledger existed there
        # was nowhere for it to decay: `favour` only ever went up. It does now.
        self.court.write(town_key, "gift", coin * 0.01, self.day)
        self.kin.did("open", 0.10)
        self.kin.teach("charm", 6.0, self.day, post="envoy")
        return (f"{coin:,.0f}c goes to {town.lord} of {town.name}; "
                f"his temper cools from {before:.0f} to {town.hostility:.0f}")

    def truce_cost(self, town_key: str, days: int) -> float:
        town = self.world.towns[town_key]
        # An envoy who has sat with these people before does not pay the
        # stranger's price, and neither does a lord with a name for mercy.
        # And what sort of man he is. A Magpie would rather be paid than
        # fight and prices himself accordingly; the Wolf takes your coin and
        # calls it tribute.
        return (C.TRUCE_RATE * days * town.muster * town.prosperity
                * self.kin.mult("truce_cost") * lordly.sort_of(town_key).bought)

    def truce(self, town_key: str, days: int = 180) -> str:
        """Peace by the day. A lord who is paid not to march does not march."""
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to treat with"
        if town.mine:
            return f"{town.name} is sworn to you already"
        if town_key in self.court.coalition:
            # The point of the letter. Buying them off one at a time is
            # exactly what they signed it to stop you doing.
            return (f"{town.lord} has put his name to the letter against you "
                    f"and will not treat alone. `court` says what the whole "
                    f"of it would cost, and what it would take to let it "
                    f"lapse.")
        days = max(1, int(days))
        cost = self.truce_cost(town_key, days)
        if self.treasury < cost:
            return (f"{days} days of peace with {town.name} costs "
                    f"{cost:,.0f}c; you have {self.treasury:,.0f}c")
        self.treasury -= cost
        self._outlay += cost
        town.truce_days = max(town.truce_days, days)
        town.hostility = min(town.hostility, 40.0)
        self.kin.did("merciful", 0.10)
        self.kin.teach("charm", 8.0, self.day, post="envoy")
        line = lordly.says(town_key, "paid", self.voice)
        tail = f'\n    {town.lord}: "{line}"' if line else ""
        return (f"{town.lord} of {town.name} takes {cost:,.0f}c and swears off "
                f"the march for {days} days" + tail)

    def buy_off_coalition(self) -> str:
        """Pay the whole letter off at once, which is the only way to pay it.

        Dear on purpose. The coalition exists to make the third town cost
        something that the first two did not, and a price you can always meet
        would make it a toll rather than a decision. The cheap way out is the
        slow one: stop taking towns and let it wear off.
        """
        c = self.court
        if not c.coalition:
            return "there is no letter against you"
        cost = c.coalition_price(self.day)
        if self.treasury < cost:
            return (f"buying the whole letter off costs {cost:,.0f}c and you "
                    f"have {self.treasury:,.0f}c. Beating their hosts in the "
                    f"field is the other way, and waiting is the third.")
        self.treasury -= cost
        self._outlay += cost
        for key in list(c.coalition):
            c.write(key, "gift", c.offence(key, self.day) * 0.75, self.day)
            t = self.world.towns.get(key)
            if t is not None:
                t.truce_days = max(t.truce_days, 150)
        names = [self.world.node_name(k) for k in c.coalition]
        c.coalition = []
        c.coalition_day = -1
        self.kin.teach("charm", 25.0, self.day, post="envoy")
        return self.note(f"*** {cost:,.0f}c buys the letter back. "
                         f"{', '.join(names)} stand down, and none of them "
                         f"will say what it cost them. ***", MOMENTOUS)

    def demand(self, town_key: str) -> str:
        """Demand tribute. It works on a weaker lord and enrages any other."""
        self.court.write(town_key, "demanded", -18.0, self.day)
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to lean on"
        if town.mine:
            return f"{town.name} already pays you"
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self.likely_host(town_key)) + town.wall_hp / 10.0
        if mine < theirs * 1.5:
            town.hostility = min(C.HOSTILITY_WAR, town.hostility + 30.0)
            return (f"{town.lord} of {town.name} laughs at you and calls his "
                    f"levies (his strength {theirs:.0f} against your {mine:.0f})")
        paid = 220.0 * town.wealth * town.prosperity * (1.0 + self.rng.random())
        paid = min(paid, 4000.0)
        self.treasury += paid
        town.hostility = min(C.HOSTILITY_WAR, town.hostility + 12.0)
        town.prosperity = max(0.4, town.prosperity - 0.04)
        return (f"{town.lord} of {town.name} pays {paid:,.0f}c and remembers it")

    # -------------------------------------------------------------- endings
    def pace(self) -> List[Tuple[str, float, float, float]]:
        """Where you stand against each clause of the goal, and where the
        rate you are actually going will put you by the last day.

        A game whose result you only learn on the final day is a game where
        the player could not have done anything about it -- and this one is
        decided long before then, because a thin surplus over near-fixed costs
        compounds. The projection is a straight line through the last season,
        which is crude and is the point: it is the same arithmetic a steward
        would do on the back of the tax roll, and it is enough to tell you in
        the first year that the second one will not be enough.

        Each row is (what, where you are, what is wanted, where you land).
        """
        rows: List[Tuple[str, float, float, float]] = []
        left = max(0, self.goals.days - self.day)
        span = min(len(self.history), int(C.DAYS_PER_YEAR / 2))

        def rate(field: str, now: float) -> float:
            if span < 30:
                return 0.0
            then = self.history[-span]
            return (now - then.get(field, now)) / span

        if "wealth" in self.goals.paths:
            worth = self.real_worth()
            rows.append(("net worth", worth, self.goals.net_worth,
                         worth + rate("worth", worth) * left))
            pop = self.population
            rows.append(("souls", pop, float(self.goals.population),
                         pop + rate("pop", pop) * left))
        if "dominion" in self.goals.paths:
            held = float(len(self.world.vassals()))
            rows.append(("towns sworn", held, float(self.goals.towns), held))
        if "reliquary" in self.goals.paths:
            held = float(self.relics_held())
            rows.append(("relics", held, float(self.goals.relics), held))
        if "commons" in self.goals.paths and self.goals.mood:
            seat = self.home()
            rows.append(("mood held", float(self.mood_days),
                         float(self.goals.mood_days),
                         self.mood_days + (left if seat.popularity
                                           >= self.goals.mood else 0)))
        return rows

    def _check_ending(self) -> List[str]:
        if self.over:
            return [self.over]
        if self.treasury < self.goals.bankruptcy:
            self.over = "Ruined. Your debts outran your carts."
            return [self.note(self.over, MOMENTOUS)]
        if self.population < 5:
            self.over = ("Ended. The last of your people are gone and there is "
                         "nothing left to rule.")
            return [self.note(self.over, MOMENTOUS)]
        vassals = self.world.vassals()
        if "dominion" in self.goals.paths and len(vassals) >= self.goals.towns:
            self.over = (f"Dominion. {len(vassals)} towns of the march answer to you: "
                         f"{', '.join(self.world.node_name(v) for v in vassals)}.")
            return [self.note(self.over, MOMENTOUS)]
        if "reliquary" in self.goals.paths and self.relics_held() >= self.goals.relics:
            self.relic_days += 1
            if self.relic_days == 1:
                return [f"You hold {self.relics_held()} of the march's relics. "
                        f"Keep them {self.goals.relic_days} days."]
            if self.relic_days >= self.goals.relic_days:
                self.over = (f"The Reliquary. {self.relics_held()} of the march's "
                             f"relics have rested in your keeping for "
                             f"{self.goals.relic_days} days, and the pilgrims "
                             f"come to you.")
                return [self.note(self.over, MOMENTOUS)]
        else:
            self.relic_days = 0
        if self.goals.wonder and any(s.effect("wonder")
                                     for s in self.world.settlements.values()):
            self.cathedral_days += 1
            if self.cathedral_days == 1:
                return [f"The cathedral is finished. Hold it {CATHEDRAL_HOLD} days."]
            if self.cathedral_days >= CATHEDRAL_HOLD:
                self.over = ("The cathedral stands and the bells have rung for "
                             "half a year. The marches are yours.")
                return [self.note(self.over, MOMENTOUS)]
        worth = self.real_worth()
        if ("wealth" in self.goals.paths and worth >= self.goals.net_worth
                and self.population >= self.goals.population):
            self.over = (f"Triumph. {worth:,.0f}c of house and holdings in the "
                         f"coin of the first year, {self.population:.0f} souls, "
                         f"in {self.day} days.")
            return [self.note(self.over, MOMENTOUS)]
        if "commons" in self.goals.paths and self.goals.mood:
            seat = self.world.settlements.get(
                self.lord.seat or next(iter(self.world.settlements), ""))
            if seat is not None and seat.popularity >= self.goals.mood:
                self.mood_days += 1
                if self.mood_days == 1:
                    return [f"{seat.name} is content. Keep it so for "
                            f"{self.goals.mood_days} days."]
                if self.mood_days >= self.goals.mood_days:
                    self.over = (f"The Commons. {seat.name} has been content for "
                                 f"{self.goals.mood_days} days together, which is "
                                 f"longer than most lords manage in a lifetime.")
                    return [self.note(self.over, MOMENTOUS)]
            else:
                self.mood_days = 0
        if self.day >= self.goals.days:
            if "endure" in self.goals.paths:
                self.over = (f"You held. {worth:,.0f}c and {self.population:.0f} "
                             f"souls still answer to you, which was the whole of "
                             f"what was asked.")
                return [self.note(self.over, MOMENTOUS)]
            # Say what was actually asked for. A chapter that wants relics has
            # no meaningful coin target, and printing the unused one gives you
            # "against a goal of 1,000,000,000,000c", which is not a sentence
            # anybody should be handed at the end of two years' play.
            want = []
            if "wealth" in self.goals.paths:
                want.append(f"{worth:,.0f}c of {self.goals.net_worth:,.0f}")
                want.append(f"{self.population:.0f} of {self.goals.population} souls")
            if "dominion" in self.goals.paths:
                want.append(f"{len(vassals)} of {self.goals.towns} towns sworn")
            if "reliquary" in self.goals.paths:
                want.append(f"{self.relics_held()} of {self.goals.relics} relics "
                            f"held, for {self.relic_days} of "
                            f"{self.goals.relic_days} days")
            if "commons" in self.goals.paths:
                seat = self.world.settlements.get(
                    self.lord.seat or next(iter(self.world.settlements), ""))
                mood = seat.popularity if seat is not None else 0.0
                want.append(f"content {self.mood_days} of "
                            f"{self.goals.mood_days} days (mood {mood:.0f} of "
                            f"{self.goals.mood:.0f})")
            if not want:
                want.append(f"{worth:,.0f}c of house and holdings")
            self.over = "Time called. You end with " + ", ".join(want) + "."
            return [self.note(self.over, MOMENTOUS)]
        return []

    # ------------------------------------------------------------- caravans
    def new_caravan(self, home: str, name: str = "",
                    kind: str = CART) -> Tuple[Optional[Caravan], str]:
        if home not in self.world.settlements:
            return None, f"{home} is not yours to outfit from"
        if len(self.caravans) >= self.caravan_limit:
            return None, (f"you can run {self.caravan_limit} carts and hulls; "
                          f"build a trading post or a harbour for another")
        if kind == SHIP and not self.world.settlements[home].effect("port"):
            return None, f"{self.world.node_name(home)} has no harbour to build a cog in"
        cost = C.SHIP_COST if kind == SHIP else C.CARAVAN_COST
        if self.treasury < cost:
            return None, f"that costs {cost:,.0f}c and you have {self.treasury:,.0f}c"
        self.treasury -= cost
        self._outlay += cost
        uid = self.next_caravan_uid
        self.next_caravan_uid += 1
        label = "Cog" if kind == SHIP else "Caravan"
        c = Caravan(uid=uid, name=name or f"{label} {uid}", home=home, at=home,
                    kind=kind)
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
        self.treasury += (C.SHIP_COST if c.sails else C.CARAVAN_COST) * 0.4
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
        ok, why = s.can_build(building_key, self.progress)
        if not ok:
            return why
        self.treasury -= coin
        self._outlay += coin
        inst = s.start_build(building_key)
        # Whoever has the works here. An engineer does not make stone cheaper;
        # he makes the same gang of men get more done before the frost.
        speed = self.kin.mult("build", self._key_of(s))
        inst.days_left = max(1, int(round(inst.days_left / speed)))
        return (f"{spec.name} begun at {s.name}; {inst.days_left} days, "
                f"{coin:.0f}c paid")

    def found(self, site_key: str) -> str:
        """Settle unclaimed land. Expensive, and the new town starts hungry."""
        site = self.world.sites.get(site_key)
        if not site:
            return f"no unclaimed site called {site_key!r}"
        if site.key in self.world.settlements:
            del self.world.sites[site_key]
            return f"{site.name} is already yours"
        if self.treasury < site.coin_cost:
            return (f"settling {site.name} costs {site.coin_cost:,.0f}c; "
                    f"you have {self.treasury:,.0f}c")
        self.treasury -= site.coin_cost
        self._outlay += site.coin_cost
        market = Market(name=site.name, stock={}, target={})
        s = Settlement(name=site.name, terrain=dict(site.terrain), market=market,
                       culture=cultures.for_ground(site.terrain, self.house),
                       population=25.0, popularity=C.POPULARITY_START,
                       deposits=dict(site.deposits))
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
            "next_army_uid": self.next_army_uid, "house": self.house,
            "goals": self.goals.to_dict(), "scenario": self.scenario,
            "briefing": self.briefing, "start_month": self.start_month,
            "over": self.over, "world": self.world.to_dict(),
            "caravans": [caravan_to_dict(c) for c in self.caravans],
            "armies": [a.to_dict() for a in self.armies],
            "events": self.events.to_dict(), "progress": self.progress.to_dict(),
            "history": self.history[-400:], "battles": self.battles[-40:],
            "cathedral_days": self.cathedral_days,
            "relic_days": self.relic_days, "mood_days": self.mood_days,
            "lord": self.lord.to_dict(), "kin": self.kin.to_dict(),
            "economy": self.economy.to_dict(),
            "league": self.league.to_dict(),
            "court": self.court.to_dict(),
            "estates": self.estates.to_dict(),
            "feats": self.feats.to_dict(),
            "tallies": {"hosts": self._hosts_raised, "won": self._battles_won,
                        "stormed": self._stormed, "lost": self._towns_lost,
                        "trade": self._trade_profit},
            "chronicle": self.chronicle.to_dict(),
            "chapter": self.chapter,
            "rng": list(self.rng.getstate()),
            "voice_rng": list(self.voice.getstate()),
        }

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh)
        return f"saved to {path}"

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        g = cls(world=World.from_dict(d["world"]), treasury=d["treasury"],
                day=d["day"], seed=d["seed"], house=d.get("house", ""),
                goals=Goals.from_dict(d.get("goals", {})),
                scenario=d.get("scenario", "marchlands"),
                briefing=d.get("briefing", ""),
                start_month=d.get("start_month", C.START_MONTH))
        g.caravans = [caravan_from_dict(c) for c in d["caravans"]]
        g.armies = [Army.from_dict(a) for a in d.get("armies", [])]
        g.events = EventEngine.from_dict(d["events"])
        g.progress = Progress.from_dict(d["progress"])
        g.next_caravan_uid = d["next_caravan_uid"]
        g.next_army_uid = d.get("next_army_uid", 1)
        g.history = list(d.get("history", []))
        g.battles = list(d.get("battles", []))
        g.cathedral_days = d.get("cathedral_days", 0)
        g.relic_days = d.get("relic_days", 0)
        g.mood_days = d.get("mood_days", 0)
        g.lord = Lord.from_dict(d["lord"]) if "lord" in d else Lord()
        # A save from before the house existed gets one founded around the
        # lord it already has, rather than a hall with nobody in it.
        if d.get("kin"):
            g.kin = Kin.from_dict(d["kin"])
        else:
            g.kin = found_kin(random.Random(d["seed"] * 104729),
                              seat=g.lord.seat, lord_name=g.lord.name)
        g.kin.seat = g.lord.seat
        g.kin.riding = g.lord.riding
        g.economy = Economy.from_dict(d.get("economy", {}))
        g.league = League.from_dict(d.get("league", {}))
        g.court = court.Chancery.from_dict(d.get("court"))
        g.estates = estates_mod.Estates.from_dict(d.get("estates") or {})
        g.feats = feats_mod.Book.from_dict(d.get("feats") or {})
        tall = d.get("tallies") or {}
        g._hosts_raised = int(tall.get("hosts", 0))
        g._battles_won = int(tall.get("won", 0))
        g._stormed = int(tall.get("stormed", 0))
        g._towns_lost = int(tall.get("lost", 0))
        g._trade_profit = float(tall.get("trade", 0.0))
        for s in g.world.settlements.values():
            s.market.level = g.economy.price_level
            s.market.caps = dict(g.economy.assize)
        for t in g.world.towns.values():
            t.market.level = g.economy.price_level
        g.chronicle = Chronicle.from_dict(d.get("chronicle", {}))
        g.chapter = d.get("chapter", "")
        g.over = d.get("over", "")
        # Put the dice back exactly where they were. Re-seeding here -- which
        # is what this did -- loads a game whose state matches to the coin and
        # whose *future* does not: same save, reloaded, different weather,
        # different prices, different battles. The state was never the hard
        # part of saving a game; the stream position is.
        raw = d.get("rng")
        if raw:
            g.rng.setstate((raw[0], tuple(raw[1]), raw[2]))
        else:
            g.rng = random.Random(d["seed"] + d["day"])   # a save from before
        g.trade_engine = TradeEngine(g.world, g.rng)
        raw = d.get("voice_rng")
        if raw:
            g.voice.setstate((raw[0], tuple(raw[1]), raw[2]))
        return g

    @classmethod
    def load(cls, path: str) -> "GameState":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
