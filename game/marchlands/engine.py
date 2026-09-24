"""The game: one state object, one tick, one ledger.

The tick is deliberately ordered -- produce before you feed, feed before you
take the mood, pay before you count the day's coin -- because several feedback
loops (hunger -> mood -> productivity -> hunger) are only stable if the order
is fixed. War is settled last, after the day's work, so a siege eats into
tomorrow rather than rewriting today.
"""

from __future__ import annotations

import copy
import json
import math
import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import building
from .chronicle import MOMENTOUS, NOTABLE, ROUTINE, Chronicle
from .castle import INVEST, Works, choose, storms_now
from .economics import MONEY_BASE, Accounts, Economy
from . import estates as estates_mod
from . import feats as feats_mod
from . import missions as missions_mod
from .events import EventEngine
from .goods import ALL_KEYS, RATION_GOODS, good
from . import lords as lordly
from . import lord as manly
from . import chancery as court
from . import culture as cultures
from . import keep as keeps
from . import rivers as waters
from . import sight
from .kin import POSTS, Kin, found as found_kin
from . import league as lg
from .league import League, PLAYER
from .lord import Lord
from .market import Market
from .military import (Battle, open_battle, BESIEGING, GARRISON, HOLD, LINE, MARCHING, RAIDING,
                       RELIEVING, RETURNING, STORM, describe,
                       UNITS, Army,
                       Side, can_recruit, describe, fight, host_size, host_speed,
                       host_strength, host_upkeep, raid_day, recruit_cost, siege_day, unit)
from .military import Field, going_of, sky_on, sortie_odds
from . import cartography as carto
from . import military
from . import plague as plague_mod
from . import supply
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
    #: Coin a mission paid. A reward that goes straight into the chest is a
    #: coin the day's accounts cannot explain, and this game has a test that
    #: says every one of them can be.
    reward: float = 0.0
    interest: float = 0.0
    wages: float = 0.0
    upkeep: float = 0.0
    caravans: float = 0.0
    building: float = 0.0
    war: float = 0.0

    @property
    def income(self) -> float:
        return (self.taxes + self.tribute + self.plunder + self.offerings
                + self.interest + self.reward + max(0.0, self.trade))

    @property
    def net(self) -> float:
        # Written as income minus outgoings rather than as its own list of
        # columns. Two hand-written sums of the same ledger is one of them
        # forgetting a column, which is exactly what happened when `reward`
        # was added to `income` and not to this.
        return (self.taxes + self.trade + self.tribute + self.plunder
                + self.offerings + self.interest + self.reward
                - self.wages - self.upkeep - self.caravans - self.building
                - self.war)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _ordinal(n: int) -> str:
    """`3rd of 9`, because `place 3` is not how anybody says it."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


@dataclass
class PendingBattle:
    """A fight the day has stopped on, waiting for somebody to fight it.

    Everything the aftermath needs to finish the day is here by key rather
    than by reference, because this has to survive a save: the army by uid,
    the place by key, the hosts standing inside a sworn town by uid. The
    sides themselves live in the Battle, casualties and all.
    """
    battle: Battle
    kind: str                     # 'wall' -- your own town; 'storm' -- a foreign one
    army: int                     # uid of the host going in
    where: str                    # settlement key, or town key
    side: str                     # which side is yours: 'attacker' or 'defender'
    title: str
    day: int
    stationed: List[int] = field(default_factory=list)
    #: A field battle has hosts on both sides rather than a host and a
    #: wall: `stationed` is the relieving side, `foes` the ring it fights.
    foes: List[int] = field(default_factory=list)
    #: The standing wall, for the picture: the fight itself is at the
    #: breach, with `wall_hp` nought, exactly as `fight` has always had it.
    wall_standing: float = 0.0
    wall_full: float = 0.0
    #: What followed, once it was over -- the sack, the rout, the town
    #: changing hands. Kept on the fight so the screen can say it, because
    #: the engine finishing a battle and the player finishing reading it are
    #: two different moments and the first version conflated them: the day
    #: cleared the fight the instant it ended and the verdict was never seen.
    after: List[str] = field(default_factory=list)

    #: Whether the aftermath has run. A fight can be over and unsettled for
    #: the instant between the last round and `_finish_battle`.
    settled: bool = False
    #: The lord's own part, when he rode at their head: rounds ridden, men
    #: cut down by his hand, steadiness given, and what became of him.
    lord_rode: int = 0
    lord_kills: int = 0
    lord_rally: float = 0.0
    lord_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"battle": self.battle.to_dict(), "kind": self.kind,
                "army": self.army, "where": self.where, "side": self.side,
                "title": self.title, "day": self.day,
                "stationed": list(self.stationed), "foes": list(self.foes),
                "lord_rode": self.lord_rode, "lord_kills": self.lord_kills,
                "lord_rally": self.lord_rally, "lord_lines": list(self.lord_lines),
                "wall_standing": self.wall_standing, "wall_full": self.wall_full,
                "after": list(self.after), "settled": self.settled}

    @classmethod
    def from_dict(cls, d: dict) -> "PendingBattle":
        return cls(battle=Battle.from_dict(d["battle"]), kind=d["kind"],
                   army=d["army"], where=d["where"], side=d["side"],
                   title=d["title"], day=d["day"],
                   stationed=list(d.get("stationed", [])),
                   foes=list(d.get("foes", [])),
                   lord_rode=int(d.get("lord_rode", 0)),
                   lord_kills=int(d.get("lord_kills", 0)),
                   lord_rally=float(d.get("lord_rally", 0.0)),
                   lord_lines=list(d.get("lord_lines", [])),
                   wall_standing=d.get("wall_standing", 0.0),
                   wall_full=d.get("wall_full", 0.0),
                   after=list(d.get("after", [])),
                   settled=bool(d.get("settled", False)))


@dataclass
class GameState:
    world: World
    treasury: float = 1500.0
    day: int = 0
    caravans: List[Caravan] = field(default_factory=list)
    armies: List[Army] = field(default_factory=list)
    #: Whether a fight your men are in stops the day and waits for you.
    #: "auto" resolves everything at once, the way it always did, and is the
    #: default so that the autoplayer, the tests and every headless run are
    #: untouched; the console and the window turn it to "play". A battle
    #: nobody is in stays "auto" whatever this says.
    battles_mode: str = "auto"
    #: The fight the day is waiting on, if there is one. See `battle_step`.
    pending: Optional[PendingBattle] = None
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
    #: A path through the game that is yours rather than the scenario's. Every
    #: house has been playing the identical campaign with different
    #: multipliers; this is what makes the Hansa's game a Hansa's game.
    missions: missions_mod.Roll = field(default_factory=missions_mod.Roll)
    #: What of the march you have seen, and what you can see today.
    shroud: sight.Shroud = field(default_factory=sight.Shroud)
    #: What you are, as distinct from who you are -- see roles.py. Every game
    #: has opened from the same position; this is the one you opened from.
    role: str = "lord"
    #: The lord you hold this valley from, for a game that opens sworn to
    #: somebody. "" for everybody else, which is almost everybody.
    liege: str = ""
    #: Tallies nothing else keeps, because a feat must be checked against a
    #: figure rather than instrumented into the thing it counts.
    _hosts_raised: int = 0
    _battles_won: int = 0
    #: The day the knights last had a war to be in. A real field, because
    #: it is read on a day there has never been one -- and because the
    #: version of it that sprang into existence on first use was not saved.
    _last_war_day: int = 0
    _stormed: int = 0
    _towns_lost: int = 0
    _trade_profit: float = 0.0
    #: How many times your seat has been stormed and gutted. In the ordinary
    #: game that is a catastrophe you play on from, deliberately -- see
    #: `_sack`. A scenario whose whole subject is one siege needs it to be
    #: the end, and asks with the "survive" path.
    _sacked: int = 0
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
        #: The sickness draws from its own stream, like every other
        #: subsystem here, and for the reason this file keeps relearning:
        #: a daily roll taken off the world's RNG shifts every seeded
        #: outcome in the game behind it. Adding one cost the siege guard a
        #: seed before it had killed a single person.
        self.pest = random.Random(self.seed * 6079 + 17)
        # And the one the carts carry it on, seeded here where the game's
        # own seed is known.
        self.trade_engine.pest = random.Random(self.seed * 5081 + 7)
        # And the water's, which spills a load at a bad ford.
        self.trade_engine.spate = random.Random(self.seed * 7717 + 23)
        self.world.river_seed = self.seed

    def _streams(self) -> Dict[str, random.Random]:
        """Every dice cup this object owns, by name.

        One list, because a stream that is seeded in `__init__` and not put
        back in `from_dict` gives you a save whose state matches to the coin
        and whose future does not -- the exact bug the `rng` note below was
        written about, repeated three times over by the sickness and the
        water, each of which quite correctly took a stream of its own and
        then quite incorrectly forgot to save it. The next subsystem that
        needs one adds a line here and is done.

        `kin`, `league` and the chancery keep and restore their own.
        """
        return {"rng": self.rng, "voice_rng": self.voice,
                "pest_rng": self.pest, "cart_pest_rng": self.trade_engine.pest,
                "spate_rng": self.trade_engine.spate}

    @staticmethod
    def _put_back(rng: random.Random, raw) -> bool:
        """Set a stream back to where the save left it. False if it cannot."""
        if not raw:
            return False
        rng.setstate((raw[0], tuple(raw[1]), raw[2]))
        return True

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
        if self.pending is not None:
            if not self.pending.battle.over:
                # The storm is going in and the day cannot end until it has.
                # Said once here rather than resolved quietly, because
                # resolving it quietly is the thing this screen exists to stop.
                return [f"The day waits on the fight at {self.pending.title}. "
                        f"`battle` to fight it, `battle auto` to let it run."]
            self.pending = None            # read, or not; the day moves on
        self.day += 1
        msgs: List[str] = []
        led = Ledger()

        # Taken before anything moves a pile, so the top bar's change is the
        # whole day's: the building, the mending, the rot, the carts, the fire.
        opened = {k: dict(s.market.stock)
                  for k, s in self.world.settlements.items()}

        msgs += self.events.tick(self.world, self.day, self.rng, self.progress)

        # 1. Settlements work, eat and are taxed.
        for key, s in self.world.settlements.items():
            before = {b.uid: b.complete for b in s.buildings}
            rep = s.tick(self.season, self.rng, self.progress, day=self.day)
            rep.opened = opened.get(key)
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

        # 4. The wider world produces, consumes and reprices -- and the
        # peddlers carry a little of it down the roads between neighbours.
        ringed = {a.at for a in self.armies if a.state == BESIEGING}
        for key, t in self.world.towns.items():
            t.tick(self.rng, besieged=key in ringed)
        self.world.peddle(closed=ringed)

        # 5. Caravans move and deal.
        before_trade = self.treasury
        self.trade_engine.season = self.season
        self.trade_engine.day = self.day
        self.trade_engine.seed = self.seed
        self.trade_engine.start_month = self.start_month
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
        standing = self._standing()
        msgs += self.feats.check(standing)
        msgs += self._missions_day(standing, led)

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
        # It marches out of the granary it was raised in, as full as the
        # granary allows. A host that had to be told to take food would
        # starve the first time somebody forgot, which is a memory test
        # rather than a decision.
        self.provision(a.uid)
        return a, ""

    def provision(self, uid: int, days: float = 0.0) -> str:
        """Load a host's baggage out of the granary it is standing in.

        Only at one of your own towns -- a host in the field fills its
        baggage by foraging, which is the whole of supply.py. The food comes
        off the town's own stores, so provisioning an army is visibly the
        bread the town would have eaten.
        """
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != PLAYER:
            return f"{a.name} is not yours to victual"
        where = a.at
        if where not in self.world.settlements:
            return f"{a.name} is not standing in a town of yours"
        room = supply.capacity(a.size) - a.stores
        if room <= 0.5:
            return f"{a.name} is carrying all it can"
        want = min(room, a.size * supply.MARCH_RATION * days) if days > 0 else room
        got = self._draw_rations(where, want)
        a.stores += got
        if got <= 0.05:
            return (f"{self.world.node_name(where)} has nothing to spare -- "
                    f"{a.name} marches on what it has")
        return (f"{a.name} victualled at {self.world.node_name(where)}: "
                f"{supply.days_left(a.size, a.stores):.0f} days in the baggage")

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
        water = self._set_march(a, a.at or a.home, node, a.units)
        return (f"{a.name} marches on {self.world.node_name(node)} -- "
                f"{a.days_left:.0f} days" + (f" ({water})" if water else ""))

    # --------------------------------------------------------------- water
    def _set_march(self, a, origin: str, target: str,
                   units: Dict[str, float]) -> str:
        """Put a host on the road, once, in one place.

        Three separate copies of these four lines used to exist -- your own
        host, an enemy's, and a pilgrimage party -- and when the rivers
        arrived only one of them would have learnt about them. That is the
        garrison bug (see settlement.max_garrison) in a different coat, and
        this time it got written down before it cost anything.

        Returns what the water did, in words, or '' if it did nothing.
        """
        dist = self.world.distance(origin, target)
        days = max(1.0, dist / max(host_speed(units), 1.0))
        extra, notes = self.world.water_days(
            origin, target, self.day, self.seed, self.start_month)
        a.bound_for = target
        a.days_left = days + extra
        a.leg_days = a.days_left
        a.state = MARCHING
        notes += self._bridge_toll(a, origin, target)
        return "; ".join(notes)

    #: What a host pays to walk over somebody else's bridge, per hundred men.
    #: Absurd and entirely real: an army on the march was a customer, and the
    #: man who held the crossing charged it. A host coming for YOU is not a
    #: customer, which is the distinction that makes it worth modelling.
    HOST_TOLL = 34.0

    def _bridge_toll(self, a, origin: str, target: str) -> List[str]:
        if a.owner == "player":
            return []
        hostile = target in self.world.settlements
        notes = []
        for r, x, y, bridge in self.world.crossings(origin, target):
            if bridge is None or bridge.owner != "player" or not bridge.standing:
                continue
            if hostile:
                # He is coming for you. He is not going to pay for the deck.
                notes.append(f"crosses your {bridge.name}")
                continue
            paid = self.HOST_TOLL * max(1.0, a.size / 100.0)
            self.treasury += paid
            notes.append(f"pays {paid:.0f}c at {bridge.name}")
        return notes

    def worst_unbridged(self) -> Optional[Tuple[str, str, "waters.River"]]:
        """The crossing your own running carts lose the most days at.

        One reader, used by the panel that offers the button and by the
        autoplayer that presses it. Two copies of "which crossing matters"
        is how the garrison rule went wrong, and the balance guard only
        measures what the autoplayer does -- so the two had better agree
        about what a good bridge is.
        """
        best: Optional[Tuple[str, str, waters.River]] = None
        for c in self.caravans:
            if not c.running or c.sails or len(c.route) < 2:
                continue
            for i, stop in enumerate(c.route):
                nxt = c.route[(i + 1) % len(c.route)]
                if nxt.node == stop.node:
                    continue
                if not (self.world.is_mine(stop.node)
                        or self.world.is_mine(nxt.node)):
                    continue
                for r, x, y, bridge in self.world.crossings(stop.node, nxt.node):
                    if bridge is not None:
                        continue
                    if best is None or r.ford_limit < best[2].ford_limit:
                        best = (stop.node, nxt.node, r)
        return best

    def restock(self, settlement_key: str = "", uid: int = -1) -> str:
        """Buy beasts in for a yard that has lost its flock.

        The other half of a raid driving them off. A flock below its seed
        share cannot breed back -- there is nothing left to breed from --
        and a rule like that is only fair if there is a way to pay your way
        out of it. This is the bill: so much a head, to fill the yard.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        yards = [b for b in s.buildings
                 if b.key in C.HERD_FULL and b.complete]
        if uid >= 0:
            yards = [b for b in yards if b.uid == uid]
        elif yards:
            # The emptiest one, because that is the one you meant.
            yards = [min(yards, key=lambda b: b.head / C.HERD_FULL[b.key])]
        if not yards:
            return f"{s.name} has no pasture, dairy or stable to stock"
        yard = yards[0]
        full = C.HERD_FULL[yard.key]
        want = full - max(0.0, yard.head)
        if want < 0.5:
            return f"the {yard.spec.name.lower()} at {s.name} is fully stocked"
        price = C.HERD_PRICE.get(yard.key, 50.0)
        bill = want * price
        if self.treasury < bill:
            return (f"{want:.0f} head for the {yard.spec.name.lower()} is "
                    f"{bill:,.0f}c and you have {self.treasury:,.0f}c")
        self.treasury -= bill
        yard.head = float(full)
        return (f"{want:.0f} head driven in to the "
                f"{yard.spec.name.lower()} at {s.name} for {bill:,.0f}c")

    def herds(self, settlement_key: str = "") -> List[dict]:
        """Every yard that keeps beasts, and how it stands."""
        s = self.world.settlements.get(settlement_key or "") or self.home()
        out = []
        for b in s.buildings:
            full = C.HERD_FULL.get(b.key, 0)
            if not full or not b.complete:
                continue
            head = max(0.0, b.head)
            out.append({"uid": b.uid, "name": b.spec.name, "key": b.key,
                        "head": round(head, 1), "full": full,
                        "share": round(head / full, 3),
                        "seed": head >= full * C.HERD_SEED,
                        "cost": round((full - head)
                                      * C.HERD_PRICE.get(b.key, 50.0))})
        return out

    def bridges_of(self, owner: str = "player") -> List[waters.Bridge]:
        return [b for b in self.world.bridges if b.owner == owner]

    def build_bridge(self, a: str, b: str, river_key: str = "") -> str:
        """Put masons on a crossing between two named places.

        You do not choose a point on a map; you choose a road. That is the
        decision the player can actually reason about -- *this* is the leg my
        carts run and the water is out on it three weeks in four -- and the
        point falls out of the geometry.
        """
        a = self.world.resolve(a) or a
        b = self.world.resolve(b) or b
        if a not in self.world.coords or b not in self.world.coords:
            return "I do not know that road"
        # A player names a river, not a key. `water bridge aldworth marchand
        # perry` has to mean the Perry, because "r0" is not a word anybody
        # in this game has ever been shown.
        if river_key:
            named = next((r.key for r in self.world.waters()
                          if r.key == river_key
                          or r.name.lower().startswith(river_key.lower())), "")
            if not named:
                return f"no water called {river_key!r}"
            river_key = named
        found = self.world.bridge_at(a, b, river_key)
        if found is None:
            if river_key:
                return f"no {river_key} on the road from {self.world.node_name(a)}"
            return (f"the road from {self.world.node_name(a)} to "
                    f"{self.world.node_name(b)} crosses no water")
        river, x, y = found
        if not (self.world.is_mine(a) or self.world.is_mine(b)):
            return ("a bridge wants a bank you hold -- neither end of that "
                    "road is yours")
        standing = waters.served_by(self.world.bridges, river.key, x, y)
        if standing is not None:
            who = "yours" if standing.owner == "player" else f"{standing.owner}'s"
            return f"{standing.name} already carries that reach, and it is {who}"
        already = [br for br in self.world.bridges
                   if br.river == river.key and not br.standing
                   and not br.broken
                   and math.hypot(br.x - x, br.y - y) <= waters.REACH]
        if already:
            return f"the masons are already at work on {already[0].name}"
        if self.treasury < waters.BRIDGE_COST:
            return (f"a bridge over the {river.name} is "
                    f"{waters.BRIDGE_COST:.0f}c and you have "
                    f"{self.treasury:.0f}c")
        self.treasury -= waters.BRIDGE_COST
        near = min((a, b), key=lambda k: math.hypot(
            self.world.coords[k][0] - x, self.world.coords[k][1] - y))
        br = waters.Bridge(uid=self.world._next_bridge, river=river.key,
                           x=x, y=y, owner="player",
                           name=f"{self.world.node_name(near)} Bridge",
                           built_day=self.day, days_left=waters.BRIDGE_DAYS)
        self.world._next_bridge += 1
        self.world.bridges.append(br)
        return (f"Masons begin {br.name} over the {river.name}: "
                f"{waters.BRIDGE_COST:.0f}c, {waters.BRIDGE_DAYS} days")

    def break_bridge(self, uid: int) -> str:
        """Throw down your own bridge. It is not a free denial.

        You lose the toll, your own carts go round with everybody else, and
        putting it back is most of a season. That is the point: a crossing
        you deny an army is a crossing you deny yourself.
        """
        for br in self.world.bridges:
            if br.uid == uid and br.owner == "player":
                if br.broken:
                    return f"{br.name} is already down"
                if not br.standing:
                    self.world.bridges.remove(br)
                    return f"the work on {br.name} is abandoned"
                br.broken = True
                br.days_left = 0
                river = self.world.river(br.river)
                return (f"{br.name} goes into the {river.name if river else 'water'}. "
                        f"Nothing crosses there now, yours included")
        return f"no bridge of yours numbered {uid}"

    def mend_bridge(self, uid: int) -> str:
        for br in self.world.bridges:
            if br.uid == uid and br.owner == "player":
                if not br.broken:
                    return f"{br.name} is standing"
                cost = waters.BRIDGE_COST * waters.REBUILD_SHARE
                if self.treasury < cost:
                    return (f"mending {br.name} is {cost:.0f}c and you have "
                            f"{self.treasury:.0f}c")
                self.treasury -= cost
                br.broken = False
                br.days_left = waters.REBUILD_DAYS
                return (f"The piers held. {br.name} back in "
                        f"{waters.REBUILD_DAYS} days for {cost:.0f}c")
        return f"no bridge of yours numbered {uid}"

    def _bridge_day(self) -> List[str]:
        """Masonry, and what other people's traffic leaves on the deck."""
        msgs: List[str] = []
        toll = 0.0
        for br in self.world.bridges:
            if br.days_left > 0:
                br.days_left -= 1
                if br.days_left == 0 and not br.broken:
                    river = self.world.river(br.river)
                    msgs.append(f"{br.name} is open over the "
                                f"{river.name if river else 'water'}")
                continue
            if br.broken or br.owner != "player":
                continue
            toll += self.toll_on(br)
        if toll:
            self.treasury += toll
        return msgs

    def toll_on(self, br: waters.Bridge) -> float:
        """What the country's own traffic pays to cross.

        Scaled by the markets either side rather than by a flat rate, because
        a bridge is worth what crosses it. The world already stands in for
        everybody-who-is-not-you as a pull toward each town's equilibrium;
        this is the share of that which has to get over the water.
        """
        near = 0.0
        for key, (x, y) in self.world.coords.items():
            d = math.hypot(x - br.x, y - br.y)
            if d > 3.0 * waters.REACH:
                continue
            town = self.world.towns.get(key)
            if town is not None:
                near += town.wealth * max(0.0, 1.0 - d / (3.0 * waters.REACH))
            elif key in self.world.settlements:
                near += 0.4 * max(0.0, 1.0 - d / (3.0 * waters.REACH))
        return min(waters.TOLL_CAP, waters.TOLL_RATE * near * 100.0)

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
        if town.truce_days > 0:
            # A treaty torn up. Whatever he thinks of you, he now knows what
            # your seal is worth, and so does everyone he writes to.
            self.court.shake(key, -30.0)
            for other in self.world.towns:
                if other != key and not self.world.towns[other].mine:
                    self.court.shake(other, -10.0)
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
            there = self.world.towns[other]
            kin = 1.3 if there.culture and there.culture == town.culture else 0.9
            self.court.write(other, "besieged",
                             -12.0 * scale * close * kin
                             * lordly.sort_of(other).temper,
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

    def split_host(self, uid: int, units: Dict[str, int],
                   name: str = "") -> Tuple[Optional[Army], str]:
        """Detach part of a host as a host of its own, standing where it is.

        The horse ride off to burn the country while the foot sit before
        the wall: that is what a detachment is for, and it is the one thing
        "select the knights and send them" can honestly mean here, where a
        host is a count of men and not a crowd of sprites. The new host takes
        the old one's order and posture and its share of the baggage. The
        captain stays with the host he was posted to.
        """
        a = self.army(uid)
        if a is None:
            return None, f"no host {uid}"
        if a.owner != PLAYER:
            return None, f"{a.name} is not yours to command"
        if a.state == MARCHING:
            return None, f"{a.name} is on the road -- split it when it arrives"
        take: Dict[str, float] = {}
        for k, n in units.items():
            if n <= 0:
                continue
            have = a.units.get(k, 0.0)
            if have < n:
                return None, f"{a.name} has only {have:.0f} {unit(k).name}"
            take[k] = float(n)
        if not take:
            return None, "name some soldiers to detach"
        left = {k: v - take.get(k, 0.0) for k, v in a.units.items()}
        if host_size({k: v for k, v in left.items() if v >= 0.5}) < 1:
            return None, f"that is the whole of {a.name} -- march it instead"
        share = host_size(take) / max(1, a.size)
        for k, n in take.items():
            a.units[k] -= n
            if a.units[k] < 0.5:
                del a.units[k]
        b = Army(uid=self.next_army_uid, name=name or f"Host {self.next_army_uid}",
                 owner=PLAYER, units=take, at=a.at, home=a.home,
                 state=a.state, order=a.order, siege_days=a.siege_days)
        self.next_army_uid += 1
        b.stores, a.stores = a.stores * share, a.stores * (1.0 - share)
        self.armies.append(b)
        where = self.world.node_name(a.at)
        a.log.append(f"{describe(take)} detached as {b.name} at {where}")
        b.log.append(f"detached from {a.name} at {where}")
        return b, ""

    def join_hosts(self, uid: int, other: int) -> str:
        """Fold one host into another standing in the same place."""
        a, b = self.army(uid), self.army(other)
        if a is None or b is None:
            return f"no host {other if a is not None else uid}"
        if a is b:
            return f"{a.name} is already one host"
        if a.owner != PLAYER or b.owner != PLAYER:
            return "both hosts must be yours"
        if a.state == MARCHING or b.state == MARCHING:
            return "a host on the road cannot be joined -- wait for it to arrive"
        if a.at != b.at:
            return (f"{b.name} is at {self.world.node_name(b.at)}, "
                    f"{a.name} at {self.world.node_name(a.at)}")
        for k, n in b.units.items():
            a.units[k] = a.units.get(k, 0.0) + n
        a.stores += b.stores
        a.siege_days = max(a.siege_days, b.siege_days)
        # A captain posted to the host that is gone rides with the one that
        # is left; otherwise he would be riding with a number.
        for p in self.kin.people:
            if p.alive and p.post == "captain" and p.target == str(b.uid):
                p.target = str(a.uid)
        self.armies.remove(b)
        a.log.append(f"{b.name} joined: {describe(b.units)}")
        return f"{b.name} joins {a.name} at {self.world.node_name(a.at)}: {describe(a.units)}"

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
        msgs += self._field_day()
        msgs += self._relieve_day()
        for a in list(self.armies):
            if a not in self.armies:
                continue    # a town fell today and its host went with it
            if a.owner != "player" and self.world.towns[a.owner].mine:
                msgs.append(f"{a.name} turns for home -- {self.world.node_name(a.owner)} "
                            f"is sworn to you now")
                self.armies.remove(a)
                continue
            msgs += self._feed_host(a)
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
        # The country comes back where nobody is eating it. Done after every
        # host has had its morning, so a place a host is standing in is the
        # one place that does not recover today.
        standing = {a.at or a.bound_for for a in self.armies if a.size > 0}
        for key in list(self.world.grazed):
            if key in standing:
                continue
            left = supply.recover(self.world.grazed[key])
            if left <= 0:
                del self.world.grazed[key]
            else:
                self.world.grazed[key] = left
        msgs += self._plague_day()
        msgs += self._bridge_day()
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

    def _ring_at(self, node: str, against: str) -> List[Army]:
        """The hosts sitting round or burning `node` that are `against`'s
        enemies: the player's besiegers at a lord's town, or a lord's at
        the player's. Two lords at each other's walls are nobody's business
        but theirs, so a lord's host coming home to a lord's siege walks in
        as it always has."""
        out = []
        for x in self.armies:
            if x.at != node or x.state not in (BESIEGING, RAIDING):
                continue
            if against == PLAYER and x.owner != PLAYER:
                out.append(x)
            elif against != PLAYER and x.owner == PLAYER:
                out.append(x)
        return out

    def _field_day(self) -> List[str]:
        """Hosts that came up to relieve a place give battle in the open.

        One fight a place, both sides pooled: every host that came up
        against every host in the ring. The relief attacks -- it is the
        side that has to get through -- and the ring holds its lines under
        its own order. In the open there is no wall, so the storm's oil and
        pitch have nothing to be poured over, and the fight is the same
        arithmetic every field battle has always used. If you are on either
        side and playing your battles, the day waits on it like a storm.
        """
        if self.pending is not None:
            return []
        msgs: List[str] = []
        for node in sorted({a.at for a in self.armies if a.state == RELIEVING}):
            relief = [a for a in self.armies if a.at == node and a.state == RELIEVING]
            if not relief:
                continue
            side_owner = relief[0].owner
            ring = self._ring_at(node, against=side_owner)
            if not ring:
                for a in relief:
                    a.state = GARRISON
                msgs.append(f"{relief[0].name} finds the lines before "
                            f"{self.world.node_name(node)} empty and walks in")
                continue
            msgs += self._field_battle(node, relief, ring)
            if self.pending is not None:
                break
        return msgs

    def _field_side(self, hosts: List[Army]) -> Side:
        """Every host of one side as one line, dressed as the player's are."""
        pooled: Dict[str, float] = {}
        for x in hosts:
            for k, n in x.units.items():
                pooled[k] = pooled.get(k, 0.0) + n
        if hosts[0].owner != PLAYER:
            return Side(pooled)
        lead = hosts[0]
        return Side(pooled,
                    attack_mult=(self.progress.mult("attack")
                                 * self.kin.mult("attack", lead.uid)
                                 * manly.attack_bonus(self.lord, lead.uid)),
                    defense_mult=self.progress.mult("defense"))

    def _field_battle(self, node: str, relief: List[Army],
                      ring: List[Army]) -> List[str]:
        att, dfn = self._field_side(relief), self._field_side(ring)
        lead, foe = relief[0], ring[0]
        orders = (lead.order if lead.owner == PLAYER else lordly.sort_of(lead.home).fights,
                  foe.order if foe.owner == PLAYER else lordly.sort_of(foe.home).fights)
        name = self.world.node_name(node)
        battle = open_battle(att, dfn, rng=self.rng, place=name, orders=orders,
                             field=self.field_at(node), walled=False)
        if self.battles_mode == "play":
            self.pending = PendingBattle(
                battle=battle, kind="field", army=lead.uid, where=node,
                side="attacker" if lead.owner == PLAYER else "defender",
                title=name, day=self.day,
                stationed=[x.uid for x in relief], foes=[x.uid for x in ring])
            return [self.note(f"*** BATTLE IS JOINED BEFORE {name.upper()}. "
                              f"The day waits on it. ***", MOMENTOUS)]
        battle.run()
        battle.close()
        return self._after_field(battle.res, node, relief, ring, att, dfn)

    @staticmethod
    def _share_out(hosts: List[Army], side: Side) -> None:
        """Give a pooled line's survivors back to the hosts that made it up,
        each keeping its share of what is left of each kind."""
        before: Dict[str, float] = {}
        for x in hosts:
            for k, n in x.units.items():
                before[k] = before.get(k, 0.0) + n
        for x in hosts:
            for k in list(x.units):
                have = before.get(k, 0.0)
                x.units[k] = side.units.get(k, 0.0) * (x.units[k] / have) if have else 0.0
            x.prune()

    def _after_field(self, res, node: str, relief: List[Army], ring: List[Army],
                     att: Side, dfn: Side) -> List[str]:
        """What follows a battle in the open before a besieged place."""
        name = self.world.node_name(node)
        lead, foe = relief[0], ring[0]
        msgs = [f"BATTLE BEFORE {name.upper()}: the {res.winner} holds the ground "
                f"after {res.rounds} rounds",
                self._box_score(f"{lead.name} relieves {name}", res, lead.owner, foe.owner)]
        self.scored(lead.owner, won=res.winner == "attacker")
        self.scored(foe.owner, won=res.winner == "defender")
        self._share_out(relief, att)
        self._share_out(ring, dfn)
        if res.winner == "attacker":
            # The ring is broken. Its hosts fall back the way they came.
            for x in ring:
                # Marked as falling back even when nothing is left to fall
                # back: the day's loop buries a host with no men, and it
                # must not find a dead one still sitting at the wall.
                x.siege_days = 0
                x.state = RETURNING
                if x.size > 0:
                    self.march(x.uid, x.home)
            msgs.append(f"The siege of {name} is broken: the host of "
                        f"{self.world.node_name(foe.home)} falls back")
            if foe.owner == PLAYER and self.lord.riding in [x.uid for x in ring]:
                msgs += self._lord_fell()
            for x in relief:
                self._come_inside(x, node)
            if foe.owner != PLAYER and foe.owner in self.world.towns:
                self.court.write(foe.owner, "beaten", 22.0, self.day)
                self.court.reckon(foe.owner, 25.0)
        else:
            # Held or stood off: the relief could not get through. What is
            # left of it slips inside if this is its own gate, and goes home
            # if it is not; the ring stays where it sat.
            how = ("breaks off" if res.broken_off == "attacker"
                   else "is thrown back" if res.winner == "defender" else "cannot get through")
            msgs.append(f"{lead.name} {how} before {name}")
            if lead.owner == PLAYER and self.lord.riding in [x.uid for x in relief]:
                msgs += self._lord_fell()
            for x in relief:
                x.state = RETURNING
                if x.size <= 0:
                    continue
                if x.home == node:
                    self._come_inside(x, node)
                    msgs.append(f"what is left of {x.name} slips inside the walls")
                else:
                    x.state = RETURNING
                    self.march(x.uid, x.home)
        return msgs

    def _come_inside(self, x: Army, node: str) -> None:
        """A host that has fought its way to the gate goes through it: yours
        stands in the place as a garrisoned host, a lord's stands down into
        his town's garrison as any host of his does at home."""
        if x.owner == PLAYER or node not in self.world.towns:
            x.state = GARRISON
            x.siege_days = 0
            return
        town = self.world.towns[node]
        for k, n in x.units.items():
            town.garrison[k] = town.garrison.get(k, 0.0) + n
        if x in self.armies:
            self.armies.remove(x)

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
                ring = self._ring_at(node, against=PLAYER)
                if ring:
                    # The besiegers are between him and the gate. He stands
                    # off tonight and they must turn and fight him at dawn.
                    a.state = RELIEVING
                    return self.note(
                        f"*** {a.name} comes up before {self.world.node_name(node)}. "
                        f"The host of {self.world.node_name(ring[0].home)} must turn "
                        f"and fight at dawn. ***", MOMENTOUS)
                a.state = GARRISON
                return f"{a.name} reaches {self.world.node_name(node)}"
            town = self.world.towns[node]
            a.state = BESIEGING
            return (f"{a.name} sits down before {town.name} "
                    f"({town.wall_hp:.0f} of wall, {describe(town.garrison)} within)"
                    + self._declare(town))

        if node == a.home and node in self.world.towns:
            if self._ring_at(node, against=a.owner):
                # Your lines are between him and his own gate. He does not
                # walk through them: he stands off, and you fight at dawn.
                a.state = RELIEVING
                return self.note(
                    f"*** A host out of {self.world.node_name(node)} comes up behind "
                    f"your lines -- {describe(a.units)}. Battle at dawn. ***", MOMENTOUS)
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

    #: Warband's two rules for a lord's siege: he stays while he outnumbers
    #: the men inside by this much, and hunger does his work for him; below
    #: it, he lifts. And nobody sits for ever.
    SIEGE_ODDS = 1.75
    SIEGE_LIMIT = 90

    def _inside(self, a: Army) -> float:
        """The strength of the men behind the wall this host is sitting at."""
        town = self.world.towns.get(a.at)
        if town is not None:
            return host_strength(town.garrison) + sum(
                host_strength(x.units) for x in self.armies
                if x is not a and x.owner == "player" and x.at == a.at and town.mine)
        s = self.world.settlements.get(a.at)
        return host_strength(s.units) if s else 0.0

    def _siege_holds(self, a: Army) -> bool:
        """Whether a lord's host keeps its lines another day."""
        if a.siege_days > self.SIEGE_LIMIT:
            return False
        if a.siege_days <= self.SIEGE_PATIENCE or a.siege_power > 0:
            return True           # hunger wants its three weeks; engines work
        return host_strength(a.units) >= self.SIEGE_ODDS * self._inside(a)

    #: Days before word of a siege reaches a lord's other towns, and the
    #: share of a garrison he will strip to answer it.
    RELIEF_NEWS = 3
    RELIEF_SHARE = 0.5

    def _relieve_day(self) -> List[str]:
        """A lord with more than one town sends men to the one under siege.

        In Warband a lord whose castle is besieged comes back for it; here a
        lord was never anywhere else, so what comes is half the garrison of
        whichever other town of his is nearest and not itself ringed. Up
        against your lines it stands off and you fight it at dawn; against
        another lord's it walks in, and the odds outside change.
        """
        msgs: List[str] = []
        ringed = {x.at for x in self.armies if x.state == BESIEGING}
        for b in sorted((x for x in self.armies if x.state == BESIEGING),
                        key=lambda x: x.uid):
            town = self.world.towns.get(b.at)
            if town is None or town.mine or b.siege_days < self.RELIEF_NEWS:
                continue
            holder = town.owner or town.key
            if holder == b.owner or holder not in self.world.towns:
                continue
            if any(x.owner == holder and x.home == town.key and x.state == MARCHING
                   for x in self.armies):
                continue                     # already on the road
            sources = sorted(
                (k for k, t in self.world.towns.items()
                 if k != town.key and (t.owner or k) == holder and not t.mine
                 and k not in ringed and k in self.world.coords),
                key=lambda k: (self.world.distance(k, town.key), k))
            if not sources:
                continue
            src = self.world.towns[sources[0]]
            send = {k: v * self.RELIEF_SHARE for k, v in src.garrison.items()
                    if v * self.RELIEF_SHARE >= 0.5}
            if host_strength(send) < 0.25 * host_strength(b.units):
                continue                     # not enough to be worth the road
            for k, n in send.items():
                src.garrison[k] -= n
            src.garrison = {k: v for k, v in src.garrison.items() if v >= 0.5}
            lord = self.world.towns[holder].lord
            a = Army(uid=self.next_army_uid, name=f"{lord}'s relief", owner=holder,
                     units=send, at=src.key, home=town.key)
            self.next_army_uid += 1
            self.armies.append(a)
            self._set_march(a, src.key, town.key, send)
            if b.owner == PLAYER:
                msgs.append(self.note(
                    f"Out of {src.name} a relief marches for {town.name} -- "
                    f"{describe(send)}, {a.days_left:.0f} days out", MOMENTOUS))
        return msgs

    def _siege(self, a: Army) -> List[str]:
        a.siege_days += 1
        if a.owner != "player":
            breaks = not self._siege_holds(a)
        else:
            breaks = a.siege_power <= 0 and a.siege_days > self.SIEGE_PATIENCE
        if breaks:
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
                            place=sh.name, field=self.field_at(key))
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
        self._outfit(a, town.key)
        self._set_march(a, town.key, target, party)
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
        if self.lord.wounded > 0:
            return self.lord.cannot_ride()
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
                season.fixtures.append(lg.Fixture(
                    who=key, target=target, declared=self.day,
                    reason=self._intent_reason(t, target)))
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

    def _intent_reason(self, town, target: str) -> str:
        """Why he says he is going, in the words he would use."""
        if target in self.world.settlements:
            worst = [(label, v) for label, v, _d in self.court.reasons(town.key, self.day)
                     if v < 0]
            if worst:
                return worst[0][0]
            return "your wealth, and his temper"
        other = self.world.towns.get(target)
        if other is not None and other.owner == PLAYER:
            return "it is sworn to you, and thinly held"
        if (self.court.claim_live(town.key, self.day)
                or self.court.claim_live(target, self.day)):
            return "an old claim"
        return "it is the nearest he can take"

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

    #: How much of a besieging host is standing over its own siege works at
    #: any moment, and so what a sortie actually has to fight through.
    #: A siege train is guarded by a detachment, not by the army. Set at a
    #: third, a sortie had to beat sixty-three men to reach a ram in a
    #: two-hundred-man host, which meant the gate was never worth opening.
    #: Of a besieger's baggage, what a successful sortie puts to the torch.
    #: Men who have got in among the engines are standing in the camp, and
    #: his stores are the other thing there is to put a match to.
    #:
    #: A third, which is a great deal against an ordinary besieger carrying
    #: a fortnight -- it leaves him nine days -- and next to nothing against
    #: the one in the siege scenario, who sat down with a year. That is the
    #: intended shape: burning the baggage is how you lift a siege laid by
    #: somebody who was passing, and not how you lift one laid by a man who
    #: came to stay.
    SALLY_BURN = 0.34

    SALLY_GUARD = 0.16

    def shore(self, settlement_key: str = "", on: bool = True) -> str:
        """Work the breach while it is being made.

        Slower than peacetime masonry, nearly twice the stone a yard, and it
        costs men -- masons on a wall somebody is shooting at. Worth it
        against a siege train that is barely out-pacing you and worth
        nothing against one that is not, which is the shape a lever should
        have.
        """
        s = self.world.settlements.get(settlement_key or self.home().name)
        if s is None:
            s = self.home()
        s.shoring = bool(on)
        if not on:
            return f"{s.name}: the masons come off the wall"
        stone = s.market.stock.get("stone", 0.0)
        return (f"{s.name}: masons to the breach"
                + (f" -- {stone:.0f} of stone in store" if stone >= 1
                   else " -- and no stone to do it with"))

    #: How often the sickness appears somewhere on the march by itself,
    #: per day. It has to start somewhere, and it starts abroad: a player
    #: who can be given it out of nowhere has no lever, and this whole
    #: thing is about the lever.
    PLAGUE_ODDS = 0.0016

    def _plague_day(self) -> List[str]:
        """Where the sickness is, where it is going, and when it goes out.

        Three short jobs. Foreign towns burn out on their own clock, the
        same as yours. A cart that came home carrying it hands it over --
        at your gate, which is why shutting the gate is the answer. And
        once in a long while it begins somewhere, abroad, off the map's
        own traffic rather than yours.
        """
        msgs: List[str] = []
        for key, t in self.world.towns.items():
            if t.sick.here and self.day >= t.sick.until:
                t.sick = plague_mod.Sickness()
                t.last_sick = self.day
                if self.known(key)[1] >= 0:
                    msgs.append(f"The sickness has gone out at {t.name}")

        # The carts, coming home.
        for c in self.caravans:
            if not c.carrying_it:
                continue
            where = c.at or ""
            # Wherever it next does business, not only at your own gate.
            # Written as "carries it home" it almost never arrived: the
            # trade layer puts carts on the best pair of foreign markets it
            # can find, so a cart can work a circuit for a year without
            # standing in one of your towns -- two of them carried the
            # sickness for two hundred and eighty days and delivered it
            # nowhere. A cart passes it to the next market it opens its
            # packs in, which is also how it got round a continent.
            place = (self.world.settlements.get(where)
                     or self.world.towns.get(where))
            if place is None:
                continue                       # still on the road
            came_from = c.carrying_it
            c.carrying_it = ""
            if place.sick.here or where == came_from:
                continue
            if getattr(place, "shut", False):
                # It got as far as the gate and no further, which is the
                # whole of what a shut gate buys you.
                msgs.append(f"{c.name} is turned away at the gate of "
                            f"{place.name} -- they had been at "
                            f"{self.world.node_name(came_from)}")
                continue
            if self.day - place.last_sick < plague_mod.IMMUNE:
                continue
            place.sick = plague_mod.takes_hold(self.day, self.pest, came_from)
            if where in self.world.settlements:
                msgs.append(self.note(
                    f"The sickness is in {place.name}. It came up the road "
                    f"from {self.world.node_name(came_from)}, on {c.name}.",
                    MOMENTOUS))
            elif self.known(where)[1] >= 0:
                msgs.append(f"They are ill at {place.name} now -- "
                            f"{c.name} was there")

        # And the traffic that is not yours. A shut gate stops this too --
        # it is the whole of what a shut gate is for, and without this vector
        # the gate protected you from a road your own carts were not on.
        abroad = [t for t in self.world.towns.values() if not t.mine]
        ill = [t for t in abroad if t.sick.here]
        if ill and abroad:
            for key, place in self.world.settlements.items():
                if place.shut or place.sick.here:
                    continue
                if self.day - place.last_sick < plague_mod.IMMUNE:
                    continue
                # Weighted by how near each sick market is, not by how many
                # of them there are. See plague.CARRY: without this a town
                # on the far corner of the map was as dangerous as one you
                # can see from the wall, and the only sane answer to any
                # word at all was to shut and stop trading.
                near = [plague_mod.nearness(self.world.distance(key, t.key))
                        for t in ill]
                whole = sum(plague_mod.nearness(self.world.distance(key, t.key))
                            for t in abroad)
                if whole <= 0.0:
                    continue
                if self.pest.random() >= plague_mod.VISITORS * sum(near) / whole:
                    continue
                came = self.pest.choices(ill, weights=near, k=1)[0]
                place.sick = plague_mod.takes_hold(self.day, self.pest, came.key)
                msgs.append(self.note(
                    f"The sickness is in {place.name}. Somebody brought it "
                    f"up the road from {came.name}.", MOMENTOUS))

        # And once in a while, somewhere out there.
        if self.pest.random() < self.PLAGUE_ODDS:
            free = [t for t in self.world.towns.values()
                    if not t.sick.here
                    and self.day - t.last_sick >= plague_mod.IMMUNE]
            if free:
                t = self.pest.choice(free)
                t.sick = plague_mod.takes_hold(self.day, self.pest)
                if self.known(t.key)[1] >= 0:
                    msgs.append(self.note(
                        f"Word from {t.name}: they are ill there.", MOMENTOUS))
        return msgs

    def shut_gates(self, settlement_key: str = "", on: bool = True) -> str:
        """Close your own gates to the roads.

        No cart comes in and none goes out, so nothing you earn on the road
        you earn, and nothing on the road reaches you. It is the only
        answer to the sickness and it is meant to hurt: a fortnight of no
        trade against a chance of a season of no people.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if s.shut == on:
            return (f"{s.name}'s gates are already shut" if on
                    else f"{s.name}'s gates are already open")
        s.shut = on
        if on:
            return (f"{s.name} shuts its gates. No cart comes or goes, and "
                    f"nothing on the road reaches you.")
        return f"{s.name} opens its gates again. The carts may run."

    def _ground_at(self, node: str) -> Dict[str, int]:
        """The country round a place, wherever the map happens to keep it.

        One reader for both questions -- what a battle here is fought over
        and what a host here can eat -- so the two can never disagree about
        what a place is. Somewhere the map never drew country for gets some
        off its own name, because `fields_of({})` is zero and a map with
        towns that feed nobody is a map where every host starves.
        """
        s = self.world.settlements.get(node)
        if s is not None and s.terrain:
            return dict(s.terrain)
        t = self.world.towns.get(node)
        if t is not None and t.ground:
            return dict(t.ground)
        return carto.ground_from_name(node) if node else {}

    def _larder(self, a: Army) -> Tuple[str, float]:
        """The nearest granary that would send carts to this host, and how
        far the carts have to come. A host's own lord's towns only: nobody
        victuals the man besieging him."""
        mine = ([k for k in self.world.settlements] if a.owner == PLAYER
                else [a.owner] if a.owner in self.world.towns else [])
        mine += [k for k, t in self.world.towns.items()
                 if t.owner == a.owner and k not in mine]
        where = a.at or a.bound_for
        best, far = "", 1e9
        for key in mine:
            if key not in self.world.coords or where not in self.world.coords:
                continue
            d = 0.0 if key == where else self.world.distance(key, where)
            if d < far:
                best, far = key, d
        return best, far

    #: Days of the town's own eating that an army may not touch. Eight, which
    #: on the opening town is about a third of the larder -- enough that a
    #: host marches out with a full baggage train, and not so much that the
    #: town is left with nothing. A host that emptied the larder on its way
    #: through the gate would be a tax on raising one at all, and the town
    #: starving behind you is not a cost anybody chose.
    LARDER_FLOOR = 8.0

    def _draw_rations(self, key: str, want: float) -> float:
        """Take rations out of a granary, in whatever it keeps them as.

        Densest food first: cheese and bread travel and a cart of raw wheat
        is mostly cart. Written the other way round at first, which had a
        host march out with the town's apples and leave the bread -- the
        opposite of what a baggage train is for, and it stripped the variety
        the town's mood is partly made of.

        Counted in the same nourishment the townsfolk are fed in, so
        victualling an army is visibly the bread the town would have eaten.
        An army that fed itself out of nowhere would make the whole granary
        chain decorative.
        """
        if want <= 0:
            return 0.0
        market = None
        keep = 0.0
        s = self.world.settlements.get(key)
        if s is not None:
            market = s.market
            per_head, _mood = C.RATION_LEVELS[s.ration_level]
            keep = per_head * s.population * self.LARDER_FLOOR
        else:
            t = self.world.towns.get(key)
            market = t.market if t is not None else None
        if market is None:
            return 0.0
        dense = sorted((k for k in RATION_GOODS if good(k).nourish > 0),
                       key=lambda k: -good(k).nourish)
        on_hand = sum(market.stock.get(k, 0.0) * good(k).nourish for k in dense)
        spare = max(0.0, on_hand - keep)
        want = min(want, spare)
        got = 0.0
        for good_key in dense:
            if got >= want - 1e-9:
                break
            per = good(good_key).nourish
            have = market.stock.get(good_key, 0.0)
            if have <= 0:
                continue
            take = min(have, (want - got) / per)
            market.take(good_key, take)
            got += take * per
        return got

    def _outfit(self, a: Army, from_key: str) -> None:
        """Fill a host's baggage out of the granary it is leaving.

        Every host, whoever raised it -- theirs as well as yours, and the
        relic parties too. An AI that starves itself is not an opponent, and
        a test found exactly that: the war hosts were provisioned here and
        the pilgrimages were not, because they are made somewhere else. One
        call, at every place an army comes into the world.
        """
        a.stores = min(supply.capacity(a.size),
                       a.stores + self._draw_rations(from_key,
                                                     supply.capacity(a.size)))

    def _feed_host(self, a: Army) -> List[str]:
        """One host's morning.

        A garrison sitting in one of your own towns is not fed here: the
        town already feeds it, because `Settlement._feed` counts soldiers in
        the population that eats. Charging it twice would make a garrison
        the most expensive thing in the game to own.
        """
        where = a.at or a.bound_for
        if a.state == GARRISON and where in self.world.settlements:
            a.fed = "in quarters"
            return []
        men = a.size
        if men <= 0:
            return []
        larder, far = self._larder(a)
        # A host that has stopped has a road behind it; one on the march
        # does not, because carts cannot catch a moving army.
        settled = a.state in (BESIEGING, GARRISON, RAIDING)
        share = supply.convoy_share(far, settled) if larder else 0.0
        carts = 0.0
        if share > 0:
            asked = share * men * supply.MARCH_RATION
            carts = self._draw_rations(larder, asked)
        grazed = self.world.grazed.get(where, 0.0)
        ration, a.stores, grazed = supply.eat(
            men, a.stores, ground=self._ground_at(where),
            season=self.season, grazed=grazed, carts=carts)
        if where:
            self.world.grazed[where] = grazed
        a.fed = ration.words()
        msgs: List[str] = []
        if ration.deserted >= 0.5:
            gone = self._thin(a, ration.deserted)
            if gone >= 1 and (a.owner == PLAYER or self.day % 3 == 0):
                msgs.append(f"{a.name} is short of food -- {gone:.0f} men "
                            f"gone in the night")
        return msgs

    def _thin(self, a: Army, men: float) -> float:
        """Take men off a host, spread over what it has. They go home rather
        than die: a starved host is beaten without a battle, which is most
        of what starving one is for."""
        total = a.size
        if total <= 0 or men <= 0:
            return 0.0
        gone = 0.0
        for key in list(a.units):
            share = a.units[key] / total
            off = min(a.units[key], men * share)
            a.units[key] -= off
            gone += off
        a.prune()
        return gone

    def field_at(self, node: str) -> Field:
        """Where and when a battle here would be fought.

        The ground comes off the map -- the same slots the cartographer laid
        down and the same ones that chose the roofline -- and the weather
        off the day, so both are things the player can look at before he
        commits rather than things he reads about afterwards. A place he has
        never been is still country: `going_of` falls back to the name.
        """
        ground = self._ground_at(node)
        return Field(going=going_of(ground, node),
                     weather=sky_on(self.season, self.day, self.seed),
                     place=self.world.node_name(node) or node)

    def fire_baggage(self, settlement_key: str = "", men: int = 0) -> str:
        """Out of the gate at his wagons rather than at his engines.

        The small party's answer, and the reason the size of a sortie is a
        decision at all. At the works you have to beat the watch standing
        over the engines, so too few men is men thrown away. Here you have
        to beat nobody: you have to arrive, fire the wagons and get back, so
        the only thing that matters is not being seen -- and the fewer you
        send the likelier that is and the less it costs you when it is not.

        It does nothing to his rams. What it does is make his own supply the
        thing that runs out first, which is how most sieges that failed
        actually failed, and which was not a thing that could be done to
        anybody until hosts had to eat.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if not s.besieged:
            return f"{s.name} is not besieged"
        foe = self._besieger_of(s)
        if foe is None:
            return "there is nobody outside to go at"
        have = sum(s.units.values())
        if have < 1:
            return f"{s.name} has nobody to send out"
        share = 1.0 if men <= 0 else max(0.05, min(1.0, men / have))
        going = {k: v * share for k, v in s.units.items() if v * share >= 0.5}
        if not going:
            return "too few to be worth opening the gate for"
        if foe.stores <= 1.0:
            return (f"there is nothing left in that camp to burn -- "
                    f"{self.world.node_name(foe.owner)} is living off the country")

        odds = sortie_odds(share, self.field_at(self._key_of(s)).weather,
                           foe.siege_days, s.sorties)
        caught = self.rng.random() < odds.surprise
        s.sorties += 1
        said = [f"{s.name} sends men over the wall at the wagons -- "
                + ("nobody sees them go" if caught
                   else "and the camp is up before they are halfway")]
        if caught:
            burnt = min(0.85, military.RAID_BURN_BASE
                        + military.RAID_BURN_PER * share) * foe.stores
            foe.stores = max(0.0, foe.stores - burnt)
            left = supply.days_left(foe.size, foe.stores)
            said.append(f"The baggage of {self.world.node_name(foe.owner)} "
                        f"burns: {left:.0f} days of food left in that camp")
            # Not free. Somebody has to hold the wagon line while the rest
            # work, and men who go out at night do not all come back.
            lost = self._thin_garrison(s, going, 0.10)
            if lost >= 1:
                said.append(f"{lost:.0f} did not come back")
        else:
            # A running fight to the gate rather than a battle, against
            # whatever turned out -- which for a small party is everybody.
            out = Side(dict(going),
                       attack_mult=self.progress.mult("attack")
                       * self.kin.mult("attack", -1),
                       defense_mult=self.progress.mult("defense"))
            guard = {k: n * odds.roused for k, n in foe.units.items()
                     if UNITS[k].siege_power <= 0 and k != "engineer"}
            them = Side({k: v for k, v in guard.items() if v >= 0.5})
            res = fight(out, them, rng=self.rng,
                        max_rounds=military.RAID_ROUNDS,
                        place=f"the wagon lines before {s.name}",
                        field=self.field_at(self._key_of(s)))
            for key in list(s.units):
                s.units[key] -= going.get(key, 0.0)
                s.units[key] = max(0.0, s.units[key] + out.units.get(key, 0.0))
            for key in list(foe.units):
                met = guard.get(key, 0.0)
                if met:
                    foe.units[key] = max(0.0, foe.units[key] - met
                                         + them.units.get(key, 0.0))
            foe.units = {k: v for k, v in foe.units.items() if v >= 0.5}
            said.append(self._box_score(f"{s.name} raids the wagons", res,
                                        PLAYER, foe.owner))
            said.append("They are driven off the wagon lines with nothing fired")
        self.battles += said
        return "\n".join(said)

    def _besieger_of(self, s: Settlement) -> Optional[Army]:
        """The host sitting round this town, or None."""
        outside = [a for a in self.armies
                   if a.owner != PLAYER and a.at == self._key_of(s)
                   or (a.owner != PLAYER and a.state == BESIEGING
                       and self.world.node_name(a.at) == s.name)]
        return max(outside, key=lambda a: a.size) if outside else None

    def _thin_garrison(self, s: Settlement, went: Dict[str, float],
                       rate: float) -> float:
        """Take a toll off the men who went out, spread over what went."""
        gone = 0.0
        for key, n in went.items():
            off = min(s.units.get(key, 0.0), n * rate)
            s.units[key] = max(0.0, s.units.get(key, 0.0) - off)
            gone += off
        s.units = {k: v for k, v in s.units.items() if v >= 0.5}
        return gone

    def sally(self, settlement_key: str = "", men: int = 0) -> str:
        """Out of the gate at the siege works.

        The other lever, and the opposite of shoring: you give up the wall
        entirely for one fight in the open, to get at the engines. Win and
        the rams and the engineers are gone and the siege has to start
        again; lose and you have spent the garrison that was holding the
        wall-walk.

        A gamble, and for a long time it was not one: it met a fixed share
        of the besieging host whatever the defender did, so any garrison
        walked out, beat a detachment it outnumbered, burnt the rams and
        went back in -- a hundred wins out of a hundred, measured. What it
        turns on now is whether the camp is caught, and that is bought and
        sold with things the player chooses: how many men he sends, what the
        sky is doing, how long the besieger has been sitting there, and
        whether he has tried this before. See `military.sortie_odds`.

        The trade at the middle of it is the size of the party. A small one
        slips out and may not be enough to do the work; a large one does the
        work and is watched forming up.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if not s.besieged:
            return f"{s.name} is not besieged"
        outside = [a for a in self.armies
                   if a.owner != "player" and a.at == getattr(s, "key", "")
                   or (a.owner != "player" and a.state == BESIEGING
                       and self.world.node_name(a.at) == s.name)]
        if not outside:
            return "there is nobody outside to sally against"
        foe = max(outside, key=lambda a: a.size)
        have = sum(s.units.values())
        if have < 1:
            return f"{s.name} has nobody to send out"
        share = 1.0 if men <= 0 else max(0.05, min(1.0, men / have))
        going = {k: v * share for k, v in s.units.items() if v * share >= 0.5}
        if not going:
            return "too few to be worth opening the gate for"
        # No battlement: that is the whole cost of coming out from behind it.
        out = Side(dict(going),
                   attack_mult=self.progress.mult("attack")
                   * self.kin.mult("attack", -1),
                   defense_mult=self.progress.mult("defense"))
        # What turns out to meet you. Caught, it is the guard over the
        # engines; roused, it is most of his host, in the open, with no wall
        # at your back. The roll is made here rather than read off the odds
        # so that the odds shown before are the odds actually run.
        odds = sortie_odds(share, self.field_at(self._key_of(s)).weather,
                           foe.siege_days, s.sorties)
        caught = self.rng.random() < odds.surprise
        s.sorties += 1
        met_share = odds.quiet if caught else odds.roused
        works, guard = {}, {}
        for key, n in foe.units.items():
            if UNITS[key].siege_power > 0 or key == "engineer":
                works[key] = n
            else:
                guard[key] = n * met_share
        met = {k: v for k, v in list(works.items()) + list(guard.items())
               if v >= 0.5}
        them = Side(dict(met))
        if caught:
            # Among them before they have formed. This is what makes a small
            # party worth sending: without it, stealth bought you nothing you
            # could fight with, and the only answer was to send everybody.
            out.attack_mult *= military.SORTIE_CAUGHT_ATTACK
            them.morale *= military.SORTIE_CAUGHT_MORALE
        # The works are outside the gate, so a sortie is fought on the town's
        # own ground and under the day's own sky -- which is the argument for
        # going out in a hard frost and not in April.
        out_field = replace(self.field_at(self._key_of(s)),
                            place=f"the works before {s.name}")
        res = fight(out, them, rng=self.rng, orders=(getattr(s, "order", "") or STORM,
                                                     foe.order), field=out_field)
        said = [f"{s.name} opens the gate -- "
                + ("the camp is asleep" if caught
                   else "and the camp is up and waiting")]
        # What came back, on both sides. The guard that was not at the works
        # was never in this fight and is still out there.
        for key in list(s.units):
            s.units[key] -= going.get(key, 0.0)
            s.units[key] = max(0.0, s.units[key] + out.units.get(key, 0.0))
        for key in list(foe.units):
            fought = met.get(key, 0.0)
            if fought:
                foe.units[key] = max(0.0, foe.units[key] - fought
                                     + them.units.get(key, 0.0))
        foe.units = {k: v for k, v in foe.units.items() if v >= 0.5}
        said.append(self._box_score(f"{s.name} sallies", res, PLAYER, foe.owner))
        if res.winner == "attacker":
            # The engines are what you came for, and they do not run. Count
            # what was standing there before rather than what is left to
            # burn: the fight itself kills most of it, and reading the
            # remainder reported a successful sortie as burning "no one".
            gone = {k: n for k, n in works.items()
                    if n - foe.units.get(k, 0.0) >= 0.5}
            for key, n in gone.items():
                gone[key] = n - foe.units.get(key, 0.0)
            for key in list(works):
                foe.units.pop(key, None)
            for key, n in works.items():
                if key not in gone:
                    gone[key] = n
            foe.siege_days = 0
            foe.siege = type(foe.siege)()
            said.append(f"The works before {s.name} are burnt"
                        + (": " + describe(gone) if gone else ""))
            # And the baggage behind them. Men who have got in among the
            # engines are standing in the camp, and a besieger's stores are
            # the other thing there is to put a torch to -- which is what
            # actually lifted sieges. It gives the defender a second way to
            # spend a sortie: burn his month rather than his rams.
            burnt = foe.stores * self.SALLY_BURN
            if burnt > 0:
                foe.stores -= burnt
                days = supply.days_left(foe.size, foe.stores)
                said.append(f"His baggage burns with them -- "
                            f"{days:.0f} days of food left in that camp")
        else:
            said.append(f"The sally is thrown back under the walls of {s.name}")
        self.battles += said
        return "\n".join(said)

    def order_host(self, uid: int, key: str) -> str:
        """Tell a host how to fight before it has to."""
        from .military import ORDERS, order as order_of, order_note
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != "player":
            return "that host is not yours to order"
        if key not in ORDERS:
            return (f"there is no order called {key!r}; try "
                    + ", ".join(ORDERS))
        a.order = key
        return f"{a.name}: {order_of(key).name}. {order_note(a.units, key)}"

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
        if a.owner == "player" and not town.mine:
            # Written down at last: `raided_them` was in the book and nothing
            # ever put it there, so burning a lord's country cost you nothing
            # he would remember past his temper.
            self.court.write(town.key, "raided_them", -3.0 * worked, self.day)
            self.court.reckon(town.key, 1.0 * worked)
            if self.court.ground_for(town.key, self.day) is None:
                others = [k for k, x in self.world.towns.items()
                          if not x.mine and k != town.key]
                self.court.write_all(others, "unjust", -0.6 * worked, self.day)
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
        # A wall that has thrown one storm back is readier for the next:
        # Warband's siege hardness, a point of battlement a little under
        # every seventeen of it, and wearing off by two a day.
        holder = Side(defenders, battlement=8.0 * (
            1.0 if town.mine else lordly.sort_of(town.key).holds)
            + town.hardened * 0.06)
        works = town.works()
        if not player:
            a.siege.plan = choose(works, siege_power=a.siege_power,
                                  engineers=a.units.get("engineer", 0.0),
                                  host=a.size, garrison=sum(town.garrison.values()),
                                  wall=town.wall_hp, wall_max=town.wall_max,
                                  patient=a.siege_days > 8, days=a.siege_days)
        wall, _la, _ld, lines = siege_day(besieger, holder, town.wall_hp, self.rng,
                                          town.name, wall_max=town.wall_max,
                                          works=works, state=a.siege,
                                          faith=town.faith())
        town.wall_hp = wall
        if player:
            town.hostility = C.HOSTILITY_WAR
        if self.day % 5 == 0 and lines and (player or town.mine):
            msgs.append(f"{a.name}: {lines[0]}")
        msgs += self._starve_town(town, a, holder, player)
        if not town.mine and holder.alive():
            msgs += self._sally_at(town, a, holder, besieger, player)
        if storms_now(a.siege.plan, wall, holder.alive()):
            battle = open_battle(besieger, holder, rng=self.rng, place=town.name,
                                 orders=(a.order, lordly.sort_of(town.key).fights),
                                 field=self.field_at(town.key), works=works,
                                 state=a.siege, wall_max=town.wall_max)
            # Yours to fight if you are going in or it is yours to hold.
            # Two lords at each other's walls is nobody's business but
            # theirs, and resolves at once as it always has.
            if (player or town.mine) and self.battles_mode == "play":
                self.pending = PendingBattle(
                    battle=battle, kind="storm", army=a.uid, where=town.key,
                    side="attacker" if player else "defender",
                    title=town.name, day=self.day,
                    stationed=[x.uid for x in stationed],
                    wall_standing=wall, wall_full=town.wall_max)
                msgs.append(self.note(
                    f"*** THE STORM GOES IN AT {town.name.upper()}. "
                    f"The day waits on it. ***", MOMENTOUS))
                return msgs
            battle.run()
            battle.close()
            return msgs + self._after_storm(battle.res, a, town, holder,
                                            besieger, stationed)
        self._settle_survivors(a, town, holder, stationed)
        return msgs

    def _after_storm(self, res, a: Army, town, holder: Side, besieger: Side,
                     stationed: List[Army]) -> List[str]:
        """What follows an assault on a foreign wall, whoever fought it.

        One function for the fight resolved at once and the fight resolved
        a round at a time, because two copies of "what happens when a town
        falls" is one of them forgetting the relics.
        """
        msgs: List[str] = []
        player = a.owner == "player"
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
        elif res.broken_off == "attacker":
            # A storm called off is not a storm thrown back. He is still at
            # the wall, and he has kept most of his men to try again with.
            town.hardened = min(200.0, town.hardened + 40.0)
            msgs.append(f"{a.name} calls off the storm and draws back to the "
                        f"lines before {town.name}")
        elif player:
            a.state = RETURNING
            town.hardened = min(200.0, town.hardened + 100.0)
            self.court.reckon(town.key, -20.0)
            msgs.append(f"{a.name} is thrown back from {town.name}, and the "
                        f"men on its wall have learned how it is done")
            # He was standing where the arrows were. Sometimes that tells.
            if self.lord.riding == a.uid:
                msgs += self._lord_fell()
            self.march(a.uid, a.home)
        else:
            a.state = RETURNING
            town.hardened = min(200.0, town.hardened + 100.0)
            if a.owner in self.world.towns:
                # A letter is easier to sign than to keep. Every host of
                # theirs you break takes a bite out of the reason it was
                # written, which is the one way out that is not money.
                self.court.write(a.owner, "beaten", 22.0, self.day)
                self.court.reckon(a.owner, 20.0)
                line = lordly.says(a.owner, "beaten", self.voice)
                if line:
                    msgs.append(f'    {self.world.towns[a.owner].lord}: '
                                f'"{line}"')
            self.march(a.uid, a.home)
        town.wall_hp = max(town.wall_hp, town.wall_max * 0.15)
        self._settle_survivors(a, town, holder, stationed)
        return msgs

    def _starve_town(self, town, a: Army, holder: Side, player: bool) -> List[str]:
        """A garrison that has eaten the town's larder starts to die of it.

        Warband wounds a starving garrison one day in ten; here it thins a
        little every day the granary stands under a fifth of what the town
        wants, which is a blockade's whole argument: you do not have to
        carry the wall if you can wait for the men on it to stop standing.
        """
        food = sum(v for k, v in town.market.stock.items() if good(k).nourish > 0)
        want = sum(v for k, v in town.market.target.items() if good(k).nourish > 0)
        if want <= 0 or food >= 0.2 * want:
            return []
        for k in list(holder.units):
            holder.units[k] *= 0.975
        town.garrison = {k: v for k, v in holder.units.items() if v >= 0.5}
        if self.day % 5 == 0 and (player or town.mine):
            return [f"{town.name} is starving: the granary is bare and the "
                    f"garrison thins by the day"]
        return []

    def _sally_at(self, town, a: Army, holder: Side, besieger: Side,
                  player: bool) -> List[str]:
        """A lord's garrison goes out at the lines, now and then.

        Only the player ever sallied; a lord sat behind his wall until it
        fell. Stronghold's lords keep men for exactly this. A garrison near
        the besiegers' strength goes out one day in twenty-five or so, after
        the first few days, hurts the lines and comes back lighter.
        """
        if a.siege_days < 4:
            return []
        if host_strength(holder.units) < 0.5 * host_strength(besieger.units):
            return []
        dice = random.Random(f"{self.seed}:sally:{town.key}:{self.day}")
        if dice.random() > 0.04 * lordly.sort_of(town.key).holds:
            return []
        hurt = {k: v * 0.06 for k, v in a.units.items()}
        a.units = {k: v - hurt[k] for k, v in a.units.items() if v - hurt[k] >= 0.5}
        for k in list(holder.units):
            holder.units[k] *= 0.97
        town.garrison = {k: v for k, v in holder.units.items() if v >= 0.5}
        if player:
            return [f"{town.name}'s garrison sallies against your lines at "
                    f"dawn -- {describe({k: round(v) for k, v in hurt.items() if v >= 0.5}) or 'a few men'} lost"]
        return []

    def _settle_survivors(self, a: Army, town, holder: Side,
                          stationed: List[Army]) -> None:
        """Casualties fall on the stationed hosts first, then on the town levy."""
        a.prune()
        survivors = dict(holder.units)
        for x in stationed:
            for k in list(x.units):
                share = min(x.units[k], survivors.get(k, 0.0))
                survivors[k] = survivors.get(k, 0.0) - share
                x.units[k] = share
            x.prune()
        town.garrison = {k: v for k, v in survivors.items() if v >= 0.5}

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
                      battlement=6.0 + s.effect("battlement") + s.hardened * 0.06
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
                                  patient=a.siege_days > 8, days=a.siege_days)
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
        # A hungry town is a town whose soldiers are hungry too.
        if s.report is not None and s.report.hunger > 0.5 and s.units:
            thin = 0.02 * s.report.hunger
            s.units = {k: v * (1 - thin) for k, v in s.units.items() if v * (1 - thin) >= 0.5}
            holder = Side(s.units, attack_mult=holder.attack_mult,
                          defense_mult=holder.defense_mult,
                          battlement=holder.battlement)
            if self.day % 5 == 0:
                msgs.append(f"{s.name} is starving, and the garrison thins with "
                            f"the town -- {s.report.hunger:.0%} of the ration "
                            f"going unserved")
        if storms_now(a.siege.plan, wall, holder.alive()):
            # Your own wall: whatever you told the garrison to do.
            battle = open_battle(besieger, holder, rng=self.rng, place=s.name,
                                 orders=(a.order, getattr(s, "order", "") or HOLD),
                                 field=self.field_at(self._key_of(s)),
                                 works=works, state=a.siege,
                                 have_pitch=s.market.stock.get("charcoal", 0) >= 5,
                                 wall_max=s.wall_max(self.progress))
            if self.battles_mode == "play":
                self.pending = PendingBattle(
                    battle=battle, kind="wall", army=a.uid,
                    where=self._key_of(s), side="defender", title=s.name,
                    day=self.day, wall_standing=wall,
                    wall_full=s.wall_max(self.progress))
                msgs.append(self.note(
                    f"*** THE STORM GOES IN AT {s.name.upper()}. "
                    f"The day waits on it. ***", MOMENTOUS))
                return msgs
            battle.run()
            battle.close()
            msgs += self._after_wall(battle.res, a, s, holder, besieger)
        return msgs

    def _after_wall(self, res, a: Army, s: Settlement, holder: Side,
                    besieger: Side) -> List[str]:
        """What follows an assault on your own wall, however it was fought."""
        msgs: List[str] = []
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
            if a.owner in self.world.towns:
                self.court.reckon(a.owner, -30.0)
            msgs.append(self._sack(s, a))
        elif res.broken_off == "attacker":
            s.hardened = min(200.0, s.hardened + 40.0)
            msgs.append(f"The storm is called off before {s.name}; the host "
                        f"draws back to its lines")
            a.siege_days = 0
        else:
            s.hardened = min(200.0, s.hardened + 100.0)
            if a.owner in self.world.towns:
                self.court.reckon(a.owner, 25.0)
            msgs.append(f"The host is broken beneath the walls of {s.name}; "
                        f"the men on it have learned how it is done")
            if a in self.armies:
                self.armies.remove(a)
            if a.home in self.world.towns:
                self.world.towns[a.home].hostility = 25.0
        s.wall_hp = max(s.wall_hp, s.wall_max(self.progress) * 0.10)
        return msgs

    # --------------------------------------------------------- the battle
    def battle_step(self, action: str = "fight", arg: str = "") -> str:
        """Do one thing in the fight the day is waiting on.

        `fight` is a round. `auto` is the rest of it. The others are the
        levers -- an order, the reserve, the oil, the pitch, breaking off --
        each of which the Battle itself decides whether you may pull, so
        the console and the picture cannot disagree about that.
        """
        pb = self.pending
        if pb is None:
            return "there is no fight waiting on you"
        b, me = pb.battle, pb.side
        if action == "close":
            if not b.over:
                return "the fight is not over"
            self.pending = None
            return "back to the day"
        if b.over:
            return "\n".join(pb.after) or "the fight is over"
        if action == "fight":
            said = "\n".join(b.step()) or "a quiet round"
        elif action == "auto":
            b.run()
            said = "\n".join(b.res.log[-3:])
        elif action == "order":
            said = b.reorder(me, arg)
        elif action == "commit":
            said = b.commit(me)
        elif action in ("oil", "pitch"):
            if me != "defender":
                said = "you are not the one on the wall"
            else:
                said = b.pour_oil() if action == "oil" else b.fire_pitch()
        elif action == "break":
            said = b.break_off(me)
        elif action == "ride":
            said = self._ride(pb, arg)
        else:
            return (f"battle: nothing called {action!r}; fight, ride, auto, order, "
                    f"commit, oil, pitch, break, close")
        if b.over:
            said += "\n" + "\n".join(self._finish_battle())
        return said

    # ------------------------------------------------------ at their head
    def _lord_in(self, pb: PendingBattle) -> str:
        """Why the lord is not in this fight to ride at their head, or ''."""
        why = self.lord.cannot_ride()
        if why:
            return why
        if pb.kind == "wall":
            if not (self.lord.at_home and self.lord.seat in ("", pb.where, pb.title)):
                return f"{self.lord.name} is not at {pb.title}"
            return ""
        mine = [pb.army] if pb.kind == "storm" else (
            pb.stationed if pb.side == "attacker" else pb.foes)
        if self.lord.riding not in mine:
            return f"{self.lord.name} is not with this host"
        return ""

    def _ride_view(self, pb: PendingBattle) -> dict:
        """What riding at their head would meet this round, for the screen
        that fights it and the console that rolls it."""
        b = pb.battle
        them = b.side("defender" if pb.side == "attacker" else "attacker")
        why = self._lord_in(pb)
        who = self.kin.lord
        valour = who.level("valour") if who is not None else 0
        horse = them.class_share().get(military.HORSE, 0.0)
        press = int(min(9, 3 + them.alive() / 25.0 + 3 * horse))
        return {"can": not why and not b.over, "why": why, "name": self.lord.name,
                "valour": valour, "hits": self.lord.hits,
                "down": manly.RIDE_HITS_DOWN, "press": press,
                "cap": self._ride_cap(them), "rode": pb.lord_rode,
                "kills": pb.lord_kills}

    @staticmethod
    def _ride_cap(them: Side) -> int:
        return max(1, min(manly.RIDE_KILL_CAP, int(them.alive() * manly.RIDE_KILL_SHARE)))

    def _roll_ride(self, pb: PendingBattle) -> Tuple[int, int]:
        """The dice ride for him where there is no screen: the console."""
        v = self._ride_view(pb)
        rng = pb.battle.rng
        p_kill = min(0.8, 0.35 + 0.05 * v["valour"])
        p_hit = max(0.08, 0.30 - 0.03 * v["valour"])
        kills = sum(1 for _ in range(v["cap"]) if rng.random() < p_kill)
        hits = sum(1 for _ in range(v["press"]) if rng.random() < p_hit)
        return kills, min(hits, manly.RIDE_HITS_DOWN)

    def _ride(self, pb: PendingBattle, arg: str) -> str:
        """Fight this round at the head of your own men.

        `arg` is what the screen saw -- "kills hits" -- or nothing, in
        which case the dice ride. Either way the engine believes only so
        much: kills are capped at an order's worth of the men facing him,
        blows count against the three that bear him down, and the round
        then runs as any round does. His men, seeing him in front, are a
        little steadier; he learns valour by doing it; and if he is borne
        down he is abed for weeks or dead where he stood.
        """
        b = pb.battle
        why = self._lord_in(pb)
        if why:
            return why
        parts = arg.split()
        if len(parts) >= 2 and all(x.lstrip("-").isdigit() for x in parts[:2]):
            kills, hits = int(parts[0]), int(parts[1])
        else:
            kills, hits = self._roll_ride(pb)
        them = b.side("defender" if pb.side == "attacker" else "attacker")
        mine = b.side(pb.side)
        kills = max(0, min(kills, self._ride_cap(them)))
        hits = max(0, min(hits, manly.RIDE_HITS_DOWN))
        # The men he cut down come off the line facing him, foot first.
        left = float(kills)
        for key in sorted(them.units, key=lambda k: (UNITS[k].unit_class != military.FOOT, k)):
            take = min(them.units[key], left)
            them.units[key] -= take
            left -= take
            if left <= 0:
                break
        them.units = {k: v for k, v in them.units.items() if v >= 0.5}
        gain = min(manly.RIDE_RALLY, manly.RIDE_RALLY_CAP - pb.lord_rally)
        if gain > 0:
            mine.morale += gain
            pb.lord_rally += gain
        pb.lord_rode += 1
        pb.lord_kills += kills
        self.lord.hits += hits
        self.kin.teach("valour", manly.VALOUR_PER_RIDE + 2.0 * kills, self.day)
        blow = ("no blow taken" if hits == 0 else "one blow taken" if hits == 1
                else f"{hits} blows taken")
        said = [f"{self.lord.name} rides at their head: "
                f"{kills} {'man' if kills == 1 else 'men'} cut down, {blow}"]
        if self.lord.hits >= manly.RIDE_HITS_DOWN:
            heir = self.kin.heir(self.day)
            fell = self.lord.borne_down(self.rng, heir.name if heir else self.lord.name)
            pb.lord_lines += fell
            said += [self.note(ln, MOMENTOUS) for ln in fell]
            if not self.lord.alive:
                who = self.kin.lord
                if who is not None:
                    pb.lord_lines += self.kin.bury(who, self.day)
                for st in self.world.settlements.values():
                    st.popularity = max(0.0, st.popularity - manly.MOURNING)
        said += b.step() or ["a quiet round"]
        return "\n".join(said)

    def _finish_battle(self) -> List[str]:
        """The fight is over: take the dressing off and let the day have it.

        The aftermath runs once, here, and is kept on the fight rather than
        the fight being thrown away -- see PendingBattle.after. The next day
        puts it away; so does `battle close`.
        """
        pb = self.pending
        if pb is None:
            return []
        if pb.settled:
            return list(pb.after)
        b = pb.battle
        b.close()
        a = self.army(pb.army)
        msgs: List[str] = []
        if a is None:
            msgs.append("the host that was going in is gone")
        elif pb.kind == "field":
            relief = [x for x in (self.army(u) for u in pb.stationed) if x]
            ring = [x for x in (self.army(u) for u in pb.foes) if x]
            if relief and ring:
                msgs = self._after_field(b.res, pb.where, relief, ring,
                                         b.attacker, b.defender)
        elif pb.kind == "wall":
            s = self.world.settlements.get(pb.where)
            if s is not None:
                msgs = self._after_wall(b.res, a, s, b.defender, b.attacker)
        else:
            town = self.world.towns.get(pb.where)
            stationed = [x for x in (self.army(u) for u in pb.stationed) if x]
            if town is not None:
                msgs = self._after_storm(b.res, a, town, b.defender, b.attacker,
                                         stationed)
        if pb.lord_rode:
            msgs.append(f"{self.lord.name if self.lord.alive else 'The lord'} rode "
                        f"{pb.lord_rode} {'round' if pb.lord_rode == 1 else 'rounds'} at "
                        f"their head and cut down {pb.lord_kills} "
                        f"{'man' if pb.lord_kills == 1 else 'men'} by his own hand")
            msgs += [ln for ln in pb.lord_lines if ln not in msgs]
        self.lord.hits = 0
        pb.after = list(msgs)
        pb.settled = True
        for line in msgs:
            if line.strip().startswith("box"):
                self.battles.append(line.strip())
        return msgs

    def battle_view(self) -> Optional[dict]:
        """The fight, as a screen needs it -- or None when the day is not
        waiting on one."""
        pb = self.pending
        if pb is None:
            return None
        b = pb.battle
        v = b.snapshot()
        mine = b.side(pb.side)
        v.update({"kind": pb.kind, "side": pb.side, "title": pb.title,
                  "day": pb.day, "after": list(pb.after),
                  "wall_standing": round(pb.wall_standing, 1),
                  "wall_full": round(pb.wall_full, 1),
                  "field": b.field_words,
                  "can": b.can(pb.side),
                  "orders": [{"key": o.key, "name": o.name, "blurb": o.blurb,
                              "rounds": o.rounds}
                             for o in military.ORDERS.values()],
                  "modifiers": self._battle_modifiers(pb),
                  "ride": self._ride_view(pb),
                  "kinds": {k: {"name": u.name, "kind": u.unit_class,
                                "counters": dict(u.counters)}
                            for k in set(b.attacker.units) | set(b.defender.units)
                            for u in [UNITS[k]]},
                  "costs": {"reorder": military.REFORM_COST,
                            "commit": military.COMMIT_PUNCH,
                            "break": military.ROUT_TOLL}})
        return v

    def _battle_modifiers(self, pb: PendingBattle) -> List[dict]:
        """Every dial your side is fighting under, as rows a screen can show.

        Shown rather than hidden, which is the one thing worth taking from
        the Paradox battle screen: the numbers are small and they are the
        whole difference in a close fight, so the player is owed them.
        """
        b = pb.battle
        mine = b.side(pb.side)
        o = military.order(b.orders[0] if pb.side == "attacker" else b.orders[1])
        rows: List[dict] = []
        if b.field_words:
            rows.append({"what": "the field", "value": b.field_words, "good": None})
        # Only the kinds you actually have: telling a garrison with no horse
        # what the mud would do to its horse is noise (see field_note).
        have = mine.class_share()
        for cls, v in sorted(mine.class_mult.items()):
            if abs(v - 1.0) > 0.004 and have.get(cls, 0.0) >= 0.02:
                rows.append({"what": f"your {cls} on this ground",
                             "value": f"{v:.2f}", "good": v > 1.0})
        rows.append({"what": f"order: {o.name}",
                     "value": f"attack {o.attack:.2f} · defence {o.defense:.2f} "
                              f"· steadiness {o.morale:.2f}",
                     "good": None})
        if mine.battlement:
            rows.append({"what": "the battlement", "value": f"+{mine.battlement:.1f}",
                         "good": True})
        w = b.works
        if w is not None and pb.side == "defender":
            if w.towers:
                rows.append({"what": "towers", "value": str(w.towers), "good": True})
            if w.oil:
                rows.append({"what": "oil over the gate",
                             "value": "spent" if b.oil_spent else "ready", "good": not b.oil_spent})
            if w.pitch:
                spent = b.pitch_spent or (b.state is not None and b.state.pitch_spent)
                rows.append({"what": "the pitch ditch",
                             "value": "burned" if spent else ("ready" if b.have_pitch else "no charcoal"),
                             "good": (not spent) and b.have_pitch})
        # Read off the snapshot, not the side: once the fight is closed the
        # side wears its pre-battle dial again and would say 1.00.
        now = b.snapshot()[pb.side]["morale"]
        rows.append({"what": "steadiness now", "value": f"{now:.2f}", "good": now >= 0.6})
        return rows

    def _sack(self, s: Settlement, a: Army) -> str:
        """A storming is a catastrophe, not a trapdoor.

        The keep is thrown down and the town gutted, but so long as you hold
        ground anywhere you are still in the game -- which is the whole argument
        for founding a second settlement before you need one.
        """
        self._sacked += 1
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
        loser = town.key
        town.owner = "player" if a.owner == "player" else a.owner
        town.hostility = 0.0
        town.ambition = 0.0
        town.loyalty = 35.0
        # A lord with no hall has no host. Whatever of his is still in the
        # field goes over to whoever holds the hall now, or, if that is you,
        # goes home to farms that are not his any more.
        for x in list(self.armies):
            if x is a or x.owner != loser or x.errand:
                continue
            if a.owner == "player":
                self.armies.remove(x)
            else:
                x.owner = a.owner
                x.home = a.owner if a.owner in self.world.towns else x.home
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
                # And kin mind more than strangers: a town of their own
                # people taken is a thing done to them, EU4's culture rule.
                kin = 1.3 if other.culture and other.culture == town.culture else 0.9
                self.court.write(key, "took_town",
                                 -34.0 * lawful * close * kin
                                 * lordly.sort_of(key).temper,
                                 self.day)
            self.court.reckon(town.key, 40.0)
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
            t.grow(self.rng, besieged=key in besieged, day=self.day)
            if t.truce_days > 0:
                t.truce_days -= 1
            if t.mine:
                said = self._loyalty_day(key, t)
                if said:
                    msgs.append(said)
                revolt = self._revolt(key, t)
                if revolt:
                    msgs.append(revolt)
                continue
            self._keep_the_chest(key, t)
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
                                * (0.6 + 0.8 * self._week_mood(key, "temper")))
                t.hostility = max(0.0, t.hostility - t.favour * 0.02
                                  - self.kin.bonus("cooling"))
            if t.hostility >= C.HOSTILITY_WAR:
                said = self._reckon_war(key, t, pressure)
                if said:
                    msgs.append(said)
                continue

            # -- offence taken at each other --------------------------------
            t.ambition += (C.AMBITION_DRIFT * t.aggression * pressure
                           * (0.5 + self._week_mood(key, "ambition")))
            if t.ambition < C.HOSTILITY_WAR or rival_wars >= self.MAX_RIVAL_WARS:
                continue
            # Patience, Warband's way: a lord who has gathered his men and
            # found nobody weak enough settles for a little less each time,
            # rather than stand his host down and start the year again.
            prey = self._prey_for(key, 0.8 + 0.05 * min(6, t.waited))
            if prey is None:
                t.ambition = 60.0
                t.waited += 1
                continue
            t.waited = 0
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
        msgs += self._peace_day()
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
            if c.opinion(key, day) <= 0 or c.trust_of(key) < c.TRUST_LAPSE:
                c.allies.remove(key)
                c.write(key, "ally", -10.0, day)
                why = ("does not trust your word"
                       if c.trust_of(key) < c.TRUST_LAPSE else "has cooled")
                msgs.append(self.note(f"{t.lord} of {t.name} {why} and lets "
                                      f"the alliance lapse."))
        msgs += self._aid_day()
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

    #: How long a lord's suit for peace stands, and how long an ally waits
    #: before sending men again.
    SUIT_DAYS = 20
    AID_EVERY = 120

    def _aid_day(self) -> List[str]:
        """Allies come when you are attacked -- which the alliance always
        promised and nothing did. A host of theirs marching on or sitting
        before a town of yours is the call; each ally answers it one day in
        twelve or so, and sends men under your command, marching from his
        gate to yours. You feed them: that is what an alliance costs."""
        msgs: List[str] = []
        c = self.court
        pressed = {a.bound_for or a.at for a in self.armies
                   if a.owner in self.world.towns
                   and (a.bound_for in self.world.settlements
                        or (a.at in self.world.settlements
                            and a.state in (BESIEGING, RAIDING)))}
        pressed.discard("")
        if not pressed:
            return msgs
        for key in list(c.allies):
            t = self.world.towns.get(key)
            if t is None or self.day - c.aided.get(key, -9999) < self.AID_EVERY:
                continue
            dice = random.Random(f"{self.seed}:aid:{key}:{self.day}")
            if dice.random() > 0.08:
                continue
            target = min(pressed, key=lambda k: self.world.distance(key, k))
            units = {k: v * 0.5 for k, v in
                     self._muster_enemy(t, self.war_pressure(), spread=False).items()
                     if UNITS.get(k) is None or UNITS[k].unit_class != "siege"}
            units = {k: v for k, v in units.items() if v >= 1}
            if not units:
                continue
            a = Army(uid=self.next_army_uid, name=f"{t.lord}'s men", owner=PLAYER,
                     units=units, at=key, home=target)
            self.next_army_uid += 1
            self.armies.append(a)
            self._set_march(a, key, target, units)
            c.aided[key] = self.day
            c.shake(key, 5.0)
            msgs.append(self.note(
                f"*** {t.lord} of {t.name} keeps his word: {describe(a.units)} "
                f"march for {self.world.node_name(target)} under your banner. ***",
                MOMENTOUS))
        return msgs

    def _peace_day(self) -> List[str]:
        """A lord losing his war with you says so, and asks for peace.

        EU4's war score, as small as it can be made: when the reckoning
        with one lord stands at +50 or better and none of his men is on
        the road to you, he sues -- and a truce with him is free for the
        next SUIT_DAYS days."""
        msgs: List[str] = []
        c = self.court
        c.settle_day()
        c.settle_opinions(sorted(self.world.towns), self.day)
        for key, v in list(c.score.items()):
            t = self.world.towns.get(key)
            if t is None or t.mine or v < self.sues_at(key) or t.truce_days > 0:
                continue
            if self.day - c.sued.get(key, -9999) < 90:
                continue
            if any(a.owner == key and a.bound_for in self.world.settlements
                   for a in self.armies):
                continue
            c.sued[key] = self.day
            msgs.append(self.note(
                f"*** {t.lord} of {t.name} sues for peace. `truce {t.name.lower()}` "
                f"costs nothing for {self.SUIT_DAYS} days. ***", MOMENTOUS))
        return msgs

    def sues_at(self, key: str) -> float:
        """The war score at which a lord asks for peace: +50, less a point
        for every eight days the war has run, down to +25."""
        return 50.0 - min(25.0, self.court.war_days.get(key, 0) / 8.0)

    def about_to_take(self, key: str) -> str:
        """A settlement of yours this lord's lines are about to carry, if
        any. Unciv's AI will not make peace the week it is going to take a
        city, and neither will he."""
        for a in self.armies:
            if a.owner != key or a.state != BESIEGING:
                continue
            s = self.world.settlements.get(a.at)
            if s is None:
                continue
            full = s.wall_max(self.progress)
            if (full > 0 and s.wall_hp < 0.25 * full) or sum(s.units.values()) < 5:
                return s.name
        return ""

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
            c.shake(who, 10.0)
            c.refused.pop(who, None)
            # Whoever is marching on them has now given you a reason to
            # march on him, which is the other half of what an ally is for.
            for a in self.armies:
                if a.bound_for == who and a.owner in self.world.towns:
                    c.give_ground(a.owner, "called", self.day)
            if t is not None:
                t.truce_days = max(t.truce_days, 120)
            return self.note(f"You answer {name}'s call. Whoever is at their "
                             f"gate is now your business too.", MOMENTOUS)
        # Freeciv's ally asks three times. The first no is a disappointment
        # and the second a warning; the third ends it, and everybody hears.
        c.refused[who] = c.refused.get(who, 0) + 1
        if who in c.allies and c.refused[who] < self.ALLY_PATIENCE:
            c.write(who, "broke_word", -20.0 * c.refused[who], self.day)
            c.shake(who, -10.0 * c.refused[who])
            left = self.ALLY_PATIENCE - c.refused[who]
            return self.note(
                f"You do not come when {name} calls. They write that they "
                f"are disappointed" + (" -- and that they will not ask many "
                f"more times" if left == 1 else "") + ".", MOMENTOUS)
        c.refused.pop(who, None)
        if who in c.allies:
            c.allies.remove(who)
        c.write(who, "broke_word", -60.0, self.day)
        c.shake(who, -20.0)
        others = [k for k, x in self.world.towns.items() if not x.mine and k != who]
        c.write_all(others, "broke_word", -22.0, self.day)
        self.kin.did("open", -0.2)
        return self.note(f"You do not come when {name} calls. The alliance "
                         f"ends, and every lord on the march is told.",
                         MOMENTOUS)

    ALLY_PATIENCE = 3            # calls let go by before the alliance ends

    def ally(self, town_key: str) -> str:
        """Swear to come when they are attacked, and they to you."""
        t = self.world.towns.get(town_key)
        if t is None:
            return f"there is no {town_key!r} to treat with"
        if not t.mine and self.court.trust_of(town_key) < self.court.TRUST_FLOOR_ALLY:
            return (f"{t.lord} likes you well enough, perhaps, but does not "
                    f"trust your word ({self.court.trust_of(town_key):.0f} of "
                    f"{self.court.TRUST_FLOOR_ALLY:.0f} needed). Keep it a while.")
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

    def _loyalty_day(self, key: str, town) -> str:
        """A sworn town's loyalty, a day at a time -- EU4's liberty desire
        turned the right way up. It settles toward 70 under a lord who is
        strong and near; it slides while there is a letter against you on
        the march (somebody is courting it) and while you are too weak to
        hold it. Under 50 it wavers and says so; at 0 it goes."""
        before = town.loyalty
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self._muster_enemy(town, self.war_pressure(),
                                                  spread=False))
        drift = 0.08 * (70.0 - town.loyalty) / 70.0
        if self.court.coalition:
            drift -= 0.12
        if mine < 0.45 * theirs:
            drift -= 0.2
        town.loyalty = max(0.0, min(100.0, town.loyalty + drift))
        if before >= 50.0 > town.loyalty:
            return self.note(f"{town.name} wavers in its oath ({town.loyalty:.0f} "
                             f"of 100) -- there are letters on the march, and "
                             f"your hand is not heavy enough.")
        return ""

    def _revolt(self, key: str, town) -> str:
        """A town holds its oath while the hand that took it is still visible.

        Conquest is not a purchase: a lord who takes five towns and then lets
        his host melt away will watch them leave one at a time.
        """
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self._muster_enemy(town, self.war_pressure(),
                                                  spread=False))
        if town.loyalty > 0.0:
            if mine >= 0.45 * theirs:
                return ""
            # A loyal town rides out a thin year; a wavering one does not.
            odds = C.REVOLT_CHANCE * max(0.0, 1.5 - town.loyalty / 50.0)
            if self.rng.random() > odds:
                return ""
        town.owner = ""
        town.hostility = 65.0
        town.garrison = dict(town.target_garrison())
        return self.note(f"*** {town.name} throws off its oath -- you have "
                         f"nothing left nearby to hold it with. ***", MOMENTOUS)

    def _nearest_of_mine(self, key: str) -> str:
        return min(self.world.settlements,
                   key=lambda k: self.world.distance(key, k))

    # --------------------------------------------------------- the lords' coin
    def _income_of(self, t) -> float:
        """What a lord's country pays him a day: a little over what his
        standing garrison costs, and a share of his town's trade."""
        return (1.3 * host_upkeep(t.target_garrison())
                + 0.5 * t.tribute() * lordly.sort_of(t.key).thrift)

    def _host_price(self, host: Dict[str, float]) -> float:
        return sum(UNITS[k].coin * n for k, n in host.items() if k in UNITS)

    FEUDAL_SERVICE = 40          # days a host serves before it is paid

    def _keep_the_chest(self, key: str, t) -> None:
        """A lord's day of accounts. Warband gives its lords a week's income
        less wages and lets a host in debt melt away; this is the same, a
        day at a time. In debt his garrison drifts off a hundredth a day and
        his men in the field faster.

        A levy owes its lord forty days in the field at its own cost -- the
        old feudal service -- and only after that does he pay wages; a host
        sitting down before a wall lives half off the country round it; and a
        lord runs a few days behind on wages before anyone walks off. Without
        these, a siege that had its ram at the gate melted in the lines before
        it was ever ready to go in: a whole host costs six times what a
        lord's country pays him a day."""
        if t.chest < 0 and t.chest == -1.0:
            t.chest = self._host_price(self._muster_enemy(t, 1.0, spread=False)) + 200.0
        field = [a for a in self.armies if a.owner == key]
        income = self._income_of(t)
        wages = 0.0
        for a in field:
            a.served += 1
            if a.served > self.FEUDAL_SERVICE:
                wages += host_upkeep(a.units) * (0.5 if a.state == BESIEGING else 1.0)
        t.chest += income - host_upkeep(t.garrison) - wages
        # And no deeper than three hosts' worth: what a lord cannot spend on
        # soldiers goes on the things lords spend money on, and a chest that
        # grew for ever would be a chest that never said no.
        cap = 3.0 * self._host_price(self._muster_enemy(t, self.war_pressure(),
                                                        spread=False))
        t.chest = min(t.chest, max(cap, 600.0))
        if t.chest < -3.0 * income:
            t.garrison = {k: v * 0.99 for k, v in t.garrison.items() if v * 0.99 >= 0.5}
            for a in field:
                a.units = {k: v * 0.985 for k, v in a.units.items() if v * 0.985 >= 0.5}
            t.chest = max(t.chest, -3000.0)

    # ------------------------------------------------- a war on you, weighed
    #: Unciv's two lines: at PREPARE he is gathering and says so; at DECLARE
    #: he marches. Below both his temper is up and he holds back.
    PREPARE = 15.0
    DECLARE = 20.0

    def _war_terms(self, t, target: str, pressure: float) -> List[Tuple[str, float]]:
        """Why a lord would or would not march on you, as a list of named
        reasons with a weight each -- Unciv's motivation-to-attack, Warband's
        assailability, Freeciv's want against fear. Named, because a lord
        who can say why is a lord a player can answer."""
        key = t.key
        c = self.court
        terms: List[Tuple[str, float]] = [("his temper is up", 12.0)]
        # His habit reads you as it reads anybody: a lord who goes for the
        # nearest goes for you when you are the nearest, and one who goes for
        # the weakest when your wall is the thinnest on the march.
        hunts = lordly.sort_of(key).hunts
        if hunts == "you":
            terms.append(("he has his eye on you", 4.0))
        elif hunts == "closest" and target in self.world.coords:
            mine = self.world.distance(key, target)
            if all(self.world.distance(key, k) >= mine for k in self.world.towns
                   if k != key and self.world.towns[k].owner != key
                   and k in self.world.coords):
                terms.append(("you are the nearest thing to him", 5.0))
        elif hunts == "gold":
            # And the richer you get, the more of a mark you are to him.
            rich = min(1.0, self.real_worth() / max(1.0, self.goals.net_worth))
            if rich > 0.25:
                terms.append(("you are worth robbing", round(10.0 * rich, 1)))
        host = self._muster_enemy(t, pressure, spread=False)
        price = self._host_price(host)
        if t.chest < price:
            share = max(0.0, t.chest) / max(price, 1.0)
            terms.append(("his chest will not pay for it", -12.0 * (1.0 - share)))
            host = {k: v * max(0.35, share) for k, v in host.items()}
        s = self.world.settlements.get(target)
        yours = 0.0
        if s is not None:
            yours = host_strength(s.units) + s.wall_hp / 12.0
        yours += sum(host_strength(a.units) for a in self.armies
                     if a.owner == PLAYER and a.at == target)
        ratio = host_strength(host) / max(1.0, yours)
        band = (20.0 if ratio >= 3 else 14.0 if ratio >= 2 else 8.0 if ratio >= 1.5
                else 3.0 if ratio >= 1 else -6.0 if ratio >= 0.7
                else -15.0 if ratio >= 0.5 else -30.0)
        terms.append((f"his host against your wall, {ratio:.1f} to 1", band))
        far = self.world.distance(key, target) if target in self.world.coords else 0.0
        if far:
            terms.append(("the distance", -min(10.0, far / 12.0)))
        beset = sum(1 for a in self.armies if a.bound_for == key and a.owner != key)
        if beset:
            terms.append(("somebody is marching on him", -10.0 * beset))
        if c.allies:
            terms.append(("your allies would come", -4.0 * len(c.allies)))
        # What has settled in him, not what he said this morning.
        view = c.settled_view(key, self.day)
        if view <= -40:
            terms.append(("he hates you", 8.0))
        elif view <= -15:
            terms.append(("he dislikes you", 4.0))
        elif view >= 40:
            terms.append(("he thinks well of you", -8.0))
        elif view >= 15:
            terms.append(("he likes you", -4.0))
        off = c.offence(key, self.day)
        if off:
            terms.append(("what you have done on this march", min(10.0, off / 6.0)))
        if key in c.coalition:
            terms.append(("his name is on the letter", 8.0))
        war = c.score.get(key, 0.0)
        if war:
            terms.append(("how the war has gone", max(-10.0, min(10.0, -war / 10.0))))
        nature = (t.aggression - 1.0) * 10.0
        if abs(nature) >= 0.5:
            terms.append(("his nature", nature))
        if t.gathering:
            terms.append(("he has waited", min(15.0, t.gathering / 4.0)))
        return terms

    def _reckon_war(self, key: str, t, pressure: float) -> str:
        """His temper is up. Does he march?"""
        target = self._nearest_of_mine(key)
        terms = self._war_terms(t, target, pressure)
        total = sum(v for _l, v in terms)
        t.reckoning = [[label, round(v, 1)] for label, v in terms]
        t.reckoned = round(total, 1)
        t.hostility = min(t.hostility, C.HOSTILITY_WAR)
        if total >= self.DECLARE:
            t.gathering = 0
            return self._send_host(t, pressure, target)
        t.gathering += 1
        worst = min(terms, key=lambda r: r[1])
        who = t.lord if " of " in t.lord else f"{t.lord} of {t.name}"
        if total >= self.PREPARE:
            if t.gathering == 1:
                return self.note(
                    f"{who} is gathering men against you "
                    f"({total:.0f}; he marches at {self.DECLARE:.0f}). "
                    f"`court {key}` for his reasons.", MOMENTOUS)
            return ""
        if t.gathering == 1 or t.gathering % 60 == 0:
            return self.note(f"{who} is angry enough to march, and holds "
                             f"back -- {worst[0]}.")
        return ""

    def _week_mood(self, key: str, what: str) -> float:
        """A lord's humour for the week, 0 to 1. Rerolled every seven days
        rather than every morning -- Warband rerolls its lords' dice weekly
        so a man is steadily hot or steadily cool for a while, instead of
        jittering between the two, and so this does not draw on the world's
        dice either."""
        return random.Random(f"{self.seed}:{what}:{key}:{self.day // 7}").random()

    def _prey_for(self, key: str, reach: float = 0.8) -> Optional[str]:
        """A weaker neighbour worth marching on -- your vassals included.

        `reach` is how strong the neighbour may be against his own muster;
        it rises as he waits (see `waited`)."""
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
            if defence >= mine_strength * reach:
                continue
            score = (mine_strength * reach - defence) / max(
                40.0, self.world.distance(key, other_key))
            # And his habit: Stronghold's lords each pick a target their own
            # way, which is what makes one of them predictable and another
            # a nuisance in a different corner of the map.
            hunts = lordly.sort_of(key).hunts
            if hunts == "closest":
                score /= max(1.0, self.world.distance(key, other_key) / 40.0)
            elif hunts == "gold":
                score *= other.prosperity ** 2
            elif hunts == "you" and other.mine:
                score *= 1.6
            if score > best_score:
                best, best_score = other_key, score
        return best

    WAVE_GROWTH = 0.15           # each host at you a sixth bigger, to four

    def _send_host(self, town, pressure: float, target: str) -> str:
        host = self._muster_enemy(town, pressure)
        if target in self.world.settlements:
            grow = 1.0 + self.WAVE_GROWTH * min(4, town.waves)
            host = {k: v * grow for k, v in host.items()}
            town.waves += 1
        # Bought out of his chest, as much of it as he can pay for -- never
        # less than a third of a host, which is a raiding party at worst.
        if town.chest >= 0:
            price = self._host_price(host)
            share = max(0.35, min(1.0, town.chest / max(price, 1.0)))
            if share < 1.0:
                host = {k: v * share for k, v in host.items() if v * share >= 0.5}
            town.chest -= price * share
        a = Army(uid=self.next_army_uid, name=f"{town.lord}'s host", owner=town.key,
                 units=host, at=town.key, home=town.key)
        self.next_army_uid += 1
        self.armies.append(a)
        self._outfit(a, town.key)
        water = self._set_march(a, town.key, target, host)
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
                f"{a.days_left:.0f} days out"
                + (f", {water}" if water else "") + said)

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
        idle = self.day - self._last_war_day
        if at_war:
            self._last_war_day = self.day
            e.note("knights", "there is a war on, and they are in it", 10.0,
                   self.day)
        elif idle > 240:
            e.note("knights", "a long peace, and nothing to take",
                   -8.0 - (4.0 if e.granted("levy") else 0.0), self.day)
        return e.day(self.day)

    def _missions_day(self, standing, led=None) -> List[str]:
        """Anything finished today, and the reward actually paid.

        Paid here rather than announced here: a reward that is a line of text
        is a reward nobody notices was never given.
        """
        said: List[str] = []
        for mission, words in self.missions.check(self.house, standing):
            said.append(f"*** {mission.name} -- {mission.asks} ***")
            said.append("  " + (self._pay(mission, led) or words))
        return said

    def _pay(self, mission, led=None) -> str:
        """Hand over what a mission promised.

        Coin goes through the day's ledger, not around it. A reward added
        straight to the treasury is a coin the accounts cannot explain, and
        the first thing it broke was the test that says they always can.
        """
        kind, value = mission.gives
        if kind == "coin":
            self.treasury += float(value)
            if led is not None:
                led.reward += float(value)
            return f"{float(value):,.0f}c into the chest"
        if kind == "tech":
            self.progress.researched.add(str(value))
            return f"{value} learned outright, without the scholars"
        if kind == "claim":
            # "nearest" rather than a named town, because which town is
            # nearest depends on the map the scenario drew.
            key = self._nearest_foreign() if value == "nearest" else str(value)
            if key:
                # A claim is a town key and the day it was made -- claims
                # outlive the person the marriage was to, which is the whole
                # point of them.
                self.court.claims.setdefault(key, self.day)
                return f"a claim on {self.world.node_name(key)}"
            return "no claim to be had"
        if kind == "privilege":
            return self.estates.grant(str(value), self.day)
        if kind == "prosperity":
            for s in self.world.settlements.values():
                s.popularity = min(100.0, s.popularity + float(value) * 20.0)
            for t in self.world.towns.values():
                if t.mine:
                    t.prosperity += float(value)
            return f"your holdings prosper"
        if kind == "opinion":
            # Through the book, not onto `favour`: favour is re-read off the
            # book every morning, so writing to it directly was a reward that
            # lasted until breakfast.
            for key, t in self.world.towns.items():
                if not t.mine:
                    self.court.write(key, "gift", float(value), self.day)
            return f"every lord thinks better of you"
        if kind == "units":
            seat = self.home()
            for k, n in dict(value).items():
                seat.units[k] = seat.units.get(k, 0.0) + float(n)
            return "they muster at " + seat.name
        return mission.reward_words()

    def _nearest_foreign(self) -> str:
        """The foreign town closest to your seat, for a claim that has to
        land somewhere the map actually put one."""
        seat = self.home()
        here = self.world.coords.get(getattr(seat, "key", ""), (0.0, 0.0))
        best, far = "", 1e9
        for key, t in self.world.towns.items():
            if t.mine:
                continue
            x, y = self.world.coords.get(key, (0.0, 0.0))
            d = (x - here[0]) ** 2 + (y - here[1]) ** 2
            if d < far:
                best, far = key, d
        return best

    def _look_around(self) -> None:
        """Refresh what you know about the march.

        Your carts are your intelligence service, which is the right answer for
        this game in particular: the map you can see is the map you trade with,
        and a lord you have never sent a cart to is a lord you are guessing
        about. A host of yours standing somewhere sees it too, and a town sworn
        to you reports every day.
        """
        self._scout()
        for t in self.world.towns.values():
            if t.mine:
                t.observe(self.day)
        for c in self.caravans:
            node = getattr(c, "at", "") or ""
            if node in self.world.towns:
                self.world.towns[node].observe(self.day)
        # An ally writes: what he has behind his wall is no secret from you.
        for key in self.court.allies:
            if key in self.world.towns:
                self.world.towns[key].observe(self.day)
        for a in self.armies:
            if a.owner == "player" and a.at in self.world.towns:
                self.world.towns[a.at].observe(self.day)
        self._sight_hosts()

    def host_xy(self, a) -> Optional[Tuple[float, float]]:
        """Where a host is on the map this morning, between towns if need be."""
        xy = self.world.coords
        if a.state == MARCHING and a.bound_for and a.at in xy and a.bound_for in xy:
            total = a.leg_days if a.leg_days > 0 else a.days_left + 1.0
            done = max(0.0, min(1.0, 1.0 - a.days_left / max(total, 1e-9)))
            (x0, y0), (x1, y1) = xy[a.at], xy[a.bound_for]
            return (x0 + (x1 - x0) * done, y0 + (y1 - y0) * done)
        where = a.at or a.bound_for
        return xy.get(where)

    def cart_xy(self, c) -> Tuple[Optional[Tuple[float, float]],
                                  Optional[Tuple[float, float]]]:
        """Where a cart set out from on this leg, and where it is now."""
        xy = self.world.coords
        frm = c.at or (c.route[c.leg - 1].node if c.route and c.leg else c.home)
        if frm not in xy:
            return None, None
        if not c.bound_for or c.bound_for not in xy:
            return xy[frm], xy[frm]
        total = max(1.0, self.world.distance(frm, c.bound_for) / max(c.speed, 1.0))
        done = max(0.0, min(1.0, 1.0 - c.days_left / total))
        (x0, y0), (x1, y1) = xy[frm], xy[c.bound_for]
        return xy[frm], (x0 + (x1 - x0) * done, y0 + (y1 - y0) * done)

    def _scout(self) -> None:
        """Clear the shroud round everybody of yours, and say what is in
        sight today. Your towns see round their walls; a cart or a host has
        seen the whole road it has come along this leg, and sees round where
        it stands now."""
        sh = self.shroud
        sh.morning()
        xy = self.world.coords
        for key in self.world.settlements:
            if key in xy:
                sh.look(*xy[key], self._sight_from(key, sight.TOWN_SIGHT))
        for key, t in self.world.towns.items():
            # Your sworn towns, and your allies': an ally shares what his
            # walls can see, which is half of what an alliance is for.
            if (t.mine or key in self.court.allies) and key in xy:
                sh.look(*xy[key], self._sight_from(key, sight.TOWN_SIGHT))
        for c in self.caravans:
            frm, now = self.cart_xy(c)
            if now:
                sh.trail(frm, now, sight.CART_SIGHT)
                sh.look(*now, sight.CART_SIGHT)
        for a in self.armies:
            if a.owner != "player":
                continue
            now = self.host_xy(a)
            if not now:
                continue
            if a.state == MARCHING and a.at in xy:
                sh.trail(xy[a.at], now, sight.HOST_SIGHT)
            sh.look(*now, sight.HOST_SIGHT if a.state == MARCHING
                    else self._sight_from(a.at, sight.HOST_SIGHT))

    def _sight_from(self, node: str, base: float) -> float:
        """How far a place sees: further from hill country, a twentieth
        more for every hill round it past the three most places have, up to
        a quarter."""
        hills = self._ground_at(node).get("hills", 0) if node else 0
        return base * (1.0 + 0.05 * min(5, max(0, hills - 3)))

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
            # Or simply in sight: inside the ring round a town, a cart or a
            # host of yours, wherever on the road it has got to.
            if not close:
                where = self.host_xy(a)
                close = bool(where) and self.shroud.sees(*where)
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

    #: How long word of a sickness is worth anything. A market you have not
    #: had anybody in for six weeks is a market you do not know the state
    #: of, and this is the whole reason shutting the gates is a decision:
    #: shut on a rumour and you may have stopped your carts for nothing,
    #: wait for certainty and the certainty arrives on a cart.
    WORD_KEEPS = 40

    def word_of_sickness(self) -> List[dict]:
        """Where you have heard there is sickness, and how old the word is.

        Off the same `seen_day` the rest of the fog runs on: somebody of
        yours has to have been there. A town you have never traded with
        could be burying half its people and you would not know.
        """
        out = []
        for key, t in self.world.towns.items():
            _seen, age = self.known(key)
            if age < 0 or age > self.WORD_KEEPS:
                continue
            if not t.sick.here:
                continue
            out.append({"key": key, "name": t.name, "days": age,
                        "sure": age <= 3})
        return sorted(out, key=lambda r: r["days"])

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
        # And the war itself: a lord you are beating asks less for peace,
        # one who is beating you asks more -- EU4's war score on the price.
        war = max(0.35, min(2.0, 1.0 - self.court.score.get(town_key, 0.0) / 100.0))
        # And a long war is a war both sides are tired of.
        war *= max(0.6, 1.0 - self.court.war_days.get(town_key, 0) / 500.0)
        # And how little he likes you, squared: Freeciv's AI prices a treaty
        # on the goodwill it is short of, so a lord who merely dislikes you
        # asks a little over the odds and one who hates you a great deal.
        short = max(0.0, 25.0 - self.court.settled_view(town_key, self.day)) / 100.0
        war *= 1.0 + 1.5 * short * short
        return (C.TRUCE_RATE * days * town.muster * town.prosperity * war
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
        if self.court.score.get(town_key, 0.0) <= -50.0:
            return (f"{town.lord} is winning this war and knows it. He will "
                    f"talk when that changes.")
        falling = self.about_to_take(town_key)
        if falling:
            return (f"{town.lord}'s men are on the wall at {falling}. He will "
                    f"talk about peace after he has it.")
        cost = self.truce_cost(town_key, days)
        if self.day - self.court.sued.get(town_key, -9999) <= self.SUIT_DAYS:
            cost = 0.0                  # he asked
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
        # A scenario whose whole subject is one siege ends when the wall does.
        # Everywhere else a sacking is survivable on purpose.
        if "survive" in self.goals.paths and self._sacked:
            self.over = ("Stormed. They came over the wall and the hold is "
                         "theirs. There was nowhere else to be.")
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
            "pending": self.pending.to_dict() if self.pending else None,
            "battles_mode": self.battles_mode,
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
            "missions": self.missions.to_dict(),
            "shroud": self.shroud.to_dict(),
            "role": self.role,
            "liege": self.liege,
            "tallies": {"hosts": self._hosts_raised, "won": self._battles_won,
                        "stormed": self._stormed, "lost": self._towns_lost,
                        "trade": self._trade_profit},
            "chronicle": self.chronicle.to_dict(),
            "chapter": self.chapter,
            "last_war_day": self._last_war_day,
            **{name: list(rng.getstate())
               for name, rng in self._streams().items()},
        }

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh)
        return f"saved to {path}"

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        # The save is read, not taken. Readers below keep lists and dicts
        # from `d` by reference where copying them would be busywork, which
        # is fine for a file read once and wrong for a dict loaded twice:
        # two games built from one dict shared their stock and their
        # history and drifted apart by the second morning. One copy here
        # keeps every reader honest without each having to remember.
        d = copy.deepcopy(d)
        g = cls(world=World.from_dict(d["world"]), treasury=d["treasury"],
                day=d["day"], seed=d["seed"], house=d.get("house", ""),
                goals=Goals.from_dict(d.get("goals", {})),
                scenario=d.get("scenario", "marchlands"),
                briefing=d.get("briefing", ""),
                start_month=d.get("start_month", C.START_MONTH))
        g.caravans = [caravan_from_dict(c) for c in d["caravans"]]
        g.armies = [Army.from_dict(a) for a in d.get("armies", [])]
        # A fight the save was taken in the middle of picks up where it was.
        # The mode is not restored: it belongs to the surface running the
        # game, not to the game, and a save from the window loaded headless
        # must not stop a test dead on a wall.
        raw = d.get("pending")
        g.pending = PendingBattle.from_dict(raw) if raw else None
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
        g.missions = missions_mod.Roll.from_dict(d.get("missions") or {})
        g.shroud = sight.Shroud.from_dict(d.get("shroud"))
        g.role = str(d.get("role") or "lord")
        g.liege = str(d.get("liege") or "")
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
        # The knights' quiet clock. It used to be set with `self._last_war_day
        # = ...` the first time there was a war and read with a `getattr`
        # default, which meant it was not a field, was not saved, and a
        # reloaded game forgot how long the peace had been. Not an RNG and
        # not visible in any fingerprint of the day it loaded -- it diverged
        # a season later, when the estates decided the peace had been long
        # enough to complain about and the original game did not.
        g._last_war_day = int(d.get("last_war_day", 0))
        # Put the dice back exactly where they were. Re-seeding here -- which
        # is what this did -- loads a game whose state matches to the coin and
        # whose *future* does not: same save, reloaded, different weather,
        # different prices, different battles. The state was never the hard
        # part of saving a game; the stream position is.
        # The trade engine is rebuilt on the new world before the streams go
        # back, because two of them live on it and a fresh TradeEngine brings
        # its own literal-seeded pair with it.
        g.trade_engine = TradeEngine(g.world, g.rng)
        g.trade_engine.pest = random.Random(d["seed"] * 5081 + 7)
        g.trade_engine.spate = random.Random(d["seed"] * 7717 + 23)
        for name, rng in g._streams().items():
            if not cls._put_back(rng, d.get(name)) and name == "rng":
                g.rng = random.Random(d["seed"] + d["day"])   # a save from before
                g.trade_engine.rng = g.rng
        return g

    @classmethod
    def load(cls, path: str) -> "GameState":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
