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
        self.js = (STATIC / "marchlands.js").read_text()
        self.html = (STATIC / "index.html").read_text()

    def test_a_right_click_is_the_order(self):
        self.assertIn("addEventListener('contextmenu'", self.js)
        for line in ("send(`staff ${shed.uid} ${hands}`)", "send(`march ${h.uid} ${n.key}`)",
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
