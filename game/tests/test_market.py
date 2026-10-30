"""The price mechanism: the part everything else trusts."""

import unittest

from marchlands import config as C
from marchlands.goods import ALL_KEYS, good
from marchlands.market import Market


def flat_market(stock=200.0, target=200.0, **kw) -> Market:
    return Market(name="T", stock={k: stock for k in ALL_KEYS},
                  target={k: target for k in ALL_KEYS}, **kw)


class TestCurve(unittest.TestCase):
    def test_price_falls_as_stock_rises(self):
        m = flat_market()
        prices = [m.curve("wheat", s) for s in (10, 50, 200, 800, 4000)]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_at_target_price_is_base(self):
        m = flat_market()
        self.assertAlmostEqual(m.curve("wheat", 200.0), good("wheat").base_price, places=6)

    def test_clamped_both_ends(self):
        m = flat_market()
        self.assertAlmostEqual(m.curve("wheat", 1e9),
                               good("wheat").base_price * C.PRICE_FLOOR_MULT, places=6)
        self.assertAlmostEqual(m.curve("wheat", 1e-9),
                               good("wheat").base_price * C.PRICE_CEIL_MULT, places=6)

    def test_spread_brackets_the_posted_price(self):
        m = flat_market()
        self.assertLess(m.bid("wheat"), m.price("wheat"))
        self.assertGreater(m.ask("wheat"), m.price("wheat"))


class TestTransactions(unittest.TestCase):
    def test_buying_lifts_the_price(self):
        m = flat_market()
        before = m.price("wheat")
        m.buy_from("wheat", 100)
        self.assertGreater(m.price("wheat"), before)

    def test_selling_drops_the_price(self):
        m = flat_market()
        before = m.price("wheat")
        m.sell_to("wheat", 100)
        self.assertLess(m.price("wheat"), before)

    def test_round_trip_never_profits(self):
        """Buy then immediately sell back: the spread and the impact must bite."""
        for qty in (1, 10, 100, 400):
            m = flat_market()
            bought = m.buy_from("wheat", qty)
            sold = m.sell_to("wheat", bought.quantity)
            self.assertLess(sold.value, bought.value + 1e-9,
                            f"free money at qty={qty}")

    def test_large_order_pays_worse_than_small(self):
        m1, m2 = flat_market(), flat_market()
        small = m1.buy_from("wheat", 10)
        large = m2.buy_from("wheat", 300)
        self.assertGreater(large.avg_price, small.avg_price)

    def test_market_keeps_a_reserve(self):
        m = flat_market(stock=50.0)
        fill = m.buy_from("wheat", 10_000)
        self.assertLess(fill.quantity, 50.0)
        self.assertGreater(m.stock["wheat"], 0.0)

    def test_budget_is_respected(self):
        m = flat_market()
        fill = m.buy_from("wheat", 1000, budget=100.0)
        self.assertLessEqual(fill.net, 100.0 + 1e-6)

    def test_limit_price_stops_the_walk(self):
        m = flat_market()
        cap = m.ask("wheat") * 1.05
        fill = m.buy_from("wheat", 1000, max_price=cap)
        self.assertGreater(fill.quantity, 0)
        self.assertLessEqual(fill.avg_price, cap + 1e-9)

    def test_tariff_is_charged_on_both_sides(self):
        m = flat_market(tariff_rate=0.10)
        buy = m.buy_from("wheat", 30)
        self.assertAlmostEqual(buy.tariff, buy.value * 0.10, places=6)
        sell = m.sell_to("wheat", 30)
        self.assertAlmostEqual(sell.tariff, sell.value * 0.10, places=6)

    def test_untradeable_good_is_refused(self):
        m = flat_market(tradeable=("wheat",))
        self.assertEqual(m.buy_from("silk", 10).quantity, 0.0)


class TestTransfers(unittest.TestCase):
    def test_transfer_out_respects_a_limit(self):
        m = flat_market(stock=40.0, target=200.0)     # scarce: price is high
        moved = m.transfer_out("wheat", 100, limit_price=m.ask("wheat") * 0.5)
        self.assertEqual(moved, 0.0)

    def test_transfer_out_moves_the_price(self):
        m = flat_market()
        before = m.price("wheat")
        moved = m.transfer_out("wheat", 120)
        self.assertGreater(moved, 0)
        self.assertGreater(m.price("wheat"), before)

    def test_inventory_value_ignores_ceiling_scarcity(self):
        m = flat_market(stock=0.0)
        m.stock["silk"] = 2.0
        self.assertLessEqual(m.inventory_value(), 2.0 * 2.0 * good("silk").base_price + 1e-6)


class TestRelaxation(unittest.TestCase):
    def test_posted_price_converges_on_fundamentals(self):
        m = flat_market()
        m.stock["wheat"] = 40.0                       # shock the stock, not the price
        for _ in range(80):
            m.settle_day()
        self.assertAlmostEqual(m.price("wheat"), m.fundamental("wheat"), places=3)

    def test_history_is_bounded(self):
        m = flat_market()
        for _ in range(500):
            m.settle_day()
        self.assertLessEqual(len(m.history["wheat"]), 120)


if __name__ == "__main__":
    unittest.main()
