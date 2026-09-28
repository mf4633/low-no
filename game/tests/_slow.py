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
