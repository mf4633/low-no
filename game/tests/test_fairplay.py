"""Consistency, coherence and fair play.

Not tests that the numbers are pretty -- tests that the game does not contain
a free win, a lever with no upside, or a loss you could not see coming. Each
of these was a real finding before it was a test.
"""

import io
import unittest

from marchlands import config as C
from marchlands.cli import Console
from marchlands.scenario import new_game
from marchlands.sim import Bot


#: The three levers that used to be simply available and are now institutions
#: you have to found: see tech.py. A test about what a price ceiling *does* is
#: not a test about whether you are allowed one, so these grant the charter
#: and get on with the measurement -- and tests/test_tech.py is where being
#: allowed one is tested.
CHARTERED = ("coinage", "assize_of_bread", "chancery")


def chartered(game):
    game.progress.researched |= set(CHARTERED)
    return game


def grown(seed: int = 5, days: int = 400):
    g = chartered(new_game(seed=seed))
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g, bot


class TestYouCannotPrintTheWin(unittest.TestCase):
    """Net worth counts the chest and the granary at today's prices, so a
    debasement used to raise it the instant it was struck -- twenty thousand
    of it, against a goal of a hundred and twenty.

    The fix is not to make debasement worthless. Seigniorage is a real tax
    really collected, and a lord who strikes light coin really is better off
    at the expense of everyone holding the old. What had to go was the *free*
    lunch: the goal moving before a single price had noticed.
    """

    def test_a_rich_house_is_poorer_for_striking_coin(self):
        """The shape debasement has in life: worth most to somebody with
        nothing to lose, a straight loss to somebody with holdings, because a
        third more coin against a hundred thousand of goods takes more than
        the twenty thousand it hands over."""
        g, _ = grown(days=900)
        # Rich *on purpose*, rather than hoping nine hundred days of bot play
        # lands above a threshold. The claim here is about what a debasement
        # does to a house with holdings; "has holdings" is the setup, and a
        # setup that depends on the economy's difficulty is one that breaks
        # every time the economy is tuned -- which is exactly how it broke.
        g.treasury += 60_000
        before = g.real_worth()
        self.assertGreater(before, 60_000, "this test wants a rich house")
        g.mint(C.MINT_LIMIT)
        self.assertLess(g.real_worth(), before,
                        "minting made a rich house richer")

    def test_a_poor_one_gains_something_real_by_it(self):
        """And it should. Seigniorage is a real tax really collected."""
        g, _ = grown(days=300)
        before = g.real_worth()
        g.mint(C.MINT_LIMIT)
        self.assertGreater(g.real_worth(), before)

    def test_the_debasement_counts_the_day_it_is_done(self):
        """Prices lag a year or two and that lag is the whole reason anybody
        does it -- but a goal measured against the lagging number could be
        crossed by minting on the last afternoon."""
        g, _ = grown(days=300)
        g.mint(C.MINT_LIMIT)
        self.assertAlmostEqual(g.economy.price_level, 1.0, places=2)
        self.assertGreater(g.net_worth() / g.real_worth(), 1.3)

    def test_most_of_it_is_given_back_once_prices_have_noticed(self):
        g, _ = grown()
        real, nominal = g.real_worth(), g.net_worth()
        g.mint(C.MINT_LIMIT)
        for _ in range(1200):           # let prices catch all the way up
            g.economy.settle()
        gained_nominal = g.net_worth() - nominal
        gained_real = g.real_worth() - real
        self.assertGreater(gained_nominal, C.MINT_LIMIT * 0.9)
        self.assertLess(gained_real, gained_nominal * 0.85,
                        "the coin kept all of its value")

    def test_it_cannot_carry_a_run_that_is_nearly_there_over_the_line(self):
        g, _ = grown(days=900)
        short = g.goals.net_worth - g.real_worth()
        self.assertGreater(short, 0, "this test wants a run still short")
        g.mint(C.MINT_LIMIT)
        g.tick()
        self.assertLess(g.real_worth(), g.goals.net_worth,
                        "a purse of new pennies bought the crown")
        self.assertEqual(g.over, "")

class TestTheTaxDialIsADial(unittest.TestCase):
    """It had seven bands and one that worked: cruel collected four times
    what normal did, and the only thing stopping it being the obvious answer
    was that the win also wants souls."""

    def setUp(self):
        self.g, _ = grown()
        self.s = self.g.home()

    def test_what_a_rate_asks_for_is_not_what_it_collects(self):
        asks = C.TAX_LEVELS[4][0] * self.s.population
        self.assertLess(self.s.tax_take(4), asks * 0.6)

    def test_nothing_leaks_at_the_rates_the_game_was_tuned_around(self):
        for band in (-2, -1, 0, 1, 2):
            asks = C.TAX_LEVELS[band][0] * self.s.population
            self.assertAlmostEqual(self.s.tax_take(band), asks, places=6)

    def test_the_peak_is_somewhere_in_the_middle(self):
        """A Laffer curve or it is not a curve. The cruellest band must not be
        the most profitable one, or the dial has one right answer."""
        takes = {b: self.s.tax_take(b) for b in C.TAX_LEVELS}
        self.assertLess(takes[4], takes[3], "cruel still out-collects heavy")

    def test_largesse_is_paid_in_full_because_you_are_the_one_paying(self):
        self.assertLess(self.s.tax_take(-2), 0)
        self.assertAlmostEqual(self.s.tax_take(-2),
                               C.TAX_LEVELS[-2][0] * self.s.population, places=6)

    def test_a_generous_band_is_worth_something_to_them(self):
        self.assertGreater(C.TAX_LEVELS[-2][1], 10.0)
        self.assertGreater(C.TAX_LEVELS[-1][1], C.TAX_LEVELS[0][1])

    def test_every_band_is_priced_before_you_pull_it(self):
        buf = io.StringIO()
        Console(self.g, out=buf).do("tax")
        out = buf.getvalue()
        for band in C.TAX_LEVELS:
            self.assertIn(C.TAX_LABELS[band], out)
        self.assertIn("never reaches you", out)


class TestTheAssizeIsAChoice(unittest.TestCase):
    """A lever with no upside is a trap, not a decision. A price ceiling is
    usually a bad idea, which is not the same as never being a use."""

    def setUp(self):
        self.g, self.bot = grown(days=450)
        self.s = self.g.home()

    def cap(self, share=0.5):
        self.g.decree("bread", self.s.market.fundamental("bread") * share)

    def test_cheap_bread_is_worth_something_while_there_is_any(self):
        self.s.market.stock["bread"] = 900.0
        self.cap()
        self.g.tick()
        factors = dict(self.s.mood_factors(self.g.progress))
        self.assertIn("the assize", factors)
        self.assertGreater(factors["the assize"], 2.0)

    def test_and_costs_you_once_there_is_not(self):
        self.cap(0.3)
        for _ in range(120):
            self.bot.step()
            self.g.tick()
        factors = dict(self.s.mood_factors(self.g.progress))
        self.assertIn("queuing for it", factors)
        self.assertLess(factors["queuing for it"], 0)

    def test_the_decree_says_how_long_the_goodwill_lasts(self):
        self.s.market.stock["bread"] = 900.0
        said = self.g.decree("bread", self.s.market.fundamental("bread") * 0.5)
        self.assertIn("before the shelves are bare", said)

    def test_a_fuller_granary_buys_a_longer_reprieve(self):
        def days(stock):
            self.g.decree("bread", 0.0)
            self.s.market.stock["bread"] = float(stock)
            said = self.g.decree("bread",
                                 self.s.market.fundamental("bread") * 0.5)
            return said
        thin, fat = days(60), days(1500)
        self.assertNotEqual(thin, fat)

    def test_a_ceiling_over_the_market_is_still_only_a_proclamation(self):
        said = self.g.decree("bread", self.s.market.fundamental("bread") * 3)
        self.assertIn("nothing else", said)
        self.g.tick()
        self.assertEqual(self.s.assize_mood, 0.0)


class TestTheRaceIsLegible(unittest.TestCase):
    """A game whose result you only learn on the last day is one you could not
    have played differently. This one is decided long before then."""

    def test_it_projects_every_clause_of_the_goal(self):
        g, _ = grown(days=400)
        rows = g.pace()
        self.assertTrue(rows)
        names = {r[0] for r in rows}
        self.assertIn("net worth", names)
        self.assertIn("souls", names)
        for _what, now, want, land in rows:
            self.assertGreaterEqual(now, 0)
            self.assertGreater(want, 0)
            self.assertIsInstance(land, float)

    def test_it_says_nothing_before_it_has_anything_to_say(self):
        g = chartered(new_game(seed=5))
        for _what, now, _want, land in g.pace():
            self.assertAlmostEqual(now, land, places=6)   # no rate, no claim

    def test_a_run_that_is_going_nowhere_says_so_while_there_is_time(self):
        """Seed 47 finishes at a fifth of the goal without a single disaster
        in the log. It should be obvious by the first winter, not the last."""
        g = chartered(new_game(seed=47))
        bot = Bot(g)
        for _ in range(400):
            bot.step()
            g.tick()
        worth = next(r for r in g.pace() if r[0] == "net worth")
        self.assertLess(worth[3], worth[2] * 0.5,
                        "a flatlining run is projected to make it")
        buf = io.StringIO()
        Console(g, out=buf).do("status")
        self.assertIn("the race", buf.getvalue())

    def test_the_projection_carries_the_days_that_are_left(self):
        g, _ = grown(days=300)
        rows = dict((r[0], r) for r in g.pace())
        self.assertNotEqual(rows["souls"][1], rows["souls"][3])


class TestNothingHasChangedUnderneath(unittest.TestCase):
    """The middle of the game is tuned; this pass was not allowed to move it.
    Three per cent off the tax roll compounds into half the net worth over
    three years, which is how carefully it has to be left alone."""

    def test_the_ordinary_bands_collect_what_they_always_did(self):
        g, _ = grown(days=200)
        s = g.home()
        for band in (1, 2):
            self.assertAlmostEqual(s.tax_take(band),
                                   C.TAX_LEVELS[band][0] * s.population,
                                   places=6)

    def test_a_game_nobody_interferes_with_is_measured_in_real_coin(self):
        g, _ = grown(days=300)
        self.assertAlmostEqual(g.real_worth(), g.net_worth(), places=3)


if __name__ == "__main__":
    unittest.main()
