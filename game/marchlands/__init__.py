"""Marchlands -- a medieval game about land, labour, the road and the wall.

    python -m marchlands            play
    python -m marchlands --sim 360  run the economy headless and print a report
"""

__all__ = ["GameState", "new_game"]
#: The one place the version is written. pyproject reads it from here, and so
#: does the Windows build when it decides whether to cut a release -- this used
#: to be a number here and a different number in pyproject, which is what two
#: hand-written copies of anything eventually are.
__version__ = "0.6.0"

from .engine import GameState          # noqa: F401
from .scenario import new_game         # noqa: F401
