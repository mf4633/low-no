"""The town: drawing it, the sheds and their hands, rations, herds, the
ages and the research.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from . import config as C
from .advisor import shortage_report
from .buildings import ALL_BUILDING_KEYS, BUILDINGS, building
from .buildings import resolve as resolve_building
from .goods import ALL_KEYS, good
from . import render as ink
from . import rivers as waters
from .military import sky_on
from .tech import AGES, HOUSES, TECHS
from .iso import scene
from .view import GLYPHS, townscape
from .console_common import RULE, sparkline, _node_colour, _level


class TownMixin:
    """The console's town. Mixed into Console; see cli.py."""

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

    def cmd_rest(self, args: List[str]) -> None:
        """rest <building> <hands> -- stand hands off a shed; `rest free` ends it."""
        st = self.settlement()
        if args and args[0] in ("free", "all"):
            n, st.resting = st.resting, 0
            st._seat_hands()
            return self.say(f"  {n} hands standing about go back to the queue")
        uid = self._which(args, "rest <building> <hands> | rest free")
        if uid is None:
            return
        try:
            hands = int(args[1]) if len(args) > 1 else 1 << 30
        except ValueError:
            return self.err("rest <building> <hands> | rest free")
        self.say("  " + st.rest_hands(uid, hands))

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

    def cmd_map(self, args: List[str]) -> None:
        """The march as a chart of who is where."""
        self.map_view()

    def cmd_chart(self, args: List[str]) -> None:
        """One measure of yours, drawn over time."""
        self.chart(args[0] if args else "worth")
