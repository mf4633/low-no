"""The line: the people the whole arrangement is actually about.

Stronghold gives you a lord standing in his courtyard with a sword. Age of
Empires gives you a civilisation that cannot die. Bannerlord gives you the
third thing both of them leave out -- a person who gets *better at what he
actually does*, marries somebody's daughter for reasons of state, has children
who grow up while you are busy elsewhere, and eventually dies and hands the
whole business to one of them.

That last clause is the design. Everything in this file exists so that the
heir is *somebody*. A succession that resets the numbers is a death in a
spreadsheet. A succession that hands the seat to a woman of twenty-two who has
had your carts since she was fifteen -- and whose trade is four, and you can
see it in the margin the week she takes over -- is a story, and it is the same
arithmetic either way. The only difference is whether the game bothered to
remember what she had been doing.

Three rules hold it together:

* **A skill is earned by the day, not bought.** Nobody here spends points.
  Whoever holds a post gets better at that post, at a rate that falls off, and
  at nothing else. What your house is good at is a record of what it has been
  doing, which means it is a record of how you have been playing.
* **A trait is a verdict, not a choice.** Nobody picks "merciful" off a list.
  You storm a town or you take its surrender, you pay the wages or you do not,
  and the march forms its own opinion. The opinion then costs or pays.
* **A post is a real decision with a real cost.** Everyone can only be in one
  place. A son governing Aldworth is a son not riding with the host, and the
  tax roll and the battle line both know it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C

# --------------------------------------------------------------------- skills
#: What a person can get good at. One per post, deliberately: a skill nobody
#: can hold a job in is a skill that only grows by fiat.
SKILLS: Tuple[str, ...] = ("stewardship", "trade", "tactics", "engineering",
                           "charm")

SKILL_BLURB = {
    "stewardship": "the town: mood and the tax roll",
    "trade": "the road: what a cart brings home",
    "tactics": "the field: how hard a host hits",
    "engineering": "the works: walls up and down",
    "charm": "the lords: what peace costs",
}

MAX_SKILL = 10
#: Experience for level n is n*n*STEEP. Learning by doing has to fall off or a
#: fifty-year-old steward is a god; this puts level 4 inside one chapter of
#: honest service and level 10 at about a working lifetime.
STEEP = 70.0
YOUNG_LEARNER = 1.4       # 14-17: quick
OLD_LEARNER = 0.6         # 50+: slow

# ---------------------------------------------------------------------- ages
COMES_OF_AGE = 14         # old enough to be given something to do
ELDERLY = 55              # old enough for the winter to be a question
FERTILE = (16, 42)        # a mother's years
BIRTH_ODDS = 1 / 400.0    # per day, for a married couple both at home
MANY = 6                  # living children past which the chronicle stops caring
DEATH_BASE = 0.00006      # per day per year over ELDERLY

# -------------------------------------------------------------------- traits
#: Each runs -3 (the second word) to +3 (the first). Nobody chooses these.
TRAITS: Tuple[Tuple[str, str, str], ...] = (
    ("just", "just", "grasping"),
    ("merciful", "merciful", "cruel"),
    ("open", "open-handed", "close-fisted"),
    ("bold", "bold", "cautious"),
)
TRAIT_NAMES = {k: (good, bad) for k, good, bad in TRAITS}
TRAIT_CAP = 3.0
#: How much of a father's reputation a child is born into. Not all of it --
#: the march gives an heir the benefit of a doubt it would not give his father.
INHERITED = 0.5


@dataclass(frozen=True)
class Post:
    key: str
    skill: str
    needs: str                 # "", "town" or "host"
    verb: str                  # how it reads, with {t} for the target
    blurb: str


POSTS: Dict[str, Post] = {p.key: p for p in [
    Post("steward", "stewardship", "town", "governs {t}",
         "mood and the tax roll where they sit"),
    Post("factor", "trade", "", "has the carts",
         "every cart of yours sells a little better"),
    Post("captain", "tactics", "host", "rides with {t}",
         "that host hits harder and breaks later"),
    Post("master", "engineering", "town", "has the works at {t}",
         "building and wall repair there, and your siege engines everywhere"),
    Post("envoy", "charm", "", "sits with the other lords",
         "peace is cheaper and hostility cools faster"),
]}

#: The head of the house is not posted; what he is doing decides what he learns.
HEAD_SKILL = {"hall": "stewardship", "field": "tactics", "siege": "engineering"}

FIRST_M = ("Aldred", "Osric", "Godwin", "Hereward", "Edric", "Wulfstan",
           "Leofric", "Cuthbert", "Morcar", "Siward", "Eadric", "Beorn")
FIRST_F = ("Aelfgifu", "Edith", "Godgifu", "Hild", "Emma", "Mildred",
           "Sunniva", "Aethelflaed", "Rohese", "Maud", "Alys", "Gunnhild")
STYLE = ("the Younger", "the Elder", "the Lame", "the Red", "One-Hand",
         "the Quiet", "the Grim", "Longshanks", "the Fair", "the Black")


def given_name(rng: random.Random, sex: str) -> str:
    return rng.choice(FIRST_M if sex == "m" else FIRST_F)


def _fresh_name(kin, rng: random.Random, sex: str) -> str:
    """A name nobody in the hall answers to. Two Herewards is a bug report."""
    taken = {q.name.split()[0] for q in kin.people if q.alive}
    for _ in range(12):
        name = given_name(rng, sex)
        if name not in taken:
            return name
    return given_name(rng, sex)


@dataclass
class Person:
    """One of yours, with everything they have done written on them."""
    uid: int
    name: str
    sex: str = "m"
    born: int = 0                  # game day; negative for anyone older than day 0
    alive: bool = True
    died: int = -1
    father: int = 0
    mother: int = 0
    spouse: int = 0
    married_to: str = ""           # the town a marriage tied you to, if any
    inlaw: bool = False            # married in rather than born to the house
    sworn: bool = False            # took service; not of the blood, cannot inherit
    post: str = ""                 # a POSTS key, "" for nothing, "head" for the lord
    target: str = ""               # town key or host uid, as the post needs
    xp: Dict[str, float] = field(default_factory=dict)
    traits: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------ the person
    def age(self, day: int) -> int:
        return max(0, (day - self.born) // C.DAYS_PER_YEAR)

    def grown(self, day: int) -> bool:
        return self.alive and self.age(day) >= COMES_OF_AGE

    def level(self, skill: str) -> int:
        got = self.xp.get(skill, 0.0)
        return min(MAX_SKILL, int((got / STEEP) ** 0.5))

    def to_next(self, skill: str) -> float:
        """Experience still wanted for the next level, for the skill sheet."""
        nxt = self.level(skill) + 1
        if nxt > MAX_SKILL:
            return 0.0
        return max(0.0, nxt * nxt * STEEP - self.xp.get(skill, 0.0))

    def learn(self, skill: str, amount: float, day: int) -> None:
        if not self.alive or skill not in SKILLS:
            return
        age = self.age(day)
        rate = (YOUNG_LEARNER if age < 18 else
                OLD_LEARNER if age >= 50 else 1.0)
        self.xp[skill] = self.xp.get(skill, 0.0) + amount * rate

    def trait(self, key: str) -> float:
        return self.traits.get(key, 0.0)

    def shift(self, key: str, by: float) -> None:
        if key in TRAIT_NAMES:
            self.traits[key] = max(-TRAIT_CAP, min(TRAIT_CAP,
                                                   self.trait(key) + by))

    def reputation(self) -> List[str]:
        """The words the march would use, strongest first, and only earned ones."""
        out = []
        for key, good, bad in TRAITS:
            v = self.trait(key)
            if abs(v) < 0.75:
                continue
            word = good if v > 0 else bad
            out.append((abs(v), ("very " if abs(v) >= 2.25 else "") + word))
        return [w for _, w in sorted(out, reverse=True)]

    def doing(self, name_of=None) -> str:
        if not self.alive:
            return "dead"
        if self.post == "head":
            return "the lord"
        spec = POSTS.get(self.post)
        if not spec:
            return "nothing in particular"
        t = self.target
        if spec.needs == "town" and name_of:
            t = name_of(self.target)
        elif spec.needs == "host":
            t = f"host {self.target}"
        return spec.verb.format(t=t)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["xp"] = dict(self.xp)
        d["traits"] = dict(self.traits)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Person":
        return cls(**d)


@dataclass
class Kin:
    """Your house, as people rather than as a counter."""
    people: List[Person] = field(default_factory=list)
    head: int = 0                  # uid of the lord
    next_uid: int = 1
    founded: str = ""              # the family name, if you like ("of Aldworth")
    #: Where the lord keeps his hall and which host he is with, if any. The
    #: engine owns both facts; they are copied here so that the levers below
    #: can answer "is this his own town?" without being handed the world.
    seat: str = ""
    riding: int = 0
    #: The house rolls its own dice. Sharing the world's stream would mean a
    #: birth in the hall moved the weather, the prices and every battle after
    #: it -- which is how adding this system re-rolled twelve seeds' worth of
    #: balance measurement the first time, without changing a single rule.
    seed: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed or 1)

    # -------------------------------------------------------------- lookups
    def get(self, uid: int) -> Optional[Person]:
        for p in self.people:
            if p.uid == uid:
                return p
        return None

    def by_name(self, text: str) -> Optional[Person]:
        """Whatever the player typed. First names are unique enough in a house."""
        want = text.strip().lower()
        for p in self.people:
            if p.alive and p.name.lower() == want:
                return p
        for p in self.people:
            if p.alive and p.name.lower().startswith(want):
                return p
        for p in self.people:
            if p.alive and want in p.name.lower():
                return p
        return None

    @property
    def lord(self) -> Optional[Person]:
        return self.get(self.head)

    def living(self) -> List[Person]:
        return [p for p in self.people if p.alive]

    def children_of(self, uid: int) -> List[Person]:
        return sorted((p for p in self.people
                       if p.father == uid or p.mother == uid),
                      key=lambda p: p.born)

    def add(self, name: str, sex: str = "m", born: int = 0,
            father: int = 0, mother: int = 0) -> Person:
        p = Person(uid=self.next_uid, name=name, sex=sex, born=born,
                   father=father, mother=mother)
        self.next_uid += 1
        self.people.append(p)
        return p

    # ------------------------------------------------------------ the posts
    def holder(self, post: str, target: str = "") -> Optional[Person]:
        for p in self.people:
            if p.alive and p.post == post and (not target or p.target == target):
                return p
        return None

    def level(self, post: str, target: str = "") -> int:
        """The skill of whoever holds a post, or nought if nobody does."""
        who = self.holder(post, target)
        if who is None:
            return 0
        return who.level(POSTS[post].skill)

    def at_town(self, post: str, town: str) -> int:
        """A post's level in a town, counting the lord in his own hall.

        A lord who has kept Aldworth for fifteen years is its steward whether
        or not anyone has typed the word, and a game that made you post a son
        to get any of that would be asking for paperwork rather than a choice.
        """
        best = self.level(post, town)
        lord = self.lord
        if lord is not None and lord.alive and town and town == self.seat:
            best = max(best, lord.level(POSTS[post].skill))
        return best

    def give(self, who: Person, post: str, target: str = "",
             name_of=None) -> str:
        """Post somebody. One place each, which is the whole cost of it."""
        if post and post not in POSTS:
            return f"there is no such post as {post!r}"
        if who.uid == self.head:
            return f"{who.name} is the lord; his post is his seat"
        if not post:
            was, who.post, who.target = who.post, "", ""
            return (f"{who.name} is called home"
                    if was else f"{who.name} had nothing to leave")
        spec = POSTS[post]
        if not who.alive:
            return f"{who.name} is dead"
        if who.age(self._today) < COMES_OF_AGE:
            return (f"{who.name} is {who.age(self._today)}; nobody is given "
                    f"anything before {COMES_OF_AGE}")
        if spec.needs and not target:
            return f"a {post} wants a {spec.needs}: `post {who.name} {post} <{spec.needs}>`"
        sitting = self.holder(post, target if spec.needs else "")
        if sitting is not None and sitting.uid != who.uid:
            sitting.post, sitting.target = "", ""
        who.post, who.target = post, target if spec.needs else ""
        return f"{who.name} {who.doing(name_of)}"

    # -------------------------------------------------------------- the day
    _today: int = 0

    def day(self, day: int, *, head_doing: str) -> List[str]:
        """Learning, births, coming of age, and the winters that carry people off.

        Everything here is slow on purpose. A house should change over a
        campaign and be barely visible over a week.
        """
        self._today = day
        rng = self.rng
        out: List[str] = []
        for p in list(self.people):
            if not p.alive:
                continue
            # 1. What the day taught them.
            if p.uid == self.head:
                p.learn(HEAD_SKILL.get(head_doing, "stewardship"), 1.0, day)
                p.learn("charm", 0.25, day)          # a lord is always being watched
            elif p.post in POSTS:
                p.learn(POSTS[p.post].skill, 1.0, day)
            # 2. Coming of age.
            if p.age(day) == COMES_OF_AGE and (day - p.born) % C.DAYS_PER_YEAR == 0:
                out.append(f"{p.name} is {COMES_OF_AGE} and old enough to be "
                           f"given something to do (`post`)")
            # 3. The winter.
            if p.age(day) >= ELDERLY:
                if rng.random() < DEATH_BASE * (p.age(day) - ELDERLY + 1):
                    out += self.bury(p, day, "of age")
        out += self._births(day)
        return out

    def _births(self, day: int) -> List[str]:
        rng = self.rng
        out: List[str] = []
        young = sum(1 for q in self.living() if q.age(day) < COMES_OF_AGE)
        if young >= MANY:
            return out
        for p in list(self.people):
            if not (p.alive and p.sex == "f" and p.spouse):
                continue
            mate = self.get(p.spouse)
            if mate is None or not mate.alive:
                continue
            if not FERTILE[0] <= p.age(day) <= FERTILE[1]:
                continue
            if rng.random() >= BIRTH_ODDS:
                continue
            sex = "m" if rng.random() < 0.51 else "f"
            name = _fresh_name(self, rng, sex)
            father, mother = (mate.uid, p.uid)
            child = self.add(name, sex, born=day, father=father, mother=mother)
            # A child is born into half his father's name, good or bad.
            head = self.get(father) or self.lord
            if head:
                for key, _, _ in TRAITS:
                    child.traits[key] = head.trait(key) * INHERITED
            out.append(f"*** {name} is born to {p.name} and {mate.name}. ***")
        return out

    # ---------------------------------------------------------- death and heir
    def heir(self, day: int) -> Optional[Person]:
        """Who takes the seat. Eldest grown child first, then the eldest kin.

        Sex is not a bar here, and that is a game decision rather than a
        historical one: a house with three daughters is a house, and a rule
        that dissolves it is a rule that deletes ten years of the player's
        attention over an accident of dice.
        """
        lord = self.lord
        pool = self.children_of(lord.uid) if lord else []
        grown = [p for p in pool if p.grown(day)]
        if grown:
            return grown[0]
        others = sorted((p for p in self.living()
                         if p.uid != self.head and p.grown(day)
                         and not p.inlaw and not p.sworn),
                        key=lambda p: p.born)
        if others:
            return others[0]
        young = sorted((p for p in pool if p.alive), key=lambda p: p.born)
        return young[0] if young else None

    def heirs_left(self, day: int) -> int:
        return sum(1 for p in self.living()
                   if p.uid != self.head and p.age(day) >= 1)

    def bury(self, who: Person, day: int, how: str = "") -> List[str]:
        """Mark a death, and if it was the lord's, raise whoever is next."""
        who.alive = False
        who.died = day
        who.post, who.target = "", ""
        tail = f" ({how})" if how else ""
        if who.uid != self.head:
            return [f"{who.name} is dead{tail}"]
        nxt = self.heir(day)
        if nxt is None:
            # The seat is not held by a corpse. Everything downstream asks the
            # house for its lord; if a dead one answers, a line that has ended
            # goes on collecting his stewardship and his reputation.
            self.head = 0
            return [f"*** {who.name} is dead{tail}, and there is nobody left "
                    f"to raise. ***"]
        self.head = nxt.uid
        nxt.post, nxt.target = "head", ""
        return [f"*** {who.name} is dead{tail}. {nxt.name} takes the seat"
                f"{self._reads(nxt, day)}. ***"]

    def _reads(self, p: Person, day: int) -> str:
        best = max(SKILLS, key=lambda s: p.xp.get(s, 0.0))
        if p.level(best) <= 0:
            return f", {p.age(day)} years old and untried"
        return f", {p.age(day)} years old, {best} {p.level(best)}"

    # ------------------------------------------------------------- marriage
    def marry(self, who: Person, town_key: str, town_name: str,
              day: int) -> Tuple[str, Optional[Person]]:
        """Marry one of yours into a town. A treaty with a person in it."""
        if not who.alive:
            return f"{who.name} is dead", None
        if who.spouse:
            return f"{who.name} is married already", None
        if who.age(day) < COMES_OF_AGE:
            return f"{who.name} is {who.age(day)}, and that is that", None
        rng = self.rng
        sex = "f" if who.sex == "m" else "m"
        name = _fresh_name(self, rng, sex)
        # Old enough to be a match, young enough to matter.
        age = rng.randint(16, max(17, min(34, who.age(day) + 4)))
        mate = self.add(f"{name} of {town_name}", sex,
                        born=day - age * C.DAYS_PER_YEAR)
        mate.married_to = town_key
        mate.inlaw = True
        mate.spouse, who.spouse = who.uid, mate.uid
        who.married_to = town_key
        # They arrive knowing something. A merchant's daughter can count.
        mate.xp[rng.choice(SKILLS)] = STEEP * 1.2
        return (f"{who.name} is married to {mate.name}. {town_name} is kin now.",
                mate)

    # ------------------------------------------------------------ the levers
    def mult(self, key: str, target: str = "") -> float:
        """A multiplier the engine can read the same way it reads a tech."""
        lord = self.lord
        if key == "taxes":
            grasp = -lord.trait("just") if lord else 0.0
            return 1.0 + 0.015 * self.at_town("steward", target) + 0.02 * grasp
        if key == "trade":
            return 1.0 + 0.015 * self.level("factor")
        if key == "attack":
            # The captain of that host, and the lord too if he is riding it.
            out = 1.0 + 0.02 * self.level("captain", str(target))
            if lord is not None and self.riding and str(self.riding) == str(target):
                # He is with this host, so his tactics and his nerve both count.
                out += 0.02 * lord.level("tactics") + 0.03 * lord.trait("bold")
            return out
        if key == "build":
            return 1.0 + 0.03 * self.at_town("master", target)
        if key == "siege":
            best = max([p.level("engineering") for p in self.living()
                        if p.post == "master"]
                       + ([lord.level("engineering")] if lord else [0]))
            return 1.0 + 0.025 * best
        if key == "truce_cost":
            return max(0.5, 1.0 - 0.025 * self.level("envoy"))
        if key == "wages":
            return 1.0 + (0.02 * lord.trait("open") if lord else 0.0)
        return 1.0

    def bonus(self, key: str, target: str = "") -> float:
        lord = self.lord
        if key == "mood":
            out = 0.5 * self.at_town("steward", target)
            if lord:
                out += 1.0 * lord.trait("just") + 0.8 * lord.trait("open")
            return out
        if key == "cooling":
            # How fast a foreign lord forgets he was angry with you.
            out = 0.15 * self.level("envoy")
            if lord:
                out += 0.10 * lord.trait("merciful")
            return out
        if key == "defence":
            return 2.0 * -lord.trait("bold") if lord else 0.0
        return 0.0

    def did(self, key: str, by: float = 1.0) -> None:
        """The march forms an opinion of the lord. Nobody asked it to."""
        lord = self.lord
        if lord is not None:
            lord.shift(key, by)

    def teach(self, skill: str, amount: float, day: int,
              post: str = "", target: str = "") -> None:
        """A deed, rather than a day, taught somebody something."""
        who = self.holder(post, target) if post else None
        if who is None:
            who = self.lord
        if who is not None:
            who.learn(skill, amount, day)

    # ------------------------------------------------------------ save/load
    def to_dict(self) -> dict:
        return {"people": [p.to_dict() for p in self.people],
                "head": self.head, "next_uid": self.next_uid,
                "founded": self.founded, "seat": self.seat,
                "riding": self.riding, "seed": self.seed,
                "rng": list(self.rng.getstate())}

    @classmethod
    def from_dict(cls, d: dict) -> "Kin":
        k = cls(people=[Person.from_dict(p) for p in d.get("people", [])],
                head=d.get("head", 0), next_uid=d.get("next_uid", 1),
                founded=d.get("founded", ""), seat=d.get("seat", ""),
                riding=d.get("riding", 0), seed=d.get("seed", 0))
        raw = d.get("rng")
        if raw:
            k.rng.setstate((raw[0], tuple(raw[1]), raw[2]))
        return k


def found(rng: random.Random, seat: str = "",
          lord_name: Optional[str] = None) -> Kin:
    """A house as it stands on the first morning: a lord, a wife, children.

    The children are the point of starting this way. A campaign is twelve
    years; a child born in chapter one is twelve at the end of it and has done
    nothing. Starting with a boy of sixteen and a girl of eleven means the
    house actually turns over inside a game somebody plays.
    """
    k = Kin(founded=seat, seed=rng.randrange(1, 2 ** 31))
    year = C.DAYS_PER_YEAR
    name = lord_name or f"{rng.choice(FIRST_M)} {rng.choice(STYLE)}"
    lord = k.add(name, "m", born=-rng.randint(33, 39) * year)
    lord.post = "head"
    k.head = lord.uid
    lord.xp["stewardship"] = STEEP * 4.2        # he has held a hall before
    lord.xp["tactics"] = STEEP * 1.6           # and been out with the levy
    wife = k.add(_fresh_name(k, rng, "f"), "f",
                 born=-rng.randint(28, 34) * year)
    wife.spouse, lord.spouse = lord.uid, wife.uid
    ages = [rng.randint(15, 17), rng.randint(9, 13), rng.randint(2, 6)]
    for i, age in enumerate(ages):
        sex = "m" if (i == 0 or rng.random() < 0.5) else "f"
        child = k.add(_fresh_name(k, rng, sex), sex, born=-age * year,
                      father=lord.uid, mother=wife.uid)
        child.xp[rng.choice(SKILLS)] = STEEP * 0.4   # whatever they took to
    return k
