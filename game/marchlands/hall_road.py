"""The road: bridges and their tolls, carts and ships, and what you can see of the
march from where your people stand.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from . import config as C
from . import rivers as waters
from . import sight
from .military import BESIEGING, MARCHING, RAIDING
from .trade import CART, SHIP, Caravan


class RoadMixin:
    """GameState's road. Mixed into GameState; see engine.py."""

    #: What a host pays to walk over somebody else's bridge, per hundred men.
    #: Absurd and entirely real: an army on the march was a customer, and the
    #: man who held the crossing charged it. A host coming for YOU is not a
    #: customer, which is the distinction that makes it worth modelling.
    HOST_TOLL = 34.0

    def _bridge_toll(self, a, origin: str, target: str) -> List[str]:
        if a.owner == "player":
            return []
        hostile = target in self.world.settlements
        notes = []
        for r, x, y, bridge in self.world.crossings(origin, target):
            if bridge is None or bridge.owner != "player" or not bridge.standing:
                continue
            if hostile:
                # He is coming for you. He is not going to pay for the deck.
                notes.append(f"crosses your {bridge.name}")
                continue
            paid = self.HOST_TOLL * max(1.0, a.size / 100.0)
            self.treasury += paid
            notes.append(f"pays {paid:.0f}c at {bridge.name}")
        return notes

    def worst_unbridged(self) -> Optional[Tuple[str, str, "waters.River"]]:
        """The crossing your own running carts lose the most days at.

        One reader, used by the panel that offers the button and by the
        autoplayer that presses it. Two copies of "which crossing matters"
        is how the garrison rule went wrong, and the balance guard only
        measures what the autoplayer does -- so the two had better agree
        about what a good bridge is.
        """
        best: Optional[Tuple[str, str, waters.River]] = None
        for c in self.caravans:
            if not c.running or c.sails or len(c.route) < 2:
                continue
            for i, stop in enumerate(c.route):
                nxt = c.route[(i + 1) % len(c.route)]
                if nxt.node == stop.node:
                    continue
                if not (self.world.is_mine(stop.node)
                        or self.world.is_mine(nxt.node)):
                    continue
                for r, x, y, bridge in self.world.crossings(stop.node, nxt.node):
                    if bridge is not None:
                        continue
                    if best is None or r.ford_limit < best[2].ford_limit:
                        best = (stop.node, nxt.node, r)
        return best

    def bridges_of(self, owner: str = "player") -> List[waters.Bridge]:
        return [b for b in self.world.bridges if b.owner == owner]

    def build_bridge(self, a: str, b: str, river_key: str = "") -> str:
        """Put masons on a crossing between two named places.

        You do not choose a point on a map; you choose a road. That is the
        decision the player can actually reason about -- *this* is the leg my
        carts run and the water is out on it three weeks in four -- and the
        point falls out of the geometry.
        """
        a = self.world.resolve(a) or a
        b = self.world.resolve(b) or b
        if a not in self.world.coords or b not in self.world.coords:
            return "I do not know that road"
        # A player names a river, not a key. `water bridge aldworth marchand
        # perry` has to mean the Perry, because "r0" is not a word anybody
        # in this game has ever been shown.
        if river_key:
            named = next((r.key for r in self.world.waters()
                          if r.key == river_key
                          or r.name.lower().startswith(river_key.lower())), "")
            if not named:
                return f"no water called {river_key!r}"
            river_key = named
        found = self.world.bridge_at(a, b, river_key)
        if found is None:
            if river_key:
                return f"no {river_key} on the road from {self.world.node_name(a)}"
            return (f"the road from {self.world.node_name(a)} to "
                    f"{self.world.node_name(b)} crosses no water")
        river, x, y = found
        if not (self.world.is_mine(a) or self.world.is_mine(b)):
            return ("a bridge wants a bank you hold -- neither end of that "
                    "road is yours")
        standing = waters.served_by(self.world.bridges, river.key, x, y)
        if standing is not None:
            who = "yours" if standing.owner == "player" else f"{standing.owner}'s"
            return f"{standing.name} already carries that reach, and it is {who}"
        already = [br for br in self.world.bridges
                   if br.river == river.key and not br.standing
                   and not br.broken
                   and math.hypot(br.x - x, br.y - y) <= waters.REACH]
        if already:
            return f"the masons are already at work on {already[0].name}"
        if self.treasury < waters.BRIDGE_COST:
            return (f"a bridge over the {river.name} is "
                    f"{waters.BRIDGE_COST:.0f}c and you have "
                    f"{self.treasury:.0f}c")
        self.treasury -= waters.BRIDGE_COST
        near = min((a, b), key=lambda k: math.hypot(
            self.world.coords[k][0] - x, self.world.coords[k][1] - y))
        br = waters.Bridge(uid=self.world._next_bridge, river=river.key,
                           x=x, y=y, owner="player",
                           name=f"{self.world.node_name(near)} Bridge",
                           built_day=self.day, days_left=waters.BRIDGE_DAYS)
        self.world._next_bridge += 1
        self.world.bridges.append(br)
        return (f"Masons begin {br.name} over the {river.name}: "
                f"{waters.BRIDGE_COST:.0f}c, {waters.BRIDGE_DAYS} days")

    def break_bridge(self, uid: int) -> str:
        """Throw down your own bridge. It is not a free denial.

        You lose the toll, your own carts go round with everybody else, and
        putting it back is most of a season. That is the point: a crossing
        you deny an army is a crossing you deny yourself.
        """
        for br in self.world.bridges:
            if br.uid == uid and br.owner == "player":
                if br.broken:
                    return f"{br.name} is already down"
                if not br.standing:
                    self.world.bridges.remove(br)
                    return f"the work on {br.name} is abandoned"
                br.broken = True
                br.days_left = 0
                river = self.world.river(br.river)
                return (f"{br.name} goes into the {river.name if river else 'water'}. "
                        f"Nothing crosses there now, yours included")
        return f"no bridge of yours numbered {uid}"

    def mend_bridge(self, uid: int) -> str:
        for br in self.world.bridges:
            if br.uid == uid and br.owner == "player":
                if not br.broken:
                    return f"{br.name} is standing"
                cost = waters.BRIDGE_COST * waters.REBUILD_SHARE
                if self.treasury < cost:
                    return (f"mending {br.name} is {cost:.0f}c and you have "
                            f"{self.treasury:.0f}c")
                self.treasury -= cost
                br.broken = False
                br.days_left = waters.REBUILD_DAYS
                return (f"The piers held. {br.name} back in "
                        f"{waters.REBUILD_DAYS} days for {cost:.0f}c")
        return f"no bridge of yours numbered {uid}"

    def _bridge_day(self) -> List[str]:
        """Masonry, and what other people's traffic leaves on the deck."""
        msgs: List[str] = []
        toll = 0.0
        for br in self.world.bridges:
            if br.days_left > 0:
                br.days_left -= 1
                if br.days_left == 0 and not br.broken:
                    river = self.world.river(br.river)
                    msgs.append(f"{br.name} is open over the "
                                f"{river.name if river else 'water'}")
                continue
            if br.broken or br.owner != "player":
                continue
            toll += self.toll_on(br)
        if toll:
            self.treasury += toll
        return msgs

    def _close_tolls(self) -> None:
        """Fold the day's tolls into each lord's running mean."""
        for t in self.world.towns.values():
            t.tolls_paid += (t.tolls_today - t.tolls_paid) / 30.0
            t.tolls_today = 0.0

    def toll_on(self, br: waters.Bridge) -> float:
        """What the country's own traffic pays to cross.

        Scaled by the markets either side rather than by a flat rate, because
        a bridge is worth what crosses it. The world already stands in for
        everybody-who-is-not-you as a pull toward each town's equilibrium;
        this is the share of that which has to get over the water.
        """
        near = 0.0
        for key, (x, y) in self.world.coords.items():
            d = math.hypot(x - br.x, y - br.y)
            if d > 3.0 * waters.REACH:
                continue
            town = self.world.towns.get(key)
            if town is not None:
                near += town.wealth * max(0.0, 1.0 - d / (3.0 * waters.REACH))
            elif key in self.world.settlements:
                near += 0.4 * max(0.0, 1.0 - d / (3.0 * waters.REACH))
        return min(waters.TOLL_CAP, waters.TOLL_RATE * near * 100.0)

    #: How fast a dyke turns fen into field, in slots a year. Slow on purpose:
    #: the drainage of the Fens and the Dutch polders took generations and the
    #: capital of whole cities, and a tech that converted a marsh overnight
    #: would make the wettest map the best one to start on.
    DRAIN_DAYS = 90

    def _drainage_day(self) -> List[str]:
        """Dykes, a cut and a wind-pump.

        The only tech in the tree that changes the *map*. Undrained fen is
        land you own and cannot work -- no building will stand on it -- which
        is exactly what made draining it worth a generation's money. One slot
        a quarter, and it is gone when it is gone.
        """
        if not self.progress.knows("drainage") or self.day % self.DRAIN_DAYS:
            return []
        out: List[str] = []
        for s in self.world.settlements.values():
            left = s.terrain.get("marsh", 0)
            if left <= 0:
                continue
            s.terrain["marsh"] = left - 1
            s.terrain["fertile"] = s.terrain.get("fertile", 0) + 1
            out.append(self.note(
                f"The cut at {s.name} is finished and the water is off "
                f"another field. {left - 1} of fen left."))
        return out

    def _look_around(self) -> None:
        """Refresh what you know about the march.

        Your carts are your intelligence service, which is the right answer for
        this game in particular: the map you can see is the map you trade with,
        and a lord you have never sent a cart to is a lord you are guessing
        about. A host of yours standing somewhere sees it too, and a town sworn
        to you reports every day.
        """
        self._scout()
        for t in self.world.towns.values():
            if t.mine:
                t.observe(self.day)
        for c in self.caravans:
            node = getattr(c, "at", "") or ""
            if node in self.world.towns:
                self.world.towns[node].observe(self.day)
        # An ally writes: what he has behind his wall is no secret from you.
        for key in self.court.allies:
            if key in self.world.towns:
                self.world.towns[key].observe(self.day)
        for a in self.armies:
            if a.owner == "player" and a.at in self.world.towns:
                self.world.towns[a.at].observe(self.day)
        self._sight_hosts()

    def host_xy(self, a) -> Optional[Tuple[float, float]]:
        """Where a host is on the map this morning, between towns if need be."""
        xy = self.world.coords
        if a.state == MARCHING and a.bound_for and a.at in xy and a.bound_for in xy:
            total = a.leg_days if a.leg_days > 0 else a.days_left + 1.0
            done = max(0.0, min(1.0, 1.0 - a.days_left / max(total, 1e-9)))
            (x0, y0), (x1, y1) = xy[a.at], xy[a.bound_for]
            return (x0 + (x1 - x0) * done, y0 + (y1 - y0) * done)
        where = a.at or a.bound_for
        return xy.get(where)

    def cart_xy(self, c) -> Tuple[Optional[Tuple[float, float]],
                                  Optional[Tuple[float, float]]]:
        """Where a cart set out from on this leg, and where it is now."""
        xy = self.world.coords
        frm = c.at or (c.route[c.leg - 1].node if c.route and c.leg else c.home)
        if frm not in xy:
            return None, None
        if not c.bound_for or c.bound_for not in xy:
            return xy[frm], xy[frm]
        total = max(1.0, self.world.distance(frm, c.bound_for) / max(c.speed, 1.0))
        done = max(0.0, min(1.0, 1.0 - c.days_left / total))
        (x0, y0), (x1, y1) = xy[frm], xy[c.bound_for]
        return xy[frm], (x0 + (x1 - x0) * done, y0 + (y1 - y0) * done)

    def _scout(self) -> None:
        """Clear the shroud round everybody of yours, and say what is in
        sight today. Your towns see round their walls; a cart or a host has
        seen the whole road it has come along this leg, and sees round where
        it stands now."""
        sh = self.shroud
        sh.morning()
        xy = self.world.coords
        for key in self.world.settlements:
            if key in xy:
                sh.look(*xy[key], self._sight_from(key, sight.TOWN_SIGHT))
        for key, t in self.world.towns.items():
            # Your sworn towns, and your allies': an ally shares what his
            # walls can see, which is half of what an alliance is for.
            if (t.mine or key in self.court.allies) and key in xy:
                sh.look(*xy[key], self._sight_from(key, sight.TOWN_SIGHT))
        for c in self.caravans:
            frm, now = self.cart_xy(c)
            if now:
                sh.trail(frm, now, sight.CART_SIGHT)
                sh.look(*now, sight.CART_SIGHT)
        for a in self.armies:
            if a.owner != "player":
                continue
            now = self.host_xy(a)
            if not now:
                continue
            if a.state == MARCHING and a.at in xy:
                sh.trail(xy[a.at], now, sight.HOST_SIGHT)
            sh.look(*now, sight.HOST_SIGHT if a.state == MARCHING
                    else self._sight_from(a.at, sight.HOST_SIGHT))

    def _sight_from(self, node: str, base: float) -> float:
        """How far a place sees: further from hill country, a twentieth
        more for every hill round it past the three most places have, up to
        a quarter."""
        hills = self._ground_at(node).get("hills", 0) if node else 0
        return base * (1.0 + 0.05 * min(5, max(0, hills - 3)))

    def _sight_hosts(self) -> None:
        """Which of their hosts you can actually see today.

        A field army is not a town: it moves, and there is nothing standing
        there to report. So you see one when it is close enough that you could
        not miss it -- sitting on something of yours, besieging or raiding it,
        marching for it -- or when one of yours is at the same place. Anything
        else is a memory with a date on it, which is what `seen_day` is for.

        Drawing every enemy host wherever it really is would quietly delete
        the fog of war, and the fog is most of what makes a march tense.
        """
        mine = set(self.world.settlements)
        mine |= {k for k, t in self.world.towns.items() if t.mine}
        standing = {a.at for a in self.armies if a.owner == "player" and a.at}
        for a in self.armies:
            if a.owner == "player":
                continue
            close = (a.at in mine or a.bound_for in mine or a.at in standing
                     or (a.state in (BESIEGING, RAIDING) and a.at in mine))
            # Or simply in sight: inside the ring round a town, a cart or a
            # host of yours, wherever on the road it has got to.
            if not close:
                where = self.host_xy(a)
                close = bool(where) and self.shroud.sees(*where)
            if close:
                a.seen_day = self.day
                a.seen_at = a.at or a.bound_for
                a.seen_size = a.size

    def known(self, town_key: str) -> Tuple[Dict[str, float], int]:
        """What you believe about a town, and how many days old it is."""
        t = self.world.towns[town_key]
        if t.seen_day < 0:
            return {}, -1
        return dict(t.seen), self.day - t.seen_day

    #: How long word of a sickness is worth anything. A market you have not
    #: had anybody in for six weeks is a market you do not know the state
    #: of, and this is the whole reason shutting the gates is a decision:
    #: shut on a rumour and you may have stopped your carts for nothing,
    #: wait for certainty and the certainty arrives on a cart.
    WORD_KEEPS = 40

    def word_of_sickness(self) -> List[dict]:
        """Where you have heard there is sickness, and how old the word is.

        Off the same `seen_day` the rest of the fog runs on: somebody of
        yours has to have been there. A town you have never traded with
        could be burying half its people and you would not know.
        """
        out = []
        for key, t in self.world.towns.items():
            _seen, age = self.known(key)
            if age < 0 or age > self.WORD_KEEPS:
                continue
            if not t.sick.here:
                continue
            out.append({"key": key, "name": t.name, "days": age,
                        "sure": age <= 3})
        return sorted(out, key=lambda r: r["days"])

    def believed_host(self, town_key: str) -> Dict[str, float]:
        """The host you think that town could field, from what you last saw."""
        town = self.world.towns[town_key]
        if town.mine:
            return {}
        seen, age = self.known(town_key)
        if age < 0:
            return {}                      # you have no idea, and should not pretend
        pressure = self.war_pressure()
        scale = seen.get("muster", 1.0) * pressure * (
            0.6 + 0.5 * seen.get("prosperity", 1.0))
        return {"spearman": round(10 * scale), "archer": round(7 * scale)}

    def likely_host(self, town_key: str) -> Dict[str, float]:
        """The host that town could put in the field today. Look before you
        decide the wall is high enough."""
        town = self.world.towns[town_key]
        if town.mine:
            return {}
        return self._muster_enemy(town, self.war_pressure(), spread=False)

    # ------------------------------------------------------------- caravans
    def new_caravan(self, home: str, name: str = "",
                    kind: str = CART) -> Tuple[Optional[Caravan], str]:
        if home not in self.world.settlements:
            return None, f"{home} is not yours to outfit from"
        if len(self.caravans) >= self.caravan_limit:
            return None, (f"you can run {self.caravan_limit} carts and hulls; "
                          f"build a trading post or a harbour for another")
        if kind == SHIP and not self.world.settlements[home].effect("port"):
            return None, f"{self.world.node_name(home)} has no harbour to build a cog in"
        cost = C.SHIP_COST if kind == SHIP else C.CARAVAN_COST
        if self.treasury < cost:
            return None, f"that costs {cost:,.0f}c and you have {self.treasury:,.0f}c"
        self.treasury -= cost
        self._outlay += cost
        uid = self.next_caravan_uid
        self.next_caravan_uid += 1
        label = "Cog" if kind == SHIP else "Caravan"
        c = Caravan(uid=uid, name=name or f"{label} {uid}", home=home, at=home,
                    kind=kind)
        self.caravans.append(c)
        return c, ""

    def caravan(self, uid: int) -> Optional[Caravan]:
        return next((c for c in self.caravans if c.uid == uid), None)

    def disband(self, uid: int) -> str:
        c = self.caravan(uid)
        if not c:
            return f"no caravan {uid}"
        if c.state == "moving":
            return f"{c.name} is on the road; it must reach a town first"
        market = self.world.market_of(c.at)
        if market and c.cargo:
            for k, q in list(c.cargo.items()):
                market.add(k, q)
        self.caravans.remove(c)
        self.treasury += (C.SHIP_COST if c.sails else C.CARAVAN_COST) * 0.4
        return f"{c.name} disbanded at {self.world.node_name(c.at)}"
