"""The console: every command should run, and none should raise."""

import io
import os
import tempfile
import unittest

from marchlands.chronicle import MOMENTOUS, ROUTINE
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
            "truce dunmere",
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

    def test_diplomacy(self):
        g = self.con.game
        g.treasury = 40_000
        g.world.towns["ostmark"].hostility = 80.0
        out = self.run_script("truce ostmark", "truce ostmark 120",
                              "gift ostmark 1500", "demand dunmere", "war")
        self.assertIn("would cost", out)
        self.assertIn("swears off", out)
        self.assertIn("cools", out)
        self.assertGreater(g.world.towns["ostmark"].truce_days, 0)

    def test_bad_military_input_is_reported(self):
        out = self.run_script("recruit dragon 3", "host nowhere spearman 2",
                              "march 99 dunmere", "army 99", "tech alchemy",
                              "host aldworth spearman 900")
        self.assertGreaterEqual(out.count("!"), 4)

    def test_onboarding_commands(self):
        out = self.run_script("briefing", "scenarios", "hint")
        self.assertIn("Marchlands", out)
        self.assertIn("salt_road", out)
        self.assertIn("*", out)          # the hints are bulleted

    def test_hints_point_at_what_is_actually_wrong(self):
        g = self.con.game
        s = g.world.settlements["aldworth"]
        for k in ("bread", "apples", "cheese", "wheat", "flour"):
            s.market.stock[k] = 0.0
        hints = " ".join(self.con.hints())
        self.assertIn("food", hints.lower())

    def test_autosave_writes_after_every_turn(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "auto.save")
            self.run_script(f"autosave {path}", "next 2")
            self.assertTrue(os.path.exists(path))
            self.run_script("autosave off")
            os.remove(path)
            self.run_script("next 1")
            self.assertFalse(os.path.exists(path))

    def test_the_sea(self):
        g = self.con.game
        g.treasury = 60_000
        g.progress.age = 2
        g.found("sealow")
        s = g.world.settlements["sealow"]
        for k, q in (("wood", 300), ("planks", 200), ("stone", 300)):
            s.market.add(k, q)
        g.build("sealow", "harbour")
        s.buildings[-1].days_left = 0
        out = self.run_script("scan sea 3", "new ship sealow", "caravans", "map")
        self.assertIn("hull of", out)
        self.assertIn("launched at", out)
        self.assertTrue(any(c.sails for c in g.caravans))

    def test_quit_sets_the_flag(self):
        self.run_script("quit")
        self.assertTrue(self.con.quit)


class TestSparkline(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(sparkline([1]), "")
        self.assertEqual(len(sparkline(list(range(100)), width=30)), 30)
        self.assertEqual(sparkline([5, 5, 5]), "▄▄▄")


class TestBadSaves(unittest.TestCase):
    """Nothing a player can point `load` at should end the session.

    A missing file used to take the whole game down with it, which is a poor
    way to find out you typed the name wrong and a worse one if you had an
    hour in the game you were about to save.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = io.StringIO()
        self.con = Console(new_game(seed=5), out=self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self, path):
        self.out.truncate(0)
        self.out.seek(0)
        self.con.do(f"load {path}")          # must not raise
        return self.out.getvalue()

    def _write(self, name, body):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_a_file_that_is_not_there(self):
        said = self._load(os.path.join(self.tmp.name, "nope.json"))
        self.assertIn("no saved game", said)

    def test_a_file_that_is_not_json(self):
        said = self._load(self._write("junk.json", "not a save at all"))
        self.assertIn("not even JSON", said)

    def test_a_save_cut_off_half_way(self):
        good = os.path.join(self.tmp.name, "ok.json")
        self.con.do(f"save {good}")
        with open(good, encoding="utf-8") as fh:
            body = fh.read()
        said = self._load(self._write("cut.json", body[:400]))
        self.assertIn("not even JSON", said)

    def test_json_that_is_not_a_game(self):
        said = self._load(self._write("empty.json", "{}"))
        self.assertIn("damaged", said)

    def test_a_directory(self):
        said = self._load(self.tmp.name)
        self.assertIn("cannot read", said)

    def test_and_the_game_carries_on_afterwards(self):
        before = self.con.game.day
        self._load(os.path.join(self.tmp.name, "nope.json"))
        self.con.do("next")
        self.assertEqual(self.con.game.day, before + 1)

    def test_a_good_save_still_loads(self):
        path = os.path.join(self.tmp.name, "ok.json")
        self.con.do("next 5")
        self.con.do(f"save {path}")
        day = self.con.game.day
        self.con.do("next 5")
        said = self._load(path)
        self.assertIn("loaded", said)
        self.assertEqual(self.con.game.day, day)

    def test_saving_somewhere_it_cannot_write(self):
        self.out.truncate(0)
        self.out.seek(0)
        self.con.do(f"save {os.path.join(self.tmp.name, 'no', 'such', 'dir.json')}")
        self.assertIn("could not write", self.out.getvalue())


class TestTheChronicleCountsWhatItShows(unittest.TestCase):
    """The head used to count the whole book while the page showed only the
    days worth telling, so a reader saw `4 entries` above one line."""

    def setUp(self):
        self.buf = io.StringIO()
        self.game = new_game(seed=5)
        self.con = Console(self.game, out=self.buf)
        g = self.game
        for text, weight in [("a quiet day", ROUTINE), ("another", ROUTINE),
                             ("the keep fell", MOMENTOUS)]:
            g.chronicle.record(day=g.day, year=g.year, season=g.season,
                               text=text, weight=weight)

    def said(self, line):
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do(line)
        return self.buf.getvalue()

    def test_a_filtered_page_says_how_much_it_is_hiding(self):
        out = self.said("chronicle")
        self.assertIn("of 3 entries", out)
        self.assertIn("chronicle all", out)

    def test_the_whole_book_is_counted_plainly(self):
        out = self.said("chronicle all")
        self.assertIn("3 entries", out)
        self.assertNotIn("of 3 entries", out)
        self.assertNotIn("chronicle all` reads", out)


if __name__ == "__main__":
    unittest.main()
