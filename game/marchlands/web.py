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

from .cli import Console
from .layout import plan_for

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

TYPES = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8",
         ".json": "application/json"}


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
        "goals": {"net_worth": game.goals.net_worth,
                  "population": game.goals.population,
                  "towns": game.goals.towns,
                  "days": game.goals.days,
                  "paths": list(game.goals.paths)},
        "lord": {"name": game.lord.name, "standing": game.lord.standing()},
        "here": key,
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
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{server.server_address[1]}/"
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
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
