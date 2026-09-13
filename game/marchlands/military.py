"""Soldiers, hosts and battles.

The recruiting loop is Stronghold's: coin and a *made* weapon buy a soldier,
and the soldier walks out of the labour pool to get him. An armoury is worth
more than a mine if you intend to fight, and nothing at all if you do not.

The fighting is Age of Empires' triangle, resolved in rounds rather than in
real time: spears break horse, horse rides down bows, bows cut up foot, and
none of it matters while a wall is standing -- which is what siege engines are
for.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .tech import NO_PROGRESS, Progress

FOOT = "foot"
RANGED = "ranged"
HORSE = "horse"
SIEGE = "siege"

GARRISON = "garrison"
MARCHING = "marching"
BESIEGING = "besieging"
RETURNING = "returning"


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str
    age: int
    coin: float
    equipment: Dict[str, float]
    attack: float
    defense: float
    hp: float
    unit_class: str
    speed: float                       # leagues per day on the march
    upkeep: float                      # coins per day
    counters: Dict[str, float] = field(default_factory=dict)
    siege_power: float = 0.0           # damage to walls per day
    needs_tech: str = ""
    blurb: str = ""

    @property
    def ranged(self) -> bool:
        return self.unit_class == RANGED


def _u(*args, **kwargs) -> UnitType:
    return UnitType(*args, **kwargs)


UNITS: Dict[str, UnitType] = {u.key: u for u in [
    _u("militia", "Levy Militia", 1, 16, {"spears": 1}, 4, 2, 12, FOOT, 18, 0.4,
       blurb="Farmhands with a spear. Cheap, and they show it."),
    _u("spearman", "Spearman", 1, 30, {"spears": 1}, 6, 5, 18, FOOT, 18, 0.8,
       counters={HORSE: 2.5}, blurb="A wall of points. Horse will not face it."),
    _u("archer", "Archer", 1, 36, {"bows": 1}, 8, 2, 12, RANGED, 20, 0.9,
       counters={FOOT: 1.5}, blurb="Worth three of himself on a battlement."),
    _u("man_at_arms", "Man-at-Arms", 2, 62, {"weapons": 1, "armour": 1},
       13, 10, 26, FOOT, 16, 1.6, counters={RANGED: 1.6},
       blurb="The line that holds when the levy runs."),
    _u("crossbowman", "Crossbowman", 2, 58, {"bows": 1, "armour": 1},
       12, 6, 18, RANGED, 18, 1.4, counters={FOOT: 1.5, HORSE: 1.3},
       needs_tech="crossbow", blurb="Punches plate. Slow to wind, quick to learn."),
    _u("knight", "Knight", 3, 115, {"weapons": 1, "armour": 2},
       17, 13, 34, HORSE, 30, 2.6, counters={RANGED: 2.0, SIEGE: 1.8},
       needs_tech="plate_armour", blurb="Fast, dear, and ruinous to an archer line."),
    _u("engineer", "Engineer", 3, 48, {"tools": 1}, 3, 3, 14, SIEGE, 18, 1.0,
       blurb="No engineers, no engines: rams and trebuchets need crews."),
    _u("ram", "Battering Ram", 3, 140, {"planks": 20, "iron": 4},
       4, 9, 65, SIEGE, 12, 2.0, siege_power=26,
       blurb="Walks a gate down while the towers shoot at it."),
    # --- one of these belongs to your house alone ---------------------------
    _u("billman", "Billman", 1, 48, {"weapons": 1}, 11, 7, 22, FOOT, 18, 1.2,
       counters={HORSE: 1.6, FOOT: 1.2}, needs_tech="plough",
       blurb="A hedging bill on a long shaft. No armourer required."),
    _u("hanse_guard", "Hanse Guard", 1, 44, {"bows": 1, "cloth": 1},
       10, 6, 17, RANGED, 20, 1.1, counters={FOOT: 1.4}, needs_tech="hansa",
       blurb="Paid watchmen who came up with the caravans."),
    _u("ironhand_serjeant", "Ironhand Serjeant", 2, 78, {"weapons": 1, "armour": 2},
       14, 15, 30, FOOT, 15, 1.9, counters={RANGED: 1.5}, needs_tech="ironhand",
       blurb="Walks through arrow fire because the arrows do not get through."),
    _u("border_horse", "Border Horse", 2, 72, {"spears": 1, "armour": 1},
       12, 8, 25, HORSE, 36, 1.8, counters={RANGED: 1.8, SIEGE: 1.6},
       needs_tech="marcher", blurb="Three days from anywhere on the march."),
    _u("abbey_guard", "Abbey Guard", 2, 60, {"weapons": 1, "armour": 1},
       9, 13, 27, FOOT, 16, 1.5, counters={RANGED: 1.4}, needs_tech="abbey",
       blurb="Holds a gate all day and asks for very little."),

    _u("trebuchet", "Trebuchet", 4, 320, {"planks": 35, "iron": 16},
       5, 4, 48, SIEGE, 10, 4.2, siege_power=80, needs_tech="trebuchet_frames",
       blurb="Breaks stone from beyond bowshot. Nothing else does."),
]}
ALL_UNITS = tuple(UNITS)


def unit(key: str) -> UnitType:
    try:
        return UNITS[key]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown unit {key!r}") from None


def resolve(prefix: str) -> str:
    p = prefix.strip().lower().replace(" ", "_").replace("-", "_")
    if p in UNITS:
        return p
    hits = [k for k in ALL_UNITS if k.startswith(p)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise KeyError(f"no soldier matches {prefix!r}")
    raise KeyError(f"{prefix!r} is ambiguous: {', '.join(hits)}")


def host_size(units: Dict[str, float]) -> int:
    return int(sum(units.values()))


def host_upkeep(units: Dict[str, float]) -> float:
    return sum(UNITS[k].upkeep * n for k, n in units.items())


def host_strength(units: Dict[str, float]) -> float:
    """A single number for display: what this host is worth in a fair fight."""
    return sum((UNITS[k].attack + UNITS[k].defense) * UNITS[k].hp * n / 20.0
               for k, n in units.items())


def host_speed(units: Dict[str, float]) -> float:
    live = [UNITS[k].speed for k, n in units.items() if n > 0]
    return min(live) if live else C.CARAVAN_BASE_SPEED


def describe(units: Dict[str, float]) -> str:
    bits = [f"{int(n)} {UNITS[k].name}" for k, n in sorted(units.items()) if n >= 1]
    return ", ".join(bits) if bits else "no one"


# ---------------------------------------------------------------- the battle
@dataclass
class Side:
    units: Dict[str, float]
    attack_mult: float = 1.0
    defense_mult: float = 1.0
    battlement: float = 0.0        # defence added by towers, defenders only
    morale: float = 1.0

    def alive(self) -> float:
        return sum(self.units.values())

    def class_share(self) -> Dict[str, float]:
        total = self.alive()
        out: Dict[str, float] = {}
        if total <= 0:
            return out
        for k, n in self.units.items():
            out[UNITS[k].unit_class] = out.get(UNITS[k].unit_class, 0.0) + n / total
        return out


@dataclass
class BattleResult:
    winner: str                       # 'attacker', 'defender' or 'stalemate'
    attacker_losses: Dict[str, float] = field(default_factory=dict)
    defender_losses: Dict[str, float] = field(default_factory=dict)
    wall_damage: float = 0.0
    rounds: int = 0
    log: List[str] = field(default_factory=list)


def _damage(side: Side, foe: Side, *, ranged_only: bool, cover: float) -> float:
    shares = foe.class_share()
    total = 0.0
    for k, n in side.units.items():
        if n <= 0:
            continue
        u = UNITS[k]
        if ranged_only and not u.ranged:
            continue
        mult = sum(share * u.counters.get(cls, 1.0) for cls, share in shares.items()) or 1.0
        total += n * u.attack * mult
    return total * side.attack_mult * side.morale * (1.0 - cover)


def _apply(side: Side, damage: float, rng: random.Random) -> Dict[str, float]:
    """Spread damage over a host in proportion to how much of it there is."""
    losses: Dict[str, float] = {}
    weight = {k: n * UNITS[k].hp for k, n in side.units.items() if n > 0}
    total_weight = sum(weight.values())
    if total_weight <= 0:
        return losses
    for k, w in weight.items():
        u = UNITS[k]
        share = damage * (w / total_weight)
        soak = (1.0 + (u.defense * side.defense_mult + side.battlement) / 9.0)
        killed = min(side.units[k], share / soak / u.hp * C.LETHALITY)
        killed *= 0.85 + 0.3 * rng.random()
        killed = min(side.units[k], killed)
        if killed > 0:
            side.units[k] -= killed
            losses[k] = losses.get(k, 0.0) + killed
    return losses


def siege_day(besieger: Side, defender: Side, wall_hp: float,
              rng: random.Random, place: str = "the walls",
              wall_max: float = 0.0
              ) -> Tuple[float, Dict[str, float], Dict[str, float], List[str]]:
    """One day of a siege: engines work on the stone, bowmen trade at a distance.

    Nobody storms a standing wall by accident. This is the slow part, and it is
    where a besieger's supply of patience runs out before his supply of men.
    """
    lines: List[str] = []
    siege = sum(UNITS[k].siege_power * n for k, n in besieger.units.items())
    siege *= besieger.attack_mult
    wall = wall_hp
    if siege > 0:
        hit = min(wall, siege * (0.8 + 0.4 * rng.random()))
        wall -= hit
        lines.append(f"engines work on {place}: {wall:.0f} of wall standing")
    else:
        lines.append(f"the host sits before {place} with nothing to break stone")
    # While the wall stands the garrison is barely exposed; as it comes down
    # they are shooting over rubble. This is most of what a wall is *for*.
    intact = min(1.0, wall / wall_max) if wall_max > 0 else (1.0 if wall > 0 else 0.0)
    cover = 0.55 + 0.42 * intact
    fire_d = _damage(defender, besieger, ranged_only=True, cover=0.0) * C.SIEGE_ATTRITION
    fire_a = _damage(besieger, defender, ranged_only=True, cover=cover) * C.SIEGE_ATTRITION
    lost_a = _apply(besieger, fire_d, rng)
    lost_d = _apply(defender, fire_a, rng)
    if lost_a or lost_d:
        lines.append(f"skirmishing: {describe({k: round(v) for k, v in lost_a.items()})}"
                     f" lost outside, {describe({k: round(v) for k, v in lost_d.items()})}"
                     f" lost within")
    return wall, lost_a, lost_d, lines


def fight(attacker: Side, defender: Side, *, wall_hp: float = 0.0,
          rng: Optional[random.Random] = None, max_rounds: int = 14,
          place: str = "the field") -> BattleResult:
    """Resolve a battle round by round. Walls change everything until they fall."""
    rng = rng or random.Random()
    res = BattleResult(winner="stalemate")
    start_att, start_def = attacker.alive(), defender.alive()
    if start_att <= 0:
        res.winner = "defender"
        return res
    if start_def <= 0 and wall_hp <= 0:
        res.winner = "attacker"
        return res
    wall = wall_hp

    for rnd in range(1, max_rounds + 1):
        res.rounds = rnd
        breached = wall <= 0
        if not breached:
            # Siege work first: engines chew the wall while the towers reply.
            siege = sum(UNITS[k].siege_power * n for k, n in attacker.units.items())
            siege *= attacker.attack_mult
            if siege > 0:
                hit = min(wall, siege * (0.8 + 0.4 * rng.random()))
                wall -= hit
                res.wall_damage += hit
                res.log.append(f"round {rnd}: engines batter {place} "
                               f"({wall:.0f} of wall left)")
            else:
                res.log.append(f"round {rnd}: the host has nothing to break stone with")
            dmg_a = _damage(attacker, defender, ranged_only=True, cover=0.55)
            dmg_d = _damage(defender, attacker, ranged_only=True, cover=0.0)
        else:
            dmg_a = _damage(attacker, defender, ranged_only=False, cover=0.0)
            dmg_d = _damage(defender, attacker, ranged_only=False, cover=0.0)

        lost_d = _apply(defender, dmg_a, rng)
        lost_a = _apply(attacker, dmg_d, rng)
        for store, losses in ((res.defender_losses, lost_d), (res.attacker_losses, lost_a)):
            for k, v in losses.items():
                store[k] = store.get(k, 0.0) + v
        if lost_a or lost_d:
            res.log.append(
                f"round {rnd}: {describe({k: round(v) for k, v in lost_a.items() if v >= 1}) }"
                f" lost storming, {describe({k: round(v) for k, v in lost_d.items() if v >= 1})}"
                f" lost holding")

        attacker.morale = max(0.25, attacker.alive() / max(start_att, 1e-9))
        defender.morale = max(0.25, defender.alive() / max(start_def, 1e-9))

        if defender.alive() <= start_def * 0.25 and wall <= 0:
            res.winner = "attacker"
            break
        if attacker.alive() <= start_att * 0.30:
            res.winner = "defender"
            break
        if wall > 0 and rnd >= max_rounds:
            res.winner = "defender"          # the walls held; the siege is off
            break
    else:
        res.winner = "attacker" if defender.alive() < attacker.alive() else "defender"

    res.log.append(f"the {res.winner} holds the ground at {place}")
    return res


# ------------------------------------------------------------------- armies
@dataclass
class Army:
    uid: int
    name: str
    owner: str                    # 'player' or a foreign town key
    units: Dict[str, float] = field(default_factory=dict)
    at: str = ""
    bound_for: str = ""
    days_left: float = 0.0
    state: str = GARRISON
    home: str = ""
    siege_days: int = 0
    log: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return host_size(self.units)

    @property
    def upkeep(self) -> float:
        return host_upkeep(self.units)

    @property
    def siege_power(self) -> float:
        return sum(UNITS[k].siege_power * n for k, n in self.units.items())

    def where(self) -> str:
        if self.state == MARCHING:
            return f"{self.days_left:.0f}d from {self.bound_for}"
        if self.state == BESIEGING:
            return f"besieging {self.at}"
        return self.at

    def note(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 30:
            del self.log[:-30]

    def prune(self) -> None:
        for k in list(self.units):
            if self.units[k] < 0.5:
                del self.units[k]

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("units", "log")}
        d["units"] = dict(self.units)
        d["log"] = list(self.log[-8:])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Army":
        units = dict(d.pop("units", {}))
        log = list(d.pop("log", []))
        a = cls(**d)
        a.units, a.log = units, log
        return a


def recruit_cost(key: str, count: int, progress: Progress = NO_PROGRESS
                 ) -> Tuple[float, Dict[str, float]]:
    u = unit(key)
    mult = progress.mult("recruit_cost")
    goods = {g: q * count for g, q in u.equipment.items()}
    return u.coin * count * mult, goods


def can_recruit(key: str, progress: Progress) -> Tuple[bool, str]:
    u = unit(key)
    if u.age > progress.age:
        return False, f"{u.name} belongs to the {['', 'first', 'second', 'third', 'fourth'][u.age]} age"
    if u.needs_tech and not progress.knows(u.needs_tech):
        from .tech import TECHS
        return False, f"{u.name} needs {TECHS[u.needs_tech].name}"
    return True, ""
