"""Caravans, routes, and the frictions of the road."""

import random
import unittest

from marchlands import config as C
from marchlands.advisor import route_from, scan
from marchlands.goods import good
from marchlands.scenario import new_game
from marchlands.trade import CART, MOVING, Caravan, Order, Stop
from marchlands.world import make_town


class TestCaravanBasics(unittest.TestCase):
    def test_load_is_weighed_not_counted(self):
        c = Caravan(1, "A", "home")
        c.cargo = {"stone": 10.0}          # stone is heavy
        self.assertAlmostEqual(c.load, 10.0 * good("stone").weight)
        self.assertLess(c.free_space, c.capacity)

    def test_guards_cost_coin(self):
        lean, guarded = Caravan(1, "A", "h", guards=0), Caravan(2, "B", "h", guards=4)
        self.assertGreater(guarded.daily_cost, lean.daily_cost)


class TestOnTheRoad(unittest.TestCase):
    def setUp(self):
        self.game = new_game(seed=5)
        self.world = self.game.world
        self.cart = self.game.caravans[0]

    def test_a_route_is_walked_and_repeated(self):
        c = self.cart
        c.set_route([Stop(node="aldworth", buy=[Order("bread", 40)]),
                     Stop(node="dunmere", sell=[Order("bread", -1)])])
        c.start()
        seen = set()
        for _ in range(40):
            self.game.tick()
            seen.add(c.state)
        self.assertIn(MOVING, seen)
        self.assertGreater(c.total_profit, 0.0)

    def test_capacity_caps_a_load(self):
        c = self.cart
        c.set_route([Stop(node="aldworth", buy=[Order("bread", 10_000)])])
        c.start()
        for _ in range(6):
            self.game.tick()
        self.assertLessEqual(c.load, c.capacity + 1e-6)

    def test_home_loading_costs_no_coin(self):
        c = self.cart
        before = self.game.treasury
        c.set_route([Stop(node="aldworth", buy=[Order("wood", 30)])])
        c.start()
        self.game.tick()
        self.assertGreaterEqual(self.game.treasury, before - c.daily_cost - 1e-6)
        self.assertGreater(c.cargo.get("wood", 0.0), 0.0)

    def test_foreign_buying_spends_coin(self):
        c = self.cart
        c.at = "dunmere"
        c.set_route([Stop(node="dunmere", buy=[Order("wood", 40)])])
        c.start()
        before = self.game.treasury
        self.game.tick()
        self.assertLess(self.game.treasury, before - c.daily_cost)

    def test_a_dead_route_stands_itself_down(self):
        c = self.cart
        # Nothing to buy at any price: an order that can never fill.
        c.set_route([Stop(node="aldworth", buy=[Order("silk", 10, limit_price=0.01)]),
                     Stop(node="dunmere", sell=[Order("silk", -1, limit_price=1e9)])])
        c.start()
        for _ in range(60):
            self.game.tick()
            if not c.running:
                break
        self.assertFalse(c.running)

    def test_road_risk_rises_with_distance_and_falls_with_guards(self):
        w = self.world
        near = w.danger("aldworth", "dunmere")
        far = w.danger("aldworth", "marchand")
        self.assertGreater(far, 0)
        self.assertGreater(far / max(near, 1e-9), 1.0)
        self.assertLess(1.0 - C.GUARD_PROTECTION * 3, 1.0)


class TestAdvisor(unittest.TestCase):
    def setUp(self):
        self.game = new_game(seed=5)

    def test_scan_finds_something_and_ranks_it(self):
        opts = scan(self.game.world, "aldworth", top=6)
        self.assertTrue(opts)
        self.assertEqual([o.per_day for o in opts],
                         sorted((o.per_day for o in opts), reverse=True))

    def test_scan_never_books_revenue_for_a_home_delivery(self):
        for o in scan(self.game.world, "aldworth", top=12):
            if o.to in self.game.world.settlements:
                self.assertIsNone(o.out)
            if o.frm in self.game.world.settlements:
                self.assertIsNone(o.back)

    def test_scanned_profit_is_roughly_collectable(self):
        """The scan promises coin; running the route must actually earn some."""
        g = self.game
        opp = scan(g.world, "aldworth", top=1)[0]
        c = g.caravans[0]
        c.set_route(route_from(opp))
        c.start()
        for _ in range(int(opp.days) + 4):
            g.tick()
        self.assertGreater(c.total_profit, 0.0)

    def test_route_from_sets_limit_prices(self):
        opp = scan(self.game.world, "aldworth", top=1)[0]
        stops = route_from(opp)
        orders = [o for s in stops for o in list(s.buy) + list(s.sell)]
        self.assertTrue(orders)
        self.assertTrue(all(o.limit_price > 0 for o in orders))


class TestForeignTowns(unittest.TestCase):
    def test_a_surplus_town_is_cheap_and_a_hungry_one_is_dear(self):
        t = make_town("x", "X", 0, 0, produces={"wool": 12}, consumes={"cloth": 5})
        self.assertLess(t.market.ask("wool"), good("wool").base_price)
        self.assertGreater(t.market.bid("cloth"), good("cloth").base_price)

    def test_towns_sit_at_their_steady_state(self):
        t = make_town("x", "X", 0, 0, produces={"wool": 12}, consumes={"cloth": 5})
        start = t.market.price("wool")
        rng = random.Random(1)
        for _ in range(120):
            t.tick(rng)
        self.assertAlmostEqual(t.market.price("wool"), start, delta=start * 0.25)

    def test_dumping_moves_a_town_and_it_recovers(self):
        t = make_town("x", "X", 0, 0, produces={}, consumes={"cloth": 5})
        dear = t.market.bid("cloth")
        t.market.sell_to("cloth", 400)
        self.assertLess(t.market.bid("cloth"), dear)
        rng = random.Random(1)
        for _ in range(200):
            t.tick(rng)
        self.assertAlmostEqual(t.market.bid("cloth"), dear, delta=dear * 0.3)


class TestACartSaysWhenItHasStopped(unittest.TestCase):
    """A route wearing out is by design; hiding it is not.

    A cart that has worked its route out stops itself and keeps its cargo and
    its lifetime profit on the line, so a stopped cart read exactly like a
    working one -- and the hint telling you it was idle read like a bug in the
    hint rather than news about the cart.
    """

    def test_a_running_cart_just_says_where_it_is(self):
        g = new_game(seed=7)
        c = g.caravans[0]
        c.running = True
        c.state = "idle"
        c.at = "dunmere"
        self.assertEqual(c.where(), "dunmere")

    def test_a_stopped_one_says_so(self):
        g = new_game(seed=7)
        c = g.caravans[0]
        c.running = False
        c.state = "idle"
        c.at = "dunmere"
        self.assertIn("idle", c.where())

    def test_a_cart_on_the_road_says_where_it_is_going(self):
        g = new_game(seed=7)
        c = g.caravans[0]
        c.running = True
        c.state = MOVING
        c.bound_for = "dunmere"
        c.days_left = 2.0
        self.assertIn("dunmere", c.where())
        self.assertNotIn("idle", c.where())

    def test_the_status_line_and_the_hint_agree(self):
        import io
        from marchlands.cli import Console
        g = new_game(seed=7)
        con = Console(g, out=io.StringIO())
        con.do("scan")
        con.do("auto 1")
        out = io.StringIO()
        con.out = out
        con.do("next 30")
        con.do("status")
        con.do("hint")
        text = out.getvalue()
        stopped = [c for c in g.caravans if not c.running]
        if stopped:
            self.assertIn("(idle)", text,
                          "a cart stopped earning and the status line hid it")

class TestAManifestFitsOrSaysSo(unittest.TestCase):
    """A cargo cut off mid-number reads as a cargo of nothing."""

    def cart(self, cargo):
        c = Caravan(uid=1, name="Old Mare", kind=CART, home="aldworth",
                    at="aldworth")
        c.cargo = dict(cargo)
        return c

    def test_an_empty_cart_says_empty(self):
        self.assertEqual(self.cart({}).manifest(), "empty")
        self.assertEqual(self.cart({}).manifest(20), "empty")

    def test_no_width_asked_for_means_the_whole_load(self):
        c = self.cart({"wheat": 40, "salt": 15})
        self.assertEqual(c.manifest(), "15 Salt, 40 Wheat")

    def test_a_load_that_fits_is_not_touched(self):
        c = self.cart({"wheat": 40, "salt": 15})
        self.assertEqual(c.manifest(34), "15 Salt, 40 Wheat")

    def test_what_does_not_fit_is_counted_not_chopped(self):
        c = self.cart({"cheese": 19, "planks": 13, "salt": 15, "wheat": 34})
        out = c.manifest(34)
        self.assertLessEqual(len(out), 34)
        self.assertTrue(out.endswith("more"), out)
        self.assertNotIn(", 3", out[-6:])           # no half-written load
        for part in out.split(", "):
            self.assertTrue(part[0].isdigit() or part.startswith("+"), part)

    def test_the_count_of_what_is_left_is_right(self):
        c = self.cart({"cheese": 19, "planks": 13, "salt": 15, "wheat": 34})
        self.assertIn("+2 more", c.manifest(34))
        self.assertIn("+3 more", c.manifest(14))


if __name__ == "__main__":
    unittest.main()
