"""Marchlands -- a medieval economy game about land, labour and the road.

    python -m marchlands            play
    python -m marchlands --sim 360  run the economy headless and print a report
"""

__all__ = ["GameState", "new_game"]
__version__ = "0.1.0"

from .engine import GameState          # noqa: F401
from .scenario import new_game         # noqa: F401
