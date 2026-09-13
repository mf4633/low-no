"""The starting map.

Each foreign town is drawn so that at least one of its surpluses is another
town's shortage. Read the flows as a sentence: Caldmoor digs iron out of the
hills and cannot feed itself; Vantry grows more bread than it can eat and has
no smith. A cart between them is the whole game.
"""

from __future__ import annotations

from . import config as C
from .engine import GameState
from .events import EventEngine, RivalCompany
from .goods import ALL_KEYS
from .market import Market
from .settlement import Settlement
from .world import Site, World, make_town


def _home_market(name: str, pop: float) -> Market:
    m = Market(name=name, stock={}, target={})
    start = {"wheat": 180, "flour": 60, "bread": 220, "apples": 120, "cheese": 60,
             "wood": 260, "stone": 140, "planks": 50, "clay": 20, "ale": 30,
             "cloth": 20, "pottery": 20, "salt": 15, "iron": 20, "tools": 6}
    for k in ALL_KEYS:
        m.stock[k] = float(start.get(k, 0))
        m.target[k] = max(25.0, 0.45 * pop)
        m.posted[k] = m.curve(k, m.stock[k])
    return m


def new_game(seed: int = 7) -> GameState:
    world = World()

    # ---------------------------------------------------------------- home
    pop = 130.0
    home = Settlement(
        name="Aldworth",
        terrain={"fertile": 9, "forest": 5, "hills": 2, "clay": 3, "coast": 0,
                 "urban": 30},
        market=_home_market("Aldworth", pop),
        population=pop,
    )
    home.update_market_targets()
    # The seat comes with roofs over most heads and the old lord's stores.
    for key in ("cottage", "cottage", "cottage", "cottage", "cottage",
                "farm", "farm", "woodcutter", "granary", "warehouse"):
        inst = home.start_build(key)
        inst.days_left = 0                       # already standing at day one
    world.settlements["aldworth"] = home
    world.place("aldworth", 0.0, 0.0)

    # ------------------------------------------------------------- the road
    towns = [
        make_town("dunmere", "Dunmere", 30, 15,
                  produces={"wood": 14, "clay": 10},
                  consumes={"bread": 5, "salt": 2, "tools": 1.2, "ale": 3},
                  appetite=0.8, lawlessness=0.006, tariff=0.04,
                  blurb="A timber village a day's walk off. Everyone's first route."),
        make_town("vantry", "Vantry", -55, 20,
                  produces={"wheat": 22, "apples": 14, "cheese": 6},
                  consumes={"tools": 2.5, "pottery": 4, "cloth": 3.5, "salt": 3,
                            "iron": 2},
                  appetite=1.1, lawlessness=0.008, tariff=0.05,
                  blurb="The breadbasket. Grain is cheap here and the smiths are not."),
        make_town("bruille", "Bruille", 10, -65,
                  produces={"ale": 10, "hops": 8, "cheese": 7},
                  consumes={"wood": 9, "stone": 7, "tools": 2, "iron": 2.5},
                  appetite=1.0, lawlessness=0.010, tariff=0.06,
                  blurb="Brewers and cheesemongers, short of everything hard."),
        make_town("ostmark", "Ostmark", 85, 25,
                  produces={"weapons": 3.5, "iron": 5, "tools": 2.5},
                  consumes={"bread": 9, "ale": 6, "cloth": 4, "charcoal": 5,
                            "wheat": 5},
                  appetite=1.2, lawlessness=0.014, tariff=0.07, wealth=1.2,
                  blurb="Armourers and garrisons. It eats far more than it grows."),
        make_town("caldmoor", "Caldmoor", -40, -95,
                  produces={"stone": 16, "iron_ore": 12, "charcoal": 6},
                  consumes={"bread": 11, "apples": 5, "ale": 5, "cloth": 4,
                            "pottery": 3},
                  appetite=1.1, lawlessness=0.018, tariff=0.05,
                  blurb="A mining camp in the highlands. Feed it and it pays in ore."),
        make_town("havnhold", "Havnhold", 60, 110,
                  produces={"salt": 7, "spice": 4, "silk": 2.5},
                  consumes={"wheat": 8, "wood": 12, "iron": 4, "pottery": 4,
                            "planks": 6},
                  appetite=1.2, lawlessness=0.009, tariff=0.08, wealth=1.3,
                  blurb="A salt port with ships from the south. The only spice on the coast."),
        make_town("marchand", "Marchand", -150, 90,
                  produces={"silk": 4, "spice": 6, "cloth": 5},
                  consumes={"weapons": 3, "tools": 4, "salt": 4, "cheese": 5,
                            "iron": 4, "pottery": 4},
                  appetite=1.4, lawlessness=0.007, tariff=0.10, wealth=1.6,
                  blurb="The great fair, nine days out. Steep tolls, deep pockets."),
    ]
    for t in towns:
        world.towns[t.key] = t
        world.place(t.key, t.x, t.y)

    # ------------------------------------------------------------- frontier
    for site in [
        Site("sealow", "Sealow", 55, 75,
             {"fertile": 4, "forest": 3, "hills": 0, "clay": 2, "coast": 3,
              "urban": 14}, 2800,
             "Salt flats on the north shore, three days from Havnhold."),
        Site("greyfell", "Greyfell", -25, -60,
             {"fertile": 3, "forest": 5, "hills": 6, "clay": 1, "coast": 0,
              "urban": 14}, 3200,
             "Iron and stone under the moor. Nothing much grows."),
    ]:
        world.sites[site.key] = site

    game = GameState(world=world, treasury=1800.0, seed=seed)
    game.events = EventEngine(rivals=[
        RivalCompany("the Vellani House", reach=1.3, nerve=0.10),
        RivalCompany("the Ostmark Guild", reach=0.9, nerve=0.16),
        RivalCompany("the Brotherhood of the Sea", reach=1.6, nerve=0.22),
    ])
    # One cart to start, so the first day has a decision in it.
    car, _ = game.new_caravan("aldworth", "Old Mare")
    game.treasury += C.CARAVAN_COST      # the first one is a gift
    return game
