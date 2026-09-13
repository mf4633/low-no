"""Terminal interface. Stdlib only, no curses, works over ssh and in a pipe."""

from __future__ import annotations

import shlex
import sys
from typing import Dict, List, Optional, Sequence

from . import config as C
from .advisor import route_from, scan, shortage_report
from .buildings import ALL_BUILDING_KEYS, BUILDINGS, building
from .buildings import resolve as resolve_building
from .engine import GameState
from .goods import ALL_KEYS, good
from .goods import resolve as resolve_good
from .military import UNITS, describe, host_strength, host_upkeep
from .military import resolve as resolve_unit
from .scenario import new_game
from .tech import AGES, HOUSES, TECHS
from .trade import IDLE, MOVING, TRADING, Order, Stop

BARS = " ▁▂▃▄▅▆▇█"
RULE = "-" * 72


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

    def _node(self, text: str) -> str:
        return self.game.world.resolve(text)

    def _name(self, key: str) -> str:
        return self.game.world.node_name(key)

    # ================================================================ views
    def status(self) -> None:
        g = self.game
        led = g.ledger
        p = g.progress
        vassals = g.world.vassals()
        self.say(RULE,
                 f"  {g.date_str():<38}  treasury {g.treasury:>10,.0f}c",
                 f"  net worth {g.net_worth():>10,.0f}c of {C.GOAL_NET_WORTH:,.0f}"
                 f"      souls {g.population:>6,.0f} of {C.GOAL_POPULATION}",
                 f"  {p.age_name():<24} {HOUSES[g.house].name if g.house else '':<26}"
                 f"  towns sworn {len(vassals)} of {C.GOAL_TOWNS}",
                 RULE)
        for s in g.world.settlements.values():
            bar = "#" * int(s.popularity / 5) + "." * (20 - int(s.popularity / 5))
            siege = " UNDER SIEGE" if s.besieged else ""
            self.say(f"  {s.name:<12} pop {s.population:>6,.0f}/"
                     f"{s.housing(p):<5,.0f}"
                     f"  mood [{bar}] {s.popularity:>4.0f}"
                     f"  work {s.employed:>3}/{s.jobs_offered:<3}"
                     f"  {C.RATION_LABELS[s.ration_level]} rations,"
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
                 f"  day's ledger   taxes {led.taxes:+8,.0f}   trade {led.trade:+9,.0f}"
                 f"   tribute {led.tribute:+7,.0f}   interest {led.interest:+6,.0f}",
                 f"                 wages {-led.wages:+8,.0f}   upkeep {-led.upkeep:+9,.0f}"
                 f"   carts {-led.caravans:+9,.0f}   war {-led.war:+11,.0f}",
                 f"                 net   {led.net:+8,.0f}c")
        if len(g.history) > 3:
            self.say(f"  worth  {sparkline([h['worth'] for h in g.history])}")
        for m in g.messages[-8:]:
            self.say(f"  * {m}")
        if g.over:
            self.say(RULE, f"  {g.over}", RULE)

    def town_view(self, key: Optional[str] = None) -> None:
        s = self.settlement(key)
        p = self.game.progress
        self.say(RULE, f"  {s.name}  --  pop {s.population:,.0f}, "
                 f"housing {s.housing(p):,.0f}, mood {s.popularity:.0f}"
                 + ("  *** UNDER SIEGE ***" if s.besieged else ""), RULE)
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
        self.say("   id  building            staff  running  note")
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
            self.say(f"  {b.uid:>3}  {b.spec.name:<20}{jobs:>5}  {run:>9}  {b.idle_reason}")
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
        self.say(RULE, f"  {s.name} stores", RULE,
                 "  good           stock    price   made/day   used/day")
        rows = []
        for k in ALL_KEYS:
            stock = s.market.stock[k]
            made = rep.produced.get(k, 0.0)
            used = rep.consumed.get(k, 0.0) + rep.eaten.get(k, 0.0)
            if stock < 0.5 and not made and not used:
                continue
            rows.append((k, stock, s.market.price(k), made, used))
        for k, stock, price, made, used in rows[:count]:
            flag = "  <-- falling" if used > made + 0.01 and stock < 60 else ""
            self.say(f"  {good(k).name:<12}{stock:>8,.0f}  {price:>7.2f}"
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
        self.say(RULE, f"  {good(k).name}  --  base {good(k).base_price:.2f}c,"
                 f" {good(k).weight:.1f} cart units, "
                 f"{100 * good(k).spoilage:.1f}%/day spoilage", RULE,
                 "  place          they pay   they ask   stock   trend")
        rows = []
        for node in g.world.all_nodes():
            m = g.world.market_of(node)
            if not m or not m.sells(k):
                continue
            rows.append((node, m))
        rows.sort(key=lambda r: -r[1].bid(k))
        for node, m in rows:
            spark = sparkline(m.history[k], 20)
            tag = " (yours)" if g.world.is_mine(node) else ""
            self.say(f"  {self._name(node) + tag:<14}{m.bid(k):>10.2f}{m.ask(k):>11.2f}"
                     f"{m.stock[k]:>8,.0f}   {spark}")

    def chain_view(self, gkey: str) -> None:
        k = resolve_good(gkey)
        self.say(RULE, f"  {good(k).name} chain", RULE)
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
        self.say(RULE, "  what you may raise", RULE,
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
        self.say(RULE, f"  {b.name} ({b.key})", RULE,
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
            self.say(RULE, f"  caravans ({len(g.caravans)}/{g.caravan_limit})", RULE)
            for c in g.caravans:
                state = {IDLE: "idle", MOVING: "on the road", TRADING: "in town"}[c.state]
                self.say(f"  [{c.uid}] {c.name:<12} {state:<12} {c.where():<22}"
                         f" {c.guards} guards  {c.total_profit:+,.0f}c lifetime")
                if c.route:
                    self.say("       route: " + "  ->  ".join(
                        s.describe() for s in c.route) + ("  (looping)" if c.running else "  (halted)"))
            return
        c = g.caravan(uid)
        if not c:
            return self.err(f"no caravan {uid}")
        self.say(RULE, f"  [{c.uid}] {c.name}", RULE,
                 f"  where     {c.where()}",
                 f"  cargo     {c.manifest()}  ({c.load:.0f}/{c.capacity:.0f} cart units)",
                 f"  guards    {c.guards}  ({c.daily_cost:.0f}c/day all in)",
                 f"  earned    {c.total_profit:+,.0f}c lifetime")
        for i, s in enumerate(c.route):
            mark = ">" if i == c.leg % max(1, len(c.route)) else " "
            self.say(f"   {mark} {s.describe()}")
        for line in c.log[-8:]:
            self.say(f"     . {line}")

    def scan_view(self, top: int = 8) -> None:
        g = self.game
        cap = C.CARAVAN_BASE_CAPACITY + self.settlement().effect("caravan_capacity")
        spd = C.CARAVAN_BASE_SPEED + self.settlement().effect("caravan_speed")
        self.say(RULE, f"  the counting house  (cart of {cap:.0f} units at {spd:.0f} leagues/day,"
                 f" all costs in)", RULE)
        for o in scan(g.world, self.here, capacity=cap, speed=spd,
                      budget=max(0.0, g.treasury), top=top):
            self.say("  " + o.describe(self._name))
        self.say("  (`auto <caravan>` puts a cart on the best of these)")

    def map_view(self) -> None:
        g = self.game
        w, h = 62, 19
        xs = [c[0] for c in g.world.coords.values()] + [s.x for s in g.world.sites.values()]
        ys = [c[1] for c in g.world.coords.values()] + [s.y for s in g.world.sites.values()]
        lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
        grid = [[" "] * w for _ in range(h)]

        def plot(x: float, y: float, label: str) -> None:
            cx = min(w - len(label) - 1,
                     int((x - lo_x) / max(hi_x - lo_x, 1e-6) * (w - 14)) + 1)
            cy = int((hi_y - y) / max(hi_y - lo_y, 1e-6) * (h - 2)) + 1
            for row in (cy, cy + 1, cy - 1, cy + 2):   # nudge off a neighbour
                if not 0 <= row < h:
                    continue
                span = grid[row][max(0, cx - 1):cx + len(label) + 1]
                if all(ch == " " for ch in span):
                    cy = row
                    break
            for i, ch in enumerate(label):
                if 0 <= cx + i < w:
                    grid[cy][cx + i] = ch

        labels: List[str] = []
        for key, (x, y) in sorted(g.world.coords.items()):
            plot(x, y, ("@" if g.world.is_mine(key) else "o") + self._name(key))
            labels.append(f"{self._name(key):<10} {g.world.distance(self.here, key):>4.0f} leagues")
        for key, site in g.world.sites.items():
            plot(site.x, site.y, "+" + site.name)
        self.say(RULE, "  the marchlands   (@ yours, o foreign, + unclaimed)", RULE)
        for row in grid:
            self.say("  " + "".join(row).rstrip())
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
            if topic in HELP_TOPICS:
                return self.say(HELP_TOPICS[topic])
        self.say(HELP)

    def cmd_next(self, args: List[str]) -> None:
        n = int(args[0]) if args else 1
        self.game.advance(n)
        self.status()

    def cmd_status(self, args: List[str]) -> None:
        self.status()

    def cmd_town(self, args: List[str]) -> None:
        if args:
            key = self._node(args[0])
            if key in self.game.world.settlements:
                self.here = key
        self.town_view()

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
        self.say(RULE, f"  {s.name} garrison", RULE,
                 f"  {s.garrison_line()}",
                 f"  strength {host_strength(s.units):.0f}, "
                 f"upkeep {host_upkeep(s.units):.0f}c/day",
                 f"  wall {s.wall_hp:,.0f}/{s.wall_max(p):,.0f}"
                 f"   works {s.effect('defense'):.0f}"
                 f"   battlements {s.effect('battlement'):.0f}")

    def cmd_units(self, args: List[str]) -> None:
        p = self.game.progress
        self.say(RULE, "  who you may muster", RULE,
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
            self.say(RULE, f"  [{a.uid}] {a.name}", RULE,
                     f"  where     {a.where()}",
                     f"  strength  {host_strength(a.units):.0f}"
                     f"   upkeep {a.upkeep:.0f}c/day"
                     f"   siege {a.siege_power:.0f}",
                     f"  host      {describe(a.units)}")
            for line in a.log[-8:]:
                self.say(f"     . {line}")
            return
        self.say(RULE, "  hosts in the field", RULE)
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

    def cmd_march(self, args: List[str]) -> None:
        if len(args) < 2:
            return self.err("march <host> <place>")
        self.say("  " + self.game.march(int(args[0]), self._node(args[1])))

    def cmd_recall(self, args: List[str]) -> None:
        a = self.game.army(int(args[0]))
        if not a:
            return self.err("no such host")
        self.say("  " + self.game.march(a.uid, a.home))

    def cmd_standdown(self, args: List[str]) -> None:
        self.say("  " + self.game.disband_host(int(args[0])))

    def cmd_war(self, args: List[str]) -> None:
        g = self.game
        self.say(RULE, "  the state of the march", RULE,
                 "  town          lord                     walls   could field"
                 "   mood toward you")
        for key, t in g.world.towns.items():
            if t.mine:
                state = "sworn to you"
            elif t.hostility > 70:
                state = "arming"
            elif t.hostility > 40:
                state = "cold"
            else:
                state = "civil"
            might = host_strength(g.likely_host(key))
            self.say(f"  {t.name:<13} {t.lord:<24} {t.wall_hp:>5,.0f}"
                     f"   {might:>9,.0f}   {state} ({t.hostility:.0f})")
        mine = sum(host_strength(s.units) for s in g.world.settlements.values())
        mine += sum(host_strength(a.units) for a in g.armies if a.owner == "player")
        self.say("", f"  your own strength {mine:,.0f}, spread over "
                 f"{len(g.world.settlements)} settlements and {len(g.armies)} hosts")
        for a in g.armies:
            who = "yours" if a.owner == "player" else self._name(a.home)
            self.say(f"  host: {a.name} ({who}) -- {a.where()}, {describe(a.units)}")

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
        self.say(RULE, f"  {p.age_name()}", RULE, f"  {AGES[p.age].blurb}")
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
        self.say(RULE, f"  the guildhall  ({p.age_name()})", RULE)
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
        town = self._node(args[0]) if args else self.here
        name = args[1] if len(args) > 1 else ""
        c, why = self.game.new_caravan(town, name)
        self.say(f"  {c.name} outfitted at {self._name(town)}" if c else f"  ! {why}")

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
        opts = scan(g.world, self.here, capacity=c.capacity, speed=c.speed,
                    budget=max(0.0, g.treasury), top=3)
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
        self.scan_view(int(args[0]) if args else 8)

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
    "market": Console.cmd_market, "prices": Console.cmd_prices,
    "chain": Console.cmd_chain, "buildings": Console.cmd_buildings,
    "info": Console.cmd_info, "build": Console.cmd_build, "raze": Console.cmd_raze,
    "close": Console.cmd_close, "ration": Console.cmd_ration, "tax": Console.cmd_tax,
    "garrison": Console.cmd_garrison, "found": Console.cmd_found,
    "units": Console.cmd_units, "recruit": Console.cmd_recruit,
    "host": Console.cmd_host, "army": Console.cmd_army, "armies": Console.cmd_army,
    "march": Console.cmd_march, "recall": Console.cmd_recall,
    "standdown": Console.cmd_standdown, "war": Console.cmd_war,
    "battles": Console.cmd_battles, "age": Console.cmd_age,
    "tech": Console.cmd_tech, "research": Console.cmd_tech,
    "caravans": Console.cmd_caravans, "c": Console.cmd_caravans,
    "new": Console.cmd_new, "guards": Console.cmd_guards, "route": Console.cmd_route,
    "auto": Console.cmd_auto, "go": Console.cmd_go, "stop": Console.cmd_stop,
    "disband": Console.cmd_disband, "scan": Console.cmd_scan, "needs": Console.cmd_needs,
    "map": Console.cmd_map, "chart": Console.cmd_chart, "log": Console.cmd_log,
    "save": Console.cmd_save, "load": Console.cmd_load, "quit": Console.cmd_quit,
    "exit": Console.cmd_quit,
}

HELP = """
  THE DAY           next [n]        let n days pass        status / s
  YOUR TOWN         town [name]     stores [town]          needs
                    build <key>     buildings [filter]     info <key>
                    close <id>      raze <id>
                    ration <level>  tax <level>            found [site]
  THE LONG GAME     age | age begin                        tech [key]
  THE MARKET        market <town>   prices <good>          chain <good>
                    scan [n]        map                    chart [metric]
  THE ROAD          caravans / c    caravan <id>           new [town] [name]
                    auto <id>       go <id>                stop <id>
                    guards <id> <n> disband <id>
                    route <id> add <town> buy <good> <qty>[@max] sell <good> all[@min]
                    route <id> clear | show
  WAR               units           recruit <who> [n]      garrison [town]
                    host <town> <who> <n> ...              army [id]
                    march <id> <place>   recall <id>       standdown <id>
                    war             battles [n]
  ELSE              log [n]   save [file]   load [file]   quit
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
  the two levers; comforts (ale, cloth, pottery, salt) and a chapel or inn do
  the rest. Mood sets productivity -- at 50 your workers run at full, at 100
  half again, below 18 they down tools altogether.

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
  standing: without rams or trebuchets a host can only sit outside and starve.

  Lords grow bolder the richer you get. `war` shows who is arming. Take a town
  and it bends the knee -- no tolls, daily tribute, and every other lord one
  step angrier. Five towns sworn to you wins the game outright.

  A storming is not the end. The keep is thrown down, the town gutted, and you
  start again from whatever else you hold -- which is the best argument there
  is for founding a second settlement before you need one. You are only
  finished when there is nowhere left.
""",
    "win": f"""
  Three ways, inside {C.GOAL_DAYS // C.DAYS_PER_YEAR} years:

    WEALTH    {C.GOAL_NET_WORTH:,.0f}c of net worth with {C.GOAL_POPULATION} souls under your rule.
    DOMINION  {C.GOAL_TOWNS} of the seven towns sworn to you.
    THE BELLS Finish the cathedral and hold it half a year.

  You lose if your debts pass {abs(C.BANKRUPTCY_FLOOR):,.0f}c, the last family
  walks out of the gate, or the settlement holding your keep is stormed.
""",
}


def play(game: Optional[GameState] = None, script: Optional[Sequence[str]] = None,
         out=sys.stdout) -> Console:
    con = Console(game or new_game(), out=out)
    con.say(BANNER)
    con.status()
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
