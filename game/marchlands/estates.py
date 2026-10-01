"""The three men who actually run your march, and what each of them wants.

A lord in this game has been an unusually lonely autocrat. He sets the tax
rate and the tax rate happens; he caps the price of bread and the price of
bread is capped; he strikes coin and nobody objects. Every dial has had a
cost in *coin* or in *mood*, and none has had a cost in somebody powerful
being annoyed with him.

That is the piece EU4 has and this did not. Its estates are not a fourth
resource bar: they are the observation that a medieval ruler governed by
bargaining with people who had their own armies, their own money and their
own courts, and that the interesting decisions are the ones where two of them
want opposite things.

So: three estates, each tied to something the game already simulates.

* **The knights** hold the land and bring the levies. They want war, and land
  to take in it. Squeeze them and your muster falls -- not by a message, by
  fewer men actually mustering.
* **The chapter** holds the tithe and the learning. They want chapels built
  and the coin left alone. Mint your way out of a deficit and they will tell
  you what they think of it, and your research slows.
* **The guilds** hold the market. They want tolls low and prices free. The
  assize -- the price cap -- is a guild grievance by construction, which is
  the neatest thing about this: the economics layer already had the lever,
  it simply had nobody on the other end of it.

Two rules keep this from being a chore.

**Every grievance is something you did**, dated, decaying, and legible -- the
same shape as the chancery's opinion ledger, because it worked there.

**A privilege is a real trade.** Granting one buys loyalty and costs you a
power you had: the knights' land exemption costs you tax, the chapter's court
costs you a say in law, the guilds' charter costs you the right to cap their
prices. You can take them back, and they will remember that you did.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: How fast a grievance fades. A knight remembers a slight for about a season.
FADE = 0.985
#: Loyalty below this and they start withholding what they owe you.
SULKY = 40.0
#: Below this they are a problem in their own right.
ANGRY = 20.0
#: Loyalty moves this much of the way toward its target each day.
INERTIA = 0.06


@dataclass(frozen=True)
class Estate:
    key: str
    name: str
    blurb: str
    gives: str                  # what you lose first when they sulk
    #: What they are worth at full loyalty, as a multiplier on `gives`.
    best: float
    #: And at nothing. Between the two it is linear, because a cliff in the
    #: middle of a dial nobody can see is a trap rather than a decision.
    worst: float


ESTATES: Dict[str, Estate] = {e.key: e for e in [
    Estate("knights", "the knights",
           "hold the land and bring the levies; want war, and land to take",
           gives="muster", best=1.25, worst=0.60),
    Estate("chapter", "the chapter",
           "hold the tithe and the learning; want chapels, and the coin left alone",
           gives="research", best=1.30, worst=0.55),
    Estate("guilds", "the guilds",
           "hold the market; want tolls low and prices free",
           gives="trade", best=1.20, worst=0.65),
]}


@dataclass(frozen=True)
class Privilege:
    key: str
    estate: str
    name: str
    blurb: str
    loyalty: float              # what granting it is worth to them
    cost: str                   # what it costs you, in words
    #: The dial it actually moves, so the cost is real rather than described.
    effect: Tuple[str, float]


PRIVILEGES: Dict[str, Privilege] = {p.key: p for p in [
    Privilege("exemption", "knights", "exempt their land",
              "their manors pay no tax, and they remember that you agreed",
              loyalty=26.0, cost="a fifth of the tax roll",
              effect=("tax", -0.20)),
    Privilege("levy", "knights", "call the greater levy",
              "they bring more men, and expect a war to spend them in",
              loyalty=14.0, cost="a restlessness that grows through a long peace",
              effect=("muster", 0.18)),
    Privilege("court", "chapter", "grant them their own court",
              "the chapter judges its own, which is one law you no longer make",
              loyalty=24.0, cost="unrest is slower to settle",
              effect=("order", -0.15)),
    Privilege("tithe", "chapter", "confirm the tithe",
              "a tenth goes to the chapter before it reaches your chest",
              loyalty=20.0, cost="a tenth of what the land yields",
              effect=("tax", -0.10)),
    Privilege("charter", "guilds", "charter the market",
              "prices are theirs to set; you may not cap them again while it stands",
              loyalty=28.0, cost="no assize while it stands",
              effect=("assize", -1.0)),
    Privilege("monopoly", "guilds", "grant the wool monopoly",
              "one house takes the wool trade, and pays you handsomely for it",
              loyalty=16.0, cost="the goodwill of every merchant who is not them",
              effect=("trade", 0.12)),
]}


@dataclass
class Grievance:
    """One thing you did, and what they thought of it."""
    what: str
    by: float
    day: int

    def weight(self, today: int) -> float:
        return self.by * (FADE ** max(0, today - self.day))

    def to_dict(self) -> dict:
        return {"what": self.what, "by": self.by, "day": self.day}

    @classmethod
    def from_dict(cls, d: dict) -> "Grievance":
        return cls(what=d["what"], by=float(d["by"]), day=int(d["day"]))


@dataclass
class Standing:
    """Where one estate stands with you."""
    key: str
    loyalty: float = 55.0
    privileges: List[str] = field(default_factory=list)
    ledger: List[Grievance] = field(default_factory=list)

    def target(self, today: int) -> float:
        base = 50.0
        base += sum(g.weight(today) for g in self.ledger)
        base += sum(PRIVILEGES[p].loyalty for p in self.privileges
                    if p in PRIVILEGES)
        return max(0.0, min(100.0, base))

    def to_dict(self) -> dict:
        return {"key": self.key, "loyalty": self.loyalty,
                "privileges": list(self.privileges),
                "ledger": [g.to_dict() for g in self.ledger]}

    @classmethod
    def from_dict(cls, d: dict) -> "Standing":
        s = cls(key=d["key"], loyalty=float(d.get("loyalty", 55.0)),
                privileges=list(d.get("privileges", [])))
        s.ledger = [Grievance.from_dict(g) for g in d.get("ledger", [])]
        return s


class Estates:
    """All three of them, and the book of what you have done to each."""

    def __init__(self) -> None:
        self.by_key: Dict[str, Standing] = {
            k: Standing(key=k) for k in ESTATES}

    # ------------------------------------------------------------ the book
    def note(self, estate: str, what: str, by: float, day: int) -> None:
        """Write down something you did. Dated, so it fades."""
        st = self.by_key.get(estate)
        if st is None:
            return
        # One entry per kind of thing, refreshed rather than stacked: a tax
        # rise held for a year is one grievance somebody keeps mentioning,
        # not three hundred and sixty-five of them.
        for g in st.ledger:
            if g.what == what:
                g.by, g.day = by, day
                return
        st.ledger.append(Grievance(what=what, by=by, day=day))
        del st.ledger[:-12]

    def loyalty(self, estate: str) -> float:
        st = self.by_key.get(estate)
        return st.loyalty if st else 50.0

    def mult(self, what: str) -> float:
        """What the estates are collectively worth on one of their dials,
        privileges included -- so `levy` is more men and not a line of text."""
        """What the estates are collectively worth on one of their dials.

        This is the whole point of the module: it is not a number on a
        screen, it is fewer men at the muster.
        """
        out = 1.0
        for key, e in ESTATES.items():
            if e.gives != what:
                continue
            # Hinged at fifty, not interpolated end to end. Straight
            # interpolation made the *starting* loyalty worth about 0.96,
            # so every recruitment in the game quietly delivered fewer men
            # than you paid for from the first day, for no reason a player
            # could see. An estate you have not touched should cost nothing.
            f = max(0.0, min(1.0, self.by_key[key].loyalty / 100.0))
            if f >= 0.5:
                out *= 1.0 + (e.best - 1.0) * (f - 0.5) * 2.0
            else:
                out *= e.worst + (1.0 - e.worst) * f * 2.0
        return max(0.05, out + self.effect(what))

    def granted(self, privilege: str) -> bool:
        p = PRIVILEGES.get(privilege)
        return bool(p and privilege in self.by_key[p.estate].privileges)

    def effect(self, dial: str) -> float:
        """The sum of what every granted privilege does to one dial."""
        total = 0.0
        for st in self.by_key.values():
            for key in st.privileges:
                p = PRIVILEGES.get(key)
                if p and p.effect[0] == dial:
                    total += p.effect[1]
        return total

    # ----------------------------------------------------------- the trade
    def grant(self, privilege: str, day: int) -> str:
        p = PRIVILEGES.get(privilege)
        if p is None:
            return (f"there is no privilege called {privilege!r}; try "
                    + ", ".join(sorted(PRIVILEGES)))
        st = self.by_key[p.estate]
        if privilege in st.privileges:
            return f"{ESTATES[p.estate].name} already have that"
        st.privileges.append(privilege)
        self.note(p.estate, f"you granted them {p.name}", 0.0, day)
        return (f"granted: {p.name}. {ESTATES[p.estate].name} are pleased, "
                f"and it costs you {p.cost}")

    def revoke(self, privilege: str, day: int) -> str:
        p = PRIVILEGES.get(privilege)
        if p is None:
            return f"there is no privilege called {privilege!r}"
        st = self.by_key[p.estate]
        if privilege not in st.privileges:
            return f"{ESTATES[p.estate].name} do not have that to lose"
        st.privileges.remove(privilege)
        # Taking something back is worse than never giving it. They keep the
        # memory long after the privilege is gone, which is the whole reason
        # granting one is a decision rather than a free loyalty button.
        self.note(p.estate, f"you took back {p.name}", -p.loyalty * 1.4, day)
        return (f"revoked: {p.name}. {ESTATES[p.estate].name} will not "
                f"forget it")

    # ------------------------------------------------------------ the day
    def day(self, today: int) -> List[str]:
        said: List[str] = []
        for key, st in self.by_key.items():
            was = st.loyalty
            st.loyalty += INERTIA * (st.target(today) - st.loyalty)
            st.loyalty = max(0.0, min(100.0, st.loyalty))
            for bar, word in ((ANGRY, "are a danger to you"),
                              (SULKY, "have begun to withhold what they owe")):
                if was >= bar > st.loyalty:
                    said.append(f"{ESTATES[key].name} {word}")
            if was < SULKY <= st.loyalty:
                said.append(f"{ESTATES[key].name} are content again")
        return said

    def why(self, estate: str, today: int) -> List[Tuple[str, float]]:
        """What is moving one estate, loudest first."""
        st = self.by_key.get(estate)
        if st is None:
            return []
        out = [(g.what, round(g.weight(today), 1)) for g in st.ledger
               if abs(g.weight(today)) >= 0.5]
        out += [(PRIVILEGES[p].name, PRIVILEGES[p].loyalty)
                for p in st.privileges if p in PRIVILEGES]
        return sorted(out, key=lambda kv: -abs(kv[1]))

    # ------------------------------------------------------------- saving
    def to_dict(self) -> dict:
        return {k: st.to_dict() for k, st in self.by_key.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "Estates":
        e = cls()
        for k, sd in (d or {}).items():
            if k in e.by_key:
                e.by_key[k] = Standing.from_dict(sd)
        return e
