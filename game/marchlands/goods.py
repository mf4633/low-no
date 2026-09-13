"""Goods: the atoms of the economy.

Every good carries the parameters the market and logistics layers need:
what it is worth at equilibrium, how much cart space it eats, how fast it
rots, and how violently its price reacts to scarcity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

FOOD = "food"
DRINK = "drink"
RAW = "raw"
MATERIAL = "material"
FINISHED = "finished"
LUXURY = "luxury"


@dataclass(frozen=True)
class Good:
    key: str
    name: str
    category: str
    base_price: float          # coins per unit at equilibrium stock
    weight: float = 1.0        # cart units consumed per good unit
    spoilage: float = 0.0      # fraction of stock lost per day in storage
    elasticity: float = 0.55   # price response to scarcity (higher = wilder)
    foreign_only: bool = False # cannot be produced in your settlements
    nourish: float = 0.0       # days of ration one unit covers (0 = not food)
    tags: tuple = field(default_factory=tuple)

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


def _g(*args, **kwargs) -> Good:
    return Good(*args, **kwargs)


GOODS: Dict[str, Good] = {g.key: g for g in [
    # --- primary production -------------------------------------------------
    _g("wheat",    "Wheat",     RAW,      3.0,  1.0, 0.002, 0.50, nourish=0.6,
       tags=("ration",)),   # gruel: edible, and a poor use of grain
    _g("hops",     "Hops",      RAW,     4.0,  0.8, 0.004, 0.60),
    _g("apples",   "Apples",    FOOD,    4.0,  1.0, 0.020, 0.55, nourish=0.8,
       tags=("ration",)),
    _g("wool",     "Wool",      RAW,     4.5,  0.9, 0.000, 0.55),
    _g("cheese",   "Cheese",    FOOD,    6.5,  0.7, 0.008, 0.55, nourish=1.5,
       tags=("ration",)),
    _g("wood",     "Wood",      RAW,      2.5,  1.2, 0.000, 0.45),
    _g("stone",    "Stone",     RAW,      3.5,  2.0, 0.000, 0.40),
    _g("clay",     "Clay",      RAW,      2.2,  1.5, 0.000, 0.45),
    _g("iron_ore", "Iron Ore",  RAW,     5.0,  1.6, 0.000, 0.50),
    _g("salt",     "Salt",      MATERIAL,7.0,  0.6, 0.000, 0.65, tags=("comfort",)),

    # --- secondary processing ----------------------------------------------
    _g("flour",    "Flour",     MATERIAL,6.0,  0.9, 0.003, 0.55),
    _g("planks",   "Planks",    MATERIAL,5.0,  1.0, 0.000, 0.50),
    _g("charcoal", "Charcoal",  MATERIAL,4.5,  0.7, 0.000, 0.50),
    _g("iron",     "Iron",      MATERIAL,14.0,  1.2, 0.000, 0.55),
    _g("cloth",    "Cloth",     MATERIAL,10.0,  0.5, 0.000, 0.60, tags=("comfort",)),
    _g("pottery",  "Pottery",   MATERIAL,7.5,  0.8, 0.000, 0.55, tags=("comfort",)),

    # --- finished goods -----------------------------------------------------
    _g("bread",    "Bread",     FOOD,    8.0,  0.8, 0.050, 0.55, nourish=1.3,
       tags=("ration",)),
    _g("ale",      "Ale",       DRINK,   8.0,  1.1, 0.004, 0.60, tags=("comfort",)),
    _g("tools",    "Tools",     FINISHED,26.0,  0.9, 0.000, 0.60),
    _g("weapons",  "Weapons",   FINISHED,36.0, 1.0, 0.000, 0.70),

    # --- arms: the bridge from the workshop to the muster field -------------
    _g("spears",   "Spears",    FINISHED, 9.0,  1.0, 0.000, 0.55, tags=("arms",)),
    _g("bows",     "Bows",      FINISHED,16.0,  0.6, 0.000, 0.60, tags=("arms",)),
    _g("armour",   "Armour",    FINISHED,52.0,  1.1, 0.000, 0.70, tags=("arms",)),

    # --- imports only -------------------------------------------------------
    _g("spice",    "Spice",     LUXURY, 55.0,  0.2, 0.001, 0.80, foreign_only=True,
       tags=("luxury",)),
    _g("silk",     "Silk",      LUXURY, 80.0,  0.2, 0.000, 0.85, foreign_only=True,
       tags=("luxury",)),
]}

ALL_KEYS = tuple(GOODS.keys())

#: Goods the commons will eat when rationed, dearest nourishment last.
RATION_GOODS = tuple(k for k, g in GOODS.items() if g.nourish > 0)


def nourishment(cargo: Dict[str, float]) -> float:
    """Rations covered by a pile of food."""
    return sum(GOODS[k].nourish * q for k, q in cargo.items() if q > 0)
#: Goods that lift mood but are not food.
COMFORT_GOODS = tuple(k for k, g in GOODS.items() if "comfort" in g.tags)
LUXURY_GOODS = tuple(k for k, g in GOODS.items() if "luxury" in g.tags)
#: Goods that arm a soldier rather than feed or please one.
ARMS_GOODS = tuple(k for k, g in GOODS.items() if "arms" in g.tags) + ("weapons",)


def good(key: str) -> Good:
    try:
        return GOODS[key]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown good {key!r}; known: {', '.join(ALL_KEYS)}") from None


def cargo_weight(cargo: Dict[str, float]) -> float:
    """Cart units consumed by a cargo manifest."""
    return sum(GOODS[k].weight * q for k, q in cargo.items() if q > 0)


def resolve(prefix: str) -> str:
    """Resolve a user-typed good name or unambiguous prefix to a key."""
    p = prefix.strip().lower().replace(" ", "_")
    if p in GOODS:
        return p
    hits = [k for k in ALL_KEYS if k.startswith(p)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise KeyError(f"no good matches {prefix!r}")
    raise KeyError(f"{prefix!r} is ambiguous: {', '.join(hits)}")
