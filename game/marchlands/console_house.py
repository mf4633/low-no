"""The house: the lord and his kin, posts, marriages, missions and feats.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import List

from . import config as C
from . import kin as kinly
from . import lord as lordly
from . import render as ink


class HouseMixin:
    """The console's house. Mixed into Console; see cli.py."""

    def cmd_lord(self, args: List[str]) -> None:
        """Your lord: where he is, what he is worth there, and the risk of it."""
        g = self.game
        if args and args[0].lower() == "ransom":
            return self.say("  " + g.ransom_lord())
        if args and args[0].lower() in ("home", "recall"):
            return self.say("  " + g.lead(0))
        if args:
            return self.say("  " + g.lead(int(args[0])))
        self.say(ink.head(g.lord.name.upper(), g.lord.standing(self._name)))
        if g.lord.at_home:
            worth = (f"+{C.LORD_MOOD:.0f} mood, "
                     f"+{lordly.HOME_DEFENCE:.0f} on the wall")
            self.say("  in his hall   " + ink.c(worth, ink.LEAF))
        elif g.lord.in_the_field:
            self.say("  in the field  "
                     + ink.c(f"+{lordly.FIELD_ATTACK * 100:.0f}% to the host he "
                             f"rides with -- and he is where the arrows are",
                             ink.AMBER))
        elif g.lord.captured:
            self.say("  " + ink.c(f"ransom {g.lord.ransom:,.0f}c -- "
                                  f"`lord ransom` pays it", ink.BLOOD))
        elif not g.lord.alive:
            self.say("  " + ink.c(f"{g.lord.heirs} of the line left", ink.BLOOD))
        best = sorted(kinly.SKILLS, key=lambda sk: -g.kin.lord.xp.get(sk, 0.0)) \
            if g.kin.lord else []
        if best:
            him = g.kin.lord
            self.say("  he is         " + ", ".join(
                f"{sk} {him.level(sk)}" for sk in best[:3] if him.level(sk) > 0)
                or ink.c("untried at everything so far", ink.DIM))
            words = him.reputation()
            if words:
                self.say("  they call him " + ink.c(", ".join(words), ink.BONE))
            heir = g.kin.heir(g.day)
            if heir is not None:
                self.say(f"  after him     {heir.name}, {heir.age(g.day)}, "
                         + ink.c(heir.doing(self._name), ink.DIM))
        self.say("", ink.c("  lord <host> sends him out, lord home brings him back. "
                           "`kin` is the rest of them.", ink.DIM))

    # ------------------------------------------------------------- the house
    def _kin_word(self, p, lord) -> str:
        """How a person stands to the lord, in one word a reader already has."""
        if lord is None or p.uid == lord.uid:
            return "the lord"
        if p.uid == lord.spouse:
            return "his wife" if p.sex == "f" else "her husband"
        if lord.uid in (p.father, p.mother):
            return "his son" if p.sex == "m" else "his daughter"
        if p.uid in (lord.father, lord.mother):
            return "his father" if p.sex == "m" else "his mother"
        if p.inlaw:
            return "married in"
        if p.father and p.father == lord.father:
            return "his brother" if p.sex == "m" else "his sister"
        grandparent = {c.uid for c in self.game.kin.children_of(lord.uid)}
        if p.father in grandparent or p.mother in grandparent:
            return "his grandson" if p.sex == "m" else "his granddaughter"
        return "of the line"

    def cmd_kin(self, args: List[str]) -> None:
        """Your house: who they are, what they are doing, what it made them."""
        g = self.game
        k = g.kin
        lord = k.lord
        if lord is None:
            return self.say(ink.head("THE HOUSE"),
                            ink.c("  There is nobody left of the line.", ink.BLOOD))
        if args:
            return self._one_of_the_kin(args[0])
        living = sorted(k.living(), key=lambda p: (p.uid != k.head, p.born))
        self.say(ink.head(f"THE HOUSE OF {lord.name.upper()}",
                          f"{len(living)} of the line"))
        self.say(ink.c("  who                  age  standing      "
                       "doing                      best at", ink.DIM))
        for p in living:
            best = max(kinly.SKILLS, key=lambda sk: p.xp.get(sk, 0.0))
            skill = (f"{best} {p.level(best)}" if p.level(best) > 0
                     else ink.c("--", ink.FAINT))
            doing = p.doing(self._name)
            colour = (ink.GOLD if p.uid == k.head
                      else ink.PARCH if p.post else ink.DIM)
            self.say(f"  {ink.c(ink.pad(p.name, 20), colour)} "
                     f"{p.age(g.day):>3}  "
                     f"{ink.c(ink.pad(self._kin_word(p, lord), 13), ink.DIM)} "
                     f"{ink.pad(doing, 26)} {skill}")
        for p in living:
            if p.uid in k.idle:
                self.say(ink.c(f"  {p.name}: {k.idle[p.uid]}", ink.AMBER))
        words = lord.reputation()
        self.say("", "  they call him " + (ink.c(", ".join(words), ink.BONE)
                                           if words else
                                           ink.c("nothing in particular yet", ink.DIM)))
        open_posts = [key for key in kinly.POSTS if not k.holder(key)]
        if open_posts:
            self.say(ink.c(f"  unfilled      {', '.join(sorted(open_posts))}",
                           ink.AMBER))
        self.say(ink.c("  `kin <name>` for one of them · `post <name> <post> "
                       "[where]` · `marry <name> <town>`", ink.DIM))

    def _one_of_the_kin(self, name: str) -> None:
        g = self.game
        p = g.kin.by_name(name)
        if p is None:
            return self.err(f"nobody of yours called {name!r}")
        self.say(ink.head(p.name.upper(),
                          f"{p.age(g.day)} years old, {p.doing(self._name)}"))
        self.say(ink.c("  skill        how far it has got      what it is "
                       "worth            to next", ink.DIM))
        for skill in kinly.SKILLS:
            level = p.level(skill)
            want = p.to_next(skill)
            tail = (f"{want:>7,.0f}" if want
                    else ink.c("    top", ink.GOLD))
            self.say(f"  {ink.pad(skill, 13)}{ink.bar(level, kinly.MAX_SKILL, 12)}"
                     f" {level:>2}  "
                     f"{ink.c(ink.pad(kinly.SKILL_BLURB[skill], 34), ink.DIM)}"
                     f"{tail}")
        marks = []
        for key, kind, unkind in kinly.TRAITS:
            v = p.trait(key)
            if abs(v) < 0.35:
                continue
            marks.append(ink.c(f"{kind if v > 0 else unkind} {abs(v):.1f}",
                               ink.LEAF if v > 0 else ink.RUST))
        if marks:
            self.say("", "  reputation    " + "  ".join(marks))
        kids = [c for c in g.kin.children_of(p.uid) if c.alive]
        if kids:
            self.say("  children      " + ", ".join(
                f"{c.name} ({c.age(g.day)})" for c in kids))
        if p.spouse:
            mate = g.kin.get(p.spouse)
            if mate is not None:
                gone = " he is dead" if mate.sex == "m" else " she is dead"
                self.say(f"  married       {mate.name}"
                         + (" --" + gone if not mate.alive else ""))

    def cmd_post(self, args: List[str]) -> None:
        """Give one of yours a job. Everyone can only be in one place."""
        g = self.game
        if not args:
            self.say(ink.head("POSTS", "one person each"))
            for key, spec in kinly.POSTS.items():
                who = g.kin.holder(key)
                sits = (ink.c(f"{who.name} ({spec.skill} "
                              f"{who.level(spec.skill)})", ink.PARCH)
                        if who else ink.c("nobody", ink.AMBER))
                self.say(f"  {ink.c(ink.pad(key, 9), ink.GOLD)}"
                         f"{ink.pad(sits, 30)} {ink.c(spec.blurb, ink.DIM)}")
            return self.say("", ink.c("  post <name> <post> [town|host]  ·  "
                                      "post <name> none calls them home", ink.DIM))
        who = args[0]
        job = args[1].lower() if len(args) > 1 else ""
        if job in ("none", "home", "-"):
            job = ""
        target = args[2] if len(args) > 2 else ""
        self.say("  " + g.post(who, job, target))

    def cmd_missions(self, args: List[str]) -> None:
        """Your house's own path through the game, and what it pays."""
        from . import missions as mi
        g = self.game
        done = g.missions.to_dict()
        whole = mi.tree(g.house)
        self.say(ink.head("THE ROLL", f"{len(done)} of {len(whole)} · "
                                      f"house {g.house}"))
        openk = {m.key for m in g.missions.open(g.house)}
        for m in whole:
            day = done.get(m.key)
            if day is not None:
                state, tone = "done", ink.LEAF
            elif m.key in openk:
                state, tone = "open", ink.GOLD
            else:
                state, tone = "after " + ", ".join(m.after), ink.DIM
            self.say(f"  {ink.c(ink.pad(m.name, 26), tone)}{ink.c(state, tone)}"
                     + (ink.c(f"  day {day}", ink.DIM) if day is not None else ""))
            self.say(f"      {ink.c(m.asks, ink.DIM)}")
            if day is None:
                self.say(f"      {ink.c('costs you ' + m.costs, ink.AMBER)}")
                self.say(f"      {ink.c('pays ' + m.reward_words(), ink.LEAF)}")
        self.say("", ink.c("  the trunk is every lord's; the rest is yours "
                           "alone", ink.DIM))

    def cmd_feats(self, args: List[str]) -> None:
        """Things worth having done, and which of them you have."""
        from . import feats as fe
        g = self.game
        done = g.feats.to_dict()
        self.say(ink.head("FEATS", f"{len(done)} of {len(fe.FEATS)}"))
        for key, feat in fe.FEATS.items():
            day = done.get(key)
            mark = ink.c("done", ink.LEAF) if day is not None else ink.c(
                "·" * feat.hard, ink.DIM)
            self.say(f"  {ink.c(ink.pad(feat.name, 26), ink.GOLD if day is None else ink.LEAF)}"
                     f"{ink.pad(mark, 12)}"
                     + (ink.c(f"day {day}", ink.DIM) if day is not None else ""))
            self.say(f"      {ink.c(feat.blurb, ink.DIM)}")
        self.say("", ink.c("  the dots are how stiff it is; a goal says what "
                           "the game is for, these say what it can do", ink.DIM))

    def cmd_estates(self, args: List[str]) -> None:
        """The three who run your march, and what they want from you."""
        from . import estates as est
        g = self.game
        e = g.estates
        if args and args[0].lower() in ("grant", "give"):
            if len(args) < 2:
                return self.say("  grant <privilege>; `estates` lists them")
            return self.say("  " + e.grant(args[1].lower(), g.day))
        if args and args[0].lower() in ("revoke", "take"):
            if len(args) < 2:
                return self.say("  revoke <privilege>")
            return self.say("  " + e.revoke(args[1].lower(), g.day))
        self.say(ink.head("THE ESTATES", "who you govern with"))
        for key, spec in est.ESTATES.items():
            st = e.by_key[key]
            worth = e.mult(spec.gives)
            tone = (ink.LEAF if st.loyalty >= 60 else
                    ink.AMBER if st.loyalty >= est.SULKY else ink.BLOOD)
            self.say(f"  {ink.c(ink.pad(spec.name, 14), ink.GOLD)}"
                     f"{ink.c(f'{st.loyalty:5.0f}', tone)}   "
                     f"{spec.gives} {ink.c(f'x{worth:.2f}', tone)}")
            self.say(f"      {ink.c(spec.blurb, ink.DIM)}")
            for what, by in e.why(key, g.day)[:3]:
                mark = ink.LEAF if by > 0 else ink.BLOOD
                self.say(f"      {ink.c(f'{by:+6.1f}', mark)}  "
                         f"{ink.c(what, ink.DIM)}")
        self.say("")
        self.say(ink.head("PRIVILEGES", "what they will take in exchange"))
        for key, p in est.PRIVILEGES.items():
            held = e.granted(key)
            self.say(f"  {ink.c(ink.pad(key, 11), ink.GOLD if not held else ink.LEAF)}"
                     f"{ink.pad(est.ESTATES[p.estate].name, 14)}"
                     f"{ink.c('granted' if held else '', ink.LEAF)}")
            self.say(f"      {ink.c(p.blurb, ink.DIM)}")
            self.say(f"      {ink.c('costs you ' + p.cost, ink.AMBER)}")
        self.say("", ink.c("  estates grant <name>  ·  estates revoke <name>",
                           ink.DIM))

    def cmd_marry(self, args: List[str]) -> None:
        """Marry one of yours into a neighbouring house."""
        g = self.game
        if not args:
            self.say(ink.head("MATCHES", "a peace that does not run out"))
            free = [p for p in g.kin.living()
                    if not p.spouse and p.age(g.day) >= kinly.COMES_OF_AGE]
            self.say("  of yours      " + (", ".join(p.name for p in free)
                                           if free else "nobody unmarried"))
            for key, t in sorted(g.world.towns.items(),
                                 key=lambda kv: -kv[1].ill_will)[:6]:
                if t.mine:
                    continue
                tied = any(p.alive and p.married_to == key for p in g.kin.people)
                note = (ink.c("kin already", ink.LEAF) if tied
                        else f"{g.dowry(key):,.0f}c")
                self.say(f"  {ink.pad(t.name, 13)} {ink.pad(t.lord, 24)}"
                         f" ill-will {t.ill_will:>3.0f}   {note}")
            return self.say("", ink.c("  marry <name> <town>", ink.DIM))
        if len(args) < 2:
            return self.err("marry <name> <town>")
        self.say("  " + g.wed(args[0], self._node(args[1])))

    def cmd_relics(self, args: List[str]) -> None:
        """Where the bones are, and whose they are today."""
        g = self.game
        self.say(ink.head("THE RELICS OF THE MARCH",
                          f"you hold {g.relics_held()} of {len(g.world.shrines)}"))
        for key, sh in g.world.shrines.items():
            if not sh.holder:
                dist = min((g.world.distance(k, key)
                            for k in g.world.settlements), default=0.0)
                where = ink.c(f"still there, {dist:.0f} leagues off", ink.LEAF)
            elif sh.holder == "player":
                where = ink.c("yours", ink.GOLD)
            else:
                where = ink.c(f"held by {g.world.node_name(sh.holder)}", ink.BLOOD)
            self.say(f"  {sh.name:<26} {sh.relic:<30} {where}")
            self.say(f"     {ink.c(sh.blurb, ink.DIM)}")
        if g.relic_income():
            self.say("", f"  offerings  {ink.coin(g.relic_income())} a day"
                         + ink.c("  (a cathedral is worth half again)", ink.DIM))
            fed = g.ledger.offerings - g.relic_income()
            self.say(f"  pilgrims   {g.relics_held() * g.PILGRIMS} a day want a "
                     f"loaf and a cup at your market"
                     + (f"; yesterday they spent {ink.coin(fed)}" if fed > 0.5
                        else ink.c(" -- and found nothing to buy", ink.AMBER)))
        if "reliquary" in g.goals.paths:
            terms = (f"Hold {g.goals.relics} of them for {g.goals.relic_days} "
                     f"days and the march is yours ({g.relic_days} so far).")
            self.say("  " + ink.c(terms, ink.DIM))
        self.say("", ink.c("  march <host> <shrine> and stand there "
                           f"{C.RELIC_DAYS} days to lift one.", ink.DIM))
