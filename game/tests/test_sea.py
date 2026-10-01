"""Ports, cogs and the weather."""

import unittest

from marchlands import config as C
from marchlands.advisor import scan
from marchlands.scenario import new_game
from marchlands.trade import CART, SHIP


class TestPorts(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=5)

    def test_the_map_has_a_coast(self):
        ports = self.g.world.ports()
        self.assertGreaterEqual(len(ports), 3)
        self.assertNotIn("aldworth", ports)          # your seat is inland

    def test_sailing_needs_two_harbours(self):
        w = self.g.world
        self.assertTrue(w.can_sail("havnhold", "marchand"))
        self.assertFalse(w.can_sail("havnhold", "caldmoor"))

    def test_the_sea_is_shorter_than_the_road(self):
        w = self.g.world
        self.assertLess(w.sea_distance("havnhold", "marchand"),
                        w.distance("havnhold", "marchand"))

    def test_winter_is_the_dangerous_season(self):
        w = self.g.world
        self.assertGreater(w.storm_risk("havnhold", "marchand", "winter"),
                           w.storm_risk("havnhold", "marchand", "summer"))

    def test_a_quay_makes_your_own_town_a_port(self):
        g = self.g
        g.treasury = 60_000
        g.progress.age = 2
        g.found("sealow")
        s = g.world.settlements["sealow"]
        self.assertFalse(g.world.is_port("sealow"))
        for k, q in (("wood", 200), ("planks", 120), ("stone", 200)):
            s.market.add(k, q)
        self.assertIn("begun", g.build("sealow", "harbour"))
        s.buildings[-1].days_left = 0
        self.assertTrue(g.world.is_port("sealow"))


class TestCogs(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=5)
        self.g.treasury = 60_000
        self.g.progress.age = 2
        self.g.found("sealow")
        s = self.g.world.settlements["sealow"]
        for k, q in (("wood", 300), ("planks", 200), ("stone", 300)):
            s.market.add(k, q)
        self.g.build("sealow", "harbour")
        s.buildings[-1].days_left = 0

    def test_a_cog_needs_a_harbour_to_be_built_in(self):
        g = self.g
        c, why = g.new_caravan("aldworth", kind=SHIP)
        self.assertIsNone(c)
        self.assertIn("harbour", why)
        c, why = g.new_caravan("sealow", kind=SHIP)
        self.assertIsNotNone(c, why)

    def test_a_hull_holds_more_and_moves_faster(self):
        g = self.g
        ship, _ = g.new_caravan("sealow", kind=SHIP)
        cart, _ = g.new_caravan("aldworth", kind=CART)
        g.tick()
        self.assertGreater(ship.capacity, cart.capacity * 2)
        self.assertGreater(ship.speed, cart.speed)
        self.assertGreater(ship.daily_cost, cart.daily_cost)

    def test_a_cog_will_not_sail_inland(self):
        from marchlands.trade import Order, Stop
        g = self.g
        ship, _ = g.new_caravan("sealow", kind=SHIP)
        ship.set_route([Stop(node="sealow", buy=[Order("salt", 10)]),
                        Stop(node="caldmoor", sell=[Order("salt", -1)])])
        ship.start()
        msgs = []
        for _ in range(6):
            msgs += g.tick()
        self.assertFalse(ship.running)
        self.assertTrue(any("no harbour" in m for m in msgs))

    def test_a_cog_trades_between_ports(self):
        g = self.g
        ship, _ = g.new_caravan("sealow", kind=SHIP)
        opts = scan(g.world, "sealow", capacity=ship.capacity, speed=ship.speed,
                    sails=True, top=1)
        self.assertTrue(opts, "no sea trade on a map with four harbours")
        from marchlands.advisor import route_from
        ship.set_route(route_from(opts[0]))
        ship.start()
        for _ in range(int(opts[0].days) + 10):
            g.tick()
        self.assertGreater(ship.total_profit, 0.0)

    def test_the_scan_only_offers_ports_to_a_hull(self):
        g = self.g
        for o in scan(g.world, "sealow", sails=True, top=12):
            self.assertTrue(g.world.is_port(o.frm), o.frm)
            self.assertTrue(g.world.is_port(o.to), o.to)


class TestManifests(unittest.TestCase):
    def test_a_big_hold_is_spread_over_several_goods(self):
        g = new_game(seed=5)
        opts = scan(g.world, "havnhold", capacity=C.SHIP_CAPACITY,
                    speed=C.SHIP_SPEED, sails=True, top=3)
        self.assertTrue(opts)
        widest = max(len(leg.cargo) for o in opts for leg in (o.out, o.back) if leg)
        self.assertGreater(widest, 1, "a 420-unit hull carrying one commodity")

    def test_limit_prices_follow_each_goods_own_cost(self):
        g = new_game(seed=5)
        from marchlands.advisor import route_from
        opp = scan(g.world, "aldworth", top=1)[0]
        leg = opp.out or opp.back
        stops = route_from(opp)
        orders = {o.good: o for st in stops for o in st.buy}
        for key, qty in leg.cargo.items():
            if key in orders:
                self.assertAlmostEqual(orders[key].limit_price,
                                       leg.unit_cost(key) * 1.06, delta=0.3)


if __name__ == "__main__":
    unittest.main()
