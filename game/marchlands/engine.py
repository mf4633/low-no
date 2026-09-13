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
from .events import EventEngine
from .goods import ALL_KEYS, good
from . import lord as lordly
from .lord import Lord, name_for
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
    chronicle: Chronicle = field(default_factory=Chronicle)
    chapter: str = ""           # which chapter of a campaign, if any
    over: str = ""              # '' while playing, else the ending

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.trade_engine = TradeEngine(self.world, self.rng)
        self._outlay = 0.0        # coin spent between ticks, for the ledger
        self._war_outlay = 0.0
        self._plunder = 0.0
        if self.lord.name == Lord.name and self.world.settlements:
            # A lord of your own, named once, seated in whatever you hold.
            self.lord.name = name_for(random.Random(self.seed * 104729))
            self.lord.seat = next(iter(self.world.settlements))

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
        return (f"day {self.day_of_month:>2} of month {self.month:>2}, "
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

    # ------------------------------------------------------------------ tick
    def tick(self) -> List[str]:
        if self.over:
            return [self.over]
        self.day += 1
        msgs: List[str] = []
        led = Ledger()

        msgs += self.events.tick(self.world, self.day, self.rng, self.progress)

        # 1. Settlements work, eat and are taxed.
        for s in self.world.settlements.values():
            before = {b.uid: b.complete for b in s.buildings}
            rep = s.tick(self.season, self.rng, self.progress)
            for b in s.buildings:
                if b.complete and not before.get(b.uid, True):
                    msgs.append(f"{s.name}: {b.spec.name} finished")
            led.taxes += rep.taxes
            led.wages += rep.wages
            led.upkeep += rep.upkeep
            msgs += rep.notes
        # Your hosts, not the ones marching on you.
        led.war = sum(a.upkeep for a in self.armies if a.owner == "player")
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
        msgs += tmsgs

        # 6. Learning, and the slow climb between ages.
        msgs += self._study()

        # 7. War.
        msgs += self._military_day()

        # 8. Mood and migration settle last, on the day as it actually went.
        for s in self.world.settlements.values():
            s.update_mood(self.progress)
            s.migrate(self.rng, self.progress)
            if s.popularity < C.UNREST_THRESHOLD:
                msgs.append(f"{s.name} is in open unrest -- nobody is working")

        self.ledger = led
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
            p.research_left -= p.mult("research_speed") * self._scholars()
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
        s.units[unit_key] = s.units.get(unit_key, 0.0) + count
        return f"{count} {u.name} muster at {s.name} ({coin:,.0f}c)"

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
                    f"({town.wall_hp:.0f} of wall, {describe(town.garrison)} within)")

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
            if host_strength(a.units) < host_strength(s.units) * 0.9:
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
            return f"{self.lord.name} is {self.lord.standing()}"
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
            return f"{self.lord.name} is {self.lord.standing()}"
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

    def _lord_day(self) -> List[str]:
        msgs = self.lord.day()
        if self.lord.riding and self.army(self.lord.riding) is None:
            self.lord.riding = 0        # the host he rode with is gone
        seat = self.lord.seat or next(iter(self.world.settlements), "")
        for key, st in self.world.settlements.items():
            st.lord_home = self.lord.at_home and key == seat
            st.lord_lost = self.lord.gone and key == seat
        return msgs

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
        raiders = Side(a.units, attack_mult=self.progress.mult("attack")
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
                                     * lordly.attack_bonus(self.lord, a.uid))
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
        holder = Side(defenders, battlement=8.0)
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
            a.siege_days = 0
            if res.winner == "attacker":
                msgs.append(self._take_town(town, a))
                a.prune()
                return msgs        # the garrison is the victor's now, not the survivors'
            elif player:
                a.state = RETURNING
                msgs.append(f"{a.name} is thrown back from {town.name}")
                # He was standing where the arrows were. Sometimes that tells.
                if self.lord.riding == a.uid:
                    self.lord.ransom = min(9000.0, 900.0 + 0.06 * self.net_worth())
                    msgs += self.lord.falls(self.rng, name_for(self.rng))
                    for st in self.world.settlements.values():
                        if not self.lord.alive:
                            st.popularity = max(0.0, st.popularity - lordly.MOURNING)
                self.march(a.uid, a.home)
            else:
                a.state = RETURNING
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
        holder = Side(s.units, attack_mult=self.progress.mult("attack"),
                      defense_mult=self.progress.mult("defense"),
                      battlement=6.0 + s.effect("battlement")
                      + (lordly.HOME_DEFENCE if at_home else 0.0))
        works = Works.of([b.key for b in s.buildings
                          if b.complete and b.spec.terrain == "rampart"])
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
        s.wall_hp = wall
        if self.day % 5 == 0 and lines:
            msgs.append(f"{s.name} under siege: {lines[0]}")
        s.units = {k: v for k, v in holder.units.items() if v >= 0.5}
        a.units = {k: v for k, v in besieger.units.items() if v >= 0.5}
        if storms_now(a.siege.plan, wall, holder.alive()):
            res = fight(besieger, holder, rng=self.rng, place=s.name)
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

    def _take_town(self, town, a: Army) -> str:
        was_mine = town.mine
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
            for other in self.world.towns.values():
                if not other.mine:
                    other.hostility = min(C.HOSTILITY_WAR, other.hostility + 18.0)
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

            # -- offence taken at you ---------------------------------------
            if t.truce_days <= 0:
                t.hostility += (C.HOSTILITY_DRIFT * pressure * t.temper
                                * (0.5 + wealth_factor)
                                * (0.6 + 0.8 * self.rng.random()))
                t.hostility = max(0.0, t.hostility - t.favour * 0.02)
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
        who = "WAR" if target in self.world.settlements else "The march"
        return (f"{who}: {town.lord} of {town.name} marches on "
                f"{self.world.node_name(target)} with {describe(host)} -- "
                f"{a.days_left:.0f} days out")

    def war_pressure(self) -> float:
        return min(2.6, 1.0 + self.day / (1.7 * C.DAYS_PER_YEAR))

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
        town.favour += coin * 0.01
        return (f"{coin:,.0f}c goes to {town.lord} of {town.name}; "
                f"his temper cools from {before:.0f} to {town.hostility:.0f}")

    def truce_cost(self, town_key: str, days: int) -> float:
        town = self.world.towns[town_key]
        return C.TRUCE_RATE * days * town.muster * town.prosperity

    def truce(self, town_key: str, days: int = 180) -> str:
        """Peace by the day. A lord who is paid not to march does not march."""
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to treat with"
        if town.mine:
            return f"{town.name} is sworn to you already"
        days = max(1, int(days))
        cost = self.truce_cost(town_key, days)
        if self.treasury < cost:
            return (f"{days} days of peace with {town.name} costs "
                    f"{cost:,.0f}c; you have {self.treasury:,.0f}c")
        self.treasury -= cost
        self._outlay += cost
        town.truce_days = max(town.truce_days, days)
        town.hostility = min(town.hostility, 40.0)
        return (f"{town.lord} of {town.name} takes {cost:,.0f}c and swears off "
                f"the march for {days} days")

    def demand(self, town_key: str) -> str:
        """Demand tribute. It works on a weaker lord and enrages any other."""
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
        worth = self.net_worth()
        if ("wealth" in self.goals.paths and worth >= self.goals.net_worth
                and self.population >= self.goals.population):
            self.over = (f"Triumph. {worth:,.0f}c of house and holdings, "
                         f"{self.population:.0f} souls, in {self.day} days.")
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
        s.start_build(building_key)
        return (f"{spec.name} begun at {s.name}; {spec.build_days} days, "
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
            "lord": self.lord.to_dict(),
            "chronicle": self.chronicle.to_dict(),
            "chapter": self.chapter,
            "rng": list(self.rng.getstate()),
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
        return g

    @classmethod
    def load(cls, path: str) -> "GameState":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
