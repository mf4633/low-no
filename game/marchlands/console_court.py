"""The court: the other lords, letters, alliances, war and the league.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import List, Optional

from . import config as C
from .engine import _ordinal
from .goods import good
from . import league as lg
from . import chancery
from . import culture as cultures
from . import lords as lordkind
from . import render as ink
from .military import describe, host_strength
from .console_common import _short


class CourtMixin:
    """The console's court. Mixed into Console; see cli.py."""

    # ------------------------------------------------------------- the court
    def _standing_colour(self, view: float) -> int:
        if view >= chancery.WARM:
            return ink.LEAF
        if view >= 0:
            return ink.PARCH
        if view > chancery.COLD:
            return ink.AMBER
        return ink.BLOOD

    def cmd_court(self, args: List[str]) -> None:
        """Who thinks what of you, and exactly why."""
        g = self.game
        if args and args[0].lower() in ("buy", "buyoff", "letter"):
            return self.say("  " + g.buy_off_coalition())
        c = g.court
        if args:
            key = self._resolve_town(args[0])
            if key is None:
                return self.err(f"no town called {args[0]!r}")
            return self._one_court(key)
        signed = len(c.coalition)
        self.say(ink.head("THE COURT",
                          f"{signed} names on the letter" if signed
                          else "no letter against you"))
        for key, t in g.world.towns.items():
            if t.mine:
                continue
            view = c.opinion(key, g.day)
            marks = []
            if key in c.allies:
                marks.append(ink.c("allied", ink.LEAF))
            if key in c.coalition:
                marks.append(ink.c("signed", ink.BLOOD))
            if key in c.claims:
                marks.append(ink.c("claim", ink.GOLD))
            if t.truce_days > 0:
                marks.append(ink.c(f"treaty {t.truce_days}d", ink.DIM))
            toll = g.world.tariff_for(key, None)
            self.say(f"  {ink.c(ink.pad(t.name, 13), ink.PARCH)}"
                     + ink.c(f"{view:>+5.0f}  ", self._standing_colour(view))
                     + ink.c(ink.pad(chancery.temper(view), 11), ink.DIM)
                     + ink.c(ink.pad(f"toll {toll * 100:.1f}%", 11),
                             ink.LEAF if toll < 0.05 else ink.AMBER)
                     + "  ".join(marks))
            top = c.reasons(key, g.day)[:2]
            for label, value, decay in top:
                self.say("      " + ink.c(ink.pad(label, 44), ink.DIM)
                         + ink.c(f"{value:>+5.0f}", self._standing_colour(value))
                         + ink.c("  forever" if not decay
                                 else f"  {abs(value) / decay:,.0f} days left",
                                 ink.FAINT))
        self._letter()
        self.say("", ink.c("  The toll is what his customs post charges *you*: "
                           "a lord's opinion is a tax rate, which is\n  why a "
                           "gift is an investment and not only insurance. "
                           "`court <town>` for one in full.", ink.DIM))

    def _letter(self) -> None:
        """The coalition, and the three ways out of it."""
        g = self.game
        c = g.court
        if not c.coalition:
            near = [(c.offence(k, g.day), k) for k, t in g.world.towns.items()
                    if not t.mine and c.offence(k, g.day) > chancery.COALITION_BAR * 0.6]
            if len(near) >= chancery.COALITION_NAMES:
                near.sort(reverse=True)
                self.say("", ink.c(f"  {len(near)} lords are within sight of "
                                   f"signing against you -- "
                                   f"{chancery.COALITION_BAR:.0f} of offence "
                                   f"puts a name on the letter:", ink.AMBER))
                self.say("  " + ink.c(", ".join(
                    f"{g.world.node_name(k)} {v:.0f}" for v, k in near[:5]),
                    ink.DIM))
                self.say("  " + ink.c("Nothing has to be paid for this. It "
                                      "wears off on its own if you stop "
                                      "giving them reasons.", ink.DIM))
            return
        names = ", ".join(g.world.node_name(k) for k in c.coalition)
        self.say("", ink.c("  THE LETTER AGAINST YOU", ink.BLOOD))
        self.say(f"  {names} have signed. None of them will take a truce "
                 f"alone.")
        worst = sorted(((c.offence(k, g.day), k) for k in c.coalition),
                       reverse=True)
        self.say("  " + ink.c("it lapses under "
                              f"{chancery.COALITION_BAR:.0f} each:  ", ink.DIM)
                 + ", ".join(f"{g.world.node_name(k)} {v:.0f}"
                             for v, k in worst))
        self.say("  " + ink.c("three ways out:  ", ink.DIM)
                 + "beat their hosts (each broken host is worth 22), "
                 "wait, or `court buy` at "
                 + ink.c(f"{c.coalition_price(g.day):,.0f}c", ink.GOLD))

    def _one_court(self, key: str) -> None:
        g = self.game
        c = g.court
        t = g.world.towns[key]
        view = c.opinion(key, g.day)
        self.say(ink.head(f"{t.lord.upper()} OF {t.name.upper()}",
                          f"{view:+.0f} -- {chancery.temper(view)}"))
        # The one number, and what it is made of, straight underneath: the
        # reasons below add up to it, the timer included.
        ill = c.ill_will(key, g.day, t.hostility)
        self.say("  " + ink.c(ink.pad("his ill-will toward you", 46), ink.DIM)
                 + ink.c(f"{ill:>6.0f}", self._standing_colour(-ill))
                 + ink.c(f"   of {C.HOSTILITY_WAR:.0f}; at {C.HOSTILITY_WAR:.0f} "
                         f"he reckons a war", ink.FAINT))
        self.say("  " + ink.c(lordkind.reputation(key, g.known(key)[1] >= 0),
                              ink.BONE))
        self.say("  " + ink.c(ink.pad("his trust in your word", 46), ink.DIM)
                 + ink.c(f"{c.trust_of(key):>6.0f}", ink.BONE)
                 + ink.c("   of 100; an alliance wants 35", ink.FAINT))
        war = c.score.get(key, 0.0)
        if war:
            self.say("  " + ink.c(ink.pad("the war, as he reckons it", 46), ink.DIM)
                     + ink.c(f"{war:>+6.0f}", self._standing_colour(war))
                     + ink.c("   +50 and he sues; -50 and he will not treat",
                             ink.FAINT))
        if t.reckoning:
            self.say("", ink.c(f"  HIS RECKONING ABOUT A WAR ON YOU  "
                               f"{t.reckoned:+.0f} (he marches at "
                               f"{g.DECLARE:.0f})", ink.DIM))
            for label, value in t.reckoning:
                self.say("  " + ink.c(ink.pad(label, 46), ink.DIM)
                         + ink.c(f"{value:>+6.0f}", self._standing_colour(-value)))
            self.say("")
        rows = c.reasons(key, g.day, restless=0.0 if t.truce_days else t.hostility)
        if not rows:
            self.say("", ink.c("  He has nothing written down about you "
                               "either way.", ink.DIM))
        for label, value, decay in rows:
            self.say("  " + ink.c(ink.pad(label, 46), ink.DIM)
                     + ink.c(f"{value:>+6.0f}", self._standing_colour(value))
                     + ink.c("  forever" if not decay
                             else "  rises until he marches" if decay < 0
                             else f"   wears off in {abs(value) / decay:,.0f} days",
                             ink.FAINT))
        self.say("")
        ground = c.ground_for(key, g.day)
        if ground is not None:
            live = c.grounds_left(key, g.day)
            self.say("  " + ink.c(ink.pad("a reason to march", 18), ink.DIM)
                     + ink.c(ground.label, ink.LEAF))
            for label, left in live:
                if label != ground.label:
                    self.say("  " + " " * 18 + ink.c(label, ink.DIM)
                             + ink.c("" if not left else f" ({left} days)",
                                     ink.FAINT))
        else:
            self.say("  " + ink.c(ink.pad("a reason to march", 18), ink.DIM)
                     + ink.c("none. Marching anyway costs the mood at home "
                             "and offends every other lord twice over.",
                             ink.AMBER))
        if t.refuses:
            self.say("  " + ink.c(ink.pad("he will not trade you", 18), ink.DIM)
                     + ink.c(", ".join(good(k).name for k in t.refuses),
                             ink.BLOOD)
                     + ink.c("  -- the carts and `scan` go round him", ink.DIM))
        toll = g.world.tariff_for(key, None)
        mood = g.world.toll_mood(key)
        self.say("  " + ink.c(ink.pad("his toll on you", 18), ink.DIM)
                 + ink.c(f"{toll * 100:.1f}%", ink.GOLD)
                 + ink.c(f"  ({mood:.2f}x what he asks a stranger)", ink.DIM))
        say = []
        if key in c.allies:
            say.append("allied: he comes when you are attacked, and calls "
                       "when he is")
        elif view >= chancery.WARM:
            say.append(f"he would swear to you -- `ally {key}`")
        else:
            say.append(f"he will not ally under {chancery.WARM:+.0f}")
        if key in c.claims:
            say.append("your house has a claim here by marriage")
        if key in c.coalition:
            say.append("he has signed the letter and will not treat alone")
        for line in say:
            self.say("  " + ink.c(ink.pad("", 18) + line, ink.DIM))

    def cmd_ally(self, args: List[str]) -> None:
        """Swear to a lord who thinks well enough of you to swear back."""
        if not args:
            return self.err("ally <town>")
        key = self._resolve_town(args[0])
        if key is None:
            return self.err(f"no town called {args[0]!r}")
        self.say("  " + self.game.ally(key))

    def cmd_befriend(self, args: List[str]) -> None:
        """Declare friendship with a lord: no oath to march, and no war."""
        if not args:
            return self.err("befriend <town>")
        key = self._resolve_town(args[0])
        if key is None:
            return self.err(f"no town called {args[0]!r}")
        self.say("  " + self.game.befriend(key))

    def cmd_call(self, args: List[str]) -> None:
        """Answer an ally who has called you to his war. No is a real answer."""
        g = self.game
        if g.court.called is None:
            return self.say(ink.c("  nobody has called you", ink.DIM))
        word = args[0].lower() if args else ""
        if word in ("yes", "y", "come", "aye"):
            return self.say("  " + g.answer_call(True))
        if word in ("no", "n", "refuse", "nay"):
            return self.say("  " + g.answer_call(False))
        who = g.world.node_name(g.court.called[0])
        self.err(f"{who} is waiting on an answer: `call yes` or `call no`")

    def _resolve_town(self, want: str) -> Optional[str]:
        want = want.lower()
        for key, t in self.game.world.towns.items():
            if want in (key.lower(), t.name.lower()):
                return key
        return None

    # ---------------------------------------------------------- the league
    def cmd_season(self, args: List[str]) -> None:
        """The table, and who has said they are coming for whom."""
        g = self.game
        se = g.league.season
        if args and args[0].lower() in ("past", "history", "champions"):
            return self._seasons_past()
        self.say(ink.head(f"THE {se.year} SEASON",
                          f"you stand {_ordinal(se.place(lg.PLAYER))} of "
                          f"{len(se.records)}"))
        self.say(ink.c("   #  place        who holds it          towns"
                       "    W-L   could field", ink.DIM))
        for i, r in enumerate(se.table(), 1):
            me = r.key == lg.PLAYER
            colour = ink.GOLD if me else ink.INK
            self.say(f"  {i:>2}  {ink.c(ink.pad(r.name or r.key, 13), colour)}"
                     f"{ink.c(ink.pad(_short(r.lord, 21), 22), ink.DIM)}"
                     f"{r.towns:>4}"
                     f"{ink.c(f'{r.line():>8}', ink.PARCH if me else ink.DIM)}"
                     f"{r.muster:>13,.0f}")
        # The schedule. The difference between a war and an ambush is a
        # fortnight's notice, and this is the fortnight.
        self.say("", ink.c("  WHO IS GOING WHERE", ink.DIM))
        shown = 0
        for f in se.fixtures:
            if f.done:
                continue
            at_you = f.target in g.world.settlements
            self.say(f"  {ink.c(ink.pad(self._name(f.who), 13), ink.PARCH)}"
                     + ink.c("means to move on ", ink.DIM)
                     + ink.c(self._name(f.target), ink.BLOOD if at_you else ink.INK)
                     + (ink.c("  -- that is you", ink.BLOOD) if at_you else "")
                     + (ink.c(f"  ({f.reason})", ink.FAINT)
                        if getattr(f, "reason", "") else ""))
            shown += 1
        if not shown:
            self.say(ink.c("  nobody has said anything. It will not last.", ink.DIM))
        best = g.league.bests
        if best:
            self.say("", ink.c("  STANDING RECORDS", ink.DIM))
            for what, (value, who, year) in sorted(best.items()):
                self.say(f"  {ink.pad(what, 26)}{value:>9,.0f}  "
                         + ink.c(f"{who}, {year}", ink.DIM))
        self.say("", ink.c("  `draft` for the men looking for a lord · "
                           "`season past` for the years before this one", ink.DIM))

    def _seasons_past(self) -> None:
        g = self.game
        past = g.league.past
        self.say(ink.head("SEASONS PAST", ink.count(len(past), "year")))
        if not past:
            return self.say(ink.c("  This is the first.", ink.DIM))
        for row in reversed(past):
            table = row.get("table", [])
            mine = next((r for r in table if r["key"] == lg.PLAYER), None)
            where = next((i for i, r in enumerate(table, 1)
                          if r["key"] == lg.PLAYER), 0)
            self.say(f"  {ink.c(str(row['year']), ink.PLUM)}  "
                     f"{ink.c(ink.pad(row.get('first', '?'), 14), ink.GOLD)}"
                     + ink.c("first of the march", ink.DIM)
                     + (f"   you: {_ordinal(where)}, {mine['won']}-{mine['lost']}"
                        if mine else ""))

    def cmd_draft(self, args: List[str]) -> None:
        """The men looking for a lord this year, in reverse order of finish."""
        g = self.game
        se = g.league.season
        if args:
            return self.say("  " + g.draft(" ".join(args)))
        self.say(ink.head(f"THE {se.year} INTAKE",
                          "last year's last chooses first"))
        if not se.prospects:
            return self.say(ink.c("  Nobody is looking for a lord.", ink.DIM))
        for p in se.prospects:
            who = ("" if not p.taken_by else
                   "you" if p.taken_by == lg.PLAYER else self._name(p.taken_by))
            gone = ink.c(f"-> {who}", ink.GOLD if p.taken_by == lg.PLAYER
                         else ink.DIM) if who else ink.c("free", ink.LEAF)
            self.say(f"  {ink.c(ink.pad(_short(p.name, 22), 23), ink.PARCH)}"
                     f"{ink.c(ink.pad(f'{p.skill} {p.grade}', 16), ink.BONE)}"
                     f"{ink.pad(gone, 18)}{ink.c(_short(p.story, 44), ink.DIM)}")
        turn = se.on_the_clock()
        self.say("")
        if turn == lg.PLAYER:
            self.say(ink.c("  You are on the clock. `draft <name>` takes one.",
                           ink.GOLD))
        elif turn:
            self.say(ink.c(f"  {self._name(turn)} is on the clock.", ink.DIM))
        else:
            self.say(ink.c("  The intake is spoken for. Next spring.", ink.DIM))
        self.say(ink.c("  Reverse order of last year's table, which is the whole "
                       "point of it:\n  finish last and you choose first.", ink.DIM))

    def cmd_war(self, args: List[str]) -> None:
        """The state of the march, as far as anyone of yours has seen it."""
        g = self.game
        self.say(ink.head("THE STATE OF THE MARCH", "as last reported"),
                 "  town          lord                    sworn to    walls"
                 "  could field  as they stood    last word")
        for key, t in g.world.towns.items():
            seen, age = g.known(key)
            liege = ("you" if t.mine else
                     g.world.node_name(t.owner) if t.owner else "-")
            if age < 0:
                # Never looked. Say so rather than inventing a number: half of
                # knowing a march is knowing which parts of it you do not.
                self.say(f"  {ink.c(ink.pad(t.name, 13), ink.PARCH)} "
                         f"{ink.c(ink.pad(t.lord, 23), ink.DIM)} {liege:<10}"
                         f" {'?':>6}  {'?':>10}   "
                         + ink.c("you have never sent anyone", ink.DIM))
                continue
            hostile = seen.get("hostility", 0.0)
            if t.mine:
                state = "sworn to you"
            elif t.truce_days:
                state = f"truce ({t.truce_days}d)"
            elif hostile > 70:
                state = "arming"
            elif hostile > 40:
                state = "cold"
            else:
                state = "civil"
            might = host_strength(g.believed_host(key))
            mood = (ink.LEAF if t.mine else ink.SEA if t.truce_days else
                    ink.BLOOD if hostile > 70 else
                    ink.AMBER if hostile > 40 else ink.INK)
            stale = ("today" if age <= 1 else f"{age}d ago")
            self.say(f"  {ink.c(ink.pad(t.name, 13), ink.PARCH)} "
                     f"{ink.c(ink.pad(t.lord, 23), ink.DIM)} {liege:<10}"
                     f" {seen.get('wall_hp', 0.0):>6,.0f}  {might:>10,.0f}   "
                     + ink.c(ink.pad(f"{state} ({hostile:.0f})", 16), mood)
                     + ink.c(stale, ink.DIM if age <= 30 else ink.AMBER))
        c = g.court
        if c.coalition:
            self.say("")
            self.say("  " + ink.c("THE LETTER AGAINST YOU  ", ink.BLOOD)
                     + ink.c(", ".join(g.world.node_name(k)
                                       for k in c.coalition), ink.AMBER))
            self.say("  " + ink.c("They march together and will not treat one "
                                  "at a time. `court` has the way out.",
                                  ink.DIM))
        if c.called is not None:
            who = g.world.node_name(c.called[0])
            left = g.CALL_DAYS - (g.day - c.called[1])
            self.say("")
            self.say("  " + ink.c(f"{who} HAS CALLED YOU TO HIS WAR  ", ink.GOLD)
                     + ink.c(f"{left} days to answer -- `call yes` or "
                             f"`call no`", ink.PARCH))
        # Who they are, and not only how many. Character is intelligence and
        # intelligence is what the trade layer buys: a lord you have never
        # sent a cart to is a lord you are guessing about, and the whole of
        # what you are guessing about is the thing that decides whether a
        # gift will hold him or he is coming for the harvest either way.
        self.say("")
        for key, t in g.world.towns.items():
            _seen, age = g.known(key)
            kind = lordkind.sort_of(key)
            if age < 0:
                self.say(f"  {ink.c(ink.pad(t.name, 13), ink.DIM)}"
                         + ink.c("nobody of yours has been near enough to say",
                                 ink.FAINT))
                continue
            ground = c.ground_for(key, g.day)
            # The banner above already says who signed. Repeating it beside
            # every one of them buries the six characters this screen exists
            # to tell apart under one sentence written seven times.
            if ground is not None and ground.key == "coalition":
                live = [x for x in c.grounds_left(key, g.day)
                        if x[0] != ground.label]
                ground = None if not live else ground
            standing = c.opinion(key, g.day)
            self.say(f"  {ink.c(ink.pad(t.name, 13), ink.PARCH)}"
                     f"{ink.c(ink.pad(kind.name, 12), ink.BONE)}"
                     + ink.c(ink.pad(cultures.culture(t.culture).name, 13),
                             ink.SLATE)
                     + ink.c(ink.pad(chancery.temper(standing), 11), ink.DIM)
                     + (ink.c("grounds: " + ground.label, ink.LEAF)
                        if ground else ink.c(kind.blurb + "; "
                                             + lordkind.HUNTS.get(kind.hunts, ""),
                                             ink.DIM)))
        mine = sum(host_strength(s.units) for s in g.world.settlements.values())
        mine += sum(host_strength(a.units) for a in g.armies if a.owner == "player")
        self.say("", f"  your own strength {mine:,.0f}, spread over "
                 f"{ink.count(len(g.world.settlements), 'settlement')} and "
                 f"{ink.count(len(g.armies), 'host')}")
        self.say(ink.c("  What you know is what you last saw. A cart that calls "
                       "somewhere looks around while it is there.", ink.DIM))
        for a in g.armies:
            who = "yours" if a.owner == "player" else self._name(a.home)
            self.say(f"  host: {a.name} ({who}) · {self._where(a)}, "
                     f"{describe(a.units)}")

    def cmd_gift(self, args: List[str]) -> None:
        """Buy a lord's goodwill. Cheaper than a wall, and it does not last."""
        if len(args) < 2:
            return self.err("gift <town> <coin>")
        self.say("  " + self.game.gift(self._node(args[0]), float(args[1])))

    def cmd_truce(self, args: List[str]) -> None:
        """Buy peace by the day."""
        if not args:
            return self.err("truce <town> [days]")
        key = self._node(args[0])
        days = int(args[1]) if len(args) > 1 else 180
        if len(args) == 1:
            return self.say(f"  {days} days of peace with {self._name(key)} would "
                            f"cost {self.game.truce_cost(key, days):,.0f}c "
                            f"(`truce {args[0]} {days}` to buy it)")
        self.say("  " + self.game.truce(key, days))

    def cmd_demand(self, args: List[str]) -> None:
        """Demand tribute. It works on a weaker lord and enrages any other."""
        if not args:
            return self.err("demand <town>")
        self.say("  " + self.game.demand(self._node(args[0])))
