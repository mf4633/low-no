"""A settlement you own: land, labour, buildings, walls, and the people you feed.

Order of a day, from the settlement's point of view:
    staff the buildings -> produce -> feed the people -> pay and tax ->
    spoil and spill -> mend the walls -> take the mood -> let people come or go.

Two things here are load-bearing and easy to miss. Soldiers are drawn from the
same population that works the fields, so an army is paid for twice. And a
quarry or a mine works a *seam*: the hill under a settlement holds a finite
amount of stone and iron, and when it is gone the sheds stand idle for good.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import BUILDINGS, Building, building
from .goods import ALL_KEYS, COMFORT_GOODS, LUXURY_GOODS, RATION_GOODS, good
from .market import Market
from .military import UNITS, describe, host_size, host_strength, host_upkeep
from .tech import NO_PROGRESS, Progress


@dataclass
class BuildingInstance:
    uid: int
    key: str
    days_left: int = 0          # construction remaining
    enabled: bool = True
    staffed: int = 0            # workers actually present today
    throughput: float = 0.0     # 0..1, what it managed to run at today
    idle_reason: str = ""

    @property
    def spec(self) -> Building:
        return BUILDINGS[self.key]

    @property
    def complete(self) -> bool:
        return self.days_left <= 0

    def to_dict(self) -> dict:
        return {"uid": self.uid, "key": self.key, "days_left": self.days_left,
                "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "BuildingInstance":
        return cls(uid=d["uid"], key=d["key"], days_left=d["days_left"],
                   enabled=d.get("enabled", True))


@dataclass
class DayReport:
    """Everything that happened in one settlement on one day."""
    produced: Dict[str, float] = field(default_factory=dict)
    consumed: Dict[str, float] = field(default_factory=dict)
    eaten: Dict[str, float] = field(default_factory=dict)
    spoiled: Dict[str, float] = field(default_factory=dict)
    wages: float = 0.0
    upkeep: float = 0.0
    taxes: float = 0.0
    unpaid: bool = False
    hunger: float = 0.0         # share of the ration that went unserved
    variety: int = 0
    migration: float = 0.0
    repaired: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class Settlement:
    name: str
    terrain: Dict[str, int]
    market: Market
    population: float = 120.0
    popularity: float = C.POPULARITY_START
    ration_level: int = 2
    tax_level: int = 2
    buildings: List[BuildingInstance] = field(default_factory=list)
    units: Dict[str, float] = field(default_factory=dict)   # the garrison
    wall_hp: float = 0.0
    deposits: Dict[str, float] = field(default_factory=dict)
    besieged: bool = False
    next_uid: int = 1
    report: DayReport = field(default_factory=DayReport)

    # ------------------------------------------------------------------ land
    def slots_used(self, terrain: str) -> int:
        return sum(1 for b in self.buildings if b.spec.terrain == terrain)

    def slots_free(self, terrain: str) -> int:
        return max(0, self.terrain.get(terrain, 0) - self.slots_used(terrain))

    # --------------------------------------------------------------- effects
    def effect(self, name: str) -> float:
        return sum(b.spec.effects.get(name, 0.0)
                   for b in self.buildings if b.complete)

    def count(self, key: str) -> int:
        return sum(1 for b in self.buildings if b.key == key)

    def housing(self, mods: Progress = NO_PROGRESS) -> float:
        return (C.BASE_HOUSING + self.effect("housing")) * mods.mult("housing")

    def storage(self, mods: Progress = NO_PROGRESS) -> float:
        return C.BASE_STORAGE + self.effect("storage") + mods.bonus("storage")

    def wall_max(self, mods: Progress = NO_PROGRESS) -> float:
        return self.effect("wall") * mods.mult("wall")

    def defense(self, mods: Progress = NO_PROGRESS) -> float:
        works = self.effect("defense") * mods.mult("defense")
        return works + host_strength(self.units)

    @property
    def fear(self) -> float:
        return self.effect("fear")

    @property
    def caravan_slots(self) -> int:
        return int(self.effect("caravan_slots"))

    @property
    def tariff_relief(self) -> float:
        posts = self.effect("tariff_relief")
        return 1.0 - (1.0 - C.TRADING_POST_TARIFF_RELIEF) ** posts if posts else 0.0

    @property
    def spread(self) -> float:
        return max(0.03, C.SPREAD + self.effect("spread"))

    @property
    def soldiers(self) -> int:
        return host_size(self.units)

    @property
    def workforce(self) -> int:
        """Soldiers do not reap. Every man under arms is a man out of the fields."""
        return max(0, int(self.population * C.WORKING_FRACTION) - self.soldiers)

    @property
    def jobs_offered(self) -> int:
        return sum(b.spec.jobs for b in self.buildings if b.complete and b.enabled)

    @property
    def employed(self) -> int:
        return sum(b.staffed for b in self.buildings)

    def productivity(self, mods: Progress = NO_PROGRESS) -> float:
        if self.popularity < C.UNREST_THRESHOLD:
            return C.UNREST_PRODUCTIVITY
        base = C.PRODUCTIVITY_FLOOR + C.PRODUCTIVITY_SLOPE * self.popularity
        base += 0.035 * self.fear + mods.bonus("productivity")
        if self.besieged:
            base *= C.SIEGE_HUNGER
        return max(0.0, base)

    # ------------------------------------------------------------ build/raze
    def can_build(self, key: str, mods: Progress = NO_PROGRESS) -> Tuple[bool, str]:
        spec = building(key)
        if spec.age > mods.age:
            from .tech import AGES
            return False, f"{spec.name} waits on the {AGES[spec.age].name}"
        if key == "keep" and self.count("keep"):
            return False, f"{self.name} already has a keep"
        if self.slots_free(spec.terrain) <= 0:
            where = {"urban": "room inside", "rampart": "wall line left at"}.get(
                spec.terrain, f"free {spec.terrain} land at")
            return False, f"no {where} {self.name}"
        for k, qty in spec.build_cost.items():
            if k == "coin":
                continue
            if self.market.stock.get(k, 0.0) < qty:
                return False, (f"{self.name} needs {qty:g} {good(k).name} "
                               f"(has {self.market.stock.get(k, 0.0):.0f})")
        return True, ""

    def start_build(self, key: str) -> BuildingInstance:
        spec = building(key)
        for k, qty in spec.build_cost.items():
            if k != "coin":
                self.market.take(k, qty)
        inst = BuildingInstance(uid=self.next_uid, key=key, days_left=spec.build_days)
        self.next_uid += 1
        self.buildings.append(inst)
        return inst

    def demolish(self, uid: int) -> Optional[BuildingInstance]:
        for i, b in enumerate(self.buildings):
            if b.uid == uid:
                for k, qty in b.spec.build_cost.items():
                    if k != "coin" and b.complete:
                        self.market.add(k, qty * 0.4)
                if b.complete:
                    self.wall_hp = max(0.0, self.wall_hp - b.spec.effects.get("wall", 0.0))
                return self.buildings.pop(i)
        return None

    def find(self, uid: int) -> Optional[BuildingInstance]:
        return next((b for b in self.buildings if b.uid == uid), None)

    # ---------------------------------------------------------------- a day
    TARGET_SCALE = {"food": 0.45, "drink": 0.30, "raw": 0.55, "material": 0.45,
                    "finished": 0.20, "luxury": 0.06}

    def update_market_targets(self) -> None:
        """Your own market prices stock against your own town's appetite."""
        for k in ALL_KEYS:
            scale = self.TARGET_SCALE.get(good(k).category, 0.3)
            self.market.target[k] = max(25.0, scale * self.population)

    def tick(self, season: str, rng: random.Random,
             mods: Progress = NO_PROGRESS) -> DayReport:
        rep = DayReport()
        self.report = rep
        self.update_market_targets()
        self.market.spread = self.spread
        self._advance_construction()
        self._staff_buildings()
        self._produce(season, rep, mods)
        self._feed(rep)
        self._comforts(rep)
        self._spoil(rep, mods)
        self._mend_walls(rep, mods)
        rep.taxes = self._taxes()
        rep.wages, rep.upkeep = self._labour_bill()
        return rep

    def _advance_construction(self) -> None:
        for b in self.buildings:
            if not b.complete:
                b.days_left -= 1
                if b.complete:
                    self.wall_hp += b.spec.effects.get("wall", 0.0)

    def _staff_buildings(self) -> None:
        pool = self.workforce
        for b in self.buildings:
            b.staffed = 0
            b.throughput = 0.0
            b.idle_reason = ""
        for b in self.buildings:
            if not (b.complete and b.enabled):
                b.idle_reason = "building" if not b.complete else "closed"
                continue
            take = min(b.spec.jobs, pool)
            b.staffed = take
            pool -= take
            if take < b.spec.jobs:
                b.idle_reason = "short of hands"

    def _season_multiplier(self, spec: Building, season: str) -> float:
        if spec.season == "field":
            return C.FIELD_YIELD[season]
        if spec.season == "orchard":
            return C.ORCHARD_YIELD[season]
        return 1.0

    def _tech_multiplier(self, spec: Building, mods: Progress) -> float:
        if spec.draws:
            return mods.mult("yield_mine")
        if spec.season:
            return mods.mult("yield_field")
        if spec.category == "industry":
            return mods.mult("yield_craft")
        return 1.0

    def _produce(self, season: str, rep: DayReport, mods: Progress) -> None:
        prod = self.productivity(mods)
        for b in self.buildings:
            spec = b.spec
            if not (b.complete and b.enabled) or not (spec.inputs or spec.outputs):
                continue
            staff_ratio = (b.staffed / spec.jobs) if spec.jobs else 1.0
            scale = (staff_ratio * prod * self._season_multiplier(spec, season)
                     * self._tech_multiplier(spec, mods))
            if scale <= 0:
                if prod <= 0:
                    b.idle_reason = "unrest"
                elif spec.season:
                    b.idle_reason = "out of season"
                continue
            if spec.draws and self.deposits.get(spec.draws, 0.0) <= 0.0:
                b.idle_reason = "the seam is worked out"
                continue
            for k, need in spec.inputs.items():
                want = need * scale
                if want > 0:
                    have = self.market.stock.get(k, 0.0)
                    if have < want:
                        scale = min(scale, have / need if need else 0.0)
                        b.idle_reason = f"no {good(k).name}"
            if scale <= 1e-9:
                continue
            for k, need in spec.inputs.items():
                used = self.market.take(k, need * scale)
                rep.consumed[k] = rep.consumed.get(k, 0.0) + used
            for k, out in spec.outputs.items():
                made = out * scale
                if spec.draws == k:
                    left = self.deposits.get(k, 0.0)
                    made = min(made, left)
                    # Deep shafts do not add ore; they waste less of it.
                    self.deposits[k] = max(0.0, left - made / mods.mult("deposit_yield"))
                    if self.deposits[k] <= 0:
                        rep.notes.append(f"{self.name}: the {good(k).name.lower()} "
                                         f"seam is worked out")
                self.market.add(k, made)
                rep.produced[k] = rep.produced.get(k, 0.0) + made
            b.throughput = scale

    def _feed(self, rep: DayReport) -> None:
        per_head, _mood = C.RATION_LEVELS[self.ration_level]
        need = per_head * self.population
        if need <= 0:
            return
        # `need` counts rations, not units: a unit of cheese feeds more than a
        # unit of raw wheat, which is why the bread chain is worth its wages.
        pool = {k: self.market.stock.get(k, 0.0) for k in RATION_GOODS}
        on_hand = sum(pool[k] * good(k).nourish for k in pool)
        if on_hand <= 0:
            rep.hunger = 1.0
            return
        served = 0.0
        # Eat proportionally to what is on hand, so the perishable pile does not
        # sit there rotting while the bread runs out.
        for k, have in pool.items():
            if have <= 0:
                continue
            want_units = need * (have * good(k).nourish / on_hand) / good(k).nourish
            got = self.market.take(k, min(want_units, have))
            if got > 0:
                rep.eaten[k] = got
                served += got * good(k).nourish
        shortfall = need - served
        if shortfall > 1e-6:
            for k in RATION_GOODS:
                if shortfall <= 1e-6:
                    break
                got = self.market.take(k, shortfall / good(k).nourish)
                if got > 0:
                    rep.eaten[k] = rep.eaten.get(k, 0.0) + got
                    served += got * good(k).nourish
                    shortfall -= got * good(k).nourish
        rep.hunger = max(0.0, 1.0 - served / need)
        rep.variety = sum(1 for k, v in rep.eaten.items()
                          if v * good(k).nourish > need * 0.08)

    def _comforts(self, rep: DayReport) -> None:
        self._comfort_score = 0.0
        for k in COMFORT_GOODS:
            want = C.COMFORT_RATE * self.population
            got = self.market.take(k, want)
            if got > 0:
                rep.consumed[k] = rep.consumed.get(k, 0.0) + got
                self._comfort_score += (got / want) if want else 0.0
        self._luxury_score = 0.0
        for k in LUXURY_GOODS:
            want = C.LUXURY_RATE * self.population
            got = self.market.take(k, want)
            if got > 0:
                rep.consumed[k] = rep.consumed.get(k, 0.0) + got
                self._luxury_score += (got / want) if want else 0.0

    def _spoil(self, rep: DayReport, mods: Progress) -> None:
        preserve = (1.0 - min(0.75, self.effect("preserve"))) * mods.mult("spoilage")
        for k in ALL_KEYS:
            rate = good(k).spoilage * preserve
            if rate <= 0:
                continue
            lost = self.market.stock[k] * rate
            if lost > 1e-9:
                self.market.stock[k] -= lost
                rep.spoiled[k] = lost
        cap = self.storage(mods)
        over = self.market.total_units() - cap
        if over > 0:
            total = self.market.total_units()
            for k in ALL_KEYS:
                share = self.market.stock[k] / total if total else 0.0
                lost = over * share * C.SPILL_RATE
                self.market.stock[k] = max(0.0, self.market.stock[k] - lost)
                if lost > 1e-6:
                    rep.spoiled[k] = rep.spoiled.get(k, 0.0) + lost
            rep.notes.append(f"{self.name}: stores overflowing, {over:.0f} units past capacity")

    def _mend_walls(self, rep: DayReport, mods: Progress) -> None:
        top = self.wall_max(mods)
        if self.wall_hp >= top or self.besieged:
            self.wall_hp = min(self.wall_hp, top)
            return
        want = min(top - self.wall_hp, top * 0.03)
        stone = self.market.take("stone", want / 9.0)
        if stone > 0:
            self.wall_hp = min(top, self.wall_hp + stone * 9.0)
            rep.repaired = stone * 9.0

    def _taxes(self) -> float:
        rate, _mood = C.TAX_LEVELS[self.tax_level]
        return rate * self.population

    def _labour_bill(self) -> Tuple[float, float]:
        wages = C.WAGE * self.employed
        upkeep = sum(b.spec.upkeep for b in self.buildings if b.complete)
        upkeep += host_upkeep(self.units)
        return wages, upkeep

    # ----------------------------------------------------------------- mood
    def mood_factors(self, mods: Progress = NO_PROGRESS) -> List[Tuple[str, float]]:
        rep = self.report
        out: List[Tuple[str, float]] = []
        _, ration_mood = C.RATION_LEVELS[self.ration_level]
        out.append(("rations", ration_mood))
        if rep.hunger > 0.01:
            out.append(("hunger", -40.0 * rep.hunger))
        if rep.variety > 1:
            out.append(("variety", C.FOOD_VARIETY_BONUS * (rep.variety - 1)))
        _, tax_mood = C.TAX_LEVELS[self.tax_level]
        out.append(("taxes", tax_mood))
        buildings_mood = 0.0
        for b in self.buildings:
            if not b.complete:
                continue
            m = b.spec.effects.get("mood", 0.0)
            if m and b.key == "inn" and b.throughput <= 0:
                continue  # a dry inn cheers nobody
            buildings_mood += m
        buildings_mood += mods.bonus("mood")
        if buildings_mood:
            out.append(("buildings", buildings_mood))
        if self.fear:
            out.append(("fear", -2.6 * self.fear))
        comfort = getattr(self, "_comfort_score", 0.0)
        if comfort:
            out.append(("comforts", C.COMFORT_BONUS * comfort))
        luxury = getattr(self, "_luxury_score", 0.0)
        if luxury:
            out.append(("luxuries", C.LUXURY_BONUS * luxury))
        roofs = self.housing(mods)
        if roofs < self.population:
            crowd = min(2.0, (self.population - roofs) / max(roofs, 1.0))
            out.append(("crowding", -C.CROWDING_PENALTY * (0.4 + crowd)))
        if rep.unpaid:
            out.append(("unpaid wages", -C.UNPAID_WAGE_PENALTY))
        if self.besieged:
            out.append(("under siege", -8.0))
        jobless = self.workforce - self.employed
        if self.workforce and jobless / self.workforce > 0.35:
            out.append(("idle hands", -6.0))
        return out

    def update_mood(self, mods: Progress = NO_PROGRESS) -> None:
        target = 50.0 + sum(v for _, v in self.mood_factors(mods))
        target = max(0.0, min(100.0, target))
        self.popularity += C.POPULARITY_INERTIA * (target - self.popularity)
        self.popularity = max(0.0, min(100.0, self.popularity))

    def migrate(self, rng: random.Random, mods: Progress = NO_PROGRESS) -> float:
        pull = (self.popularity - 50.0) / 50.0
        if pull > 0:
            headroom = max(0.0, self.housing(mods) - self.population)
            move = headroom * C.MIGRATION_RATE * pull * 4.0
        else:
            move = self.population * C.MIGRATION_RATE * pull * 2.0
        move *= 0.7 + 0.6 * rng.random()
        self.population = max(0.0, self.population + move)
        self.report.migration = move
        return move

    # --------------------------------------------------------------- display
    def net_worth(self) -> float:
        goods_value = self.market.inventory_value()
        bricks = sum(b.spec.build_cost.get("coin", 0.0) * (0.6 if b.complete else 0.3)
                     for b in self.buildings)
        troops = sum(UNITS[k].coin * n * 0.5 for k, n in self.units.items())
        return goods_value + bricks + troops

    def garrison_line(self) -> str:
        return describe(self.units)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "terrain": dict(self.terrain),
            "market": self.market.to_dict(), "population": self.population,
            "popularity": self.popularity, "ration_level": self.ration_level,
            "tax_level": self.tax_level, "units": dict(self.units),
            "wall_hp": self.wall_hp, "deposits": dict(self.deposits),
            "besieged": self.besieged, "next_uid": self.next_uid,
            "buildings": [b.to_dict() for b in self.buildings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Settlement":
        s = cls(name=d["name"], terrain=dict(d["terrain"]),
                market=Market.from_dict(d["market"]),
                population=d["population"], popularity=d["popularity"],
                ration_level=d["ration_level"], tax_level=d["tax_level"],
                units=dict(d.get("units", {})), wall_hp=d.get("wall_hp", 0.0),
                deposits=dict(d.get("deposits", {})),
                besieged=d.get("besieged", False), next_uid=d.get("next_uid", 1))
        s.buildings = [BuildingInstance.from_dict(b) for b in d["buildings"]]
        return s
