"""The Marcher Chronicle: six chapters, one house, and the record of it.

The systems were all there and the game still had no middle. A scenario asks
whether you can do a thing; a campaign asks what became of you, and the
difference is entirely in what crosses from one chapter to the next.
"""

import io
import json
import os
import tempfile
import unittest

from marchlands import config as C
from marchlands.campaign import (CHAPTERS, RIVAL, Carry, Run, carry_from,
                                 chapter_at, won_chapter)
from marchlands.chronicle import MOMENTOUS, ROUTINE, Chronicle
from marchlands.cli import Console, play_campaign
from marchlands.scenarios import start
from marchlands.sim import Bot


# ------------------------------------------------------------- the chronicle
class TestChronicle(unittest.TestCase):
    def test_it_writes_things_down_with_the_date(self):
        c = Chronicle()
        e = c.record(day=40, year=1247, season="spring", text="something")
        self.assertIsNotNone(e)
        self.assertEqual(e.stamp(), "spring 1247")

    def test_it_does_not_write_the_same_line_every_day_of_a_siege(self):
        c = Chronicle()
        for day in range(14):
            c.record(day=day, year=1247, season="spring", text="the host is here")
        self.assertEqual(len(c), 1)

    def test_but_the_same_thing_a_year_later_is_a_new_thing(self):
        c = Chronicle()
        c.record(day=1, year=1247, season="spring", text="the host is here")
        c.record(day=400, year=1248, season="spring", text="the host is here")
        self.assertEqual(len(c), 2)

    def test_reading_it_back_skips_the_routine(self):
        c = Chronicle()
        c.record(day=1, year=1247, season="spring", text="quiet", weight=ROUTINE)
        c.record(day=2, year=1247, season="spring", text="loud", weight=MOMENTOUS)
        self.assertEqual([e.text for e in c.read()], ["loud"])
        self.assertEqual(len(c.read(least=ROUTINE)), 2)

    def test_it_does_not_grow_without_limit(self):
        from marchlands.chronicle import MAX_ENTRIES
        c = Chronicle()
        for day in range(MAX_ENTRIES + 120):
            c.record(day=day, year=1247, season="spring", text=f"day {day}",
                     weight=ROUTINE)
        self.assertLessEqual(len(c), MAX_ENTRIES)

    def test_the_momentous_outlives_the_routine(self):
        from marchlands.chronicle import MAX_ENTRIES
        c = Chronicle()
        c.record(day=0, year=1247, season="spring", text="the keep fell",
                 weight=MOMENTOUS)
        for day in range(1, MAX_ENTRIES + 200):
            c.record(day=day, year=1247, season="spring", text=f"day {day}",
                     weight=ROUTINE)
        self.assertIn("the keep fell", [e.text for e in c.entries])

    def test_it_survives_a_save(self):
        c = Chronicle()
        c.record(day=4, year=1247, season="autumn", text="a thing", chapter="dust")
        back = Chronicle.from_dict(json.loads(json.dumps(c.to_dict())))
        self.assertEqual(back.entries[0].text, "a thing")
        self.assertEqual(back.entries[0].chapter, "dust")


class TestTheGameWritesItDown(unittest.TestCase):
    def test_a_reign_leaves_a_record(self):
        g = start("marchlands", seed=3)
        Bot(g).run(700)
        self.assertGreater(len(g.chronicle), 0)
        self.assertTrue(any("Age of" in e.text for e in g.chronicle.entries))

    def test_your_own_doings_outrank_other_lords_errands(self):
        """A rival's pilgrimage is not an event in your reign."""
        g = start("marchlands", seed=3)
        Bot(g).run(700)
        theirs = [e for e in g.chronicle.entries if "lifted" in e.text]
        self.assertTrue(theirs)
        for e in theirs:
            self.assertEqual(e.weight, ROUTINE)

    def test_the_ending_is_the_last_line_of_it(self):
        g = start("marchlands", seed=3)
        Bot(g).run(C.GOAL_DAYS + 5)
        self.assertTrue(g.over)
        self.assertEqual(g.chronicle.entries[-1].text, g.over)

    def test_a_chronicle_survives_a_save(self):
        g = start("marchlands", seed=3)
        g.note("a thing happened", MOMENTOUS)
        back = type(g).from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(len(back.chronicle), 1)


# -------------------------------------------------------------- the chapters
class TestChapters(unittest.TestCase):
    def test_there_are_six_and_they_each_teach_something(self):
        self.assertEqual(len(CHAPTERS), 6)
        self.assertEqual(len({c.key for c in CHAPTERS}), 6)
        for ch in CHAPTERS:
            self.assertTrue(ch.teaches and ch.briefing and ch.won and ch.lost)

    def test_every_chapter_starts(self):
        for ch in CHAPTERS:
            g = ch.start(seed=5)
            self.assertEqual(g.chapter, ch.key)
            self.assertTrue(g.briefing)
            self.assertFalse(g.over)

    def test_they_set_different_terms(self):
        paths = {ch.key: ch.start(seed=5).goals.paths for ch in CHAPTERS}
        self.assertGreater(len({tuple(p) for p in paths.values()}), 2)

    def test_the_early_ones_are_not_about_being_invaded(self):
        quiet = CHAPTERS[0].start(seed=5)
        war = CHAPTERS[3].start(seed=5)
        self.assertLess(quiet.world.towns[RIVAL].hostility,
                        war.world.towns[RIVAL].hostility)

    def test_the_count_is_the_one_who_comes(self):
        g = CHAPTERS[3].start(seed=5)
        others = [t.hostility for k, t in g.world.towns.items() if k != RIVAL]
        self.assertGreater(g.world.towns[RIVAL].hostility, max(others))

    def test_and_he_is_worse_by_the_last_chapter(self):
        four = CHAPTERS[3].start(seed=5).world.towns[RIVAL]
        six = CHAPTERS[5].start(seed=5).world.towns[RIVAL]
        self.assertGreater(six.muster, four.muster)
        self.assertGreater(six.wall_base, four.wall_base)

    def test_chapter_at_stays_in_range(self):
        self.assertIs(chapter_at(-4), CHAPTERS[0])
        self.assertIs(chapter_at(99), CHAPTERS[-1])


class TestWhatCrosses(unittest.TestCase):
    def _finished(self, index=0, seed=5, days=200):
        ch = CHAPTERS[index]
        g = ch.start(seed=seed)
        Bot(g).run(days)
        g.over = g.over or "Triumph. enough."
        return g

    def test_the_house_remembers_what_it_worked_out(self):
        g = self._finished()
        carry = carry_from(g, Carry(), won=True)
        self.assertTrue(carry.techs)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        for key in carry.techs:
            self.assertIn(key, nxt.progress.researched)

    def test_it_brings_a_purse_but_not_the_whole_purse(self):
        g = self._finished()
        g.treasury = 40_000.0
        carry = carry_from(g, Carry(), won=True)
        self.assertGreater(carry.purse, 0)
        self.assertLess(carry.purse, 40_000.0)

    def test_losing_carries_less_than_winning(self):
        g = self._finished()
        g.treasury = 40_000.0
        self.assertGreater(carry_from(g, Carry(), True).purse,
                           carry_from(g, Carry(), False).purse)

    def test_the_lord_and_what_is_left_of_his_line_cross_over(self):
        g = self._finished()
        g.lord.name = "Osric the Grim"
        g.lord.heirs = 1
        carry = carry_from(g, Carry(), won=True)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        self.assertEqual(nxt.lord.name, "Osric the Grim")
        self.assertEqual(nxt.lord.heirs, 1)

    def test_the_chronicle_crosses_over_and_keeps_its_chapters(self):
        g = self._finished()
        carry = carry_from(g, Carry(), won=True)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        nxt.note("something in the second chapter", MOMENTOUS)
        chapters = {e.chapter for e in nxt.chronicle.entries}
        self.assertIn("inheritance", chapters)
        self.assertIn("reeve", chapters)

    def test_renown_only_goes_up(self):
        carry = Carry()
        g = self._finished()
        for won in (True, False, True):
            before = carry.renown
            carry = carry_from(g, carry, won)
            self.assertGreater(carry.renown, before)


class TestWonChapter(unittest.TestCase):
    def test_an_unfinished_chapter_is_not_a_won_one(self):
        g = CHAPTERS[0].start(seed=5)
        self.assertFalse(won_chapter(g))

    def test_the_endings_say_which_they_are(self):
        g = CHAPTERS[0].start(seed=5)
        for ending, expected in (("Triumph. 30,000c", True),
                                 ("The Commons. content", True),
                                 ("You held. 40,000c", True),
                                 ("The Reliquary. three of them", True),
                                 ("Ruined. Your debts outran your carts.", False),
                                 ("Time called. You end with 9c", False),
                                 ("Ended. The last of your people", False)):
            g.over = ending
            self.assertEqual(won_chapter(g), expected, ending)


class TestRun(unittest.TestCase):
    def test_it_walks_the_chapters_in_order(self):
        run = Run(seed=5)
        self.assertIs(run.current, CHAPTERS[0])
        g = run.begin()
        g.over = "Triumph. enough."
        won, epilogue = run.finish(g)
        self.assertTrue(won)
        self.assertEqual(epilogue, CHAPTERS[0].won)
        self.assertIs(run.current, CHAPTERS[1])

    def test_a_loss_still_moves_you_on(self):
        """You do not replay chapter two for ever; you live with it."""
        run = Run(seed=5)
        g = run.begin()
        g.over = "Time called. not enough."
        won, epilogue = run.finish(g)
        self.assertFalse(won)
        self.assertEqual(epilogue, CHAPTERS[0].lost)
        self.assertEqual(run.chapter, 1)

    def test_it_knows_when_it_is_over(self):
        run = Run(seed=5, chapter=len(CHAPTERS))
        self.assertTrue(run.done)

    def test_each_chapter_gets_its_own_seed(self):
        run = Run(seed=5)
        first = run.begin()
        run.chapter = 3
        self.assertNotEqual(first.seed, run.begin().seed)

    def test_standing_shows_where_you_are(self):
        run = Run(seed=5, chapter=2)
        lines = run.standing()
        self.assertIn("here", lines[2])
        self.assertIn("done", lines[0])

    def test_it_survives_being_put_down_and_picked_up(self):
        run = Run(seed=5, chapter=2)
        run.carry.renown = 7
        run.carry.purse = 3_400.0
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.campaign")
            run.save(path)
            back = Run.load(path)
        self.assertEqual(back.chapter, 2)
        self.assertEqual(back.carry.renown, 7)
        self.assertAlmostEqual(back.carry.purse, 3_400.0)


class TestPlayingIt(unittest.TestCase):
    def test_a_chapter_can_be_played_and_closed_out(self):
        run = Run(seed=5)
        out = io.StringIO()
        play_campaign(run, out=out, script=["next 400", "next 400"])
        text = out.getvalue()
        self.assertIn("A SMALL INHERITANCE", text)
        self.assertIn("END OF CHAPTER", text)
        self.assertEqual(run.chapter, 1)

    def test_the_whole_thing_can_be_played_through(self):
        run = Run(seed=5)
        for _ in range(len(CHAPTERS)):
            out = io.StringIO()
            play_campaign(run, out=out, script=["next 800"])
        self.assertTrue(run.done)
        self.assertEqual(len(run.carry.outcomes), len(CHAPTERS))
        self.assertGreater(len(run.carry.chronicle), 0)

    def test_the_console_shows_where_you_are(self):
        run = Run(seed=5, chapter=2)
        g = run.begin()
        out = io.StringIO()
        con = Console(g, out=out)
        con.run = run
        con.do("campaign")
        self.assertIn("THE SALT ROAD".title().upper(), out.getvalue().upper())

    def test_outside_a_campaign_it_says_so(self):
        g = start("marchlands", seed=5)
        out = io.StringIO()
        Console(g, out=out).do("campaign")
        self.assertIn("single game", out.getvalue())

    def test_chronicle_reads_back_in_the_console(self):
        g = start("marchlands", seed=3)
        Bot(g).run(500)
        out = io.StringIO()
        Console(g, out=out).do("chronicle")
        self.assertIn("THE CHRONICLE", out.getvalue())

    def test_an_empty_chronicle_says_so_rather_than_nothing(self):
        g = start("marchlands", seed=5)
        out = io.StringIO()
        Console(g, out=out).do("chronicle")
        self.assertIn("Nothing worth writing down", out.getvalue())

    def test_none_of_it_emits_escapes_when_piped(self):
        run = Run(seed=5, chapter=1)
        g = run.begin()
        out = io.StringIO()
        con = Console(g, out=out)
        con.run = run
        for cmd in ("campaign", "chronicle", "chronicle all"):
            con.do(cmd)
        self.assertNotIn("\033", out.getvalue())


if __name__ == "__main__":
    unittest.main()
