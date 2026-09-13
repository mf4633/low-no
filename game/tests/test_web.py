"""The picture: where things stand, and the window that serves it.

Canvas cannot be unit tested and does not need to be. What can be tested is
everything the drawing depends on -- that the layout puts every building
somewhere, that the same town always comes out the same way, and that the
server hands the browser a state it can actually draw.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from io import StringIO

from marchlands.cli import Console
from marchlands.layout import (CLAY, FIELD, FOREST, GRASS, HILL, ROAD, WATER,
                               YARD, plan_for)
from marchlands.scenarios import start
from marchlands.settlement import BuildingInstance
from marchlands.sim import Bot
from marchlands.web import (Handler, march, options, run_command, serve,
                            snapshot)


def grown(seed=3, days=600, scenario="marchlands"):
    g = start(scenario, seed=seed)
    Bot(g).run(days)
    return g, g.world.settlements[next(iter(g.world.settlements))]


class TestLayout(unittest.TestCase):
    def test_every_building_gets_a_place_to_stand(self):
        _g, s = grown()
        plan = plan_for(s)
        self.assertEqual(len(plan.buildings), len(s.buildings))
        self.assertEqual(len({b.uid for b in plan.buildings}), len(s.buildings))

    def test_nothing_stands_off_the_edge_of_the_map(self):
        _g, s = grown()
        plan = plan_for(s)
        for b in plan.buildings:
            self.assertTrue(0 <= b.x < plan.w and 0 <= b.y < plan.h, b.key)
        for x, y, _kind in plan.walls:
            self.assertTrue(0 <= x < plan.w and 0 <= y < plan.h)

    def test_the_same_town_is_drawn_the_same_way_twice(self):
        _g, s = grown()
        a, b = plan_for(s), plan_for(s)
        self.assertEqual(a.tiles, b.tiles)
        self.assertEqual([x.to_dict() for x in a.buildings],
                         [x.to_dict() for x in b.buildings])

    def test_the_country_is_laid_out_by_what_the_land_is(self):
        _g, s = grown()
        kinds = {t for row in plan_for(s).tiles for t in row}
        for want in (GRASS, FIELD, FOREST, HILL, CLAY, ROAD, YARD):
            self.assertIn(want, kinds, want)

    def test_a_moat_puts_water_round_the_wall(self):
        _g, s = grown()
        s.buildings = [b for b in s.buildings if b.key != "moat"]   # it dug one
        dry = sum(row.count(WATER) for row in plan_for(s).tiles)
        s.buildings.append(BuildingInstance(uid=9999, key="moat", days_left=0))
        wet = sum(row.count(WATER) for row in plan_for(s).tiles)
        self.assertGreater(wet, dry)

    def test_the_precinct_is_inside_the_map_with_room_for_its_wall(self):
        _g, s = grown()
        plan = plan_for(s)
        x0, y0, x1, y1 = plan.precinct
        self.assertGreaterEqual(x0 - 2, 0)
        self.assertGreaterEqual(y0 - 2, 0)
        self.assertLess(x1 + 2, plan.w)
        self.assertLess(y1 + 2, plan.h)

    def test_a_wall_makes_a_closed_ring(self):
        _g, s = grown()
        plan = plan_for(s)
        self.assertTrue(plan.walls)
        x0, y0, x1, y1 = plan.precinct
        want = 2 * (x1 - x0 + 3) + 2 * (y1 - y0 + 3) - 4
        self.assertEqual(len(plan.walls), want)

    def test_an_empty_holding_still_draws(self):
        g = start("marchlands", seed=5)
        s = g.world.settlements["aldworth"]
        s.buildings.clear()
        plan = plan_for(s)
        self.assertEqual(plan.buildings, [])
        self.assertEqual(plan.walls, [])
        self.assertGreater(plan.w, 4)

    def test_a_building_whose_ground_is_missing_is_not_quietly_dropped(self):
        g = start("marchlands", seed=5)
        s = g.world.settlements["aldworth"]
        s.terrain["hills"] = 0
        s.buildings.append(BuildingInstance(uid=8888, key="quarry", days_left=0))
        plan = plan_for(s)
        self.assertIn(8888, {b.uid for b in plan.buildings})

    def test_a_coast_gets_a_sea(self):
        _g, s = grown(scenario="salt_road")
        self.assertTrue(any(WATER in row for row in plan_for(s).tiles))

    def test_the_streets_have_people_on_them_when_the_town_does(self):
        _g, s = grown()
        plan = plan_for(s)
        self.assertTrue(plan.folk)
        s.population = 2.0
        self.assertFalse(plan_for(s).folk)

    def test_it_says_which_workshops_are_running(self):
        _g, s = grown()
        plan = plan_for(s)
        self.assertTrue(any(b.running for b in plan.buildings))
        self.assertTrue(all(not (b.running and b.idle) for b in plan.buildings))

    def test_a_burning_roof_is_marked_as_one(self):
        _g, s = grown()
        uid = next(b.uid for b in s.buildings if b.complete)
        s.fires.light(uid)
        burning = [b for b in plan_for(s).buildings if b.burning]
        self.assertEqual([b.uid for b in burning], [uid])

    def test_it_serialises_to_something_a_browser_can_read(self):
        _g, s = grown()
        raw = json.dumps(plan_for(s).to_dict())
        back = json.loads(raw)
        self.assertEqual(len(back["buildings"]), len(s.buildings))
        self.assertIn("precinct", back)


class TestSnapshot(unittest.TestCase):
    def test_it_carries_what_the_picture_needs(self):
        g, _s = grown()
        snap = snapshot(g)
        for key in ("day", "season", "treasury", "town", "plan", "ledger", "lord"):
            self.assertIn(key, snap)
        for key in ("population", "popularity", "wall_hp", "soldiers", "mood"):
            self.assertIn(key, snap["town"])

    def test_all_of_it_is_json(self):
        g, _s = grown()
        json.dumps(snapshot(g))          # raises if anything is not serialisable

    def test_it_reports_trouble_so_the_page_can_show_it(self):
        g, s = grown()
        s.besieged = True
        s.kindle(__import__("random").Random(1), 2)
        snap = snapshot(g)
        self.assertTrue(snap["town"]["besieged"])
        self.assertEqual(snap["town"]["fires"], 2)


class TestTheMarch(unittest.TestCase):
    """The trade layer, which is the point of the game and was invisible."""

    def test_every_place_on_the_map_is_on_the_map(self):
        g, _s = grown()
        m = march(g, "aldworth")
        keys = {n["key"] for n in m["nodes"]}
        for key in list(g.world.settlements) + list(g.world.towns) + \
                list(g.world.shrines):
            self.assertIn(key, keys, key)

    def test_it_says_what_each_place_is(self):
        g, _s = grown()
        kinds = {n["kind"] for n in march(g, "aldworth")["nodes"]}
        self.assertIn("mine", kinds)
        self.assertIn("town", kinds)
        self.assertIn("shrine", kinds)

    def test_prices_are_for_the_good_you_asked_about(self):
        g, _s = grown()
        bread = {n["key"]: n["price"] for n in march(g, "aldworth", "bread")["nodes"]}
        iron = {n["key"]: n["price"] for n in march(g, "aldworth", "iron")["nodes"]}
        self.assertNotEqual(bread, iron)
        town = next(k for k in g.world.towns)
        self.assertAlmostEqual(bread[town], g.world.towns[town].market.bid("bread"), 1)

    def test_a_town_you_never_visited_says_so(self):
        g, _s = grown(days=200)
        unseen = [n for n in march(g, "aldworth")["nodes"]
                  if n["kind"] == "town" and n["known"] < 0]
        self.assertTrue(unseen, "the fog is not reaching the map")

    def test_carts_report_where_they_have_got_to(self):
        g, _s = grown()
        carts = march(g, "aldworth")["carts"]
        self.assertEqual(len(carts), len(g.caravans))
        for c in carts:
            self.assertGreaterEqual(c["done"], 0.0)
            self.assertLessEqual(c["done"], 1.0)
            self.assertLessEqual(c["load"], c["capacity"])

    def test_a_cart_standing_still_is_not_pretending_to_move(self):
        g, _s = grown()
        for c in g.caravans:
            c.bound_for = ""
            c.days_left = 0.0
        for c in march(g, "aldworth")["carts"]:
            self.assertFalse(c["moving"])
            self.assertEqual(c["done"], 0.0)

    def test_it_names_the_runs_worth_making(self):
        g, _s = grown()
        runs = march(g, "aldworth")["runs"]
        self.assertTrue(runs)
        self.assertEqual(runs, sorted(runs, key=lambda r: -r["per_day"]))
        for r in runs:
            self.assertIn(r["from"], g.world.coords)
            self.assertIn(r["to"], g.world.coords)

    def test_the_map_still_draws_when_the_scan_finds_nothing(self):
        g, _s = grown()
        import marchlands.web as web
        import marchlands.advisor as advisor
        was = advisor.scan
        advisor.scan = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no"))
        try:
            m = web.march(g, "aldworth")
        finally:
            advisor.scan = was
        self.assertEqual(m["runs"], [])
        self.assertTrue(m["nodes"])

    def test_all_of_it_is_json(self):
        g, _s = grown()
        json.dumps(march(g, "aldworth"))


class TestWhatYouCanDo(unittest.TestCase):
    """The page asks what is possible; it never decides."""

    def test_it_offers_every_building_in_the_game(self):
        from marchlands.buildings import BUILDINGS
        g, _s = grown()
        o = options(g, "aldworth")
        self.assertEqual({b["key"] for b in o["buildings"]}, set(BUILDINGS))

    def test_what_you_cannot_raise_says_why_not(self):
        g, _s = grown()
        for b in options(g, "aldworth")["buildings"]:
            if not b["can"]:
                self.assertTrue(b["why"], b["key"])

    def test_it_agrees_with_the_engine_about_every_one(self):
        """If these ever disagree the page offers something the game refuses."""
        g, _s = grown(days=60)
        for b in options(g, "aldworth")["buildings"]:
            ok, _why = g.world.settlements["aldworth"].can_build(b["key"], g.progress)
            afford = g.treasury >= b["coin"]
            self.assertEqual(b["can"], ok and afford, b["key"])

    def test_an_empty_purse_is_a_reason(self):
        g, _s = grown()
        g.treasury = 0.0
        pricey = [b for b in options(g, "aldworth")["buildings"] if b["coin"] > 0]
        self.assertTrue(pricey)
        for b in pricey:
            self.assertFalse(b["can"])

    def test_what_you_can_raise_comes_first(self):
        g, _s = grown(days=60)
        can = [b["can"] for b in options(g, "aldworth")["buildings"]]
        self.assertEqual(can, sorted(can, reverse=True))

    def test_it_reports_the_room_left_on_each_kind_of_ground(self):
        g, s = grown()
        slots = options(g, "aldworth")["slots"]
        for terrain, free in slots.items():
            self.assertEqual(free, s.slots_free(terrain), terrain)

    def test_all_of_it_is_json(self):
        g, _s = grown()
        json.dumps(options(g, "aldworth"))


class TestWhatTravelsAndWhatDoesNot(unittest.TestCase):
    """Prices are public; strength is not. Saying both in one breath read as a
    contradiction on the map -- a town labelled never visited, quoting a price."""

    def test_a_price_is_known_everywhere(self):
        g, _s = grown(days=200)
        for n in march(g, "aldworth")["nodes"]:
            if n["kind"] == "town":
                self.assertGreater(n["price"], 0.0, n["name"])

    def test_strength_is_only_known_where_you_have_been(self):
        g, _s = grown(days=200)
        towns = [n for n in march(g, "aldworth")["nodes"] if n["kind"] == "town"]
        unseen = [n for n in towns if n["known"] < 0]
        self.assertTrue(unseen, "nothing was left unvisited to test with")
        for n in unseen:
            self.assertIsNone(n["host"])
            self.assertIsNone(n["walls"])
        for n in towns:
            if n["known"] >= 0:
                self.assertIsNotNone(n["host"], n["name"])


class TestCommandBridge(unittest.TestCase):
    def test_a_command_runs_and_its_words_come_back(self):
        g, _s = grown(days=30)
        con = Console(g, out=StringIO())
        said = run_command(con, "status")
        self.assertIn("net worth", said)

    def test_the_console_is_left_where_it_was_found(self):
        g, _s = grown(days=30)
        buf = StringIO()
        con = Console(g, out=buf)
        run_command(con, "status")
        self.assertIs(con.out, buf)

    def test_an_empty_line_does_nothing(self):
        g, _s = grown(days=30)
        con = Console(g, out=StringIO())
        self.assertEqual(run_command(con, "   "), "")

    def test_a_command_that_fails_does_not_bring_the_page_down(self):
        g, _s = grown(days=30)
        con = Console(g, out=StringIO())
        said = run_command(con, "build nonsense")
        self.assertTrue(said.strip())


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        g = start("marchlands", seed=5)
        Bot(g).run(120)
        cls.console = Console(g, out=StringIO())
        cls.server, cls.url = serve(cls.console, port=0, open_browser=False)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        Handler.console = None

    def get(self, path):
        with urllib.request.urlopen(self.url.rstrip("/") + path) as r:
            return r.status, r.headers["Content-Type"], r.read()

    def test_it_serves_the_page_and_what_the_page_asks_for(self):
        for path, kind in (("/", "text/html"), ("/marchlands.js", "text/javascript"),
                           ("/marchlands.css", "text/css")):
            status, ctype, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(kind, ctype, path)
            self.assertTrue(body)

    def test_the_state_is_the_state(self):
        _s, _c, body = self.get("/state")
        snap = json.loads(body)
        self.assertEqual(snap["day"], self.console.game.day)
        self.assertTrue(snap["plan"]["buildings"])

    def test_the_march_is_served_too(self):
        _s, _c, body = self.get("/march?good=wheat")
        m = json.loads(body)
        self.assertEqual(m["good"], "wheat")
        self.assertTrue(m["nodes"])

    def test_what_can_be_raised_is_served_too(self):
        _s, _c, body = self.get("/options")
        o = json.loads(body)
        self.assertTrue(o["buildings"])
        self.assertIn("slots", o)

    def test_the_chronicle_is_readable_from_the_page(self):
        _s, _c, body = self.get("/chronicle")
        self.assertIn("entries", json.loads(body))

    def test_a_command_posted_from_the_page_advances_the_game(self):
        before = self.console.game.day
        req = urllib.request.Request(
            self.url + "do", method="POST",
            data=json.dumps({"line": "next 2"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            out = json.loads(r.read())
        self.assertGreater(self.console.game.day, before)
        self.assertEqual(out["state"]["day"], self.console.game.day)
        self.assertTrue(out["said"].strip())

    def test_rubbish_posted_at_it_is_refused_politely(self):
        req = urllib.request.Request(
            self.url + "do", method="POST", data=b"not json at all",
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 400)

    def test_it_does_not_serve_things_that_are_not_there(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nothing.js")
        self.assertEqual(caught.exception.code, 404)

    def test_it_will_not_be_talked_into_serving_the_rest_of_the_disk(self):
        for probe in ("/../engine.py", "/%2e%2e/engine.py", "/../../etc/passwd"):
            try:
                status, _c, body = self.get(probe)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404, probe)
                continue
            self.assertNotIn(b"import", body, probe)


if __name__ == "__main__":
    unittest.main()
