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
from .castle import Works
from .market import Market
from .plague import Sickness
from . import rivers as waters
from .military import sky_on
from . import culture as cultures
from . import lords as lordly
from .settlement import Settlement


#: The river states worth telling somebody about. A ford in low water is not
#: news, and a line of them every morning is how a log stops being read.
#: Module level rather than on World, because World has a `waters()` method
#: and a class body cannot see past it to the module of the same name.
WORTH_SAYING = (waters.HIGH, waters.SHUT, waters.ICE)


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
    #: How ready the walls are after a storm was thrown back from them: +100
    #: a repulse, wearing off by two a day. Every point is a little more
    #: battlement for the next assault -- the men who held once know how.
    hardened: float = 0.0
    #: A sworn town's loyalty, 0-100, once it is yours. Below 50 it wavers
    #: and says so; at 0 it goes. See engine._loyalty_day.
    loyalty: float = 50.0
    #: Times running this lord looked for somebody to march on and found
    #: nobody weak enough. Each one lowers what he will settle for.
    waited: int = 0
    #: The lord's chest. He is paid from his country and pays his garrison
    #: and his hosts out of it; a host is bought, not conjured. -1 until the
    #: first morning funds it.
    chest: float = -1.0
    #: His reckoning about a war on you, term by term, the last time his
    #: temper was up -- [[label, value], ...] -- and the total. Kept so the
    #: court can show a player why he did or did not come.
    reckoning: List[list] = field(default_factory=list)
    reckoned: float = 0.0
    #: Days his temper has been up without his marching.
    gathering: int = 0
    #: Hosts he has sent at you. Stronghold's invasions each come bigger
    #: than the last: a lord who has been thrown back once brings more.
    waves: int = 0
    garrison: Dict[str, float] = field(default_factory=dict)
    wall_hp: float = 0.0
    wall_max: float = 0.0
    wall_base: float = 0.0
    muster: float = 1.0           # how big a host this town can put in the field
    temper: float = 1.0           # how quickly this lord takes offence
    sort: str = ""                # what kind of lord he is (see lords.py)
    #: What he thinks of you, copied off the chancery's ledger each morning.
    #: The world does not know what politics is and should not -- it only
    #: needs the number, the way a customs post only needs today's rate.
    #: The toll this lord charges a stranger, before anything you have done
    #: about it. Kept on the town rather than on its market because the
    #: market's `tariff_rate` is the *working* rate a visiting cart trades
    #: at -- and the trade engine writes the effective rate back into it on
    #: every visit. Reading that back as the base compounded the trading
    #: posts' relief once per cart: after two hundred visits a six per cent
    #: toll was eight thousandths of one per cent, and every foreign customs
    #: post in the game had quietly stopped charging anything at all.
    tariff_base: float = C.BASE_TARIFF
    #: What it is built out of -- see culture.py. A town looks like itself
    #: wherever a scenario puts it, and taking one does not re-roof it.
    culture: str = ""
    #: The country round it, in slots of each kind -- the same dict the
    #: cartographer used to choose the roofline. It used to be thrown away
    #: the moment the culture was picked, which meant the map knew a town
    #: stood in a fen and the game did not. It decides what the ground is
    #: like to fight over: see military.field_at.
    ground: Dict[str, int] = field(default_factory=dict)
    regard: float = 0.0
    signed: bool = False          # has put his name to the letter against you
    sworn_friend: bool = False    # allied to you
    prosperity: float = 1.0       # grows in peace, falls when stormed
    harbour: bool = False         # ships may call here
    last_pilgrimage: int = -999   # day this lord last sent men to a shrine
    #: The sickness here, if there is one. Foreign towns get it the same
    #: way yours do -- off a cart -- and it is where yours comes from.
    sick: "Sickness" = field(default_factory=lambda: Sickness())
    last_sick: int = -9999
    seen_day: int = -999          # when you last had eyes on this place
    seen: Dict[str, float] = field(default_factory=dict)

    @property
    def mine(self) -> bool:
        return self.owner == "player"

    @property
    def free(self) -> bool:
        return self.owner == ""

    def tribute(self) -> float:
        return (C.TRIBUTE_BASE + C.TRIBUTE_PER_WEALTH * self.wealth) * self.prosperity

    def works(self, prosperity: Optional[float] = None) -> Works:
        """The castle a foreign lord has: how rich his seat is, and how he
        spends it.

        There are no building lists out there, so a seat is assumed to have
        spent its centuries the way that lord would spend them -- and that is
        the point, because it used to be assumed they all spent them the same
        way. The Heron, who does nothing but build, and the Boar, who builds
        nothing, had the identical wall at the identical wealth, and every
        siege in the game was therefore the same siege.

        The sort's dials are shares of one purse, so a man who buys stone has
        less for towers. Each way of spending it leaves a different thing
        wrong with the castle, which is what makes the choice of approach a
        choice: the Ox has no ditch, so mine him; the Magpie has no depth, so
        breach him; the Boar has nothing covering his wall, so put ladders on
        it; the Heron has all three and has to be starved instead.

        Pass the prosperity you *saw* rather than the one he has, and you get
        the castle as it stood when you last looked at it.
        """
        sort = lordly.sort_of(self.key)
        grade = self.wall_base * (0.6 + 0.4 * (self.prosperity if prosperity is None
                                               else prosperity))
        # A tower covers so much line; a lord whose towers do not cover each
        # other leaves a run of wall nobody is shooting along, and `Works.naked`
        # is what the siege code reads to know it -- eight yards of it is a
        # wall nobody is watching at all.
        #
        # No towers means the whole line is that. Writing zero here, which is
        # the tempting thing to write, says the opposite: the siege reads
        # `1 - naked/8` as how watched the wall is, so a castle with nothing
        # on it would have been the hardest in the game to put a ladder
        # against.
        towers = min(5, int(grade * sort.towers // 320))
        naked = 12 if towers <= 0 else max(0, int(26 - towers * 7 * sort.cover))
        return Works(
            moat=1 if grade * sort.water >= 600 else 0,
            pitch=1 if grade * sort.traps >= 450 else 0,
            pits=1 if grade * sort.traps >= 550 else 0,
            oil=1 if grade * sort.traps >= 850 else 0,
            towers=towers,
            gate=grade >= 380,
            stone=grade * sort.stone >= 300,
            naked=naked,
            depth=max(1, min(3, int(1 + grade * sort.layers // 700))),
        )

    def observe(self, day: int) -> None:
        """Write down what the place looks like today.

        Everything a player is told about a rival comes out of this snapshot,
        not out of the town itself -- so what you know is what you last saw,
        and it goes stale while the lord goes on building.
        """
        self.seen_day = day
        self.seen = {
            "garrison": sum(self.garrison.values()),
            "wall_hp": self.wall_hp,
            "wall_max": self.wall_max,
            "muster": self.muster,
            "prosperity": self.prosperity,
            "hostility": self.hostility,
        }

    def faith(self) -> float:
        """How well churched a foreign town is, and so how deaf to preaching.

        Read off wealth and prosperity for the same reason its castle is: a
        rich old seat has a minster, and a market town has a parish priest.
        """
        return max(0.0, min(0.95, 0.25 + 0.30 * self.wealth
                            + 0.25 * (self.prosperity - 1.0)))

    def rebuild_walls(self, share: float = 0.02) -> None:
        self.wall_hp = min(self.wall_max, self.wall_hp + self.wall_max * share)

    def target_garrison(self) -> Dict[str, float]:
        scale = self.muster * self.prosperity
        return {"spearman": 11 * scale, "archer": 8 * scale, "man_at_arms": 4 * scale}

    def grow(self, rng: random.Random, besieged: bool = False,
             day: int = 0) -> None:
        """A year of quiet makes a town richer, higher-walled and better held.

        This is the difference between a map that is scenery and a map that is
        playing against you: leave Ostmark alone for three years and Ostmark
        will not be the same problem it was.
        """
        self.hardened = max(0.0, self.hardened - 2.0)
        if besieged:
            self.prosperity = max(0.4, self.prosperity - 0.004)
            return
        # And some countries are better at being left alone than others: a
        # Magpie's country compounds in peace, a Boar's is spent on soldiers
        # as fast as it is earned. Leaving Havnhold alone for three years is
        # a worse idea than leaving Dunmere alone for three years.
        #
        # Held back by want, not capped by it: a town short of what it needs
        # grows at half pace on the part of its trade that is not met, and one
        # made richer than its trade will bear -- more than half again over
        # it, by a reward or a good year -- slides back toward what it can
        # carry. Below that, thrift compounds as it always did. Now and then a
        # year is simply good or bad -- one day in six hundred, a tenth
        # either way.
        ideal = self.ideal_prosperity()
        met = (ideal - 1.0) / 1.2                # 1.0 all met, 0.0 none
        self.prosperity += (0.00055 * lordly.sort_of(self.key).thrift
                            * (0.5 + 0.5 * met))
        bear = ideal + 0.5                       # thrift earns half again
        if self.prosperity > bear:
            self.prosperity = max(bear, self.prosperity - 0.001 * (1.0 - met))
        # Its own dice, keyed on the town and the day, so a good year in
        # Dunmere does not move the weather.
        luck = random.Random(f"prosper:{self.key}:{day}")
        if luck.random() < 1 / 600:
            self.prosperity += 0.1 if luck.random() < 0.5 else -0.1
        self.prosperity = max(0.4, min(2.2, self.prosperity))
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

    def ideal_prosperity(self) -> float:
        """How rich this town's trade will carry it: 2.2 with every want met,
        down to 1.0 with none. A want is met when the market holds at least
        half what it aims to."""
        wants = self.wants()
        if not wants:
            return 2.2
        short = sum(1 for k in wants
                    if self.market.stock.get(k, 0.0) < 0.5 * self.market.target.get(k, 0.0))
        return 2.2 - 1.2 * short / len(wants)

    def specialties(self) -> List[str]:
        return [k for k, v in sorted(self.flow.items(), key=lambda kv: -kv[1]) if v > 0]

    def wants(self) -> List[str]:
        return [k for k, v in sorted(self.flow.items(), key=lambda kv: kv[1]) if v < 0]

    def tick(self, rng: random.Random, besieged: bool = False) -> None:
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
        lean = C.STOCK_REVERSION
        if besieged:
            # The ring is round the fields as well as the walls: what the
            # country brought in stops coming, nobody else's carts get
            # through to lean the market back, and the town inside eats its
            # granary -- a sixtieth or so of it a day, so a siege of fifty
            # days finds the bins at a fifth and the garrison starting to go.
            lean *= 0.3
            for k in ALL_KEYS:
                if good(k).nourish > 0:
                    flow[k] = (min(flow.get(k, 0.0), 0.0)
                               - 0.015 * self.market.target.get(k, 0.0))
        for k in ALL_KEYS:
            net = flow.get(k, 0.0)
            tgt = self.market.target.get(k, 0.0)
            stock = self.market.stock.get(k, 0.0)
            # Own production/consumption, then the rest of the world leaning back.
            stock += net
            if not (besieged and good(k).nourish > 0):
                stock += lean * (tgt - stock)
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
                "seen": dict(self.seen), "seen_day": self.seen_day,
                "muster": self.muster, "temper": self.temper,
                "sort": self.sort, "regard": self.regard,
                "culture": self.culture, "ground": dict(self.ground),
                "tariff_base": self.tariff_base,
                "signed": self.signed,
                "sworn_friend": self.sworn_friend,
                "prosperity": self.prosperity, "harbour": self.harbour,
                # The day this lord last sent men to a shrine. `from_dict`
                # has always been ready to read it and nothing ever wrote
                # it, so every lord came back off a save believing he had
                # never sent any -- and sent a party the next morning. It
                # looks derived, in the way `raid_heat` and yesterday's
                # hands look derived, and it is not: it gates a decision
                # taken days later, which is the whole class of bug this
                # file keeps relearning.
                "last_pilgrimage": self.last_pilgrimage,
                "hardened": self.hardened, "loyalty": self.loyalty,
                "waited": self.waited, "chest": self.chest,
                "reckoning": [list(r) for r in self.reckoning],
                "reckoned": self.reckoned, "gathering": self.gathering,
                "waves": self.waves,
                "sick": self.sick.to_dict(), "last_sick": self.last_sick}

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
        t.hardened = float(d.get("hardened", 0.0))
        t.loyalty = float(d.get("loyalty", 50.0))
        t.waited = int(d.get("waited", 0))
        t.chest = float(d.get("chest", -1.0))
        t.reckoning = [list(r) for r in d.get("reckoning", [])]
        t.reckoned = float(d.get("reckoned", 0.0))
        t.gathering = int(d.get("gathering", 0))
        t.waves = int(d.get("waves", 0))
        t.garrison = dict(d.get("garrison", {}))
        t.seen = dict(d.get("seen", {}))
        t.wall_hp = d.get("wall_hp", 0.0)
        t.wall_max = d.get("wall_max", 0.0)
        t.sort = d.get("sort", "")
        t.regard = float(d.get("regard", 0.0))
        t.culture = d.get("culture", "")
        t.ground = dict(d.get("ground", {}))
        t.sick = Sickness.from_dict(d.get("sick"))
        t.last_sick = int(d.get("last_sick", -9999))
        t.tariff_base = float(d.get("tariff_base", C.BASE_TARIFF))
        t.signed = bool(d.get("signed", False))
        t.sworn_friend = bool(d.get("sworn_friend", False))
        for name in ("ambition", "aggression", "truce_days", "favour", "muster",
                     "temper", "prosperity", "wall_base", "harbour",
                     "last_pilgrimage", "seen_day"):
            if name in d:
                setattr(t, name, d[name])
        return t


@dataclass
class Shrine:
    """A wayside shrine with a saint's bones in it.

    Age of Empires put five relics on the map and made you leave home to get
    them, which is the cheapest way ever invented to stop a strategy game
    being two players farming in separate corners. These do the same work: the
    offerings are steady coin, the shrines are nowhere near your walls, and
    the other lords want them too.
    """
    key: str
    name: str
    x: float
    y: float
    short: str = ""             # what it is called on a map, where room is short
    relic: str = ""             # what rests here; empty once it is carried off
    holder: str = ""            # '' | 'player' | a town key
    blurb: str = ""

    @property
    def taken(self) -> bool:
        return bool(self.holder)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Shrine":
        return cls(**d)


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
    shrines: Dict[str, "Shrine"] = field(default_factory=dict)
    #: How picked over the country round each place is, 0 to 1 -- see
    #: supply.py. Kept here rather than on the host that did the eating,
    #: because a country is eaten out by whoever has been in it: two hosts
    #: in one place are competing for the same fields, and a lord who has
    #: just marched through is somewhere you should not follow.
    grazed: Dict[str, float] = field(default_factory=dict)
    #: The rivers, drawn once from wherever the towns ended up and then kept.
    #: Empty until something asks -- see `waters()` -- because four different
    #: places build a World and a geography that only some of them had would
    #: be a geography the player could not trust.
    river_lines: List["waters.River"] = field(default_factory=list)
    bridges: List["waters.Bridge"] = field(default_factory=list)
    #: Seed for the drawing. Set by whoever builds the world; the map is the
    #: same every time for a given seed, which is the whole contract.
    river_seed: int = 0
    _next_bridge: int = 1

    # ------------------------------------------------------------- the roads
    def roads(self) -> List[Tuple[str, str]]:
        """Each trading place joined to its nearest three, which is how roads
        happen -- the same roads the map draws and the peddlers walk."""
        # Sorted throughout: a save read back in another order must lay the
        # same roads, or the peddlers walk a different day.
        trade = sorted(k for k in self.coords
                       if k not in self.shrines and k not in self.sites)
        out, seen = [], set()
        for a in trade:
            for b in sorted((b for b in trade if b != a),
                            key=lambda b: (self.distance(a, b), b))[:3]:
                pair = tuple(sorted((a, b)))
                if pair not in seen:
                    seen.add(pair)
                    out.append(pair)
        return sorted(out)

    #: A peddler's share: how much of a cheap town's surplus walks down one
    #: road to a dearer neighbour in a day, at full margin.
    PEDDLE_SHARE = 0.01
    PEDDLE_NERVE = 0.15

    def peddle(self, closed=frozenset()) -> None:
        """Small traders on the roads between neighbouring towns.

        Warband carries a price list from town to town on its caravans and
        nudges each place toward the last; here the goods themselves walk,
        a little at a time, from a town with more than it wants to the
        neighbour paying more -- so prices close along the roads that join
        them, and a road cut by a siege is a gap that stays open. Your own
        settlements are left alone: their markets are your carts' business.
        """
        for a, b in self.roads():
            if a not in self.towns or b not in self.towns or a in closed or b in closed:
                continue
            ta, tb = self.towns[a], self.towns[b]
            for k in ALL_KEYS:
                if not (ta.market.sells(k) and tb.market.sells(k)):
                    continue
                pa, pb = ta.market.price(k), tb.market.price(k)
                cheap, dear = (ta, tb) if pa < pb else (tb, ta)
                # A peddler carries what a town makes, not what you sold it:
                # carting your glut off for you turned every market into a
                # sink that never filled.
                if cheap.flow.get(k, 0.0) <= 0:
                    continue
                lo, hi = min(pa, pb), max(pa, pb)
                rel = (hi - lo) / max(lo, 1e-6)
                if rel < self.PEDDLE_NERVE:
                    continue
                spare = cheap.market.stock.get(k, 0.0) - cheap.market.target.get(k, 0.0)
                if spare <= 0:
                    continue          # never peddle away what a town is short of
                qty = spare * self.PEDDLE_SHARE * min(1.0, rel)
                if qty < 0.05:
                    continue
                moved = cheap.market.take(k, qty)
                dear.market.transfer_in(k, moved)

    # ------------------------------------------------------------- geography
    def place(self, key: str, x: float, y: float) -> None:
        self.coords[key] = (x, y)

    def distance(self, a: str, b: str) -> float:
        (ax, ay), (bx, by) = self.coords[a], self.coords[b]
        return math.hypot(ax - bx, ay - by)

    # ------------------------------------------------------------ the water
    def waters(self) -> List["waters.River"]:
        """The rivers. Drawn on first ask, then kept for good."""
        if not self.river_lines and len(self.coords) >= 3:
            self.river_lines = waters.draw(self.coords, self.river_seed)
        return self.river_lines

    def river(self, key: str) -> Optional["waters.River"]:
        for r in self.waters():
            if r.key == key:
                return r
        return None

    def crossings(self, a: str, b: str
                  ) -> List[Tuple["waters.River", float, float, Optional["waters.Bridge"]]]:
        """Every river on the road from a to b, and what carries it there."""
        if a not in self.coords or b not in self.coords:
            return []
        (ax, ay), (bx, by) = self.coords[a], self.coords[b]
        out = []
        for r, x, y in waters.crossings(self.waters(), ax, ay, bx, by):
            out.append((r, x, y, waters.served_by(self.bridges, r.key, x, y)))
        return out

    def water_state(self, a: str, b: str, day: int, seed: int = 0,
                    start_month: int = C.START_MONTH) -> List[dict]:
        """Every crossing on this road today, in a shape a panel can print.

        The one computation. `water_days` is a view of these rows rather
        than a second pass over the same rivers, because a cart, a host and
        the panel that warned you about both have to agree to the tenth of
        a day -- and two readers of one rule that disagree by a little is
        exactly how the garrison cap went wrong (settlement.max_garrison).
        """
        level = waters.stage(day, seed, start_month)
        sky = sky_on(waters._season_on(day, start_month), day, seed)
        rows = []
        for r, x, y, bridge in self.crossings(a, b):
            st = waters.state_of(r, level, sky, bridged=bridge is not None)
            rows.append({"river": r.name, "key": r.key, "size": r.size,
                         "state": st, "words": waters.WORDS[st],
                         "days": waters.DELAY.get(st, 0.0),
                         "x": x, "y": y,
                         "bridge": bridge.name if bridge else "",
                         "mine": bool(bridge and bridge.owner == "player")})
        return rows

    def water_days(self, a: str, b: str, day: int, seed: int = 0,
                   start_month: int = C.START_MONTH
                   ) -> Tuple[float, List[str]]:
        """Days the water adds to this road today, and what to say about it."""
        rows = self.water_state(a, b, day, seed, start_month)
        days = sum(r["days"] for r in rows)
        notes = [f"the {r['river']} is {r['words']}" for r in rows
                 if r["state"] in WORTH_SAYING]
        return days, notes

    def bridge_at(self, a: str, b: str, river_key: str = ""
                  ) -> Optional[Tuple["waters.River", float, float]]:
        """Where a bridge would go if you built one on this road."""
        found = self.crossings(a, b)
        if river_key:
            found = [c for c in found if c[0].key == river_key]
        else:
            # The worst one first. A road that crosses a beck and a real
            # river wants the bridge over the river, and a player who has to
            # name which is being asked to know the ford limits by heart.
            found = sorted(found, key=lambda c: c[0].ford_limit)
        for r, x, y, _ in found:
            return (r, x, y)
        return None

    # ------------------------------------------------------------- the sea
    def is_port(self, key: str) -> bool:
        """A foreign harbour, or one of yours once the quay is built."""
        t = self.towns.get(key)
        if t is not None:
            return t.harbour
        s = self.settlements.get(key)
        return bool(s and s.effect("port"))

    def ports(self) -> List[str]:
        return [k for k in self.all_nodes() if self.is_port(k)]

    def sea_distance(self, a: str, b: str) -> float:
        return self.distance(a, b) * C.SEA_DIRECTNESS

    def can_sail(self, a: str, b: str) -> bool:
        return self.is_port(a) and self.is_port(b)

    def storm_risk(self, a: str, b: str, season: str) -> float:
        """The sea is quicker and cheaper, and it drowns people in winter."""
        rough = C.STORM_WINTER if season == "winter" else (
            1.6 if season == "autumn" else 1.0)
        return C.STORM_RISK * rough * (0.5 + self.sea_distance(a, b) / 260.0)

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
        if key in self.shrines:
            return self.shrines[key].short or self.shrines[key].name
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
        """Everywhere a cart can trade. Shrines are not on this list: they have
        no market, and a caravan sent to one would have nothing to do there."""
        return list(self.settlements.keys()) + list(self.towns.keys())

    def march_nodes(self) -> List[str]:
        """Everywhere a host can walk to, which does include the shrines."""
        return self.all_nodes() + list(self.shrines.keys())

    def resolve(self, prefix: str, shrines: bool = False) -> str:
        p = prefix.strip().lower().replace(" ", "_")
        nodes = self.march_nodes() if shrines else self.all_nodes()
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

    #: What a lord's opinion is worth at his own customs post. A merchant's
    #: world is the diplomatic one: this is the seam where the two halves of
    #: the game meet, and it runs both ways. Politics decides what your carts
    #: pay, which decides what routes are worth running, which decides where
    #: your money comes from -- and a gift or a marriage is an investment with
    #: a rate of return rather than only war insurance.
    TOLL_FLOOR = 0.35            # an ally waves your carts through
    TOLL_CEILING = 2.6           # a man who has signed against you does not
    TOLL_SLOPE = 95.0            # points of opinion per unit of toll

    #: What a sealed letter is worth at a gate that does not like you. It
    #: takes the worst off a hostile toll and nothing at all off a friendly
    #: one, which is what a safe-conduct actually did: it was protection
    #: against being stopped, not a discount.
    safe_conduct: bool = False

    def toll_mood(self, node: str) -> float:
        """The multiplier this lord's feelings put on his own toll."""
        t = self.towns.get(node)
        if t is None or t.mine:
            return 0.0
        if t.sworn_friend:
            return self.TOLL_FLOOR
        mult = 1.0 - t.regard / self.TOLL_SLOPE
        if t.signed:
            mult = max(mult, 1.9)
        mult = max(self.TOLL_FLOOR, min(self.TOLL_CEILING, mult))
        if self.safe_conduct and mult > 1.0:
            mult = 1.0 + (mult - 1.0) * 0.45
        return mult

    def tariff_for(self, node: str, home: Optional[Settlement]) -> float:
        """Toll charged at `node`, after any relief your trading posts bought."""
        if node in self.settlements:
            return 0.0
        if self.towns[node].mine:
            return 0.0                     # a vassal does not toll its lord
        base = self.towns[node].tariff_base
        relief = max((s.tariff_relief for s in self.settlements.values()), default=0.0)
        return base * (1.0 - relief) * self.toll_mood(node)

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
                "sites": {k: v.to_dict() for k, v in self.sites.items()},
                "safe_conduct": self.safe_conduct,
                "grazed": dict(self.grazed),
                "shrines": {k: v.to_dict() for k, v in self.shrines.items()},
                "river_lines": [r.to_dict() for r in self.river_lines],
                "bridges": [b.to_dict() for b in self.bridges],
                "river_seed": self.river_seed,
                # The order the places were laid down in, kept as a list of
                # its own. A dict rebuilt from JSON comes back in the order
                # the keys sit in the file, and the day walks the towns in
                # that order -- so a save run through any pretty-printer
                # that sorts keys came back a different campaign: another
                # town caught the shock, another lord took offence first,
                # and every seeded thing behind them moved. The state was
                # never the hard part of saving a game; this is the same
                # lesson as the stream positions, one layer down.
                "order": {"settlements": list(self.settlements),
                          "towns": list(self.towns)},
                "next_bridge": self._next_bridge}

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        w = cls()
        order = d.get("order", {})

        def laid_out(raw: dict, kept) -> list:
            """The keys in the order they were laid down, then any the save
            order does not mention -- a save from before this was written
            keeps the order its file happens to have, which is what it had
            before, so nothing moves under an old game."""
            named = [k for k in kept if k in raw]
            return named + [k for k in raw if k not in set(named)]

        w.settlements = {k: Settlement.from_dict(d["settlements"][k])
                         for k in laid_out(d["settlements"], order.get("settlements", []))}
        w.towns = {k: ForeignTown.from_dict(d["towns"][k])
                   for k in laid_out(d["towns"], order.get("towns", []))}
        w.coords = {k: tuple(v) for k, v in d["coords"].items()}
        w.sites = {k: Site(**v) for k, v in d.get("sites", {}).items()}
        w.shrines = {k: Shrine.from_dict(v) for k, v in d.get("shrines", {}).items()}
        w.safe_conduct = bool(d.get("safe_conduct", False))
        w.grazed = {k: float(v) for k, v in d.get("grazed", {}).items()}
        w.river_lines = [waters.River.from_dict(r) for r in d.get("river_lines", [])]
        w.bridges = [waters.Bridge.from_dict(b) for b in d.get("bridges", [])]
        w.river_seed = int(d.get("river_seed", 0))
        w._next_bridge = int(d.get("next_bridge", 1))
        return w


def make_town(key: str, name: str, x: float, y: float, *, produces: Dict[str, float],
              consumes: Dict[str, float], appetite: float = 1.0,
              lawlessness: float = 0.01, tariff: float = C.BASE_TARIFF,
              wealth: float = 1.0, blurb: str = "",
              trades: Optional[Iterable[str]] = None,
              lord: str = "", walls: float = 500.0, muster: float = 1.0,
              garrison: Optional[Dict[str, float]] = None,
              port: bool = False) -> ForeignTown:
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
    # What sort of lord holds it, which is a real difference in how he plays
    # and not a label: see lords.py. A rival you cannot tell apart from
    # another rival is a number with a name on it.
    kind = lordly.sort_of(key)
    return ForeignTown(key=key, name=name, x=x, y=y, market=m, flow=flow,
                       tariff_base=tariff, culture=cultures.of_town(key),
                       base_target=dict(target), lawlessness=lawlessness,
                       wealth=wealth, blurb=blurb, lord=lord,
                       sort=kind.key,
                       aggression=kind.aggression, temper=kind.temper,
                       garrison=dict(garrison or {
                           "spearman": round(11 * muster * kind.muster),
                           "archer": round(8 * muster * kind.muster),
                           "man_at_arms": round(4 * muster * kind.muster)}),
                       wall_hp=walls, wall_max=walls, wall_base=walls,
                       muster=muster * kind.muster, harbour=port)
