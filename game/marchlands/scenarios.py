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
from .scenario import (OPENING_STORES, build_sites, build_towns, default_rivals,
                       found_seat, new_game)
from .tech import HOUSES, Progress
from .world import World


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    build: Callable[[int, str], GameState]
    blurb: str = ""
    years: float = 3

    def start(self, seed: int = 7, house: str = "plough") -> GameState:
        if house not in HOUSES:
            raise KeyError(f"no house called {house!r}; "
                           f"choose from {', '.join(HOUSES)}")
        g = self.build(seed, house)
        g.scenario = self.key
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


SCENARIOS: Dict[str, Scenario] = {s.key: s for s in [
    Scenario("marchlands", "The Marchlands", _marchlands,
             blurb="The full march. One hill, seven towns, three ways to win."),
    Scenario("salt_road", "The Salt Road", _salt_road, years=2,
             blurb="Coastal and peaceful. Trade only, two years, no walls to hide behind."),
    Scenario("iron_marches", "The Iron Marches", _iron_marches,
             blurb="Ore under you, grain nowhere, and lords who already hate you."),
    Scenario("winter_crown", "The Winter Crown", _winter_crown, years=2.5,
             blurb="Midwinter, a month of bread and a short rope. The hard one."),
]}

#: The order they are meant to be played in.
CAMPAIGN: List[str] = ["salt_road", "marchlands", "iron_marches", "winter_crown"]


def scenario(key: str) -> Scenario:
    try:
        return SCENARIOS[key]
    except KeyError:
        raise KeyError(f"no scenario called {key!r}; "
                       f"choose from {', '.join(SCENARIOS)}") from None


def start(key: str = "marchlands", seed: int = 7, house: str = "plough") -> GameState:
    return scenario(key).start(seed=seed, house=house)
