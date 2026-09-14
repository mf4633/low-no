"""The castle as a place rather than a number.

A wall in most games is a pool of hit points: buy more of it and the siege
takes longer. Stronghold's castles were *designs*. The question was never how
much wall you had, it was what a man had to cross to reach it, what was
looking down at him while he crossed, and which of his answers you had spoiled
before he arrived.

So a besieger here picks a plan, and every plan is answered by a different
thing you dug:

    batter    rams at the gate        beaten by boiling oil
    breach    engines on the curtain  slowed by a moat, needs real engines
    escalade  ladders on the wall     beaten by towers and a pitch ditch
    sap       a mine under a section  beaten outright by water in the ditch
    invest    sit down and starve it  beaten by a full granary and a sortie

None of it is free to the defender. Works stand on the wall line and the wall
line is finite, so every ditch you dig is a tower you did not build -- which
is the decision Stronghold was actually about.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

BATTER = "batter"
BREACH = "breach"
ESCALADE = "escalade"
SAP = "sap"
INVEST = "invest"


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    needs_siege: float      # siege power the host must bring to try it at all
    needs_engineers: bool
    wall_rate: float        # multiplier on what engines take off the wall
    exposure: float         # multiplier on what the garrison does to the host
    reach: float            # how much of the garrison a storm can get at
    blurb: str

    def viable(self, siege_power: float, engineers: float) -> Tuple[bool, str]:
        if self.needs_engineers and engineers < 1:
            return False, "no engineers in the host to dig it"
        if siege_power < self.needs_siege:
            return False, (f"needs {self.needs_siege:.0f} of engine power, "
                           f"the host has {siege_power:.0f}")
        return True, ""


PLANS: Dict[str, Plan] = {
    BATTER: Plan(BATTER, "batter the gate", needs_siege=20, needs_engineers=False,
                 wall_rate=1.30, exposure=1.15, reach=0.9,
                 blurb="Rams at the gate. The quickest way through a wall, and "
                       "the one place a defender expects you."),
    BREACH: Plan(BREACH, "breach the curtain", needs_siege=55, needs_engineers=False,
                 wall_rate=1.0, exposure=0.65, reach=1.0,
                 blurb="Stand off and throw stone until a length of wall lies "
                       "down. Slow, dear, and it ignores the gatehouse."),
    ESCALADE: Plan(ESCALADE, "escalade the wall", needs_siege=0, needs_engineers=False,
                   wall_rate=0.0, exposure=2.10, reach=0.75,
                   blurb="Ladders, and men to climb them. Needs no engines at "
                         "all, which is the only kind thing about it."),
    SAP: Plan(SAP, "sap the foundation", needs_siege=0, needs_engineers=True,
              wall_rate=0.0, exposure=0.30, reach=1.0,
              blurb="Dig under a section and fire the props. Quiet, cheap in "
                    "men, and useless against water."),
    INVEST: Plan(INVEST, "invest and starve", needs_siege=0, needs_engineers=False,
                 wall_rate=0.0, exposure=0.20, reach=0.0,
                 blurb="Touch nothing. Cut the roads, sit down, and let the "
                       "granary do the work."),
}

SAP_DAYS = 6            # how long a mine takes before the props are fired
CROSS_DAYS = 3          # days a moat costs a host before it can come to grips


def storms_now(plan: str, wall: float, defenders: float) -> bool:
    """Whether today is the day the host actually goes in.

    A breach or a mine waits for the stone to come down. Ladders do not: they
    wait for the *wall-walk* to be empty, which is why escalade is a way of
    spending men to avoid spending engines.
    """
    if wall <= 0:
        return True
    return plan == ESCALADE and defenders < 1.0


@dataclass
class Works:
    """What stands on a wall line, from the besieger's point of view."""
    moat: int = 0
    pitch: int = 0
    pits: int = 0
    oil: int = 0
    towers: int = 0
    gate: bool = False
    stone: bool = False
    #: Read off the drawing rather than off the shopping list. A castle with
    #: four towers all on one side has four towers and one open flank, and
    #: these are the two numbers that tell the difference.
    naked: int = 0          # yards in the longest run no tower covers
    depth: int = 1          # rings a man has to get through to reach the keep

    @classmethod
    def of(cls, standing: List[str]) -> "Works":
        """Read the works off a list of completed rampart building keys."""
        return cls(
            moat=standing.count("moat"),
            pitch=standing.count("pitch_ditch"),
            pits=standing.count("kill_pit"),
            oil=standing.count("oil_pot"),
            towers=standing.count("wall_tower"),
            gate="gatehouse" in standing,
            stone=any(k in standing for k in ("stone_wall", "gatehouse", "wall_tower")),
        )

    @classmethod
    def read(cls, castle, reading=None) -> "Works":
        """The works as they actually stand on the ground.

        The same five questions as `of`, asked of a drawing instead of a list
        of purchases -- so a moat dug on the far side from where they are
        digging is not a moat that answers this mine, and four towers in a
        clump are not four towers covering the wall.
        """
        from . import keep as keeps
        r = reading if reading is not None else keeps.read(castle)
        counts = castle.spent()
        return cls(moat=counts.get(keeps.MOAT, 0),
                   pitch=counts.get(keeps.PITCH, 0),
                   pits=counts.get(keeps.PITS, 0),
                   oil=0, towers=r.towers, gate=bool(r.gates),
                   stone=bool(r.stone or r.towers or r.gates),
                   naked=len(r.weak), depth=max(1, r.depth))

    def answers(self, plan: str) -> List[str]:
        """The works that bear on this plan, named so a player can see why."""
        out: List[str] = []
        if plan == BATTER and self.oil:
            out.append("boiling oil over the gate")
        if plan == SAP and self.moat:
            out.append("a flooded ditch they cannot dig under")
        if plan in (BATTER, ESCALADE) and self.moat:
            out.append("a moat to cross first")
        if plan in (BATTER, ESCALADE) and self.pitch:
            out.append("a pitch ditch waiting to be lit")
        if plan == ESCALADE and self.towers and not self.naked:
            out.append(f"{self.towers} tower(s), and no stretch they do not cover")
        elif plan == ESCALADE and self.towers:
            out.append(f"{self.towers} tower(s) -- but {self.naked} yards "
                       f"they cannot see")
        if plan == BREACH and self.towers:
            out.append(f"{self.towers} tower(s) shooting back at the engine crews")
        if plan == BREACH and self.stone:
            out.append("a stone curtain rather than a palisade")
        if plan in (ESCALADE, BATTER) and self.pits:
            out.append("killing pits under the wall")
        if plan == INVEST and self.gate:
            out.append("a gatehouse they can sortie from")
        if self.depth > 1:
            out.append(f"{self.depth} walls between them and the hall")
        return out


@dataclass
class SiegeState:
    """What a particular host has got through so far. Lives on the army."""
    plan: str = BREACH
    days: int = 0
    crossed: int = 0        # days spent filling the moat
    sap_days: int = 0
    pitch_spent: bool = False

    def to_dict(self) -> dict:
        return {"plan": self.plan, "days": self.days, "crossed": self.crossed,
                "sap_days": self.sap_days, "pitch_spent": self.pitch_spent}

    @classmethod
    def from_dict(cls, d: dict) -> "SiegeState":
        return cls(plan=d.get("plan", BREACH), days=d.get("days", 0),
                   crossed=d.get("crossed", 0), sap_days=d.get("sap_days", 0),
                   pitch_spent=d.get("pitch_spent", False))


@dataclass
class Approach:
    """One day of a plan meeting the works that answer it."""
    wall_damage: float = 0.0
    attacker_mult: float = 1.0      # scales the garrison's fire onto the host
    defender_mult: float = 1.0      # scales the host's fire onto the garrison
    burst: float = 0.0              # extra fraction of the host killed outright
    blockade: bool = False          # the roads are cut
    lines: List[str] = field(default_factory=list)


def approach(plan_key: str, works: Works, state: SiegeState, *,
             siege_power: float, engineers: float, wall: float, wall_max: float,
             have_pitch: bool, rng: Optional[random.Random] = None) -> Approach:
    """Work out what one day of this plan against these works actually does.

    Returns the multipliers the day's fighting is then resolved with, so the
    plan changes the shape of the siege rather than just its arithmetic.
    """
    rng = rng or random.Random()
    plan = PLANS.get(plan_key, PLANS[BREACH])
    out = Approach(attacker_mult=plan.exposure, defender_mult=plan.reach)
    state.days += 1
    # A second ring is not more stone, it is a yard they have to cross with
    # a wall shooting into it: most of the garrison is not on the wall they
    # have just taken. It reduces what a day of this can reach, not what it
    # has to knock down.
    inner = 1.0 / max(1, works.depth)

    # A moat has to be filled before anything that needs to touch the wall.
    if works.moat and plan.key in (BATTER, ESCALADE) and state.crossed < CROSS_DAYS:
        state.crossed += 1
        out.attacker_mult = plan.exposure * 1.25
        out.defender_mult = 0.0
        out.lines.append(f"the host works at the ditch under fire "
                         f"({CROSS_DAYS - state.crossed} days of it left)")
        return out

    if plan.key == SAP:
        if works.moat:
            out.lines.append("the miners strike water: nothing can be dug here "
                             "while the ditch is flooded")
            out.attacker_mult = plan.exposure
            return out
        state.sap_days += 1
        if state.sap_days >= SAP_DAYS:
            state.sap_days = 0
            out.wall_damage = wall_max * (0.30 + 0.15 * rng.random())
            out.lines.append("the props are fired and a length of wall sits down "
                             "into its own cellar")
        else:
            out.lines.append(f"the mine goes forward, quietly "
                             f"({SAP_DAYS - state.sap_days} days to the props)")
        return out

    if plan.key == INVEST:
        out.blockade = True
        out.lines.append("the roads are cut; nothing goes in and nothing comes out")
        return out

    # Pitch goes off once, on the first day anyone comes close enough.
    if (works.pitch and not state.pitch_spent and have_pitch
            and plan.key in (BATTER, ESCALADE)):
        state.pitch_spent = True
        out.burst += 0.11 + 0.05 * rng.random()
        out.lines.append("the ditch is fired: the assault goes in through burning pitch")

    if plan.key == ESCALADE:
        # Ladders against an intact wall are the worst trade in the game, and
        # towers are exactly what makes them worse -- but only the towers that
        # can see where the ladders are going. A besieger puts them on the
        # longest stretch nobody covers, so a tower on the far side of the
        # castle is a tower he has already walked past.
        intact = min(1.0, wall / wall_max) if wall_max > 0 else 0.0
        watched = max(0.0, 1.0 - works.naked / 8.0)
        out.attacker_mult = plan.exposure * (1.0 + 0.55 * intact
                                             + 0.22 * works.towers * watched)
        out.defender_mult = plan.reach * (1.0 - 0.45 * intact) * inner
        if works.pits:
            out.burst += 0.02 * works.pits
        if works.naked and works.towers:
            out.lines.append(f"the ladders go up on the {works.naked} yards "
                             f"no tower covers")
        else:
            out.lines.append("ladders go up against the wall")
        return out

    # batter and breach both work stone; the gate is softer but better covered.
    out.wall_damage = siege_power * plan.wall_rate * (0.8 + 0.4 * rng.random())
    if plan.key == BATTER:
        if works.oil:
            out.burst += 0.05 + 0.03 * rng.random()
            out.lines.append("oil comes over the gatehouse onto the ram crews")
        if works.pits:
            out.burst += 0.015 * works.pits
        out.lines.append("the ram goes in at the gate")
    else:
        # The answer to a man standing off with engines is engines of your own,
        # which is what a tower is: it shoots at the crews, not at the wall.
        if works.towers:
            out.wall_damage /= 1.0 + 0.20 * works.towers
            out.attacker_mult = plan.exposure * (1.0 + 0.28 * works.towers)
        if works.stone:
            out.wall_damage *= 0.85
        out.lines.append("the engines work on the curtain")
    out.defender_mult *= inner
    return out


def choose(works: Works, *, siege_power: float, engineers: float,
           host: float, garrison: float, wall: float, wall_max: float,
           patient: bool = False) -> str:
    """Pick the plan a competent captain would pick against these works.

    Used by the AI lords, and by `hint` when it is asked what to do with a
    host that is standing in front of somebody else's wall.
    """
    intact = min(1.0, wall / wall_max) if wall_max > 0 else 0.0
    scores: Dict[str, float] = {}
    for key, plan in PLANS.items():
        ok, _why = plan.viable(siege_power, engineers)
        if not ok:
            continue
        if key == SAP and works.moat:
            continue
        s = 0.0
        if key == BREACH:
            s = 1.0 + siege_power / 90.0
        elif key == BATTER:
            s = 1.15 + siege_power / 70.0 - 0.55 * works.oil
        elif key == ESCALADE:
            # What makes a ladder bad is the man at the top of it, not the
            # stone: an intact wall with nobody on it is simply a tall step.
            odds = min(4.0, host / max(garrison, 1.0))
            manned = min(1.0, garrison / max(1.0, 0.30 * host))
            # A captain does not average your towers. He walks round the
            # wall until he finds the longest stretch none of them covers,
            # and that is where the ladders go -- so towers are worth
            # something to him only while there is no such stretch.
            watched = max(0.0, 1.0 - works.naked / 8.0)
            s = (0.30 + 0.55 * odds - 1.45 * intact * manned
                 - 0.30 * works.towers * manned * watched
                 + 0.55 * min(1.0, works.naked / 8.0) * manned
                 + 2.20 * (1.0 - manned))   # an empty wall is a tall step, not a siege
        elif key == SAP:
            s = 1.25 if intact > 0.5 else 0.6
        elif key == INVEST:
            s = 1.90 if patient else 0.25
            s -= 0.35 if works.gate else 0.0
        scores[key] = s
    if not scores:
        return INVEST
    return max(scores.items(), key=lambda kv: kv[1])[0]
