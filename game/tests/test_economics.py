"""The economy, read the way an economist would read it.

These are not tests that the numbers are pretty. They are tests that the
textbook results actually come out of the simulation rather than being printed
over the top of it: a ceiling below the market empties the shelf, a debasement
raises prices and nothing else, and a toll destroys more than it collects.
"""

import io
import unittest

from marchlands import config as C
from marchlands.cli import Console
from marchlands.economics import (BASKET, Economy, MONEY_BASE, base_basket,
                                  basket_cost, compare, daily_output,
                                  marginal_hands, opportunity_cost, surplus,
                                  town_output)
from marchlands.engine import GameState
from marchlands.goods import good
from marchlands.scenario import new_game
from marchlands.sim import Bot


#: The three levers that used to be simply available and are now institutions
#: you have to found: see tech.py. A test about what a price ceiling *does* is
#: not a test about whether you are allowed one, so these grant the charter
#: and get on with the measurement -- and `TestTheInstitutionsAreGates` in
#: tests/test_tech.py is where being allowed one is tested.
CHARTERED = ("coinage", "assize_of_bread", "chancery")


def chartered(game):
    game.progress.researched |= set(CHARTERED)
    return game


def grown(seed: int = 5, days: int = 500):
    g, _ = played(seed, days)
    return g


def played(seed: int = 5, days: int = 500):
    """The game, and the hands still on it.

    Several of these measurements are about what a lever does to a town that
    is still being played -- which is not the same town as one left to tick
    with nobody buying or selling. A frozen settlement's sheds pile their
    output on a shelf nobody draws from, and a shortage cannot be measured
    against a market that has stopped.
    """
    g = chartered(new_game(seed=seed))
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g, bot


class TestTheIndex(unittest.TestCase):
    def test_the_basket_is_a_basket(self):
        self.assertAlmostEqual(sum(share for _, share in BASKET), 1.0, places=6)
        for key, _ in BASKET:
            self.assertIsNotNone(good(key))

    def test_a_hundred_means_everything_at_what_it_is_worth(self):
        """The base is not day one. A new holding is sitting on its founding
        stores, so day-one prices are the floor, and an index based there
        reads the granary emptying as four hundred per cent inflation."""
        g = chartered(new_game(seed=5))
        g.tick()
        self.assertGreater(base_basket(), 0)
        self.assertAlmostEqual(g.economy.base_cpi, base_basket(), places=6)

    def test_the_index_reads_what_is_charged(self):
        g = chartered(new_game(seed=5))
        m = g.home().market
        self.assertAlmostEqual(
            basket_cost(m), sum(share * m.price(k) for k, share in BASKET),
            places=6)

    def test_inflation_is_a_yearly_rate_off_the_series(self):
        econ = Economy()
        econ.base_cpi = 1.0
        for day in range(1, int(C.DAYS_PER_YEAR) + 1):
            econ.series.append({"day": day, "cpi": 100.0, "workforce": 1.0,
                                "employed": 1.0})
        self.assertAlmostEqual(econ.inflation_rate(110.0), 10.0, places=1)

    def test_an_index_with_no_history_is_not_a_rate(self):
        self.assertEqual(Economy().inflation_rate(200.0), 0.0)


class TestTheMint(unittest.TestCase):
    """MV = PY. More pennies is not more bread, and everybody finds out."""

    def test_striking_coin_puts_it_in_the_chest_today(self):
        g = grown(days=200)
        purse = g.treasury
        g.mint(5_000)
        self.assertAlmostEqual(g.treasury, purse + 5_000, places=3)
        self.assertEqual(g.economy.minted, 5_000)

    def test_and_takes_it_back_in_prices(self):
        g = grown(days=300)
        before = g.economy.price_level
        g.mint(C.MINT_LIMIT)
        for _ in range(400):
            g.economy.settle()
        self.assertGreater(g.economy.price_level, before * 1.1)

    def test_the_price_level_chases_the_money_supply_and_stops(self):
        econ = Economy()
        econ.strike(MONEY_BASE, 1.0)          # twice the coin
        for _ in range(4000):
            econ.settle()
        self.assertAlmostEqual(econ.price_level, 2.0, places=2)

    def test_it_does_not_happen_the_day_you_do_it(self):
        """The whole reason anybody ever debased anything is the lag."""
        g = grown(days=200)
        g.mint(C.MINT_LIMIT)
        self.assertLess(g.economy.price_level, 1.02)

    def test_the_town_knows_at_once_even_if_the_prices_do_not(self):
        g = grown(days=200)
        mood = g.home().popularity
        g.mint(C.MINT_LIMIT)
        self.assertLess(g.home().popularity, mood)

    def test_the_mint_has_a_limit(self):
        g = grown(days=100)
        said = g.mint(C.MINT_LIMIT * 4)
        self.assertIn("cannot", said)
        self.assertEqual(g.economy.minted, 0)

    def test_prices_in_every_market_of_yours_carry_the_level(self):
        g = grown(days=200)
        m = g.home().market
        was = m.curve("bread", 100.0)
        g.mint(C.MINT_LIMIT)
        for _ in range(600):
            g.economy.settle()
        g.tick()
        self.assertGreater(m.curve("bread", 100.0), was * 1.1)


class TestTheAssize(unittest.TestCase):
    """A price ceiling: the most famous experiment in the book."""

    def setUp(self):
        self.g, self.bot = played(days=420)
        self.m = self.g.home().market

    def play(self, days: int) -> None:
        """Keep playing. A price ceiling empties a shelf that people are
        still taking off; against a town that has stopped trading it is only
        a number, and a test that froze the town was measuring the number."""
        for _ in range(days):
            self.bot.step()
            self.g.tick()

    def test_a_ceiling_above_the_market_does_nothing_whatever(self):
        worth = self.m.fundamental("bread")
        said = self.g.decree("bread", worth * 2)
        self.assertIn("nothing else", said)
        self.assertEqual(self.m.binding("bread"), 0.0)

    def test_a_ceiling_below_it_binds(self):
        worth = self.m.fundamental("bread")
        self.g.decree("bread", worth * 0.4)
        self.assertGreater(self.m.binding("bread"), 0.4)
        self.assertLessEqual(self.m.price("bread"), worth * 0.4 + 1e-9)

    def test_and_empties_the_shelf(self):
        stock = self.m.stock["bread"]
        self.g.decree("bread", self.m.fundamental("bread") * 0.3)
        self.play(150)
        self.assertLess(self.m.stock["bread"], stock * 0.5)

    def test_which_is_the_shelf_it_would_otherwise_have_had(self):
        """The claim is a comparison, not a level: this town at this hour with
        the ceiling has less bread than the same town at the same hour without
        it. Anything short of that is measuring the weather."""
        from marchlands.engine import GameState
        save = self.g.to_dict()

        def run(decree):
            h = GameState.from_dict(save)
            if decree:
                h.decree("bread", h.home().market.fundamental("bread") * 0.3)
            bot = Bot(h)
            for _ in range(150):
                bot.step()
                h.tick()
            return h

        free, capped = run(False), run(True)
        self.assertLess(capped.home().market.stock["bread"],
                        free.home().market.stock["bread"] * 0.5)
        # And it is paid for out of the house, not out of nowhere. A lever
        # that only ever gave would be the mint's free lunch a second time.
        self.assertLess(capped.net_worth(), free.net_worth())

    def test_the_town_is_grateful_and_then_it_is_not(self):
        """A control is a transfer out of the granary, so its whole life is
        however much is in the granary. Cheap bread first, a queue after.

        The granary is filled here rather than inherited. That is the whole
        premise of the first half -- gratitude is `relief` scaled by how
        much bread there is to be cheap -- and leaving it to whatever the
        autoplayer had in the barn on day 420 made this test a reading of
        the bot's baking rather than of the assize. It duly went red on an
        unrelated change to how the bot reserves its coin, with the town
        already queuing on the morning the proclamation was read.
        """
        home = self.g.home()
        want = max(1.0, home.market.target.get("bread", 0.0) * 0.6)
        home.market.stock["bread"] = max(home.market.stock.get("bread", 0.0),
                                         want * 1.5)
        self.g.decree("bread", self.m.fundamental("bread") * 0.3)
        # And the carts kept off it for the morning of the proclamation. Bread
        # at a third of its worth is bread every exporter on the march wants,
        # and the bot's standing routes carried the whole planted granary off
        # before anybody could be grateful for it -- true, and the second
        # half of this test, but not the first.
        held = [(st, list(st.buy)) for c in self.g.caravans for st in c.route]
        for st, orders in held:
            st.buy = [o for o in orders if o.good != "bread"]
        self.g.tick()
        for st, orders in held:
            st.buy = orders
        first = dict(self.g.home().mood_factors(self.g.progress))
        self.assertIn("the assize", first,
                      f"a full granary and a binding cap and no gratitude: "
                      f"{first}")
        self.assertGreater(first["the assize"], 0)
        self.play(200)
        later = dict(self.g.home().mood_factors(self.g.progress))
        self.assertIn("queuing for it", later)
        self.assertLess(later["queuing for it"], 0)

    def test_the_index_does_not_show_the_shortage(self):
        """Which is the point. Measured prices fall while the shelf empties --
        exactly what a price control does to a price index.

        A comparison, not a level. Reading the index before and after forty
        days asks whether the *whole economy* got cheaper in that time, which
        it may not have for a dozen reasons that have nothing to do with
        bread; the claim is that the index is lower with the ceiling than it
        would have been without one, and that is two runs of the same save.
        """
        save = self.g.to_dict()

        def run(decree):
            h = GameState.from_dict(save)
            if decree:
                h.decree("bread", h.home().market.fundamental("bread") * 0.25)
            for _ in range(40):
                h.tick()
            return h

        free, capped = run(False), run(True)
        self.assertLess(capped.accounts.cpi, free.accounts.cpi)
        self.assertGreater(capped.economy.shortage.get("bread", 0.0), 0.3)
        # The emptying shelf is the other half of this and it is measured in
        # `test_and_empties_the_shelf`, where somebody is still buying. Here
        # the town eats through its own granary either way, so a shelf
        # comparison would compare nothing to nothing.

    def test_lifting_it_lets_the_price_find_its_own_level(self):
        self.g.decree("bread", 1.0)
        self.g.tick()
        self.g.decree("bread", 0.0)
        self.assertEqual(self.m.binding("bread"), 0.0)
        self.assertNotIn("bread", self.g.economy.assize)


class TestSurplusAndTheWedge(unittest.TestCase):
    def setUp(self):
        self.g = grown(days=400)
        self.m = self.g.home().market
        # These measure the wedge a toll drives, and three of them do it in
        # wheat. They were reading whatever four hundred simulated days had
        # left in the bin, which is a number that belongs to the bot's
        # trading rather than to the arithmetic under test -- and when a
        # change to what the bot does with its carts emptied the wheat, the
        # tests went quiet rather than wrong: a surplus of nothing is zero,
        # and zero is not greater than zero.
        self.m.stock["wheat"] = max(self.m.stock.get("wheat", 0.0), 120.0)

    def test_buyers_gain_when_a_thing_is_scarce_enough_to_want(self):
        r = surplus(self.m, "bread")
        self.assertGreaterEqual(r.consumer, 0.0)
        self.assertAlmostEqual(r.total, r.consumer + r.producer + r.revenue,
                               places=6)

    def test_an_empty_shelf_is_worth_nothing_to_anybody(self):
        self.m.stock["bread"] = 0.0
        self.assertEqual(surplus(self.m, "bread").quantity, 0.0)

    def test_a_toll_collects_less_than_it_destroys_the_chance_of(self):
        self.m.tariff_rate = 0.0
        free = surplus(self.m, "wheat")
        self.m.tariff_rate = 0.25
        tolled = surplus(self.m, "wheat")
        self.assertEqual(free.deadweight, 0.0)
        self.assertGreater(tolled.revenue, 0.0)
        self.assertGreater(tolled.deadweight, 0.0)

    def test_a_bigger_toll_destroys_more_than_proportionately(self):
        """The triangle goes with the square of the wedge, which is why the
        second half of a tax hurts more than the first."""
        self.m.tariff_rate = 0.10
        small = surplus(self.m, "wheat").deadweight
        self.m.tariff_rate = 0.20
        big = surplus(self.m, "wheat").deadweight
        self.assertGreater(big, small * 3.0)

    def test_an_elastic_good_loses_more_trade_to_the_same_toll(self):
        elastic = max(BASKET, key=lambda kv: good(kv[0]).elasticity)[0]
        rigid = min(BASKET, key=lambda kv: good(kv[0]).elasticity)[0]
        self.m.tariff_rate = 0.2
        a, b = surplus(self.m, elastic), surplus(self.m, rigid)
        if a.quantity and b.quantity:
            self.assertGreaterEqual(a.deadweight / max(a.revenue, 1e-9),
                                    b.deadweight / max(b.revenue, 1e-9))


class TestComparativeAdvantage(unittest.TestCase):
    """Not who is better at it. Who gives up less to do it."""

    def test_opportunity_cost_is_a_ratio_of_what_you_can_make(self):
        out = {"bread": 10.0, "ale": 5.0}
        self.assertAlmostEqual(opportunity_cost(out, "bread", "ale"), 0.5)
        self.assertAlmostEqual(opportunity_cost(out, "ale", "bread"), 2.0)

    def test_a_place_that_cannot_make_it_gives_up_everything(self):
        self.assertEqual(opportunity_cost({"ale": 1.0}, "bread", "ale"),
                         float("inf"))

    def test_the_worse_place_at_everything_still_has_an_advantage(self):
        """Mankiw's whole point, in four numbers: they are worse at both and
        should still be making one of them."""
        mine = {"bread": 20.0, "cloth": 10.0}      # better at both
        theirs = {"bread": 4.0, "cloth": 4.0}
        bread = compare(mine, theirs, "bread", "them", against="cloth")[0]
        cloth = compare(mine, theirs, "cloth", "them", against="bread")[0]
        self.assertFalse(bread.theirs)             # you give up less for bread
        self.assertTrue(cloth.theirs)              # they give up less for cloth

    def test_two_places_with_nothing_in_common_are_still_comparable(self):
        mine = {"wheat": 20.0, "wood": 10.0}
        theirs = {"clay": 10.0, "wood": 14.0}
        rows = compare(mine, theirs, "wood", "them")
        self.assertTrue(rows)
        self.assertTrue(rows[0].theirs)            # wood costs them less

    def test_a_good_nobody_can_make_has_no_reading(self):
        self.assertEqual(compare({"wheat": 1.0}, {"clay": 1.0}, "silk", "x"), [])

    def test_it_reads_off_the_game_s_own_towns(self):
        g = chartered(new_game(seed=5))
        mine = daily_output(g.home())
        town = g.world.towns["dunmere"]
        rows = compare(mine, town_output(town), "wood", town.name)
        self.assertTrue(rows)
        self.assertIn("gives up less", rows[0].reads())


class TestTheLabourMarket(unittest.TestCase):
    """Hire while the next hand is worth more than the wage."""

    def setUp(self):
        self.g = grown(days=400)
        self.rows = marginal_hands(self.g.home())

    def test_every_shed_that_makes_something_is_in_the_table(self):
        made = {b.uid for b in self.g.home().buildings
                if b.complete and b.spec.jobs and b.spec.outputs}
        self.assertEqual({r.uid for r in self.rows}, made)

    def test_it_is_ranked_by_what_the_next_hand_is_worth(self):
        nets = [r.net for r in self.rows]
        self.assertEqual(nets, sorted(nets, reverse=True))

    def test_the_hiring_rule_is_the_wage(self):
        for r in self.rows:
            self.assertEqual(r.hire, r.net > C.WAGE)

    def test_a_shed_that_eats_more_than_it_makes_says_shut_it(self):
        r = min(self.rows, key=lambda r: r.net)
        if r.net < C.WAGE and r.staffed:
            self.assertTrue(r.shut)

    def test_the_value_falls_when_the_price_does(self):
        """A hand is worth what its output fetches, so a glut is a pay cut."""
        home = self.g.home()
        row = next(r for r in self.rows
                   if r.value > 0
                   and len(next(b for b in home.buildings
                                if b.uid == r.uid).spec.outputs) == 1)
        key = next(iter(next(b for b in home.buildings
                             if b.uid == row.uid).spec.outputs))
        home.market.stock[key] = home.market.stock.get(key, 0.0) * 50.0 + 5_000.0
        for _ in range(40):                       # the posted price is a lag
            home.market.settle_day()
        again = next(r for r in marginal_hands(home) if r.uid == row.uid)
        self.assertLess(again.value, row.value)


class TestItSurvivesBeingPutDown(unittest.TestCase):
    def test_the_accounts_come_back(self):
        g = grown(days=200)
        g.mint(3_000)
        g.decree("bread", 2.0)
        g.tick()
        back = GameState.from_dict(g.to_dict())
        self.assertAlmostEqual(back.economy.price_level, g.economy.price_level)
        self.assertEqual(back.economy.minted, g.economy.minted)
        self.assertEqual(back.economy.assize, g.economy.assize)
        self.assertEqual(len(back.economy.series), len(g.economy.series))

    def test_a_loaded_game_still_holds_the_price_down(self):
        g = grown(days=200)
        g.decree("bread", 1.5)
        back = GameState.from_dict(g.to_dict())
        self.assertLessEqual(back.home().market.price("bread"), 1.5 + 1e-9)

    def test_a_save_from_before_the_accounts_existed_loads(self):
        g = grown(days=120)
        raw = g.to_dict()
        del raw["economy"]
        back = GameState.from_dict(raw)
        back.tick()
        self.assertGreater(back.accounts.cpi, 0)


class TestTheConsoleSaysIt(unittest.TestCase):
    def setUp(self):
        self.g = grown(days=400)
        self.buf = io.StringIO()
        self.con = Console(self.g, out=self.buf)

    def said(self, line):
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do(line)
        return self.buf.getvalue()

    def test_the_accounts_screen_names_its_numbers(self):
        out = self.said("economy")
        for word in ("prices", "inflation", "purse", "idle hands", "velocity"):
            self.assertIn(word, out)

    def test_the_margin_screen_ranks_the_sheds(self):
        out = self.said("margin")
        self.assertIn("THE NEXT HAND", out)
        self.assertIn("a hand costs", out)

    def test_surplus_says_who_gains_what(self):
        out = self.said("surplus bread")
        self.assertIn("to the buyers", out)
        self.assertIn("to the sellers", out)

    def test_a_toll_shows_up_as_a_thing_destroyed(self):
        self.g.home().market.stock["wheat"] = 120.0
        self.g.home().market.tariff_rate = 0.2
        out = self.said("surplus wheat")
        self.assertIn("to nobody", out)

    def test_advantage_names_a_town_and_a_verdict(self):
        out = self.said("advantage wood")
        self.assertIn("WHO SHOULD MAKE WOOD", out)
        self.assertIn("gives up", out.lower() + "gives up")

    def test_the_assize_screen_says_when_it_is_not_biting(self):
        out = self.said("assize")
        self.assertIn("nothing is held", out)

    def test_an_assize_that_bites_is_reported_in_the_accounts(self):
        self.said(f"assize bread {self.g.home().market.fundamental('bread') * 0.3:.2f}")
        for _ in range(20):
            self.g.tick()
        out = self.said("economy")
        self.assertIn("short", out)

    def test_the_mint_screen_explains_the_bargain(self):
        out = self.said("mint")
        self.assertIn("prices find out", out)

    def test_a_shed_losing_money_reaches_the_hints(self):
        """A hint that can only appear on a quiet day is a system nobody is
        ever told about."""
        rows = marginal_hands(self.g.home())
        if any(r.shut for r in rows):
            self.assertIn("margin", " ".join(self.con.hints()))


class TestTheInflationReadoutIsNotInvented(unittest.TestCase):
    """Found by playing it. Day seven of a fresh campaign reported prices up
    two hundred and seventy-six billion per cent a year -- arithmetic and
    nonsense together, because annualising a three-day wobble raises it to
    the hundred-and-twentieth power."""

    def figures(self, days):
        from marchlands.scenarios import start
        g = start("marchlands", seed=11)
        g.advance(days)
        return g.accounts

    def test_a_short_run_is_never_extrapolated_to_a_year(self):
        for days in (3, 7, 20, 60, 120, 200):
            a = self.figures(days)
            self.assertLess(abs(a.inflation), 2000.0,
                            f"day {days} reported {a.inflation:,.0f}%")

    def test_a_short_run_says_it_is_a_short_run(self):
        self.assertFalse(self.figures(20).yearly)

    def test_and_a_long_one_says_it_is_a_year(self):
        a = self.figures(int(C.DAYS_PER_YEAR) + 40)
        self.assertTrue(a.yearly)

    def test_the_words_follow_the_figure(self):
        # "a year" printed over a figure that is not a yearly rate was the
        # readable half of the bug.
        import re
        from io import StringIO
        from marchlands.cli import Console
        from marchlands.scenarios import start
        for days, want in ((20, "since you began"), (400, "a year")):
            c = Console(start("marchlands", seed=11), out=StringIO())
            c.do(f"next {days}")
            said = re.sub(r"\x1b\[[0-9;]*m", "", c.out.getvalue())
            line = [l for l in said.splitlines() if "prices" in l]
            if line:
                self.assertIn(want, line[0], f"day {days}: {line[0].strip()}")

    def test_it_is_still_a_real_measurement(self):
        # Not silenced: a run that is genuinely getting dearer still says so.
        early = self.figures(20).inflation
        later = self.figures(200).inflation
        self.assertGreater(later, early)


if __name__ == "__main__":
    unittest.main()
