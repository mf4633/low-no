"""Five architecture sets, and one honest ratio for the people in them.

Two questions answered in one file because they are the same question asked at
two scales. The first is Age of Empires II's: can you tell whose town you are
looking at from the roofline? The second is the one every builder game has to
answer and most answer by lying: the simulation runs on aggregates and the
picture draws people, so what is a drawn person?

The answer to both is that the picture must be a *readout*. A place is built
out of what is under it, and a figure is a sample of the aggregate at a stated
ratio, doing what the aggregate is really doing.
"""

import io
import json
import random
import re
import unittest

from marchlands import culture as cultures
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.layout import MEN_PER_FIGURE, SOULS_PER_FIGURE, plan_for
from marchlands.scenario import new_game
from marchlands.scenarios import start
from marchlands.sim import Bot
from marchlands.web import snapshot


def plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def grown(seed=5, days=300, house="plough"):
    g = start("marchlands", seed=seed, house=house)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
    return g, g.home()


class TestFiveSkylines(unittest.TestCase):
    def test_every_idiom_differs_in_more_than_colour(self):
        """A palette swap is a reskin. Four channels -- what the walls are,
        what the roofs are, how steep and how tall -- is a place."""
        seen = set()
        for c in cultures.CULTURES.values():
            mark = (tuple(sorted(c.walls.items())), tuple(sorted(c.roofs.items())),
                    round(c.pitch, 2), c.gable, round(c.stretch, 2))
            self.assertNotIn(mark, seen, f"{c.key} is a reskin of another")
            seen.add(mark)

    def test_each_has_a_name_and_a_reason(self):
        for c in cultures.CULTURES.values():
            self.assertTrue(c.name and c.blurb, c.key)
            self.assertGreater(len(c.blurb), 40, c.key)

    def test_an_unknown_idiom_falls_back_rather_than_raising(self):
        self.assertEqual(cultures.culture("atlantean").key, cultures.DEFAULT)
        self.assertEqual(cultures.culture("").key, cultures.DEFAULT)

    def test_the_gables_are_genuinely_different_shapes(self):
        shapes = {c.gable for c in cultures.CULTURES.values()}
        self.assertGreaterEqual(len(shapes), 3)
        self.assertIn("stepped", shapes)
        self.assertIn("hipped", shapes)


class TestTheGroundDecides(unittest.TestCase):
    """A culture belongs to the place, not the player -- otherwise a game has
    one skyline in it and the whole feature is a character-select screen."""

    def test_a_coast_builds_like_a_port(self):
        self.assertEqual(cultures.for_ground({"coast": 3, "fertile": 9}), "hansa")

    def test_a_hill_builds_in_stone(self):
        self.assertEqual(cultures.for_ground({"hills": 7, "fertile": 2}), "ironhand")

    def test_and_chalk_builds_low(self):
        self.assertEqual(cultures.for_ground({"fertile": 9, "hills": 1}), "vale")

    def test_a_house_raises_its_first_hold_in_its_own_idiom(self):
        """The exception, and it has to be checked first or it is not one:
        testing the ground before the house opened all five houses on the
        same chalk in the same idiom, which makes the feature pointless."""
        for house, want in cultures.OF_HOUSE.items():
            g = new_game(seed=5, house=house)
            self.assertEqual(g.home().culture, want, house)

    def test_but_not_the_ones_it_founds_afterwards(self):
        g = new_game(seed=5, house="marcher")
        for site in g.world.sites.values():
            local = cultures.for_ground(site.terrain)
            self.assertEqual(local, cultures.for_ground(site.terrain, "marcher"),
                             "the house followed its masons to the second hold")

    def test_every_town_on_the_march_has_one(self):
        g = new_game(seed=5)
        for key, t in g.world.towns.items():
            self.assertIn(t.culture, cultures.CULTURES, key)

    def test_and_the_march_has_more_than_one_skyline_on_it(self):
        g = new_game(seed=5)
        self.assertGreaterEqual(
            len({t.culture for t in g.world.towns.values()}), 3)

    def test_taking_a_town_does_not_re_roof_it(self):
        g = new_game(seed=5)
        was = g.world.towns["dunmere"].culture
        g.world.towns["dunmere"].owner = "player"
        self.assertEqual(g.world.towns["dunmere"].culture, was)

    def test_it_survives_a_save(self):
        g = new_game(seed=5, house="hansa")
        back = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.home().culture, "hansa")
        self.assertEqual(back.world.towns["ostmark"].culture,
                         g.world.towns["ostmark"].culture)

    def test_it_is_the_same_building_underneath(self):
        """Architecture is how a thing looks. A bonus attached to a roof shape
        would be a bonus pretending to be a culture."""
        a = new_game(seed=5, house="hansa").home()
        b = new_game(seed=5, house="ironhand").home()
        self.assertNotEqual(a.culture, b.culture)
        self.assertEqual(a.housing(), b.housing())
        self.assertEqual(a.storage(), b.storage())
        self.assertEqual(a.wall_max(), b.wall_max())


class TestOneFigureStandsForFourteen(unittest.TestCase):
    """The simulation runs on aggregates and the picture draws people. Draw
    one figure per soul and a town of two hundred is an unreadable crowd; draw
    a decorative handful and the picture is telling you something untrue. A
    figure is a sample at a ratio the interface states."""

    def test_the_ratio_is_stated_rather_than_implied(self):
        _g, s = grown()
        plan = json.loads(json.dumps(plan_for(s).to_dict()))
        self.assertEqual(plan["per_figure"], SOULS_PER_FIGURE)
        self.assertEqual(plan["per_watch"], MEN_PER_FIGURE)

    def test_and_the_page_says_it_out_loud(self):
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
            self.assertIn('id="scale"', fh.read())
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("one figure =", js)

    def test_a_bigger_town_has_more_of_them(self):
        _g, s = grown()
        few = len([f for f in plan_for(s).folk if f.kind != "watch"])
        s.population *= 2
        many = len([f for f in plan_for(s).folk if f.kind != "watch"])
        self.assertGreater(many, few)

    def test_but_never_a_crowd_nobody_can_read(self):
        _g, s = grown()
        s.population = 100000.0
        self.assertLessEqual(
            len([f for f in plan_for(s).folk if f.kind != "watch"]), 20)

    def test_everybody_drawn_is_doing_something_the_town_is_doing(self):
        _g, s = grown()
        for f in plan_for(s).folk:
            self.assertIn(f.kind, ("worker", "idle", "watch"))
            self.assertTrue(f.at, f.kind)

    def test_a_worker_walks_to_a_shed_that_is_actually_running(self):
        _g, s = grown()
        running = {b.name for b in plan_for(s).buildings if b.running}
        for f in plan_for(s).folk:
            if f.kind == "worker":
                self.assertIn(f.at, running)

    def test_a_thinly_held_wall_looks_thinly_held(self):
        """No warning, no icon, no number. The garrison is drawn along the
        wall you drew, so enclosing more ground than you can man is something
        you can see."""
        _g, s = grown()
        long_wall = len([f for f in plan_for(s).folk if f.kind == "watch"])
        s.units = {k: v * 0.25 for k, v in s.units.items()}
        thin = len([f for f in plan_for(s).folk if f.kind == "watch"])
        self.assertLess(thin, long_wall)

    def test_and_the_watch_is_standing_on_real_wall(self):
        _g, s = grown()
        wall = set(s.plan().wall)
        for f in plan_for(s).folk:
            if f.kind == "watch":
                self.assertIn((int(f.x), int(f.y)), wall)

    def test_a_town_with_no_garrison_has_an_empty_wall(self):
        _g, s = grown()
        s.units = {}
        self.assertFalse([f for f in plan_for(s).folk if f.kind == "watch"])

    def test_shutting_every_shed_puts_everybody_in_the_street(self):
        _g, s = grown()
        for b in s.buildings:
            b.enabled = False
        s.tick("spring", random.Random(1))
        kinds = {f.kind for f in plan_for(s).folk}
        self.assertIn("idle", kinds)
        self.assertNotIn("worker", kinds)


class TestItReachesTheScreens(unittest.TestCase):
    def test_the_snapshot_carries_the_idiom(self):
        g, _s = grown(house="abbey")
        snap = json.loads(json.dumps(snapshot(g)))
        self.assertEqual(snap["culture"]["key"], "abbey")
        for field in ("walls", "roofs", "pitch", "gable", "stretch"):
            self.assertIn(field, snap["culture"])

    def test_and_which_skyline_each_town_has(self):
        g, _s = grown()
        snap = json.loads(json.dumps(snapshot(g)))
        self.assertTrue(snap["court"]["towns"]["havnhold"]["culture"])

    def test_the_renderer_acts_on_all_four_channels(self):
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        for hook in ("c.walls[st.wall]", "c.roofs[st.roof]",
                     "st.pitch", "st.gable", "drawCrowSteps", "hipped"):
            self.assertIn(hook, js, hook)

    def test_the_town_screen_names_it(self):
        g, _s = grown(house="hansa")
        buf = io.StringIO()
        Console(g, out=buf).do("view")
        self.assertIn("built in the Hansa", plain(buf.getvalue()))

    def test_and_the_war_screen_names_everybody_elses(self):
        g, _s = grown()
        buf = io.StringIO()
        Console(g, out=buf).do("war")
        out = plain(buf.getvalue())
        self.assertIn("the Ironhand", out)
        self.assertIn("the Abbey", out)
