"""Python never talks to the player.

Every registered command, run with nothing and with plausible arguments,
against a fresh game and one with a few weeks on it. Nothing may raise, and
nothing may answer with a sentence written by the interpreter: `invalid
literal for int()`, `list index out of range` and their kind are bugs in the
voice even when the game carries on working.

Written after a sweep found two: `accounts` on the first morning, where the
accounts had no yesterday to compare with, and `ration full` -- a word a
player would obviously try, answered with an int() parse error.
"""
import io
import unittest

from marchlands.cli import COMMANDS, Console
from marchlands.scenarios import start

#: Sentences only a traceback would write.
PYTHONISH = ("Traceback", "object has no attribute", "invalid literal",
             "list index out of range", "KeyError", "IndexError", "TypeError",
             "NoneType", "unsupported operand", "not subscriptable")


def plausible(name, g):
    home = next(iter(g.world.settlements))
    town = next(iter(g.world.towns))
    st = g.world.settlements[home]
    shed = next((b.uid for b in st.buildings if b.complete and b.spec.jobs), 1)
    host = next((a.uid for a in g.armies if a.owner == "player"), 1)
    who = g.kin.living()[0].name.split()[0] if g.kin.living() else "Aldred"
    return {
        "build": ["cottage"], "raze": [str(shed)], "close": [str(shed)],
        "work": ["farm", "first"], "hands": ["farm", "normal"],
        "staff": [str(shed), "2"], "pin": [str(shed), "free"],
        "ration": ["full"], "tax": ["lavish"], "recruit": ["spearman", "2"],
        "host": [home, "spearman", "2"], "army": [str(host)],
        "march": [str(host), town], "split": [str(host), "spearman", "1"],
        "join": [str(host), str(host)], "detach": [str(host), "spearman", "1"],
        "merge": [str(host), str(host)], "siege": [str(host), "batter"],
        "order": [str(host), "flank"], "raid": [str(host)], "recall": [str(host)],
        "standdown": [str(host)], "lead": [str(host)], "post": [who, "steward", home],
        "battle": ["fight"], "fight": ["ride"], "storm": ["auto"],
        "water": ["bridge", home, town], "restock": ["sheep_farm"],
        "info": ["farm"], "tech": ["ploughing"], "study": ["ploughing"],
        "next": ["1"], "n": ["1"], "wait": ["1"],
    }.get(name, [])


class TestTheConsoleSpeaksEnglish(unittest.TestCase):
    def sweep(self, g, label):
        complaints = []
        for name in sorted(set(COMMANDS)):
            for args in ([], plausible(name, g)):
                if name in ("save", "load", "quit", "exit"):
                    continue          # they touch the disk or the process
                buf = io.StringIO()
                line = (name + " " + " ".join(args)).strip()
                try:
                    Console(g, out=buf).do(line)
                except Exception as e:                      # noqa: BLE001
                    complaints.append(f"{label}: `{line}` raised {type(e).__name__}: {e}")
                    continue
                said = buf.getvalue()
                for tell in PYTHONISH:
                    if tell in said:
                        complaints.append(f"{label}: `{line}` said {tell!r}")
                        break
        return complaints

    def test_a_fresh_game_answers_every_command_in_english(self):
        g = start("marchlands", seed=3)
        said = self.sweep(g, "the first morning")
        self.assertEqual(said, [], "\n".join(said))

    def test_a_game_with_a_few_weeks_on_it_does_too(self):
        g = start("marchlands", seed=3)
        g.advance(40)
        said = self.sweep(g, "six weeks in")
        self.assertEqual(said, [], "\n".join(said))

    def test_the_dials_say_what_they_take(self):
        g = start("marchlands", seed=3)
        for line, wanted in (("ration full", "none, half, normal"),
                             ("tax lavish", "largesse")):
            buf = io.StringIO()
            Console(g, out=buf).do(line)
            self.assertIn(wanted, buf.getvalue(), line)

    def test_the_accounts_open_on_the_first_morning(self):
        g = start("marchlands", seed=3)
        self.assertIsNone(g.economy.at(-1))
        self.assertIsNone(g.economy.at(9_999))
        buf = io.StringIO()
        Console(g, out=buf).do("accounts")
        self.assertIn("prices", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
