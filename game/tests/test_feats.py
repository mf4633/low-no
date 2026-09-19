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
import statistics
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

    #: Seeds enough to say something about the game rather than about one
    #: run of it, and a floor with room under it.
    #:
    #: Net worth at nine hundred days is the noisiest figure this game
    #: produces: measured over twenty-four seeds the median is near fifty
    #: thousand and the spread runs better than five to one, because wealth
    #: tracks trade profit at +0.95 and trade compounds. That spread is an
    #: economy working, not a fault, and no amount of tuning removes it --
    #: so a test that reads one seed is reading a die.
    #:
    #: This suite did read one seed, and went red the first time the
    #: sickness moved the median by a sixth: seed 3 had been printing a
    #: hundred and twenty thousand and printed thirty-six, having also moved
    #: twenty thousand the other way for reasons nobody had touched. What
    #: follows asserts five things instead, each of them robust to which
    #: seeds you drew and each of them able to fail on its own.
    #: 9 and 17 are in here on purpose: they are the two runs of the first
    #: sixteen that used to end in bankruptcy, so the test below that says a
    #: trading game reaches the end of itself is a test that can fail. A
    #: regression suite that does not contain the regression is scenery.
    SEEDS = (3, 5, 9, 11, 17)

    #: Measured 43,600 across these five. Set well under it: this is here to
    #: catch a collapse, not to pin a number the game is allowed to move.
    FLOOR = 25_000

    @classmethod
    def setUpClass(cls):
        cls.runs = []
        for seed in cls.SEEDS:
            g = start("marchlands", seed=seed)
            Bot(g).run(900)
            cls.runs.append(g)
        cls.g = cls.runs[0]

    def earned(self, g):
        return {f.key for f in g.feats.earned()}

    def test_trade_alone_pays(self):
        """`factor` is cumulative trade profit, which is the steady figure.

        Every run must clear it. A trading game that cannot make forty
        thousand coin on the road in nine hundred days is not a trading
        game, and this is the assertion that says so.
        """
        for g in self.runs:
            self.assertIn("factor", self.earned(g),
                          f"seed {g.seed}: {sum(c.total_profit for c in g.caravans):,.0f}c "
                          f"of trade profit in nine hundred days")

    def test_a_trading_game_does_not_go_bankrupt(self):
        """The one that would have caught what nothing else did.

        Two runs in sixteen used to end "Ruined. Your debts outran your
        carts" -- one of them on day 386, with a sickness in the capital and
        the masons still in the yard. The autoplayer had a rule against
        spending through a siege and none against spending through anything
        else. Nothing in this suite noticed, because nothing asserted that a
        game gets to the end of itself.
        """
        for g in self.runs:
            self.assertNotIn(
                "Ruined", g.over or "",
                f"seed {g.seed} went bankrupt on day {g.day} "
                f"holding {g.treasury:,.0f}c")

    def test_a_played_game_ends_up_worth_something(self):
        median = statistics.median(g.net_worth() for g in self.runs)
        self.assertGreater(
            median, self.FLOOR,
            "the median game is worth "
            + f"{median:,.0f}c at the bell, under the {self.FLOOR:,}c floor. "
            + "Each: "
            + ", ".join(f"{g.seed}={g.net_worth():,.0f}" for g in self.runs))

    def test_the_peaceable_kingdom_is_still_a_way_to_play(self):
        """Rich, with no host ever raised. The feat's own claim.

        Stated as "some game of this kind", because that is all a threshold
        on a five-to-one spread can support -- measured, two of these five
        clear sixty thousand. If it ever becomes none, trade has stopped
        being a way to win and that is worth a red test.
        """
        for g in self.runs:
            self.assertEqual(g._hosts_raised, 0,
                             f"seed {g.seed} raised a host, so it cannot "
                             f"speak to a feat about never raising one")
        rich = [g for g in self.runs if "peaceable" in self.earned(g)]
        self.assertTrue(
            rich,
            "not one of these games got rich without raising a host. Worth "
            "at the bell: "
            + ", ".join(f"{g.net_worth():,.0f}" for g in self.runs))

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
