from __future__ import annotations

import argparse
import sys

from .campaign import CHAPTERS, Run
from .cli import play, play_campaign
from .engine import GameState
from . import cartography as carto
from .scenario import drawn_game
from .scenarios import CAMPAIGN, SCENARIOS, start


def ink_free(dials) -> str:
    """The dials in words, for the listing -- which runs before any colour."""
    return " \u00b7 ".join(word for _n, _v, word in carto.describe(dials))
from .tech import HOUSES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="marchlands")
    ap.add_argument("--scenario", default="marchlands", choices=sorted(SCENARIOS),
                    help="which game to play; --list describes them")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--house", default="plough", choices=sorted(HOUSES),
                    help="the house you were born into; see `tech` in game")
    ap.add_argument("--region", choices=sorted(carto.REGIONS),
                    help="draw a march on real country instead of the "
                         "hand-made map: " + ", ".join(sorted(carto.REGIONS)))
    ap.add_argument("--dials", metavar="hills=0.8,marsh=0.3",
                    help="turn the country's dials yourself. "
                         + ", ".join(carto.DIAL_NAMES))
    ap.add_argument("--list", action="store_true",
                    help="describe the scenarios and the houses, then stop")
    ap.add_argument("--autosave", metavar="FILE",
                    help="save after every `next`")
    ap.add_argument("--load", metavar="FILE", help="resume a saved game")
    ap.add_argument("--web", action="store_true",
                    help="play in a browser, with the town drawn rather than spelled")
    ap.add_argument("--port", type=int, default=8731, help="port for --web")
    ap.add_argument("--no-browser", action="store_true",
                    help="with --web, do not open a browser window")
    ap.add_argument("--campaign", action="store_true",
                    help="play the Marcher Chronicle: six linked chapters")
    ap.add_argument("--campaign-file", metavar="FILE", default="chronicle.campaign",
                    help="where the campaign remembers itself between chapters")
    ap.add_argument("--sim", type=int, metavar="DAYS",
                    help="run headless for DAYS and print a balance report")
    args = ap.parse_args(argv)

    if args.list:
        print("  THE MARCHER CHRONICLE  (--campaign plays these in order)")
        for i, ch in enumerate(CHAPTERS, 1):
            print(f"  {i}. {ch.name:<28} {ch.years:g} years   teaches {ch.teaches}")
        print("\n  SCENARIOS  (--scenario plays one on its own)")
        for key in CAMPAIGN:
            sc = SCENARIOS[key]
            print(f"     {sc.key:<14} {sc.name:<20} {sc.years:g} years")
            print(f"     {sc.blurb}")
        print("\n  COUNTRY  (--region draws a march instead of playing the "
              "hand-made one)")
        for key, reg in carto.REGIONS.items():
            print(f"     {key:<10} {reg.name}")
            print(f"     {reg.note}")
            print("     " + ink_free(reg.dials))
        print("\n     --dials turns them yourself, e.g. "
              "--region fens --dials hills=0.4,towns=9")
        print("\n  HOUSES")
        for key, h in HOUSES.items():
            print(f"  {key:<10} {h.name}")
            print(f"             {h.blurb}")
        return 0
    if args.sim:
        from .sim import main as sim_main
        return sim_main(["--days", str(args.sim), "--seed", str(args.seed),
                         "--scenario", args.scenario])
    if args.campaign:
        import os
        if os.path.exists(args.campaign_file):
            run = Run.load(args.campaign_file)
            print(f"  resuming the Marcher Chronicle at chapter "
                  f"{min(run.chapter + 1, len(CHAPTERS))}")
        else:
            run = Run(seed=args.seed, house=args.house)
        play_campaign(run, save_to=args.campaign_file)
        return 0
    if args.load:
        game = GameState.load(args.load)
    elif args.region or args.dials:
        region = args.region or carto.DEFAULT_REGION
        dials = carto.REGIONS[region].dials
        if args.dials:
            try:
                dials = carto.parse_dials(args.dials, dials)
            except KeyError as exc:
                ap.error(str(exc))
        game = drawn_game(region, seed=args.seed, house=args.house,
                          dials=dials)
    else:
        game = start(args.scenario, seed=args.seed, house=args.house)
    if args.web:
        from .web import main as web_main
        return web_main(game, port=args.port, open_browser=not args.no_browser)
    play(game, autosave=args.autosave)
    return 0


if __name__ == "__main__":
    sys.exit(main())
