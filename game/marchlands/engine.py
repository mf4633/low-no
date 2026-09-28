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
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import building
from .chronicle import MOMENTOUS, NOTABLE, Chronicle
from .economics import Accounts, Economy
from . import estates as estates_mod
from . import feats as feats_mod
from . import missions as missions_mod
from .events import EventEngine
from .goods import ALL_KEYS
from . import chancery as court
from . import culture as cultures
from . import sight
from .kin import Kin, found as found_kin
from .league import League
from .lord import Lord
from .market import Market
from .military import BESIEGING, Army
from . import plague as plague_mod
from .settlement import Settlement
from .tech import Progress
from .trade import Caravan, TradeEngine, caravan_from_dict, caravan_to_dict
from .world import World
# Re-exported: campaign, scenarios and the tests name these through here.
from .records import (CATHEDRAL_HOLD, Goals, Ledger, PendingBattle,  # noqa: F401
                      _ordinal)
from .hall_accounts import AccountsMixin
from .hall_road import RoadMixin
from .hall_wall import WallMixin
from .hall_court import CourtMixin
from .hall_house import HouseMixin

SAVE_VERSION = 2


@dataclass
class GameState(AccountsMixin, RoadMixin, WallMixin, CourtMixin, HouseMixin):
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
        #: Men under arms by home town at the close of the last day; None
        #: until a day has closed, so a loaded game counts nobody as dead.
        self._roll: Optional[Dict[str, float]] = None
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

        # 1. Settlements work, eat and are taxed -- with the men away at war
        # counted out of the hands before anybody is seated.
        self._muster_roll()
        pre_work = self._under_arms()
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
        # What the towns lost under arms by themselves -- the sick, the men
        # shoring a wall under fire. Already off the population; the roll
        # must not bury them twice.
        post_work = self._under_arms()
        buried_at_home = {k: pre_work[k] - post_work.get(k, 0.0) for k in pre_work}
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
        self._close_tolls()
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

        # The roll is called after the war and before the mood, so a town
        # mourns the day it buries its men.
        msgs += self._count_the_fallen(buried_at_home)

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

    def note(self, text: str, weight: int = NOTABLE) -> str:
        """Write a line in the chronicle and hand it back to be said aloud."""
        self.chronicle.record(day=self.day, year=self.year, season=self.season,
                              text=text, weight=weight, chapter=self.chapter)
        return text

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

    def _resolve_town(self, text: str) -> Optional[str]:
        want = (text or "").strip().lower()
        for key, s in self.world.settlements.items():
            if want in (key.lower(), s.name.lower()):
                return key
        for key, s in self.world.settlements.items():
            if s.name.lower().startswith(want) or key.lower().startswith(want):
                return key
        return None

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
