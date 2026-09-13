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
TERRAINS = (FERTILE, FOREST, HILLS, CLAY, COAST, URBAN)

PRIMARY = "primary"
INDUSTRY = "industry"
CIVIC = "civic"


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
       {"coin": 140, "wood": 25}, 7, {}, {"stone": 8.0}),
    _b("iron_mine", "Iron Mine", PRIMARY, HILLS, 4,
       {"coin": 200, "wood": 35, "planks": 10}, 9, {}, {"iron_ore": 7.0}),
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
       {"ale": 6.0}),
    _b("sawmill", "Sawmill", INDUSTRY, URBAN, 2,
       {"coin": 130, "wood": 25}, 5, {"wood": 8.0}, {"planks": 7.0}),
    _b("charcoal_burner", "Charcoal Burner", INDUSTRY, FOREST, 1,
       {"coin": 60, "wood": 8}, 3, {"wood": 6.0}, {"charcoal": 5.0}),
    _b("smelter", "Smelter", INDUSTRY, URBAN, 3,
       {"coin": 260, "wood": 30, "stone": 40}, 9,
       {"iron_ore": 6.0, "charcoal": 4.0}, {"iron": 5.0}),
    _b("weaver", "Weaver's Shop", INDUSTRY, URBAN, 2,
       {"coin": 140, "wood": 20, "planks": 8}, 5, {"wool": 5.0}, {"cloth": 4.0}),
    _b("kiln", "Pottery Kiln", INDUSTRY, URBAN, 2,
       {"coin": 150, "wood": 20, "stone": 15}, 5, {"clay": 6.0, "charcoal": 2.0},
       {"pottery": 5.0}),
    _b("blacksmith", "Blacksmith", INDUSTRY, URBAN, 2,
       {"coin": 220, "wood": 25, "stone": 20, "iron": 5}, 7,
       {"iron": 3.0, "planks": 2.0}, {"tools": 3.0}),
    _b("armoury", "Armoury", INDUSTRY, URBAN, 3,
       {"coin": 320, "wood": 30, "stone": 35, "iron": 10}, 10,
       {"iron": 4.0, "charcoal": 3.0}, {"weapons": 3.0},
       note="Weapons sell for a fortune in a town at war -- and for scrap in peace."),

    # --- civic --------------------------------------------------------------
    _b("hovel", "Hovel", CIVIC, URBAN, 0,
       {"coin": 35, "wood": 8}, 2, {}, {}, effects={"housing": 8}),
    _b("cottage", "Cottage Row", CIVIC, URBAN, 0,
       {"coin": 110, "wood": 20, "planks": 6}, 4, {}, {},
       effects={"housing": 22, "mood": 1.0}),
    _b("townhouse", "Townhouses", CIVIC, URBAN, 0,
       {"coin": 380, "wood": 30, "planks": 25, "stone": 20}, 7, {}, {},
       effects={"housing": 55, "mood": 2.0},
       note="The only way past a few hundred souls on one hill."),
    _b("warehouse", "Warehouse", CIVIC, URBAN, 1,
       {"coin": 160, "wood": 35, "planks": 10}, 5, {}, {},
       effects={"storage": 500}),
    _b("granary", "Granary", CIVIC, URBAN, 1,
       {"coin": 140, "wood": 30, "stone": 10}, 5, {}, {},
       effects={"storage": 250, "preserve": 0.5},
       note="Halves spoilage across the settlement. Cheaper than a second farm."),
    _b("chapel", "Chapel", CIVIC, URBAN, 0,
       {"coin": 200, "wood": 15, "stone": 45}, 8, {}, {}, upkeep=3.0,
       effects={"mood": 5.0}),
    _b("inn", "Inn", CIVIC, URBAN, 1,
       {"coin": 180, "wood": 30, "planks": 8}, 6, {"ale": 3.0}, {}, upkeep=2.0,
       effects={"mood": 7.0},
       note="Only cheers anyone up on days the ale actually arrives."),
    _b("market", "Market Square", CIVIC, URBAN, 2,
       {"coin": 220, "wood": 25, "stone": 30}, 7, {}, {}, upkeep=2.0,
       effects={"spread": -0.03, "mood": 2.0},
       note="Narrows the spread you pay on every deal struck in this town."),
    _b("trading_post", "Trading Post", CIVIC, URBAN, 2,
       {"coin": 300, "wood": 40, "planks": 15, "stone": 20}, 9, {}, {}, upkeep=4.0,
       effects={"caravan_slots": 1, "tariff_relief": 1.0},
       note="Each post cuts foreign tolls and lets you run another caravan."),
    _b("stable", "Stables", CIVIC, URBAN, 1,
       {"coin": 200, "wood": 35, "planks": 10}, 6, {}, {}, upkeep=3.0,
       effects={"caravan_speed": 5.0, "caravan_capacity": 50.0}),
    _b("guardhouse", "Guardhouse", CIVIC, URBAN, 0,
       {"coin": 180, "wood": 20, "stone": 40}, 7, {}, {}, upkeep=2.0,
       effects={"defense": 12.0}),
    _b("wall_tower", "Wall Tower", CIVIC, URBAN, 0,
       {"coin": 260, "stone": 80}, 10, {}, {}, upkeep=1.0,
       effects={"defense": 25.0},
       note="Raiders price your walls before they price your granary."),
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
