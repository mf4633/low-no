"""The house: the lord and his line, what they study, where they are posted,
whom they marry, and the estates and missions that are theirs rather than the map's.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.
"""

from __future__ import annotations

from typing import List

from . import config as C
from .buildings import building
from .chronicle import MOMENTOUS
from .goods import good
from . import lord as manly
from .kin import POSTS
from .military import BESIEGING, GARRISON
from .tech import AGES, TECHS


class HouseMixin:
    """GameState's house. Mixed into GameState; see engine.py."""

    # ------------------------------------------------------- ages and techs
    def _study(self) -> List[str]:
        msgs: List[str] = []
        p = self.progress
        if p.advancing:
            p.advancing -= 1
            if p.advancing <= 0:
                p.age += 1
                msgs.append(self.note(f"*** The {AGES[p.age].name} begins ***",
                                      MOMENTOUS))
        if p.researching:
            p.research_left -= (p.mult("research_speed") * self._scholars()
                                * self.estates.mult("research"))
            if p.research_left <= 0:
                p.researched.add(p.researching)
                msgs.append(f"Learned: {TECHS[p.researching].name}")
                p.researching = ""
        return msgs

    def _scholars(self) -> float:
        """Guildhalls do the studying; without one, nothing is learned."""
        halls = sum(s.effect("research") for s in self.world.settlements.values())
        return min(2.0, halls) if halls else 0.0

    def begin_age(self) -> str:
        p = self.progress
        nxt = p.next_age()
        if p.advancing:
            return f"already climbing to the {AGES[p.age + 1].name} ({p.advancing}d)"
        if not nxt:
            return "there is no age beyond this one"
        home = self.home()
        for key in nxt.needs:
            if not any(s.count(key) for s in self.world.settlements.values()):
                return f"the {nxt.name} needs {building(key).name} first"
        coin = nxt.cost.get("coin", 0.0)
        if self.treasury < coin:
            return f"the {nxt.name} costs {coin:,.0f}c; you have {self.treasury:,.0f}c"
        short = [(k, q) for k, q in nxt.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{home.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short))
        self.treasury -= coin
        self._outlay += coin
        for k, q in nxt.cost.items():
            if k != "coin":
                home.market.take(k, q)
        p.advancing = nxt.days
        return f"Work begins toward the {nxt.name} -- {nxt.days} days"

    def research(self, key: str) -> str:
        p = self.progress
        if key not in TECHS:
            return f"no such craft as {key!r}"
        t = TECHS[key]
        if key in p.researched:
            return f"{t.name} is already known"
        if p.researching:
            return f"the guildhall is busy with {TECHS[p.researching].name}"
        if t.age > p.age:
            return f"{t.name} belongs to the {AGES[t.age].name}"
        if t.prereq and t.prereq not in p.researched:
            return f"{t.name} follows {TECHS[t.prereq].name}"
        if not self._scholars():
            return "you have no guildhall to study in"
        home = self.home()
        coin = t.cost.get("coin", 0.0)
        if self.treasury < coin:
            return f"{t.name} costs {coin:,.0f}c"
        short = [(k, q) for k, q in t.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{home.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short))
        self.treasury -= coin
        self._outlay += coin
        for k, q in t.cost.items():
            if k != "coin":
                home.market.take(k, q)
        p.researching = key
        p.research_left = float(t.days)
        return f"The guildhall takes up {t.name} -- about {t.days} days"

    def lead(self, uid: int) -> str:
        """Send your lord out with a host, for what that is worth both ways."""
        if self.lord.gone:
            return f"{self.lord.name} is {self.lord.standing(self.world.node_name)}"
        if uid == 0:
            self.lord.riding = 0
            return f"{self.lord.name} returns to his hall"
        a = self.army(uid)
        if not a or a.owner != "player":
            return f"no host of yours numbered {uid}"
        if self.lord.wounded > 0:
            return self.lord.cannot_ride()
        self.lord.riding = uid
        return (f"{self.lord.name} rides with {a.name}. The men will fight "
                f"harder and stand longer, and he is where the arrows are.")

    def ransom_lord(self) -> str:
        if not self.lord.captured:
            return f"{self.lord.name} is {self.lord.standing(self.world.node_name)}"
        if self.treasury < self.lord.ransom:
            return (f"They want {self.lord.ransom:,.0f}c for {self.lord.name} "
                    f"and you have {self.treasury:,.0f}c")
        self.treasury -= self.lord.ransom
        self.ledger.war += self.lord.ransom
        self.lord.captured = False
        self.lord.ransom = 0.0
        return f"{self.lord.name} is bought back and rides in at the gate"

    def _lord_fell(self) -> List[str]:
        """His host broke around him. Both halves of the man have to hear it.

        `Lord` holds where he is standing; `Kin` holds who he was and who has
        been training behind him. Keeping the two in step in one place is the
        only reason a succession can say `Osric takes the seat, 22 years old,
        trade 4` instead of picking a name out of a hat -- which is what the
        old call to `name_for` did, and it is why the heir was nobody.
        """
        self.lord.ransom = min(9000.0, 900.0 + 0.06 * self.net_worth())
        heir = self.kin.heir(self.day)
        msgs = self.lord.falls(self.rng, heir.name if heir else self.lord.name)
        if not self.lord.alive:
            who = self.kin.lord
            if who is not None:
                msgs += [self.note(ln, MOMENTOUS)
                         for ln in self.kin.bury(who, self.day)]
            for st in self.world.settlements.values():
                st.popularity = max(0.0, st.popularity - manly.MOURNING)
        return msgs

    def _lord_day(self) -> List[str]:
        msgs = self.lord.day()
        if self.lord.riding and self.army(self.lord.riding) is None:
            self.lord.riding = 0        # the host he rode with is gone
        seat = self.lord.seat or next(iter(self.world.settlements), "")
        self.kin.seat, self.kin.riding = seat, self.lord.riding

        # What the head of the house did today is what the head of the house
        # learned today. A lord who never leaves the hall is a good steward
        # and an unproven soldier, and the campaign will say so.
        riding = self.army(self.lord.riding) if self.lord.riding else None
        # A host in garrison is a host at home: riding with it is the hall.
        if riding is not None and riding.state == GARRISON:
            riding = None
        doing = ("siege" if riding is not None and riding.state == BESIEGING
                 else "field" if riding is not None else "hall")
        afield = {str(a.uid) for a in self.armies
                  if a.owner == "player" and a.state != GARRISON}
        before = self.kin.head
        # A birth, a death and a succession are the three things a chronicle is
        # for. The house says them; this is where they get written down.
        for line in self.kin.day(self.day, head_doing=doing, afield=afield):
            msgs.append(self.note(line, MOMENTOUS) if line.startswith("***")
                        else line)
        if self.kin.head != before and self.lord.alive:
            # He died in his bed. The hall is as empty as if he had not.
            self.lord.alive = False
            self.lord.riding = 0
            self.lord.heir_days = manly.SUCCESSION_DAYS
            for st in self.world.settlements.values():
                st.popularity = max(0.0, st.popularity - manly.MOURNING)
        if self.kin.lord is not None:
            self.lord.name = self.kin.lord.name
        self.lord.heirs = self.kin.heirs_left(self.day)
        msgs += self._reputation_day()

        for key, st in self.world.settlements.items():
            st.lord_home = self.lord.at_home and key == seat
            st.lord_lost = self.lord.gone and key == seat
            st.steward_mood = self.kin.bonus("mood", key)
        return msgs

    def _reputation_day(self) -> List[str]:
        """The march's opinion of your lord, formed a little at a time.

        Nobody picks a trait off a list. You hold the tax low for two years and
        the word gets about; you keep him behind his own wall through a war and
        that gets about too. A day moves any of these by about a four-hundredth
        of the way to its extreme, which is the point: a reputation you can
        change in a week is not a reputation.
        """
        home = self.home()
        if home is not None:
            # The bands run -2 (largesse) to 4 (cruel), so the count of them is
            # not the worst of them. Normalising against the wrong one made
            # "none" read as half-way to cruel.
            tax = home.tax_level / max(C.TAX_LEVELS)
            self.kin.did("just", 0.008 * (0.45 - tax))
            if home.report.unpaid:
                self.kin.did("open", -0.02)
        at_war = any(a.owner != "player" for a in self.armies)
        if self.lord.in_the_field:
            self.kin.did("bold", 0.006)
        elif at_war and self.lord.at_home:
            self.kin.did("bold", -0.003)
        return []

    def _estates_day(self) -> List[str]:
        """What the three of them made of today.

        Every grievance here is a lever the player pulled, read off the state
        it left rather than hooked onto the command that pulled it -- so a tax
        rise set by a script, by the console or by a button all register, and
        none of them can be forgotten about when a fourth way of setting it
        is added.
        """
        e = self.estates
        seats = list(self.world.settlements.values())
        if not seats:
            return []
        # Tax. The knights pay it on their manors and the guilds on their
        # stalls; both notice, and the knights notice harder.
        tax = sum(s.tax_level for s in seats) / len(seats)
        e.note("knights", "the tax you take from their manors",
               (2.0 - tax) * 7.0, self.day)
        e.note("guilds", "the tax on the market", (2.0 - tax) * 5.0, self.day)
        # The assize is a price cap, which is a guild grievance by
        # construction: the economics layer already had the lever and simply
        # had nobody on the other end of it.
        capped = len(getattr(self.economy, "assize", {}) or {})
        if capped:
            e.note("guilds", f"you hold the price of {capped} good(s) down",
                   -9.0 * capped, self.day)
        elif not e.granted("charter"):
            e.note("guilds", "prices are theirs to set", 4.0, self.day)
        # Coin struck out of nothing is the chapter's oldest complaint.
        minted = float(getattr(self.economy, "minted", 0.0) or 0.0)
        if minted > 0:
            e.note("chapter", "you have struck coin out of nothing",
                   -min(22.0, minted / 900.0), self.day)
        # Chapels and minsters, which is the thing they actually want built.
        faith = sum(s.coverage("faith_reach") for s in seats) / len(seats)
        e.note("chapter", "the souls in your towns have somewhere to pray",
               -6.0 + 20.0 * faith, self.day)
        # Knights want a war, and grow restless without one. A greater levy
        # granted and then left idle is worse: you armed them for nothing.
        at_war = any(a.owner != "player" for a in self.armies)
        idle = self.day - self._last_war_day
        if at_war:
            self._last_war_day = self.day
            e.note("knights", "there is a war on, and they are in it", 10.0,
                   self.day)
        elif idle > 240:
            e.note("knights", "a long peace, and nothing to take",
                   -8.0 - (4.0 if e.granted("levy") else 0.0), self.day)
        return e.day(self.day)

    def _missions_day(self, standing, led=None) -> List[str]:
        """Anything finished today, and the reward actually paid.

        Paid here rather than announced here: a reward that is a line of text
        is a reward nobody notices was never given.
        """
        said: List[str] = []
        for mission, words in self.missions.check(self.house, standing):
            said.append(f"*** {mission.name} -- {mission.asks} ***")
            said.append("  " + (self._pay(mission, led) or words))
        return said

    # ----------------------------------------------------------- the house
    def post(self, who: str, post: str = "", target: str = "") -> str:
        """Give one of yours a job, or call them home.

        The cost of a post is not coin, it is the person: everybody can only
        be in one place, so a son governing Aldworth is a son not riding with
        the host, and both the tax roll and the battle line know it.
        """
        person = self.kin.by_name(who)
        if person is None:
            return f"nobody of yours called {who!r}"
        spec = POSTS.get(post)
        if post and spec is None:
            return (f"there is no post called {post!r}; "
                    f"try {', '.join(sorted(POSTS))}")
        if spec and spec.needs == "town":
            key = self._resolve_town(target)
            if key is None:
                return f"{target!r} is no settlement of yours"
            target = key
        if spec and spec.needs == "host":
            if not target.isdigit() or self.army(int(target)) is None:
                return f"no host {target!r} of yours to ride with"
            a = self.army(int(target))
            if a.owner != "player":
                return "that host is not yours"
        return self.kin.give(person, post, target,
                             name_of=self.world.node_name)

    def dowry(self, town_key: str) -> float:
        """What a house of that standing expects to see before it says yes."""
        town = self.world.towns.get(town_key)
        if town is None:
            return 0.0
        return C.DOWRY_BASE * (0.7 + town.muster) * town.prosperity

    def wed(self, who: str, town_key: str) -> str:
        """Marry one of yours into a neighbouring house.

        This is the cheapest lasting peace in the game and the only one that
        cannot be un-bought: a truce runs out, a gift is forgotten as the
        favour decays, and a daughter married into Ostmark is still married
        into Ostmark in the fifth chapter. What it costs is a dowry now and a
        person you might have posted somewhere.
        """
        person = self.kin.by_name(who)
        if person is None:
            return f"nobody of yours called {who!r}"
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to treat with"
        if town.mine:
            return f"{town.name} is sworn to you already; there is nothing to buy"
        if any(p.alive and p.married_to == town_key for p in self.kin.people):
            return f"your house is tied to {town.name} already"
        cost = self.dowry(town_key)
        if self.treasury < cost:
            return (f"{town.lord} of {town.name} expects {cost:,.0f}c with the "
                    f"match; you have {self.treasury:,.0f}c")
        said, mate = self.kin.marry(person, town_key, town.name, self.day)
        if mate is None:
            return said
        self.treasury -= cost
        self._outlay += cost
        self.court.write(town_key, "marriage", C.MARRIAGE_FAVOUR, self.day)
        # And a claim, which is the other half of what a marriage is for. If
        # that house ends without an heir, what it holds can come to yours
        # without a single man in the field -- see `_succession_abroad`.
        self.court.claims[town_key] = self.day
        # The marriage is in the book above; taking it off the timer too
        # counted it twice. The truce is the part that is not goodwill.
        town.truce_days = max(town.truce_days, C.MARRIAGE_TRUCE)
        self._reread(town_key)
        self.kin.did("open", 0.15)
        self.kin.teach("charm", 20.0, self.day, post="envoy")
        return self.note(f"{said} {cost:,.0f}c goes with her, and "
                         f"{town.lord}'s ill-will falls to {town.ill_will:.0f}.",
                         MOMENTOUS)
