"""Telling a host how to fight, before it has to.

The thing worth taking from a real-time battle is not the clicking. It is
that you arrived having decided something and then watched the decision be
right or wrong. A day-ticked game can offer exactly that, and it costs no new
simulation: every order multiplies dials `fight` already reads.
"""

from __future__ import annotations

import random
import unittest

from marchlands.military import (FLANK, HOLD, LINE, ORDERS, RESERVE, STORM,
                                 Side, fight, order, order_note, ordered)
from marchlands.scenarios import start
from marchlands.sim import Bot


def odds(att_order, mult=1.05, n=300, def_order=LINE):
    won = 0
    for i in range(n):
        a = Side({"spearman": 40 * mult, "archer": 18 * mult, "knight": 8 * mult})
        d = Side({"spearman": 42, "archer": 20, "man_at_arms": 10})
        won += fight(a, d, rng=random.Random(i),
                     orders=(att_order, def_order)).winner == "attacker"
    return won / n


class TestTheOrdersThemselves(unittest.TestCase):
    def test_every_order_says_what_it_is_for(self):
        for o in ORDERS.values():
            self.assertTrue(o.name and o.blurb, o.key)

    def test_none_of_them_is_free(self):
        # An order with no downside is not a decision.
        for o in ORDERS.values():
            if o.key == LINE:
                continue
            gains = [o.attack > 1.0, o.defense > 1.0, o.morale > 1.0]
            costs = [o.attack < 1.0, o.defense < 1.0, o.morale < 1.0]
            self.assertTrue(any(gains), o.key)
            self.assertTrue(any(costs) or o.rounds != 14, o.key)

    def test_the_line_is_the_one_with_no_opinion(self):
        o = order(LINE)
        self.assertEqual((o.attack, o.defense, o.morale), (1.0, 1.0, 1.0))

    def test_an_unknown_order_falls_back_rather_than_raising(self):
        self.assertEqual(order("nonesuch").key, LINE)


class TestAnOrderDoesNotEditTheHost(unittest.TestCase):
    def test_it_returns_a_new_side(self):
        # A battle is resolved against copies. An order that changed the host
        # it was given would leave the survivors permanently braver.
        side = Side({"spearman": 30}, attack_mult=1.0, morale=1.0)
        out = ordered(side, STORM)
        self.assertIsNot(out, side)
        self.assertEqual(side.attack_mult, 1.0)
        self.assertNotEqual(out.attack_mult, 1.0)

    def test_an_order_that_wants_horse_is_worth_nothing_without_any(self):
        foot = Side({"spearman": 40})
        horse = Side({"knight": 40})
        self.assertLess(ordered(foot, FLANK).attack_mult,
                        ordered(horse, FLANK).attack_mult)

    def test_and_says_so(self):
        self.assertIn("no horse", order_note({"spearman": 40}, FLANK))
        self.assertIn("worth", order_note({"knight": 40}, FLANK))


class TestItDecidesACloseFightAndNothingElse(unittest.TestCase):
    """The combat model is a knife edge -- at even strength the attacker wins
    one time in sixty, at ten per cent over he wins every time. An order
    worth a quarter therefore did not tilt battles, it decided them: "form
    the line" won two per cent of the fights "send the horse wide" won
    ninety-five per cent of."""

    def test_the_order_matters_in_a_close_fight(self):
        plain = odds(LINE)
        self.assertGreater(odds(FLANK), plain + 0.15)
        self.assertGreater(odds(RESERVE), plain + 0.15)

    def test_it_cannot_rescue_a_rout(self):
        for key in ORDERS:
            self.assertLess(odds(key, mult=0.85, n=120), 0.1, key)

    def test_nor_lose_a_won_battle(self):
        for key in ORDERS:
            self.assertGreater(odds(key, mult=1.25, n=120), 0.9, key)

    def test_no_single_order_is_simply_correct(self):
        # If one order beat the line by fifty points everywhere, there would
        # be one order.
        spread = {k: odds(k, n=200) for k in ORDERS}
        self.assertLess(max(spread.values()) - min(spread.values()), 0.6,
                        spread)


class TestGivingOne(unittest.TestCase):
    def host(self):
        g = start("marchlands", seed=7)
        Bot(g).run(200)
        here = next(iter(g.world.settlements))
        g.world.settlements[here].units.update({"spearman": 40, "knight": 10})
        a, _why = g.raise_host(here, {"spearman": 30, "knight": 8})
        return g, a

    def test_a_host_starts_in_line(self):
        _g, a = self.host()
        self.assertEqual(a.order, LINE)

    def test_you_can_change_it(self):
        g, a = self.host()
        said = g.order_host(a.uid, FLANK)
        self.assertEqual(a.order, FLANK)
        self.assertIn("horse", said)

    def test_a_nonsense_order_is_a_message_not_a_crash(self):
        g, a = self.host()
        self.assertIn("no order called", g.order_host(a.uid, "nonesuch"))
        self.assertEqual(a.order, LINE)

    def test_you_cannot_order_somebody_elses_host(self):
        g, _a = self.host()
        foe = next(k for k, t in g.world.towns.items() if not t.mine)
        from marchlands.military import Army
        theirs = Army(uid=9100, name="x", owner=foe, units={"spearman": 10})
        g.armies.append(theirs)
        self.assertIn("not yours", g.order_host(9100, STORM))

    def test_it_survives_a_save(self):
        import os
        import tempfile
        g, a = self.host()
        g.order_host(a.uid, RESERVE)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            g.save(path)
            back = type(g).load(path)
        self.assertEqual(back.army(a.uid).order, RESERVE)


class TestEachLordFightsLikeHimself(unittest.TestCase):
    def test_the_sorts_do_not_all_fight_the_same_way(self):
        from marchlands.lords import SORTS
        how = {s.fights for s in SORTS.values()}
        self.assertGreater(len(how), 2, "six lords, one tactic")

    def test_and_each_one_fights_the_way_he_talks(self):
        from marchlands.lords import SORTS
        self.assertEqual(SORTS["boar"].fights, STORM)
        self.assertEqual(SORTS["heron"].fights, HOLD)

    def test_every_sort_names_an_order_that_exists(self):
        from marchlands.lords import SORTS
        for s in SORTS.values():
            self.assertIn(s.fights, ORDERS, s.key)


if __name__ == "__main__":
    unittest.main()
