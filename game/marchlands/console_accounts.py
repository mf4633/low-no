"""The books: markets and prices, tax, the economist's readouts, the mint
and the assize.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import List

from . import config as C
from .advisor import shortage_report
from .buildings import BUILDINGS
from .economics import (compare, daily_output, marginal_hands,
                        surplus, town_output)
from .goods import ALL_KEYS, good
from .goods import resolve as resolve_good
from . import chancery
from . import render as ink
from .console_common import RULE, _level


class AccountsMixin:
    """The console's accounts. Mixed into Console; see cli.py."""

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

    def cmd_needs(self, args: List[str]) -> None:
        """What your own town is short of, and where it is cheap."""
        for s in self.game.world.settlements.values():
            rows = shortage_report(s)
            self.say(f"  {s.name}: " + (", ".join(
                f"{good(k).name} {net:+.1f}/day ({stock:.0f} left,"
                f" {stock / -net:.0f}d)" for k, net, stock in rows[:5] if net < 0)
                or "nothing running down"))
