"""Terminal interface. Stdlib only, no curses, works over ssh and in a pipe.

This file is the console itself -- i/o, the command table, help, save and
load, the campaign loop. What it says about each part of the game lives
beside the halls it reads: console_town, console_accounts, console_road,
console_wall, console_court and console_house, plus console_advice for the
hints and console_common for what they all draw with.
"""

from __future__ import annotations

import json
import sys
from typing import List, Optional, Sequence

from . import config as C
from .campaign import CHAPTERS, BY_KEY as CHAPTERS_BY_KEY
from .chronicle import MOMENTOUS, NOTABLE, ROUTINE
from .engine import GameState
from .goods import good
from . import kin as kinly
from . import voices
from . import render as ink
from .scenarios import CAMPAIGN, SCENARIOS, start as start_scenario
from .tech import AGES, HOUSES, TECHS
from .console_common import RULE, _words, _wrap
from .console_common import sparkline  # noqa: F401 -- tests read it here
from .console_advice import AdviceMixin
from .console_town import TownMixin
from .console_accounts import AccountsMixin
from .console_road import RoadMixin
from .console_wall import WallMixin
from .console_court import CourtMixin
from .console_house import HouseMixin


class Console(AdviceMixin, TownMixin, AccountsMixin, RoadMixin, WallMixin,
              CourtMixin, HouseMixin):
    def __init__(self, game: GameState, out=sys.stdout) -> None:
        self.game = game
        self.out = out
        self.here = next(iter(game.world.settlements))
        self.quit = False
        self.autosave_path = ""
        try:
            ink.set_colour(ink._enabled() and out.isatty())
        except Exception:                    # pragma: no cover - odd streams
            ink.set_colour(False)

    # ------------------------------------------------------------------ i/o
    def say(self, *lines: str) -> None:
        for ln in lines:
            print(ln, file=self.out)

    def err(self, msg: str) -> None:
        self.say(f"  ! {msg}")

    # -------------------------------------------------------------- helpers
    run = None          # the campaign this game belongs to, if any

    def settlement(self, key: Optional[str] = None):
        w = self.game.world
        k = key or self.here
        if k in w.settlements:
            return w.settlements[k]
        return w.settlements[self.here]

    def _which(self, args: List[str], usage: str) -> Optional[int]:
        """Read the number a command was given, or explain what it wanted.

        Eight commands used to say "list index out of range" when handed
        nothing and "invalid literal for int()" when handed a word. That is
        Python talking to a player, which is never the right voice.
        """
        if not args:
            self.err(usage)
            return None
        try:
            return int(args[0])
        except ValueError:
            self.err(f"{args[0]!r} is not a number -- {usage}")
            return None

    def _node(self, text: str, shrines: bool = False) -> str:
        return self.game.world.resolve(text, shrines=shrines)

    def _name(self, key: str) -> str:
        return self.game.world.node_name(key)

    def _where(self, thing) -> str:
        """Where a host or a cart is, with every key turned into a name."""
        return thing.where(self._name)

    # ================================================================ views
    def status(self) -> None:
        g = self.game
        led = g.ledger
        p = g.progress
        vassals = g.world.vassals()
        tint = ink.SEASON_TINT.get(g.season, ink.GOLD)
        self.say(ink.head(g.date_str(), f"{g.treasury:,.0f}c in the chest", tint),
                 f"  net worth {ink.coin(g.net_worth(), 10)}c of "
                 f"{g.goals.net_worth:,.0f}"
                 f"      souls {ink.c(f'{g.population:>6,.0f}', ink.PARCH)}"
                 f" of {g.goals.population}",
                 f"  {ink.c(p.age_name(), ink.PLUM):<33} "
                 f"{ink.c(HOUSES[g.house].name, ink.BONE) if g.house else '':<35}"
                 f"  towns sworn {len(vassals)} of {g.goals.towns}",
                 RULE)
        for s in g.world.settlements.values():
            siege = ink.c("  UNDER SIEGE", ink.BLOOD, bold=True) if s.besieged else ""
            self.say(f"  {ink.c(ink.pad(s.name, 12), ink.PARCH, bold=True)}"
                     f" pop {s.population:>6,.0f}/{s.housing(p):<5,.0f}"
                     f" {ink.bar(s.popularity, 100, 16)} {s.popularity:>4.0f}"
                     f"  work {s.employed:>3}/{s.jobs_offered:<3}"
                     f"  {C.RATION_LABELS[s.ration_level]},"
                     f" {C.TAX_LABELS[s.tax_level]} tax{siege}")
        # One line of macro, and only when it is telling you something. A
        # steady price level and full employment need no commentary.
        a = g.accounts
        notes = []
        if abs(a.inflation) >= 4.0:
            notes.append(ink.c(f"prices {a.inflation:+.0f}% "
                               + ("a year" if a.yearly else "since you began"),
                               ink.BLOOD if a.inflation > 0 else ink.SEA))
        if a.unemployment >= 25.0:
            notes.append(ink.c(f"{a.unemployment:.0f}% of hands idle", ink.AMBER))
        short = [k for k, v in g.economy.shortage.items() if v > 0.1]
        if short:
            notes.append(ink.c(f"no {good(short[0]).name.lower()} to be had "
                               f"at the assize price", ink.BLOOD))
        if notes:
            self.say("  " + ink.c("the accounts ", ink.DIM) + " · ".join(notes))
        # Where the race actually stands. A game whose result you only learn
        # on the last day is one you could not have played differently.
        rows = g.pace()
        if rows and g.day > 60 and not g.over:
            left = max(0, g.goals.days - g.day)
            # Several of these are alternative ways to win rather than
            # clauses you are failing, so a path you have not started on is
            # dim rather than red. Red is only for a race you are in.
            live = [r for r in rows if r[1] > 0] or rows
            parts = []
            for what, now, want, land in live:
                short = land < want * 0.995
                started = now > 0
                parts.append(
                    ink.c(f"{what} {now:,.0f}", ink.PARCH if started else ink.DIM)
                    + ink.c(f"/{want:,.0f}", ink.DIM)
                    + ink.c(f" →{land:,.0f}",
                            (ink.BLOOD if short else ink.LEAF) if started
                            else ink.FAINT))
            self.say(f"  {ink.c('the race', ink.DIM)}     " + "   ".join(parts)
                     + ink.c(f"   ({left}d left, at this rate)", ink.DIM))
        busy = []
        if p.advancing:
            busy.append(f"climbing to the {AGES[p.age + 1].name} ({p.advancing}d)")
        if p.researching:
            busy.append(f"studying {TECHS[p.researching].name} "
                        f"({p.research_left:.0f}d)")
        if busy:
            self.say("  " + ";  ".join(busy))
        if g.soldiers:
            self.say(f"  under arms   {g.soldiers} soldiers"
                     + (f", {len(g.armies)} in the field" if g.armies else ""))
        for a in g.armies:
            if a.owner != "player":
                self.say(f"  ! {a.name} out of {self._name(a.home)}: {self._where(a)}")
        if g.caravans:
            self.say("")
            for c in g.caravans:
                self.say(f"  [{c.uid}] {c.name:<12} {self._where(c):<22} "
                         f"{c.load:>3.0f}/{c.capacity:<3.0f} {c.manifest(34):<34}"
                         f" {c.total_profit:+,.0f}c")
        self.say("",
                 f"  day's ledger   taxes {ink.coin(led.taxes, 7, True)}"
                 f"   trade {ink.coin(led.trade, 8, True)}"
                 f"   tribute {ink.coin(led.tribute, 6, True)}"
                 f"   interest {ink.coin(led.interest, 5, True)}",
                 f"                 wages {ink.coin(-led.wages, 7, True)}"
                 f"   upkeep {ink.coin(-led.upkeep, 7, True)}"
                 f"   carts {ink.coin(-led.caravans, 8, True)}"
                 f"   war {ink.coin(-led.war, 10, True)}",
                 f"                 net   {ink.coin(led.net, 7, True)}c")
        if len(g.history) > 3:
            self.say("  worth  " + ink.spark([h["worth"] for h in g.history]))
        for m in g.messages[-8:]:
            self.say("  " + ink.c("*", ink.FAINT) + " " + self._tint(m))
        if g.over:
            self.say(RULE, "  " + ink.c(g.over, ink.GOLD, bold=True), RULE)

    MESSAGE_TINTS = (
        (("WAR:", "ASSAULT", "RAID", "STORMED", "TAKEN", "under siege",
          "COFFERS", "unrest"), ink.BLOOD),
        (("bends the knee", "Learned:", "***", "finished", "Triumph",
          "Dominion"), ink.GOLD),
        (("News:", "marches on", "lays siege"), ink.AMBER),
    )

    def _tint(self, msg: str) -> str:
        for words, colour in self.MESSAGE_TINTS:
            if any(w in msg for w in words):
                return ink.c(msg, colour)
        return msg

    # ============================================================== commands
    def do(self, line: str) -> None:
        try:
            parts = _words(line)
        except ValueError as exc:
            return self.err(str(exc))
        if not parts:
            return
        cmd, args = parts[0].lower(), parts[1:]
        fn = COMMANDS.get(cmd)
        if not fn:
            matches = [c for c in COMMANDS if c.startswith(cmd)]
            if len(matches) == 1:
                fn = COMMANDS[matches[0]]
            else:
                return self.err(f"unknown command {cmd!r}; try `help`")
        try:
            fn(self, args)
        except (KeyError, ValueError, IndexError) as exc:
            self.err(str(exc))

    # -- individual commands --------------------------------------------
    def cmd_help(self, args: List[str]) -> None:
        """Everything there is, or `help <topic>` for one of them."""
        if args:
            topic = args[0].lower()
            if topic in ("win", "goal", "goals"):
                return self.say(self.win_text())
            if topic in HELP_TOPICS:
                return self.say(HELP_TOPICS[topic])
        self.say(HELP)

    def _where_name(self, g) -> str:
        """A settlement key a `post` line can actually be typed with."""
        return next(iter(g.world.settlements), "")

    def cmd_next(self, args: List[str]) -> None:
        """Let days pass. `next 7` is a week."""
        n = int(args[0]) if args else 1
        self.game.advance(n)
        self.status()
        self._autosave()

    def _autosave(self) -> None:
        if not self.autosave_path:
            return
        try:
            self.game.save(self.autosave_path)
        except OSError as exc:                       # pragma: no cover - disk
            self.err(f"could not autosave: {exc}")

    def cmd_autosave(self, args: List[str]) -> None:
        """Write the game out after every day from now on."""
        if args and args[0].lower() in ("off", "no", "stop"):
            self.autosave_path = ""
            return self.say("  autosave off")
        self.autosave_path = args[0] if args else "marchlands.autosave"
        self._autosave()
        self.say(f"  autosaving to {self.autosave_path} after every `next`")

    def cmd_scenarios(self, args: List[str]) -> None:
        """The maps you can start on, and the houses you can start as."""
        self.say(ink.head("SCENARIOS"))
        for i, key in enumerate(CAMPAIGN, 1):
            sc = SCENARIOS[key]
            here = "  <- you are here" if key == self.game.scenario else ""
            self.say(f"  {i}. {sc.key:<14} {sc.name:<20} {sc.years:g}y{here}")
            self.say(f"     {sc.blurb}")
        self.say("", "  start one with:  python3 -m marchlands --scenario <key>")

    def cmd_briefing(self, args: List[str]) -> None:
        """Why you are here, in the words it was put to you."""
        g = self.game
        sc = SCENARIOS.get(g.scenario)
        self.say(ink.head((sc.name if sc else g.scenario).upper()))
        for line in (g.briefing or "").splitlines():
            self.say(f"  {line}")
        self.say(self.win_text())

    def cmd_status(self, args: List[str]) -> None:
        """The day at a glance: purse, souls, towns, carts, the ledger."""
        self.status()

    def cmd_campaign(self, args: List[str]) -> None:
        """Where you are in the Marcher Chronicle, and what you are carrying."""
        run = self.run
        if run is None:
            return self.say(
                ink.head("THE MARCHER CHRONICLE"),
                ink.c("  You are playing a single game, not the campaign.",
                      ink.DIM),
                ink.c("  Start it with:  python3 -m marchlands --campaign",
                      ink.DIM))
        ch = run.current
        self.say(ink.head("THE MARCHER CHRONICLE",
                          f"chapter {min(run.chapter + 1, len(CHAPTERS))}"
                          f" of {len(CHAPTERS)}"))
        for line in run.standing():
            self.say(line)
        self.say("", f"  this chapter teaches {ink.c(ch.teaches, ink.GOLD)}")
        carry = run.carry
        self.say(f"  you brought    {ink.coin(carry.purse)}c, "
                 f"{len(carry.techs)} things your house had already worked out",
                 f"  renown         {carry.renown}")
        # The house is the part of a campaign that is actually a campaign, so
        # it belongs on the screen that is about the campaign.
        k = self.game.kin
        lord = k.lord
        if lord is not None:
            years = carry.days // C.DAYS_PER_YEAR
            best = max(kinly.SKILLS, key=lambda sk: lord.xp.get(sk, 0.0))
            reads = (f", {best} {lord.level(best)}" if lord.level(best)
                     else ", untried")
            self.say(f"  your house     {lord.name}, {lord.age(self.game.day)}"
                     f"{reads} · {len(k.living())} of the line"
                     + (f" · {years} years in" if years else ""))
            posted = [p for p in k.living() if p.post and p.post != "head"]
            if posted:
                self.say("  " + ink.c("               " + "; ".join(
                    f"{p.name} {p.doing(self._name)}" for p in posted[:3]),
                    ink.DIM))

    def cmd_chronicle(self, args: List[str]) -> None:
        """Your reign, read back to you."""
        g = self.game
        least = ROUTINE if args and args[0].lower() in ("all", "full") else NOTABLE
        entries = g.chronicle.read(least=least, limit=60)
        if not entries:
            return self.say(ink.head("THE CHRONICLE"),
                            ink.c("  Nothing worth writing down has happened yet.",
                                  ink.DIM))
        # The head used to count the whole book while the page showed only the
        # days worth telling, which made it look as though entries were lost.
        total = len(g.chronicle)
        right = (ink.count(total, "entry") if len(entries) == total
                 else f"{len(entries)} of {ink.count(total, 'entry')}")
        self.say(ink.head("THE CHRONICLE", right))
        chapter = None
        for e in entries:
            if e.chapter != chapter:
                chapter = e.chapter
                name = CHAPTERS_BY_KEY[chapter].name if chapter in CHAPTERS_BY_KEY \
                    else ""
                if name:
                    self.say("", ink.c(f"  -- {name} --", ink.GOLD))
            colour = ink.BONE if e.weight >= MOMENTOUS else ink.DIM
            self.say(f"  {ink.c(ink.pad(e.stamp(), 13), ink.PLUM)} "
                     + ink.c(e.text.strip("* "), colour))
        if len(entries) < total:
            self.say("", ink.c("  `chronicle all` reads the quiet days too.",
                               ink.DIM))

    def cmd_ask(self, args: List[str]) -> None:
        """Ask the town how it is. Somebody will tell you."""
        g = self.game
        s = self.settlement(self._resolve_here(args))
        how_many = 3 if args and args[-1].lower() in ("all", "more") else 2
        self.say(ink.head(f"IN THE STREET AT {s.name.upper()}",
                          f"mood {s.popularity:.0f}"))
        for who, said in voices.speak(s, g, voices.street_rng(s, g), how_many):
            self.say(f"  {ink.c(who, ink.DIM)}")
            rows = _wrap(said, 66)
            for i, line in enumerate(rows):
                head = "“" if i == 0 else " "
                tail = "”" if i == len(rows) - 1 else ""
                self.say(ink.c(f"    {head}{line}{tail}", ink.PARCH))
        self.say("", ink.c("  The same facts as `town`, from somebody who has "
                           "to live in it.", ink.DIM))

    def cmd_log(self, args: List[str]) -> None:
        """The last lines of what happened."""
        n = int(args[0]) if args else 15
        for m in self.game.events.log[-n:]:
            self.say(f"  * {m}")

    def cmd_save(self, args: List[str]) -> None:
        """Write the game to a file."""
        try:
            self.say("  " + self.game.save(args[0] if args else "marchlands.save"))
        except OSError as exc:
            self.err(f"could not write it: {exc}")

    def cmd_load(self, args: List[str]) -> None:
        """Open a saved game, and survive it not being one.

        A missing file used to take the whole session down with it, which is a
        poor way to find out you typed the name wrong -- and a poorer one if
        you had an hour in the game you were about to save.
        """
        path = args[0] if args else "marchlands.save"
        try:
            loaded = GameState.load(path)
        except FileNotFoundError:
            return self.err(f"no saved game at {path}")
        except OSError as exc:
            # Everything else the filesystem can say: a directory, a bad
            # permission, a dead symlink. All of it is "cannot read that".
            return self.err(f"cannot read {path}: {exc.strerror or exc}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self.err(f"{path} is not a saved game -- it is not even JSON")
        except (KeyError, TypeError, ValueError) as exc:
            return self.err(f"{path} is damaged or from another version ({exc})")
        if not loaded.world.settlements:
            return self.err(f"{path} has no holding in it; the game is unchanged")
        self.game = loaded
        self.here = next(iter(self.game.world.settlements))
        self.say(f"  loaded {path}")
        self.status()

    def cmd_quit(self, args: List[str]) -> None:
        """Leave. Nothing is written unless you asked for it."""
        self.quit = True


COMMANDS = {
    "court": Console.cmd_court, "standing": Console.cmd_court,
    "ally": Console.cmd_ally, "alliance": Console.cmd_ally,
    "befriend": Console.cmd_befriend, "friend": Console.cmd_befriend,
    "call": Console.cmd_call,
    "castle": Console.cmd_castle, "keep": Console.cmd_castle,
    "wall": Console.cmd_wall, "tower": Console.cmd_tower,
    "gate": Console.cmd_gate, "moat": Console.cmd_moat,
    "pitch": Console.cmd_pitchditch, "pits": Console.cmd_pits,
    "unwall": Console.cmd_unwall,
    "help": Console.cmd_help, "?": Console.cmd_help,
    "next": Console.cmd_next, "n": Console.cmd_next, "wait": Console.cmd_next,
    "status": Console.cmd_status, "s": Console.cmd_status,
    "town": Console.cmd_town, "stores": Console.cmd_stores,
    "view": Console.cmd_view, "plan": Console.cmd_view, "v": Console.cmd_view,
    "watch": Console.cmd_watch,
    "market": Console.cmd_market, "prices": Console.cmd_prices,
    "chain": Console.cmd_chain, "buildings": Console.cmd_buildings,
    "info": Console.cmd_info, "build": Console.cmd_build, "raze": Console.cmd_raze,
    "close": Console.cmd_close, "ration": Console.cmd_ration,
    "work": Console.cmd_work, "hands": Console.cmd_work, "tax": Console.cmd_tax,
    "staff": Console.cmd_staff, "pin": Console.cmd_staff, "move": Console.cmd_move,
    "rest": Console.cmd_rest,
    "split": Console.cmd_split, "detach": Console.cmd_split,
    "join": Console.cmd_join, "merge": Console.cmd_join,
    "garrison": Console.cmd_garrison, "found": Console.cmd_found,
    "units": Console.cmd_units, "recruit": Console.cmd_recruit,
    "host": Console.cmd_host, "army": Console.cmd_army, "armies": Console.cmd_army,
    "march": Console.cmd_march, "recall": Console.cmd_recall,
    "siege": Console.cmd_siege, "plans": Console.cmd_plans,
    "raid": Console.cmd_raid, "relics": Console.cmd_relics,
    "lord": Console.cmd_lord, "chronicle": Console.cmd_chronicle,
    "kin": Console.cmd_kin, "house": Console.cmd_kin, "family": Console.cmd_kin,
    "ask": Console.cmd_ask, "street": Console.cmd_ask, "listen": Console.cmd_ask,
    "season": Console.cmd_season, "standings": Console.cmd_season,
    "table": Console.cmd_season, "draft": Console.cmd_draft,
    "economy": Console.cmd_economy, "accounts": Console.cmd_economy,
    "margin": Console.cmd_margin, "surplus": Console.cmd_surplus,
    "advantage": Console.cmd_advantage, "mint": Console.cmd_mint,
    "assize": Console.cmd_assize, "decree": Console.cmd_assize,
    "post": Console.cmd_post, "posts": Console.cmd_post,
    "marry": Console.cmd_marry, "match": Console.cmd_marry,
    "estates": Console.cmd_estates, "privileges": Console.cmd_estates,
    "feats": Console.cmd_feats, "achievements": Console.cmd_feats,
    "missions": Console.cmd_missions, "roll": Console.cmd_missions,
    "order": Console.cmd_order, "orders": Console.cmd_order,
    "ground": Console.cmd_ground, "weather": Console.cmd_ground,
    # Not "gate": that is the gatehouse you lay in the wall, and a second
    # "gate" here silently replaced it -- the drawbar's gate tool asked the
    # sortie odds of a coordinate. tests/test_verbs.py keeps the keys unique.
    "odds": Console.cmd_sortie_odds,
    "gates": Console.cmd_gates, "quarantine": Console.cmd_gates,
    "battle": Console.cmd_battle, "fight": Console.cmd_battle,
    "storm": Console.cmd_battle,
    "herds": Console.cmd_herds, "flock": Console.cmd_herds,
    "beasts": Console.cmd_herds, "livestock": Console.cmd_herds,
    "restock": Console.cmd_herds,
    "water": Console.cmd_water, "rivers": Console.cmd_water,
    "ford": Console.cmd_water, "fords": Console.cmd_water,
    "bridge": Console.cmd_water, "bridges": Console.cmd_water,
    "sickness": Console.cmd_gates, "plague": Console.cmd_gates,
    "torch": Console.cmd_torch, "wagons": Console.cmd_torch,
    "baggage": Console.cmd_torch,
    "victual": Console.cmd_victual, "supply": Console.cmd_victual,
    "provision": Console.cmd_victual,
    "sally": Console.cmd_sally, "sortie": Console.cmd_sally,
    "shore": Console.cmd_shore, "mend": Console.cmd_shore,
    "campaign": Console.cmd_campaign, "chapter": Console.cmd_campaign,
    "standdown": Console.cmd_standdown, "war": Console.cmd_war,
    "battles": Console.cmd_battles, "age": Console.cmd_age,
    "gift": Console.cmd_gift, "truce": Console.cmd_truce,
    "demand": Console.cmd_demand,
    "tech": Console.cmd_tech, "research": Console.cmd_tech,
    "caravans": Console.cmd_caravans, "c": Console.cmd_caravans,
    "new": Console.cmd_new, "guards": Console.cmd_guards, "route": Console.cmd_route,
    "auto": Console.cmd_auto, "go": Console.cmd_go, "stop": Console.cmd_stop,
    "disband": Console.cmd_disband, "scan": Console.cmd_scan, "needs": Console.cmd_needs,
    "map": Console.cmd_map, "chart": Console.cmd_chart, "log": Console.cmd_log,
    "save": Console.cmd_save, "load": Console.cmd_load, "quit": Console.cmd_quit,
    "hint": Console.cmd_hint, "hints": Console.cmd_hint,
    "autosave": Console.cmd_autosave, "scenarios": Console.cmd_scenarios,
    "briefing": Console.cmd_briefing,
    "exit": Console.cmd_quit,
}

HELP = """
  THE DAY           next [n]        let n days pass        status / s
  YOUR TOWN         view / v        view flat              watch [days]
                    ask [town]      what the street says
  THE MARCH'S EAR   court [town]    who thinks what of you, and why
                    ally <town>     swear to a friendly lord
                    call yes/no     answer an ally who called you to his war
                    court buy       pay off the whole letter against you
  THE CASTLE        castle          the wall as you drew it
                    wall <x,y> <x,y>   tower <x,y>   gate <x,y>
                    moat / pitch / pits <x,y> <x,y>  unwall <x,y> <x,y>
                    town [name]     stores [town]
                    needs
                    build <key>     buildings [filter]     info <key>
                    close <id>      raze <id>
                    ration <level>  tax <level>            found [site]
  THE LONG GAME     age | age begin                        tech [key]
  THE MARKET        market <town>   prices <good>          chain <good>
                    scan [n]        map                    chart [metric]
  THE ROAD          caravans / c    caravan <id>           new [town] [name]
                    new ship [town] scan sea                auto <id>
                    go <id>         stop <id>
                    guards <id> <n> disband <id>
                    route <id> add <town> buy <good> <qty>[@max] sell <good> all[@min]
                    route <id> clear | show
  WAR               units           recruit <who> [n]      garrison [town]
                    host <town> <who> <n> ...              army [id]
                    march <id> <place>   recall <id>       standdown <id>
                    plans [place]   siege [<id> <plan>]   raid <id>
                    lord [<id>|home|ransom]     relics    chronicle
  YOUR HOUSE        kin [name]      post [<name> <post> [where]]
                    marry [<name> <town>]
  THE MARCH         season [past]   draft [<name>]
  THE ECONOMY       economy         margin [town]          surplus <good> [town]
                    advantage <good> [town]                mint [coin]
                    assize [<good> <price>|off]
                    war             battles [n]
                    gift <town> <coin>   truce <town> [days]   demand <town>
  ELSE              hint            briefing               scenarios
                    campaign        chronicle [all]
                    log [n]   save [file]   load [file]   autosave [file]   quit
                    help trade | help town | help war | help win
"""

def catalogue() -> list:
    """Every command, with the one line its own docstring gives it.

    Built from the registry rather than written out beside it, so a command
    that exists is a command the palette offers and a command that is renamed
    cannot go on being listed under the old name. Aliases are folded into the
    entry they point at.
    """
    # The first spelling in the registry is the real one; everything after it
    # is an alias, because that is the order they were written in and the
    # order somebody chose on purpose.
    by_fn: dict = {}
    for name, fn in COMMANDS.items():
        entry = by_fn.setdefault(fn, {"name": name, "aliases": [], "help": ""})
        if name != entry["name"]:
            entry["aliases"].append(name)
    out = []
    for fn, entry in by_fn.items():
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        entry["help"] = doc
        entry["aliases"] = sorted(entry["aliases"])
        out.append(entry)
    return sorted(out, key=lambda e: e["name"])


HELP_TOPICS = {
    "trade": f"""
  A price here is a function of stock. Buying lifts it, selling drops it, and
  a big order walks the curve the whole way -- so the second hundred bushels
  never fetch what the first did. Foreign tolls come off both ends of a deal,
  the road costs a day per {C.CARAVAN_BASE_SPEED:.0f} leagues, and bandits take a cut of whatever
  is in the cart.

  `scan` fills every candidate trade against copies of the real markets and
  reports coin per day after all of that. `auto <id>` puts a cart on the best
  one. Rival houses are running the same arithmetic, and every run they make
  narrows the gap you were about to take.
""",
    "town": """
  People need a roof, food, and a reason not to leave. Rations and taxes are
  the two levers. Mood sets productivity -- at 50 your workers run at full, at
  100 half again, below 18 they down tools altogether.

  Ale and a service are *coverage*, not cheer. An inn serves so many souls and
  a chapel so many, so a town that grows past them is a town half of which is
  drinking nothing: the same building, bought again, is what success costs.
  An inn with no ale in it, or no hand in it, serves nobody at all.

  Towns are made of timber and they burn. Ovens and kilns start fires by
  themselves now and then, raiders bring torches, and men who get over a wall
  set light to what is behind it. Everyone runs at a fire, so the water scales
  with the town -- but the hands carrying it are hands not working, and a
  building you save still wants days of work. Summer is the dangerous season.
  Past about eight roofs alight at once the town cannot find enough people and
  the fire is simply winning.

  Hands are shorter than jobs and always will be. `work` shows the queue --
  who gets people first when there are not enough -- and `work <building>
  first` reorders it. Something goes short every morning; you only get to
  choose what.

  Land is the real constraint. You have so many fertile, forest, hill and clay
  slots, and no settlement has all four in quantity. What you cannot grow you
  must buy, and what you have too much of is only worth what a cart can carry
  to somebody who wants it.
""",
    "water": """
  Rivers are lines on the map, and a road crosses one where the line crosses
  it. What that costs depends on how high the water is -- one stage for the
  whole march, and it is the last fortnight of weather rather than a roll:
  rain today is still in the river on Thursday, and it drains off from there.
  Spring is the melt and the worst of it; summer is a formality; a hard frost
  on low water turns a river into a road, which is why winter campaigns
  crossed.

  A ford in low water costs nothing, one running high costs a day and a half
  and risks part of the load, and one in flood costs three -- you ride
  upstream to somebody else's bridge.

  Which is what a bridge of your own is for. It costs 1,400c and forty-five
  days of masonry, it never floods, and every host that is not coming for you
  pays to walk over it. You can also throw it down, and the crossing you deny
  an army is the crossing you deny your own carts.

  `water` for today, `water <from> <to>` for a road, `water bridge <from>
  <to>` to build, `water throw <n>` to put one in the river.
""",
    "war": """
  Soldiers are made, not bought. A barracks turns coin and arms from your own
  workshops into men: spears from a poleturner, bows from a fletcher, swords
  from an armoury, plate from an armourer. Every soldier also walks out of the
  labour pool -- an army is paid for twice, once in coin and once in fields
  nobody is working.

  Spears break horse. Horse rides down bows and siege crews. Bows cut up foot.
  Foot in armour walks through bows. None of it matters while a wall is
  standing, which is what a castle is for.

  A castle is not a pool of hit points, it is a set of answers. A besieger
  picks a plan and each plan is beaten by a different thing you dug:

    batter    rams at the gate         answered by boiling oil
    breach    engines on the curtain   answered by towers shooting the crews
    escalade  ladders, no engines      answered by towers and a pitch ditch
    sap       a mine under a section   answered outright by water in a moat
    invest    sit down and starve it   answered by a full granary and a gate

  `plans <place>` reads a castle and says what each way in would meet there.
  `siege <host> <plan>` sets how a host of yours goes in -- and changing the
  plan starts the work over, so a mine half-dug is a mine wasted. Works stand
  on the wall line and the wall line is finite: every ditch is a tower you did
  not build.

  Lords grow bolder the richer you get, and they scheme against each other as
  well as against you: leave the march alone long enough and one of them will
  swallow his neighbours -- your sworn towns included. `war` shows who answers
  to whom and what each could field today.

  You need not take a castle to beat the man in it. `raid <host>` looses a host
  on the country instead: the fields stop being worked, the people leave, and
  a rival loses prosperity, which is the number his walls and his muster are
  both computed from. A garrison that is clearly stronger will come out after
  you, which is what a raider wants if he is stronger still.

  Five shrines stand out on the map with relics in them. Six days' standing
  lifts one; `relics` says where they are and who holds what. They pay
  offerings daily, four of them held for a hundred and twenty days wins the
  march, and the other lords send parties of their own.

  Your lord is a man. `lord` says where he is: in his hall he is worth mood
  and a stretch of wall, riding with a host he is worth a sixth of its
  strength and he is where the arrows are. He can fall, and he can be taken
  and ransomed, and the line is not endless.

  The Preaching Orders, in the third age, buy you friars: they talk men off a
  wall and onto your side, a few a day. What stops them is a church -- a
  defender's faith coverage is exactly what blunts preaching, so a great seat
  with a minster is deaf to it and a market town is not. Friars count as siege,
  which means cavalry ride them down.

  You do not see the march; you see what you last looked at. Your carts are
  your intelligence service. `war` reports what you know and how old it is, and
  says plainly when you have never sent anyone -- and old word always
  understates a lord, because he grows while you are not watching.

  You need not meet all of it with soldiers. A `gift` cools a temper, a `truce`
  buys a fixed number of quiet days outright, and a `demand` squeezes tribute
  out of a lord too weak to refuse -- and is remembered by one who is not.

  Take a town and it bends the knee: no tolls, daily tribute, and every other
  lord one step angrier. Five towns sworn to you wins the game outright.

  A storming is not the end. The keep is thrown down, the town gutted, and you
  start again from whatever else you hold -- which is the best argument there
  is for founding a second settlement before you need one. You are only
  finished when there is nowhere left.
""",
}


def play_campaign(run, *, out=sys.stdout, script: Optional[Sequence[str]] = None,
                  save_to: Optional[str] = None):
    """Play the Marcher Chronicle through, chapter after chapter.

    Each chapter is an ordinary game with its own terms. What makes it a
    campaign is what crosses between them: the purse, what the house has
    worked out, the lord and what is left of his line, and the chronicle,
    which by the last chapter is the only record of how you got there.
    """
    con = None
    while not run.done:
        ch = run.current
        g = run.begin()
        con = Console(g, out=out)
        con.run = run
        con.say("")
        con.say(ink.head(ch.name.upper(),
                         f"chapter {run.chapter + 1} of {len(CHAPTERS)}"))
        for line in (g.briefing or "").splitlines():
            con.say(f"  {line}")
        if run.carry.purse:
            con.say("", ink.c(f"  You bring {run.carry.purse:,.0f}c and "
                              f"{len(run.carry.techs)} things your house already "
                              f"knows.", ink.DIM))
        con.say("")
        con.status()
        con.say("", "  `campaign` for where you are, `chronicle` for how you got "
                    "here, `hint` if you are stuck.")
        _drive(con, script)
        won, epilogue = run.finish(con.game)
        con.say("")
        con.say(ink.head("END OF CHAPTER", ch.name))
        con.say(f"  {con.game.over}")
        con.say("")
        con.say("  " + ink.c(epilogue, ink.GOLD if won else ink.AMBER))
        if save_to:
            con.say("  " + run.save(save_to))
        if con.quit or script is not None:
            break
    if run.done and con is not None:
        con.say("")
        con.say(ink.head("THE MARCHER CHRONICLE", "complete"))
        for line in run.standing():
            con.say(line)
        con.say("", f"  renown {run.carry.renown} of a possible "
                    f"{3 * len(CHAPTERS)}")
        con.say("", ink.c("  `chronicle` reads the whole of it back.", ink.DIM))
    return con


def _drive(con, script: Optional[Sequence[str]]) -> None:
    """Run one chapter to its end, from a script or from a person."""
    if script is not None:
        for line in script:
            con.say(f"\n> {line}")
            con.do(line)
            if con.quit or con.game.over:
                return
        return
    while not con.quit and not con.game.over:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            con.quit = True
            return
        if line:
            con.do(line)


def play(game: Optional[GameState] = None, script: Optional[Sequence[str]] = None,
         out=sys.stdout, autosave: Optional[str] = None) -> Console:
    con = Console(game or start_scenario(), out=out)
    if autosave:
        con.autosave_path = autosave
    con.say(BANNER)
    sc = SCENARIOS.get(con.game.scenario)
    if sc:
        con.say(f"  {sc.name.upper()}")
    for line in (con.game.briefing or "").splitlines():
        con.say(f"  {line}")
    con.say("")
    con.status()
    con.say("", "  `hint` if you are not sure what to do next; `help` for the rest.")
    if script is not None:
        for line in script:
            con.say(f"\n> {line}")
            con.do(line)
            if con.quit:
                break
        return con
    while not con.quit:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line:
            con.do(line)
    return con


BANNER = r"""
   __  __              _    _                 _
  |  \/  |__ _ _ _ __ | |_ | |__ _ _ _  __ _ | |___
  | |\/| / _` | '_/ _|| ' \| / _` | ' \/ _` || (_-<
  |_|  |_\__,_|_| \__||_||_|_\__,_|_||_\__,_||_/__/

  A holding, a hinterland, and seven towns that each want
  what somebody else has. Type `help` to begin.
"""
