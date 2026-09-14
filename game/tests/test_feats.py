"""Things worth having done.

A scenario's goal tells you what the game is *for*. It does not tell you what
the game is *capable of*, and a player who has met it twice has nothing else
to aim at. The good achievements in other games share a property worth
copying: they are not "play for a hundred hours", they are a different way to
play, stated as a condition.

The rule that keeps the list trustworthy is that no feat is instrumented into
the thing it counts -- each is checked against a figure the game was already
keeping. If a feat could be earned by a bug, the bug is in the figure.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from marchlands import feats as fe
from marchlands.feats import Book, Standing
from marchlands.scenarios import start
from marchlands.sim import Bot


class TestTheListItself(unittest.TestCase):
    def test_every_feat_says_what_to_do_rather_than_what_it_is(self):
        for f in fe.FEATS.values():
            self.assertTrue(f.blurb, f.key)
            # A blurb is an instruction, so it starts with a verb.
            self.assertFalse(f.blurb[0].isupper(), f.key)
            self.assertIn(f.hard, (1, 2, 3), f.key)

    def test_no_two_feats_share_a_name(self):
        names = [f.name for f in fe.FEATS.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_they_cover_more_than_one_way_to_play(self):
        # The whole point: a trader, a builder, a soldier and a politician
        # should each have something to aim at.
        blurbs = " ".join(f.blurb for f in fe.FEATS.values())
        for word in ("trade", "wall", "storm", "lords", "institutions"):
            self.assertIn(word, blurbs, word)


class TestEarningThem(unittest.TestCase):
    def test_a_feat_is_announced_once_and_never_again(self):
        b = Book()
        s = Standing(day=1, net_worth=90_000, trade_profit=50_000)
        first = b.check(s)
        self.assertTrue(first)
        self.assertEqual(b.check(Standing(day=2, net_worth=90_000,
                                          trade_profit=50_000)), [])

    def test_it_writes_down_the_day(self):
        b = Book()
        b.check(Standing(day=77, trade_profit=50_000))
        self.assertEqual(b.to_dict()["factor"], 77)

    def test_the_peaceable_kingdom_needs_you_never_to_have_raised_one(self):
        b = Book()
        self.assertNotIn("peaceable", b.to_dict())
        b.check(Standing(day=1, net_worth=70_000, hosts_raised=1))
        self.assertNotIn("peaceable", b.to_dict())
        b.check(Standing(day=2, net_worth=70_000, hosts_raised=0))
        self.assertIn("peaceable", b.to_dict())

    def test_a_feat_that_throws_does_not_break_the_day(self):
        # A day of the game must never fail because a trophy miscounted.
        boom = fe.Feat("boom", "Boom", "do the impossible",
                       lambda s: 1 / 0 > 0)
        fe.FEATS["boom"] = boom
        try:
            self.assertEqual(Book().check(Standing(day=1)), [])
        finally:
            del fe.FEATS["boom"]

    def test_an_unknown_key_in_an_old_save_is_dropped(self):
        b = Book.from_dict({"factor": 10, "nonesuch": 4})
        self.assertIn("factor", b.to_dict())
        self.assertNotIn("nonesuch", b.to_dict())


class TestAgainstARealGame(unittest.TestCase):
    """The figures have to come off the game's own books, so this plays one."""

    @classmethod
    def setUpClass(cls):
        cls.g = start("marchlands", seed=3)
        Bot(cls.g).run(900)

    def test_a_trading_game_earns_the_trading_feats(self):
        earned = {f.key for f in self.g.feats.earned()}
        self.assertIn("factor", earned)
        self.assertIn("peaceable", earned,
                      "the bot never raised a host and got rich; that is the feat")

    def test_the_standing_is_filled_from_the_games_own_figures(self):
        s = self.g._standing()
        self.assertEqual(s.day, self.g.day)
        self.assertAlmostEqual(s.net_worth, self.g.net_worth(), places=3)
        self.assertEqual(s.techs, len(self.g.progress.researched))
        self.assertEqual(s.age, self.g.progress.age)

    def test_a_host_raised_is_a_host_counted(self):
        g = start("marchlands", seed=5)
        Bot(g).run(300)
        here = next(iter(g.world.settlements))
        g.world.settlements[here].units.update({"spearman": 30})
        was = g._hosts_raised
        g.raise_host(here, {"spearman": 10})
        self.assertEqual(g._hosts_raised, was + 1)

    def test_the_book_survives_a_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            self.g.save(path)
            back = type(self.g).load(path)
        self.assertEqual(back.feats.to_dict(), self.g.feats.to_dict())
        self.assertEqual(back._trade_profit, self.g._trade_profit)
        self.assertEqual(back._hosts_raised, self.g._hosts_raised)


if __name__ == "__main__":
    unittest.main()
