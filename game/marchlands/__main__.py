from __future__ import annotations

import argparse
import sys

from .cli import play
from .engine import GameState
from .scenarios import CAMPAIGN, SCENARIOS, start
from .tech import HOUSES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="marchlands")
    ap.add_argument("--scenario", default="marchlands", choices=sorted(SCENARIOS),
                    help="which game to play; --list describes them")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--house", default="plough", choices=sorted(HOUSES),
                    help="the house you were born into; see `tech` in game")
    ap.add_argument("--list", action="store_true",
                    help="describe the scenarios and the houses, then stop")
    ap.add_argument("--autosave", metavar="FILE",
                    help="save after every `next`")
    ap.add_argument("--load", metavar="FILE", help="resume a saved game")
    ap.add_argument("--sim", type=int, metavar="DAYS",
                    help="run headless for DAYS and print a balance report")
    args = ap.parse_args(argv)

    if args.list:
        print("  SCENARIOS  (in the order they are meant to be played)")
        for i, key in enumerate(CAMPAIGN, 1):
            sc = SCENARIOS[key]
            print(f"  {i}. {sc.key:<14} {sc.name:<20} {sc.years:g} years")
            print(f"     {sc.blurb}")
        print("\n  HOUSES")
        for key, h in HOUSES.items():
            print(f"  {key:<10} {h.name}")
            print(f"             {h.blurb}")
        return 0
    if args.sim:
        from .sim import main as sim_main
        return sim_main(["--days", str(args.sim), "--seed", str(args.seed),
                         "--scenario", args.scenario])
    game = (GameState.load(args.load) if args.load
            else start(args.scenario, seed=args.seed, house=args.house))
    con = play(game, autosave=args.autosave)
    return 0 if con else 0


if __name__ == "__main__":
    sys.exit(main())
