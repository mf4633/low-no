"""The keys card and the keys agree.

W said "a week" on the card for a whole release while the handler caught it
first and toggled the wall -- the clock never moved and a player who learned
from `?` would think it broken. These read the card and the handler and hold
them to each other: every letter the card names is bound exactly once, and
the ones that send a line send the line the card describes.
"""

import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "marchlands" / "static"
JS = (STATIC / "marchlands.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")


def _card() -> str:
    start = HTML.index('<div id="keys"')
    return HTML[start:HTML.index("</dl>", start)]


def _handler() -> str:
    """The global keydown listener: from the KEYS table to its last line."""
    start = JS.index("const KEYS = {")
    return JS[start:JS.index("$('keys').addEventListener('click'", start)]


def _table(name: str) -> dict:
    body = re.search(name + r"\s*=\s*\{([^}]*)\}", JS).group(1)
    return {k: v for k, v in re.findall(r"(\w)\s*:\s*'([^']*)'", body)}


def _letters_on_card() -> set:
    """Bare letters the card names -- not the K of <kbd>⌘</kbd><kbd>K</kbd>,
    which is a chord and another key altogether."""
    return {k.lower() for k in re.findall(
        r"(?<!<kbd>[⌘⌃]</kbd>)<kbd>([A-Za-z])</kbd>", _card())}


class TestTheCardIsTrue(unittest.TestCase):
    def bindings(self, letter: str) -> int:
        """Lines of the handler that act on the bare letter -- a pair like
        (e.key === 'b' || e.key === 'B') is one line and one binding, and a
        chord behind `meta` (Ctrl+P, Ctrl+K) is another key altogether --
        plus its entries in the two tables."""
        pat = re.compile(rf"e\.key === '[{letter}{letter.upper()}]'")
        n = sum(1 for line in _handler().splitlines()
                if pat.search(line) and "meta" not in line)
        n += int(letter in _table("KEYS")) + int(letter in _table("VIEW_KEYS"))
        return n

    def test_every_letter_on_the_card_is_bound_once(self):
        letters = _letters_on_card()
        self.assertTrue({"w", "m", "t", "r", "c", "b", "h"} <= letters, letters)
        for k in sorted(letters):
            self.assertEqual(self.bindings(k), 1,
                             f"{k.upper()} is bound {self.bindings(k)} times")

    def test_the_time_keys_move_time(self):
        keys = _table("KEYS")
        card = _card()
        self.assertEqual(keys["w"], "next 7")
        self.assertIn("<kbd>W</kbd></dt><dd>a week", card)
        self.assertEqual(keys["m"], "next 30")
        self.assertIn("<kbd>M</kbd></dt><dd>a month", card)

    def test_the_views_are_the_views(self):
        self.assertEqual(_table("VIEW_KEYS"),
                         {"t": "town", "r": "march", "c": "castle"})
        self.assertIn("the town / the march / the wall", _card())

    def test_no_view_letter_is_also_a_line(self):
        self.assertFalse(set(_table("KEYS")) & set(_table("VIEW_KEYS")))

    def test_the_right_button_only_gives_orders(self):
        self.assertIn("if (e.button === 2) return;", JS)
        self.assertNotIn("right-drag", _card())

    def test_the_palette_has_a_button(self):
        self.assertIn('id="v-act"', HTML)
        self.assertIn("$('v-act').addEventListener('click', () => openPalette(''))", JS)

    def test_the_fight_says_what_space_is(self):
        self.assertIn('id="battle-space"', HTML)
        self.assertIn("Space — fight a round", HTML)

    def test_the_eyes_say_they_do_not_walk(self):
        self.assertIn("turn only", HTML[HTML.index('id="eyes"'):])

    def test_question_mark_works_in_the_prompt(self):
        # Before the typing guard, so it opens the card with the cursor in
        # the prompt -- the state the game spends all its time in.
        h = _handler()
        self.assertLess(h.index("e.key === '?'"), h.index("if (typing()) return;"))


class TestThePanelHasFivePages(unittest.TestCase):
    def test_five_tabs_and_every_section_is_on_one(self):
        tabs = re.findall(r'<button[^>]*role="tab"[^>]*data-tab="(\w+)"', HTML)
        self.assertEqual(tabs, ["town", "wall", "road", "court", "house"])
        panel = HTML[HTML.index('<aside id="panel"'):HTML.index("</aside>")]
        for sec in re.findall(r"<section[^>]*>", panel):
            m = re.search(r'data-tab="(\w+)"', sec)
            self.assertTrue(m and m.group(1) in tabs, sec)

    def test_every_tab_has_something_on_it(self):
        panel = HTML[HTML.index('<aside id="panel"'):HTML.index("</aside>")]
        for t in ("town", "wall", "road", "court", "house"):
            self.assertIn(f'<section', panel)
            self.assertRegex(panel, rf'<section[^>]*data-tab="{t}"')


if __name__ == "__main__":
    unittest.main()
