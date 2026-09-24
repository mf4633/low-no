"""The march as a diplomatic web rather than eight separate quarrels.

What people mean when they say they like Europa Universalis' politics is
rarely the peace screen. It is four things, and none of them is a war:

* **You can see why somebody hates you.** Not a number -- an itemised list of
  dated reasons, each decaying at its own rate. "He dislikes you" is flavour;
  "-38 for taking Vantry, and it wears off at a tenth a day" is a plan.
* **Conquest is self-limiting.** Taking a town offends everybody who watched
  you do it, and past a point they stop quarrelling with each other and start
  writing to each other instead. A coalition is the game telling you that the
  third town is a different kind of decision from the first.
* **A war needs a reason.** Not permission -- a *reason*, and the difference
  between having one and not having one is paid by everybody who was on the
  fence.
* **Friends cost something.** An ally who comes when you are attacked is an
  ally who calls when he is, and the day you do not answer is the day your
  word is worth less to everyone on the march.

This game had one number per lord called `hostility`, which went up on a timer
and down when you paid. Everything above is built on top of it rather than in
place of it: the timer is still the timer, and what changes is that the number
now has *reasons* attached, that the reasons are visible, and that they add up
across the march instead of only pointing at you one lord at a time.

The whole module is a ledger and a set of readings over it. It owns no dice
except its own -- see `Chancery.rng`, and the note on it, which is the third
time this codebase has had to learn that lesson.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


# --------------------------------------------------------------- the reasons
#
# One catalogue, so that every part of the game that can offend a lord has to
# come here and say so in words a player will read back. A grudge with no
# entry here has no business existing.

@dataclass(frozen=True)
class Why:
    key: str
    label: str              # what the court screen calls it
    decay: float            # points a day back toward nothing; 0 is forever
    aggressive: bool = False   # does it count toward a coalition?
    #: Awe is not affection. A lord whose host you broke will not put his
    #: name to a letter with a man who beat him twice on it -- and he does
    #: not think better of you for it either, will not ally, and his temper
    #: is not cooled. Keeping the two apart is the difference between "they
    #: fear you" and "they like you", which are not the same lever.
    awe: bool = False


WHYS: Dict[str, Why] = {w.key: w for w in [
    # -- things you did to them, or to somebody they were watching -----------
    # Decays are per day, so the number to think in is how long a reason
    # takes to wear out: taking a town is about four hundred days of ill-will
    # at the neighbours, an unjust war rather more because it is about your
    # character rather than your appetite, and a siege the march thought was
    # fair is forgotten inside a season. That separation is the whole design:
    # a lord who makes war for reasons other lords accept can make war for
    # years; a lord who does not gets two before they stop quarrelling with
    # each other and start writing to each other.
    Why("took_town", "you took a town on this march", 0.085, aggressive=True),
    Why("unjust", "you marched with no reason anybody accepted", 0.038,
        aggressive=True),
    Why("raided_them", "you burned their country", 0.075, aggressive=True),
    Why("besieged", "you sat down in front of their walls", 0.115,
        aggressive=True),
    Why("demanded", "you demanded tribute of them", 0.090),
    Why("broke_word", "you did not come when you were called", 0.020,
        aggressive=True),
    Why("inherited", "a house ended and you took what it held", 0.045,
        aggressive=True),
    # -- things you did for them --------------------------------------------
    Why("marriage", "your houses are married", 0.0),
    Why("gift", "you have been generous", 0.022),
    Why("ally", "you are allied", 0.0),
    Why("came_when_called", "you came when they called", 0.008),
    Why("truce", "there is a treaty between you", 0.045),
    Why("relieved", "you broke a siege of theirs", 0.020),
    # -- things that happened to them ---------------------------------------
    Why("beaten", "you have beaten their host, and they know it", 0.035,
        aggressive=True, awe=True),
    Why("neighbourly", "you have traded here for years", 0.0),
]}

#: Below this, a lord will not treat with you at all; above it he will ally.
COLD = -30.0
WARM = 40.0

#: How much aggressive ill-will it takes before a lord will put his name to a
#: letter with his neighbours on it, and how many names make a coalition.
COALITION_BAR = 45.0
#: ...and how far it has to fall before that name comes off again. Lower than
#: the bar on purpose: without the gap a lord hovering on 45 signs and unsigns
#: every few days, and a coalition that flickers is one nobody can plan round.
COALITION_LAPSE = 32.0
COALITION_NAMES = 3
#: And what it costs to buy the whole thing off at once, per name, per point.
COALITION_PRICE = 26.0


@dataclass
class Grudge:
    """One dated, decaying reason. Positive means they think better of you."""
    why: str
    weight: float
    day: int

    def value(self, today: int) -> float:
        spec = WHYS.get(self.why)
        if spec is None:
            return 0.0
        if not spec.decay:
            return self.weight
        worn = spec.decay * max(0, today - self.day)
        if abs(self.weight) <= worn:
            return 0.0
        return self.weight - worn * (1.0 if self.weight > 0 else -1.0)

    def to_dict(self) -> dict:
        return {"why": self.why, "weight": round(self.weight, 3), "day": self.day}

    @classmethod
    def from_dict(cls, d: dict) -> "Grudge":
        return cls(why=d["why"], weight=float(d["weight"]), day=int(d["day"]))


# ---------------------------------------------------------- a reason to march

@dataclass(frozen=True)
class Ground:
    """A reason to march that other people will accept.

    Not permission. Nothing stops you marching on anybody at any hour. What a
    ground buys is that the rest of the march shrugs instead of writing to
    each other about you, and that your own town does not spend the season
    saying it was a wicked business.
    """
    key: str
    label: str
    days: int               # how long it stays good once it happens


GROUNDS: Dict[str, Ground] = {g.key: g for g in [
    Ground("attacked", "their host is on your land", 120),
    Ground("raided", "they burned your country", 150),
    Ground("blockade", "they have cut your roads", 90),
    Ground("broken_truce", "they marched while a treaty ran", 400),
    Ground("claim", "your house has a claim there by marriage", 0),
    Ground("shrine", "they hold a shrine you have men at", 200),
    Ground("coalition", "they have signed against you", 0),
    Ground("called", "an ally of yours called you to it", 60),
]}


@dataclass
class Chancery:
    """Every letter anybody has written, and who is talking to whom."""
    #: town key -> the grudges standing against (or for) you
    ledger: Dict[str, List[Grudge]] = field(default_factory=dict)
    #: town key -> {ground key: the day it happened}
    grounds: Dict[str, Dict[str, int]] = field(default_factory=dict)
    #: town keys who have put their names to the same letter, and the day
    coalition: List[str] = field(default_factory=list)
    coalition_day: int = -1
    #: town keys sworn to come when you are attacked
    allies: List[str] = field(default_factory=list)
    #: an ally who has called and is waiting for an answer: (key, day)
    called: Optional[Tuple[str, int]] = None
    #: town key -> day the marriage claim was made (claims outlive the person)
    claims: Dict[str, int] = field(default_factory=dict)
    #: town key -> days the war with him has run, while there is a war score
    #: at all. EU4's war exhaustion: a long war makes a lord readier to treat
    #: and cheaper to treat with, whoever is winning it.
    war_days: Dict[str, int] = field(default_factory=dict)
    #: town key -> his opinion of you as it has settled in him: Unciv keeps a
    #: slow average under the day's number so one gift the week before a war
    #: does not undo a year of grievance, nor one insult a year of trade. It
    #: is what his decisions read; `opinion` is what he says today.
    settled: Dict[str, float] = field(default_factory=dict)
    #: town key -> calls of his you have let go by. Freeciv's ally asks
    #: three times, each more sharply, before the alliance is over.
    refused: Dict[str, int] = field(default_factory=dict)
    #: Defensive pacts between lords, keyed by the sorted pair of town keys
    #: ("a|b"), and the day each was sworn. Civ's small neighbours band
    #: together against the big one; here two lords who both fear the
    #: strongest on the march swear to march for each other's walls.
    pacts: Dict[str, int] = field(default_factory=dict)
    #: town key -> the day he declared friendship with you. Civ's
    #: declaration of friendship: short of an alliance, nobody is sworn to
    #: march, but a friend does not march on you, and a friend betrayed
    #: tells everybody.
    friends: Dict[str, int] = field(default_factory=dict)
    #: town key -> the day a war with them last began. Its own dict and not a
    #: private key in `grounds`, which is what it was for about ten minutes:
    #: a bookkeeping marker filed among the real reasons is a marker that
    #: turns up in somebody's reason-to-march list.
    declared: Dict[str, int] = field(default_factory=dict)
    #: Heralds. A grievance you can name lasts longer than one you cannot --
    #: so your own grounds for war keep twice as long, which is the whole of
    #: what a herald was for.
    long_memory: bool = False
    #: ...and which of those wars had a reason the march accepted. Kept
    #: separately because it has to outlive the ground itself: a claim that
    #: expires in the third month of a siege does not retroactively make the
    #: war you began in the first month a robbery.
    justified: Dict[str, int] = field(default_factory=dict)
    #: Towns the march has already priced you as the conqueror of.
    taken: set = field(default_factory=set)
    #: Trust, 0-100, apart from liking. Opinion is whether a lord is fond of
    #: you; trust is whether he thinks you keep your word -- EU4 keeps them
    #: apart and so does this. It drifts back toward 50, a call answered is
    #: +10 and one ignored -20, a truce broken -30, and only an ally is ever
    #: trusted past 80. An alliance wants 35 to swear and lapses under 30.
    trust: Dict[str, float] = field(default_factory=dict)
    #: The war as each lord reckons it, -100 to +100 from your side: a host
    #: of his broken, a storm thrown back, a town taken, his country burned.
    #: Wears back toward nothing a point a day. It is what he asks for a
    #: truce on, and what makes him ask you for one.
    score: Dict[str, float] = field(default_factory=dict)
    #: town key -> the day he sued for peace, which makes a truce free a while.
    sued: Dict[str, int] = field(default_factory=dict)
    #: ally key -> the day he last sent men to help you.
    aided: Dict[str, int] = field(default_factory=dict)

    #: Its own dice, and the reason is worth writing down for the fourth time.
    #: The kin drew from the world's stream and a birth in the hall moved the
    #: weather; the league drew from it and a draft class re-rolled twelve
    #: seeds of balance measurement; the voices drew from it and a browser
    #: poll would have re-rolled the campaign. A subsystem that draws gets a
    #: stream of its own, and there are no exceptions left to find.
    seed: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed or 104729)

    # ------------------------------------------------------------- the ledger
    def write(self, key: str, why: str, weight: float, day: int) -> None:
        """Put a reason in the book. Nothing else may touch the number."""
        if why not in WHYS or not weight:
            return
        self.ledger.setdefault(key, []).append(Grudge(why, weight, day))

    def write_all(self, keys: Iterable[str], why: str, weight: float,
                  day: int) -> None:
        for k in keys:
            self.write(k, why, weight, day)

    def sweep(self, day: int) -> None:
        """Drop what has worn out, so the book does not grow without end."""
        for key, rows in list(self.ledger.items()):
            live = [g for g in rows if g.value(day)]
            if live:
                self.ledger[key] = live
            else:
                self.ledger.pop(key, None)

    def opinion(self, key: str, day: int) -> float:
        # 0.0 rather than sum()'s int 0, so a lord nobody has written anything
        # about returns the same type as one they have.
        return sum((g.value(day) for g in self.ledger.get(key, ())), 0.0)

    #: How fast the settled opinion follows the day's: a tenth a day.
    SETTLE = 0.1

    def settle_opinions(self, keys: Iterable[str], day: int) -> None:
        for k in keys:
            now = self.opinion(k, day)
            was = self.settled.get(k, now)
            self.settled[k] = was + (now - was) * self.SETTLE

    def settled_view(self, key: str, day: int) -> float:
        return self.settled.get(key, self.opinion(key, day))

    @staticmethod
    def pair(a: str, b: str) -> str:
        return "|".join(sorted((a, b)))

    def partners(self, key: str) -> List[str]:
        """The lords sworn to march for this one's walls."""
        out = []
        for p in sorted(self.pacts):
            a, b = p.split("|")
            if key in (a, b):
                out.append(b if a == key else a)
        return out

    def goodwill(self, key: str, day: int) -> float:
        """Only what is in your favour -- the number the old `favour` was.

        Awe is left out. Breaking a lord's host is a reason he will not sign
        a letter against you; it is not a reason he warms to you, and letting
        it read as one made a man you had beaten twice into a friend.
        """
        return sum((g.value(day) for g in self.ledger.get(key, ())
                    if g.value(day) > 0 and not WHYS[g.why].awe), 0.0)

    def offence(self, key: str, day: int) -> float:
        """Only aggressive ill-will: what a coalition is actually about.

        A lord who dislikes you for demanding tribute is a lord who dislikes
        you. A lord who has watched you take three towns is a lord with a
        reason to talk to his neighbours, and only the second kind of feeling
        puts a name on a letter.
        """
        # Every aggressive reason, both ways round. Summing only the
        # negative ones meant a broken host counted for nothing at all while
        # the court screen was telling the player it was worth twenty-two --
        # a promise in the interface that the arithmetic did not keep.
        return max(0.0, -sum(g.value(day) for g in self.ledger.get(key, ())
                             if WHYS[g.why].aggressive))

    def reasons(self, key: str, day: int) -> List[Tuple[str, float, float]]:
        """The itemised list, biggest first: (label, value, per-day decay).

        This is the whole point of keeping a ledger instead of a number. A
        player who can read why can do something about it.
        """
        rolled: Dict[str, float] = {}
        for g in self.ledger.get(key, ()):
            v = g.value(day)
            if v:
                rolled[g.why] = rolled.get(g.why, 0.0) + v
        return sorted(((WHYS[w].label, v, WHYS[w].decay)
                       for w, v in rolled.items()),
                      key=lambda row: -abs(row[1]))

    # --------------------------------------------------- trust and the war
    TRUST_FLOOR_ALLY = 35.0
    TRUST_LAPSE = 30.0

    def trust_of(self, key: str) -> float:
        return self.trust.get(key, 50.0)

    def shake(self, key: str, by: float) -> None:
        """Move a lord's trust, within 0-100 -- and past 80 only for an ally."""
        top = 100.0 if key in self.allies else 80.0
        self.trust[key] = max(0.0, min(top, self.trust_of(key) + by))

    def reckon(self, key: str, by: float) -> None:
        """Move the war's score with one lord, from your side."""
        self.score[key] = max(-100.0, min(100.0, self.score.get(key, 0.0) + by))

    def settle_day(self) -> None:
        """Trust drifts home and the war's score wears off, a day at a time."""
        for k in list(self.trust):
            t = self.trust[k]
            t += (50.0 - t) * 0.01
            if k not in self.allies:
                t = min(80.0, t)
            self.trust[k] = t
        for k in list(self.score):
            v = self.score[k]
            v = v - 1.0 if v > 1.0 else v + 1.0 if v < -1.0 else 0.0
            if v:
                self.score[k] = v
                self.war_days[k] = self.war_days.get(k, 0) + 1
            else:
                del self.score[k]
                self.war_days.pop(k, None)

    #: How long a claim is a reason to march. EU4 lets an unpressed claim
    #: lapse after twenty-five years; a game here is three, so two. The
    #: right to inherit is another thing and does not lapse.
    CLAIM_DAYS = 2 * 360

    def claim_live(self, key: str, day: int) -> bool:
        return key in self.claims and day - self.claims[key] <= self.CLAIM_DAYS

    # ------------------------------------------------------------- the ground
    def give_ground(self, key: str, ground: str, day: int) -> None:
        if ground in GROUNDS:
            self.grounds.setdefault(key, {})[ground] = day

    def ground_for(self, key: str, day: int) -> Optional[Ground]:
        """The best reason you have to march on this lord today, if any."""
        live = []
        keep = 2.0 if self.long_memory else 1.0
        for name, when in self.grounds.get(key, {}).items():
            spec = GROUNDS[name]
            if not spec.days or day - when <= spec.days * keep:
                live.append(spec)
        if key in self.coalition:
            live.append(GROUNDS["coalition"])
        if self.claim_live(key, day):
            live.append(GROUNDS["claim"])
        if not live:
            return None
        # The longest-lived reason reads as the strongest, which is also true.
        return max(live, key=lambda g: (g.days == 0, g.days))

    def grounds_left(self, key: str, day: int) -> List[Tuple[str, int]]:
        """Every live reason and how many days it has left; 0 means forever."""
        out = []
        keep = 2.0 if self.long_memory else 1.0
        for name, when in sorted(self.grounds.get(key, {}).items()):
            spec = GROUNDS[name]
            if not spec.days:
                out.append((spec.label, 0))
            elif day - when <= spec.days * keep:
                out.append((spec.label, int(spec.days * keep - (day - when))))
        if self.claim_live(key, day):
            out.append((GROUNDS["claim"].label,
                        self.CLAIM_DAYS - (day - self.claims[key])))
        if key in self.coalition:
            out.append((GROUNDS["coalition"].label, 0))
        return out

    # ---------------------------------------------------------- the coalition
    def signatories(self, keys: Iterable[str], day: int) -> List[str]:
        """Who has enough reason to put a name to a letter."""
        return sorted(k for k in keys if self.offence(k, day) >= COALITION_BAR)

    def still_signed(self, day: int) -> List[str]:
        """Who is still angry enough to keep their name on it.

        Separate from `signatories` and lower, so that mollifying one lord
        takes his name off without taking the whole letter down -- and so a
        lord who has just about cooled does not sign and unsign weekly.
        """
        return [k for k in self.coalition
                if self.offence(k, day) >= COALITION_LAPSE]

    def coalition_price(self, day: int) -> float:
        return COALITION_PRICE * sum(self.offence(k, day)
                                     for k in self.coalition)

    def to_dict(self) -> dict:
        return {
            "ledger": {k: [g.to_dict() for g in v]
                       for k, v in self.ledger.items()},
            "grounds": {k: dict(v) for k, v in self.grounds.items()},
            "coalition": list(self.coalition),
            "coalition_day": self.coalition_day,
            "allies": list(self.allies),
            "called": list(self.called) if self.called else None,
            "claims": dict(self.claims),
            "declared": dict(self.declared),
            "long_memory": self.long_memory,
            "justified": dict(self.justified),
            "taken": sorted(self.taken),
            "trust": dict(self.trust), "score": dict(self.score),
            "sued": dict(self.sued), "aided": dict(self.aided),
            "war_days": dict(self.war_days),
            "settled": dict(self.settled), "refused": dict(self.refused),
            "pacts": dict(self.pacts), "friends": dict(self.friends),
            "seed": self.seed,
            "rng": list(self.rng.getstate()),
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Chancery":
        d = d or {}
        c = cls(seed=int(d.get("seed", 0)))
        c.ledger = {k: [Grudge.from_dict(g) for g in v]
                    for k, v in d.get("ledger", {}).items()}
        c.grounds = {k: {n: int(day) for n, day in v.items()}
                     for k, v in d.get("grounds", {}).items()}
        c.coalition = list(d.get("coalition", []))
        c.coalition_day = int(d.get("coalition_day", -1))
        c.allies = list(d.get("allies", []))
        called = d.get("called")
        c.called = (called[0], int(called[1])) if called else None
        c.claims = {k: int(v) for k, v in d.get("claims", {}).items()}
        c.declared = {k: int(v) for k, v in d.get("declared", {}).items()}
        c.long_memory = bool(d.get("long_memory", False))
        c.justified = {k: int(v) for k, v in d.get("justified", {}).items()}
        c.taken = set(d.get("taken", []))
        c.trust = {k: float(v) for k, v in d.get("trust", {}).items()}
        c.score = {k: float(v) for k, v in d.get("score", {}).items()}
        c.sued = {k: int(v) for k, v in d.get("sued", {}).items()}
        c.aided = {k: int(v) for k, v in d.get("aided", {}).items()}
        c.war_days = {k: int(v) for k, v in d.get("war_days", {}).items()}
        c.settled = {k: float(v) for k, v in d.get("settled", {}).items()}
        c.refused = {k: int(v) for k, v in d.get("refused", {}).items()}
        c.pacts = {k: int(v) for k, v in d.get("pacts", {}).items()}
        c.friends = {k: int(v) for k, v in d.get("friends", {}).items()}
        raw = d.get("rng")
        if raw:
            c.rng.setstate((raw[0], tuple(raw[1]), raw[2]))
        return c


# ------------------------------------------------------------- what it is worth
#
# Read off the ledger, never stored. Same rule as the castle: a stored
# judgement goes stale the moment somebody writes a letter.

def temper(opinion: float) -> str:
    """A word for a number, because "-38" is not how anybody thinks of a man."""
    if opinion >= 70:
        return "devoted"
    if opinion >= WARM:
        return "friendly"
    if opinion >= 12:
        return "warm"
    if opinion > -12:
        return "correct"
    if opinion > -40:
        return "cool"
    if opinion > -75:
        return "hostile"
    return "implacable"


def unjust_cost(offended: int) -> float:
    """What marching with no reason costs in mood at home.

    Your own town is not a spectator. They have sons in the host, and a war
    nobody can name a cause for is a war they remember you for.
    """
    return min(14.0, 5.0 + 1.5 * offended)
