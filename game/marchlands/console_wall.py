"""The wall: hosts, the castle and its works, sieges, sallies and battles.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .castle import PLANS, SiegeState, Works
from . import keep as keeps
from . import render as ink
from .military import UNITS, describe, host_strength, host_upkeep
from .military import resolve as resolve_unit


class WallMixin:
    """The console's wall. Mixed into Console; see cli.py."""

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

    def cmd_sally(self, args: List[str]) -> None:
        """Open the gate and go at the siege works."""
        g = self.game
        men = next((int(a) for a in args if a.isdigit()), 0)
        where = self._here_unless(self._place_words(args))
        self.say("  " + g.sally(where, men).replace("\n", "\n  "))

    def cmd_shore(self, args: List[str]) -> None:
        """Put masons on the breach while it is being made."""
        g = self.game
        verb, where = self._verb_and_place(args, ("off", "no", "stop", "on"))
        on = verb not in ("off", "no", "stop")
        self.say("  " + g.shore(self._here_unless(where), on))

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

    def _here_unless(self, where: str) -> str:
        """The town named, or else the one you are looking at -- never the
        seat by default. The page shows this town's gates, bell and breach,
        so a button pressed on it must act on this town and not on the hall."""
        return self._town_named(where) or self.here

    def _town_named(self, where: str) -> str:
        """The settlement this phrase names -- key, key with underscores,
        or display name -- or '' if it names none."""
        towns = self.game.world.settlements
        where = (where or "").strip().lower()
        if not where:
            return ""
        for tried in (where, where.replace(" ", "_")):
            if tried in towns:
                return tried
        by_name = {s.name.lower(): k for k, s in towns.items()}
        return by_name.get(where, "")

    def _verb_and_place(self, args: List[str], verbs) -> Tuple[str, str]:
        """The first verb word is the action, and only that one word is
        taken out of the place -- so `bell ring north stand` rings North
        Stand, and `shore aldworth off` sends the masons off. But a phrase
        that names a town whole is a place with no verb: `bell north stand`
        is North Stand's bell, not "stand down the town on screen"."""
        words = [a for a in args if not a.isdigit()]
        if self._town_named(" ".join(words)):
            return "", " ".join(words)
        for i, w in enumerate(words):
            if w.lower() in verbs:
                return w.lower(), " ".join(words[:i] + words[i + 1:])
        return "", " ".join(words)

    def _place_words(self, args: List[str], verbs=()) -> str:
        """Every word that is not a verb or a number, as one phrase -- so
        `bell ring caer ithel` means Caer Ithel and not the town on screen."""
        return " ".join(a for a in args
                        if not a.isdigit() and a.lower() not in verbs)

    def cmd_bell(self, args: List[str]) -> None:
        """Ring the bell and bring the country hands in, or stand it down."""
        g = self.game
        verb, place = self._verb_and_place(
            args, ("ring", "on", "down", "off", "stand"))
        where = self._here_unless(place)
        s = self.settlement(where)
        if verb in ("down", "off", "stand"):
            return self.say("  " + g.ring_bell(where, False))
        if verb in ("ring", "on") or not s.bell:
            return self.say("  " + g.ring_bell(where, True))
        self.say(f"  the bell has been ringing at {s.name} for "
                 f"{max(0, s.bell - 1)} days -- `bell down` to send them out")

    def cmd_gates(self, args: List[str]) -> None:
        """Shut your gates against the sickness, or open them again."""
        from . import plague
        g = self.game
        verb, place = self._verb_and_place(args, ("shut", "close", "open", "up"))
        where = self._here_unless(place)
        s = self.settlement(where)
        if verb in ("shut", "close"):
            return self.say("  " + g.shut_gates(where, True))
        if verb == "open":
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
        men = next((int(a) for a in args if a.isdigit()), 0)
        where = self._here_unless(self._place_words(args))
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
        """Disband a host: into the garrison, or `square` to send them home to work."""
        uid = self._which(args, "standdown <host> [square]")
        if uid is not None:
            home = any(a.lower() in ("square", "home", "work") for a in args[1:])
            self.say("  " + self.game.disband_host(uid, to_square=home))

    def cmd_battles(self, args: List[str]) -> None:
        """What has been fought, and how it went."""
        n = int(args[0]) if args else 12
        for line in self.game.battles[-n:]:
            self.say(f"  * {line}")
        if not self.game.battles:
            self.say("  the march has been quiet")
