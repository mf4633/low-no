"""Ages and technologies -- the long arc of the game.

An age is a gate: it costs a great deal, takes weeks, and opens a tier of
buildings, techs and soldiers. A technology is a permanent multiplier bought
once. Together they are what stops a good opening from being the whole game:
the town you can run in the Age of Clearing is not the town you need by the
Age of the Crown.

Effects are named by convention. Anything in `MULTIPLIERS` compounds (1.2 and
1.25 make 1.5); everything else adds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

MULTIPLIERS = {
    "yield_field", "yield_mine", "yield_craft", "spoilage", "tariff",
    "wall", "attack", "defense", "recruit_cost", "research_speed",
    "housing", "deposit_yield", "siege",
}
ADDITIONS = {
    "productivity", "storage", "cart_capacity", "cart_speed", "mood",
    "interest", "caravan_slots",
}


@dataclass(frozen=True)
class Age:
    level: int
    name: str
    cost: Dict[str, float]
    days: int
    needs: Tuple[str, ...] = ()        # buildings that must already stand
    blurb: str = ""


AGES: Dict[int, Age] = {a.level: a for a in [
    Age(1, "Age of Clearing", {}, 0, (),
        "Fields, timber and a road out. Everything else is ambition."),
    Age(2, "Age of Craft", {"coin": 700, "wood": 160, "stone": 90}, 22,
        ("mill",),
        "Workshops, stone walls, a market worth the name, and letters of credit."),
    Age(3, "Age of the Castle", {"coin": 2800, "stone": 280, "iron": 70,
                                 "planks": 100}, 32,
        ("guildhall", "keep"),
        "Armour, towers, siege engines and horse. The march stops being quiet."),
    Age(4, "Age of the Crown", {"coin": 9000, "stone": 650, "tools": 150,
                                "armour": 40}, 45,
        ("armourer",),
        "Trebuchets, chivalry, a royal charter -- and a cathedral, if you dare."),
]}
MAX_AGE = max(AGES)


@dataclass(frozen=True)
class Tech:
    key: str
    name: str
    age: int
    cost: Dict[str, float]
    days: int
    effects: Dict[str, float] = field(default_factory=dict)
    prereq: str = ""
    unlocks: Tuple[str, ...] = ()      # unit keys this makes available
    hidden: bool = False               # a house's birthright, never researched
    blurb: str = ""


def _t(*args, **kwargs) -> Tech:
    return Tech(*args, **kwargs)


TECHS: Dict[str, Tech] = {t.key: t for t in [
    # --- Age of Clearing ----------------------------------------------------
    _t("heavy_plough", "Heavy Plough", 1, {"coin": 220, "wood": 50}, 12,
       {"yield_field": 1.20}, blurb="The mouldboard turns the heavy soils."),
    _t("scythes", "Scythes and Sickles", 1, {"coin": 260, "tools": 12}, 12,
       {"yield_field": 1.15}),
    _t("pit_sawing", "Pit Sawing", 1, {"coin": 230, "planks": 25}, 12,
       {"yield_craft": 1.12}),
    _t("salted_stores", "Salted Stores", 1, {"coin": 240, "salt": 25}, 14,
       {"spoilage": 0.60}, blurb="What the granary saves, the cart can sell."),

    # --- Age of Craft -------------------------------------------------------
    _t("three_field", "Three-Field Rotation", 2, {"coin": 520, "wood": 60}, 20,
       {"yield_field": 1.25}, prereq="heavy_plough"),
    _t("horse_collar", "Horse Collar", 2, {"coin": 460, "iron": 20}, 18,
       {"yield_field": 1.05, "cart_speed": 6.0}),
    _t("watermill", "Watermill", 2, {"coin": 620, "stone": 70, "planks": 30}, 22,
       {"yield_craft": 1.18}),
    _t("guild_charter", "Guild Charter", 2, {"coin": 540, "cloth": 25}, 20,
       {"mood": 4.0, "research_speed": 1.30}),
    _t("drove_roads", "Drove Roads", 2, {"coin": 500, "stone": 60}, 18,
       {"cart_capacity": 40.0}, blurb="A cart is only as good as the road under it."),
    _t("letters_of_credit", "Letters of Credit", 2, {"coin": 720}, 24,
       {"interest": 0.00035, "tariff": 0.85},
       blurb="Coin that sits in a chest earns nothing; coin on a ledger earns."),
    _t("masonry", "Masonry", 2, {"coin": 680, "stone": 90}, 22,
       {"wall": 1.35, "storage": 200.0}),
    _t("crossbow", "Crossbow", 2, {"coin": 600, "iron": 25, "wood": 40}, 20,
       {"attack": 1.05}, unlocks=("crossbowman",)),

    # --- Age of the Castle --------------------------------------------------
    _t("blast_bellows", "Blast Bellows", 3, {"coin": 900, "iron": 45}, 26,
       {"yield_craft": 1.15}),
    _t("deep_shafts", "Deep Shafts", 3, {"coin": 1000, "planks": 60, "tools": 20}, 26,
       {"yield_mine": 1.30, "deposit_yield": 1.40},
       blurb="Timbered galleries reach the seam a surface working gives up on."),
    _t("crop_rotation", "Crop Rotation", 3, {"coin": 1100, "wood": 80}, 28,
       {"yield_field": 1.20}, prereq="three_field"),
    _t("ox_carts", "Ox Carts", 3, {"coin": 980, "planks": 60, "iron": 20}, 26,
       {"cart_capacity": 60.0, "cart_speed": 4.0}, prereq="drove_roads"),
    _t("murder_holes", "Murder Holes", 3, {"coin": 860, "stone": 90}, 24,
       {"defense": 1.25}, prereq="masonry"),
    _t("plate_armour", "Plate Armour", 3, {"coin": 1250, "iron": 70, "armour": 10}, 30,
       {"defense": 1.30}, unlocks=("knight",)),
    _t("counting_house", "Counting House", 3, {"coin": 1150, "planks": 40}, 26,
       {"tariff": 0.70, "interest": 0.00030}, prereq="letters_of_credit"),
    _t("burgage_plots", "Burgage Plots", 3, {"coin": 950, "planks": 70}, 24,
       {"housing": 1.25}, blurb="Narrow fronts, deep yards, twice the roofs."),

    # --- Age of the Crown ---------------------------------------------------
    _t("blast_furnace", "Blast Furnace", 4, {"coin": 2100, "stone": 180, "iron": 90}, 34,
       {"yield_craft": 1.30}, prereq="blast_bellows"),
    _t("trebuchet_frames", "Trebuchet Frames", 4, {"coin": 1900, "planks": 120,
                                                   "iron": 60}, 32,
       {"siege": 1.50}, unlocks=("trebuchet",)),
    _t("royal_charter", "Royal Charter", 4, {"coin": 2400, "silk": 20}, 34,
       {"tariff": 0.50, "mood": 5.0, "caravan_slots": 2.0}),
    _t("chivalry", "Chivalry", 4, {"coin": 2100, "armour": 25}, 32,
       {"attack": 1.30}, prereq="plate_armour"),
    _t("great_granaries", "Great Granaries", 4, {"coin": 1850, "stone": 220}, 30,
       {"spoilage": 0.55, "storage": 600.0}, prereq="salted_stores"),
]}

# --- the houses -------------------------------------------------------------
# A house is a hidden technology you are simply born knowing: its bonuses, and
# the one soldier nobody else can muster.
HOUSES: Dict[str, Tech] = {t.key: t for t in [
    _t("plough", "House of the Plough", 1, {}, 0,
       {"yield_field": 1.15, "housing": 1.10}, unlocks=("billman",), hidden=True,
       blurb="Farmers first. Deeper fields, fuller villages, and billmen who "
             "need no armourer."),
    _t("hansa", "The Hansa of Havnhold", 1, {}, 0,
       {"cart_capacity": 35.0, "tariff": 0.75, "interest": 0.00015},
       unlocks=("hanse_guard",), hidden=True,
       blurb="Merchants first. Bigger carts, lighter tolls, and a watch that "
             "pays for itself."),
    _t("ironhand", "House Ironhand", 1, {}, 0,
       {"yield_craft": 1.15, "recruit_cost": 0.90}, unlocks=("ironhand_serjeant",),
       hidden=True,
       blurb="Smiths first. Every workshop runs hotter and every soldier costs less."),
    _t("marcher", "The Marcher Lords", 1, {}, 0,
       {"wall": 1.25, "attack": 1.10, "recruit_cost": 0.85},
       unlocks=("border_horse",), hidden=True,
       blurb="Soldiers first. Thicker walls, cheaper musters, and horse that "
             "can be anywhere in three days."),
    _t("abbey", "Abbey of Saint Cuth", 1, {}, 0,
       {"mood": 7.0, "spoilage": 0.70, "research_speed": 1.30},
       unlocks=("abbey_guard",), hidden=True,
       blurb="Scholars first. A contented town, a full granary, and the "
             "quickest guildhall in the march."),
]}
TECHS.update(HOUSES)


@dataclass
class Progress:
    """What the house knows, and what it is in the middle of learning."""

    age: int = 1
    advancing: int = 0                 # days left on an age, 0 if not advancing
    researched: Set[str] = field(default_factory=set)
    researching: str = ""
    research_left: float = 0.0
    bonuses: Dict[str, float] = field(default_factory=dict)   # from your house

    # -- lookups -------------------------------------------------------------
    def mult(self, key: str) -> float:
        out = self.bonuses.get(key, 1.0) if key in MULTIPLIERS else 1.0
        for t in self.researched:
            out *= TECHS[t].effects.get(key, 1.0)
        return out

    def bonus(self, key: str) -> float:
        out = self.bonuses.get(key, 0.0) if key in ADDITIONS else 0.0
        for t in self.researched:
            out += TECHS[t].effects.get(key, 0.0)
        return out

    def unlocked_units(self) -> Set[str]:
        out: Set[str] = set()
        for t in self.researched:
            out.update(TECHS[t].unlocks)
        return out

    def knows(self, key: str) -> bool:
        return key in self.researched

    # -- availability --------------------------------------------------------
    def available(self) -> List[Tech]:
        out = []
        for t in TECHS.values():
            if t.hidden or t.key in self.researched or t.age > self.age:
                continue
            if t.prereq and t.prereq not in self.researched:
                continue
            out.append(t)
        return sorted(out, key=lambda t: (t.age, t.cost.get("coin", 0)))

    def age_name(self) -> str:
        return AGES[self.age].name

    def next_age(self) -> Optional[Age]:
        return AGES.get(self.age + 1)

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> dict:
        return {"age": self.age, "advancing": self.advancing,
                "researched": sorted(self.researched),
                "researching": self.researching,
                "research_left": self.research_left,
                "bonuses": dict(self.bonuses)}

    @classmethod
    def from_dict(cls, d: dict) -> "Progress":
        return cls(age=d["age"], advancing=d["advancing"],
                   researched=set(d["researched"]), researching=d["researching"],
                   research_left=d["research_left"], bonuses=dict(d.get("bonuses", {})))


#: A stand-in for code that does not care about technology (tests, previews).
NO_PROGRESS = Progress()
