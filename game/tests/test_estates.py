"""The three men who actually run the march.

A lord in this game was an unusually lonely autocrat: he set the tax rate and
the tax rate happened, capped the price of bread and the price of bread was
capped, struck coin and nobody objected. Every dial cost coin or mood and
none cost him somebody powerful being annoyed about it.

These tests are about the two things that keep estates from being a fourth
resource bar: a grievance is something the player actually did, and a
privilege is a real trade rather than a free loyalty button.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from marchlands import estates as est
from marchlands.estates import ANGRY, Estates, SULKY
from marchlands.scenarios import start
from marchlands.sim import Bot


def grown(seed=5, days=200):
    g = start("marchlands", seed=seed)
    Bot(g).run(days)
    return g


class TestTheyWantDifferentThings(unittest.TestCase):
    def test_there_are_three_of_them_and_each_holds_something(self):
        gives = {e.gives for e in est.ESTATES.values()}
        self.assertEqual(len(gives), len(est.ESTATES),
                         "two estates holding the same thing is one estate")

    def test_loyalty_is_worth_something_real_at_both_ends(self):
        for e in est.ESTATES.values():
            self.assertGreater(e.best, 1.0, e.key)
            self.assertLess(e.worst, 1.0, e.key)

    def test_a_contented_estate_gives_more_than_a_sulking_one(self):
        e = Estates()
        e.by_key["knights"].loyalty = 95.0
        good = e.mult("muster")
        e.by_key["knights"].loyalty = 5.0
        self.assertGreater(good, e.mult("muster"))

    def test_every_privilege_belongs_to_an_estate_that_exists(self):
        for p in est.PRIVILEGES.values():
            self.assertIn(p.estate, est.ESTATES, p.key)
            self.assertTrue(p.cost, p.key)
            self.assertTrue(p.blurb, p.key)


class TestAGrievanceIsSomethingYouDid(unittest.TestCase):
    def test_taxing_them_hard_costs_you_their_loyalty(self):
        g = grown()
        for s in g.world.settlements.values():
            s.tax_level = 4
        g.advance(120)
        book = dict(g.estates.why("knights", g.day))
        self.assertTrue(any("tax" in k for k in book), book)
        self.assertLess(g.estates.by_key["knights"].loyalty, 50.0)

    def test_capping_a_price_is_a_guild_grievance_by_construction(self):
        g = grown()
        g.economy.assize = {"bread": 3.0}
        g.advance(90)
        book = dict(g.estates.why("guilds", g.day))
        self.assertTrue(any("price" in k for k in book), book)

    def test_striking_coin_is_the_chapters_oldest_complaint(self):
        g = grown()
        g.economy.minted = 20_000.0
        g.advance(90)
        book = dict(g.estates.why("chapter", g.day))
        self.assertTrue(any("struck coin" in k for k in book), book)

    def test_one_entry_per_grievance_not_one_per_day(self):
        # A tax rise held for a year is one thing somebody keeps mentioning,
        # not three hundred and sixty-five of them.
        g = grown()
        for s in g.world.settlements.values():
            s.tax_level = 4
        g.advance(150)
        book = g.estates.by_key["knights"].ledger
        self.assertEqual(len(book), len({x.what for x in book}))
        self.assertLessEqual(len(book), 12)

    def test_a_grievance_fades_when_you_stop(self):
        e = Estates()
        e.note("guilds", "something", -30.0, day=0)
        self.assertLess(e.by_key["guilds"].target(0), 30.0)
        self.assertGreater(e.by_key["guilds"].target(400),
                           e.by_key["guilds"].target(0))


class TestSulkingCostsYouSomethingYouCanCount(unittest.TestCase):
    """Not a message: fewer men actually mustering."""

    def test_angry_knights_send_fewer_men_than_you_paid_for(self):
        g = grown(days=300)
        here = next(iter(g.world.settlements))
        s = g.world.settlements[here]
        s.buildings = s.buildings          # unchanged; just naming it
        g.estates.by_key["knights"].loyalty = 2.0
        g.treasury += 100_000
        for key in ("spearman",):
            before = s.units.get(key, 0.0)
            said = g.recruit(here, key, 20)
            if "no barracks" in said or "spare hands" in said:
                return self.skipTest(said)
            got = s.units.get(key, 0.0) - before
            self.assertLess(got, 20, said)
            self.assertIn("spared what they chose", said)

    def test_a_sulking_chapter_slows_your_learning(self):
        e = Estates()
        e.by_key["chapter"].loyalty = 95.0
        quick = e.mult("research")
        e.by_key["chapter"].loyalty = 5.0
        self.assertLess(e.mult("research"), quick)

    def test_they_say_so_when_they_cross_the_line(self):
        e = Estates()
        e.by_key["guilds"].loyalty = SULKY + 1.0
        e.note("guilds", "everything", -60.0, day=0)
        said = []
        for day in range(60):
            said += e.day(day)
        self.assertTrue(any("withhold" in s for s in said), said)


class TestAPrivilegeIsARealTrade(unittest.TestCase):
    def test_granting_one_raises_them_and_costs_you_a_dial(self):
        g = grown()
        was = g.estates.mult("tax") if False else g.estates.effect("tax")
        g.estates.grant("exemption", g.day)
        self.assertLess(g.estates.effect("tax"), was)
        self.assertIn("exemption", g.estates.by_key["knights"].privileges)

    def test_the_greater_levy_is_more_men_and_not_a_line_of_text(self):
        g = grown()
        before = g.estates.mult("muster")
        g.estates.grant("levy", g.day)
        self.assertGreater(g.estates.mult("muster"), before)

    def test_a_chartered_market_cannot_be_capped(self):
        g = grown()
        g.progress.researched.add("assize_of_bread")
        self.assertNotIn("chartered", g.decree("bread", 3.0))
        g.estates.grant("charter", g.day)
        self.assertIn("chartered", g.decree("bread", 2.0))

    def test_but_lifting_a_cap_is_always_allowed(self):
        # Refusing to let a player *un*cap a price would be a trap, not a cost.
        g = grown()
        g.progress.researched.add("assize_of_bread")
        g.decree("bread", 3.0)
        g.estates.grant("charter", g.day)
        self.assertNotIn("chartered", g.decree("bread", 0.0))

    def test_taking_one_back_is_worse_than_never_giving_it(self):
        e = Estates()
        clean = e.by_key["guilds"].target(0)
        e.grant("charter", 0)
        e.revoke("charter", 0)
        self.assertLess(e.by_key["guilds"].target(0), clean)

    def test_a_privilege_nobody_has_is_a_message_not_a_crash(self):
        e = Estates()
        self.assertIn("no privilege", e.grant("nonesuch", 0))
        self.assertIn("do not have", e.revoke("charter", 0))

    def test_granting_twice_is_a_message_not_two_grants(self):
        e = Estates()
        e.grant("levy", 0)
        self.assertIn("already", e.grant("levy", 0))
        self.assertEqual(e.by_key["knights"].privileges.count("levy"), 1)


class TestItSurvivesBeingSavedAndLoaded(unittest.TestCase):
    def test_a_grievance_and_a_privilege_both_come_back(self):
        g = grown()
        g.estates.grant("charter", g.day)
        g.estates.note("chapter", "a test grievance", -17.0, g.day)
        loyal = {k: st.loyalty for k, st in g.estates.by_key.items()}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            g.save(path)
            back = type(g).load(path)
        self.assertIn("charter", back.estates.by_key["guilds"].privileges)
        self.assertTrue(any(x.what == "a test grievance"
                            for x in back.estates.by_key["chapter"].ledger))
        for k, was in loyal.items():
            self.assertAlmostEqual(back.estates.by_key[k].loyalty, was, places=4)

    def test_an_old_save_without_estates_still_loads(self):
        e = Estates.from_dict({})
        self.assertEqual(set(e.by_key), set(est.ESTATES))


if __name__ == "__main__":
    unittest.main()


class TestAnEstateYouHaveNotTouchedCostsNothing(unittest.TestCase):
    """Straight interpolation from worst to best made the *starting* loyalty
    worth about 0.96, so every recruitment in the game quietly delivered
    fewer men than the player paid for, from the first day, for no reason
    anybody could see. The curve is hinged at fifty instead."""

    def test_the_middle_is_exactly_neutral(self):
        e = Estates()
        for key, spec in est.ESTATES.items():
            e.by_key[key].loyalty = 50.0
            self.assertAlmostEqual(e.mult(spec.gives), 1.0, places=6, msg=key)

    def test_a_fresh_game_asks_for_no_toll(self):
        e = Estates()
        for spec in est.ESTATES.values():
            self.assertGreaterEqual(e.mult(spec.gives), 1.0, spec.key)

    def test_recruiting_at_rest_gives_you_what_you_paid_for(self):
        g = grown(days=300)
        here = next(iter(g.world.settlements))
        s = g.world.settlements[here]
        for st in g.estates.by_key.values():
            st.loyalty = 50.0
        g.treasury += 100_000
        before = s.units.get("spearman", 0.0)
        said = g.recruit(here, "spearman", 10)
        if "no barracks" in said or "spare hands" in said:
            return self.skipTest(said)
        self.assertEqual(s.units.get("spearman", 0.0) - before, 10, said)

    def test_the_ends_still_mean_something(self):
        e = Estates()
        e.by_key["knights"].loyalty = 0.0
        self.assertLess(e.mult("muster"), 0.7)
        e.by_key["knights"].loyalty = 100.0
        self.assertGreater(e.mult("muster"), 1.2)
