"""Sending hands by name -- the thing a click on a figure can honestly do.

A figure in the picture is eight hands at a shed. Boxing three of them and
right-clicking the mill means "put twenty-four hands at the mill", and the
engine's word for that is a pin: a floor under the queue that `work` orders.
These tests are about the pin being real -- seated ahead of the bands, capped
at what the shed can use, undone cleanly, saved, and visible in the picture.
"""
import io
import pathlib
import unittest

from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.layout import plan_for
from marchlands.scenarios import start

STATIC = pathlib.Path(__file__).resolve().parents[1] / "marchlands" / "static"


def short_of_hands(st):
    """Make the town's hands fewer than its jobs, and seat them."""
    st.units = {}
    st.population = 30.0
    while st.workforce >= st.jobs_offered and st.population > 2:
        st.population -= 2
    while st.workforce < 2:
        st.population += 2
    st._seat_hands()
    assert 2 <= st.workforce < st.jobs_offered, (st.workforce, st.jobs_offered)


def starved(st):
    """The shed at the back of the queue, which got nothing."""
    sheds = [b for b in st.buildings if b.complete and b.enabled and b.spec.jobs]
    return next(b for b in sorted(sheds, key=lambda b: (st.band(b.key), -b.uid))
                if b.staffed < b.spec.jobs)


class TestPins(unittest.TestCase):
    def setUp(self):
        self.g = start("marchlands", seed=3)
        self.key = next(iter(self.g.world.settlements))
        self.st = self.g.world.settlements[self.key]
        short_of_hands(self.st)

    def test_a_pin_is_seated_ahead_of_the_queue(self):
        st = self.st
        b = starved(st)
        before = {x.uid: x.staffed for x in st.buildings}
        total = sum(before.values())
        said = st.pin_hands(b.uid, b.spec.jobs)
        self.assertIn("pinned", said)
        self.assertEqual(b.staffed, b.spec.jobs)
        # Hands are conserved: what the back of the queue got, the front lost.
        self.assertEqual(sum(x.staffed for x in st.buildings), total)
        self.assertTrue(any(x.staffed < before[x.uid] for x in st.buildings))

    def test_a_pin_is_capped_at_what_the_shed_can_use(self):
        b = starved(self.st)
        said = self.st.pin_hands(b.uid, 99)
        self.assertIn("all it can use", said)
        self.assertEqual(self.st.pins[b.uid], b.spec.jobs)

    def test_freeing_the_pin_puts_the_queue_back(self):
        st = self.st
        before = {x.uid: x.staffed for x in st.buildings}
        b = starved(st)
        st.pin_hands(b.uid, b.spec.jobs)
        said = st.pin_hands(b.uid, 0)
        self.assertIn("back into the queue", said)
        self.assertEqual(st.pins, {})
        self.assertEqual({x.uid: x.staffed for x in st.buildings}, before)
        self.assertIn("nobody was pinned", st.pin_hands(b.uid, 0))

    def test_the_newest_pin_outranks_the_older(self):
        st = self.st
        while st.workforce > 1:
            st.population -= 1
        st._seat_hands()
        self.assertEqual(st.workforce, 1)
        ones = [b for b in st.buildings if b.complete and b.spec.jobs == 1][:2]
        self.assertEqual(len(ones), 2, "the town needs two one-hand sheds for this")
        st.pin_hands(ones[0].uid, 1)
        st.pin_hands(ones[1].uid, 1)
        self.assertEqual(list(st.pins)[0], ones[1].uid)
        self.assertEqual((ones[1].staffed, ones[0].staffed), (1, 0))

    def test_a_pin_refuses_what_makes_no_sense(self):
        st = self.st
        self.assertEqual(st.pin_hands(9999, 3), "no such building")
        roof = next(b for b in st.buildings if not b.spec.jobs)
        self.assertIn("no work for hands", st.pin_hands(roof.uid, 3))
        b = starved(st)
        b.enabled = False
        self.assertIn("closed", st.pin_hands(b.uid, 1))
        b.enabled = True

    def test_pins_survive_save_and_load(self):
        st = self.st
        b = starved(st)
        st.pin_hands(b.uid, b.spec.jobs)
        g2 = GameState.from_dict(self.g.to_dict())
        st2 = g2.world.settlements[self.key]
        self.assertEqual(st2.pins, st.pins)
        st2.units = {}
        st2.population = st.population
        st2._seat_hands()
        self.assertEqual({x.uid: x.staffed for x in st2.buildings},
                         {x.uid: x.staffed for x in st.buildings})

    def test_pulling_the_shed_down_drops_the_pin(self):
        b = starved(self.st)
        self.st.pin_hands(b.uid, 1)
        self.st.demolish(b.uid)
        self.assertNotIn(b.uid, self.st.pins)

    def test_the_figure_walks_to_the_pinned_shed(self):
        st = self.st
        b = starved(st)
        self.assertFalse(any(f.work == b.uid and f.kind == "worker"
                             for f in plan_for(st).folk))
        st.pin_hands(b.uid, b.spec.jobs)
        self.assertTrue(any(f.work == b.uid and f.kind == "worker"
                            for f in plan_for(st).folk))

    def test_the_console_speaks_it(self):
        st = self.st
        b = starved(st)
        buf = io.StringIO()
        con = Console(self.g, out=buf)
        con.do(f"staff {b.uid} {b.spec.jobs}")
        con.do("staff")
        con.do(f"staff {b.uid} lots")
        con.do(f"pin {b.uid} free")
        text = buf.getvalue()
        self.assertIn("pinned at", text)
        self.assertIn("PINNED HANDS", text)
        self.assertIn("not a number", text)
        self.assertIn("back into the queue", text)

    def test_the_picture_carries_the_pin(self):
        from marchlands import web
        rows = web.snapshot(self.g, self.key)["margin"]
        uid = next(u for u, r in rows.items() if r["jobs"])
        self.st.pin_hands(uid, 1)
        rows = web.snapshot(self.g, self.key)["margin"]
        self.assertEqual(rows[uid]["pinned"], 1)


class TestControls(unittest.TestCase):
    """The client speaks the same commands, and the keys card says how."""

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text(encoding="utf-8")
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_a_right_click_is_the_order(self):
        self.assertIn("addEventListener('contextmenu'", self.js)
        for line in ("send(`staff ${want.shed.uid} ${hands}`)", "send(`march ${h.uid} ${n.key}`)",
                     "send(`post ${first} captain ${h.uid}`)",
                     "send(`split ${h.uid} ${pairs.join(' ')}`)",
                     "send(`join ${h.uid} ${b.dataset.join}`)"):
            self.assertIn(line, self.js)

    def test_the_selection_is_on_screen_and_escape_lets_it_go(self):
        for i in ("sel", "sel-text", "sel-hint", "sel-group", "sel-clear"):
            self.assertIn(f'id="{i}"', self.html)
        self.assertIn("['sel', clearSel]", self.js)
        self.assertIn("function boxSelect", self.js)
        self.assertIn("function rememberGroup", self.js)
        self.assertIn("function nextIdle", self.js)

    def test_the_keys_card_teaches_the_mouse(self):
        for words in ("right-click", "double-click", "shift-click", "<kbd>.</kbd>",
                      "right-drag / arrows"):
            self.assertIn(words, self.html)


if __name__ == "__main__":
    unittest.main()


class TestTheyWalkThere(unittest.TestCase):
    """A right-click means "go there", and going takes walking.

    The books seat the hands the moment the order is given -- a day is the
    unit in there -- so the walk is a transition the picture draws between
    two true states. What the client must get right is which shed the
    ground was asking for, and that a shed you have shut is never one of
    them.
    """

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text(encoding="utf-8")

    def test_the_ground_is_asked_what_it_wants_doing(self):
        # Trees mean the woodcutter, the field means the farm, water means
        # the boats: the tile under the click picks the kind of shed.
        self.assertIn("const WORK_ON = { forest: 'forest', field: 'fertile', water: 'coast'", self.js)
        self.assertIn("function workFor", self.js)
        self.assertIn("function tileKind", self.js)
        # and the fallback is still the nearest work there is
        self.assertIn("the nearest work", self.js)

    def test_a_shed_you_have_shut_is_not_work(self):
        self.assertIn("b.enabled !== false", self.js)

    def test_the_walk_is_drawn(self):
        for bit in ("function setThemWalking", "function claimTrip", "function crossesWater",
                    "const arriving = new Map()", "claimedTrip.clear()"):
            self.assertIn(bit, self.js, bit)
        # the figure that would otherwise stand there is the one that walks
        self.assertIn("const trip = (f.kind === 'worker' && !afoot) ? claimTrip(f.work) : null", self.js)

    def test_the_drawing_is_told_whether_a_shed_is_open(self):
        from marchlands.layout import plan_for
        g, key = None, None
        st = start("marchlands", seed=3).world.settlements["aldworth"]
        shed = next(b for b in st.buildings if b.complete and b.spec.jobs)
        self.assertTrue(next(p for p in plan_for(st).buildings if p.uid == shed.uid).enabled)
        shed.enabled = False
        self.assertFalse(next(p for p in plan_for(st).buildings if p.uid == shed.uid).enabled)
        self.assertIn("enabled", plan_for(st).to_dict()["buildings"][0])


class TestIdleHands(unittest.TestCase):
    """Hands with nothing to do, and the chip that says so.

    Age of Empires needs an idle-villager button because its villagers
    scatter and are commanded one at a time. Stronghold has none, because
    its idle peasants all stand round the campfire where you cannot miss
    them. This town scatters its idle folk along the roads, so it takes
    the button -- and what it counts is hands, not figures, because a
    figure here is eight of them.
    """

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text(encoding="utf-8")
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_the_chip_is_on_the_page_and_wired_to_the_same_order(self):
        self.assertIn('id="idle"', self.html)
        self.assertIn('id="idle-count"', self.html)
        self.assertIn("$('idle').addEventListener('click', nextIdle)", self.js)
        self.assertIn("function paintIdle", self.js)

    def test_it_counts_hands_rather_than_figures(self):
        self.assertIn("String(idle.length * per)", self.js)

    def test_idle_figures_mean_a_town_with_more_hands_than_work(self):
        # The claim the chip makes, checked against the town it is drawn
        # from: nobody stands about while there is a job going.
        from marchlands.sim import Bot
        g = start("marchlands", seed=5)
        Bot(g).run(150)
        st = g.world.settlements["aldworth"]
        # Enough sheds for everybody: nobody is drawn standing about.
        while st.jobs_offered < st.workforce:
            st.population -= 10
        st._seat_hands()
        self.assertFalse([f for f in plan_for(st).folk if f.kind == "idle"],
                         "somebody is drawn idle in a town with work going spare")
        # More hands than the town has work for: now they stand about, and
        # the chip has something to count.
        st.population += 400
        st._seat_hands()
        self.assertLess(st.jobs_offered, st.workforce)
        self.assertTrue([f for f in plan_for(st).folk if f.kind == "idle"],
                        "a town that has outgrown its work draws nobody idle")


class TestTheyGatherAtTheMarket(unittest.TestCase):
    """Stronghold's campfire, in a town that has a market square.

    Idle folk used to be sprinkled along the roads, which is the AoE2
    picture and hid the one thing worth seeing: a town with more hands
    than work. They stand together now, in front of the square, and the
    size of the crowd is the reading.
    """

    def crowded(self, seed=5, extra=400):
        from marchlands.sim import Bot
        g = start("marchlands", seed=seed)
        Bot(g).run(200)
        st = g.world.settlements["aldworth"]
        st.population += extra
        st._seat_hands()
        return st, plan_for(st)

    def test_they_stand_together_in_front_of_the_square(self):
        import math
        st, plan = self.crowded()
        market = next((b for b in plan.buildings if b.key == "market"), None)
        self.assertIsNotNone(market, "this fixture wants a market square")
        idle = [f for f in plan.folk if f.kind == "idle"]
        self.assertTrue(idle, "nobody is idle in a town with more hands than jobs")
        for f in idle:
            gap = math.hypot(f.x - market.x, f.y - market.y)
            self.assertLess(gap, 4.5, "an idle figure is nowhere near the square")
            self.assertGreater(gap, 0.8, "an idle figure is standing on the square itself")
            self.assertGreater(f.y, market.y, "somebody is loitering round the back")

    def test_they_say_what_they_are_waiting_for(self):
        st, plan = self.crowded()
        idle = [f for f in plan.folk if f.kind == "idle"]
        self.assertIn("waiting at the", idle[0].at)
        self.assertIn("Market Square", idle[0].at)

    def test_a_town_with_nowhere_to_gather_still_draws_them(self):
        st, _ = self.crowded()
        for b in st.buildings:
            if b.key in ("market", "chapel", "inn"):
                b.days_left = 5          # unbuilt: nowhere to stand about
        plan = plan_for(st)
        idle = [f for f in plan.folk if f.kind == "idle"]
        self.assertTrue(idle, "the idle vanished when the square did")
        self.assertEqual(idle[0].at, "nothing to do")


class TestTheThreeRules(unittest.TestCase):
    """Left click selects. Drag selects a group. Right click is the order.

    No exceptions left: every clickable thing in the town and on the march
    is picked up by a click, nothing opens a panel by itself, and bare
    ground lets go. The panels are all behind `i` and the strip's button.
    """

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text(encoding="utf-8")
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_a_click_selects_every_kind_of_thing(self):
        # A figure, a beast and a host also answer once picked up (see
        # test_frame), so those three are not a bare `return select(...)`.
        for line in ("select('folk', who, shift)",
                     "select('beast', beast, shift)",
                     "return select('building', b.uid, shift)",
                     "select(h.mine ? 'host' : 'theirs', h.uid, shift)",
                     "return select('place', n.key, shift)"):
            self.assertIn(line, self.js, line)

    def test_no_click_opens_a_panel_by_itself(self):
        # The writs are only reachable through the selection now.
        self.assertNotIn("return buildingWrit(b, e)", self.js)
        self.assertNotIn("return openSoul(beast, true)", self.js)
        self.assertNotIn("return nodeWrit(n, e)", self.js)
        self.assertIn("closeWrit();\n  closeSoul();\n  paintSel();", self.js)

    def test_bare_ground_lets_go(self):
        self.assertIn("// Bare ground: let them be.", self.js)
        self.assertIn("return clearSel();", self.js)

    def test_building_is_asked_for_rather_than_stumbled_into(self):
        self.assertIn("function startPlacing", self.js)
        self.assertIn("$('sel-build').addEventListener('click', startPlacing)", self.js)
        self.assertIn('id="sel-build"', self.html)
        self.assertIn("if (placing) {", self.js)
        # and the old way is kept as a double-click on a plot
        self.assertIn("// still reaches for the ground.", self.js.replace(
            "still reaches for the ground.", "still reaches for the ground."))

    def test_every_kind_answers_a_right_click(self):
        for said in ("that host is not yours to command",
                     "a place takes no orders",
                     "a shed stays where it was put",
                     "the beasts keep to their yard",
                     "the watch holds the wall"):
            self.assertIn(said, self.js, said)

    def test_going_after_a_host_of_theirs(self):
        self.assertIn("going after ${foe.name}", self.js)
        self.assertIn("where it was last seen", self.js)

    def test_the_card_is_one_press_away_for_everything(self):
        for bit in ("if (sel.kind === 'place')", "if (sel.kind === 'building')",
                    "if (sel.kind === 'beast') return openSoul(sel.ids[0], true)"):
            self.assertIn(bit, self.js, bit)
        self.assertIn("function isoOnScreen", self.js)

    def test_the_keys_card_says_all_of_it(self):
        for words in ("pick up whatever you point at", "let them be",
                      "<kbd>B</kbd> / double-click"):
            self.assertIn(words, self.html, words)


class TestThroughTheirEyes(unittest.TestCase):
    """The one view an isometric game never gives you.

    Bannerlord's hold on people is not its polygons, it is that you are
    somebody standing in the place rather than a hand above it. This is
    that, in the only terms this game has: the same plan, the same day's
    sky, projected out of one figure's eyes instead of down onto the town.

    There is no walking in it, and that is not a shortcut: a figure here is
    eight pairs of hands at a shed, which is a fact about the town, not a
    body to drive around it. What standing there offers is what it offers.
    """

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text(encoding="utf-8")
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_the_view_is_on_the_page_and_reachable(self):
        for el in ("eyes", "eyes-view", "eyes-who", "eyes-where", "eyes-ahead",
                   "eyes-left", "eyes-right", "eyes-close"):
            self.assertIn(f'id="{el}"', self.html, el)
        self.assertIn('id="sel-eyes"', self.html)
        self.assertIn("$('sel-eyes').addEventListener('click', eyesOpen)", self.js)
        self.assertIn("['eyes', eyesShut]", self.js)

    def test_it_projects_the_same_town(self):
        for fn in ("function eyesOpen", "function eyesFrame", "function eyesPoint",
                   "function eyesBox", "function eyesBuilding", "function eyesWall",
                   "function eyesFigure", "function eyesBeast", "function eyesTile"):
            self.assertIn(fn, self.js, fn)
        # from the plan and the day, not from a second world
        self.assertIn("for (const b of plan.buildings)", self.js)
        self.assertIn("const p = pal(), s = sun();", self.js)

    def test_you_stand_outside_what_you_work_at(self):
        self.assertIn("function eyesStand", self.js)
        self.assertIn("function eyesFootprint", self.js)

    def test_it_says_who_is_looking_and_at_what(self):
        self.assertIn("$('eyes-ahead').textContent", self.js)
        self.assertIn("on the wall-walk, looking out", self.js)

    def test_turning_is_the_whole_of_the_movement(self):
        self.assertIn("function eyesTurn", self.js)
        self.assertNotIn("function eyesWalk", self.js)
