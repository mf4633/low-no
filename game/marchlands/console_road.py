"""The road: carts and their routes, the counting house's scan, and the
rivers.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import List, Optional

from . import config as C
from .advisor import route_from, scan
from . import render as ink
from . import rivers as waters
from .military import sky_on
from .trade import CART, IDLE, MOVING, SHIP, TRADING
from .console_common import _parse_stop


class RoadMixin:
    """The console's road. Mixed into Console; see cli.py."""

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
