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
          place: str = "the field", orders: Tuple[str, str] = ("", "")
          ) -> BattleResult:
    """Resolve a battle round by round. Walls change everything until they fall.

    `orders` is (attacker, defender) -- how each side was told to fight. An
    order multiplies dials this function already reads and lengthens or
    shortens the fight, so a decision made before the battle is visible in
    its outcome without a second combat model being written.
    """
    rng = rng or random.Random()
    if any(orders):
        att_key, def_key = orders
        if att_key:
            attacker = ordered(attacker, att_key)
            max_rounds = order(att_key).rounds
        if def_key:
            defender = ordered(defender, def_key)
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
