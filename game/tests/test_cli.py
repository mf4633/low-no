"""The console: every command should run, and none should raise."""

import io
import os
import tempfile
import unittest

from marchlands.cli import Console, sparkline
from marchlands.scenario import new_game


class TestConsole(unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        self.con = Console(new_game(seed=5), out=self.buf)

    def run_script(self, *lines):
        for line in lines:
            self.con.do(line)
        return self.buf.getvalue()

    def test_every_view_renders(self):
        out = self.run_script(
            "status", "map", "town", "stores", "needs", "buildings",
            "info mill", "chain bread", "prices wheat", "market vantry",
            "market aldworth", "scan 3", "caravans", "log", "chart worth",
            "age", "tech", "units", "war", "army", "garrison", "battles",
            "help", "help trade", "help town", "help war", "help win",
        )
        self.assertNotIn("Traceback", out)
        self.assertIn("Aldworth", out)
        self.assertIn("Vantry", out)

    def test_playing_a_few_turns(self):
        out = self.run_script("build poleturner", "next 8", "town", "status")
        self.assertIn("Poleturner begun", out)

    def test_running_a_route_by_hand(self):
        out = self.run_script(
            "route 1 add aldworth buy bread 60@9",
            "route 1 add dunmere sell bread all@6",
            "go 1", "next 6", "caravan 1",
        )
        self.assertNotIn("Traceback", out)
        self.assertTrue(self.con.game.caravans[0].route)

    def test_auto_route(self):
        self.run_script("auto 1", "next 10")
        self.assertTrue(self.con.game.caravans[0].route)

    def test_levers(self):
        out = self.run_script("ration generous", "tax 3", "ration", "tax", "garrison")
        self.assertIn("generous", out)
        self.assertIn("heavy", out)
        self.assertIn("garrison", out)

    def test_bad_input_is_reported_not_raised(self):
        out = self.run_script(
            "frobnicate", "build castle", "prices unobtanium", "route 9 add nowhere",
            "market atlantis", "info 42", "ration sideways", "next -4",
        )
        self.assertGreaterEqual(out.count("!"), 5)

    def test_abbreviations_resolve(self):
        out = self.run_script("s", "c", "buil", "prices whe")
        self.assertIn("Wheat", out)

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.save")
            self.run_script("next 4", f"save {path}", f"load {path}")
            self.assertTrue(os.path.exists(path))
        self.assertEqual(self.con.game.day, 4)

    def test_climbing_and_learning(self):
        g = self.con.game
        g.treasury = 50_000
        home = g.home()
        home.market.add("wood", 400)
        home.market.add("stone", 400)
        for key in ("mill", "guildhall"):
            home.start_build(key).days_left = 0
        out = self.run_script("age begin", "tech heavy_plough", "next 2", "status")
        self.assertIn("Work begins", out)
        self.assertIn("takes up", out)
        self.assertTrue(g.progress.advancing)
        self.assertEqual(g.progress.researching, "heavy_plough")

    def test_mustering_and_marching(self):
        g = self.con.game
        g.treasury = 50_000
        g.world.settlements["aldworth"].market.add("spears", 60)
        out = self.run_script("recruit spearman 6", "garrison",
                              "host aldworth spearman 4", "army 1",
                              "march 1 dunmere", "next 2", "war", "recall 1")
        self.assertIn("muster at", out)
        self.assertIn("marches on", out)
        self.assertEqual(len(g.armies), 1)

    def test_bad_military_input_is_reported(self):
        out = self.run_script("recruit dragon 3", "host nowhere spearman 2",
                              "march 99 dunmere", "army 99", "tech alchemy",
                              "host aldworth spearman 900")
        self.assertGreaterEqual(out.count("!"), 4)

    def test_quit_sets_the_flag(self):
        self.run_script("quit")
        self.assertTrue(self.con.quit)


class TestSparkline(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(sparkline([1]), "")
        self.assertEqual(len(sparkline(list(range(100)), width=30)), 30)
        self.assertEqual(sparkline([5, 5, 5]), "▄▄▄")


if __name__ == "__main__":
    unittest.main()
