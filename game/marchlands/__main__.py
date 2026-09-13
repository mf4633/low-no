from __future__ import annotations

import argparse
import sys

from .cli import play
from .engine import GameState
from .scenario import new_game


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="marchlands")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--load", metavar="FILE", help="resume a saved game")
    ap.add_argument("--sim", type=int, metavar="DAYS",
                    help="run headless for DAYS and print a balance report")
    args = ap.parse_args(argv)
    if args.sim:
        from .sim import main as sim_main
        return sim_main(["--days", str(args.sim), "--seed", str(args.seed)])
    game = GameState.load(args.load) if args.load else new_game(seed=args.seed)
    play(game)
    return 0


if __name__ == "__main__":
    sys.exit(main())
