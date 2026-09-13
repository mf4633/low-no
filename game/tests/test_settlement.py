"""Land, labour, food and mood."""

import random
import unittest

from marchlands import config as C
from marchlands.goods import ALL_KEYS, RATION_GOODS, good
from marchlands.market import Market
from marchlands.settlement import Settlement


def make(pop=120.0, stock=150.0, **terrain) -> Settlement:
    land = {"fertile": 6, "forest": 4, "hills": 2, "clay": 2, "coast": 1, "urban": 12}
    land.update(terrain)
    m = Market(name="Home", stock={k: stock for k in ALL_KEYS},
               target={k: 100.0 for k in ALL_KEYS})
    s = Settlement(name="Home", terrain=land, market=m, population=pop)
    s.update_market_targets()
    return s


def raise_now(s: Settlement, *keys: str):
    for k in keys:
        inst = s.start_build(k)
        inst.days_left = 0
    return s


class TestLand(unittest.TestCase):
    def test_slots_are_finite(self):
        s = make(fertile=2)
        raise_now(s, "farm", "farm")
        ok, why = s.can_build("farm")
        self.assertFalse(ok)
        self.assertIn("fertile", why)

    def test_materials_are_required(self):
        s = make(stock=0.0)
        ok, why = s.can_build("mill")
        self.assertFalse(ok)
        self.assertIn("Wood", why)

    def test_building_consumes_materials(self):
        s = make()
        before = s.market.stock["wood"]
        s.start_build("mill")
        self.assertLess(s.market.stock["wood"], before)

    def test_construction_takes_days(self):
        s = make()
        s.start_build("mill")
        self.assertFalse(s.buildings[-1].complete)
        for _ in range(C.DAYS_PER_MONTH):
            s.tick("summer", random.Random(1))
        self.assertTrue(s.buildings[-1].complete)


class TestProduction(unittest.TestCase):
    def test_chain_runs(self):
        s = make(stock=0.0)
        s.market.stock["wheat"] = 500.0
        raise_now(s, "mill")
        s.tick("summer", random.Random(1))
        self.assertGreater(s.market.stock["flour"], 0.0)
        self.assertLess(s.market.stock["wheat"], 500.0)

    def test_no_inputs_no_output(self):
        s = make(stock=0.0)
        raise_now(s, "mill")
        rep = s.tick("summer", random.Random(1))
        self.assertEqual(rep.produced.get("flour", 0.0), 0.0)
        self.assertIn("Wheat", s.buildings[-1].idle_reason)

    def test_season_moves_the_harvest(self):
        out = {}
        for season in ("winter", "summer"):
            s = make(stock=0.0)
            raise_now(s, "farm")
            out[season] = s.tick(season, random.Random(1)).produced.get("wheat", 0.0)
        self.assertGreater(out["summer"], out["winter"] * 2)

    def test_closed_buildings_do_nothing(self):
        s = make(stock=0.0)
        s.market.stock["wheat"] = 500.0
        raise_now(s, "mill")
        s.buildings[-1].enabled = False
        rep = s.tick("summer", random.Random(1))
        self.assertEqual(rep.produced.get("flour", 0.0), 0.0)

    def test_workforce_is_shared_out(self):
        s = make(pop=10.0, stock=0.0)         # 5 workers for 9 jobs
        raise_now(s, "farm", "farm", "farm")
        s.tick("summer", random.Random(1))
        self.assertEqual(s.employed, s.workforce)
        self.assertLess(s.employed, s.jobs_offered)


class TestFood(unittest.TestCase):
    def test_rations_are_counted_in_nourishment(self):
        s = make(stock=0.0)
        s.market.stock["bread"] = 1000.0
        rep = s.tick("summer", random.Random(1))
        eaten = rep.eaten["bread"]
        want = C.RATION_LEVELS[s.ration_level][0] * s.population
        self.assertAlmostEqual(eaten * good("bread").nourish, want, places=3)
        self.assertEqual(rep.hunger, 0.0)

    def test_gruel_feeds_worse_than_bread(self):
        eaten = {}
        for k in ("wheat", "bread"):
            s = make(stock=0.0)
            s.market.stock[k] = 1000.0
            eaten[k] = s.tick("summer", random.Random(1)).eaten[k]
        self.assertGreater(eaten["wheat"], eaten["bread"])

    def test_empty_stores_mean_hunger(self):
        s = make(stock=0.0)
        rep = s.tick("summer", random.Random(1))
        self.assertEqual(rep.hunger, 1.0)
        self.assertLess(dict(s.mood_factors()).get("hunger", 0.0), 0.0)

    def test_variety_is_rewarded(self):
        s = make(stock=0.0)
        for k in RATION_GOODS:
            s.market.stock[k] = 300.0
        rep = s.tick("summer", random.Random(1))
        self.assertGreater(rep.variety, 1)
        self.assertGreater(dict(s.mood_factors()).get("variety", 0.0), 0.0)


class TestMoodAndPeople(unittest.TestCase):
    def test_taxes_cost_goodwill(self):
        moods = {}
        for level in (0, 4):
            s = make()
            s.tax_level = level
            s.tick("summer", random.Random(1))
            moods[level] = dict(s.mood_factors())["taxes"]
        self.assertGreater(moods[0], moods[4])

    def test_crowding_hurts(self):
        s = make(pop=300.0)
        s.tick("summer", random.Random(1))
        self.assertLess(dict(s.mood_factors()).get("crowding", 0.0), 0.0)

    def test_happy_towns_grow_and_sad_ones_empty(self):
        grow = make(pop=50.0)
        raise_now(grow, "townhouse", "townhouse")
        grow.popularity = 90.0
        grow.tick("summer", random.Random(1))
        self.assertGreater(grow.migrate(random.Random(1)), 0)

        shrink = make(pop=50.0)
        shrink.popularity = 5.0
        shrink.tick("summer", random.Random(1))
        self.assertLess(shrink.migrate(random.Random(1)), 0)

    def test_unrest_stops_the_work(self):
        s = make()
        s.popularity = 2.0
        self.assertLessEqual(s.productivity, C.UNREST_PRODUCTIVITY)


class TestStores(unittest.TestCase):
    def test_perishables_rot(self):
        s = make(stock=0.0)
        s.market.stock["bread"] = 100.0
        s.population = 0.0
        rep = s.tick("summer", random.Random(1))
        self.assertGreater(rep.spoiled.get("bread", 0.0), 0.0)

    def test_a_granary_halves_the_loss(self):
        losses = []
        for with_granary in (False, True):
            s = make(stock=0.0)
            s.population = 0.0
            if with_granary:
                raise_now(s, "granary")
            s.market.stock["bread"] = 100.0
            losses.append(s.tick("summer", random.Random(1)).spoiled.get("bread", 0.0))
        self.assertAlmostEqual(losses[1], losses[0] * 0.5, places=4)

    def test_overflow_spills(self):
        s = make(stock=0.0)
        s.population = 0.0
        s.market.stock["stone"] = C.BASE_STORAGE * 2
        rep = s.tick("summer", random.Random(1))
        self.assertGreater(rep.spoiled.get("stone", 0.0), 0.0)
        self.assertTrue(any("overflow" in n for n in rep.notes))

    def test_stock_never_goes_negative(self):
        rng = random.Random(4)
        s = make(stock=30.0)
        raise_now(s, "farm", "mill", "bakery", "brewery", "smelter", "kiln")
        for _ in range(400):
            s.tick(random.choice(("winter", "spring", "summer", "autumn")), rng)
            s.update_mood()
            s.migrate(rng)
            for k in ALL_KEYS:
                self.assertGreaterEqual(s.market.stock[k], -1e-9, k)


if __name__ == "__main__":
    unittest.main()
