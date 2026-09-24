"""Ages, technologies and the house you were born into."""

import unittest

from marchlands.buildings import BUILDINGS
from marchlands.military import UNITS
from marchlands.scenario import new_game
from marchlands.tech import AGES, HOUSES, TECHS, Progress


class TestEffects(unittest.TestCase):
    def test_multipliers_compound_and_bonuses_add(self):
        p = Progress(researched={"heavy_plough", "three_field"})
        self.assertAlmostEqual(p.mult("yield_field"), 1.20 * 1.25, places=6)
        q = Progress(researched={"drove_roads", "ox_carts"})
        self.assertAlmostEqual(q.bonus("cart_capacity"), 100.0, places=6)

    def test_an_unknown_effect_is_neutral(self):
        p = Progress()
        self.assertEqual(p.mult("yield_field"), 1.0)
        self.assertEqual(p.bonus("storage"), 0.0)

    def test_prerequisites_gate_the_list(self):
        p = Progress(age=2)
        keys = {t.key for t in p.available()}
        self.assertIn("heavy_plough", keys)
        self.assertNotIn("crop_rotation", keys)     # needs three_field, age 3
        p.researched.add("heavy_plough")
        self.assertIn("three_field", {t.key for t in p.available()})

    def test_the_age_gates_the_list(self):
        p = Progress(age=1)
        self.assertTrue(all(t.age == 1 for t in p.available()))

    def test_every_prerequisite_exists_and_comes_first(self):
        for t in TECHS.values():
            if t.prereq:
                self.assertIn(t.prereq, TECHS, t.key)
                self.assertLessEqual(TECHS[t.prereq].age, t.age, t.key)

    def test_every_unlock_names_a_real_soldier(self):
        for t in TECHS.values():
            for u in t.unlocks:
                self.assertIn(u, UNITS, t.key)


class TestHouses(unittest.TestCase):
    def test_each_house_is_hidden_and_unique(self):
        for key, h in HOUSES.items():
            self.assertTrue(h.hidden)
            self.assertTrue(h.unlocks, key)
            p = Progress(researched={key})
            self.assertNotIn(key, [t.key for t in p.available()])

    def test_a_house_bonus_is_live_from_day_one(self):
        g = new_game(house="plough")
        self.assertAlmostEqual(g.progress.mult("yield_field"), 1.15, places=6)
        h = new_game(house="hansa")
        self.assertAlmostEqual(h.progress.bonus("cart_capacity"), 35.0, places=6)

    def test_a_unique_soldier_belongs_to_one_house(self):
        plough = new_game(house="plough")
        marcher = new_game(house="marcher")
        self.assertIn("billman", plough.progress.unlocked_units())
        self.assertNotIn("billman", marcher.progress.unlocked_units())

    def test_an_unknown_house_is_refused(self):
        with self.assertRaises(KeyError):
            new_game(house="borgia")


class TestClimbing(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=4)

    def test_the_age_needs_its_buildings(self):
        g = self.g
        g.treasury = 99999
        home = g.home()
        for k, q in AGES[2].cost.items():
            if k != "coin":
                home.market.add(k, q * 2)
        self.assertIn("Windmill", g.begin_age())     # no mill yet

    def test_climbing_costs_coin_goods_and_weeks(self):
        g = self.g
        g.treasury = 99999
        home = g.home()
        inst = home.start_build("mill")
        inst.days_left = 0
        for k, q in AGES[2].cost.items():
            if k != "coin":
                home.market.add(k, q * 2)
        before = g.treasury
        self.assertIn("Work begins", g.begin_age())
        self.assertLess(g.treasury, before)
        self.assertEqual(g.progress.age, 1)
        g.advance(AGES[2].days + 1)
        self.assertEqual(g.progress.age, 2)

    def test_research_needs_a_guildhall(self):
        g = self.g
        g.treasury = 99999
        self.assertIn("guildhall", g.research("heavy_plough"))

    def test_research_finishes_and_applies(self):
        g = self.g
        g.treasury = 99999
        home = g.home()
        inst = home.start_build("guildhall")
        inst.days_left = 0
        home.market.add("wood", 200)
        self.assertIn("takes up", g.research("heavy_plough"))
        self.assertIn("busy", g.research("scythes"))
        g.advance(TECHS["heavy_plough"].days + 2)
        self.assertTrue(g.progress.knows("heavy_plough"))
        self.assertAlmostEqual(g.progress.mult("yield_field"), 1.15 * 1.20, places=6)

    def test_buildings_wait_on_their_age(self):
        g = self.g
        g.treasury = 99999
        home = g.home()
        home.market.add("stone", 400)
        home.market.add("iron", 100)
        self.assertIn("Age of", g.build("aldworth", "armourer"))

    def test_every_building_and_unit_sits_in_a_real_age(self):
        for b in BUILDINGS.values():
            self.assertIn(b.age, AGES, b.key)
        for u in UNITS.values():
            self.assertIn(u.age, AGES, u.key)


if __name__ == "__main__":
    unittest.main()
