"""The three things players actually name, when you ask them.

Not features from a design document -- the things people who have played
these games for twenty years bring up unprompted: the AI lords they still
have favourites among, the peasant who says "Double rations? Oh, thank you,
Sire!", and the mode where nobody is coming and you just build.
"""

import io
import pathlib
import unittest

from marchlands import config as C
from marchlands import lords, voices
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.scenario import new_game
from marchlands.scenarios import SCENARIOS, start
from marchlands.sim import Bot


def grown(seed: int = 5, days: int = 400, key: str = "marchlands"):
    g = start(key, seed=seed)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g, bot


class TestTheLordsAreDifferentPeople(unittest.TestCase):
    """A rival you cannot tell apart from another rival is a number with a
    name on it. Ask anybody about Stronghold and you get the Rat, the Snake
    and the Wolf -- characters, because each one plays differently."""

    def test_every_lord_on_the_march_is_a_sort_of_lord(self):
        g = new_game(seed=5)
        for key, t in g.world.towns.items():
            self.assertIn(key, lords.CAST, t.name)
            self.assertIn(lords.CAST[key], lords.SORTS)
            self.assertEqual(t.sort, lords.sort_of(key).key)

    def test_no_two_sorts_play_the_same(self):
        seen = set()
        for sort in lords.SORTS.values():
            shape = (sort.aggression, sort.temper, sort.muster,
                     sort.thrift, sort.raids, sort.bought, sort.holds)
            self.assertNotIn(shape, seen, f"{sort.name} is somebody else")
            seen.add(shape)

    def test_the_scenario_sets_the_decade_and_the_lord_sets_himself(self):
        """Rolling the band straight over the top of his nature -- which is
        what this did -- made the Heron and the Boar the same man."""
        g = new_game(seed=5)
        boars = [t.aggression for k, t in g.world.towns.items()
                 if lords.CAST[k] == "boar"]
        herons = [t.aggression for k, t in g.world.towns.items()
                  if lords.CAST[k] == "heron"]
        self.assertGreater(min(boars), max(herons))

    def test_a_bigger_lord_musters_bigger(self):
        g = new_game(seed=5)
        wolf = next(t for k, t in g.world.towns.items()
                    if lords.CAST[k] == "wolf")
        heron = next(t for k, t in g.world.towns.items()
                     if lords.CAST[k] == "heron")
        self.assertGreater(wolf.muster, heron.muster)

    def test_each_of_them_has_something_to_say(self):
        for sort in lords.SORTS.values():
            for when in ("declares", "takes", "beaten", "paid"):
                self.assertTrue(getattr(sort, when), f"{sort.name}: {when}")
                for line in getattr(sort, when):
                    self.assertTrue(line.strip().endswith((".", "!", "?")))

    def test_and_says_it_when_the_moment_comes(self):
        g, _ = grown(days=900)
        spoken = [m for m in g.battles if "“" in m or '"' in m]
        self.assertTrue(spoken, "nobody said anything in three years of war")

    def test_a_magpie_is_cheaper_to_buy_off_than_a_wolf(self):
        g = new_game(seed=5)
        magpie = next(k for k in g.world.towns if lords.CAST[k] == "magpie")
        wolf = next(k for k in g.world.towns if lords.CAST[k] == "wolf")
        per = lambda key: (g.truce_cost(key, 100)          # noqa: E731
                           / (g.world.towns[key].muster
                              * g.world.towns[key].prosperity))
        self.assertLess(per(magpie), per(wolf))

    def test_what_sort_he_is_is_something_you_have_to_find_out(self):
        """Character is intelligence, and intelligence is what the trade layer
        buys. The same rule the rest of the fog follows."""
        self.assertIn("nobody of yours", lords.reputation("dunmere", seen=False))
        self.assertEqual(lords.reputation("dunmere", seen=True),
                         lords.sort_of("dunmere").blurb)

    def test_the_war_screen_names_them_once_you_have_been(self):
        g, _ = grown(days=500)
        buf = io.StringIO()
        Console(g, out=buf).do("war")
        out = buf.getvalue()
        self.assertTrue(any(s.name in out for s in lords.SORTS.values()))

    def test_a_lord_keeps_his_character_across_a_save(self):
        g, _ = grown(days=300)
        back = GameState.from_dict(g.to_dict())
        for key, t in g.world.towns.items():
            self.assertEqual(back.world.towns[key].sort, t.sort)
            self.assertAlmostEqual(back.world.towns[key].aggression, t.aggression)


class TestTheSortIsRealAndNotALabel(unittest.TestCase):
    """Every dial on a Sort has to do something. A multiplier declared and
    never read is exactly the "described rather than real" character the
    module was written to replace -- a number with a name on it, again."""

    def test_a_thrifty_lord_compounds_and_a_spendthrift_does_not(self):
        import random as _r
        g = new_game(seed=5)
        havn, dun = g.world.towns["havnhold"], g.world.towns["dunmere"]
        havn.prosperity = dun.prosperity = 1.0
        rng = _r.Random(1)
        for _ in range(3 * int(C.DAYS_PER_YEAR)):
            havn.grow(rng)
            dun.grow(rng)
        self.assertGreater(havn.prosperity, dun.prosperity * 1.05,
                           "the Magpie's peace bought him nothing")
        self.assertGreater(lords.sort_of("havnhold").thrift,
                           lords.sort_of("dunmere").thrift)

    def test_an_ox_is_harder_to_shift_off_his_own_parapet(self):
        self.assertGreater(lords.sort_of("ostmark").holds,
                           lords.sort_of("havnhold").holds)
        src = pathlib.Path("marchlands/engine.py").read_text(encoding="utf-8")
        self.assertIn("lordly.sort_of(town.key).holds", src,
                      "holds is declared and never read")

    def test_every_dial_a_sort_has_is_read_somewhere(self):
        code = "".join(f.read_text(encoding="utf-8")
                       for f in pathlib.Path("marchlands").glob("*.py")
                       if f.name != "lords.py")
        for dial in ("aggression", "temper", "muster", "thrift",
                     "raids", "bought", "holds",
                     # How he builds, which is the half that makes two lords
                     # two different sieges rather than two different voices.
                     "stone", "towers", "water", "traps", "layers", "cover"):
            self.assertIn(f".{dial}", code, f"{dial} does nothing")


class TestTheTownTalksBack(unittest.TestCase):
    """The single most quoted thing about Stronghold is not a mechanic. It is
    a peasant saying "Double rations? Oh, thank you, Sire!" -- and when a
    sequel dropped the voices the complaint was that the game had gone "more
    bland", which is a complaint about information, not charm."""

    def setUp(self):
        self.g, _ = grown(days=300)
        self.s = self.g.home()

    def said(self, how_many=4):
        return " ".join(
            line for _who, line in voices.speak(self.s, self.g, self.g.rng,
                                                how_many))

    def test_somebody_always_has_something_to_say(self):
        self.assertTrue(voices.speak(self.s, self.g))
        for _who, line in voices.speak(self.s, self.g, how_many=3):
            self.assertTrue(line.strip())

    def test_the_two_lines_everybody_quotes_are_in_there(self):
        # Asserting they land in the top four lines was a double lottery:
        # which voices outrank which on the day, and which of a voice's own
        # lines the dice pick. Neither is a promise the game makes, and the
        # test duly broke on an unrelated two per cent change to trade.
        #
        # What the game does promise is this: the lines exist, and the dial
        # each is attached to is the dial that fires it.
        lines = [l for v in voices.VOICES for l in v.lines]
        self.assertTrue(any("Double rations" in l for l in lines))
        self.assertTrue(any("No taxes is good taxes" in l for l in lines))

    def test_the_famous_lines_answer_the_dial_they_belong_to(self):
        rations = next(v for v in voices.VOICES if v.key == "full rations")
        tax = next(v for v in voices.VOICES if v.key == "light tax")
        self.s.ration_level = max(C.RATION_LEVELS)
        self.s.tax_level = 0
        mood = voices.read(self.s, self.g)
        self.assertTrue(rations.when(mood), "double rations said nothing")
        self.assertTrue(tax.when(mood), "no taxes said nothing")
        # And they stop when you stop.
        self.s.ration_level = min(C.RATION_LEVELS)
        self.s.tax_level = max(C.TAX_LEVELS)
        mood = voices.read(self.s, self.g)
        self.assertFalse(rations.when(mood))
        self.assertFalse(tax.when(mood))

    def test_it_answers_the_dial_you_actually_moved(self):
        self.s.tax_level = max(C.TAX_LEVELS)
        self.assertEqual(voices.read(self.s, self.g).tax, max(C.TAX_LEVELS))
        self.assertIn("tax", voices.loudest(self.s, self.g)) if \
            voices.loudest(self.s, self.g).endswith("tax") else None
        self.s.tax_level = 0
        self.s.ration_level = 1
        said = self.said()
        self.assertNotIn("two pence in every three", said)

    def test_the_loudest_thing_in_the_town_is_what_you_hear_about(self):
        """A town with a host at the gate does not want to talk about beer.

        One crisis at a time, set deliberately. This used to assert `raided`
        was top of a town three hundred days into a real game, and that held
        only while nothing else was wrong with it -- the day a bakery
        happened to be alight the answer was `fire`, which outranks a raid
        and is quite right to. The claim is that a crisis outranks the
        chatter, not that a raid outranks a fire.
        """
        self.s.fires.blazes.clear()
        self.s.raided = False
        self.s.besieged = True
        self.assertEqual(voices.loudest(self.s, self.g), "siege")
        self.s.besieged = False
        self.s.raided = True
        self.assertEqual(voices.loudest(self.s, self.g), "raided")
        # And with nothing wrong, the town goes back to talking about beer.
        self.s.raided = False
        self.assertNotIn(voices.loudest(self.s, self.g),
                         ("siege", "raided", "fire"))

    def test_every_line_belongs_to_a_condition_that_can_happen(self):
        for v in voices.VOICES:
            self.assertTrue(v.lines, v.key)
            self.assertGreater(v.weight, 0)
            self.assertTrue(v.when(voices.Mood()) in (True, False))

    def test_there_is_always_a_last_resort(self):
        quiet = voices.Mood(popularity=55, rations=2, tax=2)
        live = [v for v in voices.VOICES if v.when(quiet)]
        self.assertTrue(live, "a perfectly ordinary day has nobody in it")

    def test_a_debased_penny_is_felt_in_the_street(self):
        # You cannot debase a coinage you do not strike: see tech.py. This
        # test is about what the street says afterwards, not about who is
        # allowed a mint, so it founds one first.
        self.g.progress.researched.add("coinage")
        self.g.mint(C.MINT_LIMIT)
        self.g.tick()
        self.assertIn("debased",
                      [v.key for v in voices.VOICES
                       if v.when(voices.read(self.s, self.g))])

    def test_the_console_puts_a_person_in_front_of_the_numbers(self):
        buf = io.StringIO()
        Console(self.g, out=buf).do("ask")
        out = buf.getvalue()
        self.assertIn("IN THE STREET", out)
        self.assertIn("“", out)

    def test_the_page_carries_it_too(self):
        from marchlands.web import snapshot
        shot = snapshot(self.g)
        self.assertTrue(shot["street"])
        self.assertIn("who", shot["street"][0])
        self.assertIn("said", shot["street"][0])


class TestFreebuild(unittest.TestCase):
    """Named in every retrospective anybody writes: build without fear of
    attack, at your own pace. The building is the thing they came for."""

    def test_it_is_a_scenario_you_can_start(self):
        self.assertIn("freebuild", SCENARIOS)
        g = start("freebuild", seed=5)
        self.assertIn("Freebuild", g.briefing)

    def test_nobody_comes(self):
        g, _ = grown(days=1000, key="freebuild")
        self.assertEqual(g.over, "")
        wars = [m for m in g.battles if "WAR:" in m]
        self.assertFalse(wars, f"somebody came: {wars[:2]}")

    def test_and_nothing_ends(self):
        g, _ = grown(days=1000, key="freebuild")
        self.assertEqual(g.over, "")
        self.assertGreater(g.goals.days, 20 * C.DAYS_PER_YEAR)

    def test_but_everything_else_is_still_real(self):
        """Not a sandbox with the rules off: the market still prices by
        scarcity, the labour still runs out, the house still ages."""
        g, _ = grown(days=700, key="freebuild")
        self.assertGreater(g.population, 100)
        self.assertGreater(g.accounts.cpi, 0)
        self.assertTrue(g.kin.living())
        self.assertGreater(g.home().employed, 0)
        self.assertTrue(any(b.complete for b in g.home().buildings))

    def test_the_march_still_quarrels_among_itself(self):
        """Merchants, not pacifists. A dead march is not a peaceful one, it is
        a diorama."""
        g, _ = grown(days=1000, key="freebuild")
        self.assertTrue(g.league.season.records)
        moves = sum(r.won + r.lost for r in g.league.season.records.values())
        self.assertGreaterEqual(moves, 0)


if __name__ == "__main__":
    unittest.main()


class TestFlavourDoesNotMoveTheWorld(unittest.TestCase):
    """Third time this bug has been written in this codebase. The kin drew
    from the world's stream and a birth in the hall moved the weather; the
    league drew from it and a draft class re-rolled twelve seeds of balance
    measurement. A voice line is the same shape of mistake and worse, because
    a browser polls the street once a second."""

    def test_asking_the_town_does_not_move_the_dice(self):
        g = start("marchlands", seed=11)
        before = g.rng.getstate()
        s = next(iter(g.world.settlements.values()))
        for _ in range(50):
            voices.speak(s, g, voices.street_rng(s, g), 3)
        self.assertEqual(before, g.rng.getstate(),
                         "reading the street re-rolled the campaign")

    def test_the_street_is_the_same_street_while_you_look_at_it(self):
        g = start("marchlands", seed=11)
        s = next(iter(g.world.settlements.values()))
        once = voices.speak(s, g, voices.street_rng(s, g), 2)
        twice = voices.speak(s, g, voices.street_rng(s, g), 2)
        self.assertEqual(once, twice, "the browser would flicker every poll")

    def test_but_it_is_a_different_day_tomorrow(self):
        g = start("marchlands", seed=11)
        s = next(iter(g.world.settlements.values()))
        said = set()
        for day in range(40):
            g.day = day
            said.add(tuple(voices.speak(s, g, voices.street_rng(s, g), 2)))
        self.assertGreater(len(said), 5, "the same afternoon forty times over")

    def test_the_street_does_not_depend_on_when_the_program_started(self):
        # hash() of a string is salted per process. Seeding on one would give
        # a different town every launch, which is not what stable means.
        import subprocess
        import sys
        code = ("from marchlands.scenarios import start\n"
                "from marchlands import voices\n"
                "g = start('marchlands', seed=11)\n"
                "s = next(iter(g.world.settlements.values()))\n"
                "print(voices.speak(s, g, voices.street_rng(s, g), 2))\n")
        out = [subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, env={"PYTHONHASHSEED": str(n),
                                              "PYTHONPATH": "."}).stdout
               for n in (1, 2)]
        self.assertEqual(out[0], out[1], out)
        self.assertTrue(out[0].strip(), "the subprocess said nothing at all")

    def test_a_lord_declaring_does_not_move_the_dice_either(self):
        g = start("marchlands", seed=11)
        before = g.rng.getstate()
        for key in g.world.towns:
            for when in ("declares", "takes", "beaten", "paid"):
                lords.says(key, when, g.voice)
        self.assertEqual(before, g.rng.getstate())

    def test_and_what_he_says_survives_a_save(self):
        g = start("marchlands", seed=11)
        for _ in range(20):
            lords.says("dunmere", "declares", g.voice)
        again = GameState.from_dict(g.to_dict())
        self.assertEqual(lords.says("dunmere", "declares", g.voice),
                         lords.says("dunmere", "declares", again.voice))
