"""Buildings: land, labour, and the production chains that join them.

A settlement's economy is a directed graph over goods. No settlement has every
terrain, so no settlement can close every chain on its own -- that gap is what
makes the trade layer load-bearing rather than decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

# Terrain a building must occupy a slot of.
FERTILE = "fertile"
FOREST = "forest"
HILLS = "hills"
CLAY = "clay"
COAST = "coast"
URBAN = "urban"
RAMPART = "rampart"      # the castle perimeter, not the town plots
TERRAINS = (FERTILE, FOREST, HILLS, CLAY, COAST, URBAN, RAMPART)

PRIMARY = "primary"
INDUSTRY = "industry"
CIVIC = "civic"
CASTLE = "castle"
CASTLE = "castle"


@dataclass(frozen=True)
class Building:
    key: str
    name: str
    category: str
    terrain: str
    jobs: int
    build_cost: Dict[str, float]        # 'coin' plus goods
    build_days: int
    inputs: Dict[str, float] = field(default_factory=dict)   # per day, full staff
    outputs: Dict[str, float] = field(default_factory=dict)  # per day, full staff
    upkeep: float = 0.0                 # coins per day
    season: str = ""                    # '', 'field' or 'orchard'
    effects: Dict[str, float] = field(default_factory=dict)
    age: int = 1                        # the age that unlocks it
    draws: str = ""                     # settlement deposit its output comes out of
    note: str = ""

    @property
    def is_producer(self) -> bool:
        return bool(self.outputs)


def _b(*args, **kwargs) -> Building:
    return Building(*args, **kwargs)


BUILDINGS: Dict[str, Building] = {b.key: b for b in [
    # --- primary production -------------------------------------------------
    _b("farm", "Wheat Farm", PRIMARY, FERTILE, 3,
       {"coin": 90, "wood": 15}, 4, {}, {"wheat": 12.0}, season="field",
       note="Wheat is the base of the bread chain and half the brewery's mash."),
    _b("orchard", "Orchard", PRIMARY, FERTILE, 2,
       {"coin": 70, "wood": 10}, 6, {}, {"apples": 9.0}, season="orchard",
       note="Cheap calories, but autumn gives you a year's worth in one month."),
    _b("hop_farm", "Hop Garden", PRIMARY, FERTILE, 2,
       {"coin": 80, "wood": 12}, 4, {}, {"hops": 5.0}, season="field"),
    _b("sheep_farm", "Sheep Pasture", PRIMARY, FERTILE, 2,
       {"coin": 100, "wood": 18}, 5, {}, {"wool": 6.0}, season="field"),
    _b("dairy", "Dairy", PRIMARY, FERTILE, 2,
       {"coin": 120, "wood": 20}, 5, {}, {"cheese": 5.0}, season="field"),
    _b("woodcutter", "Woodcutter's Hut", PRIMARY, FOREST, 2,
       {"coin": 50, "wood": 5}, 3, {}, {"wood": 10.0}),
    _b("quarry", "Quarry", PRIMARY, HILLS, 3,
       {"coin": 140, "wood": 25}, 7, {}, {"stone": 8.0}, draws="stone",
       note="Works a seam. When the hill is quarried out, the sheds stand idle."),
    _b("iron_mine", "Iron Mine", PRIMARY, HILLS, 4,
       {"coin": 200, "wood": 35, "planks": 10}, 9, {}, {"iron_ore": 7.0},
       age=2, draws="iron_ore",
       note="Works a seam. Iron under one hill does not last a lifetime."),
    _b("clay_pit", "Clay Pit", PRIMARY, CLAY, 2,
       {"coin": 60, "wood": 10}, 3, {}, {"clay": 8.0}),
    _b("saltworks", "Saltworks", PRIMARY, COAST, 3,
       {"coin": 180, "wood": 30, "stone": 15}, 8, {}, {"salt": 4.0},
       note="Salt keeps the winter meat and sells for a great deal inland."),

    # --- processing ---------------------------------------------------------
    _b("mill", "Windmill", INDUSTRY, URBAN, 2,
       {"coin": 160, "wood": 30, "stone": 10}, 6, {"wheat": 14.0}, {"flour": 11.0}),
    _b("bakery", "Bakery", INDUSTRY, URBAN, 2,
       {"coin": 150, "wood": 20, "stone": 12}, 5, {"flour": 10.0, "wood": 2.0},
       {"bread": 12.0}),
    _b("brewery", "Brewery", INDUSTRY, URBAN, 2,
       {"coin": 170, "wood": 25, "stone": 10}, 6, {"hops": 4.0, "wheat": 4.0},
       {"ale": 6.0}, age=2),
    _b("sawmill", "Sawmill", INDUSTRY, URBAN, 2,
       {"coin": 130, "wood": 25}, 5, {"wood": 8.0}, {"planks": 7.0}),
    _b("charcoal_burner", "Charcoal Burner", INDUSTRY, FOREST, 1,
       {"coin": 60, "wood": 8}, 3, {"wood": 6.0}, {"charcoal": 5.0}),
    _b("smelter", "Smelter", INDUSTRY, URBAN, 3,
       {"coin": 260, "wood": 30, "stone": 40}, 9,
       {"iron_ore": 6.0, "charcoal": 4.0}, {"iron": 5.0}, age=2),
    _b("weaver", "Weaver's Shop", INDUSTRY, URBAN, 2,
       {"coin": 140, "wood": 20, "planks": 8}, 5, {"wool": 5.0}, {"cloth": 4.0}, age=2),
    _b("kiln", "Pottery Kiln", INDUSTRY, URBAN, 2,
       {"coin": 150, "wood": 20, "stone": 15}, 5, {"clay": 6.0, "charcoal": 2.0},
       {"pottery": 5.0}, age=2),
    _b("blacksmith", "Blacksmith", INDUSTRY, URBAN, 2,
       {"coin": 220, "wood": 25, "stone": 20, "iron": 5}, 7,
       {"iron": 3.0, "planks": 2.0}, {"tools": 3.0}, age=2),
    _b("armoury", "Armoury", INDUSTRY, URBAN, 3,
       {"coin": 320, "wood": 30, "stone": 35, "iron": 10}, 10,
       {"iron": 4.0, "charcoal": 3.0}, {"weapons": 3.0},
       note="Swords and pole-arms: a fortune in a town at war, scrap in peace.", age=3),
    _b("poleturner", "Poleturner", INDUSTRY, URBAN, 1,
       {"coin": 90, "wood": 15}, 4, {"wood": 5.0}, {"spears": 4.0},
       note="The cheapest way to put a weapon in a levy's hands."),
    _b("fletcher", "Fletcher", INDUSTRY, URBAN, 2,
       {"coin": 130, "wood": 20, "planks": 6}, 5, {"wood": 6.0, "cloth": 1.0},
       {"bows": 3.0}, age=2,
       note="Bows are worth three times as much on a battlement as in a field."),
    _b("armourer", "Armourer", INDUSTRY, URBAN, 3,
       {"coin": 300, "wood": 25, "stone": 30, "iron": 12}, 9,
       {"iron": 5.0, "charcoal": 3.0}, {"armour": 2.0}, age=3,
       note="Armour is the difference between a man-at-arms and a casualty."),

    # --- civic --------------------------------------------------------------
    _b("hovel", "Hovel", CIVIC, URBAN, 0,
       {"coin": 35, "wood": 8}, 2, {}, {}, effects={"housing": 8}),
    _b("cottage", "Cottage Row", CIVIC, URBAN, 0,
       {"coin": 110, "wood": 20, "planks": 6}, 4, {}, {},
       effects={"housing": 22, "mood": 1.0}),
    _b("townhouse", "Townhouses", CIVIC, URBAN, 0,
       {"coin": 380, "wood": 30, "planks": 25, "stone": 20}, 7, {}, {},
       effects={"housing": 55, "mood": 2.0},
       note="The only way past a few hundred souls on one hill.", age=3),
    _b("warehouse", "Warehouse", CIVIC, URBAN, 1,
       {"coin": 160, "wood": 35, "planks": 10}, 5, {}, {},
       effects={"storage": 500}),
    _b("granary", "Granary", CIVIC, URBAN, 1,
       {"coin": 140, "wood": 30, "stone": 10}, 5, {}, {},
       effects={"storage": 250, "preserve": 0.5},
       note="Halves spoilage across the settlement. Cheaper than a second farm."),
    _b("chapel", "Chapel", CIVIC, URBAN, 0,
       {"coin": 200, "wood": 15, "stone": 45}, 8, {}, {}, upkeep=3.0,
       effects={"mood": 5.0}, age=2),
    _b("inn", "Inn", CIVIC, URBAN, 1,
       {"coin": 180, "wood": 30, "planks": 8}, 6, {"ale": 3.0}, {}, upkeep=2.0,
       effects={"mood": 7.0},
       note="Only cheers anyone up on days the ale actually arrives."),
    _b("market", "Market Square", CIVIC, URBAN, 2,
       {"coin": 220, "wood": 25, "stone": 30}, 7, {}, {}, upkeep=2.0,
       effects={"spread": -0.03, "mood": 2.0},
       note="Narrows the spread you pay on every deal struck in this town.", age=2),
    _b("trading_post", "Trading Post", CIVIC, URBAN, 2,
       {"coin": 300, "wood": 40, "planks": 15, "stone": 20}, 9, {}, {}, upkeep=4.0,
       effects={"caravan_slots": 1, "tariff_relief": 1.0},
       note="Each post cuts foreign tolls and lets you run another caravan.", age=2),
    _b("harbour", "Harbour", CIVIC, COAST, 2,
       {"coin": 420, "wood": 60, "planks": 40, "stone": 60}, 10, {}, {}, upkeep=4.0,
       age=2, effects={"port": 1.0, "caravan_slots": 1, "storage": 200},
       note="A quay, a crane and a customs shed. Ships may call, and one hull "
            "carries what four carts carry."),
    _b("stable", "Stables", CIVIC, URBAN, 1,
       {"coin": 200, "wood": 35, "planks": 10}, 6, {}, {}, upkeep=3.0,
       effects={"caravan_speed": 5.0, "caravan_capacity": 50.0}, age=3),
    _b("guardhouse", "Guardhouse", CIVIC, URBAN, 0,
       {"coin": 180, "wood": 20, "stone": 40}, 7, {}, {}, upkeep=2.0,
       effects={"defense": 12.0}),
    # --- the castle ---------------------------------------------------------
    _b("keep", "The Keep", CASTLE, RAMPART, 0,
       {"coin": 900, "stone": 220, "planks": 40}, 20, {}, {}, upkeep=2.0,
       effects={"wall": 400.0, "defense": 20.0, "storage": 150.0, "mood": 3.0},
       note="Your seat. Lose it and you lose everything; you may only hold one."),
    _b("palisade", "Palisade", CASTLE, RAMPART, 0,
       {"coin": 70, "wood": 35}, 3, {}, {},
       effects={"wall": 160.0, "defense": 4.0},
       note="Timber buys you a season, not a siege."),
    _b("stone_wall", "Stone Wall", CASTLE, RAMPART, 0,
       {"coin": 190, "stone": 95}, 7, {}, {}, age=2,
       effects={"wall": 420.0, "defense": 8.0}),
    _b("gatehouse", "Gatehouse", CASTLE, RAMPART, 0,
       {"coin": 240, "stone": 70, "planks": 20}, 8, {}, {}, upkeep=1.0, age=2,
       effects={"wall": 260.0, "defense": 12.0, "sortie": 1.0},
       note="Lets a garrison sortie at besiegers instead of waiting behind stone."),
    _b("wall_tower", "Wall Tower", CASTLE, RAMPART, 0,
       {"coin": 260, "stone": 80}, 10, {}, {}, upkeep=1.0, age=3,
       effects={"wall": 220.0, "defense": 25.0, "battlement": 12.0},
       note="Raiders price your walls before they price your granary."),

    # --- war and learning ---------------------------------------------------
    _b("barracks", "Barracks", CASTLE, URBAN, 1,
       {"coin": 160, "wood": 30, "stone": 20}, 6, {}, {}, upkeep=2.0,
       effects={"muster": 1.0},
       note="Coin and arms go in, soldiers come out -- and out of the labour pool."),
    _b("siege_yard", "Siege Yard", CASTLE, URBAN, 2,
       {"coin": 280, "wood": 40, "planks": 25, "iron": 8}, 9, {}, {}, upkeep=3.0,
       age=3, effects={"siege": 1.0},
       note="Rams and trebuchets. Walls do not fall to men on foot."),
    _b("guildhall", "Guildhall", CIVIC, URBAN, 2,
       {"coin": 260, "wood": 30, "stone": 35, "planks": 15}, 8, {}, {}, upkeep=3.0,
       age=2, effects={"research": 1.0, "mood": 1.0},
       note="Where the crafts are written down. Nothing is researched without one."),
    _b("cathedral", "Cathedral", CIVIC, URBAN, 3,
       {"coin": 6000, "stone": 900, "planks": 250, "iron": 120, "tools": 60}, 120,
       {}, {}, upkeep=12.0, age=4,
       effects={"mood": 15.0, "wonder": 1.0},
       note="A lifetime's work. Finish it, hold it, and the marches are yours."),

    # --- carrot and stick ---------------------------------------------------
    _b("maypole", "Maypole", CIVIC, URBAN, 0,
       {"coin": 40, "wood": 12}, 2, {}, {}, effects={"mood": 4.0}),
    _b("garden", "Pleasure Garden", CIVIC, URBAN, 0,
       {"coin": 160, "wood": 15, "stone": 25}, 6, {}, {}, upkeep=2.0, age=2,
       effects={"mood": 8.0}),
    _b("stocks", "Stocks", CIVIC, URBAN, 0,
       {"coin": 50, "wood": 15}, 2, {}, {}, effects={"fear": 2.0},
       note="Fear drives the work along, and drives the people out."),
    _b("gallows", "Gallows", CIVIC, URBAN, 0,
       {"coin": 90, "wood": 25}, 3, {}, {}, upkeep=1.0, effects={"fear": 4.0}),
]}

ALL_BUILDING_KEYS = tuple(BUILDINGS.keys())


def building(key: str) -> Building:
    try:
        return BUILDINGS[key]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown building {key!r}") from None


def resolve(prefix: str) -> str:
    p = prefix.strip().lower().replace(" ", "_").replace("-", "_")
    if p in BUILDINGS:
        return p
    hits = [k for k in ALL_BUILDING_KEYS if k.startswith(p)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise KeyError(f"no building matches {prefix!r}")
    raise KeyError(f"{prefix!r} is ambiguous: {', '.join(hits)}")


def producers_of(good_key: str) -> Tuple[str, ...]:
    return tuple(k for k, b in BUILDINGS.items() if good_key in b.outputs)


def consumers_of(good_key: str) -> Tuple[str, ...]:
    return tuple(k for k, b in BUILDINGS.items() if good_key in b.inputs)
