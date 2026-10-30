"""The long battery, and the switch that runs it.

A handful of tests here play whole games -- every scenario to the end, two
years of a campaign, a bot across a dozen seeds -- and between them they are
seventeen minutes of a twenty-minute run. They are the balance of the game
and they matter, but they are not what anybody needs to see after changing
a toll table. So they are marked, and skipped unless asked for:

    python -m unittest discover -s tests                     # the fast run
    MARCHLANDS_SLOW=1 python -m unittest discover -s tests   # everything

Run the long battery before cutting a release; `packaging/README.md` says so.
"""

import os
import unittest

RUN_SLOW = os.environ.get("MARCHLANDS_SLOW", "") not in ("", "0")

slow = unittest.skipUnless(
    RUN_SLOW, "plays a long game -- set MARCHLANDS_SLOW=1 to run it")


#: The words a finished game's `over` line opens with when the house won.
WON = ("Triumph", "Dominion", "cathedral", "Reliquary")


def _play_to_the_end(job):
    """One bot game, played out: (seed, won, lasted, net worth)."""
    scenario, seed = job
    from marchlands import config as C
    from marchlands.scenario import new_game
    from marchlands.scenarios import start
    from marchlands.sim import Bot
    if scenario is None:
        g = new_game(seed=seed)
        Bot(g).run(C.GOAL_DAYS)
    else:
        g = start(scenario, seed=seed)
        Bot(g).run(g.goals.days)
    won = any(w in g.over for w in WON)
    lasted = "Ruined" not in g.over and "Ended" not in g.over
    return seed, won, lasted, g.net_worth()


def play_many(seeds, scenario=None):
    """A bot game on each seed, side by side on the machine's cores.

    A balance guard is a rate, and a rate wants two dozen games, not one:
    a single pinned seed is a coin already flipped, and any change that
    shuffles the dice -- a man buried a day earlier -- flips it again.
    Played in a row two dozen games are eight minutes; side by side, one.
    """
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(scenario, s) for s in seeds]
    with ProcessPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 1)) as pool:
        return list(pool.map(_play_to_the_end, jobs))
