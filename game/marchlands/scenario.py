"""The starting map.

Each foreign town is drawn so that at least one of its surpluses is another
town's shortage. Read the flows as a sentence: Caldmoor digs iron out of the
hills and cannot feed itself; Vantry grows more bread than it can eat and has
no smith. A cart between them is the whole game.
"""

from __future__ import annotations

import random

from typing import Dict, List, Optional, Tuple

from . import config as C
from .engine import GameState
from .events import EventEngine, RivalCompany
from .goods import ALL_KEYS
from .market import Market
from .settlement import Settlement
from .tech import HOUSES, Progress
from .world import ForeignTown, Site, World, make_town


#: What a seat has in its stores on the first morning.
OPENING_STORES = {
    "wheat": 180, "flour": 60, "bread": 220, "apples": 120, "cheese": 60,
    "wood": 280, "stone": 180, "planks": 60, "clay": 20, "ale": 30,
    "cloth": 20, "pottery": 20, "salt": 15, "iron": 20, "tools": 6,
    "spears": 20, "bows": 12,
}


def _towns() -> List[ForeignTown]:
    """The seven towns of the march, and the shore beyond them."""
    return [
        make_town("dunmere", "Dunmere", 30, 15,
                  produces={"wood": 14, "clay": 10},
                  consumes={"bread": 5, "salt": 2, "tools": 1.2, "ale": 3},
                  appetite=0.8, lawlessness=0.006, tariff=0.04,
                  lord="Reeve Halden", walls=260, muster=0.5,
                  blurb="A timber village a day's walk off. Everyone's first route."),
        make_town("vantry", "Vantry", -55, 20,
                  produces={"wheat": 22, "apples": 14, "cheese": 6},
                  consumes={"tools": 2.5, "pottery": 4, "cloth": 3.5, "salt": 3,
                            "iron": 2},
                  appetite=1.1, lawlessness=0.008, tariff=0.05,
                  lord="Dame Ysolt", walls=420, muster=0.8,
                  blurb="The breadbasket. Grain is cheap here and the smiths are not."),
        make_town("bruille", "Bruille", 10, -65,
                  produces={"ale": 10, "hops": 8, "cheese": 7},
                  consumes={"wood": 9, "stone": 7, "tools": 2, "iron": 2.5},
                  appetite=1.0, lawlessness=0.010, tariff=0.06,
                  lord="Abbot Gervase", walls=380, muster=0.7,
                  blurb="Brewers and cheesemongers, short of everything hard."),
        make_town("ostmark", "Ostmark", 85, 25,
                  produces={"weapons": 3.5, "iron": 5, "tools": 2.5},
                  consumes={"bread": 9, "ale": 6, "cloth": 4, "charcoal": 5,
                            "wheat": 5},
                  appetite=1.2, lawlessness=0.014, tariff=0.07, wealth=1.2,
                  lord="the Margrave Ekhart", walls=900, muster=1.6,
                  blurb="Armourers and garrisons. It eats far more than it grows."),
        make_town("caldmoor", "Caldmoor", -40, -95,
                  produces={"stone": 16, "iron_ore": 12, "charcoal": 6},
                  consumes={"bread": 11, "apples": 5, "ale": 5, "cloth": 4,
                            "pottery": 3},
                  appetite=1.1, lawlessness=0.018, tariff=0.05,
                  lord="Warden Ulf", walls=620, muster=1.1,
                  blurb="A mining camp in the highlands. Feed it and it pays in ore."),
        make_town("havnhold", "Havnhold", 60, 110,
                  produces={"salt": 10, "spice": 5},
                  consumes={"wheat": 8, "wood": 12, "iron": 4, "pottery": 4,
                            "planks": 6, "cloth": 5},
                  appetite=1.2, lawlessness=0.009, tariff=0.08, wealth=1.3,
                  lord="Portreeve Maren", walls=700, muster=1.2, port=True,
                  blurb="A salt port with ships from the south. The only spice on the coast."),
        make_town("marchand", "Marchand", -150, 90,
                  produces={"silk": 5, "spice": 6, "cloth": 7},
                  consumes={"weapons": 3, "tools": 4, "salt": 6, "cheese": 5,
                            "iron": 4, "pottery": 4, "wool": 10},
                  appetite=1.4, lawlessness=0.007, tariff=0.10, wealth=1.6,
                  lord="the Count of Marchand", walls=1100, muster=1.8, port=True,
                  blurb="The great fair, nine days out by road, four by sea."),
        make_town("caer_ithel", "Caer Ithel", -120, 150,
                  produces={"wool": 14, "cheese": 8, "salt": 5},
                  consumes={"iron": 4, "tools": 3, "ale": 5, "pottery": 4,
                            "planks": 5},
                  appetite=1.1, lawlessness=0.012, tariff=0.07, wealth=1.1,
                  lord="the Lady of Caer Ithel", walls=640, muster=1.0, port=True,
                  blurb="A wool haven on the western shore. No road worth the "
                        "name reaches it -- come by sea or not at all."),
    ]


def _sites() -> List[Site]:
    """Land nobody holds, for a price."""
    return [
        Site("sealow", "Sealow", 55, 75,
             {"fertile": 4, "forest": 3, "hills": 1, "clay": 2, "coast": 3,
              "urban": 16, "rampart": 8}, 2800,
             "Salt flats on the north shore, three days from Havnhold.",
             deposits={"stone": 3200.0, "iron_ore": 600.0}),
        Site("greyfell", "Greyfell", -25, -60,
             {"fertile": 3, "forest": 5, "hills": 6, "clay": 1, "coast": 0,
              "urban": 16, "rampart": 8}, 3200,
             "Iron and stone under the moor. Nothing much grows.",
             deposits={"stone": 42000.0, "iron_ore": 28000.0}),
    ]


def build_towns(world: World, seed: int, *, temper: Tuple[float, float] = (0.55, 1.50),
                aggression: Tuple[float, float] = (0.45, 1.65),
                hostility: Tuple[float, float] = (12.0, 60.0)) -> None:
    """Put the seven towns and the shore on the map.

    A scenario can turn the dials on the lords' patience without redrawing the
    geography: the same march, in a better or a worse decade.
    """
    for t in _towns():
        world.towns[t.key] = t
        world.place(t.key, t.x, t.y)
    stagger = random.Random(seed * 7919)
    for t in world.towns.values():
        # No two lords take offence at the same rate, and none of them start
        # from the same place -- otherwise they all declare on one morning.
        t.temper = temper[0] + (temper[1] - temper[0]) * stagger.random()
        t.aggression = aggression[0] + (aggression[1] - aggression[0]) * stagger.random()
        t.hostility = hostility[0] + (hostility[1] - hostility[0]) * stagger.random()
        t.ambition = 20.0 * stagger.random()


def build_sites(world: World) -> None:
    """Unclaimed land -- minus anything a scenario has already settled."""
    for site in _sites():
        if site.key in world.settlements:
            continue
        world.sites[site.key] = site


def found_seat(world: World, key: str, name: str, terrain: Dict[str, int],
               coords: Tuple[float, float], *, population: float,
               deposits: Dict[str, float], standing: Tuple[str, ...],
               stock: Dict[str, float],
               units: Optional[Dict[str, float]] = None) -> Settlement:
    """Raise a starting settlement with what it already has standing."""
    market = Market(name=name, stock={}, target={})
    home = Settlement(name=name, terrain=dict(terrain), market=market,
                      population=population, units=dict(units or {}),
                      deposits=dict(deposits))
    home.update_market_targets()
    for b in standing:
        home.start_build(b).days_left = 0
    # Stock the stores *after* raising what is already standing, so the opening
    # inventory is exactly what it says on the tin rather than whatever the
    # pre-built keep left behind.
    for k in ALL_KEYS:
        market.stock[k] = float(stock.get(k, 0))
        market.posted[k] = market.curve(k, market.stock[k])
    world.settlements[key] = home
    world.place(key, *coords)
    return home


def default_rivals() -> EventEngine:
    return EventEngine(rivals=[
        RivalCompany("the Vellani House", reach=1.3, nerve=0.10),
        RivalCompany("the Ostmark Guild", reach=0.9, nerve=0.16),
        RivalCompany("the Brotherhood of the Sea", reach=1.6, nerve=0.22),
    ])


def new_game(seed: int = 7, house: str = "plough") -> GameState:
    if house not in HOUSES:
        raise KeyError(f"no house called {house!r}; "
                       f"choose from {', '.join(HOUSES)}")
    world = World()

    home = found_seat(
        world, "aldworth", "Aldworth",
        {"fertile": 9, "forest": 5, "hills": 2, "clay": 3, "coast": 0,
         "urban": 30, "rampart": 14}, (0.0, 0.0),
        population=130.0,
        deposits={"stone": 9000.0, "iron_ore": 5200.0},
        units={"spearman": 4, "archer": 3},
        # The seat comes with roofs over most heads and the old lord's stores.
        standing=("keep", "palisade", "barracks", "cottage", "cottage", "cottage",
                  "cottage", "cottage", "farm", "farm", "woodcutter", "granary",
                  "warehouse"),
        stock=OPENING_STORES)

    # ------------------------------------------------------------- the road
    build_towns(world, seed)
    build_sites(world)

    game = GameState(world=world, treasury=1800.0, seed=seed, house=house,
                     progress=Progress(researched={house}))
    game.events = default_rivals()
    home.wall_hp = home.wall_max(game.progress)
    # One cart to start, so the first day has a decision in it.
    game.new_caravan("aldworth", "Old Mare")
    game.treasury += C.CARAVAN_COST      # the first one is a gift
    game._outlay = 0.0                   # ...and the ledger should not bill it
    return game
