"""A window onto the game, served from the standard library and nothing else.

The terminal view has place and motion and it is still glyphs. This is the
same game with a picture on it: a small HTTP server that hands the browser the
state, and a canvas that draws a town out of it -- timber frames, thatch,
stone, water, smoke, weather, people in the streets.

Everything is drawn, nothing is loaded. There are no images in this
repository and there is no dependency list, because the roofs are vector paths
and the rule that this game installs with nothing is worth more than a texture
atlas.

    python3 -m marchlands --web

The browser is a view and a keyboard. Every command the console takes works
here, because it is the same Console underneath.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from typing import Tuple
from urllib.parse import parse_qs, urlparse

from .cli import Console, catalogue
from . import config as C
from .economics import marginal_hands
from .kin import SKILLS
from .league import PLAYER as LEAGUE_PLAYER
from . import cartography as carto
from . import chancery
from . import culture as cultures
from . import keep as keeps
from . import voices
from .layout import plan_for


def _static_dir() -> str:
    """Where the page, its stylesheet and its scripts actually are.

    Not simply `__file__`'s directory. A PyInstaller one-file build unpacks
    everything into a temporary directory and points `sys._MEIPASS` at it, so
    a frozen Marchlands.exe that resolved this the obvious way would start,
    serve index.html from a path that does not exist, and show a blank page --
    which is the same failure `pyproject.toml` already warns about for wheels,
    arrived at by a different route.
    """
    here = getattr(sys, "_MEIPASS", None)
    if here:
        bundled = os.path.join(here, "marchlands", "static")
        if os.path.isdir(bundled):
            return bundled
        return os.path.join(here, "static")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


STATIC = _static_dir()

TYPES = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8",
         ".json": "application/json"}


def march(game, here: str, good: str = "bread") -> dict:
    """The map the trade layer actually lives on.

    The town view shows the part of the game that is not the point. This is the
    point: who is where, what the roads between them are worth, where your
    carts have got to this morning, and which two places are currently further
    apart in price than the distance between them can justify.
    """
    w = game.world
    nodes = []
    for key, (x, y) in w.coords.items():
        if key in w.settlements:
            s = w.settlements[key]
            kind, name, who = "mine", s.name, "you"
            stock = s.market.stock.get(good, 0.0)
            price = s.market.bid(good)
        elif key in w.towns:
            t = w.towns[key]
            kind = "vassal" if t.mine else "town"
            name, who = t.name, (t.lord or "")
            stock, price = t.market.stock.get(good, 0.0), t.market.bid(good)
        elif key in w.shrines:
            sh = w.shrines[key]
            kind = "shrine"
            name = sh.short or sh.name
            who = ("yours" if sh.holder == "player"
                   else w.node_name(sh.holder) if sh.holder else "")
            stock = price = 0.0
        else:
            continue
        # Prices travel: merchants talk, and `prices` has always listed every
        # market. What does not travel is how many men a lord has behind his
        # wall, so that -- and only that -- is what the fog covers here.
        seen, age = game.known(key) if key in w.towns else ({}, 0)
        from .military import host_strength
        host = (round(host_strength(game.believed_host(key)))
                if key in w.towns and age >= 0 else None)
        nodes.append({"key": key, "name": name, "x": x, "y": y, "kind": kind,
                      "who": who, "port": w.is_port(key),
                      "price": round(price, 2), "stock": round(stock),
                      "known": age, "host": host,
                      "walls": round(seen.get("wall_hp", 0.0)) if seen else None,
                      "here": key == here})
    for key, site in w.sites.items():
        nodes.append({"key": key, "name": site.name, "x": site.x, "y": site.y,
                      "kind": "site", "who": "", "port": False,
                      "price": 0.0, "stock": 0, "known": 0, "here": False})

    carts = []
    for c in game.caravans:
        frm = c.at or (c.route[c.leg - 1].node if c.route and c.leg else c.home)
        to = c.bound_for or c.at or c.home
        total = max(1.0, w.distance(frm, to) / max(c.speed, 1.0)) if frm and to else 1.0
        carts.append({
            "uid": c.uid, "name": c.name, "kind": c.kind,
            "from": frm, "to": to,
            "done": 0.0 if not c.bound_for else
                    max(0.0, min(1.0, 1.0 - c.days_left / total)),
            "moving": bool(c.bound_for), "running": c.running,
            "load": round(c.load), "capacity": round(c.capacity),
            "cargo": {k: round(v) for k, v in c.cargo.items() if v >= 1},
            "profit": round(c.total_profit),
        })

    runs = []
    seat = here if here in w.settlements else next(iter(w.settlements))
    try:
        from .advisor import scan as scan_trades
        sails = any(s.count("harbour") for s in w.settlements.values())
        for opp in scan_trades(w, seat, top=4, sails=sails, steps=6):
            goods = {}
            for leg in (opp.out, opp.back):
                if leg:
                    for k, v in leg.cargo.items():
                        goods[k] = goods.get(k, 0.0) + v
            runs.append({"from": opp.frm, "to": opp.to,
                         "per_day": round(opp.per_day, 1),
                         "days": round(opp.days, 1),
                         "goods": [k for k, _v in sorted(
                             goods.items(), key=lambda kv: -kv[1])[:3]]})
    except Exception:
        runs = []          # the map is worth drawing even if the scan is not
    # The schedule belongs on the map more than anywhere else: an arrow from
    # a lord to the place he has said he is going is the whole of it.
    fixtures = [{"who": f.who, "target": f.target,
                 "at_you": f.target in w.settlements}
                for f in game.league.season.fixtures if not f.done]
    return {"good": good, "nodes": nodes, "carts": carts, "runs": runs,
            "fixtures": fixtures}


def options(game, here: str = "") -> dict:
    """What the town could raise today, and why not where not.

    The page never decides any of this. It asks, it draws the answer, and when
    you click it sends the same `build cottage` a person would have typed --
    so there is exactly one place the rules live, and it is not in JavaScript.
    """
    from .buildings import BUILDINGS
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    out = []
    for bkey, spec in BUILDINGS.items():
        ok, why = s.can_build(bkey, game.progress)
        coin = spec.build_cost.get("coin", 0.0)
        if ok and game.treasury < coin:
            ok, why = False, f"costs {coin:,.0f}c; you have {game.treasury:,.0f}c"
        out.append({
            "key": bkey, "name": spec.name, "category": spec.category,
            "terrain": spec.terrain, "age": spec.age, "jobs": spec.jobs,
            "coin": coin, "days": spec.build_days,
            "goods": {k: v for k, v in spec.build_cost.items() if k != "coin"},
            "makes": dict(spec.outputs), "wants": dict(spec.inputs),
            "note": spec.note, "can": ok, "why": "" if ok else why,
        })
    out.sort(key=lambda b: (not b["can"], b["age"], b["coin"]))
    free = {t: s.slots_free(t) for t in
            ("fertile", "forest", "hills", "clay", "coast", "urban", "rampart")}
    return {"here": key, "slots": free, "buildings": out}


def _best_skill(person) -> str:
    """What one of yours is known for, or nothing if they have not been used."""
    best = max(SKILLS, key=lambda sk: person.xp.get(sk, 0.0))
    return f"{best} {person.level(best)}" if person.level(best) > 0 else ""


def _save_path() -> str:
    """Where a game goes when nobody has said where.

    Beside the executable for a packaged build, so a player who double-clicked
    something can find their save without knowing what a working directory is;
    beside the checkout otherwise.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "marchlands.save")
    return os.path.abspath("marchlands.save")


#: Whether the browser should open on the front door rather than straight into
#: a game. True when nobody chose anything -- a packaged build somebody
#: double-clicked, or a bare `--web` -- and False the moment they have, because
#: a player who typed `--scenario iron_marches` has already answered the only
#: question that screen asks.
SHOW_FRONT = False


def _front_door(console, route: str, body: dict) -> dict:
    """Start, save or resume a game without anybody typing a command.

    The three things a person who double-clicked an icon expects to be able
    to do, and the three that were console-only: `save`, `load` and choosing
    what to play at all.
    """
    global SHOW_FRONT
    from .scenarios import start
    path = body.get("path") or _save_path()
    if route == "/save":
        try:
            console.game.save(path)
        except OSError as exc:
            return {"error": f"could not write it: {exc}"}
        return {"said": f"saved to {path}", "saved": True}
    if route == "/load":
        try:
            from .engine import GameState
            console.game = GameState.load(path)
        except (OSError, ValueError, KeyError) as exc:
            return {"error": f"could not open it: {exc}"}
        console.here = next(iter(console.game.world.settlements))
        SHOW_FRONT = False
        return {"said": "picked up where you left it",
                "state": snapshot(console.game, console.here)}
    house = body.get("house", "plough")
    seed = int(body.get("seed") or 7)
    region = body.get("region") or ""
    try:
        if region:
            from .scenario import drawn_game
            console.game = drawn_game(region, seed=seed, house=house)
        else:
            console.game = start(body.get("scenario", "marchlands"),
                                 seed=seed, house=house)
    except KeyError as exc:
        return {"error": str(exc)}
    console.here = next(iter(console.game.world.settlements))
    SHOW_FRONT = False
    return {"said": console.game.briefing,
            "state": snapshot(console.game, console.here)}


def _at(name: str, value: float) -> "carto.Dials":
    return carto.Dials(**{name: value})


def _dials_from(q: dict) -> "carto.Dials":
    """Dials off a query string, starting from the region's own."""
    region = q.get("region", [carto.DEFAULT_REGION])[0]
    d = carto.REGIONS.get(region, carto.REGIONS[carto.DEFAULT_REGION]).dials
    parts = [f"{n}={q[n][0]}" for n in carto.DIAL_NAMES if n in q]
    return carto.parse_dials(",".join(parts), d) if parts else d


def _preview(plan) -> dict:
    """A drawn march, small enough to send on every twitch of a slider."""
    return {
        "region": plan.region, "note": plan.note, "seed": plan.seed,
        "dials": plan.dials.as_dict(),
        "words": [{"dial": n, "value": v, "says": w}
                  for n, v, w in carto.describe(plan.dials)],
        "home": {"name": plan.home_name, "terrain": dict(plan.home_terrain)},
        "towns": [{"name": t["name"], "x": t["x"], "y": t["y"],
                   "lord": t["lord"], "blurb": t["blurb"],
                   "port": t["port"], "walls": t["walls"],
                   "culture": cultures.for_ground(t["ground"]),
                   "sells": sorted(t["produces"], key=t["produces"].get,
                                   reverse=True)[:3],
                   "buys": sorted(t["consumes"], key=t["consumes"].get,
                                  reverse=True)[:3]}
                  for t in plan.towns],
        "sites": [{"name": s["name"], "x": s["x"], "y": s["y"]}
                  for s in plan.sites],
        "shrines": [{"name": s["name"], "x": s["x"], "y": s["y"]}
                    for s in plan.shrines],
    }


def _idiom(c) -> dict:
    """One idiom, as four channels the renderer can act on: what the walls
    are, what the roofs are, how steep, and what colour the street is."""
    return {"key": c.key, "name": c.name, "blurb": c.blurb,
            "walls": dict(c.walls), "roofs": dict(c.roofs),
            "pitch": c.pitch, "gable": c.gable, "stretch": c.stretch,
            "tone": c.tone, "tint": c.tint, "tint_by": c.tint_by,
            "roof_tint": c.roof_tint, "roof_by": c.roof_by}


def _culture(s) -> dict:
    return _idiom(s.idiom())


def _court(game) -> dict:
    """The march as a web of opinion, for the map that draws it."""
    c, day = game.court, game.day
    towns = {}
    for key, t in game.world.towns.items():
        if t.mine:
            continue
        view = c.opinion(key, day)
        ground = c.ground_for(key, day)
        towns[key] = {
            "name": t.name, "lord": t.lord,
            "opinion": round(view, 1), "temper": chancery.temper(view),
            "offence": round(c.offence(key, day), 1),
            "culture": chancery and t.culture or t.culture,
            "signed": key in c.coalition,
            "allied": key in c.allies,
            "claim": key in c.claims,
            "ground": ground.label if ground else "",
            "why": [{"what": w, "by": round(v, 1)}
                    for w, v, _d in c.reasons(key, day)[:4]],
        }
    called = c.called
    return {
        "towns": towns,
        "coalition": list(c.coalition),
        "bar": chancery.COALITION_BAR,
        "price": round(c.coalition_price(day)),
        "called": {"town": called[0],
                   "days": game.CALL_DAYS - (day - called[1])} if called else None,
    }


def _castle(s) -> dict:
    """What the wall is, for the bar you draw it with."""
    drawing = s.plan()
    r = keeps.read(drawing)
    return {
        "yards": r.yards, "stone": r.stone, "timber": r.timber,
        "towers": r.towers, "gates": r.gates, "shut": r.shut,
        "inside": r.inside, "covered": r.covered, "depth": r.depth,
        "weak": [{"x": x, "y": y} for x, y in r.weak],
        "side": r.weak_side,
        "per_yard": round(s.per_yard(), 2),
        "outside": len(s.outside_the_wall()),
        "own": bool(s.castle.own),
        "hand": {k: v for k, v in keeps.unlaid(s.buildings, drawing).items()
                 if v > 0},
    }


def snapshot(game, here: str = "") -> dict:
    """Everything the picture needs, and nothing it does not."""
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    led = game.ledger
    return {
        "day": game.day,
        "date": game.date_str(),
        "year": game.year,
        "month": game.month,
        "season": game.season,
        "over": game.over,
        "chapter": game.chapter,
        "treasury": round(game.treasury, 1),
        "net_worth": round(game.net_worth(), 1),
        # Where the race stands, projected. The same reading the console
        # gives, because two interfaces that disagree about whether you are
        # winning are worse than one.
        # The table, and who has said they are coming. Both halves of a league:
        # where everyone stands, and what is on the schedule.
        "league": {
            "year": game.league.season.year,
            "place": game.league.season.place(LEAGUE_PLAYER),
            "table": [{"key": r.key, "name": r.name or r.key, "lord": r.lord,
                       "towns": r.towns, "won": r.won, "lost": r.lost,
                       "muster": round(r.muster),
                       "me": r.key == LEAGUE_PLAYER}
                      for r in game.league.season.table()],
            "fixtures": [{"who": f.who, "target": f.target,
                          "at_you": f.target in game.world.settlements}
                         for f in game.league.season.fixtures if not f.done],
            "clock": game.league.season.on_the_clock(),
            "left": len(game.league.season.undrafted()),
        },
        "pace": [{"what": w, "now": round(n, 1), "want": round(k, 1),
                  "land": round(l, 1)} for w, n, k, l in game.pace()],
        "goals": {"net_worth": game.goals.net_worth,
                  "population": game.goals.population,
                  "towns": game.goals.towns,
                  "days": game.goals.days,
                  "paths": list(game.goals.paths)},
        "lord": {"name": game.lord.name,
                 "standing": game.lord.standing(game.world.node_name)},
        # The house, small enough to sit in a panel and complete enough to
        # follow: who they are, how old, what they are doing, what it made them.
        "kin": [{"name": p.name,
                 "age": p.age(game.day),
                 "head": p.uid == game.kin.head,
                 "doing": p.doing(game.world.node_name),
                 "skill": _best_skill(p)}
                for p in sorted(game.kin.living(),
                                key=lambda q: (q.uid != game.kin.head, q.born))],
        "reputation": (game.kin.lord.reputation() if game.kin.lord else []),
        # The macro reading. Four numbers, because a dashboard with twenty is
        # a dashboard nobody reads.
        "accounts": {
            "cpi": round(game.accounts.cpi, 1),
            "inflation": round(game.accounts.inflation, 1),
            "unemployment": round(game.accounts.unemployment, 1),
            "real_purse": round(100.0 * game.treasury
                                / max(game.accounts.cpi, 1e-9), 1),
            "minted": round(game.economy.minted, 1),
            "short": [{"good": k, "by": round(v, 3)}
                      for k, v in game.economy.shortage.items() if v > 0.01],
        },
        "here": key,
        # What this place is built out of, so the renderer can draw it in its
        # own idiom rather than in the one idiom it used to have.
        "culture": _culture(s),
        # Every idiom, not only yours -- so a town on the march map can be
        # drawn in its own. Seeing whose town it is from the roofline is the
        # whole point of having more than one.
        "idioms": {c.key: _idiom(c) for c in cultures.CULTURES.values()},
        # The politics: who thinks what, who has signed, and who is waiting
        # on an answer. The same reading `court` prints.
        "court": _court(game),
        # The castle, read: what you drew and what a besieger makes of it.
        # The same numbers `castle` prints, because there is one answer.
        "castle": _castle(s),
        # What the street would say, for a roof somebody clicks on. The same
        # facts as the mood breakdown, from somebody who has to live in it.
        "street": [{"who": who, "said": said}
                   for who, said in voices.speak(s, game, voices.street_rng(s, game), 2)],
        # What the next hand in each shed would be worth, so a roof you click
        # can tell you whether it is paying for itself. The same reading
        # `margin` gives, attached to the thing it is about.
        "margin": {r.uid: {"net": round(r.net, 2), "wage": C.WAGE,
                           "staffed": r.staffed, "jobs": r.jobs}
                   for r in marginal_hands(s)},
        "settlements": list(game.world.settlements),
        "town": {
            "name": s.name,
            "population": round(s.population, 1),
            "housing": round(s.housing(game.progress), 1),
            "popularity": round(s.popularity, 1),
            "workforce": round(s.workforce, 1),
            "employed": round(s.employed, 1),
            "soldiers": s.soldiers,
            "wall_hp": round(s.wall_hp, 1),
            "wall_max": round(s.wall_max(game.progress), 1),
            "besieged": s.besieged,
            "raided": s.raided,
            "blockaded": s.blockaded,
            "fires": len(s.fires.blazes),
            "rations": s.ration_level,
            "tax": s.tax_level,
            "mood": [{"what": k, "by": round(v, 1)} for k, v in s.mood_factors(
                game.progress) if v],
        },
        "ledger": {"taxes": round(led.taxes, 1), "trade": round(led.trade, 1),
                   "tribute": round(led.tribute, 1), "wages": round(led.wages, 1),
                   "upkeep": round(led.upkeep, 1), "net": round(led.net, 1)},
        "plan": plan_for(s).to_dict(),
        "caravans": len(game.caravans),
        "age": game.progress.age_name(),
        "relics": game.relics_held(),
    }


class Handler(BaseHTTPRequestHandler):
    console: Console = None            # set on the server before serving
    lock = threading.Lock()

    def log_message(self, fmt, *args) -> None:      # quiet by default
        pass

    # ------------------------------------------------------------- plumbing
    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), TYPES[".json"])

    def _static(self, path: str) -> None:
        name = os.path.basename(path) or "index.html"
        full = os.path.join(STATIC, name)
        if not os.path.isfile(full):
            return self._send(404, b"no such thing", "text/plain")
        ext = os.path.splitext(name)[1]
        with open(full, "rb") as fh:
            self._send(200, fh.read(), TYPES.get(ext, "text/plain"))

    # --------------------------------------------------------------- routes
    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            return self._static("index.html")
        if route == "/favicon.ico":
            return self._send(200, b"", "image/x-icon")
        if route == "/state":
            with self.lock:
                return self._json(snapshot(self.console.game, self.console.here))
        if route == "/commands":
            # Straight off the console's own registry, so the palette cannot
            # drift from what the game will actually accept.
            return self._json(catalogue())
        if route == "/options":
            with self.lock:
                return self._json(options(self.console.game, self.console.here))
        if route == "/march":
            good = (urlparse(self.path).query.split("good=")[-1].split("&")[0]
                    if "good=" in self.path else "bread")
            with self.lock:
                return self._json(march(self.console.game, self.console.here, good))
        if route == "/front":
            # What the front door needs: who you can be, what you can play,
            # and whether there is a game waiting to be picked back up. A
            # packaged build has to be able to start without anybody typing,
            # and this is everything that screen asks for.
            from .scenarios import CAMPAIGN, SCENARIOS
            from .tech import HOUSES
            save = _save_path()
            return self._json({
                "houses": [{"key": k, "name": h.name, "blurb": h.blurb}
                           for k, h in HOUSES.items()],
                "scenarios": [{"key": k, "name": SCENARIOS[k].name,
                               "blurb": SCENARIOS[k].blurb,
                               "years": SCENARIOS[k].years}
                              for k in CAMPAIGN if k in SCENARIOS],
                "regions": [{"key": r.key, "name": r.name, "note": r.note}
                            for r in carto.REGIONS.values()],
                "saved": os.path.exists(save),
                "save_path": save,
                "open": SHOW_FRONT,
            })
        if route == "/regions":
            # Everything the slider screen needs to draw itself: the dials,
            # what each setting is called in words, and the six real places.
            return self._json({
                "dials": list(carto.DIAL_NAMES),
                "regions": [
                    {"key": r.key, "name": r.name, "note": r.note,
                     "dials": r.dials.as_dict()}
                    for r in carto.REGIONS.values()],
                "words": {name: [carto.describe(_at(name, v))[0][2]
                                 for v in (0.0, 0.3, 0.6, 1.0)]
                          for name in carto.DIAL_NAMES if name != "towns"},
            })
        if route == "/draw":
            # A preview. Drawing is cheap and starting a game is not, so the
            # sliders can be moved as fast as anybody likes and the country
            # redraws under them without a game being made at all.
            q = parse_qs(urlparse(self.path).query)
            try:
                dials = _dials_from(q)
            except KeyError as exc:
                return self._json({"error": str(exc)})
            plan = carto.draw(q.get("region", [carto.DEFAULT_REGION])[0],
                              int(q.get("seed", ["7"])[0]), dials)
            return self._json(_preview(plan))
        if route == "/chronicle":
            with self.lock:
                g = self.console.game
                return self._json({"entries": [
                    {"stamp": e.stamp(), "text": e.text.strip("* "),
                     "weight": e.weight, "chapter": e.chapter}
                    for e in g.chronicle.read(limit=80)]})
        return self._static(route)

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/march-here":
            # Draw the country the sliders are set to, and play it. The
            # console keeps the same identity -- it is the same seat at the
            # same table, looking at a different country.
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            q = {k: [str(v)] for k, v in body.items()}
            try:
                dials = _dials_from(q)
            except KeyError as exc:
                return self._json({"error": str(exc)})
            with self.lock:
                from .scenario import drawn_game
                self.console.game = drawn_game(
                    body.get("region", carto.DEFAULT_REGION),
                    seed=int(body.get("seed", 7)),
                    house=body.get("house", "plough"), dials=dials)
                self.console.here = next(iter(self.console.game.world.settlements))
                return self._json({
                    "said": self.console.game.briefing,
                    "state": snapshot(self.console.game, self.console.here)})
        route = urlparse(self.path).path
        if route in ("/new", "/save", "/load"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            with self.lock:
                return self._json(_front_door(self.console, route, body))
        if route != "/do":
            return self._send(404, b"no such thing", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "that was not json"}, 400)
        line = str(payload.get("line", ""))[:400]
        with self.lock:
            said = run_command(self.console, line)
            state = snapshot(self.console.game, self.console.here)
        return self._json({"said": said, "state": state})


def run_command(console: Console, line: str) -> str:
    """Run one console command and capture what it said."""
    buffer = StringIO()
    was, console.out = console.out, buffer
    try:
        if line.strip():
            console.do(line)
    finally:
        console.out = was
    return buffer.getvalue()


class _Server(ThreadingHTTPServer):
    """A server that refuses to quietly share its port.

    `HTTPServer` sets SO_REUSEADDR, and that flag does not mean the same
    thing on both sides of the world. On Unix it only means "do not make me
    wait out TIME_WAIT". On Windows it means this socket may bind a port
    another program is *actively listening on*, after which the operating
    system hands each incoming connection to one of the two more or less
    arbitrarily.

    The consequence was not theoretical. The bind below cannot fail on
    Windows, so the port walk never runs, and a player who double-clicked
    Marchlands while anything else sat on 8731 got a browser window pointed
    at that other server -- in the case this was found from, a directory
    listing of their own home folder. Turning the flag off on Windows makes
    an occupied port raise, which is what the walk is for.
    """

    allow_reuse_address = os.name != "nt"


def serve(console: Console, host: str = "127.0.0.1", port: int = 8731,
          open_browser: bool = True) -> Tuple[ThreadingHTTPServer, str]:
    Handler.console = console
    # Somebody already on that port is the commonest way this fails, and a
    # traceback about EADDRINUSE is not an answer. Walk up a few and then let
    # the operating system pick.
    server = None
    for candidate in [port, port + 1, port + 2, port + 3, 0]:
        try:
            server = _Server((host, candidate), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"nothing free to listen on near port {port}")
    url = f"http://{host}:{server.server_address[1]}/"
    if open_browser:
        # A machine with no browser to open is not an error either.
        def _open() -> None:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Timer(0.6, _open).start()
    return server, url


def main(game=None, port: int = 8731, open_browser: bool = True,
         front: bool = False) -> int:
    global SHOW_FRONT
    SHOW_FRONT = front
    from .scenarios import start
    console = Console(game or start(), out=StringIO())
    server, url = serve(console, port=port, open_browser=open_browser)
    print(f"  Marchlands is at {url}")
    print("  ctrl-c to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        server.server_close()
    return 0
