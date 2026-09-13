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
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from typing import Tuple
from urllib.parse import urlparse

from .cli import Console, catalogue
from . import config as C
from .economics import marginal_hands
from .kin import SKILLS
from .layout import plan_for

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

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
    return {"good": good, "nodes": nodes, "carts": carts, "runs": runs}


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
        if route == "/chronicle":
            with self.lock:
                g = self.console.game
                return self._json({"entries": [
                    {"stamp": e.stamp(), "text": e.text.strip("* "),
                     "weight": e.weight, "chapter": e.chapter}
                    for e in g.chronicle.read(limit=80)]})
        return self._static(route)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/do":
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


def serve(console: Console, host: str = "127.0.0.1", port: int = 8731,
          open_browser: bool = True) -> Tuple[ThreadingHTTPServer, str]:
    Handler.console = console
    # Somebody already on that port is the commonest way this fails, and a
    # traceback about EADDRINUSE is not an answer. Walk up a few and then let
    # the operating system pick.
    server = None
    for candidate in [port, port + 1, port + 2, port + 3, 0]:
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
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


def main(game=None, port: int = 8731, open_browser: bool = True) -> int:
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
