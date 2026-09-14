"""The picture: where things stand, and the window that serves it.

Canvas cannot be unit tested and does not need to be. What can be tested is
everything the drawing depends on -- that the layout puts every building
somewhere, that the same town always comes out the same way, and that the
server hands the browser a state it can actually draw.
"""

import json
import random
import os
import re
import socket
import threading
import unittest
import urllib.error
import urllib.request
from io import StringIO

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from marchlands.cli import Console
from marchlands.layout import (CLAY, FIELD, FOREST, GRASS, HILL, MEN_PER_FIGURE,
                               ROAD, SOULS_PER_FIGURE, WATER, YARD, plan_for)
from marchlands.layout import POST_WHERE as layout_POST_WHERE
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
        self.assertTrue([f for f in plan.folk if f.kind != "watch"])
        s.population = 2.0
        # The watch is not townspeople: a town with nobody left in it and a
        # garrison still has men standing on the wall, which is exactly the
        # sort of thing the picture ought to keep telling you.
        self.assertFalse([f for f in plan_for(s).folk if f.kind != "watch"])

    def test_every_figure_stands_for_a_stated_number_of_real_people(self):
        """The honest answer to drawing a two-hundred-soul town: a figure is a
        sample at a ratio the interface states, doing something the aggregate
        is really doing."""
        from marchlands.layout import MEN_PER_FIGURE, SOULS_PER_FIGURE
        _g, s = grown()
        plan = plan_for(s)
        town = [f for f in plan.folk if f.kind != "watch"]
        self.assertAlmostEqual(len(town),
                               min(20, int(s.population / SOULS_PER_FIGURE)),
                               delta=1)
        watch = [f for f in plan.folk if f.kind == "watch"]
        self.assertAlmostEqual(len(watch),
                               int(sum(s.units.values()) / MEN_PER_FIGURE),
                               delta=1)

    def test_the_watch_stands_on_the_wall_it_is_holding(self):
        """Which is what makes a thinly-held wall *look* thinly held, with no
        warning, icon or number: you can see the gaps."""
        _g, s = grown()
        wall = set(s.plan().wall)
        self.assertTrue(wall)
        for f in plan_for(s).folk:
            if f.kind == "watch":
                self.assertIn((int(f.x), int(f.y)), wall)

    def test_a_worker_walks_between_a_roof_and_a_shed_that_is_running(self):
        _g, s = grown()
        workers = [f for f in plan_for(s).folk if f.kind == "worker"]
        self.assertTrue(workers)
        for f in workers:
            self.assertGreaterEqual(len(f.path), 2)
            self.assertTrue(f.at)

    def test_and_stands_in_the_street_when_there_is_no_work(self):
        _g, s = grown()
        for b in s.buildings:
            b.enabled = False
        s.tick("spring", random.Random(1))
        kinds = {f.kind for f in plan_for(s).folk}
        self.assertIn("idle", kinds)
        self.assertNotIn("worker", kinds)

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


class TestWhatIsBeingCarried(unittest.TestCase):
    """The little men with sacks, which is the thing people actually describe.

    A load exists only where something running wants what something running
    makes, so what crosses the street is what the ledger is doing.
    """

    def test_a_working_town_has_loads_on_the_move(self):
        _g, s = grown()
        self.assertTrue(plan_for(s).hauls)

    def test_every_load_goes_from_a_maker_to_a_wanter(self):
        _g, s = grown()
        plan = plan_for(s)
        at = {b.uid: b for b in plan.buildings}
        for h in plan.hauls:
            src, dst = s.find(h.frm), s.find(h.to)
            self.assertIn(h.good, src.spec.outputs, f"{src.key} does not make {h.good}")
            self.assertIn(h.good, dst.spec.inputs, f"{dst.key} does not want {h.good}")
            self.assertIn(h.frm, at)
            self.assertIn(h.to, at)

    def test_nothing_is_carried_to_a_shut_workshop(self):
        _g, s = grown()
        for b in s.buildings:
            b.enabled = False
            b.throughput = 0.0
        self.assertEqual(plan_for(s).hauls, [])

    def test_a_load_never_leaves_from_where_it_arrives(self):
        _g, s = grown()
        for h in plan_for(s).hauls:
            self.assertNotEqual(h.frm, h.to)

    def test_the_same_pair_is_not_drawn_twice_over(self):
        _g, s = grown()
        seen = [(h.frm, h.to, h.good) for h in plan_for(s).hauls]
        self.assertEqual(len(seen), len(set(seen)))

    def test_a_town_with_forty_chains_is_not_forty_carriers(self):
        _g, s = grown(days=900)
        self.assertLessEqual(len(plan_for(s).hauls), 14)

    def test_they_keep_to_the_street(self):
        """A carrier who walks the straight line spends it inside other roofs."""
        _g, s = grown()
        plan = plan_for(s)
        self.assertTrue(plan.hauls)
        walked = [h for h in plan.hauls
                  if any(plan.tile(int(x), int(y)) == ROAD for x, y in h.path[1:-1])]
        self.assertTrue(walked, "no carrier ever found a street")

    def test_a_route_starts_where_it_starts_and_ends_where_it_ends(self):
        _g, s = grown()
        plan = plan_for(s)
        at = {b.uid: b for b in plan.buildings}
        for h in plan.hauls:
            self.assertEqual(tuple(h.path[0]), (at[h.frm].x, at[h.frm].y))
            self.assertEqual(tuple(h.path[-1]), (at[h.to].x, at[h.to].y))

    def test_they_survive_the_trip_to_the_browser(self):
        _g, s = grown()
        back = json.loads(json.dumps(plan_for(s).to_dict()))
        self.assertTrue(back["hauls"])
        for h in back["hauls"]:
            self.assertIn("good", h)
            self.assertGreaterEqual(len(h["path"]), 2)


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


class TestItShips(unittest.TestCase):
    """The engine is not the whole game; the page has to be in the box.

    `pip install marchlands` shipped the Python and none of the static files,
    so `--web` served a working server and a blank screen. Nothing in the
    suite noticed, because every test ran from the source tree.
    """

    def test_the_page_and_everything_it_asks_for_are_beside_the_code(self):
        from marchlands.web import STATIC
        self.assertTrue(os.path.isdir(STATIC), STATIC)
        for name in ("index.html", "marchlands.css", "marchlands.js", "sound.js"):
            path = os.path.join(STATIC, name)
            self.assertTrue(os.path.isfile(path), name)
            self.assertGreater(os.path.getsize(path), 200, name)

    def test_the_page_asks_only_for_things_that_are_there(self):
        import re
        from marchlands.web import STATIC
        page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        wanted = [w for w in re.findall(r'(?:src|href)="([^"/][^"]*)"', page)
                  if ":" not in w.split("?")[0]]     # not a data: or http: URI
        self.assertTrue(wanted)
        for name in wanted:
            self.assertTrue(os.path.isfile(os.path.join(STATIC, name)), name)

    def test_the_page_asks_the_network_for_nothing(self):
        """No dependency list, and that includes fonts and CDNs. A game you
        can play on a train is worth more than a webfont."""
        import re
        from marchlands.web import STATIC
        page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        for url in re.findall(r'(?:src|href)="([^"]*)"', page):
            self.assertFalse(url.startswith(("http:", "https:", "//")), url)

    def test_the_tab_has_a_name_and_a_mark_of_its_own(self):
        from marchlands.web import STATIC
        page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        self.assertIn("<title>", page)
        self.assertIn('rel="icon"', page)
        self.assertIn("data:image/svg+xml,", page)    # drawn, not downloaded
        self.assertIn('name="theme-color"', page)

    def test_a_narrow_screen_still_shows_the_numbers(self):
        """The stylesheet used to answer a phone by hiding the panel, which is
        where souls, mood, hands and the wall live."""
        from marchlands.web import STATIC
        css = open(os.path.join(STATIC, "marchlands.css"), encoding="utf-8").read()
        narrow = css[css.index("@media (max-width: 720px)"):]
        self.assertNotIn("#panel { display: none", narrow)
        self.assertIn("#panel", narrow)

    def test_every_command_is_offered_with_a_line_about_itself(self):
        """The palette is built from the registry, so it cannot drift from
        what the game will accept -- and a command with no line about it is a
        command nobody will ever find."""
        from marchlands.cli import COMMANDS, catalogue
        rows = catalogue()
        # One row per command, not per spelling: aliases fold into the entry
        # they point at, so `economy` and `accounts` are one thing.
        self.assertEqual(len(rows), len(set(COMMANDS.values())))
        names = {r["name"] for r in rows} | {a for r in rows for a in r["aliases"]}
        self.assertEqual(names, set(COMMANDS))
        for row in rows:
            self.assertTrue(row["help"], f"{row['name']} says nothing about itself")
            self.assertLess(len(row["help"]), 90, row["name"])

    def test_the_first_spelling_in_the_registry_is_the_real_one(self):
        from marchlands.cli import catalogue
        by = {r["name"]: r for r in catalogue()}
        self.assertIn("economy", by)          # not "accounts"
        self.assertIn("accounts", by["economy"]["aliases"])
        self.assertIn("army", by)             # not "armies"

    def test_the_page_carries_the_palette_and_the_keys(self):
        from marchlands.web import STATIC
        page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        for bit in ('id="palette"', 'id="palette-q"', 'id="keys"',
                    'id="toasts"', 'aria-live'):
            self.assertIn(bit, page, bit)

    def test_the_light_is_laid_down_after_the_world_and_before_the_glows(self):
        """Order is the whole trick, and it is invisible when it is wrong.

        The scene is drawn in daylight colours and the hour is washed over it,
        so a hundred colours in that file stay readable as colours. Anything
        that makes its own light has to come after the wash or a lit window at
        midnight is just a slightly less dark window.
        """
        from marchlands.web import STATIC
        js = open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8").read()
        for name in ("function lightWash", "function drawGlows",
                     "function castShadow", "function turnTheSky"):
            self.assertIn(name, js, name)
        body = js[js.index("function frame()"):]
        wash = body.index("lightWash(w, h)")
        self.assertLess(body.index("drawEffects(t)"), wash)
        self.assertLess(wash, body.index("drawGlows()"))

    def test_the_renderer_still_asks_the_network_for_nothing(self):
        from marchlands.web import STATIC
        for name in ("marchlands.js", "sound.js"):
            js = open(os.path.join(STATIC, name), encoding="utf-8").read()
            for word in ("http://", "https://", "fetch('http", "import("):
                self.assertNotIn(word, js, f"{name} reaches out with {word!r}")

    def test_every_selector_the_script_reaches_for_matches_something(self):
        """A selector that matches nothing fails in silence.

        Three elements shared `id="clock"` once. Splitting them into `pace`,
        `clock` and `advance` left the handler that binds the four buttons
        under the picture -- a day, a week, a month, what now? -- querying
        `#clock button`. That id still existed; it was a `<p>` by then, with
        no buttons under it. All four did nothing for as long as that stood,
        and nothing looked wrong, because the clock goes on turning the days
        by itself and an inert button looks like one you did not quite hit.

        So checking the id exists is not enough -- it did. What has to hold
        is that the element wearing it still contains the thing being asked
        for.
        """
        from html.parser import HTMLParser
        from marchlands.web import STATIC
        js = open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8").read()
        page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()

        class Subtrees(HTMLParser):
            """Which tags sit under each id. Void elements never nest, so a
            stack that only pushes what can be closed stays honest."""
            VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                    "link", "meta", "param", "source", "track", "wbr"}

            def __init__(self):
                super().__init__()
                self.ids = {}
                self.open = []          # [(tag, id or None)]

            def handle_starttag(self, tag, attrs):
                got = dict(attrs).get("id")
                for _t, held in self.open:
                    if held:
                        self.ids[held].add(tag)
                if got:
                    self.ids.setdefault(got, set())
                if tag not in self.VOID:
                    self.open.append((tag, got))

            def handle_endtag(self, tag):
                for i in range(len(self.open) - 1, -1, -1):
                    if self.open[i][0] == tag:
                        del self.open[i:]
                        return

        seen = Subtrees()
        seen.feed(page)
        # Ids the script builds into the page as it draws are fair game too,
        # but only the ones it really writes: this test first passed a
        # reintroduced bug because the comment explaining the bug says
        # `id="clock"`, and prose about an id is not an id.
        code = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", " ", code)
        drawn = set(re.findall(r'id="([A-Za-z0-9_-]+)"', code))

        missing = []
        for holder, rest in re.findall(
                r"""querySelector(?:All)?\(['"]#([A-Za-z0-9_-]+)([^'"]*)['"]""", js):
            if holder in drawn:
                continue
            if holder not in seen.ids:
                missing.append(f"#{holder} is on nothing")
                continue
            tag = rest.strip().split()[-1] if rest.strip() else ""
            if tag and tag.isalpha() and tag not in seen.ids[holder]:
                missing.append(f"#{holder} holds no <{tag}>")
        self.assertEqual(missing, [], f"selectors that match nothing: {missing}")

        # And the four themselves, by name, because they are the ones that
        # were broken and the whole point of playing is being able to say
        # "a week passes".
        for line in ("next", "next 7", "next 30", "hint"):
            self.assertIn(f'data-do="{line}"', page, line)

    def test_the_wheel_is_told_to_carry_them(self):
        """The one line whose absence caused this, asserted directly."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        toml = open(os.path.join(root, "pyproject.toml"), encoding="utf-8").read()
        self.assertIn("[tool.setuptools.package-data]", toml)
        self.assertIn('marchlands = ["static/*"]', toml)


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

    def test_the_palette_asks_the_server_and_gets_the_registry(self):
        status, kind, body = self.get("/commands")
        self.assertEqual(status, 200)
        self.assertIn("json", kind)
        rows = json.loads(body)
        self.assertTrue(any(r["name"] == "margin" for r in rows))
        self.assertTrue(all(r["help"] for r in rows))

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


class TestTheBox(unittest.TestCase):
    """The game as something you double-click, not something you type.

    A packaged build is a different animal from a checkout: the files are
    somewhere else, there is no console to print a traceback to, and the
    person holding it has not agreed to learn a command line. Each test here
    is one of the ways that went wrong.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_the_static_files_are_found_inside_a_frozen_build(self):
        # PyInstaller unpacks a one-file build into a temporary directory and
        # points sys._MEIPASS at it. Resolving the page off __file__ -- the
        # obvious way, and the way this shipped first -- makes the exe serve a
        # blank screen from a path that does not exist on the player's disk.
        import sys as _sys
        import tempfile
        from marchlands import web
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "marchlands", "static"))
            _sys._MEIPASS = tmp
            try:
                self.assertEqual(web._static_dir(),
                                 os.path.join(tmp, "marchlands", "static"))
            finally:
                del _sys._MEIPASS
        self.assertTrue(os.path.isfile(os.path.join(web._static_dir(), "index.html")))

    def test_a_frozen_build_opens_the_drawn_game_even_when_given_a_port(self):
        # The packaged app's own error message tells a player to retry with
        # `--port 9000`. Keying "is this a double-click" off having no
        # arguments therefore dropped exactly those players into the terminal
        # game they had just chosen not to install Python for.
        source = open(os.path.join(self.ROOT, "marchlands", "__main__.py"),
                      encoding="utf-8").read()
        self.assertIn("FROZEN and not args.terminal", source)
        self.assertIn("--terminal", source)

    def test_the_recipe_packs_the_page_and_opens_no_console(self):
        spec = open(os.path.join(self.ROOT, "packaging", "marchlands.spec"),
                    encoding="utf-8").read()
        self.assertIn("static", spec)
        self.assertIn("console=False", spec)      # a window, not a terminal
        # The scenario and culture tables reach some modules by name, and
        # PyInstaller's import graph does not always follow that -- a module
        # left out is an exe that starts and then dies on a KeyError.
        for reached_by_name in ("marchlands.cartography", "marchlands.culture",
                                "marchlands.chancery"):
            self.assertIn(reached_by_name, spec)

    def test_the_launcher_says_something_when_it_cannot_start(self):
        # A windowed build has nowhere to print a traceback, so a failure is
        # an icon that does nothing at all. The launcher has to find its own
        # way to speak.
        launch = open(os.path.join(self.ROOT, "packaging", "launch.py"),
                      encoding="utf-8").read()
        self.assertIn("MessageBoxW", launch)
        self.assertIn("marchlands-error.txt", launch)

    def test_the_windows_double_click_file_has_windows_line_endings(self):
        # A .bat with bare newlines is a batch file cmd.exe reads wrong.
        raw = open(os.path.join(self.ROOT, "Marchlands.bat"), "rb").read()
        self.assertIn(b"\r\n", raw)
        # Every one of them, not just the first: cmd.exe reads a batch file
        # with bare newlines wrong, and git will happily hand one over.
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(b"--web", raw)

    def test_the_other_double_click_file_is_executable(self):
        path = os.path.join(self.ROOT, "Marchlands.command")
        self.assertTrue(os.access(path, os.X_OK), "chmod +x or nothing happens")
        self.assertIn("--web", open(path, encoding="utf-8").read())


class TestItDoesNotShareItsPort(unittest.TestCase):
    """What a player gets when something else is already on 8731.

    This was found the hard way: a Windows player double-clicked the exe and
    the browser opened on a directory listing of their own home folder. Our
    handler cannot produce a listing -- it serves four known filenames and
    404s everything else -- so the window was pointed at somebody else's
    server sharing our port.
    """

    def test_it_steps_aside_for_a_server_that_is_already_there(self):
        from marchlands.web import _Server, serve
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        taken = probe.getsockname()[1]
        probe.close()

        squatter = ThreadingHTTPServer(("127.0.0.1", taken),
                                       SimpleHTTPRequestHandler)
        self.addCleanup(squatter.server_close)
        console = Console(start("marchlands", seed=5), out=StringIO())
        server, url = serve(console, port=taken, open_browser=False)
        self.addCleanup(server.server_close)
        self.assertNotEqual(server.server_address[1], taken)
        self.assertIn(str(server.server_address[1]), url)
        self.assertIsInstance(server, _Server)

    def test_windows_is_not_allowed_to_bind_a_port_somebody_is_listening_on(self):
        # SO_REUSEADDR means two different things. On Unix it waives TIME_WAIT;
        # on Windows it waives the whole exclusion, so the bind above would
        # succeed, the walk would never run, and the two servers would split
        # the incoming connections between them.
        from marchlands.web import _Server
        self.assertEqual(_Server.allow_reuse_address, os.name != "nt")
        self.assertTrue(ThreadingHTTPServer.allow_reuse_address,
                        "the inherited default is the thing being overridden")


class TestTheFrontDoor(unittest.TestCase):
    """Starting, saving and resuming without typing a word.

    These three were console commands. That is fine for somebody who opened a
    terminal on purpose and no use at all to somebody who double-clicked an
    icon, so they are routes now as well.
    """

    def setUp(self):
        from marchlands import web
        self.web = web
        self.console = Console(start("marchlands", seed=5), out=StringIO())
        self.was = web.SHOW_FRONT

    def tearDown(self):
        self.web.SHOW_FRONT = self.was

    def door(self, route, **body):
        return self.web._front_door(self.console, route, body)

    def test_it_can_start_a_written_game(self):
        out = self.door("/new", scenario="winter_crown", house="abbey")
        self.assertNotIn("error", out)
        self.assertEqual(self.console.game.house, "abbey")
        self.assertIn("state", out)

    def test_it_can_start_on_real_country(self):
        out = self.door("/new", region="fens", house="hansa", seed=11)
        self.assertNotIn("error", out)
        self.assertEqual(self.console.game.house, "hansa")
        self.assertTrue(out["state"]["town"]["name"])

    def test_a_house_that_does_not_exist_is_a_message_not_a_crash(self):
        out = self.door("/new", scenario="marchlands", house="nonesuch")
        self.assertIn("error", out)

    def test_saving_and_resuming_come_back_to_the_same_game(self):
        path = os.path.join(self.tmp(), "front.save")
        self.door("/new", scenario="winter_crown", house="abbey", seed=3)
        keep = self.console.game.world.settlements[self.console.here].name
        self.assertTrue(self.door("/save", path=path).get("saved"))
        self.door("/new", scenario="salt_road", house="plough", seed=9)
        self.assertNotEqual(
            self.console.game.world.settlements[self.console.here].name, keep)
        out = self.door("/load", path=path)
        self.assertNotIn("error", out)
        self.assertEqual(
            self.console.game.world.settlements[self.console.here].name, keep)

    def test_resuming_nothing_is_a_message_not_a_crash(self):
        out = self.door("/load", path=os.path.join(self.tmp(), "no-such.save"))
        self.assertIn("error", out)
        self.assertTrue(self.console.game)      # and the game is still standing

    def test_the_front_door_shuts_once_somebody_has_chosen(self):
        # Otherwise a reload after starting a game asks the same question
        # again, over the top of the game it just started.
        self.web.SHOW_FRONT = True
        self.door("/new", scenario="marchlands", house="plough")
        self.assertFalse(self.web.SHOW_FRONT)

    def test_choosing_on_the_command_line_skips_the_screen_that_asks(self):
        main = open(os.path.join(TestTheBox.ROOT, "marchlands", "__main__.py"),
                    encoding="utf-8").read()
        self.assertIn("front=not chose", main)
        self.assertIn("args.scenario != \"marchlands\"", main)

    def tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return d


class TestTheFrontDoorIsOnScreen(unittest.TestCase):
    """The markup and the script have to agree about what exists.

    Every one of these is a silent failure: a button whose handler addresses
    an id that is not there throws once at load and takes the rest of the
    file's listeners with it.
    """

    @classmethod
    def setUpClass(cls):
        from marchlands.web import STATIC
        cls.page = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        cls.js = open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8").read()
        cls.css = open(os.path.join(STATIC, "marchlands.css"), encoding="utf-8").read()

    def test_every_id_the_front_door_reaches_for_is_in_the_page(self):
        wired = ("front", "front-go", "front-continue", "front-close",
                 "front-dials", "front-resume", "housepick", "wherepick",
                 "house-note", "where-note", "v-menu", "v-save", "v-load",
                 "soul", "soul-close", "soul-name", "soul-count", "soul-doing",
                 "soul-facts", "soul-said", "soul-person", "soul-age",
                 "soul-skills", "soul-posts")
        for name in wired:
            self.assertIn('id="%s"' % name, self.page, name)
            self.assertIn("'%s'" % name, self.js, name)
        self.assertIn('id="front-box"', self.page)   # styled, never addressed

    def test_the_new_buttons_take_clicks(self):
        # #bar is pointer-events: none so the sky behind it can be dragged,
        # and every control on it has to opt back in. One that does not is a
        # button the canvas swallows -- which is how `country` shipped
        # unclickable.
        opted = [line for line in self.css.splitlines()
                 if "pointer-events: auto" in line or "#ear," in line]
        rule = self.css.split("pointer-events: auto; font: 12px/1 inherit")[0]
        tail = rule.rsplit("\n", 1)[-1] + rule.rsplit("\n", 2)[-2]
        for name in ("#v-menu", "#v-save", "#v-load", "#v-draw"):
            self.assertIn(name, tail, name)
        self.assertTrue(opted)

    def test_the_door_asks_the_server_rather_than_hard_coding_the_houses(self):
        # Five houses in the page would be five houses to forget to update.
        self.assertIn("fetch('/front')", self.js)
        for key in ("plough", "hansa", "ironhand", "marcher", "abbey"):
            self.assertNotIn('data-house="%s"' % key, self.page, key)


class TestClickingSomebody(unittest.TestCase):
    """Who a figure is, when you point at one.

    The rule the whole panel is built on: nothing here is invented. A worker
    already knew the roof he sleeps under and the shed he walks to, because
    that is how his path was drawn, and the watch already knew which yard of
    wall it stands on. All that was missing was somewhere to put the answer.
    """

    @classmethod
    def setUpClass(cls):
        from marchlands import web as w
        cls.w = w
        cls.g, _s = grown(seed=5, days=300)
        cls.here = next(iter(cls.g.world.settlements))
        kin = [p for p in cls.g.kin.living() if p.grown(cls.g.day)]
        cls.g.post(kin[1].name, "master", cls.here)
        cls.officer = kin[1].name

    def plan(self):
        return plan_for(self.g.world.settlements[self.here],
                        officers=self.w._officers(self.g, self.here))

    def first(self, kind):
        for i, f in enumerate(self.plan().folk):
            if f.kind == kind:
                return i, f
        return None, None

    # ------------------------------------------------- what a figure knows
    def test_a_worker_knows_his_roof_and_his_shed(self):
        i, f = self.first("worker")
        self.assertIsNotNone(f, "a grown town with hands should have workers")
        uids = {b.uid: b for b in self.plan().buildings}
        self.assertIn(f.home, uids)
        self.assertIn(f.work, uids)
        self.assertIn(uids[f.home].key, ("cottage", "hovel", "townhouse"))
        self.assertTrue(uids[f.work].running, "walking to a shed nobody staffs")
        self.assertEqual(f.souls, SOULS_PER_FIGURE)

    def test_the_watch_stands_for_fewer_men_than_a_worker_does_souls(self):
        i, f = self.first("watch")
        if f is None:
            return self.skipTest("no garrison in this town")
        self.assertEqual(f.souls, MEN_PER_FIGURE)

    def test_one_of_yours_stands_where_you_posted_them(self):
        i, f = self.first("kin")
        self.assertIsNotNone(f, "a posted officer should be standing somewhere")
        uids = {b.uid: b for b in self.plan().buildings}
        held = self.g.kin.by_name(f.who)
        self.assertIsNotNone(held)
        self.assertIn(uids[f.work].key, layout_POST_WHERE[held.post])

    def test_the_envoy_is_not_drawn_because_he_is_not_here(self):
        # "sits with the other lords" means away. A figure of him in your own
        # square would be a lie about where he is.
        self.assertNotIn("envoy", layout_POST_WHERE)

    # ------------------------------------------------------- the dossier
    def test_it_answers_for_every_kind_of_figure(self):
        seen = set()
        for i, f in enumerate(self.plan().folk):
            if f.kind in seen:
                continue
            seen.add(f.kind)
            d = self.w.folk(self.g, self.here, i)
            self.assertNotIn("error", d, f.kind)
            self.assertTrue(d["title"], f.kind)
            self.assertTrue(d["doing"], f.kind)
            self.assertTrue(d["facts"], f.kind)
        self.assertIn("worker", seen)
        self.assertIn("kin", seen)

    def test_pointing_at_nobody_is_a_message_not_a_crash(self):
        self.assertIn("error", self.w.folk(self.g, self.here, 9999))
        self.assertIn("error", self.w.folk(self.g, self.here, -1))

    def test_a_worker_is_told_what_he_makes_and_what_he_eats(self):
        i, _ = self.first("worker")
        d = self.w.folk(self.g, self.here, i)
        keys = {f["k"] for f in d["facts"]}
        self.assertIn("makes", keys)
        self.assertIn("eating", keys)
        self.assertTrue(d["home"], "he sleeps somewhere and it should say where")

    def test_one_of_yours_is_a_person_rather_than_a_sample(self):
        i, _ = self.first("kin")
        d = self.w.folk(self.g, self.here, i)
        self.assertEqual(d["souls"], 1)
        self.assertIn("person", d)
        self.assertGreater(d["person"]["age"], 0)
        self.assertTrue(d["posts"])

    # --------------------------------------------- the jobs, and their where
    def test_a_post_that_needs_a_town_is_offered_the_town_you_are_looking_at(self):
        # `post X steward` with no town resolves to whichever settlement comes
        # first in the dictionary, which is not the one on screen. The panel
        # has to send the target or the button quietly does the wrong thing.
        i, _ = self.first("kin")
        offer = {p["key"]: p for p in self.w.folk(self.g, self.here, i)["posts"]}
        for key in ("steward", "master"):
            self.assertEqual(offer[key]["needs"], "town", key)
            self.assertEqual(offer[key]["target"], self.here, key)
            self.assertTrue(offer[key]["can"], key)

    def test_a_post_with_nowhere_to_stand_is_offered_but_not_clickable(self):
        i, _ = self.first("kin")
        offer = {p["key"]: p for p in self.w.folk(self.g, self.here, i)["posts"]}
        cap = offer["captain"]
        self.assertEqual(cap["needs"], "host")
        has_host = any(a.owner == "player" for a in self.g.armies)
        self.assertEqual(cap["can"], has_host)
        if not has_host:
            self.assertTrue(cap["why"], "a dead button should say why")

    def test_the_command_the_button_sends_actually_works(self):
        # The panel is a shortcut for `post`, not a second way of doing it.
        i, f = self.first("kin")
        d = self.w.folk(self.g, self.here, i)
        offer = {p["key"]: p for p in d["posts"]}["steward"]
        first_name = d["person"]["name"].split()[0]
        said = self.g.post(first_name, "steward", offer["target"])
        self.assertNotIn("nobody of yours", said)
        self.assertNotIn("no settlement", said)
        who = self.g.kin.by_name(first_name)
        self.assertEqual(who.post, "steward")
        self.assertEqual(who.target, self.here)
        self.g.post(first_name, "master", self.here)      # put it back

    # ------------------------------------------------------ the old rule
    def test_asking_who_somebody_is_does_not_move_the_dice(self):
        """Fifth time. The kin moved the weather, the league re-rolled twelve
        seeds of balance measurement, the voices and the chancery each did it
        once more. A panel that opens on a click and names a household is the
        same shape of mistake."""
        before = self.g.rng.getstate()
        for i in range(min(12, len(self.plan().folk))):
            self.w.folk(self.g, self.here, i)
        self.assertEqual(before, self.g.rng.getstate(),
                         "clicking a villager re-rolled the campaign")

    def test_the_same_person_is_the_same_person_while_you_look_at_them(self):
        i, _ = self.first("worker")
        once = self.w.folk(self.g, self.here, i)
        twice = self.w.folk(self.g, self.here, i)
        self.assertEqual(once["title"], twice["title"])
        self.assertEqual(once["said"], twice["said"],
                         "a second click would be a different person")

    def test_two_figures_out_of_the_same_door_are_the_same_family(self):
        plan = self.plan()
        byroof = {}
        for i, f in enumerate(plan.folk):
            if f.kind == "worker" and f.home >= 0:
                byroof.setdefault(f.home, []).append(i)
        shared = [v for v in byroof.values() if len(v) > 1]
        if not shared:
            return self.skipTest("nobody shares a roof in this town")
        names = {self.w.folk(self.g, self.here, i)["title"] for i in shared[0]}
        self.assertEqual(len(names), 1, "a house does not rename itself")


class TestThePlanIsTheSamePlanTomorrow(unittest.TestCase):
    """The layout promises determinism in its own docstring, and `hash()` of
    a str is salted per process -- so the idle folk it seeded stood in
    slightly different places every time the program started. That was
    cosmetic until a figure's place in the list became a click target."""

    def test_the_same_town_lays_out_the_same_way_in_a_fresh_process(self):
        import subprocess
        import sys as _sys
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from marchlands.scenarios import start\n"
            "from marchlands.sim import Bot\n"
            "from marchlands.layout import plan_for\n"
            "g = start('marchlands', seed=5); Bot(g).run(120)\n"
            "s = g.world.settlements[next(iter(g.world.settlements))]\n"
            "p = plan_for(s)\n"
            "print([(round(f.x, 6), round(f.y, 6), f.kind) for f in p.folk])\n"
        ) % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        runs = []
        for salt in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=salt)
            out = subprocess.run([_sys.executable, "-c", code], env=env,
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr[-400:])
            runs.append(out.stdout.strip())
        self.assertEqual(runs[0], runs[1],
                         "the town moved between two runs of the program")


class TestHostsOnTheMap(unittest.TestCase):
    """A host crossing the country was the one thing happening on the march
    map that the map did not show. Yours in full; theirs only as far as you
    can see, because drawing every enemy army where it really is would
    quietly delete the fog of war, and the fog is most of what makes a march
    tense."""

    def setUp(self):
        from marchlands.military import Army, BESIEGING
        self.Army, self.BESIEGING = Army, BESIEGING
        self.g, _s = grown(seed=5, days=420)
        self.here = next(iter(self.g.world.settlements))
        self.g.world.settlements[self.here].units.update(
            {"spearman": 60, "archer": 30})
        self.g.raise_host(self.here, {"spearman": 30, "archer": 15})
        self.mine = self.g.armies[-1]
        self.foe = next(k for k, t in self.g.world.towns.items() if not t.mine)

    def hosts(self):
        from marchlands.web import march as march_map
        return {h["uid"]: h for h in march_map(self.g, self.here)["hosts"]}

    def test_your_own_host_is_on_the_map_with_what_it_costs(self):
        h = self.hosts()[self.mine.uid]
        self.assertTrue(h["mine"])
        self.assertEqual(h["size"], 45)
        self.assertGreater(h["upkeep"], 0)
        self.assertEqual(h["units"], {"spearman": 30, "archer": 15})

    def test_the_captain_you_posted_is_named_on_his_host(self):
        who = [p for p in self.g.kin.living() if p.grown(self.g.day)][1]
        self.g.post(who.name, "captain", str(self.mine.uid))
        self.assertEqual(self.hosts()[self.mine.uid]["captain"], who.name)

    def test_a_host_you_have_never_seen_is_not_on_your_map(self):
        self.g.armies.append(self.Army(uid=901, name="x", owner=self.foe,
                                       units={"spearman": 20}, at=self.foe))
        self.g._look_around()
        self.assertNotIn(901, self.hosts(), "that is a live enemy tracker")

    def test_a_host_on_your_doorstep_is_seen(self):
        self.g.armies.append(self.Army(uid=902, name="y", owner=self.foe,
                                       units={"spearman": 25}, at=self.here,
                                       state=self.BESIEGING))
        self.g._look_around()
        h = self.hosts()[902]
        self.assertFalse(h["mine"])
        self.assertEqual(h["state"], "besieging")
        self.assertEqual(h["stale"], 0)
        self.assertEqual(h["units"], {}, "you do not get their order of battle")
        self.assertEqual(h["upkeep"], 0, "nor their books")

    def test_once_it_leaves_it_is_a_memory_with_a_date_on_it(self):
        self.g.armies.append(self.Army(uid=903, name="z", owner=self.foe,
                                       units={"spearman": 25}, at=self.here,
                                       state=self.BESIEGING))
        self.g._look_around()
        seen_at = self.hosts()[903]["at"]
        self.g.armies[-1].at = self.foe          # it marched off
        self.g.day += 9
        self.g._look_around()
        h = self.hosts()[903]
        self.assertEqual(h["state"], "remembered")
        self.assertEqual(h["stale"], 9)
        self.assertEqual(h["at"], seen_at, "a memory is of where it was")

    def test_what_you_remember_is_the_strength_you_saw(self):
        self.g.armies.append(self.Army(uid=904, name="w", owner=self.foe,
                                       units={"spearman": 25}, at=self.here,
                                       state=self.BESIEGING))
        self.g._look_around()
        self.g.armies[-1].units = {"spearman": 90}   # they reinforced, unseen
        self.g.armies[-1].at = self.foe
        self.g.day += 3
        self.g._look_around()
        self.assertEqual(self.hosts()[904]["size"], 25,
                         "you cannot count men you did not see")

    def test_a_sighting_survives_being_saved_and_loaded(self):
        import tempfile
        self.g.armies.append(self.Army(uid=905, name="v", owner=self.foe,
                                       units={"spearman": 25}, at=self.here,
                                       state=self.BESIEGING))
        self.g._look_around()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            self.g.save(path)
            back = type(self.g).load(path)
        a = next(x for x in back.armies if x.uid == 905)
        self.assertEqual(a.seen_day, self.g.day)
        self.assertEqual(a.seen_size, 25)


class TestTheCountersAreSayable(unittest.TestCase):
    """A rock-paper-scissors nobody can see is a dice roll with extra
    arithmetic. The counters have decided every battle since the first one
    and the game had never once mentioned them."""

    def test_it_is_the_same_sum_the_battle_uses(self):
        # Not a rating invented for the display: the number shown is the
        # multiplier `_damage` will apply.
        from marchlands.military import Side, UNITS, matchup
        mine, theirs = {"spearman": 40}, {"knight": 20, "man_at_arms": 30}
        shares = Side(dict(theirs)).class_share()
        u = UNITS["spearman"]
        expect = sum(s * u.counters.get(c, 1.0) for c, s in shares.items())
        self.assertAlmostEqual(matchup(mine, theirs)[0]["worth"],
                               round(expect, 2), places=2)

    def test_spears_are_worth_more_against_horse(self):
        from marchlands.military import matchup
        horse = matchup({"spearman": 30}, {"knight": 30})[0]["worth"]
        foot = matchup({"spearman": 30}, {"man_at_arms": 30})[0]["worth"]
        self.assertGreater(horse, foot)
        self.assertGreater(horse, 1.0)

    def test_the_best_of_yours_comes_first(self):
        from marchlands.military import matchup
        rows = matchup({"spearman": 30, "archer": 30}, {"knight": 40})
        self.assertEqual(rows[0]["key"], "spearman")

    def test_a_host_with_no_advantage_is_warned_about_theirs(self):
        # A shrug is no use. What has the better of you is the thing worth
        # saying, and it is the same sum the other way round.
        from marchlands.military import counter_note
        said = counter_note({"archer": 50}, {"knight": 40})
        self.assertIn("nothing of yours", said)
        self.assertIn("knights", said)

    def test_an_even_fight_says_so(self):
        from marchlands.military import counter_note
        self.assertIn("straight fight",
                      counter_note({"spearman": 30}, {"spearman": 30}))

    def test_it_ignores_units_you_have_fewer_than_one_of(self):
        from marchlands.military import matchup
        self.assertEqual(matchup({"spearman": 0.4}, {"knight": 10}), [])

    def test_every_house_has_a_unit_of_its_own(self):
        # The civilisations borrowed from AOE2 are not only architecture.
        from marchlands.military import UNITS
        from marchlands.tech import HOUSES
        gated = {u.needs_tech for u in UNITS.values() if u.needs_tech}
        for house in HOUSES:
            self.assertIn(house, gated, f"{house} has no unit of its own")


class TestTheMatchupRespectsTheFog(unittest.TestCase):
    """Costing a battle off the enemy's true muster would be reading their
    books. It is costed off what you last saw, like everything else."""

    def setUp(self):
        self.g, _s = grown(seed=5, days=420)
        self.here = next(iter(self.g.world.settlements))
        self.g.world.settlements[self.here].units.update(
            {"spearman": 60, "archer": 30})
        self.g.raise_host(self.here, {"spearman": 30, "archer": 15})
        self.a = self.g.armies[-1]
        self.foe = next(k for k, t in self.g.world.towns.items() if not t.mine)

    def mine(self):
        from marchlands.web import march as march_map
        return [h for h in march_map(self.g, self.here)["hosts"] if h["mine"]][0]

    def test_a_marching_host_is_costed_against_where_it_is_going(self):
        from marchlands.web import _matchup_for
        self.g.march(self.a.uid, self.foe)
        self.assertEqual(_matchup_for(self.g, self.a),
                         __import__("marchlands.military", fromlist=["matchup"]).matchup(
                             self.a.units, self.g.believed_host(self.foe)))
        self.assertTrue(self.mine()["matchup"])

    def test_it_reads_what_you_believe_rather_than_what_is_true(self):
        # Scaling their muster is not the test it looks like: the matchup is
        # built from class *shares*, so a host six times the size in the same
        # proportions is the same matchup, correctly. What matters is which
        # figure it asks for -- the believed host, never the real muster.
        from marchlands import web
        from marchlands.military import matchup
        self.g.march(self.a.uid, self.foe)
        asked = []
        real = self.g.believed_host

        def spy(key):
            asked.append(key)
            return {"knight": 30.0}           # nothing like the true muster

        self.g.believed_host = spy
        try:
            got = web._matchup_for(self.g, self.a)
        finally:
            self.g.believed_host = real
        self.assertEqual(asked, [self.foe])
        self.assertEqual(got, matchup(self.a.units, {"knight": 30.0}))
        self.assertNotEqual(got, matchup(self.a.units,
                                         self.g.likely_host(self.foe)))

    def test_a_host_of_different_kinds_is_a_different_matchup(self):
        from marchlands.military import matchup
        horse = matchup(self.a.units, {"knight": 30})
        foot = matchup(self.a.units, {"man_at_arms": 30})
        self.assertNotEqual(horse, foot)

    def test_a_place_you_have_never_seen_says_so(self):
        from marchlands.web import _matchup_note
        town = self.g.world.towns[self.foe]
        town.seen_day, town.seen = -1, {}
        self.g.march(self.a.uid, self.foe)
        self.assertIn("never looked", _matchup_note(self.g, self.a))

    def test_a_host_standing_at_home_is_not_costed_against_anything(self):
        from marchlands.web import _matchup_for
        self.assertEqual(_matchup_for(self.g, self.a), [])

    def test_their_hosts_carry_no_matchup_of_yours(self):
        from marchlands.military import Army
        self.g.armies.append(Army(uid=960, name="x", owner=self.foe,
                                  units={"spearman": 25}, at=self.here))
        self.g._look_around()
        from marchlands.web import march as march_map
        theirs = [h for h in march_map(self.g, self.here)["hosts"]
                  if not h["mine"]][0]
        self.assertEqual(theirs["matchup"], [])
        self.assertEqual(theirs["note"], "")


if __name__ == "__main__":
    unittest.main()
