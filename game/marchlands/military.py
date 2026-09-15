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
import zlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import config as C
from .castle import SiegeState, Works, approach
from .tech import NO_PROGRESS, Progress

FOOT = "foot"
RANGED = "ranged"
HORSE = "horse"
SIEGE = "siege"

GARRISON = "garrison"
MARCHING = "marching"
BESIEGING = "besieging"
RETURNING = "returning"
RAIDING = "raiding"


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
    _u("friar", "Friar", 3, 54, {"cloth": 1, "bread": 4}, 2, 4, 15, SIEGE, 18, 1.1,
       needs_tech="preaching",
       blurb="Talks men off a wall. Slowly, and not to men who have a "
             "cathedral of their own."),
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


# Two spearmen are not "2 Spearman". The rule covers every name in UNITS:
# -man goes to -men wherever it falls, a militia and a troop of horse are the
# same word however many of them there are, and everything else takes an s.
_SAME = ("Militia", "Horse")


def plural(name: str) -> str:
    if name.endswith(_SAME):
        return name
    if name.endswith("man"):
        return name[:-3] + "men"
    if "Man-at-Arms" in name:
        return name.replace("Man-at-Arms", "Men-at-Arms")
    return name + "s"


def describe(units: Dict[str, float]) -> str:
    bits = [f"{int(n)} {UNITS[k].name if int(n) == 1 else plural(UNITS[k].name)}"
            for k, n in sorted(units.items()) if n >= 1]
    return ", ".join(bits) if bits else "no one"


# ---------------------------------------------------------------- the battle
@dataclass
class Side:
    units: Dict[str, float]
    attack_mult: float = 1.0
    defense_mult: float = 1.0
    battlement: float = 0.0        # defence added by towers, defenders only
    morale: float = 1.0
    #: What each *kind* of soldier is worth here today -- see `Field`. Kept
    #: apart from `attack_mult` because that is one number for the whole
    #: host, and the whole point of ground is that it is not the same number
    #: for a knight and for a spearman.
    class_mult: Dict[str, float] = field(default_factory=dict)

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


def matchup(mine: Dict[str, float], theirs: Dict[str, float]) -> List[dict]:
    """Which of yours eats which of theirs, and by how much.

    The counters have been in the rules since the first battle -- a spearman
    is worth two and a half of himself against horse -- and the game has never
    once said so. A counter system nobody can see is a dice roll with extra
    arithmetic: you cannot bring spears to a cavalry fight if nothing ever
    told you spears beat cavalry.

    So this is the same sum `_damage` does, kept apart and returned as facts
    rather than a number: for each kind you have, what it is worth against
    the enemy in front of it and which part of that enemy it is worth it
    against. Nothing here decides anything; the battle still runs on
    `_damage`. This is that calculation, said out loud.
    """
    foe = Side(dict(theirs))
    shares = foe.class_share()
    out: List[dict] = []
    for key, n in sorted(mine.items()):
        if n < 1 or key not in UNITS:
            continue
        u = UNITS[key]
        mult = sum(share * u.counters.get(cls, 1.0)
                   for cls, share in shares.items()) or 1.0
        against = sorted(
            ((cls, u.counters[cls]) for cls in u.counters if shares.get(cls, 0) > 0),
            key=lambda kv: -kv[1])
        out.append({
            "key": key, "name": u.name, "count": int(n), "class": u.unit_class,
            "worth": round(mult, 2),
            "against": [{"class": c, "times": v} for c, v in against],
        })
    out.sort(key=lambda d: -d["worth"])
    return out


def counter_note(mine: Dict[str, float], theirs: Dict[str, float]) -> str:
    """One line about the matchup, for a player who will not read a table."""
    ours = matchup(mine, theirs)
    rows = [r for r in ours if r["against"]]
    if not rows:
        # No advantage of yours is worth saying. What has the advantage over
        # you is worth saying very much, and is the same sum the other way
        # round -- a warning being more use than a shrug.
        back = [r for r in matchup(theirs, mine) if r["against"]]
        if not back:
            return "neither host has the better of the other; it is a straight fight"
        them = back[0]
        return (f"nothing of yours has the better of them, and their "
                f"{plural(them['name']).lower()} are worth "
                f"{them['worth']:.2f} against yours")
    best = rows[0]
    worst = min(ours, key=lambda r: r["worth"])
    said = (f"your {plural(best['name']).lower()} are worth "
            f"{best['worth']:.2f} of themselves against that host")
    if worst["worth"] < 0.999:
        said += f", your {plural(worst['name']).lower()} rather less"
    return said


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
        mult *= side.class_mult.get(u.unit_class, 1.0)
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
              wall_max: float = 0.0, works: Optional["Works"] = None,
              state: Optional["SiegeState"] = None, have_pitch: bool = True,
              faith: float = 0.0
              ) -> Tuple[float, Dict[str, float], Dict[str, float], List[str]]:
    """One day of a siege: engines work on the stone, bowmen trade at a distance.

    Nobody storms a standing wall by accident. This is the slow part, and it is
    where a besieger's supply of patience runs out before his supply of men.
    """
    lines: List[str] = []
    siege = sum(UNITS[k].siege_power * n for k, n in besieger.units.items())
    siege *= besieger.attack_mult
    wall = wall_hp
    att_mult = def_mult = 1.0
    burst = 0.0
    if state is not None:
        # The besieger has a plan, and the plan meets whatever was dug for it.
        engineers = sum(n for k, n in besieger.units.items() if k == "engineer")
        ap = approach(state.plan, works or Works(), state, siege_power=siege,
                      engineers=engineers, wall=wall, wall_max=wall_max,
                      have_pitch=have_pitch, rng=rng)
        hit = min(wall, ap.wall_damage)
        wall -= hit
        att_mult, def_mult, burst = ap.attacker_mult, ap.defender_mult, ap.burst
        lines.extend(f"{ln} at {place}" if i == 0 else ln
                     for i, ln in enumerate(ap.lines))
        if hit > 0:
            lines.append(f"{wall:.0f} of wall standing")
    elif siege > 0:
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
    fire_d *= att_mult
    fire_a *= def_mult
    if burst > 0:
        # Oil and pitch do not trade fire with anybody: they simply kill.
        for k in list(besieger.units):
            besieger.units[k] *= max(0.0, 1.0 - burst)
    lost_a = _apply(besieger, fire_d, rng)
    lost_d = _apply(defender, fire_a, rng)
    _won, preach = convert(besieger, defender, faith=faith, rng=rng)
    lines.extend(preach)
    if lost_a or lost_d:
        lines.append(f"skirmishing: {describe({k: round(v) for k, v in lost_a.items()})}"
                     f" lost outside, {describe({k: round(v) for k, v in lost_d.items()})}"
                     f" lost within")
    return wall, lost_a, lost_d, lines


def convert(preachers: Side, flock: Side, *, faith: float,
            rng: random.Random) -> Tuple[Dict[str, float], List[str]]:
    """Friars talk men off a wall and onto your side.

    Age of Empires' monks, which are the strangest and best thing in it: a
    unit whose attack is that the enemy stops being the enemy. The answer is
    the one the period actually used -- a man with a church of his own is a
    great deal harder to preach at, so a defender's *faith coverage* is what
    blunts this, which is the same number his ale and his chapels set.
    """
    friars = preachers.units.get("friar", 0.0)
    lines: List[str] = []
    if friars < 1 or flock.alive() <= 0:
        return {}, lines
    swayed = friars * C.CONVERT_PER_FRIAR * max(0.0, 1.0 - faith)
    swayed *= 0.7 + 0.6 * rng.random()
    swayed = min(swayed, flock.alive() * C.CONVERT_CEILING)
    if swayed < 1:
        return {}, lines
    won: Dict[str, float] = {}
    total = flock.alive()
    for k, n in list(flock.units.items()):
        share = swayed * (n / total)
        share = min(share, n)
        if share <= 0:
            continue
        flock.units[k] = n - share
        preachers.units[k] = preachers.units.get(k, 0.0) + share
        won[k] = share
    if won:
        lines.append(f"the friars bring {describe({k: round(v) for k, v in won.items()})}"
                     f" over the wall to your side")
    return won, lines


def raid_day(raiders: Side, garrison: Side, *, out_of_doors: float,
             rng: random.Random) -> Tuple[float, float, Dict[str, float], List[str]]:
    """One day of a host working the countryside instead of the walls.

    A raid is the other half of medieval war and the half games usually leave
    out: you do not have to take a castle to beat the man in it, you have to
    take his harvest. The walls are irrelevant -- everything that matters is
    standing outside them -- so the only answer is to come out, which is
    exactly what the raider wants if he is the stronger.

    Returns how much of the country was worked over (0..1), how hard the
    garrison was hurt if it sortied, what the raiders lost, and the story.
    """
    lines: List[str] = []
    horse = sum(n for k, n in raiders.units.items() if UNITS[k].unit_class == HORSE)
    strength = raiders.alive() + 1.5 * horse      # horse burn more in a day
    # Hands in the fields cannot be burned faster than there are riders to do
    # it, and a big country takes longer to ruin than a small one.
    worked = min(1.0, strength / max(60.0, out_of_doors))
    lines.append(f"the country is burning: {worked * 100:.0f}% of it worked over")

    losses: Dict[str, float] = {}
    # A garrison that is clearly stronger comes out; one that is not, watches.
    if garrison.alive() > raiders.alive() * 1.25:
        hurt = _damage(garrison, raiders, ranged_only=False, cover=0.0) * C.RAID_SORTIE
        losses = _apply(raiders, hurt, rng)
        back = _damage(raiders, garrison, ranged_only=False, cover=0.0) * C.RAID_SORTIE
        _apply(garrison, back, rng)
        lines.append("the garrison comes out and the raiders are caught at it")
    return worked, 0.0, losses, lines


# ------------------------------------------------------------ the order
#: How a host is told to fight, which is the honest version of "command
#: massive tactical battles" in a game that is not real time.
#:
#: The thing worth taking from a real-time battle is not the clicking. It is
#: that you arrived having decided something -- where the horse would go,
#: whether to hold the line or break it -- and then watched the decision be
#: right or wrong. A day-ticked game can offer exactly that, and it costs no
#: new simulation: every one of these multiplies dials `fight` already reads,
#: and every one of them has a cost as well as a gain, because an order with
#: no downside is not a decision.
LINE = "line"
FLANK = "flank"
RESERVE = "reserve"
STORM = "storm"
HOLD = "hold"


@dataclass(frozen=True)
class Order:
    key: str
    name: str
    blurb: str
    attack: float = 1.0       # what your blows are worth
    defense: float = 1.0      # and what theirs are worth against you
    morale: float = 1.0       # how long your men stand
    #: What the order wants in the host to be worth anything, and how much
    #: better it gets when it has it.
    wants: str = ""
    bonus: float = 1.0
    rounds: int = 14


ORDERS: Dict[str, Order] = {o.key: o for o in [
    Order(LINE, "form the line",
          "Shields together, nobody clever. The order you give when you do "
          "not know what is in front of you.",
          attack=1.0, defense=1.0, morale=1.0),
    Order(FLANK, "send the horse wide",
          "The horse goes round. It wins the battle or it arrives late and "
          "you fought the middle without them.",
          attack=1.06, defense=0.95, morale=1.0, wants=HORSE, bonus=1.08),
    Order(RESERVE, "keep a third back",
          "Two ranks fight and one waits. You hit softer and you break much "
          "later, which is how an outnumbered host lives to be reinforced.",
          attack=0.95, defense=1.05, morale=1.15, rounds=18),
    Order(STORM, "straight at them",
          "Everything forward at once. Short, expensive, and the only order "
          "that ends a fight before their archers have spent their arrows.",
          attack=1.08, defense=0.93, morale=0.96, rounds=8),
    Order(HOLD, "stand and shoot",
          "Hold the ground and let them come onto you. Worth most with bows "
          "in the host and nothing at all without them.",
          attack=0.96, defense=1.06, morale=1.05, wants=RANGED, bonus=1.08,
          rounds=18),
]}

#: Why these numbers are small. The combat model is a knife edge: at even
#: strength the attacker wins one time in sixty, at ten per cent over he wins
#: every time, and the whole transition happens inside that band. An order
#: worth a quarter therefore did not tilt battles, it decided them -- "form
#: the line" won two per cent of the fights that "send the horse wide" won
#: ninety-five per cent of. At this size an order is the difference in a
#: close battle and nothing at all in a rout, which is what an order should
#: be.

# ------------------------------------------------- the ground and the sky
#
# Until this, a battle was arithmetic with a place name stapled on: `fight`
# took a `place` and used it only to write the log, and the word "season"
# appeared nowhere in this file. A January battle in a fen came out exactly
# like a June one on a dry plain, which is a strange thing in a game whose
# whole map is country and whose whole calendar is seasons.
#
# What ground and weather do here is what they did: they change what each
# *kind* of soldier is worth, not how big the host is. That is why they
# multiply per unit class rather than the host's one attack dial -- a fen is
# a catastrophe for a knight and an inconvenience for a spearman, and a
# single number cannot say that.
#
# The sizes are small for the same reason the orders' are: this combat model
# is a knife edge (see the note above), so anything worth a quarter does not
# tilt a battle, it decides one. These are worth about what an order is.

OPEN, CLOSE, BROKEN, HEAVY = "open", "close", "broken", "heavy"


@dataclass(frozen=True)
class Going:
    """What the ground underfoot is like."""
    key: str
    name: str
    note: str
    mult: Dict[str, float] = field(default_factory=dict)


GOING: Dict[str, Going] = {g.key: g for g in [
    Going(OPEN, "open field",
          "Room to ride and a clear shot the length of it.",
          {HORSE: 1.06, RANGED: 1.02}),
    Going(CLOSE, "close country",
          "Wood and hedge. Nobody sees far, nobody charges, and a line that "
          "goes into it comes out of it in pieces.",
          {HORSE: 0.90, RANGED: 0.95, FOOT: 1.02}),
    Going(BROKEN, "broken ground",
          "Slope and scree. Hard ground to hold a line on and harder ground "
          "to ride one down on.",
          {HORSE: 0.93, FOOT: 1.03, SIEGE: 0.95}),
    Going(HEAVY, "heavy going",
          "Fen. It takes a horse to the hock and a wagon to the axle, and "
          "everything that happens on it happens slowly.",
          {HORSE: 0.88, SIEGE: 0.91, FOOT: 1.02}),
]}

FAIR, RAIN, MUD, FROST, HEAT = "fair", "rain", "mud", "frost", "heat"


@dataclass(frozen=True)
class Weather:
    key: str
    name: str
    note: str
    mult: Dict[str, float] = field(default_factory=dict)
    #: A hard frost makes a fen into a road. This is the one piece of weather
    #: that changes what the ground *is* rather than what it is like, and it
    #: is the reason the calendar is a weapon: the fen town nobody can take
    #: in April can be ridden into in January.
    firms: bool = False


WEATHER: Dict[str, Weather] = {w.key: w for w in [
    Weather(FAIR, "a fair day", "Nothing to blame but each other.", {}),
    Weather(RAIN, "rain", "Wet strings shoot short and shoot badly.",
            {RANGED: 0.91}),
    Weather(MUD, "mud", "A charge that arrives at a walk is not a charge.",
            {HORSE: 0.93, SIEGE: 0.90}),
    Weather(FROST, "hard frost", "The ground rings. Everything moves, and "
            "nobody who stands still all day is much use by evening.",
            {FOOT: 0.98, RANGED: 0.97}, firms=True),
    Weather(HEAT, "heat", "Men in armour cook in it.",
            {FOOT: 0.96, HORSE: 0.97}),
]}

#: What the sky is likely to be doing, by season. Weighted rather than
#: uniform, because a game where January is as often fair as February is
#: sleet is a game where the calendar tells you nothing.
SKY: Dict[str, List[Tuple[str, float]]] = {
    "spring": [(FAIR, 0.42), (RAIN, 0.31), (MUD, 0.21), (FROST, 0.06)],
    "summer": [(FAIR, 0.58), (HEAT, 0.24), (RAIN, 0.18)],
    "autumn": [(FAIR, 0.34), (RAIN, 0.33), (MUD, 0.28), (FROST, 0.05)],
    "winter": [(FROST, 0.36), (MUD, 0.30), (RAIN, 0.24), (FAIR, 0.10)],
}


@dataclass(frozen=True)
class Field:
    """Where a battle is fought and what the sky is doing while it is.

    Both halves are knowable before you commit -- see `field_note`. A player
    who can be told "heavy going, and rain" and cannot act on it has been
    given flavour text; the point is that he can wait for the frost, or
    fight somewhere else, or bring different men.
    """
    going: str = OPEN
    weather: str = FAIR
    place: str = "the field"

    @property
    def ground(self) -> Going:
        return GOING.get(self.going, GOING[OPEN])

    @property
    def sky(self) -> Weather:
        return WEATHER.get(self.weather, WEATHER[FAIR])

    def mult(self) -> Dict[str, float]:
        """One dial per kind of soldier, ground and sky together."""
        out: Dict[str, float] = {}
        sky = self.sky
        # Frost firms the ground: a frozen fen is not heavy going, it is a
        # road. Applied by dropping the ground's own dials rather than by
        # adding a counter-multiplier, so a hard winter does not make a fen
        # *better* than open country -- only ordinary.
        if not (sky.firms and self.going == HEAVY):
            for cls, v in self.ground.mult.items():
                out[cls] = out.get(cls, 1.0) * v
        for cls, v in sky.mult.items():
            out[cls] = out.get(cls, 1.0) * v
        return out

    def words(self) -> str:
        if self.sky.firms and self.going == HEAVY:
            return f"{self.ground.name}, frozen hard"
        if self.weather == FAIR:
            return self.ground.name
        return f"{self.ground.name}, {self.sky.name}"


def going_of(ground: Dict[str, int], key: str = "") -> str:
    """What the country round a place is like to fight over.

    Read off the same slots the cartographer laid down, so the fen town the
    map drew is the fen you have to fight in. A place with no ground recorded
    -- the hand-built scenarios predate this -- gets one off its own name, so
    that every map has country rather than one having it and one not.
    """
    if not ground:
        pick = zlib.crc32(key.encode()) % 100 if key else 0
        return (HEAVY if pick < 12 else CLOSE if pick < 38
                else BROKEN if pick < 62 else OPEN)
    marsh = ground.get("marsh", 0)
    wood = ground.get("forest", 0)
    hills = ground.get("hills", 0)
    open_land = ground.get("fertile", 0)
    # Marsh first and on a low bar: a fen does not have to be most of the
    # country to be the part of it a battle gets fought in.
    if marsh >= 4 and marsh * 2 >= max(wood, hills, open_land):
        return HEAVY
    best = max((wood, CLOSE), (hills, BROKEN), (open_land, OPEN),
               key=lambda p: p[0])
    return best[1]


def sky_on(season: str, day: int, seed: int = 0) -> str:
    """The weather, drawn once per day and the same for everybody on it.

    Seeded off the day rather than rolled from the world's RNG, because two
    people asking what the sky is doing must get the same answer -- the
    panel that tells you before you commit and the battle that happens
    afterwards are two such askers, and a weather that re-rolled between
    them would be a lie rather than a forecast.
    """
    odds = SKY.get(season, SKY["spring"])
    r = random.Random(zlib.crc32(f"sky{seed}:{day}".encode())).random()
    at = 0.0
    for key, share in odds:
        at += share
        if r < at:
            return key
    return odds[-1][0]


def season_odds(season: str) -> List[Tuple[str, float]]:
    """What this season tends to bring, commonest first.

    Shown instead of a forecast, and the distinction matters. Nobody in 1247
    knows what next Tuesday is doing, and a game that told you would turn
    "wait for the frost" from a judgement into a lookup. What a man does
    know is his own calendar: that January is frost more often than not, and
    that waiting for it is a plan rather than a gamble.
    """
    return sorted(SKY.get(season, SKY["spring"]), key=lambda p: -p[1])


# ------------------------------------------------------------ the sortie
#
# What a sortie is actually risking, which for a long time was nothing.
#
# It used to meet a fixed sixteen per cent of the besieging host -- the guard
# set over the engines -- whatever the defender did, so a garrison of any
# size walked out, beat a detachment it outnumbered, burnt the rams and went
# back in. Its own docstring called it "deliberately a gamble rather than a
# trick", and measured over twenty-four seeds it won a hundred times out of a
# hundred. That is a button, not a decision.
#
# The thing a real sortie turned on is whether the camp was caught. Get out
# of the gate unseen and you are among the engines with only their guard to
# beat; be seen forming up and the army turns out and you are fighting it in
# the open with no wall at your back. So surprise is the gamble, and -- the
# part that makes it a decision rather than a dice roll -- it is bought and
# sold with things the player chooses.
#
# Above all with how many men he sends, which is meant to cut both ways: a
# small party slips out and may not be enough to do the work, a large one
# does the work and is seen forming.
#
# Meant to, and only half demonstrated. Measured over twenty-four seeds
# (the table is in tests/test_siege.py) the rework did the thing it had to
# do -- the sortie tops out at three wins in four instead of four in four,
# going late is no better than doing nothing, and marching everybody out
# late is worse than either. What it has not shown is the size curve: a
# third of the garrison and four fifths of it land in the same place, and a
# half dips below both, which at that sample is inside the noise. So the
# timing is a decision and the size is not yet provably one. It is written
# down here rather than tuned toward, because a constant picked to make a
# table agree with a comment is fitted to the seeds and not designed.

#: What turns out to meet you, as a share of his host that is not at the
#: works: caught unawares, and roused.
#: Caught, only the watch itself is on its feet -- which is the whole
#: meaning of the word, and it has to be small enough that a party small
#: enough to slip out can actually beat it. At sixteen per cent it was not:
#: a third of the garrison met more men than it had and lost.
SORTIE_QUIET = 0.07
SORTIE_ROUSED = 0.62

#: Where surprise starts, before anything either side has done.
SORTIE_BASE = 0.58

#: What being among them before they have formed is worth in the fight, and
#: what it does to men woken up to find the gate open.
#:
#: Without this the trade the mechanic is built on did not exist. A small
#: party got out unseen and was still too weak to beat the guard over the
#: engines, so sending a third of the garrison won four times in a hundred
#: and sending most of it won seventy-five -- which is not a choice between
#: stealth and strength, it is one good answer and several bad ones. The
#: surprise has to be worth something in the fighting, not only in who
#: turns out to do it.
SORTIE_CAUGHT_ATTACK = 1.55
SORTIE_CAUGHT_MORALE = 0.80

#: The share of the garrison you can send before the forming-up is visible
#: from the camp, and what each point past it costs.
SORTIE_SEEN = 0.35
SORTIE_SEEN_COST = 0.85

#: A camp that has sat a long time keeps a worse watch, up to this much.
SORTIE_SLACK = 0.16
SORTIE_SLACK_DAYS = 120.0

#: And a camp that has been sortied against once keeps a much better one.
SORTIE_WARNED = 0.26


@dataclass(frozen=True)
class Sortie:
    """The odds of getting out of the gate unseen, and what is behind them."""
    surprise: float
    quiet: float          # share of his loose men met if the camp is caught
    roused: float         # ...and if it is not
    helps: List[str] = field(default_factory=list)
    hurts: List[str] = field(default_factory=list)

    @property
    def words(self) -> str:
        if self.surprise >= 0.72:
            return "the camp is drowsy"
        if self.surprise >= 0.5:
            return "you might get out unseen"
        if self.surprise >= 0.28:
            return "they are watching the gate"
        return "they are waiting for it"


def sortie_odds(share: float, weather: str = FAIR, siege_days: int = 0,
                tries: int = 0) -> Sortie:
    """What a sortie would risk, before it is ordered.

    Every term is something the player can see and most are things he
    chooses, because odds he cannot read are a dice roll with extra steps.
    """
    helps: List[str] = []
    hurts: List[str] = []
    p = SORTIE_BASE

    # Weather. A sentry in sleet is not looking at the gate, and this is the
    # second place the sky decides something -- see Field.
    wet = {RAIN: 0.13, MUD: 0.11, FROST: 0.08, HEAT: 0.04}.get(weather, 0.0)
    if wet:
        p += wet
        helps.append(f"{WEATHER[weather].name} -- their sentries are miserable")
    elif weather == FAIR:
        p -= 0.07
        hurts.append("a clear day, and they can see your gate")

    # How many you send. The trade the whole thing is built on.
    over = max(0.0, share - SORTIE_SEEN)
    if over > 0:
        p -= over * SORTIE_SEEN_COST
        hurts.append(f"{share:.0%} of the garrison forming up is a thing "
                     f"they can watch you do")
    else:
        helps.append("a small party, and quick through the gate")

    # How long he has been sitting there.
    slack = min(SORTIE_SLACK, SORTIE_SLACK * siege_days / SORTIE_SLACK_DAYS)
    if slack > 0.03:
        p += slack
        helps.append(f"{siege_days} days in one camp makes a slack watch")

    # Whether he has seen this before. A second sortie is expected.
    if tries > 0:
        p -= SORTIE_WARNED * min(2, tries)
        hurts.append("you have done this to him before")

    return Sortie(surprise=max(0.04, min(0.95, p)),
                  quiet=SORTIE_QUIET, roused=SORTIE_ROUSED,
                  helps=helps, hurts=hurts)


def field_note(units: Dict[str, float], fld: Field) -> List[dict]:
    """What this field is worth to this host, by kind, for the panel.

    Only kinds you actually have: telling a man with no horse what the mud
    would do to his horse is noise.
    """
    have = Side(dict(units)).class_share()
    dials = fld.mult()
    out = []
    for cls, share in sorted(have.items(), key=lambda p: -p[1]):
        worth = dials.get(cls, 1.0)
        if share < 0.02 or abs(worth - 1.0) < 0.005:
            continue
        out.append({"kind": cls, "share": round(share, 3),
                    "worth": round(worth, 3),
                    "word": "worse" if worth < 1 else "better"})
    return out


DEFAULT_ORDER = LINE


def order(key: str) -> Order:
    return ORDERS.get(key or DEFAULT_ORDER, ORDERS[DEFAULT_ORDER])


def ordered(side: Side, key: str) -> Side:
    """A side as its order leaves it.

    Returns a *new* Side rather than editing the one passed in: a battle is
    resolved against copies, and an order that quietly changed the host it
    was given would leave the survivors permanently braver.
    """
    o = order(key)
    share = side.class_share().get(o.wants, 0.0) if o.wants else 0.0
    # An order that asks for horse and gets none is worth nothing; one given
    # to a host of horse is worth all of it.
    got = 1.0 + (o.bonus - 1.0) * min(1.0, share * 2.0)
    return Side(units=dict(side.units),
                attack_mult=side.attack_mult * o.attack * got,
                defense_mult=side.defense_mult * o.defense,
                battlement=side.battlement,
                morale=side.morale * o.morale)


def order_note(units: Dict[str, float], key: str) -> str:
    """What this order is worth to this host, in words."""
    o = order(key)
    if not o.wants:
        return o.blurb
    share = Side(dict(units)).class_share().get(o.wants, 0.0)
    if share <= 0.02:
        return f"{o.blurb} You have no {o.wants} at all."
    got = 1.0 + (o.bonus - 1.0) * min(1.0, share * 2.0)
    return f"{o.blurb} With your {o.wants}: worth {got:.2f} of itself."


def fight(attacker: Side, defender: Side, *, wall_hp: float = 0.0,
          rng: Optional[random.Random] = None, max_rounds: int = 14,
          place: str = "the field", orders: Tuple[str, str] = ("", ""),
          field: Optional[Field] = None) -> BattleResult:
    """Resolve a battle round by round. Walls change everything until they fall.

    `orders` is (attacker, defender) -- how each side was told to fight. An
    order multiplies dials this function already reads and lengthens or
    shortens the fight, so a decision made before the battle is visible in
    its outcome without a second combat model being written.

    `field` is where and when it is being fought, and it applies to both
    sides because they are standing in the same fen in the same rain. What
    differs is what each has brought to stand in it.
    """
    rng = rng or random.Random()
    # Applied to the sides that were handed in, and taken off again at the
    # end. Swapping in the copies `ordered` makes was the obvious way to
    # write this and quietly broke every battle in the game: the casualties
    # landed on the copy, the caller read its own untouched Side, and from
    # the day orders shipped nobody died in a siege assault. A sortie became
    # a free button that burnt the engines and cost nothing.
    att_key, def_key = orders
    keep = ((attacker.attack_mult, attacker.defense_mult, attacker.morale),
            (defender.attack_mult, defender.defense_mult, defender.morale))
    ground = (dict(attacker.class_mult), dict(defender.class_mult))
    if field is not None:
        dials = field.mult()
        for side in (attacker, defender):
            merged = dict(side.class_mult)
            for cls, v in dials.items():
                merged[cls] = merged.get(cls, 1.0) * v
            side.class_mult = merged
        place = field.place or place
    if att_key:
        _dress(attacker, att_key)
        max_rounds = order(att_key).rounds
    if def_key:
        _dress(defender, def_key)
    try:
        return _fight(attacker, defender, wall_hp=wall_hp, rng=rng,
                      max_rounds=max_rounds, place=place)
    finally:
        (attacker.attack_mult, attacker.defense_mult, attacker.morale) = keep[0]
        (defender.attack_mult, defender.defense_mult, defender.morale) = keep[1]
        attacker.class_mult, defender.class_mult = ground


def _dress(side: Side, key: str) -> None:
    """Put an order on a side, in place."""
    o = order(key)
    share = side.class_share().get(o.wants, 0.0) if o.wants else 0.0
    got = 1.0 + (o.bonus - 1.0) * min(1.0, share * 2.0)
    side.attack_mult *= o.attack * got
    side.defense_mult *= o.defense
    side.morale *= o.morale


def _fight(attacker: Side, defender: Side, *, wall_hp: float = 0.0,
           rng: Optional[random.Random] = None, max_rounds: int = 14,
           place: str = "the field") -> BattleResult:
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
    errand: str = ""              # 'pilgrimage' for a relic party; '' for a host
    #: What the PLAYER last saw of this host, which is not the same as where
    #: it is. Kept on the army for the same reason `Town.seen` is kept on the
    #: town: what you know is what you last looked at, and it goes stale while
    #: the other lord goes on marching. Never read for anything the world
    #: itself decides.
    #: How this host has been told to fight. Read when a battle happens, so
    #: the decision is made before the fight rather than during it -- which
    #: is the part of commanding a battle a day-ticked game can honestly
    #: offer.
    order: str = LINE
    seen_day: int = -1
    seen_at: str = ""
    seen_size: int = 0
    siege: SiegeState = field(default_factory=SiegeState)
    #: Rations in the baggage. A host eats every morning -- see supply.py --
    #: and this is the part of its eating that is its own rather than the
    #: country's. New hosts march out loaded; what they carry is the reason
    #: they can cross ground that would not feed them.
    stores: float = 0.0
    #: What it ate yesterday, in words, for the panel. Reporting only.
    fed: str = ""
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

    def where(self, name_of: Optional[Callable[[str], str]] = None) -> str:
        """Where the host is, in words a player uses.

        Given a resolver it says "besieging Dunmere" and "raiding St Brannoc";
        without one it falls back to the keys, which is fine for a log and was
        never fine on the status screen.
        """
        name = name_of or (lambda k: k)
        if self.state == MARCHING:
            return f"{self.days_left:.0f}d from {name(self.bound_for)}"
        if self.state == BESIEGING:
            return f"besieging {name(self.at)}"
        if self.state == RAIDING:
            return f"raiding {name(self.at)}"
        return name(self.at) if self.at else ""

    def note(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 30:
            del self.log[:-30]

    def prune(self) -> None:
        for k in list(self.units):
            if self.units[k] < 0.5:
                del self.units[k]

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("units", "log", "siege")}
        d["units"] = dict(self.units)
        d["log"] = list(self.log[-8:])
        d["siege"] = self.siege.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Army":
        d = dict(d)
        units = dict(d.pop("units", {}))
        log = list(d.pop("log", []))
        siege = SiegeState.from_dict(d.pop("siege", {}))
        a = cls(**d)
        a.units, a.log, a.siege = units, log, siege
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
