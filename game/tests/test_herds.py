"""Livestock as stock, not as scenery.

The point of this one is a seam rather than a mechanic. The beasts are drawn
in the yards, and the yards are paid for what they produce, and those two
numbers have to be the same number -- otherwise the picture tells you a herd
was driven off while the books go on paying you for wool, which is the sort
of lie an interface only gets to tell once.
"""

import random
import unittest

from marchlands import config as C
from marchlands.layout import plan_for
from marchlands.scenarios import start
from marchlands.sim import Bot


def grown(seed: int = 8, days: int = 600):
    g = start("marchlands", seed=seed)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g, g.home()


def a_yard(s):
    return next((b for b in s.buildings
                 if b.key in C.HERD_FULL and b.complete), None)


def raid(g, s, days=12, hard=0.8):
    rng = random.Random(1)
    for d in range(days):
        s.raided = True
        s.raid_pressure = hard
        s.tick("summer", rng, g.progress, day=g.day + d)
    s.raided = False
    s.raid_pressure = 0.0


class TestAYardIsStocked(unittest.TestCase):

    def test_a_finished_yard_comes_with_its_beasts(self):
        """You bought a pasture, not a field."""
        _g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("this town never built a yard that keeps beasts")
        self.assertEqual(yard.head, float(C.HERD_FULL[yard.key]))

    def test_every_yard_that_keeps_beasts_can_be_drawn_and_priced(self):
        for key in C.HERD_FULL:
            self.assertIn(key, C.HERD_PRICE, f"{key} has head and no price")
            from marchlands.layout import HERDS
            self.assertIn(key, HERDS, f"{key} has head and nothing to draw")


class TestARaidTakesThem(unittest.TestCase):

    def test_the_flock_goes_down_while_the_riders_are_there(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        was = yard.head
        raid(g, s)
        self.assertLess(yard.head, was * 0.5,
                        "twelve days of raiding and the flock is intact")

    def test_and_the_wool_goes_with_them(self):
        """The whole point. A raid used to cost exactly as long as it lasted."""
        g, s = grown()
        yard = a_yard(s)
        if yard is None or not yard.spec.outputs:
            self.skipTest("no yard that makes anything")
        good = next(iter(yard.spec.outputs))
        rng = random.Random(2)
        s.tick("summer", rng, g.progress, day=g.day)
        before = s.report.produced.get(good, 0.0)
        raid(g, s)
        s.tick("summer", rng, g.progress, day=g.day + 40)
        after = s.report.produced.get(good, 0.0)
        self.assertLess(after, before * 0.5,
                        f"the flock is gone and {good} is still coming in at "
                        f"{after:.1f} against {before:.1f}")

    def test_the_bill_outlives_the_raid(self):
        """Which is the difference between a raid and a bad week."""
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        raid(g, s)
        thin = yard.head
        rng = random.Random(3)
        for d in range(60):
            s.tick("summer", rng, g.progress, day=g.day + 40 + d)
        self.assertLess(yard.head, C.HERD_FULL[yard.key],
                        "two months on and the flock is back as if nothing "
                        "happened; a raid that costs nothing afterwards is a "
                        "bad week, not a raid")
        self.assertGreaterEqual(yard.head, thin)


class TestBreedingBack(unittest.TestCase):

    def test_a_worked_yard_breeds_back(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        full = C.HERD_FULL[yard.key]
        yard.head = full * 0.5
        rng = random.Random(4)
        for d in range(30):
            s.tick("summer", rng, g.progress, day=g.day + d)
        self.assertGreater(yard.head, full * 0.5)

    def test_but_not_from_nothing(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        yard.head = 0.0
        rng = random.Random(5)
        for d in range(120):
            s.tick("summer", rng, g.progress, day=g.day + d)
        self.assertEqual(yard.head, 0.0,
                         "an empty fold bred a flock out of nothing")

    def test_and_a_flock_it_cannot_breed_from_can_be_bought(self):
        """A rule that a flock cannot recover is only fair with a way to pay.

        The first cut of this had the rule and not the lever, which is a
        pasture a raid destroys for good and no way to tell that from a bug.
        """
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        here = next(k for k, v in g.world.settlements.items() if v is s)
        yard.head = 0.0
        g.treasury = 50_000.0
        purse = g.treasury
        said = g.restock(here, yard.uid)
        self.assertIn("head driven in", said)
        self.assertEqual(yard.head, float(C.HERD_FULL[yard.key]))
        self.assertLess(g.treasury, purse, "the beasts were free")

    def test_an_empty_purse_buys_nothing(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        here = next(k for k, v in g.world.settlements.items() if v is s)
        yard.head = 0.0
        g.treasury = 1.0
        self.assertIn("and you have", g.restock(here, yard.uid))
        self.assertEqual(yard.head, 0.0)

    def test_a_full_yard_is_not_sold_more(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        here = next(k for k, v in g.world.settlements.items() if v is s)
        yard.head = float(C.HERD_FULL[yard.key])
        g.treasury = 50_000.0
        purse = g.treasury
        self.assertIn("fully stocked", g.restock(here, yard.uid))
        self.assertEqual(g.treasury, purse)


class TestThePictureAndTheBooksAgree(unittest.TestCase):
    """The seam this whole thing exists to close."""

    def test_what_is_drawn_is_what_is_kept(self):
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        for head in (0.0, 1.0, 3.0, float(C.HERD_FULL[yard.key])):
            yard.head = head
            drawn = [a for a in plan_for(s).beasts if a.at == yard.uid]
            self.assertEqual(len(drawn), int(round(head)),
                             f"{head:.0f} head kept and {len(drawn)} drawn")

    def test_a_raid_empties_the_field_because_the_fold_is_empty(self):
        """Not because a renderer was told a raid looks like an empty field."""
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        self.assertTrue(plan_for(s).beasts)
        raid(g, s)
        drawn = len([a for a in plan_for(s).beasts if a.at == yard.uid])
        self.assertEqual(drawn, int(round(yard.head)))
        self.assertLess(drawn, C.HERD_FULL[yard.key])

    def test_the_herd_survives_a_save(self):
        import json
        from marchlands.engine import GameState
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        yard.head = 2.5
        h = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        back = next(b for b in h.home().buildings if b.uid == yard.uid)
        self.assertAlmostEqual(back.head, 2.5)

    def test_a_save_from_before_the_beasts_stocks_itself(self):
        import json
        from marchlands.engine import GameState
        g, s = grown()
        yard = a_yard(s)
        if yard is None:
            self.skipTest("no yard")
        d = g.to_dict()
        for town in d["world"]["settlements"].values():
            for b in town["buildings"]:
                b.pop("head", None)
        h = GameState.from_dict(json.loads(json.dumps(d)))
        back = next(b for b in h.home().buildings if b.uid == yard.uid)
        self.assertEqual(back.head, -1.0)
        h.tick()
        self.assertEqual(back.head, float(C.HERD_FULL[back.key]))


if __name__ == "__main__":
    unittest.main()
