"""Scenarios: the same rules, four different arguments.

Each one sets its own geography, opening, lords and terms of victory. The
default is the full march; the others exist because a game with one map is a
demonstration rather than a game.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from . import config as C
from .engine import Goals, GameState
from .scenario import (OPENING_STORES, build_shrines, build_sites, build_towns,
                       default_rivals, found_seat, new_game)
from .tech import HOUSES, Progress
from . import supply
from . import roles
from .world import World


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    build: Callable[[int, str], GameState]
    blurb: str = ""
    years: float = 3

    def start(self, seed: int = 7, house: str = "plough",
              role: str = "lord") -> GameState:
        if house not in HOUSES:
            raise KeyError(f"no house called {house!r}; "
                           f"choose from {', '.join(HOUSES)}")
        g = self.build(seed, house)
        g.scenario = self.key
        # The role goes on last, over whatever the scenario set up, because
        # it is a different position in the same world rather than a
        # different world.
        if role and role != roles.DEFAULT:
            if role not in roles.ROLES:
                raise KeyError(f"no role called {role!r}; "
                               f"choose from {', '.join(sorted(roles.ROLES))}")
            roles.apply(g, role)
        return g


# --------------------------------------------------------------------------
def _marchlands(seed: int, house: str) -> GameState:
    g = new_game(seed=seed, house=house)
    g.briefing = (
        "Your father held one hill, nine fields and a wood, and owed nobody.\n"
        "Seven towns trade around you and none of them needs you yet.\n"
        "Make them need you, or take them."
    )
    return g


def _salt_road(seed: int, house: str) -> GameState:
    """A coastal start. No keep, no conquest -- only the ledger."""
    world = World()
    stores = dict(OPENING_STORES)
    stores.update({"stone": 120, "salt": 40, "cloth": 40, "wheat": 120,
                   "bread": 180, "planks": 90, "iron": 0, "spears": 0, "bows": 0})
    home = found_seat(
        world, "sealow", "Sealow",
        {"fertile": 6, "forest": 4, "hills": 1, "clay": 2, "coast": 4,
         "urban": 26, "rampart": 10}, (55.0, 75.0),
        population=110.0,
        deposits={"stone": 3600.0, "iron_ore": 700.0},
        units={"spearman": 3},
        # The gentle scenario: the bread chain is already standing, so the
        # first fortnight is about the market rather than about triage.
        standing=("cottage", "cottage", "cottage", "cottage", "farm", "farm",
                  "mill", "bakery", "woodcutter", "sawmill", "granary",
                  "warehouse", "harbour"),
        stock=stores)
    build_towns(world, seed, temper=(0.9, 2.0), aggression=(0.2, 0.7),
                hostility=(0.0, 25.0))
    build_sites(world)                       # Sealow is yours, so it is not listed
    build_shrines(world)
    g = GameState(world=world, treasury=2200.0, seed=seed, house=house,
                  progress=Progress(age=2, researched={house}),
                  goals=Goals(net_worth=70000.0, population=260, towns=3,
                              days=2 * C.DAYS_PER_YEAR, paths=("wealth",),
                              wonder=False))
    g.events = default_rivals()
    home.wall_hp = home.wall_max(g.progress)
    g.new_caravan("sealow", "Salt Mare")
    g.treasury += C.CARAVAN_COST
    g._outlay = 0.0
    g.briefing = (
        "Sealow has a quay, a saltpan and no walls worth the name.\n"
        "The lords inland are quiet this decade and have no quarrel with you.\n"
        "You have two years to make the shore pay for itself."
    )
    return g


def _iron_marches(seed: int, house: str) -> GameState:
    """A cold start on the ore, with lords who already dislike you."""
    world = World()
    stores = dict(OPENING_STORES)
    stores.update({"iron": 90, "iron_ore": 140, "charcoal": 80, "stone": 300,
                   "weapons": 20, "armour": 10, "spears": 60, "bows": 40,
                   "bread": 260, "wheat": 90, "apples": 60})
    home = found_seat(
        world, "greyfell", "Greyfell",
        {"fertile": 3, "forest": 5, "hills": 6, "clay": 1, "coast": 0,
         "urban": 24, "rampart": 16}, (-25.0, -60.0),
        population=120.0,
        deposits={"stone": 42000.0, "iron_ore": 28000.0},
        units={"spearman": 8, "archer": 6, "man_at_arms": 4},
        standing=("keep", "palisade", "palisade", "barracks", "cottage",
                  "cottage", "cottage", "cottage", "farm", "woodcutter",
                  "quarry", "iron_mine", "granary", "warehouse", "poleturner"),
        stock=stores)
    build_towns(world, seed, temper=(1.1, 2.2), aggression=(0.9, 2.1),
                hostility=(35.0, 85.0))
    build_sites(world)                       # Greyfell is yours, so it is not listed
    build_shrines(world)
    g = GameState(world=world, treasury=2600.0, seed=seed, house=house,
                  progress=Progress(age=2, researched={house}),
                  goals=Goals(net_worth=75000.0, population=350, towns=3,
                              days=3 * C.DAYS_PER_YEAR,
                              paths=("wealth", "dominion"), wonder=False))
    g.events = default_rivals()
    home.wall_hp = home.wall_max(g.progress)
    g.new_caravan("greyfell", "Ore Mare")
    g.treasury += C.CARAVAN_COST
    g._outlay = 0.0
    g.briefing = (
        "Iron and stone under the moor, and very little that grows.\n"
        "Every lord on the march remembers how your house came by this hill.\n"
        "Feed it by cart or take what you need. They will come either way."
    )
    return g


def _winter_crown(seed: int, house: str) -> GameState:
    """The hard one. Midwinter, thin stores, and a short rope."""
    g = new_game(seed=seed, house=house)
    g.start_month = 12
    g.treasury = 1100.0
    home = g.world.settlements["aldworth"]
    for k in ("bread", "apples", "cheese", "wheat", "flour"):
        home.market.stock[k] *= 0.45
    home.population = 150.0
    home.popularity = 45.0
    for t in g.world.towns.values():
        t.hostility = min(95.0, t.hostility + 30.0)
        t.aggression *= 1.4
    g.goals = Goals(net_worth=110000.0, population=430, towns=3,
                    days=int(2.5 * C.DAYS_PER_YEAR))
    g.briefing = (
        "Your father died in the first week of the snow and left you the debt.\n"
        "The granary holds a month. Every lord on the march knows both facts.\n"
        "Two and a half years, and a hard winter to get through first."
    )
    return g


def _freebuild(seed: int, house: str) -> GameState:
    """A hill, a long purse, and nobody coming. Build the thing.

    Stronghold's Freebuild is named in every retrospective anybody writes
    about it -- "construct the ultimate castle without fear of attack", "at
    your own pace without combat pressure" -- and the reason is not that
    people dislike the war. It is that the *building* is the thing they came
    for, and a mode that lets them do only that is a mode they play for a
    hundred hours.

    Everything here is still real: the market still prices by scarcity, the
    labour still runs out, the mood still answers to bread and taxes, the
    house still ages and inherits. What is switched off is the clock and the
    other lords' ambition. Nobody marches. Nothing ends.
    """
    g = new_game(seed=seed, house=house)
    for t in g.world.towns.values():
        # Not pacifists -- merchants. They will still trade, and they will
        # still quarrel with each other, which keeps the march alive to watch.
        t.hostility = 0.0
        t.temper = 0.0
        t.aggression *= 0.35
    home = g.home()
    home.population = 90.0
    g.treasury = 9000.0
    g.progress = Progress(age=2, researched={house})
    home.wall_hp = home.wall_max(g.progress)
    g.goals = Goals(net_worth=1e12, population=100000, towns=99,
                    days=99 * int(C.DAYS_PER_YEAR), wonder=False,
                    paths=("wealth",))
    g.briefing = ("Freebuild. Nobody is coming and nothing is counting. "
                  "The market is real, the labour runs out, the mood answers "
                  "to bread and taxes, and the house ages the way it always "
                  "did. Build the thing you have been meaning to build.")
    return g


#: Days of food the besieger sits down with. Longer than the scenario's own
#: clock on purpose: starving him out is not meant to be one of the answers,
#: because a siege you win by waiting is a siege with nothing in it. What the
#: player can do to his baggage he does with a sortie.
BESIEGER_DAYS = 300.0


def _siege(seed: int, house: str) -> GameState:
    """A host is already outside. Hold until the season turns.

    This was built once before and thrown away, because it was not a game:
    `_mend_walls` returned early while besieged, so the wall only ever went
    down, and recruiting at any sane rate changed nothing. Every tuning was
    decided before the player acted -- eight of eight held whatever you did,
    or eight of ten fell whatever you did, with nothing in between, because
    there was no decision in between.

    There are two decisions now. `shore` puts masons on the breach while it
    is being made: slower than peacetime work, nearly twice the stone, and it
    costs men to arrows. `sally` opens the gate and goes at the works, giving
    up the wall for one fight in the open to burn the rams and the engineers.
    Neither is free and neither always works, which is what makes holding out
    something you do rather than something that happens to you.
    """
    from .military import Army, BESIEGING
    g = new_game(seed=seed, house=house)
    home = g.home()
    home.population = 260.0
    home.units.update({"spearman": 44, "archer": 30})
    g.treasury = 1400.0
    g.progress = Progress(age=3, researched={house, "masonry", "chancery"})
    # Bought, not drawn: `plan()` trims a drawing back to the wall the town
    # has actually paid for, and that rule applies to a scenario exactly as
    # it applies to a player.
    for key, many in (("stone_wall", 3), ("wall_tower", 2), ("gatehouse", 1),
                      ("moat", 1)):
        for _ in range(many):
            try:
                home.start_build(key).days_left = 0
            except Exception:
                break
    from . import keep as keeps
    cx = cy = keeps.SIDE // 2
    ring = 6
    for dx in range(-ring, ring + 1):
        for dy in range(-ring, ring + 1):
            if max(abs(dx), abs(dy)) != ring:
                continue
            corner = abs(dx) == ring and abs(dy) == ring
            gate = dy == ring and dx == 0
            home.castle.lay((cx + dx, cy + dy),
                            keeps.TOWER if corner else
                            keeps.GATE if gate else keeps.STONE)
    home.castle.own = True
    home.wall_hp = home.wall_max(g.progress)
    # Stone to shore with, and bread to outlast him on. Both are the levers.
    for key, many in (("bread", 2600.0), ("wheat", 1820.0), ("stone", 500.0)):
        home.market.stock[key] = home.market.stock.get(key, 0.0) + many
    # Your nearest neighbour, not the leftmost name on the map. He was picked
    # by x-coordinate, which put the host at your gate under a lord 175
    # leagues away -- and once hosts had to eat (supply.py) that quietly
    # decided the scenario: his relief column spent its baggage on the road
    # and came apart outside your wall, so one sortie at any hour won, twenty
    # four seeds out of twenty four. A siege is laid by the man next door.
    seat_key = next(iter(g.world.settlements))
    foe = min((k for k, t in g.world.towns.items() if not t.mine),
              key=lambda k: g.world.distance(seat_key, k))
    t = g.world.towns[foe]
    t.hostility = 100.0
    seat = seat_key
    host = Army(uid=g.next_army_uid, name=f"{t.name}'s host",
                owner=foe, at=seat, state=BESIEGING, home=foe,
                units={"spearman": 100, "archer": 55,
                       "man_at_arms": 37, "ram": 3, "engineer": 9})
    # He came to stay. A lord who has sat down in front of a wall brought a
    # baggage train, and this one brought a long one -- his seat is at the
    # far end of the map and no carts are reaching him.
    #
    # Written without this the first time, and it quietly deleted the
    # scenario: he lived out of the fields round your town, ate them bare,
    # and lifted the siege of his own accord on day twenty-five of every
    # seed. Ten of ten held whatever the player did, which is the exact
    # failure this scenario was rebuilt to stop being.
    host.stores = supply.MARCH_RATION * host.size * BESIEGER_DAYS
    g.armies.append(host)
    g.next_army_uid += 1
    g._look_around()
    g.goals = Goals(net_worth=1e12, population=1, towns=99, relics=99,
                    days=int(C.DAYS_PER_YEAR * 0.75), wonder=False,
                    paths=("survive",))
    g.briefing = (
        f"{t.name}'s host is at your gate with rams and engineers, and there "
        f"are more of them than of you. The wall is not your clock -- the "
        f"granary is. You cannot outlast him on what is in it, so the siege "
        f"has to be broken rather than endured.\n\n"
        f"`sally` opens the gate and goes at the works. Send enough and his "
        f"engines burn and the siege has to start again; send too few and you "
        f"have spent the men who could have done it. Go early: every day you "
        f"wait is a day of wall and a day of garrison you no longer have to "
        f"spend on it.\n\n"
        f"`shore` puts masons on the breach while it is being made -- nearly "
        f"twice the stone a yard and a toll in men. It buys time, and time is "
        f"only worth buying if you can eat through it.\n\n"
        f"Do not plan on starving him out. He came with a year in his "
        f"baggage and a road behind him, and the fields round your wall are "
        f"his to eat. A sortie burns what it can reach of that camp, but a "
        f"man who sat down meaning to stay is not going to be hungry before "
        f"you are.")
    return g


SCENARIOS: Dict[str, Scenario] = {s.key: s for s in [
    Scenario("siege", "The Siege", _siege, years=0.75,
             blurb="A host is already outside, and there are more of them "
                   "than of you. Shore the breach, or open the gate and go "
                   "at the works."),
    Scenario("marchlands", "The Marchlands", _marchlands,
             blurb="The full march. One hill, seven towns, three ways to win."),
    Scenario("salt_road", "The Salt Road", _salt_road, years=2,
             blurb="Coastal and peaceful. Trade only, two years, no walls to hide behind."),
    Scenario("iron_marches", "The Iron Marches", _iron_marches,
             blurb="Ore under you, grain nowhere, and lords who already hate you."),
    Scenario("winter_crown", "The Winter Crown", _winter_crown, years=2.5,
             blurb="Midwinter, a month of bread and a short rope. The hard one."),
    Scenario("freebuild", "Freebuild", _freebuild, years=99,
             blurb="A hill, a long purse and nobody coming. No clock, no goal, "
                   "and every other system still running."),
]}

#: The order they are meant to be played in.
#: Freebuild is deliberately not in it. A campaign is an order of
#: difficulty with an ending at the end, and Freebuild has neither a
#: clock nor a goal -- putting it in the sequence would promise a
#: chapter that never closes. It is a scenario you choose, not a
#: chapter you reach. See OUTSIDE_CAMPAIGN.
CAMPAIGN: List[str] = ["salt_road", "marchlands", "iron_marches", "winter_crown"]

#: ...and every scenario must be in exactly one of the two, so that a
#: new one cannot be quietly orphaned between them.
#: The Siege is not in it either, and for the opposite reason to Freebuild:
#: it has a clock and nothing else. There is no economy to build and no march
#: to take, only one hill and one host, so it is a scenario you choose when
#: you want that -- not a chapter in a sequence about growing a holding.
OUTSIDE_CAMPAIGN: List[str] = ["freebuild", "siege"]


def scenario(key: str) -> Scenario:
    try:
        return SCENARIOS[key]
    except KeyError:
        raise KeyError(f"no scenario called {key!r}; "
                       f"choose from {', '.join(SCENARIOS)}") from None


def start(key: str = "marchlands", seed: int = 7, house: str = "plough",
          role: str = "lord") -> GameState:
    return scenario(key).start(seed=seed, house=house, role=role)
