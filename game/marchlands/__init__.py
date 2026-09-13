"""Marchlands -- a medieval game about land, labour, the road and the wall.

    python -m marchlands            play
    python -m marchlands --sim 360  run the economy headless and print a report
"""

__all__ = ["GameState", "new_game"]
__version__ = "0.2.0"

from .engine import GameState          # noqa: F401
from .scenario import new_game         # noqa: F401
