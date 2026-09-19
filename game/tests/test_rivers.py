"""The water, the fords, and whether a bridge is worth its masonry.

The shape of these follows tests/test_plague.py: what the thing is, how it
gets about, what it costs, what you are allowed to know, that it survives a
save, and -- the one that matters -- whether it is worth having at all.
"""

import json
import unittest

from marchlands import rivers as waters
from marchlands.engine import GameState
from marchlands.military import FAIR, FROST, RAIN, sky_on
from marchlands.scenarios import start
from marchlands.trade import Order, Stop


def _running_route(g, home, away):
    c = g.caravans[0]
    c.route = [Stop(home, sell=[Order("wool", -1)]),
               Stop(away, buy=[Order("wool", -1)])]
    c.running = True
    return c


class TestTheHydrograph(unittest.TestCase):
    """The stage is weather with a memory, and nothing else."""

    def test_it_is_a_pure_function_of_the_day(self):
        # Two askers, one answer. The panel that warns you and the cart that
        # sets off must agree, which is why nothing here is rolled.
        for day in (0, 3, 57, 400):
            self.assertEqual(waters.stage(day, 7), waters.stage(day, 7))

    def test_different_seeds_get_different_weather(self):
        a = [waters.stage(d, 3) for d in range(60)]
        b = [waters.stage(d, 11) for d in range(60)]
        self.assertNotEqual(a, b)

    def test_rain_today_is_still_in_the_river_next_week(self):
        """The recession limb. This is the whole point of the model."""
        wet = [d for d in range(400)
               if sky_on(waters._season_on(d), d, 7) == RAIN]
        self.assertTrue(wet, "no rain in four hundred days is a broken sky")
        # Find a wet day with a dry week after it, and check the river is
        # still above where it started rather than snapping back.
        for d in wet:
            after = [sky_on(waters._season_on(k), k, 7)
                     for k in range(d + 1, d + 6)]
            if all(s == FAIR for s in after):
                self.assertGreater(waters.stage(d + 4, 7), 0.0)
                self.assertLess(waters.stage(d + 4, 7), waters.stage(d + 1, 7),
                                "a river that does not fall is a lake")
                break
        else:
            self.skipTest("no wet day followed by five dry ones in this seed")

    def test_summer_is_lower_than_spring(self):
        spring = [waters.stage(d, 7) for d in range(400)
                  if waters._season_on(d) == "spring"]
        summer = [waters.stage(d, 7) for d in range(400)
                  if waters._season_on(d) == "summer"]
        self.assertGreater(sum(spring) / len(spring), sum(summer) / len(summer))

    def test_a_season_forecast_is_not_a_forecast(self):
        # You are told what the season tends to do, never what Thursday does.
        for season in ("spring", "summer", "autumn", "winter"):
            self.assertIsInstance(waters.forecast(season), str)
        self.assertNotEqual(waters.forecast("spring"), waters.forecast("summer"))


class TestWhatARiverDoesToARoad(unittest.TestCase):

    def river(self, limit=1.50):
        return waters.River("r", "Test", 0.0, -10.0, 0.0, 10.0, limit)

    def test_low_water_costs_nothing(self):
        r = self.river()
        self.assertEqual(waters.state_of(r, 0.4), waters.LOW)
        self.assertEqual(waters.DELAY[waters.LOW], 0.0)

    def test_the_bands_run_in_the_right_order(self):
        r = self.river()
        order = [waters.state_of(r, lv) for lv in (0.2, 1.4, 1.7, 2.6)]
        self.assertEqual(order, [waters.LOW, waters.FORD, waters.HIGH,
                                 waters.SHUT])
        costs = [waters.DELAY[s] for s in order]
        self.assertEqual(costs, sorted(costs), "a worse river must cost more")

    def test_a_beck_is_fordable_where_a_river_is_not(self):
        beck, river = self.river(2.25), self.river(1.50)
        level = 1.9
        self.assertEqual(waters.state_of(beck, level), waters.LOW)
        self.assertEqual(waters.state_of(river, level), waters.SHUT)

    def test_a_frozen_river_is_a_road(self):
        r = self.river()
        self.assertEqual(waters.state_of(r, 0.5, FROST), waters.ICE)
        self.assertEqual(waters.DELAY[waters.ICE], 0.0)

    def test_a_frost_on_a_full_river_freezes_nothing(self):
        r = self.river()
        self.assertNotEqual(waters.state_of(r, 1.8, FROST), waters.ICE)

    def test_a_bridge_beats_every_state(self):
        r = self.river()
        for level in (0.1, 1.4, 1.7, 4.0):
            self.assertEqual(waters.state_of(r, level, FAIR, bridged=True),
                             waters.BRIDGED)
        self.assertEqual(waters.DELAY[waters.BRIDGED], 0.0)

    def test_the_flood_is_something_the_player_actually_sees(self):
        """A state that happens on two days in a hundred is not a state.

        This is the number IN_SPATE was set from, and it is here so that a
        later change to the weather cannot quietly retire the flood.
        """
        r = self.river()
        shut = spring = 0
        for seed in (3, 7, 11, 19):
            for d in range(3 * 360):
                if waters._season_on(d) != "spring":
                    continue
                spring += 1
                sky = sky_on("spring", d, seed)
                if waters.state_of(r, waters.stage(d, seed), sky) == waters.SHUT:
                    shut += 1
        share = shut / spring
        self.assertGreater(share, 0.08, "the big river never floods")
        self.assertLess(share, 0.45, "the big river is a wall, not a river")


class TestTheGeometry(unittest.TestCase):

    def test_a_road_that_crosses_gets_a_crossing(self):
        r = waters.River("r", "Test", -10.0, 0.0, 10.0, 0.0, 1.5)
        hit = waters.crossings([r], 0.0, -5.0, 0.0, 5.0)
        self.assertEqual(len(hit), 1)
        self.assertAlmostEqual(hit[0][1], 0.0, places=6)
        self.assertAlmostEqual(hit[0][2], 0.0, places=6)

    def test_a_road_that_stops_short_does_not(self):
        r = waters.River("r", "Test", -10.0, 0.0, 10.0, 0.0, 1.5)
        self.assertEqual(waters.crossings([r], 0.0, -5.0, 0.0, -1.0), [])

    def test_a_road_down_the_valley_crosses_nothing(self):
        r = waters.River("r", "Test", -10.0, 0.0, 10.0, 0.0, 1.5)
        self.assertEqual(waters.crossings([r], -5.0, 0.0, 5.0, 0.0), [])

    def test_a_bridge_serves_its_own_reach_and_no_further(self):
        near = waters.Bridge(uid=1, river="r", x=0.0, y=0.0)
        self.assertIsNotNone(waters.served_by([near], "r", waters.REACH - 1, 0))
        self.assertIsNone(waters.served_by([near], "r", waters.REACH + 1, 0))

    def test_an_unfinished_bridge_carries_nothing(self):
        b = waters.Bridge(uid=1, river="r", x=0.0, y=0.0, days_left=10)
        self.assertIsNone(waters.served_by([b], "r", 0.0, 0.0))
        b.days_left = 0
        self.assertIsNotNone(waters.served_by([b], "r", 0.0, 0.0))
        b.broken = True
        self.assertIsNone(waters.served_by([b], "r", 0.0, 0.0))


class TestTheMapDrawsItself(unittest.TestCase):

    def test_the_same_map_always_gets_the_same_rivers(self):
        coords = {"a": (0.0, 0.0), "b": (100.0, 40.0), "c": (-60.0, 90.0)}
        one = waters.draw(coords, 7)
        two = waters.draw(dict(reversed(list(coords.items()))), 7)
        self.assertEqual([r.to_dict() for r in one], [r.to_dict() for r in two])

    def test_different_seeds_draw_different_rivers(self):
        coords = {"a": (0.0, 0.0), "b": (100.0, 40.0), "c": (-60.0, 90.0)}
        self.assertNotEqual([r.to_dict() for r in waters.draw(coords, 3)],
                            [r.to_dict() for r in waters.draw(coords, 11)])

    def test_drawing_does_not_touch_anybody_elses_stream(self):
        """The bug this codebase has now paid for four times."""
        import random
        before = random.Random(1).random()
        waters.draw({"a": (0.0, 0.0), "b": (9.0, 9.0), "c": (-4.0, 4.0)}, 7)
        self.assertEqual(random.Random(1).random(), before)

    def test_one_of_them_is_worth_bridging_and_one_is_not(self):
        rs = waters.draw({"a": (0.0, 0.0), "b": (200.0, 40.0),
                          "c": (-60.0, 190.0)}, 7)
        limits = sorted(r.ford_limit for r in rs)
        self.assertLessEqual(limits[0], waters.WORTH_BRIDGING)
        self.assertGreater(limits[-1], waters.WORTH_BRIDGING)

    def test_a_brook_is_never_a_real_river(self):
        for seed in range(12):
            for r in waters.draw({"a": (0.0, 0.0), "b": (200.0, 40.0),
                                  "c": (-60.0, 190.0)}, seed):
                if r.size == "a real river":
                    self.assertNotIn("brook", r.name.lower())
                    self.assertNotIn("beck", r.name.lower())

    def test_a_map_too_small_to_have_a_country_has_no_rivers(self):
        self.assertEqual(waters.draw({"a": (0.0, 0.0)}, 7), [])


class TestItReachesTheGame(unittest.TestCase):

    def setUp(self):
        self.g = start("marchlands", seed=7)
        self.home = sorted(self.g.world.settlements)[0]
        self.away = max(self.g.world.towns,
                        key=lambda k: len(self.g.world.crossings(self.home, k)))

    def test_the_world_knows_its_own_water(self):
        self.assertTrue(self.g.world.waters())
        self.assertTrue(self.g.world.crossings(self.home, self.away))

    def test_a_flooded_ford_costs_a_host_days(self):
        w = self.g.world
        r = min((c[0] for c in w.crossings(self.home, self.away)),
                key=lambda r: r.ford_limit)
        dry, _ = w.water_days(self.home, self.away, 0, 7)
        # Put a bridge on every crossing of that road and the days go away.
        for river, x, y, _ in w.crossings(self.home, self.away):
            w.bridges.append(waters.Bridge(uid=len(w.bridges) + 1,
                                           river=river.key, x=x, y=y))
        wet, _ = w.water_days(self.home, self.away, 0, 7)
        self.assertEqual(wet, 0.0)
        self.assertGreaterEqual(dry, wet)

    def test_a_cart_and_a_host_are_told_the_same_thing(self):
        """One reader. Two copies of a rule is how the garrison went wrong.

        The cart asks through the trade engine and the host asks through
        `_set_march`; both of them come here, so this is the check that
        neither of them ever grows its own copy.
        """
        g, a, b = self.g, self.home, self.away
        army = next(iter(g.armies), None)
        for day in (0, 40, 120, 300):
            g.day = day
            cart = g.world.water_days(a, b, day, g.seed, g.start_month)[0]
            if army is None:
                continue
            from marchlands.military import host_speed
            g._set_march(army, a, b, {"spearman": 20.0})
            plain = max(1.0, g.world.distance(a, b)
                        / max(host_speed({"spearman": 20.0}), 1.0))
            self.assertAlmostEqual(army.days_left - plain, cart, places=6)

    def test_the_water_actually_slows_a_caravan(self):
        g, c = self.g, _running_route(self.g, self.home, self.away)
        saw = []
        for _ in range(500):
            saw += [m for m in g.tick() if "lost on the road" in m]
        self.assertTrue(saw, "five hundred days and the water never cost a day")

    def test_a_ship_never_meets_a_ford(self):
        g = self.g
        ports = g.world.ports()
        if len(ports) < 2:
            self.skipTest("this map has fewer than two harbours")
        # A cog's leg is set from the sea distance and nothing adds to it.
        c = g.caravans[0]
        c.kind = "ship"
        c.route = [Stop(ports[0]), Stop(ports[1])]
        c.running = True
        for _ in range(30):
            g.tick()
        self.assertEqual(c.wet, [])


class TestBuildingOne(unittest.TestCase):

    def setUp(self):
        self.g = start("marchlands", seed=7)
        self.home = sorted(self.g.world.settlements)[0]
        self.away = max(self.g.world.towns,
                        key=lambda k: len(self.g.world.crossings(self.home, k)))
        self.g.treasury = 40000.0

    def test_masons_take_a_season(self):
        g = self.g
        self.assertIn("Masons begin", g.build_bridge(self.home, self.away))
        b = g.world.bridges[0]
        self.assertFalse(b.standing)
        for _ in range(waters.BRIDGE_DAYS + 1):
            g.tick()
        self.assertTrue(b.standing)

    def test_it_costs_what_it_says(self):
        g = self.g
        before = g.treasury
        g.build_bridge(self.home, self.away)
        self.assertAlmostEqual(before - g.treasury, waters.BRIDGE_COST, places=3)

    def test_a_purse_that_cannot_pay_gets_told_so(self):
        g = self.g
        g.treasury = 10.0
        self.assertIn("and you have", g.build_bridge(self.home, self.away))
        self.assertEqual(g.world.bridges, [])

    def test_you_cannot_bridge_somebody_elses_country(self):
        g = self.g
        pairs = [(a, b) for a in g.world.towns for b in g.world.towns
                 if a < b and g.world.crossings(a, b)]
        if not pairs:
            self.skipTest("no foreign-to-foreign road crosses water here")
        said = g.build_bridge(*pairs[0])
        self.assertIn("bank you hold", said)
        self.assertEqual(g.world.bridges, [])

    def test_a_dry_road_gets_no_bridge(self):
        g = self.g
        dry = [k for k in g.world.towns if not g.world.crossings(self.home, k)]
        if not dry:
            self.skipTest("every road from here crosses something")
        self.assertIn("crosses no water", g.build_bridge(self.home, dry[0]))

    def test_two_bridges_do_not_go_on_one_reach(self):
        g = self.g
        g.build_bridge(self.home, self.away)
        g.world.bridges[0].days_left = 0
        again = g.build_bridge(self.home, self.away)
        self.assertIn("already carries", again)
        self.assertEqual(len(g.world.bridges), 1)

    def test_the_masons_are_not_hired_twice(self):
        g = self.g
        g.build_bridge(self.home, self.away)
        self.assertIn("already at work", g.build_bridge(self.home, self.away))
        self.assertEqual(len(g.world.bridges), 1)

    def test_it_bridges_the_worst_water_on_the_road(self):
        """Not the first one the geometry happened to find."""
        g = self.g
        found = g.world.crossings(self.home, self.away)
        if len(found) < 2:
            self.skipTest("that road crosses only one river")
        g.build_bridge(self.home, self.away)
        worst = min(found, key=lambda c: c[0].ford_limit)[0]
        self.assertEqual(g.world.bridges[0].river, worst.key)


class TestThrowingOneDown(unittest.TestCase):

    def setUp(self):
        self.g = start("marchlands", seed=7)
        self.home = sorted(self.g.world.settlements)[0]
        self.away = max(self.g.world.towns,
                        key=lambda k: len(self.g.world.crossings(self.home, k)))
        self.g.treasury = 40000.0
        self.g.build_bridge(self.home, self.away)
        self.bridge = self.g.world.bridges[0]
        self.bridge.days_left = 0

    def test_it_denies_the_crossing_to_everyone(self):
        g = self.g
        carried, _ = g.world.water_days(self.home, self.away, 0, 7)
        g.break_bridge(self.bridge.uid)
        after, _ = g.world.water_days(self.home, self.away, 0, 7)
        self.assertGreaterEqual(after, carried)
        self.assertTrue(self.bridge.broken)

    def test_a_broken_bridge_earns_nothing(self):
        g = self.g
        before = g.toll_on(self.bridge)
        self.assertGreater(before, 0.0)
        g.break_bridge(self.bridge.uid)
        purse = g.treasury
        g._bridge_day()
        self.assertEqual(g.treasury, purse)

    def test_mending_is_cheaper_than_building(self):
        g = self.g
        g.break_bridge(self.bridge.uid)
        before = g.treasury
        g.mend_bridge(self.bridge.uid)
        paid = before - g.treasury
        self.assertLess(paid, waters.BRIDGE_COST)
        self.assertGreater(paid, 0.0)
        self.assertFalse(self.bridge.broken)
        self.assertEqual(self.bridge.days_left, waters.REBUILD_DAYS)

    def test_you_cannot_throw_down_what_is_not_yours(self):
        g = self.g
        self.bridge.owner = "marchand"
        self.assertIn("no bridge of yours", g.break_bridge(self.bridge.uid))
        self.assertFalse(self.bridge.broken)

    def test_abandoning_the_masonry_removes_it(self):
        g = self.g
        self.bridge.days_left = 20
        self.assertIn("abandoned", g.break_bridge(self.bridge.uid))
        self.assertEqual(g.world.bridges, [])


class TestTheToll(unittest.TestCase):

    def setUp(self):
        self.g = start("marchlands", seed=7)
        self.home = sorted(self.g.world.settlements)[0]
        self.away = max(self.g.world.towns,
                        key=lambda k: len(self.g.world.crossings(self.home, k)))
        self.g.treasury = 40000.0
        self.g.build_bridge(self.home, self.away)
        self.bridge = self.g.world.bridges[0]
        self.bridge.days_left = 0

    def test_a_standing_bridge_pays(self):
        self.assertGreater(self.g.toll_on(self.bridge), 0.0)

    def test_a_busier_reach_pays_better(self):
        """The decision the player is being offered is *where*."""
        g = self.g
        here = g.toll_on(self.bridge)
        xs = [p[0] for p in g.world.coords.values()]
        ys = [p[1] for p in g.world.coords.values()]
        far = waters.Bridge(uid=99, river=self.bridge.river,
                            x=max(xs) + 900.0, y=max(ys) + 900.0)
        self.assertGreater(here, g.toll_on(far))
        self.assertAlmostEqual(g.toll_on(far), 0.0, places=6)

    def test_it_is_capped(self):
        self.assertLessEqual(self.g.toll_on(self.bridge), waters.TOLL_CAP)

    def test_it_pays_back_inside_a_lifetime(self):
        """Not a number I like, a number I can defend.

        A bridge on a good reach must pay for itself on tolls alone inside a
        few years -- the saved cart-days are on top and are the real reason.
        If a change to the map or the rate makes the toll a rounding error,
        the build button is a trap and this should say so.
        """
        days = waters.BRIDGE_COST / max(self.g.toll_on(self.bridge), 1e-9)
        self.assertLess(days, 3 * 360, "the toll alone never pays it back")


class TestSomebodyElsesHostOnYourDeck(unittest.TestCase):
    """A marching army was a customer. Unless it was coming for you."""

    def setUp(self):
        self.g = start("marchlands", seed=7)
        self.home = sorted(self.g.world.settlements)[0]
        self.away = max(self.g.world.towns,
                        key=lambda k: len(self.g.world.crossings(self.home, k)))
        self.g.treasury = 40000.0
        # Bridge every crossing on that road so the host cannot miss one.
        for river, x, y, _ in self.g.world.crossings(self.home, self.away):
            self.g.world.bridges.append(
                waters.Bridge(uid=len(self.g.world.bridges) + 1,
                              river=river.key, x=x, y=y, owner="player",
                              name=f"{river.name} Bridge"))
        self.army = next(iter(self.g.armies), None)

    def _host(self, owner, target):
        from marchlands.military import Army
        a = Army(uid=900, name="a host", owner=owner,
                 units={"spearman": 100.0}, at=self.away, home=self.away)
        self.g.armies.append(a)
        return a

    def test_a_host_going_past_pays(self):
        g = self.g
        a = self._host(self.away, self.away)
        # Send it somewhere that is not yours, over the same water.
        purse = g.treasury
        said = g._set_march(a, self.home, self.away, a.units)
        self.assertGreater(g.treasury, purse)
        self.assertIn("pays", said)

    def test_a_host_coming_for_you_pays_nothing(self):
        g = self.g
        a = self._host(self.away, self.home)
        purse = g.treasury
        said = g._set_march(a, self.away, self.home, a.units)
        self.assertEqual(g.treasury, purse)
        self.assertIn("crosses your", said)

    def test_your_own_host_is_not_charged(self):
        g = self.g
        a = self._host("player", self.away)
        purse = g.treasury
        g._set_march(a, self.home, self.away, a.units)
        self.assertEqual(g.treasury, purse)

    def test_a_bridge_that_is_down_charges_nobody(self):
        g = self.g
        for b in g.world.bridges:
            b.broken = True
        a = self._host(self.away, self.away)
        purse = g.treasury
        g._set_march(a, self.home, self.away, a.units)
        self.assertEqual(g.treasury, purse)


class TestWhatYouAreAllowedToKnow(unittest.TestCase):

    def test_a_river_is_not_fogged(self):
        """You can see the water. You cannot see next Tuesday's water."""
        g = start("marchlands", seed=7)
        rows = g.world.water_state(sorted(g.world.settlements)[0],
                                   sorted(g.world.towns)[0], g.day, g.seed)
        for row in rows:
            self.assertIn(row["state"], waters.WORDS)
            self.assertIn("days", row)

    def test_the_panel_and_the_cart_agree(self):
        g = start("marchlands", seed=7)
        home = sorted(g.world.settlements)[0]
        away = max(g.world.towns, key=lambda k: len(g.world.crossings(home, k)))
        for day in (0, 55, 200):
            rows = g.world.water_state(home, away, day, g.seed, g.start_month)
            days, _ = g.world.water_days(home, away, day, g.seed, g.start_month)
            self.assertAlmostEqual(sum(r["days"] for r in rows), days, places=6)


class TestItSurvivesASave(unittest.TestCase):

    def test_the_rivers_and_the_bridges_come_back(self):
        g = start("marchlands", seed=7)
        g.treasury = 40000.0
        home = sorted(g.world.settlements)[0]
        away = max(g.world.towns, key=lambda k: len(g.world.crossings(home, k)))
        g.build_bridge(home, away)
        g.world.bridges[0].days_left = 3
        for _ in range(20):
            g.tick()
        h = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual([r.to_dict() for r in h.world.waters()],
                         [r.to_dict() for r in g.world.waters()])
        self.assertEqual([b.to_dict() for b in h.world.bridges],
                         [b.to_dict() for b in g.world.bridges])

    def test_a_save_from_before_the_water_still_loads(self):
        g = start("marchlands", seed=7)
        d = g.to_dict()
        d["world"].pop("river_lines", None)
        d["world"].pop("bridges", None)
        d["world"].pop("river_seed", None)
        h = GameState.from_dict(json.loads(json.dumps(d)))
        self.assertEqual(h.world.bridges, [])
        self.assertTrue(h.world.waters())      # drawn on first ask

    def test_a_cart_mid_crossing_survives(self):
        g = start("marchlands", seed=7)
        home = sorted(g.world.settlements)[0]
        away = max(g.world.towns, key=lambda k: len(g.world.crossings(home, k)))
        c = _running_route(g, home, away)
        for _ in range(40):
            g.tick()
        h = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(h.caravans[0].wet, g.caravans[0].wet)
        self.assertAlmostEqual(h.caravans[0].days_left, g.caravans[0].days_left)


class TestTheAutoplayerUsesIt(unittest.TestCase):
    """A mechanic the bot never touches is a mechanic nothing measures."""

    def test_the_bot_and_the_panel_want_the_same_bridge(self):
        g = start("marchlands", seed=7)
        home = sorted(g.world.settlements)[0]
        away = max(g.world.towns, key=lambda k: len(g.world.crossings(home, k)))
        _running_route(g, home, away)
        found = g.worst_unbridged()
        self.assertIsNotNone(found)
        a, b, river = found
        limits = [r.ford_limit for r, _, _, br in g.world.crossings(a, b)
                  if br is None]
        self.assertEqual(river.ford_limit, min(limits))

    def test_it_asks_for_nothing_when_no_cart_is_running(self):
        g = start("marchlands", seed=7)
        for c in g.caravans:
            c.running = False
        self.assertIsNone(g.worst_unbridged())

    def test_the_bot_puts_one_up(self):
        from marchlands.sim import Bot
        g = start("marchlands", seed=5)
        bot = Bot(g)
        for _ in range(1300):
            bot.step()
            g.tick()
        self.assertTrue([b for b in g.world.bridges if b.owner == "player"],
                        "the autoplayer never built a bridge in three years")


if __name__ == "__main__":
    unittest.main()
