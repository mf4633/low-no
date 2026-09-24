"""Terminal interface. Stdlib only, no curses, works over ssh and in a pipe."""

from __future__ import annotations

import json
import shlex
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import config as C
from .advisor import route_from, scan, shortage_report
from .buildings import ALL_BUILDING_KEYS, BUILDINGS, building
from .buildings import resolve as resolve_building
from .campaign import CHAPTERS, BY_KEY as CHAPTERS_BY_KEY
from .castle import PLANS, SiegeState, Works
from .chronicle import MOMENTOUS, NOTABLE, ROUTINE
from .engine import GameState, _ordinal
from .economics import (compare, daily_output, marginal_hands,
                        surplus, town_output)
from .goods import ALL_KEYS, RATION_GOODS, good, nourishment
from .goods import resolve as resolve_good
from . import kin as kinly
from . import league as lg
from . import lord as lordly
from . import chancery
from . import culture as cultures
from . import keep as keeps
from . import lords as lordkind
from . import voices
from . import render as ink
from . import rivers as waters
from .military import UNITS, describe, host_strength, host_upkeep, sky_on
from .military import resolve as resolve_unit
from .scenarios import CAMPAIGN, SCENARIOS, start as start_scenario
from .tech import AGES, HOUSES, TECHS
from .trade import CART, IDLE, MOVING, SHIP, TRADING, Order, Stop
from .iso import scene
from .view import GLYPHS, townscape

BARS = " ▁▂▃▄▅▆▇█"
RULE = ink.rule()


def title(text: str, right: str = "", colour: int = ink.GOLD) -> str:
    return ink.head(text, right, colour)


def _fmt(x: float, width: int = 8, dp: int = 0) -> str:
    return f"{x:>{width},.{dp}f}"


def sparkline(values: Sequence[float], width: int = 48) -> str:
    vals = list(values)[-width:]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return BARS[4] * len(vals)
    return "".join(BARS[1 + int(7.99 * (v - lo) / (hi - lo))] for v in vals)


def _words(line: str) -> list:
    r"""A command line split the way a shell splits it, less the escapes.

    Quotes still hold a name with a space in it together. A backslash is
    only a backslash, because the game ships as a Windows exe and to a
    POSIX splitter `save C:\Users\me\march.json` is `C:Usersmemarch.json`,
    written quietly to wherever the game was started from.
    """
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.escape = ""
    return list(lex)


class Console:
    def __init__(self, game: GameState, out=sys.stdout) -> None:
        self.game = game
        self.out = out
        self.here = next(iter(game.world.settlements))
        self.quit = False
        self.autosave_path = ""
        try:
            ink.set_colour(ink._enabled() and out.isatty())
        except Exception:                    # pragma: no cover - odd streams
            ink.set_colour(False)

    # ------------------------------------------------------------------ i/o
    def say(self, *lines: str) -> None:
        for ln in lines:
            print(ln, file=self.out)

    def err(self, msg: str) -> None:
        self.say(f"  ! {msg}")

    # -------------------------------------------------------------- helpers
    run = None          # the campaign this game belongs to, if any

    def settlement(self, key: Optional[str] = None):
        w = self.game.world
        k = key or self.here
        if k in w.settlements:
            return w.settlements[k]
        return w.settlements[self.here]

    def _which(self, args: List[str], usage: str) -> Optional[int]:
        """Read the number a command was given, or explain what it wanted.

        Eight commands used to say "list index out of range" when handed
        nothing and "invalid literal for int()" when handed a word. That is
        Python talking to a player, which is never the right voice.
        """
        if not args:
            self.err(usage)
            return None
        try:
            return int(args[0])
        except ValueError:
            self.err(f"{args[0]!r} is not a number -- {usage}")
            return None

    def _node(self, text: str, shrines: bool = False) -> str:
        return self.game.world.resolve(text, shrines=shrines)

    def _name(self, key: str) -> str:
        return self.game.world.node_name(key)

    def _where(self, thing) -> str:
        """Where a host or a cart is, with every key turned into a name."""
        return thing.where(self._name)

    # ================================================================ views
    def status(self) -> None:
        g = self.game
        led = g.ledger
        p = g.progress
        vassals = g.world.vassals()
        tint = ink.SEASON_TINT.get(g.season, ink.GOLD)
        self.say(ink.head(g.date_str(), f"{g.treasury:,.0f}c in the chest", tint),
                 f"  net worth {ink.coin(g.net_worth(), 10)}c of "
                 f"{g.goals.net_worth:,.0f}"
                 f"      souls {ink.c(f'{g.population:>6,.0f}', ink.PARCH)}"
                 f" of {g.goals.population}",
                 f"  {ink.c(p.age_name(), ink.PLUM):<33} "
                 f"{ink.c(HOUSES[g.house].name, ink.BONE) if g.house else '':<35}"
                 f"  towns sworn {len(vassals)} of {g.goals.towns}",
                 RULE)
        for s in g.world.settlements.values():
            siege = ink.c("  UNDER SIEGE", ink.BLOOD, bold=True) if s.besieged else ""
            self.say(f"  {ink.c(ink.pad(s.name, 12), ink.PARCH, bold=True)}"
                     f" pop {s.population:>6,.0f}/{s.housing(p):<5,.0f}"
                     f" {ink.bar(s.popularity, 100, 16)} {s.popularity:>4.0f}"
                     f"  work {s.employed:>3}/{s.jobs_offered:<3}"
                     f"  {C.RATION_LABELS[s.ration_level]},"
                     f" {C.TAX_LABELS[s.tax_level]} tax{siege}")
        # One line of macro, and only when it is telling you something. A
        # steady price level and full employment need no commentary.
        a = g.accounts
        notes = []
        if abs(a.inflation) >= 4.0:
            notes.append(ink.c(f"prices {a.inflation:+.0f}% "
                               + ("a year" if a.yearly else "since you began"),
                               ink.BLOOD if a.inflation > 0 else ink.SEA))
        if a.unemployment >= 25.0:
            notes.append(ink.c(f"{a.unemployment:.0f}% of hands idle", ink.AMBER))
        short = [k for k, v in g.economy.shortage.items() if v > 0.1]
        if short:
            notes.append(ink.c(f"no {good(short[0]).name.lower()} to be had "
                               f"at the assize price", ink.BLOOD))
        if notes:
            self.say("  " + ink.c("the accounts ", ink.DIM) + " · ".join(notes))
        # Where the race actually stands. A game whose result you only learn
        # on the last day is one you could not have played differently.
        rows = g.pace()
        if rows and g.day > 60 and not g.over:
            left = max(0, g.goals.days - g.day)
            # Several of these are alternative ways to win rather than
            # clauses you are failing, so a path you have not started on is
            # dim rather than red. Red is only for a race you are in.
            live = [r for r in rows if r[1] > 0] or rows
            parts = []
            for what, now, want, land in live:
                short = land < want * 0.995
                started = now > 0
                parts.append(
                    ink.c(f"{what} {now:,.0f}", ink.PARCH if started else ink.DIM)
                    + ink.c(f"/{want:,.0f}", ink.DIM)
                    + ink.c(f" →{land:,.0f}",
                            (ink.BLOOD if short else ink.LEAF) if started
                            else ink.FAINT))
            self.say(f"  {ink.c('the race', ink.DIM)}     " + "   ".join(parts)
                     + ink.c(f"   ({left}d left, at this rate)", ink.DIM))
        busy = []
        if p.advancing:
            busy.append(f"climbing to the {AGES[p.age + 1].name} ({p.advancing}d)")
        if p.researching:
            busy.append(f"studying {TECHS[p.researching].name} "
                        f"({p.research_left:.0f}d)")
        if busy:
            self.say("  " + ";  ".join(busy))
        if g.soldiers:
            self.say(f"  under arms   {g.soldiers} soldiers"
                     + (f", {len(g.armies)} in the field" if g.armies else ""))
        for a in g.armies:
            if a.owner != "player":
                self.say(f"  ! {a.name} out of {self._name(a.home)}: {self._where(a)}")
        if g.caravans:
            self.say("")
            for c in g.caravans:
                self.say(f"  [{c.uid}] {c.name:<12} {self._where(c):<22} "
                         f"{c.load:>3.0f}/{c.capacity:<3.0f} {c.manifest(34):<34}"
                         f" {c.total_profit:+,.0f}c")
        self.say("",
                 f"  day's ledger   taxes {ink.coin(led.taxes, 7, True)}"
                 f"   trade {ink.coin(led.trade, 8, True)}"
                 f"   tribute {ink.coin(led.tribute, 6, True)}"
                 f"   interest {ink.coin(led.interest, 5, True)}",
                 f"                 wages {ink.coin(-led.wages, 7, True)}"
                 f"   upkeep {ink.coin(-led.upkeep, 7, True)}"
                 f"   carts {ink.coin(-led.caravans, 8, True)}"
                 f"   war {ink.coin(-led.war, 10, True)}",
                 f"                 net   {ink.coin(led.net, 7, True)}c")
        if len(g.history) > 3:
            self.say("  worth  " + ink.spark([h["worth"] for h in g.history]))
        for m in g.messages[-8:]:
            self.say("  " + ink.c("*", ink.FAINT) + " " + self._tint(m))
        if g.over:
            self.say(RULE, "  " + ink.c(g.over, ink.GOLD, bold=True), RULE)

    MESSAGE_TINTS = (
        (("WAR:", "ASSAULT", "RAID", "STORMED", "TAKEN", "under siege",
          "COFFERS", "unrest"), ink.BLOOD),
        (("bends the knee", "Learned:", "***", "finished", "Triumph",
          "Dominion"), ink.GOLD),
        (("News:", "marches on", "lays siege"), ink.AMBER),
    )

    def _tint(self, msg: str) -> str:
        for words, colour in self.MESSAGE_TINTS:
            if any(w in msg for w in words):
                return ink.c(msg, colour)
        return msg

    def plan_view(self, key: Optional[str] = None, flat: bool = False) -> None:
        """The one screen this game spent a long time without: your town."""
        s = self.settlement(key)
        g = self.game
        p = g.progress
        self.say(ink.head(s.name.upper(),
                          f"{C.SEASON_OF_MONTH[g.month]}, {g.year}",
                          ink.SEASON_TINT.get(g.season, ink.GOLD)))
        draw = (townscape(s, p, g.season, besieged=s.besieged) if flat
                else scene(s, p, g.season, g.day, besieged=s.besieged))
        for line in draw:
            self.say(line)
        self.say(*self._caption(s, p, flat))

    def _caption(self, s, p, flat: bool) -> List[str]:
        wall_top = s.wall_max(p)
        lines = ["",
                 f"  souls   {s.population:>6,.0f} of {s.housing(p):,.0f} roofs"
                 f"     mood {ink.bar(s.popularity, 100, 14)} {s.popularity:>3.0f}"
                 f"     {C.RATION_LABELS[s.ration_level]} rations",
                 f"  wall    {ink.bar(s.wall_hp, max(wall_top, 1), 14)}"
                 f" {s.wall_hp:>5,.0f}/{wall_top:<5,.0f}"
                 f"  garrison {s.garrison_line()}"]
        if not flat:
            lines.append("  standing " + self._roll(s))
        lines.append(ink.c(f"  built in {s.idiom().name} -- "
                           f"{s.idiom().blurb}", ink.DIM))
        # Neither town screen can draw the castle at its real shape -- both
        # are a rectangle round the town and the castle is a thirty-yard
        # square of ground. So the one thing they would otherwise hide gets
        # said instead: a workshop the ring does not reach.
        left = s.outside_the_wall()
        if left:
            names = [b.spec.name for b in s.buildings if b.uid in left]
            lines.append(ink.c(
                f"  outside  {len(left)} building(s) the wall does not reach: "
                + ", ".join(names[:3]) + (" ..." if len(names) > 3 else "")
                + "   `castle` draws the shape of it", ink.AMBER))
        return lines

    def _roll(self, s) -> str:
        """What is down there, in words, since a silhouette is not a label."""
        counts: Dict[str, int] = {}
        idle = 0
        for b in s.buildings:
            if not b.complete:
                continue
            counts[b.key] = counts.get(b.key, 0) + 1
            if (b.spec.inputs or b.spec.outputs) and (
                    not b.enabled or b.throughput <= 0.05):
                idle += 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:7]
        bits = [f"{n}x {BUILDINGS[k].name}" if n > 1 else BUILDINGS[k].name
                for k, n in top]
        tail = ink.c(f"   ({idle} idle)", ink.AMBER) if idle else ""
        return ink.c(" · ".join(bits), ink.DIM) + tail

    def town_view(self, key: Optional[str] = None) -> None:
        s = self.settlement(key)
        p = self.game.progress
        self.say(ink.head(f"{s.name}", f"pop {s.population:,.0f} / mood "
                          f"{s.popularity:.0f}" + (" / UNDER SIEGE" if s.besieged
                                                   else ""),
                          ink.BLOOD if s.besieged else ink.GOLD))
        land = "  ".join(f"{t}: {s.slots_free(t)}/{n}" for t, n in s.terrain.items() if n)
        self.say(f"  free land   {land}")
        if s.deposits:
            self.say("  seams       " + ",  ".join(
                f"{good(k).name} {v:,.0f} left" for k, v in s.deposits.items()))
        self.say(f"  stores      {s.market.total_units():,.0f}/{s.storage(p):,.0f} units,"
                 f" worth {s.market.inventory_value():,.0f}c")
        self.say(f"  defences    wall {s.wall_hp:,.0f}/{s.wall_max(p):,.0f},"
                 f" works {s.effect('defense'):.0f}, garrison {s.garrison_line()}"
                 f"  (strength {s.defense(p):.0f})")
        self.say("")
        self.say(ink.c("   id  building            staff  running  note", ink.DIM))
        headings = {"castle": "the castle", "civic": "the town",
                    "industry": "the workshops", "primary": "the land"}
        def row(b):
            if not b.complete:
                return f"{b.days_left}d to raise", ""
            if not b.enabled:
                # It said "closed" in the running column and "closed" again in
                # the note. Once is enough.
                return "closed", ""
            if b.spec.is_producer or b.spec.inputs:
                return f"{100 * b.throughput:>3.0f}%", b.idle_reason
            return "  -", b.idle_reason

        # Seven identical cottages are seven identical lines, and a table of
        # forty-five of those is a table nobody reads. Fold rows that are the
        # same in every respect you can see, and keep their numbers, because
        # the numbers are what `close` and `raze` take.
        last, group = None, []

        def flush():
            if not group:
                return
            first = group[0]
            run, note = row(first)
            jobs = f"{first.staffed}/{first.spec.jobs}" if first.spec.jobs else "  -"
            glyph, colour = GLYPHS.get(first.key, ("·", ink.DIM))
            uids = [b.uid for b in group]
            tag = f"{uids[0]:>3}" if len(uids) == 1 else f"{len(uids):>2}x"
            name = first.spec.name
            line = (f"  {tag}  {ink.c(glyph, colour)} "
                    f"{ink.pad(name, 18)}{jobs:>5}  {run:>9}")
            if note:
                line += "  " + ink.c(note, ink.AMBER)
            if len(uids) > 1:
                line += ink.c(f"   {', '.join(str(u) for u in uids)}", ink.DIM)
            self.say(line)
            group.clear()

        for b in sorted(s.buildings, key=lambda b: (b.spec.category, b.key, b.uid)):
            if b.spec.category != last:
                flush()
                last = b.spec.category
                self.say(ink.c(f"  -- {headings.get(last, last)}", ink.DIM))
            if group and (group[0].key != b.key or row(group[0]) != row(b)
                          or group[0].staffed != b.staffed):
                flush()
            group.append(b)
        flush()
        self.say("")
        factors = [(k, v) for k, v in s.mood_factors(p) if abs(v) >= 0.5]
        self.say("  mood    " + ("  ".join(f"{k} {v:+.0f}" for k, v in factors)
                                 or "nothing either way"))
        if s.fear:
            self.say(f"  fear    {s.fear:.0f} -- work runs "
                     f"{3.5 * s.fear:.0f}% harder and the people like it that much less")
        # Anything actually alight outranks everything else on this screen.
        if s.fires:
            alight = [b.spec.name for b in s.buildings if s.fires.burning(b.uid)]
            self.say("  " + ink.c(f"ON FIRE  {len(alight)} alight: "
                                  f"{', '.join(sorted(set(alight))[:5])}", ink.BLOOD))
        # "burning" meant running down faster than you make it, which was a fair
        # word for it until the town could literally be on fire.
        short = shortage_report(s)[:6]
        if short:
            self.say("  using up " + ", ".join(
                f"{good(k).name} {net:+.1f}/day (stock {stock:.0f})"
                for k, net, stock in short))

    def stores(self, key: Optional[str] = None, count: int = 24) -> None:
        s = self.settlement(key)
        rep = s.report
        self.say(ink.head(f"{s.name} stores", f"{s.market.inventory_value():,.0f}c"),
                 ink.c("  good           stock    price   made/day   used/day",
                       ink.DIM))
        rows = []
        for k in ALL_KEYS:
            stock = s.market.stock[k]
            made = rep.produced.get(k, 0.0)
            used = rep.consumed.get(k, 0.0) + rep.eaten.get(k, 0.0)
            if stock < 0.5 and not made and not used:
                continue
            rows.append((k, stock, s.market.price(k), made, used))
        for k, stock, price, made, used in rows[:count]:
            flag = ink.c("  <-- falling", ink.AMBER) if (
                used > made + 0.01 and stock < 60) else ""
            rel = price / good(k).base_price
            self.say(f"  {good(k).name:<12}{stock:>8,.0f}  "
                     f"{ink.c(f'{price:>7.2f}', ink.tone(rel))}"
                     f"{made:>10.1f}{used:>11.1f}{flag}")

    def market_view(self, key: str) -> None:
        w = self.game.world
        node = self._node(key)
        if node in w.settlements:
            return self.stores(node)
        t = w.towns[node]
        d = w.distance(self.here, node)
        self.say(RULE,
                 f"  {t.name}  --  {d:.0f} leagues from {self._name(self.here)},"
                 f" toll {100 * w.tariff_for(node, None):.0f}%,"
                 f" road risk {100 * w.danger(self.here, node):.1f}%/day", RULE)
        if t.blurb:
            self.say(f"  {t.blurb}")
        for s in t.shocks:
            self.say(f"  ! {t.name} {s.label} ({s.days_left}d left)")
        self.say("", "  good           they pay   they ask   stock   flow/day   vs base")
        rows = sorted(ALL_KEYS, key=lambda k: -abs(t.flow.get(k, 0.0)))
        for k in rows:
            if not t.market.sells(k):
                continue
            flow = t.flow.get(k, 0.0)
            if abs(flow) < 0.05 and t.market.stock[k] < 5:
                continue
            rel = t.market.price(k) / good(k).base_price
            mark = "cheap" if rel < 0.8 else ("dear" if rel > 1.25 else "")
            self.say(f"  {good(k).name:<12}{t.market.bid(k):>10.2f}{t.market.ask(k):>11.2f}"
                     f"{t.market.stock[k]:>8,.0f}{flow:>11.1f}   {rel:>4.2f}x {mark}")

    def price_view(self, gkey: str) -> None:
        g = self.game
        k = resolve_good(gkey)
        self.say(ink.head(good(k).name,
                          f"base {good(k).base_price:.2f}c / "
                          f"{good(k).weight:.1f} cart units / "
                          f"{100 * good(k).spoilage:.1f}%/day spoilage"),
                 ink.c("  place          they pay   they ask   stock   trend",
                       ink.DIM))
        rows = []
        for node in g.world.all_nodes():
            m = g.world.market_of(node)
            if not m or not m.sells(k):
                continue
            rows.append((node, m))
        rows.sort(key=lambda r: -r[1].bid(k))
        for node, m in rows:
            tag = " (yours)" if g.world.is_mine(node) else ""
            rel = m.price(k) / good(k).base_price
            name = ink.c(ink.pad(self._name(node) + tag, 14),
                         ink.PARCH if g.world.is_mine(node) else ink.INK)
            self.say(f"  {name}{ink.c(f'{m.bid(k):>10.2f}', ink.tone(rel))}"
                     f"{m.ask(k):>11.2f}{m.stock[k]:>8,.0f}   "
                     + ink.spark(m.history[k], 20, ink.tone(rel)))

    def chain_view(self, gkey: str) -> None:
        k = resolve_good(gkey)
        self.say(ink.head(f"{good(k).name} chain"))
        for bk, b in BUILDINGS.items():
            if k in b.outputs:
                ins = ", ".join(f"{v:g} {good(i).name}" for i, v in b.inputs.items()) or "nothing"
                self.say(f"  made by {b.name:<18} on {b.terrain:<8} "
                         f"{b.jobs} hands: {ins} -> {b.outputs[k]:g}/day")
        for bk, b in BUILDINGS.items():
            if k in b.inputs:
                outs = ", ".join(f"{v:g} {good(o).name}" for o, v in b.outputs.items()) or "-"
                self.say(f"  eaten by {b.name:<17} {b.inputs[k]:g}/day -> {outs}")

    def buildings_view(self, filt: str = "") -> None:
        self.say(ink.head("WHAT YOU MAY RAISE", self.game.progress.age_name()),
                 "  key             name                 land    hands  cost")
        s = self.settlement()
        for k in ALL_BUILDING_KEYS:
            b = BUILDINGS[k]
            if filt and filt not in k and filt != b.category:
                continue
            cost = f"{b.build_cost.get('coin', 0):.0f}c " + " ".join(
                f"{v:g}{i[:4]}" for i, v in b.build_cost.items() if i != "coin")
            free = s.slots_free(b.terrain)
            self.say(f"  {k:<15} {b.name:<20} {b.terrain:<7}({free}) {b.jobs:>3}   {cost}")
        self.say("  (`chain <good>` shows what feeds what; `info <key>` for one building)")

    def building_info(self, key: str) -> None:
        b = building(resolve_building(key))
        ins = ", ".join(f"{v:g} {good(i).name}" for i, v in b.inputs.items()) or "-"
        outs = ", ".join(f"{v:g} {good(o).name}" for o, v in b.outputs.items()) or "-"
        cost = ", ".join(f"{v:g} {i}" for i, v in b.build_cost.items())
        self.say(ink.head(b.name, b.key),
                 f"  land      {b.terrain}        hands {b.jobs}    raise in {b.build_days}d",
                 f"  cost      {cost}",
                 f"  per day   {ins}  ->  {outs}",
                 f"  upkeep    {b.upkeep:g}c/day" + (f"   season: {b.season}" if b.season else ""))
        if b.effects:
            self.say("  effects   " + ", ".join(f"{k} {v:+g}" for k, v in b.effects.items()))
        if b.note:
            self.say(f"  note      {b.note}")

    def caravan_view(self, uid: Optional[int] = None) -> None:
        g = self.game
        if uid is None:
            self.say(ink.head("CARAVANS AND HULLS",
                              f"{len(g.caravans)} of {g.caravan_limit}"))
            for c in g.caravans:
                state = {IDLE: "idle", MOVING: "on the road" if not c.sails else "at sea",
                         TRADING: "in port" if c.sails else "in town"}[c.state]
                self.say(f"  [{c.uid}] {c.name:<12} {'cog' if c.sails else 'cart':<5}"
                         f"{state:<12} {self._where(c):<20}"
                         f" {c.load:>4.0f}/{c.capacity:<4.0f}"
                         f" {c.total_profit:+,.0f}c lifetime")
                if c.route:
                    self.say("       route: " + "  ->  ".join(
                        s.describe() for s in c.route) + ("  (looping)" if c.running else "  (halted)"))
            return
        c = g.caravan(uid)
        if not c:
            return self.err(f"no caravan {uid}")
        self.say(ink.head(c.name, "cog" if c.sails else "cart"),
                 f"  where     {self._where(c)}",
                 f"  cargo     {c.manifest()}  ({c.load:.0f}/{c.capacity:.0f} cart units)",
                 f"  guards    {c.guards}  ({c.daily_cost:.0f}c/day all in)",
                 f"  earned    {c.total_profit:+,.0f}c lifetime")
        for i, s in enumerate(c.route):
            mark = ">" if i == c.leg % max(1, len(c.route)) else " "
            self.say(f"   {mark} {s.describe()}")
        for line in c.log[-8:]:
            self.say(f"     . {line}")

    def scan_view(self, top: int = 8, sails: bool = False) -> None:
        g = self.game
        if sails:
            cap, spd = C.SHIP_CAPACITY, C.SHIP_SPEED
            cost = C.SHIP_UPKEEP + C.GUARD_COST
            what = f"hull of {cap:.0f} units at {spd:.0f} sea leagues/day"
        else:
            cap = C.CARAVAN_BASE_CAPACITY + self.settlement().effect("caravan_capacity")
            spd = C.CARAVAN_BASE_SPEED + self.settlement().effect("caravan_speed")
            cost = C.CARAVAN_UPKEEP + C.GUARD_COST
            what = f"cart of {cap:.0f} units at {spd:.0f} leagues/day"
        self.say(ink.head("THE COUNTING HOUSE", f"{what}, all costs in"))
        rows = scan(g.world, self.here, capacity=cap, speed=spd, daily_cost=cost,
                    day=g.day, seed=g.seed, start_month=g.start_month,
                    budget=max(0.0, g.treasury), top=top, sails=sails)
        for o in rows:
            self.say("  " + o.describe(self._name))
        if not rows:
            self.say("  nothing worth the wheels today")
        if not sails and g.world.ports():
            mine = any(x.effect("port") for x in g.world.settlements.values())
            self.say("  (`scan sea` prices the same trades for a cog"
                     + ("" if mine else " -- you need a harbour first") + ")")
        self.say("  (`auto <caravan>` puts a cart or a hull on the best of these)")

    def map_view(self) -> None:
        g = self.game
        w, h = 62, 19
        xs = [c[0] for c in g.world.coords.values()] + [s.x for s in g.world.sites.values()]
        ys = [c[1] for c in g.world.coords.values()] + [s.y for s in g.world.sites.values()]
        lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
        grid = [[(" ", ink.FAINT)] * w for _ in range(h)]

        def plot(x: float, y: float, label: str, colour: int = ink.INK) -> None:
            cx = min(w - len(label) - 1,
                     int((x - lo_x) / max(hi_x - lo_x, 1e-6) * (w - 14)) + 1)
            cy = int((hi_y - y) / max(hi_y - lo_y, 1e-6) * (h - 2)) + 1
            for row in (cy, cy + 1, cy - 1, cy + 2):   # nudge off a neighbour
                if not 0 <= row < h:
                    continue
                span = grid[row][max(0, cx - 1):cx + len(label) + 1]
                if all(cell[0] == " " for cell in span):
                    cy = row
                    break
            for i, ch in enumerate(label):
                if 0 <= cx + i < w:
                    grid[cy][cx + i] = (ch, colour)

        # The water first, so a town's name is never eaten by a river. A map
        # with roads and no rivers on it is a map that cannot explain why a
        # four-day leg took six, and that was the state of this one.
        level = waters.stage(g.day, g.seed, g.start_month)
        sky = sky_on(g.season, g.day, g.seed)

        def cell(x: float, y: float) -> Tuple[int, int]:
            return (min(w - 1, max(0, int((x - lo_x) / max(hi_x - lo_x, 1e-6)
                                          * (w - 14)) + 1)),
                    min(h - 1, max(0, int((hi_y - y) / max(hi_y - lo_y, 1e-6)
                                          * (h - 2)) + 1)))

        for r in g.world.waters():
            st = waters.state_of(r, level, sky)
            colour = {waters.SHUT: ink.BLOOD, waters.HIGH: ink.GOLD,
                      waters.ICE: ink.PARCH}.get(st, ink.SKY)
            (ax, ay), (bx, by) = cell(r.x1, r.y1), cell(r.x2, r.y2)
            steps = max(abs(bx - ax), abs(by - ay)) or 1
            # The glyph follows the run of the river rather than being one
            # character everywhere: `~~~~` across a map reads as sea.
            glyph = ("|" if abs(by - ay) > 2 * abs(bx - ax) else
                     "-" if abs(bx - ax) > 2 * abs(by - ay) else
                     ("\\" if (bx - ax) * (by - ay) > 0 else "/"))
            for i in range(steps + 1):
                cx = ax + round((bx - ax) * i / steps)
                cy = ay + round((by - ay) * i / steps)
                if 0 <= cy < h and 0 <= cx < w and grid[cy][cx][0] == " ":
                    grid[cy][cx] = (glyph, colour)

        for b in g.world.bridges:
            if not b.standing:
                continue
            bxp, byp = cell(b.x, b.y)
            if 0 <= byp < h and 0 <= bxp < w:
                grid[byp][bxp] = ("#", ink.GOLD if b.owner == "player"
                                  else ink.DIM)

        labels: List[str] = []
        for key, (x, y) in sorted(g.world.coords.items()):
            if key in g.world.shrines:
                sh = g.world.shrines[key]
                colour = (ink.GOLD if sh.holder == "player"
                          else ink.DIM if sh.taken else ink.PLUM)
                plot(x, y, "+" + self._name(key), colour)
                continue
            mark = "@" if g.world.is_mine(key) else ("~" if g.world.is_port(key) else "o")
            plot(x, y, mark + self._name(key), _node_colour(g, key))
            labels.append(f"{self._name(key):<10} {g.world.distance(self.here, key):>4.0f} leagues")
        for key, site in g.world.sites.items():
            plot(site.x, site.y, "+" + site.name, ink.LEAF)
        self.say(ink.head("THE MARCHLANDS",
                          "@ yours  ~ port  o foreign  + land or shrine  # bridge"))
        for row in grid:
            line, run, colour = [], [], None
            for ch, col in row:
                if col != colour:
                    if run:
                        line.append(ink.c("".join(run), colour))
                    run, colour = [], col
                run.append(ch)
            if run:
                line.append(ink.c("".join(run), colour))
            self.say("  " + "".join(line).rstrip())
        self.say(RULE)
        # Which line is which water, and what it is doing. A river drawn and
        # not named is decoration; named with today's state beside it, it is
        # the reason the panel exists.
        rivers = g.world.waters()
        if rivers:
            bits = []
            for r in rivers:
                st = waters.state_of(r, level, sky)
                tint = {waters.SHUT: ink.BLOOD, waters.HIGH: ink.GOLD,
                        waters.ICE: ink.PARCH}.get(st, ink.SKY)
                bits.append(ink.c(f"the {r.name}", tint)
                            + ink.c(f" {waters.WORDS[st]}", ink.DIM))
            self.say("  " + "   ".join(bits))
            self.say(RULE)
        for i in range(0, len(labels), 3):
            self.say("  " + "   ".join(labels[i:i + 3]))
        for key, site in g.world.sites.items():
            self.say(f"  + {site.name} ({key}): {site.blurb} -- {site.coin_cost:,.0f}c")

    def chart(self, metric: str = "worth") -> None:
        g = self.game
        if not g.history:
            return self.err("nothing to chart yet")
        key = {"worth": "worth", "treasury": "treasury", "coin": "treasury",
               "pop": "pop", "mood": "pop_mood", "net": "net"}.get(metric, "worth")
        vals = [h[key] for h in g.history]
        self.say(f"  {key}: {vals[0]:,.0f} -> {vals[-1]:,.0f}",
                 "  " + sparkline(vals, 64))

    # ============================================================== commands
    def do(self, line: str) -> None:
        try:
            parts = _words(line)
        except ValueError as exc:
            return self.err(str(exc))
        if not parts:
            return
        cmd, args = parts[0].lower(), parts[1:]
        fn = COMMANDS.get(cmd)
        if not fn:
            matches = [c for c in COMMANDS if c.startswith(cmd)]
            if len(matches) == 1:
                fn = COMMANDS[matches[0]]
            else:
                return self.err(f"unknown command {cmd!r}; try `help`")
        try:
            fn(self, args)
        except (KeyError, ValueError, IndexError) as exc:
            self.err(str(exc))

    # -- individual commands --------------------------------------------
    def cmd_help(self, args: List[str]) -> None:
        """Everything there is, or `help <topic>` for one of them."""
        if args:
            topic = args[0].lower()
            if topic in ("win", "goal", "goals"):
                return self.say(self.win_text())
            if topic in HELP_TOPICS:
                return self.say(HELP_TOPICS[topic])
        self.say(HELP)

    def win_text(self) -> str:
        g = self.game
        goals = g.goals
        lines = [""]
        ways = []
        if "wealth" in goals.paths:
            ways.append(f"    WEALTH    {goals.net_worth:,.0f}c of net worth with "
                        f"{goals.population} souls under your rule.")
        if "dominion" in goals.paths:
            ways.append(f"    DOMINION  {goals.towns} towns sworn to you -- "
                        f"and still held at the end.")
        if "bells" in goals.paths and goals.wonder:
            ways.append("    THE BELLS Finish the cathedral and hold it half a year.")
        word = {1: "One way", 2: "Two ways", 3: "Three ways"}.get(len(ways), "Ways")
        lines.append(f"  {word}, inside {goals.years} years:")
        lines.append("")
        lines += ways
        lines += ["",
                  f"  You lose if your debts pass {abs(goals.bankruptcy):,.0f}c, or there is",
                  "  nowhere left that you hold. Being stormed is survivable: the keep",
                  "  comes down and the town is gutted, but a lord with a second",
                  "  settlement is still a lord."]
        return "\n".join(lines)

    def _castle_hints(self, coming: bool) -> List[Tuple[float, str]]:
        """The shape of the wall, which is where they will actually come in.

        Ranked rather than appended, and ranked hard when there is a host on
        the road: a hole in your own castle is the most urgent sentence in
        the game at that moment, and it was falling off the bottom of a list
        capped at four because it happened to be written last.
        """
        s = self.settlement()
        r = keeps.read(s.plan())
        urgent = 1.0 if coming else 0.0
        out: List[Tuple[float, str]] = []
        if r.yards and not r.shut:
            out.append((62.0 + 12.0 * urgent,
                        f"The ring at {s.name} is not closed -- the hall is "
                        f"not behind anything. `castle` draws where; "
                        f"`wall <x,y> <x,y>` shuts it."))
        left = s.outside_the_wall()
        if left:
            out.append((41.0 + 17.0 * urgent,
                        f"{len(left)} building(s) at {s.name} stand outside "
                        f"the wall, and outside is what gets burned. `castle` "
                        f"names them."))
        if len(r.weak) >= 5:
            out.append((38.0 + 17.0 * urgent,
                        f"{len(r.weak)} yards on the {r.weak_side} of "
                        f"{s.name} have no tower looking down at them, which "
                        f"is where the ladders go. `tower <x,y>` fixes it; "
                        f"`castle` shows it."))
        held = r.density(sum(s.units.values()))
        if r.yards and held < keeps.HELD * 0.6:
            out.append((36.0 + 16.0 * urgent,
                        f"{s.name} has {held:.1f} men to the yard over "
                        f"{r.yards} yards of wall. Recruit, or draw a shorter "
                        f"castle -- `castle` has both numbers."))
        return out

    def _court_hints(self) -> List[Tuple[float, str]]:
        """The politics, ranked against everything else a steward might say.

        Two of these are the most urgent sentences in the game when they are
        true -- an ally waiting on an answer with a clock running, and the
        moment before the march stops quarrelling with itself.
        """
        g = self.game
        c = g.court
        out: List[Tuple[float, str]] = []
        if c.called is not None:
            left = g.CALL_DAYS - (g.day - c.called[1])
            out.append((88.0, f"{g.world.node_name(c.called[0])} has called "
                              f"you to his war and wants an answer in {left} "
                              f"day(s). `call yes` or `call no` -- and the "
                              f"march hears which."))
        if c.coalition:
            out.append((72.0, f"{len(c.coalition)} lords have signed one "
                              f"letter against you. They march together and "
                              f"none will treat alone. `court` has the three "
                              f"ways out."))
        else:
            close = [k for k, t in g.world.towns.items() if not t.mine
                     and c.offence(k, g.day) >= chancery.COALITION_BAR * 0.7]
            if len(close) >= chancery.COALITION_NAMES:
                out.append((60.0, f"{len(close)} lords are close to signing "
                                  f"against you. Another town taken does it. "
                                  f"`court` says how close, and it costs "
                                  f"nothing to wait."))
        warm = [k for k, t in g.world.towns.items()
                if not t.mine and k not in c.allies
                and c.opinion(k, g.day) >= chancery.WARM]
        if warm and not c.allies:
            out.append((34.0, f"{g.world.node_name(warm[0])} thinks well "
                              f"enough of you to swear -- `ally {warm[0]}`. "
                              f"An ally comes when you are attacked."))
        return out

    def _kin_hints(self) -> List[Tuple[float, str]]:
        """The house is the easiest system in the game to never notice.

        Everything else announces itself -- a wall falls down, a cart stops
        earning, a granary empties. A son of sixteen with nothing to do makes
        no noise at all, and the cost of that is invisible for ten years and
        then decides a succession.
        """
        g = self.game
        out: List[Tuple[float, str]] = []
        k = g.kin
        idle = [p for p in k.living()
                if p.uid != k.head and not p.post and not p.inlaw
                and p.age(g.day) >= kinly.COMES_OF_AGE]
        if idle:
            who = idle[0]
            spare = [key for key in kinly.POSTS if not k.holder(key)]
            job = spare[0] if spare else "steward"
            where = ("" if not kinly.POSTS[job].needs
                     else " " + self._where_name(g))
            them = "him" if who.sex == "m" else "her"
            out.append((30.0, f"{who.name} is {who.age(g.day)} and has nothing "
                        f"to do. `post {who.name.split()[0].lower()} "
                        f"{job}{where}` starts {them} at something -- a skill "
                        f"only grows in the job."))
        if g.day > 180 and not any(p.married_to for p in k.people if p.alive):
            free = [p for p in k.living()
                    if not p.spouse and p.age(g.day) >= kinly.COMES_OF_AGE
                    and p.uid != k.head]
            if free:
                out.append((28.0, "Nobody of yours is married out. A match is "
                            "the only peace that does not run out -- `marry` "
                            "prices them."))
        heir = k.heir(g.day)
        lord = k.lord
        if lord is not None and lord.age(g.day) >= kinly.ELDERLY:
            if heir is None:
                out.append((62.0, f"{lord.name} is {lord.age(g.day)} and there "
                            f"is nobody behind him. The line ends where he "
                            f"does."))
            elif not heir.post:
                out.append((46.0, f"{lord.name} is {lord.age(g.day)}. "
                            f"{heir.name} takes the seat after him and has "
                            f"never held a post -- whatever they have not "
                            f"learned by then, they never will."))
        return out

    def _economy_hints(self) -> List[Tuple[float, str]]:
        """What the accounts would tell you if you asked them.

        Two of these are things the game could never say before: a shed that
        is losing money on every unit it makes looks exactly like a shed that
        is working, and a price control looks like a kindness right up until
        the shelf is empty.
        """
        g = self.game
        out: List[Tuple[float, str]] = []
        s = self.settlement()
        losing = [r for r in marginal_hands(s) if r.shut]
        if losing:
            worst = losing[0]
            verb, its = (("pays", "it costs") if len(losing) == 1
                         else ("pay", "they cost"))
            out.append((70.0, f"{ink.count(len(losing), 'shed')} of yours "
                        f"{verb} less than {its}: the {worst.name} makes "
                        f"{worst.net:,.1f}c a hand against a wage of "
                        f"{C.WAGE:.2f}c. `margin` ranks them; `close <id>` "
                        f"stops one."))
        for key, bite in sorted(g.economy.shortage.items(), key=lambda kv: -kv[1]):
            if bite > 0.15:
                out.append((88.0, f"The assize on {good(key).name} is "
                            f"{bite * 100:.0f}% under what it is worth, so "
                            f"there is none to be had at any price. `assize "
                            f"{key} off` lets it find its own."))
                break
        # Somebody said out loud that they are coming, and the whole reason
        # for saying it out loud is that you get to do something about it.
        se = g.league.season
        for f in se.fixtures:
            if f.done or f.target not in g.world.settlements:
                continue
            out.append((84.0, f"{self._name(f.who)} has said they mean to move "
                        f"on {self._name(f.target)}. `season` has the table and "
                        f"the rest of the schedule; `truce {f.who}` buys them "
                        f"off; `plans` says what they could try."))
            break
        if se.on_the_clock() == lg.PLAYER and se.undrafted():
            best = max(se.undrafted(), key=lambda p: p.grade)
            out.append((72.0, f"You are on the clock and {best.name} is the best "
                        f"man left ({best.skill} {best.grade}). `draft "
                        f"{best.name.split()[0].lower()}` takes him."))
        over = g.muster_cost()
        if over > 1.25:
            out.append((58.0, f"Your muster is past what "
                        f"{ink.count(len(g.world.settlements), 'town')} can keep: "
                        f"every soldier costs {over:.1f} times his wage. "
                        f"`standdown` or take another town."))
        # The most actionable thing there is: you are going to fall short, and
        # there are still two years to do something about it.
        left = g.goals.days - g.day
        if g.day > 150 and left > 120:
            for what, now, want, land in g.pace():
                if now <= 0 or land >= want * 0.9:
                    continue
                out.append((68.0, f"At the rate of the last season you finish "
                            f"with {land:,.0f} {what} against {want:,.0f}, and "
                            f"there are {left} days left. Something has to "
                            f"change before it is arithmetic. `status` keeps "
                            f"the count."))
                break
        a = g.accounts
        if a.inflation > 12 and g.economy.minted > 0:
            span = "a year" if a.yearly else "since you began"
            out.append((64.0, f"Prices are running {a.inflation:.0f}% {span} "
                        f"and you have struck {g.economy.minted:,.0f}c. That is "
                        f"the same sentence twice. `economy`."))
        if a.unemployment > 35 and g.day > 200:
            out.append((52.0, f"{a.unemployment:.0f}% of your hands have "
                        f"nowhere to go. Every one of them eats and none of "
                        f"them makes anything -- raise workshops, not roofs."))
        return out

    def _where_name(self, g) -> str:
        """A settlement key a `post` line can actually be typed with."""
        return next(iter(g.world.settlements), "")

    def cmd_next(self, args: List[str]) -> None:
        """Let days pass. `next 7` is a week."""
        n = int(args[0]) if args else 1
        self.game.advance(n)
        self.status()
        self._autosave()

    def _autosave(self) -> None:
        if not self.autosave_path:
            return
        try:
            self.game.save(self.autosave_path)
        except OSError as exc:                       # pragma: no cover - disk
            self.err(f"could not autosave: {exc}")

    def cmd_autosave(self, args: List[str]) -> None:
        """Write the game out after every day from now on."""
        if args and args[0].lower() in ("off", "no", "stop"):
            self.autosave_path = ""
            return self.say("  autosave off")
        self.autosave_path = args[0] if args else "marchlands.autosave"
        self._autosave()
        self.say(f"  autosaving to {self.autosave_path} after every `next`")

    def cmd_scenarios(self, args: List[str]) -> None:
        """The maps you can start on, and the houses you can start as."""
        self.say(ink.head("SCENARIOS"))
        for i, key in enumerate(CAMPAIGN, 1):
            sc = SCENARIOS[key]
            here = "  <- you are here" if key == self.game.scenario else ""
            self.say(f"  {i}. {sc.key:<14} {sc.name:<20} {sc.years:g}y{here}")
            self.say(f"     {sc.blurb}")
        self.say("", "  start one with:  python3 -m marchlands --scenario <key>")

    def cmd_briefing(self, args: List[str]) -> None:
        """Why you are here, in the words it was put to you."""
        g = self.game
        sc = SCENARIOS.get(g.scenario)
        self.say(ink.head((sc.name if sc else g.scenario).upper()))
        for line in (g.briefing or "").splitlines():
            self.say(f"  {line}")
        self.say(self.win_text())

    def cmd_hint(self, args: List[str]) -> None:
        """What a patient steward would point at next."""
        for line in self.hints():
            self.say(f"  * {line}")

    def hints(self) -> List[str]:
        """What a patient steward would point at, in the order he would."""
        g = self.game
        out: List[str] = []
        s = self.settlement()
        p = g.progress
        food = nourishment({k: s.market.stock[k] for k in RATION_GOODS})
        days = food / max(0.2 * s.population, 1e-6)
        coming = [a for a in g.armies if a.owner != "player"]
        if coming:
            a = coming[0]
            out.append(f"{a.name} is {self._where(a)} with {describe(a.units)}. "
                       f"`garrison` shows what you have; `recruit` adds to it.")
            # What they can try is decided by what you dug, and a ditch is days
            # of work where a tower is a season -- so it is worth saying now.
            mine = Works.of([b.key for b in s.buildings
                             if b.complete and b.spec.terrain == "rampart"])
            gaps = [label for have, label in
                    ((mine.moat, "a moat stops a mine and holds a ram off for days"),
                     (mine.pitch, "a pitch ditch is four days' work and breaks one assault"),
                     (mine.pits, "killing pits make every storm cost more"))
                    if not have]
            if gaps:
                out.append(f"Nothing is dug in front of {s.name}: {gaps[0]}. "
                           f"`plans {self.here}` shows what they could try.")
        sieging = [a for a in g.armies if a.owner == "player" and a.state == "besieging"]
        if sieging:
            a = sieging[0]
            out.append(f"{a.name} is set to {PLANS[a.siege.plan].name}. "
                       f"`plans {a.at}` shows what stands against that, and "
                       f"`siege {a.uid} <plan>` changes it.")
        if days < 12:
            out.append(f"{s.name} has about {ink.count(days, 'day')} of food. Build a farm, "
                       f"a mill and a bakery -- or buy bread in from Vantry.")
        if s.popularity < 40:
            out.append(f"Mood at {s.name} is {s.popularity:.0f}. `town` lists what is "
                       f"pulling it down; rations and taxes are the two big levers.")
        if s.housing(p) < s.population + 5:
            out.append(f"No roofs to spare at {s.name} -- nobody new will come. "
                       f"Build cottages (or townhouses, from the third age).")
        jobs = sum(b.spec.jobs for b in s.buildings if b.complete and b.enabled)
        if jobs > s.workforce * 1.25:
            starved = next((b.spec.name for b in s.buildings
                            if b.complete and b.enabled and b.spec.jobs
                            and not b.staffed), "")
            if starved:
                out.append(f"{s.name} has {s.workforce:.0f} hands for {jobs} jobs and "
                           f"the {starved} has none. `work` shows the queue; "
                           f"`work <building> first` reorders it.")
        if s.count("inn") and s.coverage("ale_reach", needs_running=True) < 0.5:
            out.append(f"The inn at {s.name} is serving under half the town -- "
                       f"either the ale is not arriving or nobody is working it. "
                       f"Ale is worth up to {C.ALE_MOOD:.0f} of mood.")
        free = [sh for sh in g.world.shrines.values() if not sh.taken]
        if free and not g.relics_held() and g.day > 120:
            out.append(f"{ink.count(len(free), 'shrine')} still hold their "
                       f"relics. Six days' standing lifts one and they pay "
                       f"every day after. `relics`.")
        if g.lord.captured:
            out.append(f"{g.lord.name} is held at {g.lord.ransom:,.0f}c. "
                       f"`lord ransom` buys him back.")

        # The water is a hint rather than an alarm: it never stops you, it
        # only costs you days, and a player who has never looked at `water`
        # will not know why a four-day leg took six.
        want = g.worst_unbridged()
        if want is not None and want[2].ford_limit <= waters.WORTH_BRIDGING \
                and g.treasury > waters.BRIDGE_COST * 1.6:
            out.append(f"Your carts ford the {want[2].name} on the road to "
                       f"{g.world.node_name(want[1])}, and in spring that is "
                       f"days. `water bridge {want[0]} {want[1]}` puts a "
                       f"bridge on it for {waters.BRIDGE_COST:,.0f}c -- and "
                       f"everybody else's traffic then pays you to use it.")
        down = [b for b in g.world.bridges if b.owner == "player" and b.broken]
        if down:
            out.append(f"{down[0].name} is still in the river. "
                       f"`water mend {down[0].uid}` puts it back for "
                       f"{waters.BRIDGE_COST * waters.REBUILD_SHARE:,.0f}c.")

        idle = [c for c in g.caravans if not c.running]
        if idle:
            out.append(f"Caravan {idle[0].uid} is standing idle. `scan`, then "
                       f"`auto {idle[0].uid}` puts it on the best trade going.")
        if not p.advancing and p.next_age():
            nxt = p.next_age()
            coin = nxt.cost.get("coin", 0)
            if g.treasury > coin:
                out.append(f"You can afford the {nxt.name} ({coin:,.0f}c). "
                           f"`age` shows what else it wants; `age begin` starts it.")
        if p.age >= 2 and not p.researching and any(
                x.effect("research") for x in g.world.settlements.values()):
            out.append("The guildhall is idle. `tech` lists what it could take up.")
        if p.age >= 2 and not any(x.effect("research")
                                  for x in g.world.settlements.values()):
            out.append("No guildhall yet -- without one nothing is ever researched.")
        coastal = [x for x in g.world.settlements.values()
                   if x.terrain.get("coast") and not x.effect("port")]
        if coastal and p.age >= 2:
            out.append(f"{coastal[0].name} is on the water. A harbour there opens "
                       f"the sea, and a hull carries four carts' worth.")
        if g.world.sites and g.treasury > 6000:
            key = min(g.world.sites, key=lambda k: g.world.sites[k].coin_cost)
            site = g.world.sites[key]
            out.append(f"You could settle {site.name} for {site.coin_cost:,.0f}c. "
                       f"One hill will not hold {g.goals.population} souls.")
        # The body above is already in the order a steward would raise things,
        # so it keeps that order among itself. What the newer systems have to
        # say is ranked against it rather than appended to it: a hint that can
        # only appear on a quiet day is a system nobody is ever told about,
        # which is how the house and the accounts both went unmentioned for a
        # hundred turns each while the fourth line was about a guildhall.
        ranked = [(50.0 - 0.01 * i, text) for i, text in enumerate(out)]
        ranked += (self._kin_hints() + self._economy_hints()
                   + self._castle_hints(bool(coming))
                   + self._court_hints())
        ranked.sort(key=lambda row: -row[0])
        picked = [text for _, text in ranked][:4]
        if not picked:
            picked.append("Nothing pressing. `scan` for a better route, `war` to "
                          "see who is arming, `age` for the long game.")
        return picked

    def cmd_status(self, args: List[str]) -> None:
        """The day at a glance: purse, souls, towns, carts, the ledger."""
        self.status()

    def cmd_town(self, args: List[str]) -> None:
        """One settlement in full: what stands, who works it, what moves the mood."""
        if args:
            key = self._node(args[0])
            if key in self.game.world.settlements:
                self.here = key
        self.town_view()

    def cmd_view(self, args: List[str]) -> None:
        """The holding drawn in perspective, from the corner."""
        flat = any(a.lower() in ("flat", "plan", "map") for a in args)
        places = [a for a in args if a.lower() not in ("flat", "plan", "map")]
        if places:
            key = self._node(places[0])
            if key in self.game.world.settlements:
                self.here = key
        self.plan_view(flat=flat)

    def cmd_watch(self, args: List[str]) -> None:
        """Let the days run and watch the town work.

        On a real terminal this redraws in place, which is the closest a
        console gets to the thing you actually miss: seeing the place move.
        """
        days = max(1, min(120, int(args[0]) if args and args[0].isdigit() else 20))
        live = ink.COLOUR
        for _ in range(days):
            self.game.tick()
            if live:
                self.out.write("\033[H\033[2J")
            self.plan_view()
            for m in self.game.messages[-3:]:
                self.say("  " + ink.c("*", ink.FAINT) + " " + self._tint(m))
            if self.game.over:
                break
            if live:
                self.out.flush()
                time.sleep(0.28)
        self.status()

    def cmd_stores(self, args: List[str]) -> None:
        """What is in the granary, what it fetches, and what is running down."""
        self.stores(self._node(args[0]) if args else None)

    def cmd_market(self, args: List[str]) -> None:
        """One town's prices and what it is short of."""
        if not args:
            return self.err("market <town>")
        self.market_view(args[0])

    def cmd_prices(self, args: List[str]) -> None:
        """One good's price everywhere you have eyes."""
        if not args:
            return self.err("prices <good>")
        self.price_view(args[0])

    def cmd_chain(self, args: List[str]) -> None:
        """What a good is made of, and what it goes into."""
        if not args:
            return self.err("chain <good>")
        self.chain_view(args[0])

    def cmd_buildings(self, args: List[str]) -> None:
        """Everything you could raise, and what each wants."""
        self.buildings_view(args[0] if args else "")

    def cmd_info(self, args: List[str]) -> None:
        """One building in full: land, hands, recipe, effects."""
        if not args:
            return self.err("info <building>")
        self.building_info(args[0])

    def cmd_build(self, args: List[str]) -> None:
        """Raise something. It costs coin, materials and days."""
        if not args:
            return self.err("build <building> [town]")
        key = resolve_building(args[0])
        town = self._node(args[1]) if len(args) > 1 else self.here
        self.say("  " + self.game.build(town, key))

    def cmd_raze(self, args: List[str]) -> None:
        """Pull something down and take back what you can."""
        uid = self._which(args, "raze <building>")
        if uid is None:
            return
        s = self.settlement()
        b = s.demolish(uid)
        self.say(f"  {b.spec.name} pulled down" if b else "  no such building")

    def cmd_close(self, args: List[str]) -> None:
        """Shut a shed, or open it again. Wages stop; so does the output."""
        uid = self._which(args, "close <building>")
        if uid is None:
            return
        s = self.settlement()
        b = s.find(uid)
        if not b:
            return self.err("no such building")
        b.enabled = not b.enabled
        self.say(f"  {b.spec.name} {'opened' if b.enabled else 'closed'}")

    def cmd_staff(self, args: List[str]) -> None:
        """staff <building> <hands|free> -- put hands at one shed by name."""
        st = self.settlement()
        if not args:
            if not st.pins:
                return self.say("  nobody is pinned anywhere; the queue decides "
                                "(`work` to see it, `staff <building> <n>` to override it)")
            self.say(ink.head("PINNED HANDS", st.name.upper()))
            for uid, n in st.pins.items():
                b = st.find(uid)
                if b is None:
                    continue
                self.say(f"  {ink.c(ink.pad(str(uid), 5), ink.DIM)}"
                         f"{ink.pad(b.spec.name, 18)} {n} asked, {b.staffed} seated")
            return
        uid = self._which(args, "staff <building> <hands|free>")
        if uid is None:
            return
        if len(args) < 2:
            return self.err("staff <building> <hands|free>")
        if args[1] in ("free", "none", "0"):
            return self.say("  " + st.pin_hands(uid, 0))
        try:
            hands = int(args[1])
        except ValueError:
            return self.err(f"{args[1]!r} is not a number of hands -- "
                            "staff <building> <hands|free>")
        self.say("  " + st.pin_hands(uid, hands))

    def cmd_move(self, args: List[str]) -> None:
        """move <building> <hands> [<from>:<n> ...] -- send hands off one shed to another."""
        usage = "move <building> <hands> [<from building>:<hands> ...]"
        uid = self._which(args, usage)
        if uid is None:
            return
        if len(args) < 2:
            return self.err(usage)
        try:
            hands = int(args[1])
            sources = {}
            for part in args[2:]:
                s, _, n = part.partition(":")
                sources[int(s)] = sources.get(int(s), 0) + int(n)
        except ValueError:
            return self.err(usage)
        self.say("  " + self.settlement().move_hands(uid, hands, sources))

    def cmd_work(self, args: List[str]) -> None:
        """Who gets hands first when there are not enough of them."""
        st = self.settlement()
        if not args:
            self.say(ink.head("WHO GETS HANDS FIRST", st.name.upper()),
                     f"  {st.workforce:.0f} hands for "
                     f"{sum(b.spec.jobs for b in st.buildings if b.complete and b.enabled)}"
                     f" jobs")
            bands: Dict[int, List[str]] = {}
            for b in st.buildings:
                if b.complete and b.spec.jobs:
                    bands.setdefault(st.band(b.key), []).append(b.spec.name)
            for value, label in sorted(((v, k) for k, v in st.BANDS.items()),
                                       reverse=True):
                names = sorted(set(bands.get(value, [])))
                if names:
                    self.say(f"  {label:<7} {ink.c(', '.join(names), ink.DIM)}")
            starved = sorted({b.spec.name for b in st.buildings
                              if b.complete and b.enabled and b.spec.jobs
                              and b.staffed < b.spec.jobs})
            if starved:
                self.say("", "  going short  "
                         + ink.c(", ".join(starved), ink.AMBER))
            self.say("", ink.c("  work <building> first|early|normal|late|last",
                               ink.DIM))
            return
        if len(args) < 2:
            return self.err("work <building> first|early|normal|late|last")
        key = resolve_building(args[0])
        if not key:
            return self.err(f"no building called {args[0]}")
        self.say("  " + st.set_band(key, args[1].lower()))

    def cmd_ration(self, args: List[str]) -> None:
        """How much the town eats. Mood follows."""
        s = self.settlement()
        if not args:
            return self.say(f"  rations at {s.name}: {C.RATION_LABELS[s.ration_level]}")
        s.ration_level = _level(args[0], C.RATION_LABELS)
        self.say(f"  {s.name} now on {C.RATION_LABELS[s.ration_level]} rations")

    def cmd_tax(self, args: List[str]) -> None:
        """What you take, what it collects, and what it costs in goodwill."""
        s = self.settlement()
        if args:
            s.tax_level = _level(args[0], C.TAX_LABELS)
            return self.say(f"  {s.name} now on {C.TAX_LABELS[s.tax_level]} taxes")
        # Every band, priced. A dial whose bands you cannot compare before
        # pulling it is not a decision, it is a surprise -- and two of these
        # collect less than the band below them, which nobody would guess.
        self.say(ink.head(f"THE TAX AT {s.name.upper()}",
                          f"{s.population:,.0f} souls"))
        self.say(ink.c("  band        asks    collects    mood    ", ink.DIM))
        best = max(C.TAX_LEVELS, key=lambda b: s.tax_take(b))
        for band in sorted(C.TAX_LEVELS):
            rate, mood = C.TAX_LEVELS[band]
            asks, gets = rate * s.population, s.tax_take(band)
            here = band == s.tax_level
            note = []
            if band == best:
                note.append(ink.c("the most there is to collect today", ink.GOLD))
            if gets < asks - 0.5:
                note.append(ink.c(f"{100 * (1 - gets / max(asks, 1e-9)):.0f}% of it "
                                  f"never reaches you", ink.RUST))
            self.say(f"  {ink.c(ink.pad(C.TAX_LABELS[band], 10), ink.PARCH if here else ink.INK)}"
                     f"{asks:>7,.0f}c{gets:>10,.0f}c"
                     f"{ink.c(f'{mood:>+8.0f}', ink.LEAF if mood > 0 else ink.BLOOD)}"
                     + ("  " + ink.c("<-- here", ink.GOLD) if here else "")
                     + ("   " + " · ".join(note) if note else ""))
        self.say("", ink.c("  A heavy rate is a lever on behaviour before it is a "
                           "lever on revenue: the day that is\n  taxed away stops "
                           "being worked, and the goods go over the wall instead "
                           "of through\n  the market. `tax <band>` sets it.", ink.DIM))

    def cmd_garrison(self, args: List[str]) -> None:
        """Soldiers at home, and what they are costing you."""
        s = self.settlement(self._node(args[0]) if args else None)
        p = self.game.progress
        self.say(ink.head(f"{s.name} garrison"),
                 f"  {s.garrison_line()}",
                 f"  strength {host_strength(s.units):.0f}, "
                 f"upkeep {host_upkeep(s.units):.0f}c/day",
                 f"  wall {s.wall_hp:,.0f}/{s.wall_max(p):,.0f}"
                 f"   works {s.effect('defense'):.0f}"
                 f"   battlements {s.effect('battlement'):.0f}")

    def cmd_units(self, args: List[str]) -> None:
        """Every soldier you could raise, what beats what, and the price."""
        p = self.game.progress
        self.say(ink.head("WHO YOU MAY MUSTER", p.age_name()),
                 "  key            name              age  coin  arms              "
                 "atk  def   hp  class")
        for k, u in UNITS.items():
            if u.needs_tech and u.needs_tech not in p.researched:
                continue
            arms = " ".join(f"{v:g} {g}" for g, v in u.equipment.items())
            mark = " " if u.age <= p.age else "-"
            self.say(f" {mark}{k:<14} {u.name:<17} {u.age:>2}  {u.coin:>5.0f}"
                     f"  {arms:<18}{u.attack:>4.0f} {u.defense:>4.0f} {u.hp:>4.0f}"
                     f"  {u.unit_class}")
        self.say("  (- means a later age; arms come out of your own stores)")

    def cmd_recruit(self, args: List[str]) -> None:
        """Arm and pay men. They come out of your own workforce."""
        if not args:
            return self.err("recruit <soldier> [number] [town]")
        key = resolve_unit(args[0])
        count = int(args[1]) if len(args) > 1 else 1
        town = self._node(args[2]) if len(args) > 2 else self.here
        self.say("  " + self.game.recruit(town, key, count))

    def cmd_host(self, args: List[str]) -> None:
        """host <town> <soldier> <n> [<soldier> <n> ...]"""
        if len(args) < 3:
            return self.err("host <town> <soldier> <n> [<soldier> <n> ...]")
        town = self._node(args[0])
        units: Dict[str, int] = {}
        rest = args[1:]
        for i in range(0, len(rest) - 1, 2):
            units[resolve_unit(rest[i])] = int(rest[i + 1])
        a, why = self.game.raise_host(town, units)
        if not a:
            return self.err(why)
        self.say(f"  {a.name} stands ready at {self._name(town)}: {describe(a.units)}")

    def cmd_army(self, args: List[str]) -> None:
        """Your hosts, where they are and what they are doing."""
        g = self.game
        if args:
            a = g.army(int(args[0]))
            if not a:
                return self.err(f"no host {args[0]}")
            self.say(ink.head(a.name, self._where(a)),
                     f"  where     {self._where(a)}",
                     f"  strength  {host_strength(a.units):.0f}"
                     f"   upkeep {a.upkeep:.0f}c/day"
                     f"   siege {a.siege_power:.0f}",
                     f"  host      {describe(a.units)}")
            for line in a.log[-8:]:
                self.say(f"     . {line}")
            return
        self.say(ink.head("HOSTS IN THE FIELD"))
        for a in g.armies:
            side = "yours" if a.owner == "player" else f"{self._name(a.home)}"
            self.say(f"  [{a.uid}] {a.name:<22} {side:<12} {self._where(a):<24}"
                     f" {describe(a.units)}")
        for key, s in g.world.settlements.items():
            if s.units:
                self.say(f"   -   garrison of {s.name:<14} {'':12} {'in the walls':<24}"
                         f" {s.garrison_line()}")
        if not g.armies and not any(s.units for s in g.world.settlements.values()):
            self.say("  nobody is under arms")

    def cmd_plans(self, args: List[str]) -> None:
        """What a castle is made of, and what each answer to it costs."""
        g = self.game
        works, name = None, ""
        if args:
            key = self._node(args[0])
            if key in g.world.towns:
                t = g.world.towns[key]
                seen, age = g.known(key)
                if age < 0:
                    return self.err(f"you have never had eyes on {t.name}. "
                                    f"Send a cart or a host and look.")
                works, name = t.works(seen.get("prosperity")), t.name
                if age > 30:
                    self.say(ink.c(f"  (this is {ink.count(age, 'day')} out of date -- he has "
                                   f"had a season to dig)", ink.AMBER))
            elif key in g.world.settlements:
                s = g.world.settlements[key]
                works = Works.of([b.key for b in s.buildings
                                  if b.complete and b.spec.terrain == "rampart"])
                name = s.name
            else:
                return self.err(f"no such place: {args[0]}")
        self.say(ink.head("WAYS INTO A CASTLE", name.upper()))
        if works is not None:
            standing = []
            if works.stone:
                standing.append("stone curtain")
            if works.gate:
                standing.append("gatehouse")
            for n, label in ((works.towers, "tower"), (works.moat, "moat"),
                             (works.pitch, "pitch ditch"), (works.pits, "killing pit"),
                             (works.oil, "oil pot")):
                if n:
                    standing.append(f"{n}x {label}" if n > 1 else label)
            self.say("  they have  " + ink.c(", ".join(standing) or "an open town",
                                             ink.BONE))
        for key, plan in PLANS.items():
            need = []
            if plan.needs_siege:
                need.append(f"{plan.needs_siege:.0f} engine power")
            if plan.needs_engineers:
                need.append("engineers")
            self.say("",
                     f"  {ink.c(plan.name, ink.GOLD)}  "
                     + ink.c(f"({', '.join(need)})" if need else "(needs nothing)",
                             ink.DIM))
            self.say(f"     {ink.c(plan.blurb, ink.DIM)}")
            if works is not None:
                answered = works.answers(key)
                if answered:
                    self.say("     " + ink.c("against you here: " + "; ".join(answered),
                                              ink.BLOOD))
                else:
                    self.say("     " + ink.c("nothing here answers it", ink.LEAF))
        self.say("", ink.c("  siege <host> <plan> sets how a host of yours goes in.",
                           ink.DIM))

    def cmd_siege(self, args: List[str]) -> None:
        """Choose how a host of yours goes at a wall."""
        g = self.game
        if not args:
            hosts = [a for a in g.armies if a.owner == "player"]
            if not hosts:
                return self.err("you have no host in the field")
            self.say(ink.head("SIEGE ORDERS"))
            for a in hosts:
                self.say(f"  [{a.uid}] {a.name:<22} "
                         f"{PLANS[a.siege.plan].name:<22} {self._where(a)}")
            return
        if len(args) < 2:
            return self.err("siege <host> <" + "|".join(PLANS) + ">")
        a = g.army(int(args[0]))
        if not a or a.owner != "player":
            return self.err(f"no host of yours numbered {args[0]}")
        key = args[1].lower()
        if key not in PLANS:
            return self.err(f"no such plan; choose from {', '.join(PLANS)}")
        plan = PLANS[key]
        ok, why = plan.viable(a.siege_power, a.units.get("engineer", 0.0))
        if not ok:
            return self.err(f"{a.name} cannot {plan.name}: {why}")
        if a.siege.plan != key:
            a.siege = SiegeState(plan=key)      # a new plan starts from nothing
        self.say(f"  {a.name} will {ink.c(plan.name, ink.GOLD)}.")
        self.say(f"  {ink.c(plan.blurb, ink.DIM)}")

    def cmd_march(self, args: List[str]) -> None:
        """Send a host somewhere, or bring it home."""
        if len(args) < 2:
            return self.err("march <host> <place>")
        uid = int(args[0])
        # Yours only. `game.march` is also how the world sends its own hosts
        # home, so the check belongs here at the player's end rather than in
        # there -- but it does have to exist: the command took any number in
        # the army list, and a player who typed a besieger's could order the
        # host outside his own wall to go somewhere else.
        a = self.game.army(uid)
        if a is not None and a.owner != "player":
            return self.err(f"host {uid} is not yours to command")
        self.say("  " + self.game.march(uid,
                                        self._node(args[1], shrines=True)))

    def cmd_campaign(self, args: List[str]) -> None:
        """Where you are in the Marcher Chronicle, and what you are carrying."""
        run = self.run
        if run is None:
            return self.say(
                ink.head("THE MARCHER CHRONICLE"),
                ink.c("  You are playing a single game, not the campaign.",
                      ink.DIM),
                ink.c("  Start it with:  python3 -m marchlands --campaign",
                      ink.DIM))
        ch = run.current
        self.say(ink.head("THE MARCHER CHRONICLE",
                          f"chapter {min(run.chapter + 1, len(CHAPTERS))}"
                          f" of {len(CHAPTERS)}"))
        for line in run.standing():
            self.say(line)
        self.say("", f"  this chapter teaches {ink.c(ch.teaches, ink.GOLD)}")
        carry = run.carry
        self.say(f"  you brought    {ink.coin(carry.purse)}c, "
                 f"{len(carry.techs)} things your house had already worked out",
                 f"  renown         {carry.renown}")
        # The house is the part of a campaign that is actually a campaign, so
        # it belongs on the screen that is about the campaign.
        k = self.game.kin
        lord = k.lord
        if lord is not None:
            years = carry.days // C.DAYS_PER_YEAR
            best = max(kinly.SKILLS, key=lambda sk: lord.xp.get(sk, 0.0))
            reads = (f", {best} {lord.level(best)}" if lord.level(best)
                     else ", untried")
            self.say(f"  your house     {lord.name}, {lord.age(self.game.day)}"
                     f"{reads} · {len(k.living())} of the line"
                     + (f" · {years} years in" if years else ""))
            posted = [p for p in k.living() if p.post and p.post != "head"]
            if posted:
                self.say("  " + ink.c("               " + "; ".join(
                    f"{p.name} {p.doing(self._name)}" for p in posted[:3]),
                    ink.DIM))

    def cmd_chronicle(self, args: List[str]) -> None:
        """Your reign, read back to you."""
        g = self.game
        least = ROUTINE if args and args[0].lower() in ("all", "full") else NOTABLE
        entries = g.chronicle.read(least=least, limit=60)
        if not entries:
            return self.say(ink.head("THE CHRONICLE"),
                            ink.c("  Nothing worth writing down has happened yet.",
                                  ink.DIM))
        # The head used to count the whole book while the page showed only the
        # days worth telling, which made it look as though entries were lost.
        total = len(g.chronicle)
        right = (ink.count(total, "entry") if len(entries) == total
                 else f"{len(entries)} of {ink.count(total, 'entry')}")
        self.say(ink.head("THE CHRONICLE", right))
        chapter = None
        for e in entries:
            if e.chapter != chapter:
                chapter = e.chapter
                name = CHAPTERS_BY_KEY[chapter].name if chapter in CHAPTERS_BY_KEY \
                    else ""
                if name:
                    self.say("", ink.c(f"  -- {name} --", ink.GOLD))
            colour = ink.BONE if e.weight >= MOMENTOUS else ink.DIM
            self.say(f"  {ink.c(ink.pad(e.stamp(), 13), ink.PLUM)} "
                     + ink.c(e.text.strip("* "), colour))
        if len(entries) < total:
            self.say("", ink.c("  `chronicle all` reads the quiet days too.",
                               ink.DIM))

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

    def cmd_ask(self, args: List[str]) -> None:
        """Ask the town how it is. Somebody will tell you."""
        g = self.game
        s = self.settlement(self._resolve_here(args))
        how_many = 3 if args and args[-1].lower() in ("all", "more") else 2
        self.say(ink.head(f"IN THE STREET AT {s.name.upper()}",
                          f"mood {s.popularity:.0f}"))
        for who, said in voices.speak(s, g, voices.street_rng(s, g), how_many):
            self.say(f"  {ink.c(who, ink.DIM)}")
            rows = _wrap(said, 66)
            for i, line in enumerate(rows):
                head = "“" if i == 0 else " "
                tail = "”" if i == len(rows) - 1 else ""
                self.say(ink.c(f"    {head}{line}{tail}", ink.PARCH))
        self.say("", ink.c("  The same facts as `town`, from somebody who has "
                           "to live in it.", ink.DIM))

    def _resolve_here(self, args: List[str]) -> str:
        if not args:
            return ""
        want = args[0].lower()
        for key, s in self.game.world.settlements.items():
            if want in (key.lower(), s.name.lower()):
                return key
        return ""

    # ------------------------------------------------------------ the castle
    def _coords(self, word: str):
        """`12,9` -- the one thing a drawing command has to be able to read."""
        try:
            x, _, y = word.partition(",")
            t = (int(x), int(y))
        except ValueError:
            return None
        return t if keeps.on_map(t) else None

    def _run(self, args: List[str]):
        """One tile, or a straight run between two. Diagonals go by the longer
        axis, which draws the line somebody meant rather than the line they
        typed."""
        here = self._coords(args[0]) if args else None
        if here is None:
            return None
        if len(args) < 2:
            return [here]
        there = self._coords(args[1])
        if there is None:
            return None
        (x0, y0), (x1, y1) = here, there
        n = max(abs(x1 - x0), abs(y1 - y0))
        if n > 60:
            return None
        if n == 0:
            return [here]
        out = []
        for i in range(n + 1):
            out.append((round(x0 + (x1 - x0) * i / n),
                        round(y0 + (y1 - y0) * i / n)))
        return out

    def _draw(self, kind: str, args: List[str], word: str) -> None:
        """Lay one kind of thing along a run, spending what is in hand."""
        s = self.settlement()
        tiles = self._run(args)
        if not tiles:
            return self.err(f"{word} <x,y> [<x,y>] -- `castle` has the map")
        castle = s.take_the_pen()
        hand = keeps.unlaid(s.buildings, castle).get(kind, 0)
        laid, over = 0, 0
        for t in tiles:
            if castle.at(t) == kind:
                continue
            back = castle.at(t)
            if laid >= hand + (1 if back == kind else 0):
                over += 1
                continue
            castle.lay(t, kind)
            laid += 1
        s.castle = castle
        name = {"timber": "timber wall", "stone": "stone wall", "tower": "tower",
                "gate": "gatehouse", "moat": "moat", "pitch": "pitch ditch",
                "pits": "killing pits"}.get(kind, kind)
        if laid:
            self.say(f"  {laid} yard(s) of {name} laid")
        if over:
            self.say(ink.c(f"  {over} more than you have paid for -- "
                           f"`build {self._to_buy(kind)}` buys the next length",
                           ink.AMBER))
        if not laid and not over:
            self.say(ink.c("  already laid", ink.DIM))
        self._castle_warn(s)

    @staticmethod
    def _to_buy(kind: str) -> str:
        return {"timber": "palisade", "stone": "stone_wall", "tower": "wall_tower",
                "gate": "gatehouse", "moat": "moat", "pitch": "pitch_ditch",
                "pits": "kill_pit"}.get(kind, kind)

    def _castle_warn(self, s) -> None:
        r = keeps.read(s.plan())
        if not r.yards:
            return
        if not r.shut:
            self.say(ink.c("  the ring is not closed: the hall is not behind "
                           "anything", ink.BLOOD))
        left = s.outside_the_wall()
        if left:
            self.say(ink.c(f"  {len(left)} building(s) stand outside it",
                           ink.AMBER))

    def cmd_wall(self, args: List[str]) -> None:
        """Lay a length of wall. `wall 12,9 12,16` runs it down the east side."""
        s = self.settlement()
        hand = keeps.unlaid(s.buildings, s.take_the_pen())
        kind = keeps.STONE if hand.get(keeps.STONE, 0) > 0 else keeps.TIMBER
        if args and args[0].lower() in ("stone", "timber"):
            kind = args[0].lower()
            args = args[1:]
        self._draw(kind, args, "wall")

    def cmd_tower(self, args: List[str]) -> None:
        """Put a tower on the wall. It covers the yards within an arrow of it."""
        self._draw(keeps.TOWER, args, "tower")

    def cmd_gate(self, args: List[str]) -> None:
        """Put the gatehouse where the road comes in."""
        self._draw(keeps.GATE, args, "gate")

    def cmd_moat(self, args: List[str]) -> None:
        """Dig water in front of the wall."""
        self._draw(keeps.MOAT, args, "moat")

    def cmd_pitchditch(self, args: List[str]) -> None:
        """Dig a pitch ditch in front of the wall."""
        self._draw(keeps.PITCH, args, "pitch")

    def cmd_pits(self, args: List[str]) -> None:
        """Stake killing pits under the wall."""
        self._draw(keeps.PITS, args, "pits")

    def cmd_unwall(self, args: List[str]) -> None:
        """Take a length back down. What comes down goes back in hand."""
        s = self.settlement()
        tiles = self._run(args)
        if not tiles:
            return self.err("unwall <x,y> [<x,y>]")
        castle = s.take_the_pen()
        gone = sum(1 for t in tiles if castle.clear(t))
        s.castle = castle
        self.say(f"  {gone} yard(s) pulled down" if gone
                 else ink.c("  nothing standing there", ink.DIM))
        self._castle_warn(s)

    def cmd_castle(self, args: List[str]) -> None:
        """The castle, drawn, and what a besieger makes of it."""
        g = self.game
        s = self.settlement(self._resolve_here(args))
        castle = s.plan()
        r = keeps.read(castle)
        self.say(ink.head(f"THE CASTLE AT {s.name.upper()}",
                          "drawn" if s.castle.drawn else "as your steward laid it"))
        if not r.yards:
            self.say(ink.c("  No wall at all. `build palisade` buys the first "
                           "28 yards of it.", ink.DIM))
            return
        self._castle_map(s, castle, r)
        per = r.density(sum(s.units.values()))
        rows = [
            ("the wall", f"{r.yards} yards -- {r.stone} stone, {r.timber} timber, "
                         f"{r.towers} tower(s), {r.gates} gatehouse(s)"),
            ("it shuts in", f"{r.inside} plots"
                            + ("" if r.shut else "  -- and the ring is OPEN")),
            ("towers cover", f"{r.covered} of {r.yards} yards"
                             if r.towers else "nothing: there are no towers"),
        ]
        if r.weak:
            rows.append(("the weak side",
                         f"{len(r.weak)} yards on the {r.weak_side} with nothing "
                         f"looking down at them"))
        rows.append(("men to the yard",
                     f"{per:.1f} -- " + ("thin" if per < keeps.HELD * 0.75 else
                                         "held" if per < keeps.HELD * 1.6 else
                                         "deep")))
        if r.depth > 1:
            rows.append(("walls to the hall", f"{r.depth}"))
        out = s.outside_the_wall()
        if out:
            names = [b.spec.name for b in s.buildings if b.uid in out]
            rows.append(("outside it", f"{len(out)} building(s) nobody is "
                                       f"defending: " + ", ".join(names[:4])
                         + (" ..." if len(names) > 4 else "")))
        for label, text in rows:
            self.say(f"  {ink.c(ink.pad(label, 18), ink.DIM)}{text}")
        hand = {k: v for k, v in keeps.unlaid(s.buildings, castle).items() if v > 0}
        if hand:
            self.say("", "  " + ink.c("in hand  ", ink.DIM)
                     + ", ".join(f"{v} {k}" for k, v in sorted(hand.items())))
        self.say("", ink.c("  wall / tower / gate / moat / pits / pitch <x,y> "
                           "[<x,y>] draw it; unwall takes it down.", ink.DIM))
        _ = g

    def _castle_map(self, s, castle, r) -> None:
        """The drawing itself, which is the whole point of it being a drawing.

        Cropped to what is standing plus a yard of air, so a small castle does
        not print thirty lines of empty field around itself.
        """
        from .layout import plan_for
        plan = plan_for(s)
        here = {(b.x, b.y): b for b in plan.buildings}
        tiles = set(castle.pieces) | set(here)
        if not tiles:
            return
        x0 = max(0, min(t[0] for t in tiles) - 1)
        x1 = min(keeps.SIDE - 1, max(t[0] for t in tiles) + 1)
        y0 = max(0, min(t[1] for t in tiles) - 1)
        y1 = min(keeps.SIDE - 1, max(t[1] for t in tiles) + 1)
        inside = keeps.enclosed(castle)
        cover = keeps.covered(castle)
        weak = set(r.weak)
        glyph = {keeps.STONE: "#", keeps.TIMBER: "+", keeps.TOWER: "T",
                 keeps.GATE: "G", keeps.MOAT: "~", keeps.PITCH: ":",
                 keeps.PITS: "^"}
        self.say("")
        self.say("     " + ink.c("".join(str(x % 10) for x in range(x0, x1 + 1)),
                                 ink.DIM))
        for y in range(y0, y1 + 1):
            row = ""
            for x in range(x0, x1 + 1):
                t = (x, y)
                kind = castle.at(t)
                if kind:
                    ch = glyph.get(kind, "?")
                    if kind in keeps.DITCH_KINDS:
                        row += ink.c(ch, ink.INK)
                    elif t in weak:
                        row += ink.c(ch, ink.BLOOD)
                    elif t in cover or kind == keeps.TOWER:
                        row += ink.c(ch, ink.GOLD)
                    else:
                        row += ink.c(ch, ink.BONE)
                elif t in here:
                    b = here[t]
                    if b.terrain not in ("urban", "rampart"):
                        row += ink.c("v", ink.DIM)     # a farm belongs outside
                    elif t in inside:
                        row += ink.c("o", ink.PARCH)
                    else:
                        row += ink.c("x", ink.AMBER)
                else:
                    row += ink.c("." if t in inside else " ", ink.DIM)
            self.say(f"  {ink.c(f'{y:>2}', ink.DIM)} {row}")
        self.say("", ink.c("     # stone  + timber  T tower  G gate  ~ moat  "
                           ": pitch  ^ pits", ink.DIM))
        self.say(ink.c("     o a workshop inside   ", ink.DIM)
                 + ink.c("x one left outside", ink.AMBER)
                 + ink.c("   v field and wood", ink.DIM)
                 + ink.c("   gold is covered by a tower, ", ink.DIM)
                 + ink.c("red is not", ink.BLOOD))

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
        self.say("  " + ink.c(lordkind.reputation(key, g.known(key)[1] >= 0),
                              ink.BONE))
        rows = c.reasons(key, g.day)
        if not rows:
            self.say("", ink.c("  He has nothing written down about you "
                               "either way.", ink.DIM))
        for label, value, decay in rows:
            self.say("  " + ink.c(ink.pad(label, 46), ink.DIM)
                     + ink.c(f"{value:>+6.0f}", self._standing_colour(value))
                     + ink.c("  forever" if not decay
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
                     + (ink.c("  -- that is you", ink.BLOOD) if at_you else ""))
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

    # --------------------------------------------------------- the economy
    def cmd_economy(self, args: List[str]) -> None:
        """The national accounts: what a purse is worth, and what it was."""
        g = self.game
        econ, a = g.economy, g.accounts
        self.say(ink.head("THE ACCOUNTS", f"{a.cpi:,.0f} on the index"))
        # A year back if there is a year; otherwise the oldest day there is,
        # and on the first morning there is none at all.
        year = econ.at(int(C.DAYS_PER_YEAR)) or econ.at(max(0, len(econ.series) - 1))
        real_purse = 100.0 * g.treasury / max(a.cpi, 1e-9)
        rows = [
            ("prices", f"{a.cpi:,.0f}", "100 is every good at what it is worth",
             ink.AMBER if a.cpi > 160 else ink.INK),
            ("inflation", f"{a.inflation:+.1f}%",
             "a year, from the basket the town actually buys",
             ink.BLOOD if a.inflation > 8 else
             ink.SEA if a.inflation < -4 else ink.LEAF),
            ("your purse", f"{real_purse:,.0f}c",
             f"{g.treasury:,.0f}c, in the coin of the first year",
             ink.GOLD),
            ("made today", f"{a.real:,.0f}", "at settled prices -- real output",
             ink.INK),
            ("idle hands", f"{a.unemployment:.0f}%",
             "of the workforce with no job to go to",
             ink.BLOOD if a.unemployment > 30 else ink.INK),
            ("coin about", f"{econ.money:,.0f}c",
             f"struck by you: {econ.minted:,.0f}c" if econ.minted
             else "none of it yours to make -- yet", ink.INK),
            ("velocity", f"{a.velocity:.1f}",
             "times a year each penny turns over", ink.DIM),
        ]
        for label, value, note, colour in rows:
            self.say(f"  {ink.c(ink.pad(label, 12), ink.DIM)}"
                     f"{ink.c(ink.pad(value, 11, '>'), colour)}   "
                     f"{ink.c(note, ink.DIM)}")
        if year is not None and len(econ.series) > 30:
            self.say("", "  prices  " + ink.spark(
                [row["cpi"] for row in econ.series[-C.DAYS_PER_YEAR:]], 48))
            self.say("  idle    " + ink.spark(
                [100.0 * max(0.0, row["workforce"] - row["employed"])
                 / max(row["workforce"], 1.0)
                 for row in econ.series[-C.DAYS_PER_YEAR:]], 48, ink.RUST))
        if econ.assize:
            self.say("")
            for key, cap in sorted(econ.assize.items()):
                bite = econ.shortage.get(key, 0.0)
                worth = g.home().market.fundamental(key)
                self.say("  " + ink.c(
                    f"assize   {good(key).name} held at {cap:,.1f}c "
                    f"(worth {worth:,.1f}c)"
                    + (f" -- {bite * 100:.0f}% short" if bite > 0.01
                       else " -- above the market, so it does nothing"),
                    ink.BLOOD if bite > 0.01 else ink.DIM))
            if any(v > 0.01 for v in econ.shortage.values()):
                self.say(ink.c(
                    "           The index above is what may be charged, so it "
                    "does not show this. That is\n           what a price "
                    "control does to a price index, and to everyone who reads "
                    "one.", ink.DIM))
        self.say("", ink.c("  `margin` what a hand is worth · `surplus <good>` "
                           "what a toll costs · `advantage <good> <town>`", ink.DIM))

    def cmd_margin(self, args: List[str]) -> None:
        """Every shed as a firm: hire while the next hand beats the wage."""
        s = self.settlement(args[0] if args else "")
        rows = marginal_hands(s)
        if not rows:
            return self.say("  nothing here makes anything yet")
        self.say(ink.head(f"{s.name.upper()}: THE NEXT HAND",
                          f"a hand costs {C.WAGE:.2f}c a day"))
        self.say(ink.c("   id  shed                staff    made   fetches"
                       "    eats      net", ink.DIM))
        for r in rows:
            verdict = ("worth hiring" if r.hire and r.staffed < r.jobs else
                       "shut it" if r.shut else
                       "full" if r.staffed >= r.jobs else "idle")
            colour = (ink.LEAF if r.hire else ink.BLOOD if r.shut else ink.DIM)
            self.say(f"  {r.uid:>3}  {ink.pad(r.name, 18)}"
                     f"{r.staffed:>3}/{r.jobs:<3}"
                     f"{r.units:>7.2f}{r.value:>9.2f}c{r.input_cost:>8.2f}c"
                     f"{ink.c(f'{r.net:>8.2f}c', colour)}  "
                     f"{ink.c(verdict, colour)}")
        self.say("", ink.c(
            "  The value of what one more pair of hands would make, less what "
            "they would use\n  up making it. Hire while that beats the wage; "
            "close what sits under it.", ink.DIM))

    def cmd_surplus(self, args: List[str]) -> None:
        """What a market is worth to both sides, and what a toll costs."""
        g = self.game
        if not args:
            return self.err("surplus <good> [town]")
        key = resolve_good(args[0])
        where = self._node(args[1]) if len(args) > 1 else ""
        political = ""
        if where and where in g.world.towns:
            t = g.world.towns[where]
            m, name = t.market, t.name
            # The toll a foreign lord charges is the toll he charges *you*,
            # and what he thinks of you sets it. Reading the rate the last
            # cart happened to leave on the market meant this screen -- the
            # one place in the game that prices a tax properly -- was the
            # only one that could not see the politics.
            m.tariff_rate = g.world.tariff_for(where, None)
            mood = g.world.toll_mood(where)
            if abs(mood - 1.0) > 0.03:
                political = (f"{t.lord} charges you "
                             f"{'less' if mood < 1 else 'more'} than a stranger "
                             f"-- {mood:.2f}x, because he thinks of you as "
                             f"{chancery.temper(t.regard)}. `court {where}` "
                             f"says what would move him.")
        else:
            s = self.settlement(args[1] if len(args) > 1 else "")
            m, name = s.market, s.name
        r = surplus(m, key)
        if r.quantity <= 0:
            return self.say(f"  there is no {good(key).name} in {name} to weigh")
        self.say(ink.head(f"{good(key).name.upper()} IN {name.upper()}",
                          f"{r.price:,.2f}c, {r.quantity:,.0f} on the shelf"))
        self.say(f"  {ink.c(ink.pad('to the buyers', 16), ink.DIM)}"
                 f"{ink.c(f'{r.consumer:>10,.0f}c', ink.LEAF)}   "
                 + ink.c("what they would have paid, over what they did", ink.DIM))
        self.say(f"  {ink.c(ink.pad('to the sellers', 16), ink.DIM)}"
                 f"{ink.c(f'{r.producer:>10,.0f}c', ink.LEAF)}   "
                 + ink.c("what they got, over what it cost to make", ink.DIM))
        if r.revenue or r.deadweight:
            self.say(f"  {ink.c(ink.pad('to the toll', 16), ink.DIM)}"
                     f"{ink.c(f'{r.revenue:>10,.0f}c', ink.GOLD)}   "
                     + ink.c(f"at {m.tariff_rate * 100:.0f}% on every sale",
                             ink.DIM))
            self.say(f"  {ink.c(ink.pad('to nobody', 16), ink.DIM)}"
                     f"{ink.c(f'{r.deadweight:>10,.0f}c', ink.BLOOD)}   "
                     + ink.c("trades worth making that stopped being made",
                             ink.DIM))
        self.say(f"  {ink.c(ink.pad('all told', 16), ink.DIM)}"
                 f"{ink.c(f'{r.total:>10,.0f}c', ink.PARCH)}")
        if r.deadweight:
            self.say("", ink.c(
                f"  The toll takes {r.revenue:,.0f}c and destroys "
                f"{r.deadweight:,.0f}c on the way. The second number is the one "
                f"nobody\n  ever sees, because it is not a payment -- it is the "
                f"trade that did not happen.", ink.DIM))
            if political:
                self.say("  " + ink.c(political, ink.AMBER))
        else:
            el = good(key).elasticity
            self.say("", ink.c(
                f"  Elasticity {el:.2f}: a tenth off the stock moves the price "
                f"about {10 * el:.0f}%. Cheap to\n  corner, if you have the "
                f"carts." if el > 0.5 else
                f"  Elasticity {el:.2f}: the price barely notices a shortage, "
                f"so there is little\n  to be made cornering it.", ink.DIM))

    def cmd_advantage(self, args: List[str]) -> None:
        """Who should be making what, by what each of you gives up to do it."""
        g = self.game
        if not args:
            return self.err("advantage <good> [town] [against-good]")
        key = resolve_good(args[0])
        s = self.settlement()
        mine = daily_output(s)
        if len(args) > 1:
            keys = [self._node(args[1])]
        else:
            keys = [k for k, t in g.world.towns.items() if t.seen_day > -900][:6]
            keys = keys or list(g.world.towns)[:6]
        against = resolve_good(args[2]) if len(args) > 2 else ""
        self.say(ink.head(f"WHO SHOULD MAKE {good(key).name.upper()}",
                          "what each gives up to make one"))
        if not mine.get(key):
            self.say(ink.c(f"  {s.name} cannot make {good(key).name} at all, "
                           f"so everything is cheaper bought.", ink.AMBER))
        any_row = False
        for tk in keys:
            town = g.world.towns.get(tk)
            if town is None:
                continue
            rows = compare(mine, town_output(town), key, town.name, against)
            if not rows:
                continue
            any_row = True
            r = rows[0]
            colour = ink.LEAF if r.theirs else ink.AMBER
            verdict = "buy it there" if r.theirs else "make it here"
            measure = ("in coin" if r.in_coin
                       else f"in {good(r.other).name}")
            def cost(v: float) -> str:
                return "cannot" if v == float("inf") else f"{v:.2f}"
            self.say(f"  {ink.c(ink.pad(town.name, 13), ink.PARCH)}"
                     f"{ink.c(ink.pad(verdict, 15), colour)}"
                     f"{ink.c(ink.pad(measure + ':', 14), ink.DIM)}"
                     f"you give up {cost(r.here)}, they {cost(r.there)}")
        if not any_row:
            self.say(ink.c("  nothing known about what those places can make -- "
                           "send a cart and look", ink.DIM))
        self.say("", ink.c(
            "  Not who is better at it: who gives up less to do it. A town that "
            "is worse at\n  everything still has something it should be making, "
            "and that is the whole of trade.", ink.DIM))

    def cmd_mint(self, args: List[str]) -> None:
        """Strike coin. The oldest tax there is, and the least popular."""
        g = self.game
        if not args:
            self.say(ink.head("THE MINT",
                              f"prices at {g.economy.price_level * 100:.0f}"))
            self.say(f"  struck so far  {g.economy.minted:,.0f}c")
            self.say(f"  coin about     {g.economy.money:,.0f}c")
            return self.say("", ink.c(
                "  `mint <coin>` strikes more pennies out of the same silver. "
                "You have the coin\n  today; prices find out over the next "
                "year or two. Nobody thanks you for it.", ink.DIM))
        self.say("  " + g.mint(float(args[0])))

    def cmd_assize(self, args: List[str]) -> None:
        """A legal maximum price. The most famous experiment in the book."""
        g = self.game
        econ = g.economy
        if not args:
            self.say(ink.head("THE ASSIZE", "what may be charged"))
            if not econ.assize:
                self.say(ink.c("  nothing is held at any price", ink.DIM))
            for key, cap in sorted(econ.assize.items()):
                worth = g.home().market.fundamental(key)
                bite = econ.shortage.get(key, 0.0)
                self.say(f"  {ink.pad(good(key).name, 12)}{cap:>8,.1f}c  "
                         f"{ink.c(f'worth {worth:,.1f}c', ink.DIM)}  "
                         + ink.c(f"{bite * 100:.0f}% short", ink.BLOOD)
                         if bite > 0.01 else ink.c("not biting", ink.DIM))
            return self.say("", ink.c("  assize <good> <price>  ·  "
                                      "assize <good> off", ink.DIM))
        key = resolve_good(args[0])
        if len(args) < 2:
            return self.err(f"assize {args[0]} <price>  (or `off`)")
        if args[1].lower() in ("off", "none", "lift", "0"):
            return self.say("  " + g.decree(key, 0.0))
        self.say("  " + g.decree(key, float(args[1])))

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

    def cmd_sally(self, args: List[str]) -> None:
        """Open the gate and go at the siege works."""
        g = self.game
        where = ""
        men = 0
        for arg in args:
            if arg.isdigit():
                men = int(arg)
            else:
                where = arg
        self.say("  " + g.sally(where, men).replace("\n", "\n  "))

    def cmd_shore(self, args: List[str]) -> None:
        """Put masons on the breach while it is being made."""
        g = self.game
        on = not (args and args[0].lower() in ("off", "no", "stop"))
        where = next((a for a in args
                      if a.lower() not in ("off", "no", "stop", "on")), "")
        self.say("  " + g.shore(where, on))

    def cmd_battle(self, args: List[str]) -> None:
        """The fight the day is waiting on: see it, fight a round, or decide."""
        from .military import DEFAULT_ORDER
        g = self.game
        v = g.battle_view()
        if v is None:
            return self.say("  " + ink.c("no fight is waiting on you. A storm on "
                                         "your wall, or your host going in, stops "
                                         "the day here until you have fought it.",
                                         ink.DIM))
        want = [a.lower() for a in args]
        if want and want[0] in ("fight", "round", "on", "go"):
            return self.say("  " + g.battle_step("fight").replace("\n", "\n  "))
        if want and want[0] in ("auto", "run", "let"):
            return self.say("  " + g.battle_step("auto").replace("\n", "\n  "))
        if want and want[0] == "order":
            key = want[1] if len(want) > 1 else DEFAULT_ORDER
            return self.say("  " + g.battle_step("order", key).replace("\n", "\n  "))
        if want and want[0] in ("commit", "reserve"):
            return self.say("  " + g.battle_step("commit").replace("\n", "\n  "))
        if want and want[0] == "oil":
            return self.say("  " + g.battle_step("oil").replace("\n", "\n  "))
        if want and want[0] == "pitch":
            return self.say("  " + g.battle_step("pitch").replace("\n", "\n  "))
        if want and want[0] in ("break", "retreat", "withdraw", "fall"):
            return self.say("  " + g.battle_step("break").replace("\n", "\n  "))
        if want and want[0] in ("ride", "lead", "charge"):
            # No screen here to swing the sword on, so the dice ride for him.
            return self.say("  " + g.battle_step("ride", " ".join(want[1:]))
                            .replace("\n", "\n  "))

        yours = v["side"]
        me, them = v[yours], v["defender" if yours == "attacker" else "attacker"]
        self.say(ink.head(f"THE STORM AT {v['title'].upper()}",
                          f"round {v['round']} of {v['max_rounds']} · {v['field']}"))

        def column(label, side, tint):
            bar = int(round(14 * side["alive"] / max(side["start"], 1e-9)))
            self.say(f"  {ink.c(ink.pad(label, 12), tint)}"
                     + ink.c("█" * bar + "░" * (14 - bar), tint)
                     + ink.c(f"  {side['alive']:.0f} of {side['start']:.0f}", ink.DIM)
                     + ink.c(f"   steadiness {side['morale']:.2f}", ink.DIM))
            self.say(f"      {ink.c(side['order_name'], ink.DIM)}")
            for k, n in sorted(side["units"].items(), key=lambda p: -p[1]):
                self.say(f"      {ink.c(ink.pad(v['kinds'][k]['name'], 18), ink.PARCH)}"
                         + ink.c(f"{n:.0f}", ink.PARCH))
        column("yours", me, ink.LEAF)
        column("theirs", them, ink.BLOOD)
        if v["wall_full"]:
            self.say(f"  {ink.c(ink.pad('the wall', 12), ink.DIM)}"
                     + ink.c(f"{v['wall_standing']:.0f} of {v['wall_full']:.0f} standing"
                             + ("" if v["wall_standing"] > 0 else " -- they are in the breach"),
                             ink.DIM))
        self.say("")
        for row in v["modifiers"]:
            tint = (ink.LEAF if row["good"] else ink.BLOOD) if row["good"] is not None else ink.DIM
            self.say(f"  {ink.c(ink.pad(row['what'], 28), ink.DIM)}{ink.c(row['value'], tint)}")
        if v["log"]:
            self.say("")
            for line in v["log"][-4:]:
                self.say("  " + ink.c(line, ink.DIM))
        self.say("")
        can = v["can"]
        for cmd, what, key in (("battle fight", "fight one round", "fight"),
                               ("battle order <what>", "reform under another order -- a soft round while you do", "reorder"),
                               ("battle commit", "throw the reserve in -- one hard round, nothing behind it after", "commit"),
                               ("battle oil", "oil over the gatehouse, once", "oil"),
                               ("battle pitch", "fire the ditch, once", "pitch"),
                               ("battle break", "break off -- keep the rest, less the pursuit", "break"),
                               ("battle auto", "let it run to the end", "fight")):
            why = can.get(key)
            if why is None and key in ("oil", "pitch"):
                continue                       # not on the wall
            tint = ink.GOLD if not why else ink.DIM
            self.say("  " + ink.c(ink.pad(cmd, 22), tint)
                     + ink.c(what if not why else f"({why})", ink.DIM))

    def cmd_herds(self, args: List[str]) -> None:
        """The beasts in your yards, and what it costs to put them back."""
        g = self.game
        want = [a.lower() for a in args]
        if want and want[0] in ("buy", "restock", "stock"):
            uid = next((int(a) for a in want if a.isdigit()), -1)
            return self.say("  " + g.restock(self.here, uid))
        rows = g.herds(self.here)
        self.say(ink.head("THE YARDS", "what is standing in them"))
        if not rows:
            self.say("  " + ink.c("no pasture, dairy or stable here", ink.DIM))
            return
        for r in rows:
            tint = (ink.LEAF if r["share"] > 0.75 else
                    ink.GOLD if r["seed"] else ink.BLOOD)
            tail = ("" if r["cost"] <= 0 else
                    "   %d head short, %sc to buy in" % (
                        r["full"] - round(r["head"]), f"{r['cost']:,}"))
            self.say(f"  {ink.c(str(r['uid']) + '.', ink.DIM)} "
                     + ink.c(ink.pad(r["name"], 18), ink.PARCH)
                     + ink.c("%.0f of %d" % (r["head"], r["full"]), tint)
                     + ink.c(tail, ink.DIM))
            if not r["seed"]:
                self.say("      " + ink.c("too few left to breed from -- this "
                                          "one only comes back if you pay for "
                                          "it", ink.BLOOD))
        self.say("")
        self.say("  " + ink.c(ink.pad("herds buy [n]", 22), ink.GOLD)
                 + ink.c("drive beasts in to a yard", ink.DIM))
        self.say("  " + ink.c("a raid takes them, and the wool stops with "
                              "them", ink.DIM))

    def cmd_water(self, args: List[str]) -> None:
        """The rivers today, the road you asked about, and the bridges."""
        g = self.game
        want = [a.lower() for a in args]

        if want and want[0] in ("bridge", "build"):
            if len(want) < 3:
                return self.say("  " + ink.c("water bridge <from> <to>", ink.DIM))
            return self.say("  " + g.build_bridge(want[1], want[2],
                                                  want[3] if len(want) > 3 else ""))
        if want and want[0] in ("throw", "break", "down"):
            if len(want) < 2 or not want[1].isdigit():
                return self.say("  " + ink.c("water throw <bridge number>", ink.DIM))
            return self.say("  " + g.break_bridge(int(want[1])))
        if want and want[0] in ("mend", "rebuild", "repair"):
            if len(want) < 2 or not want[1].isdigit():
                return self.say("  " + ink.c("water mend <bridge number>", ink.DIM))
            return self.say("  " + g.mend_bridge(int(want[1])))

        level = waters.stage(g.day, g.seed, g.start_month)
        sky = sky_on(g.season, g.day, g.seed)
        self.say(ink.head("THE WATER", waters.forecast(g.season)))
        self.say(f"  {ink.c(ink.pad('stage', 16), ink.DIM)}"
                 + f"{level:.2f}" + ink.c("   (the melt, the rain, and the "
                                          "fortnight behind it)", ink.DIM))
        self.say("")
        for r in g.world.waters():
            st = waters.state_of(r, level, sky)
            tint = {waters.LOW: ink.LEAF, waters.FORD: ink.LEAF,
                    waters.ICE: ink.SKY, waters.HIGH: ink.GOLD,
                    waters.SHUT: ink.BLOOD}.get(st, ink.PARCH)
            cost = waters.DELAY.get(st, 0.0)
            tail = "" if cost <= 0 else "  +%.1fd to cross" % cost
            self.say(f"  {ink.c(ink.pad('the ' + r.name, 16), ink.PARCH)}"
                     + ink.c(ink.pad(waters.WORDS[st], 14), tint)
                     + ink.c(r.size + tail, ink.DIM))

        mine = g.bridges_of("player")
        self.say("")
        if not mine:
            self.say("  " + ink.c("you hold no bridge. One costs %.0fc and "
                                  "%d days, and it is a crossing that never "
                                  "floods" % (waters.BRIDGE_COST,
                                              waters.BRIDGE_DAYS), ink.DIM))
        else:
            self.say("  " + ink.c("YOUR BRIDGES", ink.DIM))
            for b in mine:
                river = g.world.river(b.river)
                if b.broken:
                    state, tint = "thrown down", ink.BLOOD
                elif b.days_left > 0:
                    state, tint = "%d days of masonry" % b.days_left, ink.GOLD
                else:
                    state, tint = "standing", ink.LEAF
                self.say(f"      {ink.c(str(b.uid) + '.', ink.DIM)} "
                         + ink.c(ink.pad(b.name, 20), ink.PARCH)
                         + ink.c(ink.pad(state, 20), tint)
                         + ink.c("over the %s" % (river.name if river else "water"),
                                 ink.DIM))

        onroad = []
        for a in g.armies:
            if a.owner == "player" or a.state != "marching":
                continue
            if a.bound_for not in g.world.settlements:
                continue
            for r, x, y, bridge in g.world.crossings(a.at or a.home, a.bound_for):
                if bridge is not None and bridge.owner == "player":
                    onroad.append((a, bridge, r))
        if onroad:
            self.say("")
            self.say("  " + ink.c("ON SOMEBODY ELSE'S ROAD", ink.BLOOD))
            for a, bridge, r in onroad:
                self.say(f"      {ink.c(ink.pad(bridge.name, 20), ink.PARCH)}"
                         + ink.c("carries %s over the %s, %0.f days out"
                                 % (a.name, r.name, a.days_left), ink.DIM))
            self.say("      " + ink.c("`water throw <n>` puts it in the river. "
                                      "So does your own trade.", ink.DIM))

        road = [a for a in want if not a.isdigit()]
        if len(road) >= 2:
            a = g.world.resolve(road[0]) or road[0]
            b = g.world.resolve(road[1]) or road[1]
            self.say("")
            if a not in g.world.coords or b not in g.world.coords:
                self.say("  " + ink.c("I do not know that road", ink.DIM))
            else:
                rows = g.world.water_state(a, b, g.day, g.seed, g.start_month)
                head = "%s to %s" % (g.world.node_name(a), g.world.node_name(b))
                self.say("  " + ink.c(head.upper(), ink.DIM))
                if not rows:
                    self.say("      " + ink.c("dry all the way", ink.DIM))
                for row in rows:
                    tail = ("carried by %s" % row["bridge"] if row["bridge"]
                            else ("+%.1f days" % row["days"] if row["days"]
                                  else "no delay"))
                    self.say(f"      {ink.c(ink.pad('the ' + row['river'], 16), ink.PARCH)}"
                             + ink.c(ink.pad(row["words"], 14), ink.DIM)
                             + ink.c(tail, ink.DIM))
        self.say("")
        for cmd, what in (
                ("water <from> <to>", "what a road has to get over"),
                ("water bridge <from> <to>", "masons on its worst crossing"),
                ("water throw <n>", "throw one down -- no host crosses, "
                                    "and no cart of yours either"),
                ("water mend <n>", "put a broken one back up")):
            self.say("  " + ink.c(ink.pad(cmd, 26), ink.GOLD)
                     + ink.c(what, ink.DIM))

    def cmd_gates(self, args: List[str]) -> None:
        """Shut your gates against the sickness, or open them again."""
        from . import plague
        g = self.game
        want = [a.lower() for a in args]
        where = next((a for a in want
                      if a not in ("shut", "close", "open", "up")), "")
        s = g.world.settlements.get(where) or g.home()
        if any(w in want for w in ("shut", "close")):
            return self.say("  " + g.shut_gates(where, True))
        if "open" in want:
            return self.say("  " + g.shut_gates(where, False))

        self.say(ink.head(s.name.upper(), "the gates, and what is on the road"))
        state = "shut" if s.shut else "open"
        tint = ink.BLOOD if s.shut else ink.LEAF
        self.say(f"  {ink.c(ink.pad('the gates', 16), ink.DIM)}"
                 + ink.c(state, tint))
        if s.sick.here:
            self.say(f"  {ink.c(ink.pad('here', 16), ink.DIM)}"
                     + ink.c(plague.words(s.sick, g.day), ink.BLOOD))
            self.say(f"      {ink.c('%.0f buried so far' % s.sick.dead, ink.DIM)}")
        elif s.buried:
            self.say(f"  {ink.c(ink.pad('buried', 16), ink.DIM)}"
                     + "%.0f, over the years" % s.buried)
        word = g.word_of_sickness()
        self.say("")
        if not word:
            self.say("  " + ink.c("no word of sickness anywhere your carts have "
                                  "been lately", ink.DIM))
        else:
            self.say("  " + ink.c("WORD FROM THE ROAD", ink.DIM))
            for r in word:
                how = ("your carts were there today" if r["days"] <= 0 else
                       "%d days old" % r["days"])
                tint = ink.BLOOD if r["sure"] else ink.GOLD
                self.say(f"      {ink.c(ink.pad(r['name'], 16), ink.PARCH)}"
                         + ink.c("they are ill there", tint)
                         + ink.c(f" -- {how}", ink.DIM))
            self.say("")
            self.say("  " + ink.c("and a town you have not sent anybody to is a "
                                  "town you know nothing about", ink.DIM))
        self.say("")
        self.say("  " + ink.c("gates shut", ink.GOLD)
                 + ink.c("   no cart comes or goes: no sickness, and no trade",
                         ink.DIM))
        self.say("  " + ink.c("gates open", ink.GOLD)
                 + ink.c("   the carts run again", ink.DIM))

    def cmd_torch(self, args: List[str]) -> None:
        """Send a party over the wall at the besieger's wagons."""
        g = self.game
        men = 0
        where = ""
        for a in args:
            if a.isdigit():
                men = int(a)
            else:
                where = a.lower()
        self.say("  " + g.fire_baggage(where, men).replace("\n", "\n  "))

    def cmd_sortie_odds(self, args: List[str]) -> None:
        """What a sortie out of a besieged town would risk, before you order it."""
        from .military import BESIEGING, sortie_odds
        from . import supply
        g = self.game
        where = " ".join(args).strip().lower().replace(" ", "_") or self.here
        s = g.world.settlements.get(where)
        if s is None:
            return self.err(f"{where} is not one of your towns")
        if not s.besieged:
            return self.say("", ink.c(f"  {s.name} is not besieged", ink.DIM))
        outside = [a for a in g.armies if a.owner != "player"
                   and a.state == BESIEGING
                   and g.world.node_name(a.at) == s.name]
        sat = max((a.siege_days for a in outside), default=0)
        sky = g.field_at(where).weather
        self.say(ink.head("THE GATE", "what a sortie would risk"))
        for share, label in ((0.15, "a handful"), (0.3, "a quarter of them"),
                             (0.5, "half the garrison"), (0.8, "most of it"),
                             (1.0, "everyone")):
            o = sortie_odds(share, sky, sat, s.sorties)
            tint = ink.LEAF if o.surprise >= 0.5 else ink.BLOOD
            self.say(f"  {ink.c(ink.pad(label, 20), ink.PARCH)}"
                     + ink.c("{:.0%} unseen".format(o.surprise), tint)
                     + ink.c(f"  {o.words}", ink.DIM))
        o = sortie_odds(0.8, sky, sat, s.sorties)
        for good_reason in o.helps:
            self.say("      " + ink.c("+ " + good_reason, ink.LEAF))
        for bad in o.hurts:
            self.say("      " + ink.c("- " + bad, ink.BLOOD))
        self.say("")
        self.say("  " + ink.c("caught, you fight the watch over the engines; "
                              "seen, most of his host", ink.DIM))
        self.say("")
        self.say("  " + ink.c("sally <men>", ink.GOLD)
                 + ink.c("  at the works -- beat the watch and the engines burn,", ink.DIM))
        self.say("  " + ink.c("            ", ink.DIM)
                 + ink.c("  so too few men is men thrown away", ink.DIM))
        self.say("  " + ink.c("torch <men>", ink.GOLD)
                 + ink.c("  at the wagons -- you have to beat nobody, only", ink.DIM))
        self.say("  " + ink.c("            ", ink.DIM)
                 + ink.c("  arrive unseen, so the smallest party that can", ink.DIM))
        self.say("  " + ink.c("            ", ink.DIM)
                 + ink.c("  carry fire is the right one", ink.DIM))
        # What is in his wagons decides whether that is worth doing at all.
        camp = max((supply.days_left(a.size, a.stores) for a in outside),
                   default=0.0)
        if camp > 60:
            self.say("")
            self.say("  " + ink.c(
                "He carries {:.0f} days. One torch takes about a third: that "
                "is a campaign".format(camp), ink.DIM))
            self.say("  " + ink.c(
                "of raids or it is nothing, and he watches the gate harder "
                "after each", ink.DIM))
        elif camp > 0:
            self.say("")
            self.say("  " + ink.c(
                "He carries only {:.0f} days. A torch in that camp is a siege "
                "lifted.".format(camp), ink.LEAF))

    def cmd_victual(self, args: List[str]) -> None:
        """What your hosts are eating, and load the baggage of one that can."""
        from . import supply
        g = self.game
        mine = [a for a in g.armies if a.owner == "player"]
        if args:
            try:
                uid = int(args[0])
            except ValueError:
                match = [a for a in mine if args[0].lower() in a.name.lower()]
                if not match:
                    return self.err(f"no host of yours called {args[0]!r}")
                uid = match[0].uid
            days = 0.0
            if len(args) > 1:
                try:
                    days = float(args[1])
                except ValueError:
                    return self.err("victual <host> [days]")
            return self.say("  " + g.provision(uid, days))
        if not mine:
            return self.say("", ink.c("  you have no host in the field", ink.DIM))
        self.say(ink.head("THE BAGGAGE", "what they carry and what the country gives"))
        for a in mine:
            where = a.at or a.bound_for
            v = supply.note(a.size, a.stores, g._ground_at(where), g.season,
                            g.world.grazed.get(where, 0.0))
            larder, far = g._larder(a)
            settled = a.state in ("besieging", "garrison", "raiding")
            share = supply.convoy_share(far, settled) if larder else 0.0
            tint = ink.LEAF if v["days"] > 7 or v["enough"] else ink.BLOOD
            self.say(f"  {ink.c(ink.pad(a.name, 14), ink.PARCH)}"
                     + ink.c("{:.0f} days in the baggage".format(v["days"]), tint))
            self.say(f"      {ink.c(a.fed or 'not yet fed today', ink.DIM)}")
            self.say("      " + ink.c(
                "the country here feeds {:d} of its {:d} men".format(
                    v["feeds"], a.size), ink.DIM))
            if v["grazed"] > 0.15:
                self.say("      " + ink.c(
                    "eaten out here: {:.0%} of what it had".format(v["grazed"]),
                    ink.DIM))
            if larder:
                self.say("      " + ink.c(
                    "{:s} is {:d} leagues off and sends {:.0%}".format(
                        g.world.node_name(larder), int(far), share), ink.DIM))
        self.say("", ink.c("  victual <host> [days] to load at one of your towns",
                           ink.DIM))

    def cmd_ground(self, args: List[str]) -> None:
        """What a place is like to fight over, and what the sky is doing."""
        from .military import field_note, season_odds
        g = self.game
        where = " ".join(args).strip().lower().replace(" ", "_")
        if not where:
            where = self.here
        known = dict(g.world.settlements)
        known.update(g.world.towns)
        if where not in known:
            match = [k for k, v in known.items()
                     if where in k or where in v.name.lower()]
            if not match:
                return self.err(f"no place called {' '.join(args)!r}")
            where = match[0]
        fld = g.field_at(where)
        self.say(ink.head(fld.place.upper(), fld.words()))
        self.say(f"  {ink.c(ink.pad('the ground', 14), ink.DIM)}{fld.ground.name}")
        self.say(f"      {ink.c(fld.ground.note, ink.DIM)}")
        self.say(f"  {ink.c(ink.pad('the sky', 14), ink.DIM)}{fld.sky.name}")
        if fld.sky.note:
            self.say(f"      {ink.c(fld.sky.note, ink.DIM)}")
        if fld.sky.firms and fld.going == "heavy":
            frozen = ("The fen is frozen. It will carry a horse today and "
                      "it will not in April.")
            self.say("      " + ink.c(frozen, ink.LEAF))
        def dials(rows) -> None:
            for r in rows:
                tint = ink.BLOOD if r["worth"] < 1 else ink.LEAF
                worth = "worth {:.2f} of itself".format(r["worth"])
                self.say("      " + ink.c(ink.pad(r["kind"], 9), ink.DIM)
                         + ink.c(worth, tint))

        mine = [a for a in g.armies if a.owner == "player"]
        said = False
        for a in mine:
            rows = field_note(a.units, fld)
            if not rows:
                continue
            said = True
            self.say("")
            self.say(f"  {ink.c(a.name, ink.PARCH)} here today:")
            dials(rows)
        if not said:
            # No host of yours to weigh, or none of it cares. Say what the
            # place does to anybody, because a player deciding what to raise
            # needs to know a fen before he owns the horse it would ruin.
            every = [{"kind": k, "worth": round(v, 3)}
                     for k, v in sorted(fld.mult().items())]
            if every:
                self.say("")
                self.say("  " + ink.c("here, to anybody:", ink.DIM))
                dials(every)
        self.say("")
        self.say(f"  {ink.c(g.season + ' brings', ink.DIM)} "
                 + ", ".join(f"{k} {v:.0%}" for k, v in season_odds(g.season)))

    def cmd_order(self, args: List[str]) -> None:
        """Tell a host how to fight, before it has to."""
        from .military import ORDERS, order_note
        g = self.game
        mine = [a for a in g.armies if a.owner == "player"]
        if not args:
            self.say(ink.head("ORDERS", "decided before the fight, not during"))
            for key, o in ORDERS.items():
                self.say(f"  {ink.c(ink.pad(key, 9), ink.GOLD)}{o.name}")
                self.say(f"      {ink.c(o.blurb, ink.DIM)}")
            if mine:
                self.say("")
                for a in mine:
                    o = ORDERS.get(a.order, ORDERS["line"])
                    self.say(f"  {ink.c(ink.pad(a.name, 12), ink.PARCH)}"
                             f"{ink.c(o.name, ink.LEAF)}")
                    self.say(f"      {ink.c(order_note(a.units, a.order), ink.DIM)}")
            else:
                self.say("", ink.c("  you have no host to order", ink.DIM))
            return self.say("", ink.c("  order <host> <what>", ink.DIM))
        if len(args) < 2:
            return self.err("order <host> <what>")
        try:
            uid = int(args[0])
        except ValueError:
            match = [a for a in mine if args[0].lower() in a.name.lower()]
            if not match:
                return self.err(f"no host of yours called {args[0]!r}")
            uid = match[0].uid
        self.say("  " + g.order_host(uid, args[1].lower()))

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
                                 key=lambda kv: -kv[1].hostility)[:6]:
                if t.mine:
                    continue
                tied = any(p.alive and p.married_to == key for p in g.kin.people)
                note = (ink.c("kin already", ink.LEAF) if tied
                        else f"{g.dowry(key):,.0f}c")
                self.say(f"  {ink.pad(t.name, 13)} {ink.pad(t.lord, 24)}"
                         f" temper {t.hostility:>3.0f}   {note}")
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
        if "reliquary" in g.goals.paths:
            terms = (f"Hold {g.goals.relics} of them for {g.goals.relic_days} "
                     f"days and the march is yours ({g.relic_days} so far).")
            self.say("  " + ink.c(terms, ink.DIM))
        self.say("", ink.c("  march <host> <shrine> and stand there "
                           f"{C.RELIC_DAYS} days to lift one.", ink.DIM))

    def cmd_raid(self, args: List[str]) -> None:
        """Burn the country instead of the walls."""
        if not args:
            return self.err("raid <host>")
        self.say("  " + self.game.raid(int(args[0])))

    def cmd_split(self, args: List[str]) -> None:
        """split <host> <soldier> <n> [...] -- detach part of a host."""
        if len(args) < 3:
            return self.err("split <host> <soldier> <n> [<soldier> <n> ...]")
        uid = self._which(args, "split <host> <soldier> <n> ...")
        if uid is None:
            return
        units: Dict[str, int] = {}
        rest = args[1:]
        for i in range(0, len(rest) - 1, 2):
            try:
                units[resolve_unit(rest[i])] = int(rest[i + 1])
            except ValueError:
                return self.err(f"{rest[i + 1]!r} is not a number of {rest[i]}")
        b, why = self.game.split_host(uid, units)
        if not b:
            return self.err(why)
        self.say(f"  {b.name} stands apart at {self._where(b)}: {describe(b.units)}")

    def cmd_join(self, args: List[str]) -> None:
        """join <host> <host> -- fold the second host into the first."""
        if len(args) < 2:
            return self.err("join <host> <other host>")
        try:
            a, b = int(args[0]), int(args[1])
        except ValueError:
            return self.err("join <host> <other host> -- both by number")
        self.say("  " + self.game.join_hosts(a, b))

    def cmd_recall(self, args: List[str]) -> None:
        """Order a host home."""
        uid = self._which(args, "recall <host>")
        if uid is None:
            return
        a = self.game.army(uid)
        if not a:
            return self.err("no such host")
        self.say("  " + self.game.march(a.uid, a.home))

    def cmd_standdown(self, args: List[str]) -> None:
        """Disband a host back into the garrison it came from."""
        uid = self._which(args, "standdown <host>")
        if uid is not None:
            self.say("  " + self.game.disband_host(uid))

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
                        if ground else ink.c(kind.blurb, ink.DIM)))
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

    def cmd_battles(self, args: List[str]) -> None:
        """What has been fought, and how it went."""
        n = int(args[0]) if args else 12
        for line in self.game.battles[-n:]:
            self.say(f"  * {line}")
        if not self.game.battles:
            self.say("  the march has been quiet")

    def cmd_age(self, args: List[str]) -> None:
        """The age you are in, the next one, and what it wants."""
        g = self.game
        p = g.progress
        if args and args[0].lower() in ("begin", "go", "climb"):
            return self.say("  " + g.begin_age())
        nxt = p.next_age()
        self.say(ink.head(p.age_name().upper()),
                 "  " + ink.c(AGES[p.age].blurb, ink.DIM))
        if p.advancing:
            return self.say(f"  climbing to the {AGES[p.age + 1].name}: "
                            f"{ink.count(p.advancing, 'day')} to go")
        if not nxt:
            return self.say("  there is nothing above this.")
        cost = ", ".join(f"{v:,.0f} {'coin' if k == 'coin' else good(k).name}"
                         for k, v in nxt.cost.items())
        self.say("", f"  next: {nxt.name} -- {nxt.days} days",
                 f"  {nxt.blurb}",
                 f"  cost   {cost}",
                 "  needs  " + (", ".join(nxt.needs) if nxt.needs else "nothing built"),
                 "  (`age begin` to start the work)")

    def cmd_tech(self, args: List[str]) -> None:
        """The guildhall: what is being studied and what could be."""
        g = self.game
        p = g.progress
        if args:
            key = args[0].lower()
            if key not in TECHS:
                hits = [k for k in TECHS if k.startswith(key) and not TECHS[k].hidden]
                if len(hits) != 1:
                    return self.err(f"no craft matches {args[0]!r}")
                key = hits[0]
            return self.say("  " + g.research(key))
        self.say(ink.head("THE GUILDHALL", p.age_name()))
        if p.researching:
            self.say(f"  studying {TECHS[p.researching].name}, "
                     f"{ink.count(p.research_left, 'day')} to go", "")
        for t in p.available():
            cost = " ".join(f"{v:g}{k[:5]}" for k, v in t.cost.items())
            self.say(f"  {t.key:<18} {t.name:<22} {t.days:>3}d  {cost}")
            if t.blurb:
                self.say(f"       {t.blurb}")
        known = sorted(TECHS[k].name for k in p.researched if not TECHS[k].hidden)
        if known:
            self.say("", "  known: " + ", ".join(known))
        if g.house:
            self.say("", f"  your house: {HOUSES[g.house].name}",
                     f"       {HOUSES[g.house].blurb}")

    def cmd_found(self, args: List[str]) -> None:
        """Settle unclaimed land. Expensive, and it starts hungry."""
        if not args:
            sites = ", ".join(self.game.world.sites) or "none left"
            return self.say(f"  unclaimed: {sites}")
        self.say("  " + self.game.found(args[0].lower()))

    def cmd_caravans(self, args: List[str]) -> None:
        """Your carts and cogs: where they are and what they have earned."""
        self.caravan_view(int(args[0]) if args else None)

    def cmd_new(self, args: List[str]) -> None:
        """new [cart|ship] [town] [name]"""
        kind = CART
        if args and args[0].lower() in ("ship", "cog", "cart", "caravan"):
            kind = SHIP if args[0].lower() in ("ship", "cog") else CART
            args = args[1:]
        town = self._node(args[0]) if args else self.here
        name = args[1] if len(args) > 1 else ""
        c, why = self.game.new_caravan(town, name, kind=kind)
        if not c:
            return self.err(why)
        what = "launched at" if c.sails else "outfitted at"
        self.say(f"  {c.name} {what} {self._name(town)} "
                 f"({c.capacity:.0f} units at {c.speed:.0f} leagues/day)")

    def cmd_guards(self, args: List[str]) -> None:
        """Hire or pay off a cart's escort."""
        uid = self._which(args, "guards <cart> <n>")
        if uid is None:
            return
        c = self.game.caravan(uid)
        if not c:
            return self.err("no such caravan")
        c.guards = max(0, int(args[1]))
        self.say(f"  {c.name} rides with {c.guards} guards ({c.daily_cost:.0f}c/day)")

    def cmd_route(self, args: List[str]) -> None:
        """Give a cart a standing round to walk."""
        if len(args) < 2:
            return self.err("route <caravan> add <town> [buy|sell <good> <qty> [@price]] ...")
        c = self.game.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
        verb = args[1].lower()
        if verb == "clear":
            c.set_route([])
            c.halt()
            return self.say(f"  {c.name} route cleared")
        if verb == "show":
            return self.caravan_view(c.uid)
        if verb != "add":
            return self.err("route <caravan> add|clear|show ...")
        stop = _parse_stop(self.game.world, args[2:])
        c.route.append(stop)
        self.say(f"  {c.name}: {stop.describe()}")

    def cmd_auto(self, args: List[str]) -> None:
        """Put a cart on the best run the scanner can find."""
        if not args:
            return self.err("auto <caravan>")
        g = self.game
        c = g.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
        # Priced dry, deliberately, where the counting house prices today's
        # water. A standing route outlives the weather: charging it a spring
        # flood for ever would push every cart onto the summer ranking and
        # leave it there, and the player would be given a route he could not
        # see the reason for. `margin` answers "what is worth doing today";
        # this answers "what is worth running", which is a different question.
        opts = scan(g.world, self.here if not c.sails else c.at,
                    capacity=c.capacity, speed=c.speed, sails=c.sails,
                    daily_cost=c.daily_cost, budget=max(0.0, g.treasury), top=3)
        if not opts:
            return self.err("the counting house finds nothing worth the road today")
        opp = opts[0]
        c.set_route(route_from(opp))
        c.start()
        self.say(f"  {c.name} put on: " + opp.describe(self._name))

    def cmd_go(self, args: List[str]) -> None:
        """Set a cart running on the route it has."""
        uid = self._which(args, "go <cart>")
        if uid is None:
            return
        c = self.game.caravan(uid)
        if not c:
            return self.err("no such caravan")
        if not c.route:
            return self.err("it has no route")
        c.start()
        self.say(f"  {c.name} sets out")

    def cmd_stop(self, args: List[str]) -> None:
        """Stand a cart down where it is."""
        uid = self._which(args, "stop <cart>")
        if uid is None:
            return
        c = self.game.caravan(uid)
        if not c:
            return self.err("no such caravan")
        c.halt()
        self.say(f"  {c.name} will stand down at its next stop")

    def cmd_disband(self, args: List[str]) -> None:
        """Sell a cart off."""
        uid = self._which(args, "disband <cart>")
        if uid is not None:
            self.say("  " + self.game.disband(uid))

    def cmd_scan(self, args: List[str]) -> None:
        """The best runs on the march today, by coin a day."""
        sea = any(a.lower() in ("sea", "ship", "cog") for a in args)
        nums = [a for a in args if a.isdigit()]
        self.scan_view(int(nums[0]) if nums else 8, sails=sea)

    def cmd_needs(self, args: List[str]) -> None:
        """What your own town is short of, and where it is cheap."""
        for s in self.game.world.settlements.values():
            rows = shortage_report(s)
            self.say(f"  {s.name}: " + (", ".join(
                f"{good(k).name} {net:+.1f}/day ({stock:.0f} left,"
                f" {stock / -net:.0f}d)" for k, net, stock in rows[:5] if net < 0)
                or "nothing running down"))

    def cmd_map(self, args: List[str]) -> None:
        """The march as a chart of who is where."""
        self.map_view()

    def cmd_chart(self, args: List[str]) -> None:
        """One measure of yours, drawn over time."""
        self.chart(args[0] if args else "worth")

    def cmd_log(self, args: List[str]) -> None:
        """The last lines of what happened."""
        n = int(args[0]) if args else 15
        for m in self.game.events.log[-n:]:
            self.say(f"  * {m}")

    def cmd_save(self, args: List[str]) -> None:
        """Write the game to a file."""
        try:
            self.say("  " + self.game.save(args[0] if args else "marchlands.save"))
        except OSError as exc:
            self.err(f"could not write it: {exc}")

    def cmd_load(self, args: List[str]) -> None:
        """Open a saved game, and survive it not being one.

        A missing file used to take the whole session down with it, which is a
        poor way to find out you typed the name wrong -- and a poorer one if
        you had an hour in the game you were about to save.
        """
        path = args[0] if args else "marchlands.save"
        try:
            loaded = GameState.load(path)
        except FileNotFoundError:
            return self.err(f"no saved game at {path}")
        except OSError as exc:
            # Everything else the filesystem can say: a directory, a bad
            # permission, a dead symlink. All of it is "cannot read that".
            return self.err(f"cannot read {path}: {exc.strerror or exc}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self.err(f"{path} is not a saved game -- it is not even JSON")
        except (KeyError, TypeError, ValueError) as exc:
            return self.err(f"{path} is damaged or from another version ({exc})")
        if not loaded.world.settlements:
            return self.err(f"{path} has no holding in it; the game is unchanged")
        self.game = loaded
        self.here = next(iter(self.game.world.settlements))
        self.say(f"  loaded {path}")
        self.status()

    def cmd_quit(self, args: List[str]) -> None:
        """Leave. Nothing is written unless you asked for it."""
        self.quit = True


def _node_colour(game, key: str) -> int:
    if game.world.is_mine(key):
        return ink.GOLD
    town = game.world.towns.get(key)
    if town is None:
        return ink.INK
    if town.mine:
        return ink.LEAF
    if game.world.is_port(key):
        return ink.SEA
    return ink.BLOOD if town.hostility > 70 else ink.INK


def _wrap(text: str, n: int) -> List[str]:
    """Break a sentence at a space, because a person speaking does not wrap
    mid-word at column sixty-eight."""
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > n:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def _short(text: str, n: int) -> str:
    """A name that will not fit, cut where a reader can still place it."""
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _level(text: str, labels: Dict[int, str]) -> int:
    t = text.lower()
    for k, v in labels.items():
        if v == t:
            return k
    # A word that is not one of the labels is the likeliest thing a player
    # types here -- `ration full` rather than `ration double` -- and it used
    # to answer with `invalid literal for int() with base 10: 'full'`, which
    # is Python talking to a player. Say what the dial takes instead.
    try:
        n = int(text)
    except ValueError:
        raise ValueError(f"no setting called {text!r}; "
                         f"try {', '.join(labels.values())}") from None
    if n not in labels:
        raise ValueError(f"level must be one of {sorted(labels)} or "
                         f"{', '.join(labels.values())}")
    return n


def _parse_stop(world, tokens: List[str]) -> Stop:
    """`<town> buy wheat 120@3.2 sell ale all` -> a Stop."""
    if not tokens:
        raise ValueError("which town?")
    stop = Stop(node=world.resolve(tokens[0]))
    i = 1
    while i < len(tokens):
        verb = tokens[i].lower()
        if verb not in ("buy", "sell"):
            raise ValueError(f"expected buy/sell, got {tokens[i]!r}")
        if i + 2 >= len(tokens):
            raise ValueError(f"{verb} needs a good and a quantity")
        gkey = resolve_good(tokens[i + 1])
        qty_text = tokens[i + 2]
        limit = 0.0
        if "@" in qty_text:
            qty_text, price_text = qty_text.split("@", 1)
            limit = float(price_text)
        qty = -1.0 if qty_text.lower() in ("all", "max", "*") else float(qty_text)
        order = Order(good=gkey, quantity=qty, limit_price=limit)
        (stop.sell if verb == "sell" else stop.buy).append(order)
        i += 3
    return stop


COMMANDS = {
    "court": Console.cmd_court, "standing": Console.cmd_court,
    "ally": Console.cmd_ally, "alliance": Console.cmd_ally,
    "call": Console.cmd_call,
    "castle": Console.cmd_castle, "keep": Console.cmd_castle,
    "wall": Console.cmd_wall, "tower": Console.cmd_tower,
    "gate": Console.cmd_gate, "moat": Console.cmd_moat,
    "pitch": Console.cmd_pitchditch, "pits": Console.cmd_pits,
    "unwall": Console.cmd_unwall,
    "help": Console.cmd_help, "?": Console.cmd_help,
    "next": Console.cmd_next, "n": Console.cmd_next, "wait": Console.cmd_next,
    "status": Console.cmd_status, "s": Console.cmd_status,
    "town": Console.cmd_town, "stores": Console.cmd_stores,
    "view": Console.cmd_view, "plan": Console.cmd_view, "v": Console.cmd_view,
    "watch": Console.cmd_watch,
    "market": Console.cmd_market, "prices": Console.cmd_prices,
    "chain": Console.cmd_chain, "buildings": Console.cmd_buildings,
    "info": Console.cmd_info, "build": Console.cmd_build, "raze": Console.cmd_raze,
    "close": Console.cmd_close, "ration": Console.cmd_ration,
    "work": Console.cmd_work, "hands": Console.cmd_work, "tax": Console.cmd_tax,
    "staff": Console.cmd_staff, "pin": Console.cmd_staff, "move": Console.cmd_move,
    "split": Console.cmd_split, "detach": Console.cmd_split,
    "join": Console.cmd_join, "merge": Console.cmd_join,
    "garrison": Console.cmd_garrison, "found": Console.cmd_found,
    "units": Console.cmd_units, "recruit": Console.cmd_recruit,
    "host": Console.cmd_host, "army": Console.cmd_army, "armies": Console.cmd_army,
    "march": Console.cmd_march, "recall": Console.cmd_recall,
    "siege": Console.cmd_siege, "plans": Console.cmd_plans,
    "raid": Console.cmd_raid, "relics": Console.cmd_relics,
    "lord": Console.cmd_lord, "chronicle": Console.cmd_chronicle,
    "kin": Console.cmd_kin, "house": Console.cmd_kin, "family": Console.cmd_kin,
    "ask": Console.cmd_ask, "street": Console.cmd_ask, "listen": Console.cmd_ask,
    "season": Console.cmd_season, "standings": Console.cmd_season,
    "table": Console.cmd_season, "draft": Console.cmd_draft,
    "economy": Console.cmd_economy, "accounts": Console.cmd_economy,
    "margin": Console.cmd_margin, "surplus": Console.cmd_surplus,
    "advantage": Console.cmd_advantage, "mint": Console.cmd_mint,
    "assize": Console.cmd_assize, "decree": Console.cmd_assize,
    "post": Console.cmd_post, "posts": Console.cmd_post,
    "marry": Console.cmd_marry, "match": Console.cmd_marry,
    "estates": Console.cmd_estates, "privileges": Console.cmd_estates,
    "feats": Console.cmd_feats, "achievements": Console.cmd_feats,
    "missions": Console.cmd_missions, "roll": Console.cmd_missions,
    "order": Console.cmd_order, "orders": Console.cmd_order,
    "ground": Console.cmd_ground, "weather": Console.cmd_ground,
    "gate": Console.cmd_sortie_odds, "odds": Console.cmd_sortie_odds,
    "gates": Console.cmd_gates, "quarantine": Console.cmd_gates,
    "battle": Console.cmd_battle, "fight": Console.cmd_battle,
    "storm": Console.cmd_battle,
    "herds": Console.cmd_herds, "flock": Console.cmd_herds,
    "beasts": Console.cmd_herds, "livestock": Console.cmd_herds,
    "restock": Console.cmd_herds,
    "water": Console.cmd_water, "rivers": Console.cmd_water,
    "ford": Console.cmd_water, "fords": Console.cmd_water,
    "bridge": Console.cmd_water, "bridges": Console.cmd_water,
    "sickness": Console.cmd_gates, "plague": Console.cmd_gates,
    "torch": Console.cmd_torch, "wagons": Console.cmd_torch,
    "baggage": Console.cmd_torch,
    "victual": Console.cmd_victual, "supply": Console.cmd_victual,
    "provision": Console.cmd_victual,
    "sally": Console.cmd_sally, "sortie": Console.cmd_sally,
    "shore": Console.cmd_shore, "mend": Console.cmd_shore,
    "campaign": Console.cmd_campaign, "chapter": Console.cmd_campaign,
    "standdown": Console.cmd_standdown, "war": Console.cmd_war,
    "battles": Console.cmd_battles, "age": Console.cmd_age,
    "gift": Console.cmd_gift, "truce": Console.cmd_truce,
    "demand": Console.cmd_demand,
    "tech": Console.cmd_tech, "research": Console.cmd_tech,
    "caravans": Console.cmd_caravans, "c": Console.cmd_caravans,
    "new": Console.cmd_new, "guards": Console.cmd_guards, "route": Console.cmd_route,
    "auto": Console.cmd_auto, "go": Console.cmd_go, "stop": Console.cmd_stop,
    "disband": Console.cmd_disband, "scan": Console.cmd_scan, "needs": Console.cmd_needs,
    "map": Console.cmd_map, "chart": Console.cmd_chart, "log": Console.cmd_log,
    "save": Console.cmd_save, "load": Console.cmd_load, "quit": Console.cmd_quit,
    "hint": Console.cmd_hint, "hints": Console.cmd_hint,
    "autosave": Console.cmd_autosave, "scenarios": Console.cmd_scenarios,
    "briefing": Console.cmd_briefing,
    "exit": Console.cmd_quit,
}

HELP = """
  THE DAY           next [n]        let n days pass        status / s
  YOUR TOWN         view / v        view flat              watch [days]
                    ask [town]      what the street says
  THE MARCH'S EAR   court [town]    who thinks what of you, and why
                    ally <town>     swear to a friendly lord
                    call yes/no     answer an ally who called you to his war
                    court buy       pay off the whole letter against you
  THE CASTLE        castle          the wall as you drew it
                    wall <x,y> <x,y>   tower <x,y>   gate <x,y>
                    moat / pitch / pits <x,y> <x,y>  unwall <x,y> <x,y>
                    town [name]     stores [town]
                    needs
                    build <key>     buildings [filter]     info <key>
                    close <id>      raze <id>
                    ration <level>  tax <level>            found [site]
  THE LONG GAME     age | age begin                        tech [key]
  THE MARKET        market <town>   prices <good>          chain <good>
                    scan [n]        map                    chart [metric]
  THE ROAD          caravans / c    caravan <id>           new [town] [name]
                    new ship [town] scan sea                auto <id>
                    go <id>         stop <id>
                    guards <id> <n> disband <id>
                    route <id> add <town> buy <good> <qty>[@max] sell <good> all[@min]
                    route <id> clear | show
  WAR               units           recruit <who> [n]      garrison [town]
                    host <town> <who> <n> ...              army [id]
                    march <id> <place>   recall <id>       standdown <id>
                    plans [place]   siege [<id> <plan>]   raid <id>
                    lord [<id>|home|ransom]     relics    chronicle
  YOUR HOUSE        kin [name]      post [<name> <post> [where]]
                    marry [<name> <town>]
  THE MARCH         season [past]   draft [<name>]
  THE ECONOMY       economy         margin [town]          surplus <good> [town]
                    advantage <good> [town]                mint [coin]
                    assize [<good> <price>|off]
                    war             battles [n]
                    gift <town> <coin>   truce <town> [days]   demand <town>
  ELSE              hint            briefing               scenarios
                    campaign        chronicle [all]
                    log [n]   save [file]   load [file]   autosave [file]   quit
                    help trade | help town | help war | help win
"""

def catalogue() -> list:
    """Every command, with the one line its own docstring gives it.

    Built from the registry rather than written out beside it, so a command
    that exists is a command the palette offers and a command that is renamed
    cannot go on being listed under the old name. Aliases are folded into the
    entry they point at.
    """
    # The first spelling in the registry is the real one; everything after it
    # is an alias, because that is the order they were written in and the
    # order somebody chose on purpose.
    by_fn: dict = {}
    for name, fn in COMMANDS.items():
        entry = by_fn.setdefault(fn, {"name": name, "aliases": [], "help": ""})
        if name != entry["name"]:
            entry["aliases"].append(name)
    out = []
    for fn, entry in by_fn.items():
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        entry["help"] = doc
        entry["aliases"] = sorted(entry["aliases"])
        out.append(entry)
    return sorted(out, key=lambda e: e["name"])


HELP_TOPICS = {
    "trade": f"""
  A price here is a function of stock. Buying lifts it, selling drops it, and
  a big order walks the curve the whole way -- so the second hundred bushels
  never fetch what the first did. Foreign tolls come off both ends of a deal,
  the road costs a day per {C.CARAVAN_BASE_SPEED:.0f} leagues, and bandits take a cut of whatever
  is in the cart.

  `scan` fills every candidate trade against copies of the real markets and
  reports coin per day after all of that. `auto <id>` puts a cart on the best
  one. Rival houses are running the same arithmetic, and every run they make
  narrows the gap you were about to take.
""",
    "town": """
  People need a roof, food, and a reason not to leave. Rations and taxes are
  the two levers. Mood sets productivity -- at 50 your workers run at full, at
  100 half again, below 18 they down tools altogether.

  Ale and a service are *coverage*, not cheer. An inn serves so many souls and
  a chapel so many, so a town that grows past them is a town half of which is
  drinking nothing: the same building, bought again, is what success costs.
  An inn with no ale in it, or no hand in it, serves nobody at all.

  Towns are made of timber and they burn. Ovens and kilns start fires by
  themselves now and then, raiders bring torches, and men who get over a wall
  set light to what is behind it. Everyone runs at a fire, so the water scales
  with the town -- but the hands carrying it are hands not working, and a
  building you save still wants days of work. Summer is the dangerous season.
  Past about eight roofs alight at once the town cannot find enough people and
  the fire is simply winning.

  Hands are shorter than jobs and always will be. `work` shows the queue --
  who gets people first when there are not enough -- and `work <building>
  first` reorders it. Something goes short every morning; you only get to
  choose what.

  Land is the real constraint. You have so many fertile, forest, hill and clay
  slots, and no settlement has all four in quantity. What you cannot grow you
  must buy, and what you have too much of is only worth what a cart can carry
  to somebody who wants it.
""",
    "water": """
  Rivers are lines on the map, and a road crosses one where the line crosses
  it. What that costs depends on how high the water is -- one stage for the
  whole march, and it is the last fortnight of weather rather than a roll:
  rain today is still in the river on Thursday, and it drains off from there.
  Spring is the melt and the worst of it; summer is a formality; a hard frost
  on low water turns a river into a road, which is why winter campaigns
  crossed.

  A ford in low water costs nothing, one running high costs a day and a half
  and risks part of the load, and one in flood costs three -- you ride
  upstream to somebody else's bridge.

  Which is what a bridge of your own is for. It costs 1,400c and forty-five
  days of masonry, it never floods, and every host that is not coming for you
  pays to walk over it. You can also throw it down, and the crossing you deny
  an army is the crossing you deny your own carts.

  `water` for today, `water <from> <to>` for a road, `water bridge <from>
  <to>` to build, `water throw <n>` to put one in the river.
""",
    "war": """
  Soldiers are made, not bought. A barracks turns coin and arms from your own
  workshops into men: spears from a poleturner, bows from a fletcher, swords
  from an armoury, plate from an armourer. Every soldier also walks out of the
  labour pool -- an army is paid for twice, once in coin and once in fields
  nobody is working.

  Spears break horse. Horse rides down bows and siege crews. Bows cut up foot.
  Foot in armour walks through bows. None of it matters while a wall is
  standing, which is what a castle is for.

  A castle is not a pool of hit points, it is a set of answers. A besieger
  picks a plan and each plan is beaten by a different thing you dug:

    batter    rams at the gate         answered by boiling oil
    breach    engines on the curtain   answered by towers shooting the crews
    escalade  ladders, no engines      answered by towers and a pitch ditch
    sap       a mine under a section   answered outright by water in a moat
    invest    sit down and starve it   answered by a full granary and a gate

  `plans <place>` reads a castle and says what each way in would meet there.
  `siege <host> <plan>` sets how a host of yours goes in -- and changing the
  plan starts the work over, so a mine half-dug is a mine wasted. Works stand
  on the wall line and the wall line is finite: every ditch is a tower you did
  not build.

  Lords grow bolder the richer you get, and they scheme against each other as
  well as against you: leave the march alone long enough and one of them will
  swallow his neighbours -- your sworn towns included. `war` shows who answers
  to whom and what each could field today.

  You need not take a castle to beat the man in it. `raid <host>` looses a host
  on the country instead: the fields stop being worked, the people leave, and
  a rival loses prosperity, which is the number his walls and his muster are
  both computed from. A garrison that is clearly stronger will come out after
  you, which is what a raider wants if he is stronger still.

  Five shrines stand out on the map with relics in them. Six days' standing
  lifts one; `relics` says where they are and who holds what. They pay
  offerings daily, four of them held for a hundred and twenty days wins the
  march, and the other lords send parties of their own.

  Your lord is a man. `lord` says where he is: in his hall he is worth mood
  and a stretch of wall, riding with a host he is worth a sixth of its
  strength and he is where the arrows are. He can fall, and he can be taken
  and ransomed, and the line is not endless.

  The Preaching Orders, in the third age, buy you friars: they talk men off a
  wall and onto your side, a few a day. What stops them is a church -- a
  defender's faith coverage is exactly what blunts preaching, so a great seat
  with a minster is deaf to it and a market town is not. Friars count as siege,
  which means cavalry ride them down.

  You do not see the march; you see what you last looked at. Your carts are
  your intelligence service. `war` reports what you know and how old it is, and
  says plainly when you have never sent anyone -- and old word always
  understates a lord, because he grows while you are not watching.

  You need not meet all of it with soldiers. A `gift` cools a temper, a `truce`
  buys a fixed number of quiet days outright, and a `demand` squeezes tribute
  out of a lord too weak to refuse -- and is remembered by one who is not.

  Take a town and it bends the knee: no tolls, daily tribute, and every other
  lord one step angrier. Five towns sworn to you wins the game outright.

  A storming is not the end. The keep is thrown down, the town gutted, and you
  start again from whatever else you hold -- which is the best argument there
  is for founding a second settlement before you need one. You are only
  finished when there is nowhere left.
""",
}



def play_campaign(run, *, out=sys.stdout, script: Optional[Sequence[str]] = None,
                  save_to: Optional[str] = None):
    """Play the Marcher Chronicle through, chapter after chapter.

    Each chapter is an ordinary game with its own terms. What makes it a
    campaign is what crosses between them: the purse, what the house has
    worked out, the lord and what is left of his line, and the chronicle,
    which by the last chapter is the only record of how you got there.
    """
    con = None
    while not run.done:
        ch = run.current
        g = run.begin()
        con = Console(g, out=out)
        con.run = run
        con.say("")
        con.say(ink.head(ch.name.upper(),
                         f"chapter {run.chapter + 1} of {len(CHAPTERS)}"))
        for line in (g.briefing or "").splitlines():
            con.say(f"  {line}")
        if run.carry.purse:
            con.say("", ink.c(f"  You bring {run.carry.purse:,.0f}c and "
                              f"{len(run.carry.techs)} things your house already "
                              f"knows.", ink.DIM))
        con.say("")
        con.status()
        con.say("", "  `campaign` for where you are, `chronicle` for how you got "
                    "here, `hint` if you are stuck.")
        _drive(con, script)
        won, epilogue = run.finish(con.game)
        con.say("")
        con.say(ink.head("END OF CHAPTER", ch.name))
        con.say(f"  {con.game.over}")
        con.say("")
        con.say("  " + ink.c(epilogue, ink.GOLD if won else ink.AMBER))
        if save_to:
            con.say("  " + run.save(save_to))
        if con.quit or script is not None:
            break
    if run.done and con is not None:
        con.say("")
        con.say(ink.head("THE MARCHER CHRONICLE", "complete"))
        for line in run.standing():
            con.say(line)
        con.say("", f"  renown {run.carry.renown} of a possible "
                    f"{3 * len(CHAPTERS)}")
        con.say("", ink.c("  `chronicle` reads the whole of it back.", ink.DIM))
    return con


def _drive(con, script: Optional[Sequence[str]]) -> None:
    """Run one chapter to its end, from a script or from a person."""
    if script is not None:
        for line in script:
            con.say(f"\n> {line}")
            con.do(line)
            if con.quit or con.game.over:
                return
        return
    while not con.quit and not con.game.over:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            con.quit = True
            return
        if line:
            con.do(line)


def play(game: Optional[GameState] = None, script: Optional[Sequence[str]] = None,
         out=sys.stdout, autosave: Optional[str] = None) -> Console:
    con = Console(game or start_scenario(), out=out)
    if autosave:
        con.autosave_path = autosave
    con.say(BANNER)
    sc = SCENARIOS.get(con.game.scenario)
    if sc:
        con.say(f"  {sc.name.upper()}")
    for line in (con.game.briefing or "").splitlines():
        con.say(f"  {line}")
    con.say("")
    con.status()
    con.say("", "  `hint` if you are not sure what to do next; `help` for the rest.")
    if script is not None:
        for line in script:
            con.say(f"\n> {line}")
            con.do(line)
            if con.quit:
                break
        return con
    while not con.quit:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line:
            con.do(line)
    return con


BANNER = r"""
   __  __              _    _                 _
  |  \/  |__ _ _ _ __ | |_ | |__ _ _ _  __ _ | |___
  | |\/| / _` | '_/ _|| ' \| / _` | ' \/ _` || (_-<
  |_|  |_\__,_|_| \__||_||_|_\__,_|_||_\__,_||_/__/

  A holding, a hinterland, and seven towns that each want
  what somebody else has. Type `help` to begin.
"""
