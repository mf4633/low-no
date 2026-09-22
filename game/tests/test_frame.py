"""The frame round the picture.

"Capture the feel of those referenced games even more so." Most of that
feel is not in the picture but round it: Age of Empires' row of piles and
its minimap, the horn when you are attacked, villagers who answer, the
banner when an age turns; Stronghold's popularity number and the book with
the rations and the tax in it; Europa Universalis' space bar. None of it may
decide anything -- every number on it is one the game already had -- so
these check that the numbers are the game's own, and that the pieces are on
the page and wired to them.
"""
import pathlib
import unittest

from marchlands import config as C
from marchlands import goods as goods_mod
from marchlands import web
from marchlands.scenarios import start
from marchlands.sim import Bot

STATIC = pathlib.Path(__file__).resolve().parents[1] / "marchlands" / "static"


def grown(days=120, seed=5):
    g = start("marchlands", seed=seed)
    Bot(g).run(days)
    key = next(iter(g.world.settlements))
    return g, key, g.world.settlements[key]


class TestTheYards(unittest.TestCase):
    """The resource bar: the piles a player acts on, read off the market."""

    @classmethod
    def setUpClass(cls):
        cls.g, cls.key, cls.s = grown()
        cls.snap = web.snapshot(cls.g, cls.key)

    def test_the_piles_are_the_ones_a_player_acts_on_in_order(self):
        keys = [p["key"] for p in self.snap["stores"]["piles"]]
        self.assertEqual(keys, ["food", "wood", "stone", "iron", "ale", "arms"])

    def test_food_is_counted_in_days_of_what_they_eat(self):
        food = self.snap["stores"]["piles"][0]
        stock = self.s.market.stock
        rations = goods_mod.nourishment(
            {k: stock.get(k, 0.0) for k in goods_mod.RATION_GOODS})
        need = C.RATION_LEVELS[self.s.ration_level][0] * self.s.population
        self.assertEqual(food["have"], round(rations))
        self.assertAlmostEqual(food["days"], rations / need, delta=0.06)

    def test_each_pile_is_the_sum_of_what_it_says_it_is_made_of(self):
        stock = self.s.market.stock
        for p in self.snap["stores"]["piles"][1:]:
            keys = dict((k, ks) for k, _l, ks in web.STORES)[p["key"]]
            self.assertEqual(p["have"], round(sum(stock.get(k, 0.0) for k in keys)))
            for k in p["of"]:
                self.assertIn(k, keys)

    def test_the_stores_know_how_full_they_are(self):
        st = self.snap["stores"]
        self.assertEqual(st["room"], round(self.s.storage(self.g.progress)))
        self.assertEqual(st["held"], round(sum(v for v in self.s.market.stock.values() if v > 0)))

    def test_a_town_with_nobody_in_it_has_no_days_rather_than_infinitely_many(self):
        g, key, s = grown(days=1)
        s.population = 0.0
        food = web.snapshot(g, key)["stores"]["piles"][0]
        self.assertIsNone(food["days"])


class TestThePopularity(unittest.TestCase):
    """Stronghold's number, and where it is going -- the half you act on."""

    def test_heading_is_what_the_mood_is_pulled_toward(self):
        g, key, s = grown()
        snap = web.snapshot(g, key)
        want = max(0.0, min(100.0, 50.0 + sum(v for _, v in s.mood_factors(g.progress))))
        self.assertAlmostEqual(snap["town"]["heading"], want, places=1)
        was = s.popularity
        s.update_mood(g.progress)
        # it moves toward the heading, never past it
        if want > was:
            self.assertTrue(was < s.popularity <= want + 1e-9)
        elif want < was:
            self.assertTrue(want - 1e-9 <= s.popularity < was)

    def test_the_book_prices_every_band_before_you_pull_it(self):
        g, key, s = grown()
        book = web.snapshot(g, key)["town"]["book"]
        self.assertEqual([r["level"] for r in book["rations"]], sorted(C.RATION_LEVELS))
        self.assertEqual([r["level"] for r in book["tax"]], sorted(C.TAX_LEVELS))
        self.assertEqual(sum(r["now"] for r in book["tax"]), 1)
        self.assertEqual(sum(r["now"] for r in book["rations"]), 1)
        for r in book["tax"]:
            self.assertEqual(r["mood"], C.TAX_LEVELS[r["level"]][1])
            self.assertAlmostEqual(r["collects"], s.tax_take(r["level"]), delta=0.06)
            self.assertEqual(r["label"], C.TAX_LABELS[r["level"]])

    def test_pricing_the_bands_does_not_move_the_dial(self):
        g, key, s = grown()
        was = s.tax_level
        web.snapshot(g, key)
        self.assertEqual(s.tax_level, was)

    def test_the_book_speaks_the_console_s_words(self):
        # A band in the book sends `tax <label>` / `ration <label>`, and the
        # console must take every one of them.
        import io
        from marchlands.cli import Console
        g, key, s = grown(days=5)
        con = Console(g, out=io.StringIO())
        for label in C.TAX_LABELS.values():
            con.do(f"tax {label}")
            self.assertEqual(C.TAX_LABELS[s.tax_level], label)
        for label in C.RATION_LABELS.values():
            con.do(f"ration {label}")
            self.assertEqual(C.RATION_LABELS[s.ration_level], label)


class TestThePageHasTheFrame(unittest.TestCase):

    def setUp(self):
        self.js = (STATIC / "marchlands.js").read_text()
        self.html = (STATIC / "index.html").read_text()
        self.css = (STATIC / "marchlands.css").read_text()
        self.sound = (STATIC / "sound.js").read_text()

    def test_the_pieces_are_on_the_page(self):
        for el in ("stores", "mini", "mini-view", "mini-alert", "herald",
                   "herald-title", "herald-kicker", "herald-sub"):
            self.assertIn(f'id="{el}"', self.html, el)

    def test_they_are_drawn_from_every_reading(self):
        for call in ("paintStores(s);", "noteAlerts(was, s);", "noteHeralds(was, s);"):
            self.assertIn(call, self.js, call)
        self.assertIn("setInterval(() => { try { paintMini(); }", self.js)
        self.assertEqual(self.js.count("drawBarks(w, h);"), 2)   # town and march

    def test_a_load_is_not_news(self):
        # A save with more feats, or a siege already on, must not sound the
        # horn and herald the lot as though it happened today.
        self.assertIn("if (was.here !== s.here || s.day < was.day) return;", self.js)
        self.assertIn("s.day <= was.day || s.day - was.day > 60) return;", self.js)

    def test_the_horn_and_the_bell_divide_the_work(self):
        for sound in ("function horn(", "function fanfare(", "function voice("):
            self.assertIn(sound, self.sound, sound)
        for kind in ("'horn'", "'fanfare'", "kind.startsWith('voice')"):
            self.assertIn(kind, self.sound, kind)
        self.assertIn("raiseAlert(mid[0], mid[1], 'war', 'horn')", self.js)
        self.assertIn("raiseAlert(b.x, b.y, 'fire', 'alarm')", self.js)
        # and the halt's bell does not ring over a horn already sounding
        self.assertIn("performance.now() - hornAt > 3000", self.js)

    def test_they_answer_both_being_picked_and_being_sent(self):
        self.assertIn("select('folk', who, shift); return bark('pick', e);", self.js)
        self.assertIn("bark('go', e, want.shed.terrain);", self.js)
        self.assertIn("bark('go', e, 'foe');", self.js)
        # every kind of ground a right-click can mean has its own answer
        for terrain in ("forest", "fertile", "coast", "hills", "clay"):
            self.assertIn(f"    {terrain}: [", self.js, terrain)

    def test_the_keys(self):
        self.assertIn("e.key === 'Home' && !typing()) { goAlert();", self.js)
        self.assertIn("setSpeed(Math.min(3, speedNow + 1))", self.js)
        self.assertIn("setSpeed(Math.max(0, speedNow - 1))", self.js)
        self.assertIn("bookWrit(null)", self.js)
        # space no longer also sends a day from the shortcut table
        self.assertNotIn("' ': 'next'", self.js)
        for said in ("stop / start the clock", "faster / slower",
                     "the scribe&#39;s book", "the last thing that went wrong"):
            self.assertIn(said.replace("&#39;", "'"), self.html, said)

    def test_space_leaves_a_battle_alone(self):
        self.assertIn("!$('battle').hidden) return;", self.js)
        self.assertIn("if ($('battle').hidden) setSpeed(speedNow ? 0 : 1);", self.js)

    def test_the_build_list_has_letters(self):
        self.assertIn("function buildLetters(list)", self.js)
        self.assertIn('data-key="${keys[b.key] || \'\'}"', self.js)
        self.assertIn("picked.kind === 'plot'", self.js)

    def test_the_march_keeps_its_own_screen(self):
        self.assertIn("body.march #stores { display: none; }", self.css)
        self.assertIn("body.march #mini { display: none; }", self.css)

    def test_motion_can_be_refused(self):
        self.assertIn("#herald { animation: none; }", self.css)


if __name__ == "__main__":
    unittest.main()
