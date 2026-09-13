"""Terminal interface. Stdlib only, no curses, works over ssh and in a pipe."""

from __future__ import annotations

import shlex
import sys
import time
from typing import Dict, List, Optional, Sequence

from . import config as C
from .advisor import route_from, scan, shortage_report
from .buildings import ALL_BUILDING_KEYS, BUILDINGS, building
from .buildings import resolve as resolve_building
from .castle import PLANS, SiegeState, Works
from .engine import GameState
from .goods import ALL_KEYS, RATION_GOODS, good, nourishment
from .goods import resolve as resolve_good
from . import lord as lordly
from . import render as ink
from .military import UNITS, describe, host_strength, host_upkeep
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
    def settlement(self, key: Optional[str] = None):
        w = self.game.world
        k = key or self.here
        if k in w.settlements:
            return w.settlements[k]
        return w.settlements[self.here]

    def _node(self, text: str, shrines: bool = False) -> str:
        return self.game.world.resolve(text, shrines=shrines)

    def _name(self, key: str) -> str:
        return self.game.world.node_name(key)

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
                self.say(f"  ! {a.name} out of {self._name(a.home)}: {a.where()}")
        if g.caravans:
            self.say("")
            for c in g.caravans:
                self.say(f"  [{c.uid}] {c.name:<12} {c.where():<22} "
                         f"{c.load:>3.0f}/{c.capacity:<3.0f} {c.manifest()[:34]:<34}"
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
        for b in sorted(s.buildings, key=lambda b: (b.spec.category, b.key)):
            if not b.complete:
                run = f"{b.days_left}d to raise"
            elif not b.enabled:
                run = "closed"
            elif b.spec.is_producer or b.spec.inputs:
                run = f"{100 * b.throughput:>3.0f}%"
            else:
                run = "  -"
            jobs = f"{b.staffed}/{b.spec.jobs}" if b.spec.jobs else "  -"
            glyph, colour = GLYPHS.get(b.key, ("·", ink.DIM))
            note = ink.c(b.idle_reason, ink.AMBER if b.idle_reason else ink.DIM)
            self.say(f"  {b.uid:>3}  {ink.c(glyph, colour)} "
                     f"{ink.pad(b.spec.name, 18)}{jobs:>5}  {run:>9}  {note}")
        self.say("")
        self.say("  mood    " + "  ".join(f"{k} {v:+.0f}"
                                          for k, v in s.mood_factors(p)))
        if s.fear:
            self.say(f"  fear    {s.fear:.0f} -- work runs "
                     f"{3.5 * s.fear:.0f}% harder and the people like it that much less")
        short = shortage_report(s)[:6]
        if short:
            self.say("  burning " + ", ".join(
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
                         f"{state:<12} {c.where():<20}"
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
                 f"  where     {c.where()}",
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
                          "@ yours   ~ port   o foreign   + land or shrine"))
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
            parts = shlex.split(line)
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

    def cmd_next(self, args: List[str]) -> None:
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
        if args and args[0].lower() in ("off", "no", "stop"):
            self.autosave_path = ""
            return self.say("  autosave off")
        self.autosave_path = args[0] if args else "marchlands.autosave"
        self._autosave()
        self.say(f"  autosaving to {self.autosave_path} after every `next`")

    def cmd_scenarios(self, args: List[str]) -> None:
        self.say(ink.head("SCENARIOS"))
        for i, key in enumerate(CAMPAIGN, 1):
            sc = SCENARIOS[key]
            here = "  <- you are here" if key == self.game.scenario else ""
            self.say(f"  {i}. {sc.key:<14} {sc.name:<20} {sc.years:g}y{here}")
            self.say(f"     {sc.blurb}")
        self.say("", "  start one with:  python3 -m marchlands --scenario <key>")

    def cmd_briefing(self, args: List[str]) -> None:
        g = self.game
        sc = SCENARIOS.get(g.scenario)
        self.say(ink.head((sc.name if sc else g.scenario).upper()))
        for line in (g.briefing or "").splitlines():
            self.say(f"  {line}")
        self.say(self.win_text())

    def cmd_hint(self, args: List[str]) -> None:
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
            out.append(f"{a.name} is {a.where()} with {describe(a.units)}. "
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
            out.append(f"{s.name} has about {days:.0f} days of food. Build a farm, "
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
            out.append(f"{len(free)} shrines still hold their relics. Six days' "
                       f"standing lifts one and they pay every day after. `relics`.")
        if g.lord.captured:
            out.append(f"{g.lord.name} is held at {g.lord.ransom:,.0f}c. "
                       f"`lord ransom` buys him back.")
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
        if not out:
            out.append("Nothing pressing. `scan` for a better route, `war` to see "
                       "who is arming, `age` for the long game.")
        return out[:4]

    def cmd_status(self, args: List[str]) -> None:
        self.status()

    def cmd_town(self, args: List[str]) -> None:
        if args:
            key = self._node(args[0])
            if key in self.game.world.settlements:
                self.here = key
        self.town_view()

    def cmd_view(self, args: List[str]) -> None:
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
        self.stores(self._node(args[0]) if args else None)

    def cmd_market(self, args: List[str]) -> None:
        if not args:
            return self.err("market <town>")
        self.market_view(args[0])

    def cmd_prices(self, args: List[str]) -> None:
        if not args:
            return self.err("prices <good>")
        self.price_view(args[0])

    def cmd_chain(self, args: List[str]) -> None:
        if not args:
            return self.err("chain <good>")
        self.chain_view(args[0])

    def cmd_buildings(self, args: List[str]) -> None:
        self.buildings_view(args[0] if args else "")

    def cmd_info(self, args: List[str]) -> None:
        if not args:
            return self.err("info <building>")
        self.building_info(args[0])

    def cmd_build(self, args: List[str]) -> None:
        if not args:
            return self.err("build <building> [town]")
        key = resolve_building(args[0])
        town = self._node(args[1]) if len(args) > 1 else self.here
        self.say("  " + self.game.build(town, key))

    def cmd_raze(self, args: List[str]) -> None:
        s = self.settlement()
        b = s.demolish(int(args[0]))
        self.say(f"  {b.spec.name} pulled down" if b else "  no such building")

    def cmd_close(self, args: List[str]) -> None:
        s = self.settlement()
        b = s.find(int(args[0]))
        if not b:
            return self.err("no such building")
        b.enabled = not b.enabled
        self.say(f"  {b.spec.name} {'opened' if b.enabled else 'closed'}")

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
        s = self.settlement()
        if not args:
            return self.say(f"  rations at {s.name}: {C.RATION_LABELS[s.ration_level]}")
        s.ration_level = _level(args[0], C.RATION_LABELS)
        self.say(f"  {s.name} now on {C.RATION_LABELS[s.ration_level]} rations")

    def cmd_tax(self, args: List[str]) -> None:
        s = self.settlement()
        if not args:
            return self.say(f"  tax at {s.name}: {C.TAX_LABELS[s.tax_level]}")
        s.tax_level = _level(args[0], C.TAX_LABELS)
        self.say(f"  {s.name} now on {C.TAX_LABELS[s.tax_level]} taxes")

    def cmd_garrison(self, args: List[str]) -> None:
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
        g = self.game
        if args:
            a = g.army(int(args[0]))
            if not a:
                return self.err(f"no host {args[0]}")
            self.say(ink.head(a.name, a.where()),
                     f"  where     {a.where()}",
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
            self.say(f"  [{a.uid}] {a.name:<22} {side:<12} {a.where():<24}"
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
                works, name = t.works(), t.name
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
        g = self.game
        if not args:
            hosts = [a for a in g.armies if a.owner == "player"]
            if not hosts:
                return self.err("you have no host in the field")
            self.say(ink.head("SIEGE ORDERS"))
            for a in hosts:
                self.say(f"  [{a.uid}] {a.name:<22} "
                         f"{PLANS[a.siege.plan].name:<22} {a.where()}")
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
        if len(args) < 2:
            return self.err("march <host> <place>")
        self.say("  " + self.game.march(int(args[0]),
                                        self._node(args[1], shrines=True)))

    def cmd_lord(self, args: List[str]) -> None:
        """Your lord: where he is, what he is worth there, and the risk of it."""
        g = self.game
        if args and args[0].lower() == "ransom":
            return self.say("  " + g.ransom_lord())
        if args and args[0].lower() in ("home", "recall"):
            return self.say("  " + g.lead(0))
        if args:
            return self.say("  " + g.lead(int(args[0])))
        self.say(ink.head(g.lord.name.upper(), g.lord.standing()))
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
        self.say("", ink.c("  lord <host> sends him out, lord home brings him back.",
                           ink.DIM))

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
        if not args:
            return self.err("raid <host>")
        self.say("  " + self.game.raid(int(args[0])))

    def cmd_recall(self, args: List[str]) -> None:
        a = self.game.army(int(args[0]))
        if not a:
            return self.err("no such host")
        self.say("  " + self.game.march(a.uid, a.home))

    def cmd_standdown(self, args: List[str]) -> None:
        self.say("  " + self.game.disband_host(int(args[0])))

    def cmd_war(self, args: List[str]) -> None:
        g = self.game
        self.say(ink.head("THE STATE OF THE MARCH"),
                 "  town          lord                    sworn to    walls"
                 "  could field   mood toward you")
        for key, t in g.world.towns.items():
            if t.mine:
                state = "sworn to you"
            elif t.truce_days:
                state = f"truce ({t.truce_days}d)"
            elif t.hostility > 70:
                state = "arming"
            elif t.hostility > 40:
                state = "cold"
            else:
                state = "civil"
            liege = ("you" if t.mine else
                     g.world.node_name(t.owner) if t.owner else "-")
            might = host_strength(g.likely_host(key))
            mood = (ink.LEAF if t.mine else ink.SEA if t.truce_days else
                    ink.BLOOD if t.hostility > 70 else
                    ink.AMBER if t.hostility > 40 else ink.INK)
            self.say(f"  {ink.c(ink.pad(t.name, 13), ink.PARCH)} "
                     f"{ink.c(ink.pad(t.lord, 23), ink.DIM)} {liege:<10}"
                     f" {t.wall_hp:>6,.0f}  {might:>10,.0f}   "
                     + ink.c(f"{state} ({t.hostility:.0f})", mood))
        mine = sum(host_strength(s.units) for s in g.world.settlements.values())
        mine += sum(host_strength(a.units) for a in g.armies if a.owner == "player")
        self.say("", f"  your own strength {mine:,.0f}, spread over "
                 f"{len(g.world.settlements)} settlements and {len(g.armies)} hosts")
        for a in g.armies:
            who = "yours" if a.owner == "player" else self._name(a.home)
            self.say(f"  host: {a.name} ({who}) -- {a.where()}, {describe(a.units)}")

    def cmd_gift(self, args: List[str]) -> None:
        if len(args) < 2:
            return self.err("gift <town> <coin>")
        self.say("  " + self.game.gift(self._node(args[0]), float(args[1])))

    def cmd_truce(self, args: List[str]) -> None:
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
        if not args:
            return self.err("demand <town>")
        self.say("  " + self.game.demand(self._node(args[0])))

    def cmd_battles(self, args: List[str]) -> None:
        n = int(args[0]) if args else 12
        for line in self.game.battles[-n:]:
            self.say(f"  * {line}")
        if not self.game.battles:
            self.say("  the march has been quiet")

    def cmd_age(self, args: List[str]) -> None:
        g = self.game
        p = g.progress
        if args and args[0].lower() in ("begin", "go", "climb"):
            return self.say("  " + g.begin_age())
        nxt = p.next_age()
        self.say(ink.head(p.age_name().upper()),
                 "  " + ink.c(AGES[p.age].blurb, ink.DIM))
        if p.advancing:
            return self.say(f"  climbing to the {AGES[p.age + 1].name}: "
                            f"{p.advancing} days to go")
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
                     f"{p.research_left:.0f} days to go", "")
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
        if not args:
            sites = ", ".join(self.game.world.sites) or "none left"
            return self.say(f"  unclaimed: {sites}")
        self.say("  " + self.game.found(args[0].lower()))

    def cmd_caravans(self, args: List[str]) -> None:
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
        c = self.game.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
        c.guards = max(0, int(args[1]))
        self.say(f"  {c.name} rides with {c.guards} guards ({c.daily_cost:.0f}c/day)")

    def cmd_route(self, args: List[str]) -> None:
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
        if not args:
            return self.err("auto <caravan>")
        g = self.game
        c = g.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
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
        c = self.game.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
        if not c.route:
            return self.err("it has no route")
        c.start()
        self.say(f"  {c.name} sets out")

    def cmd_stop(self, args: List[str]) -> None:
        c = self.game.caravan(int(args[0]))
        if not c:
            return self.err("no such caravan")
        c.halt()
        self.say(f"  {c.name} will stand down at its next stop")

    def cmd_disband(self, args: List[str]) -> None:
        self.say("  " + self.game.disband(int(args[0])))

    def cmd_scan(self, args: List[str]) -> None:
        sea = any(a.lower() in ("sea", "ship", "cog") for a in args)
        nums = [a for a in args if a.isdigit()]
        self.scan_view(int(nums[0]) if nums else 8, sails=sea)

    def cmd_needs(self, args: List[str]) -> None:
        for s in self.game.world.settlements.values():
            rows = shortage_report(s)
            self.say(f"  {s.name}: " + (", ".join(
                f"{good(k).name} {net:+.1f}/day ({stock:.0f} left,"
                f" {stock / -net:.0f}d)" for k, net, stock in rows[:5] if net < 0)
                or "nothing running down"))

    def cmd_map(self, args: List[str]) -> None:
        self.map_view()

    def cmd_chart(self, args: List[str]) -> None:
        self.chart(args[0] if args else "worth")

    def cmd_log(self, args: List[str]) -> None:
        n = int(args[0]) if args else 15
        for m in self.game.events.log[-n:]:
            self.say(f"  * {m}")

    def cmd_save(self, args: List[str]) -> None:
        self.say("  " + self.game.save(args[0] if args else "marchlands.save"))

    def cmd_load(self, args: List[str]) -> None:
        self.game = GameState.load(args[0] if args else "marchlands.save")
        self.here = next(iter(self.game.world.settlements))
        self.say("  loaded")
        self.status()

    def cmd_quit(self, args: List[str]) -> None:
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


def _level(text: str, labels: Dict[int, str]) -> int:
    t = text.lower()
    for k, v in labels.items():
        if v == t:
            return k
    n = int(text)
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
    "garrison": Console.cmd_garrison, "found": Console.cmd_found,
    "units": Console.cmd_units, "recruit": Console.cmd_recruit,
    "host": Console.cmd_host, "army": Console.cmd_army, "armies": Console.cmd_army,
    "march": Console.cmd_march, "recall": Console.cmd_recall,
    "siege": Console.cmd_siege, "plans": Console.cmd_plans,
    "raid": Console.cmd_raid, "relics": Console.cmd_relics,
    "lord": Console.cmd_lord,
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
                    lord [<id>|home|ransom]     relics
                    war             battles [n]
                    gift <town> <coin>   truce <town> [days]   demand <town>
  ELSE              hint            briefing               scenarios
                    log [n]   save [file]   load [file]   autosave [file]   quit
                    help trade | help town | help war | help win
"""

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

  Hands are shorter than jobs and always will be. `work` shows the queue --
  who gets people first when there are not enough -- and `work <building>
  first` reorders it. Something goes short every morning; you only get to
  choose what.

  Land is the real constraint. You have so many fertile, forest, hill and clay
  slots, and no settlement has all four in quantity. What you cannot grow you
  must buy, and what you have too much of is only worth what a cart can carry
  to somebody who wants it.
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
