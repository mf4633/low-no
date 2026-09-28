"""The wall: hosts raised and fed, marches, sieges, storms, raids and the fight
the day stops for -- including the lord riding at their head.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from . import config as C
from .chronicle import MOMENTOUS, NOTABLE, ROUTINE
from .castle import INVEST, Works, choose, storms_now
from . import feats as feats_mod
from .goods import ALL_KEYS, RATION_GOODS, good
from . import lords as lordly
from . import lord as manly
from . import keep as keeps
from . import league as lg
from .league import PLAYER
from .military import (open_battle, BESIEGING, GARRISON, HOLD, MARCHING,
                       RAIDING, RELIEVING, RETURNING, STORM, describe, UNITS,
                       Army, Side, can_recruit, fight, host_size,
                       host_speed, host_strength, raid_day, recruit_cost,
                       siege_day, unit)
from .military import Field, going_of, sky_on, sortie_odds
from . import cartography as carto
from . import military
from . import supply
from .settlement import Settlement
from .records import PendingBattle


class WallMixin:
    """GameState's wall. Mixed into GameState; see engine.py."""

    # -------------------------------------------------------------- military
    def recruit(self, settlement_key: str, unit_key: str, count: int) -> str:
        s = self.world.settlements.get(settlement_key)
        if not s:
            return f"{settlement_key} is not yours"
        if not s.effect("muster"):
            return f"{s.name} has no barracks"
        ok, why = can_recruit(unit_key, self.progress)
        if not ok:
            return why
        u = unit(unit_key)
        count = max(1, int(count))
        coin, goods = recruit_cost(unit_key, count, self.progress)
        if self.treasury < coin:
            return f"{count} {u.name} cost {coin:,.0f}c; you have {self.treasury:,.0f}c"
        short = [(k, q) for k, q in goods.items() if s.market.stock.get(k, 0.0) < q]
        if short:
            return (f"{s.name} needs " + ", ".join(
                f"{q:g} {good(k).name}" for k, q in short) +
                " -- soldiers are armed from your own workshops")
        if u.unit_class != "siege" and s.workforce < count:
            return f"{s.name} has no spare hands; every soldier is one fewer worker"
        self.treasury -= coin
        self._war_outlay += coin
        for k, q in goods.items():
            s.market.take(k, q)
        # The knights hold the land the levies come off. Sulking, they send
        # word that the men could not be spared -- and you are out the coin
        # either way, which is the part that makes their loyalty matter.
        came = max(1, int(round(count * self.estates.mult("muster"))))
        s.units[unit_key] = s.units.get(unit_key, 0.0) + came
        self._roll_moved(settlement_key, host_size({unit_key: came}))
        self._muster_roll(settlement_key)
        if came < count:
            return (f"{came} {u.name} muster at {s.name} ({coin:,.0f}c) -- "
                    f"you paid for {count}; the knights spared what they chose")
        if came > count:
            return (f"{came} {u.name} muster at {s.name} ({coin:,.0f}c) -- "
                    f"more than you asked for; the knights are keen")
        return f"{count} {u.name} muster at {s.name} ({coin:,.0f}c)"

    def _standing(self) -> "feats_mod.Standing":
        """Every figure a feat may read, gathered once and from the game's
        own books rather than instrumented into the thing it counts."""
        seats = list(self.world.settlements.values())
        mine_towns = [t for t in self.world.towns.values() if t.mine]
        idioms = {t.culture for t in mine_towns if t.culture}
        idioms |= {getattr(s, "culture", "") for s in seats}
        wall = sum(len(s.plan().pieces) for s in seats if hasattr(s, "plan"))
        inside = 0
        for s in seats:
            if hasattr(s, "plan"):
                from . import keep as keeps
                inside = max(inside, len(keeps.enclosed(s.plan())))
        loyal = sum(1 for st in self.estates.by_key.values() if st.loyalty >= 60)
        grants = sum(len(st.privileges) for st in self.estates.by_key.values())
        return feats_mod.Standing(
            day=self.day, year=self.year,
            net_worth=self.net_worth(), treasury=self.treasury,
            population=int(sum(s.population for s in seats)),
            towns=len(mine_towns),
            relics=len([sh for sh in self.world.shrines.values()
                        if getattr(sh, "holder", "") == "player"]),
            age=self.progress.age, techs=len(self.progress.researched),
            battles_won=self._battles_won, hosts_raised=self._hosts_raised,
            coin_minted=float(getattr(self.economy, "minted", 0.0) or 0.0),
            allies=len(getattr(self.court, "allies", ())),
            coalition=len(getattr(self.court, "coalition", ())),
            marriages=sum(1 for p in self.kin.people if p.alive and p.married_to),
            wall_yards=wall, enclosed=inside,
            soldiers=int(sum(sum(s.units.values()) for s in seats)),
            trade_profit=self._trade_profit,
            idioms_seen=len([i for i in idioms if i]),
            estates_loyal=loyal, privileges=grants,
            worst_estate=min((st.loyalty for st in self.estates.by_key.values()),
                             default=100.0),
            mood=max((s.popularity for s in seats), default=0.0),
            took_by_storm=self._stormed, lost_towns=self._towns_lost)

    # ------------------------------------------------------ the muster roll
    def _under_arms(self) -> Dict[str, float]:
        """Men under arms by the town they came from: the garrison, and
        every host of yours whose home it is."""
        # Exact, not host_size's whole men: a siege's arrows take a
        # hundredth of a man a day, and rounding the roll turned the day
        # 3.0 became 2.99 into a man buried whole.
        roll = {k: float(sum(s.units.values()))
                for k, s in self.world.settlements.items()}
        for a in self.armies:
            if a.owner == PLAYER and a.home in roll:
                roll[a.home] += float(sum(a.units.values()))
        return roll

    def _muster_roll(self, key: str = "") -> None:
        """Count the men away with hosts against the towns they left, and --
        given a town -- put that town's hands back at the sheds now.

        Raising a levy empties jobs the same morning, and standing it down
        fills them the same morning: the figure you sent to war is not at
        the mill when you look, and not at the mill tomorrow either.
        """
        away = {k: 0 for k in self.world.settlements}
        for a in self.armies:
            if a.owner == PLAYER and a.home in away:
                away[a.home] += host_size(a.units)
        for k, s in self.world.settlements.items():
            s.afield = away[k]
        s = self.world.settlements.get(key)
        if s is not None:
            s._seat_hands()

    def _roll_moved(self, key: str, men: float) -> None:
        """Men put on or struck off the roll by an order, not by a blade."""
        if self._roll is not None and key in self._roll:
            self._roll[key] += men

    def _count_the_fallen(self, internal: Dict[str, float]) -> List[str]:
        """The day's dead, taken off the towns that sent them.

        Whoever is on yesterday's roll and not today's -- less what the town
        already buried itself (a sickness takes the man and the soldier at
        once) and less what an order moved -- fell. Measured as the whole
        march's loss, so a host that walked into another of your towns'
        garrisons is a move and not a death, and laid on the towns that are
        short by it. They were somebody's hands, and now they are nobody's.
        """
        now = self._under_arms()
        was, self._roll = self._roll, now
        if was is None:
            return []
        lost = {k: was[k] - internal.get(k, 0.0) - now[k]
                for k in now if k in was}
        total = sum(lost.values())
        short = {k: v for k, v in lost.items() if v > 0}
        # Every sliver comes off the population; only whole men get a line.
        if total <= 1e-9 or not short:
            return []
        scale = total / sum(short.values())
        msgs: List[str] = []
        for k, v in short.items():
            dead = v * scale
            s = self.world.settlements[k]
            s.population = max(0.0, s.population - dead)
            if dead >= 0.5:
                weight = NOTABLE if dead >= 10 else ROUTINE
                msgs.append(self.note(
                    f"{s.name} buries {dead:.0f} of the men it sent to war",
                    weight))
        return msgs

    def raise_host(self, settlement_key: str, units: Dict[str, int],
                   name: str = "") -> Tuple[Optional[Army], str]:
        s = self.world.settlements.get(settlement_key)
        if not s:
            return None, f"{settlement_key} is not yours"
        take: Dict[str, float] = {}
        for k, n in units.items():
            have = s.units.get(k, 0.0)
            if have < n:
                return None, f"{s.name} has only {have:.0f} {unit(k).name}"
            take[k] = float(n)
        if not take:
            return None, "name some soldiers to march"
        for k, n in take.items():
            s.units[k] -= n
            if s.units[k] < 0.5:
                del s.units[k]
        a = Army(uid=self.next_army_uid, name=name or f"Host {self.next_army_uid}",
                 owner="player", units=take, at=settlement_key, home=settlement_key)
        self.next_army_uid += 1
        self.armies.append(a)
        self._hosts_raised += 1
        self._muster_roll(settlement_key)
        # It marches out of the granary it was raised in, as full as the
        # granary allows. A host that had to be told to take food would
        # starve the first time somebody forgot, which is a memory test
        # rather than a decision.
        self.provision(a.uid)
        return a, ""

    def provision(self, uid: int, days: float = 0.0) -> str:
        """Load a host's baggage out of the granary it is standing in.

        Only at one of your own towns -- a host in the field fills its
        baggage by foraging, which is the whole of supply.py. The food comes
        off the town's own stores, so provisioning an army is visibly the
        bread the town would have eaten.
        """
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != PLAYER:
            return f"{a.name} is not yours to victual"
        where = a.at
        if where not in self.world.settlements:
            return f"{a.name} is not standing in a town of yours"
        room = supply.capacity(a.size) - a.stores
        if room <= 0.5:
            return f"{a.name} is carrying all it can"
        want = min(room, a.size * supply.MARCH_RATION * days) if days > 0 else room
        got = self._draw_rations(where, want)
        a.stores += got
        if got <= 0.05:
            return (f"{self.world.node_name(where)} has nothing to spare -- "
                    f"{a.name} marches on what it has")
        return (f"{a.name} victualled at {self.world.node_name(where)}: "
                f"{supply.days_left(a.size, a.stores):.0f} days in the baggage")

    def army(self, uid: int) -> Optional[Army]:
        return next((a for a in self.armies if a.uid == uid), None)

    def march(self, uid: int, node: str) -> str:
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if node not in self.world.coords:
            return f"nowhere called {node!r}"
        if a.at == node:
            return self._arrive(a)
        water = self._set_march(a, a.at or a.home, node, a.units)
        return (f"{a.name} marches on {self.world.node_name(node)} -- "
                f"{a.days_left:.0f} days" + (f" ({water})" if water else ""))

    # --------------------------------------------------------------- water
    def _set_march(self, a, origin: str, target: str,
                   units: Dict[str, float]) -> str:
        """Put a host on the road, once, in one place.

        Three separate copies of these four lines used to exist -- your own
        host, an enemy's, and a pilgrimage party -- and when the rivers
        arrived only one of them would have learnt about them. That is the
        garrison bug (see settlement.max_garrison) in a different coat, and
        this time it got written down before it cost anything.

        Returns what the water did, in words, or '' if it did nothing.
        """
        dist = self.world.distance(origin, target)
        days = max(1.0, dist / max(host_speed(units), 1.0))
        extra, notes = self.world.water_days(
            origin, target, self.day, self.seed, self.start_month)
        a.bound_for = target
        a.days_left = days + extra
        a.leg_days = a.days_left
        a.state = MARCHING
        notes += self._bridge_toll(a, origin, target)
        return "; ".join(notes)

    def split_host(self, uid: int, units: Dict[str, int],
                   name: str = "") -> Tuple[Optional[Army], str]:
        """Detach part of a host as a host of its own, standing where it is.

        The horse ride off to burn the country while the foot sit before
        the wall: that is what a detachment is for, and it is the one thing
        "select the knights and send them" can honestly mean here, where a
        host is a count of men and not a crowd of sprites. The new host takes
        the old one's order and posture and its share of the baggage. The
        captain stays with the host he was posted to.
        """
        a = self.army(uid)
        if a is None:
            return None, f"no host {uid}"
        if a.owner != PLAYER:
            return None, f"{a.name} is not yours to command"
        if a.state == MARCHING:
            return None, f"{a.name} is on the road -- split it when it arrives"
        take: Dict[str, float] = {}
        for k, n in units.items():
            if n <= 0:
                continue
            have = a.units.get(k, 0.0)
            if have < n:
                return None, f"{a.name} has only {have:.0f} {unit(k).name}"
            take[k] = float(n)
        if not take:
            return None, "name some soldiers to detach"
        left = {k: v - take.get(k, 0.0) for k, v in a.units.items()}
        if host_size({k: v for k, v in left.items() if v >= 0.5}) < 1:
            return None, f"that is the whole of {a.name} -- march it instead"
        share = host_size(take) / max(1, a.size)
        for k, n in take.items():
            a.units[k] -= n
            if a.units[k] < 0.5:
                del a.units[k]
        b = Army(uid=self.next_army_uid, name=name or f"Host {self.next_army_uid}",
                 owner=PLAYER, units=take, at=a.at, home=a.home,
                 state=a.state, order=a.order, siege_days=a.siege_days)
        self.next_army_uid += 1
        b.stores, a.stores = a.stores * share, a.stores * (1.0 - share)
        self.armies.append(b)
        where = self.world.node_name(a.at)
        a.log.append(f"{describe(take)} detached as {b.name} at {where}")
        b.log.append(f"detached from {a.name} at {where}")
        return b, ""

    def join_hosts(self, uid: int, other: int) -> str:
        """Fold one host into another standing in the same place."""
        a, b = self.army(uid), self.army(other)
        if a is None or b is None:
            return f"no host {other if a is not None else uid}"
        if a is b:
            return f"{a.name} is already one host"
        if a.owner != PLAYER or b.owner != PLAYER:
            return "both hosts must be yours"
        if a.state == MARCHING or b.state == MARCHING:
            return "a host on the road cannot be joined -- wait for it to arrive"
        if a.at != b.at:
            return (f"{b.name} is at {self.world.node_name(b.at)}, "
                    f"{a.name} at {self.world.node_name(a.at)}")
        for k, n in b.units.items():
            a.units[k] = a.units.get(k, 0.0) + n
        a.stores += b.stores
        a.siege_days = max(a.siege_days, b.siege_days)
        # A captain posted to the host that is gone rides with the one that
        # is left; otherwise he would be riding with a number.
        for p in self.kin.people:
            if p.alive and p.post == "captain" and p.target == str(b.uid):
                p.target = str(a.uid)
        self.armies.remove(b)
        a.log.append(f"{b.name} joined: {describe(b.units)}")
        return f"{b.name} joins {a.name} at {self.world.node_name(a.at)}: {describe(a.units)}"

    def disband_host(self, uid: int, to_square: bool = False) -> str:
        """Stand a host down: into the garrison, or -- `to_square` -- home.

        Into the garrison they are still soldiers, still paid and still not
        working. Home, they are hands on the square again by the next
        seating, and whatever is short of hands has them.
        """
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.state == MARCHING:
            return f"{a.name} is on the road"
        s = self.world.settlements.get(a.at)
        if not s:
            return f"{a.name} must be in one of your settlements to stand down"
        self.armies.remove(a)
        if to_square:
            men = host_size(a.units)
            self._roll_moved(a.home, -men)
            self._muster_roll(a.at)
            return (f"{a.name} is paid off at {s.name}: {men} men go back to "
                    f"the square, and to whatever is short of hands")
        for k, n in a.units.items():
            s.units[k] = s.units.get(k, 0.0) + n
        # Garrison and host are both off the roll of workers, but a host
        # from elsewhere standing down here is now this town's to feed.
        self._roll_moved(a.home, -host_size(a.units))
        self._roll_moved(a.at, host_size(a.units))
        self._muster_roll(a.at)
        return f"{a.name} stands down into the garrison of {s.name}"

    def _military_day(self) -> List[str]:
        msgs: List[str] = []
        for s in self.world.settlements.values():
            s.besieged = False
            s.blockaded = False
            s.raided = False
            s.raid_pressure = 0.0
        msgs += self._field_day()
        msgs += self._relieve_day()
        for a in list(self.armies):
            if a not in self.armies:
                continue    # a town fell today and its host went with it
            if a.owner != "player" and self.world.towns[a.owner].mine:
                msgs.append(f"{a.name} turns for home -- {self.world.node_name(a.owner)} "
                            f"is sworn to you now")
                self.armies.remove(a)
                continue
            msgs += self._feed_host(a)
            if a.state == MARCHING:
                a.siege_days = 0
                a.days_left -= 1
                if a.days_left <= 0:
                    a.at, a.bound_for = a.bound_for, ""
                    msgs.append(self._arrive(a))
            elif a.state == BESIEGING:
                msgs += self._siege(a)
            elif a.state == RAIDING:
                msgs += self._raid(a)
            a.prune()
            if a.size <= 0 and a in self.armies:
                msgs.append(f"{a.name} is no more")
                self.armies.remove(a)
        # The country comes back where nobody is eating it. Done after every
        # host has had its morning, so a place a host is standing in is the
        # one place that does not recover today.
        standing = {a.at or a.bound_for for a in self.armies if a.size > 0}
        for key in list(self.world.grazed):
            if key in standing:
                continue
            left = supply.recover(self.world.grazed[key])
            if left <= 0:
                del self.world.grazed[key]
            else:
                self.world.grazed[key] = left
        msgs += self._plague_day()
        msgs += self._bridge_day()
        self._look_around()
        msgs += self._lord_day()
        msgs += self._shrine_day()
        msgs += self._shrine_race()
        msgs += self._lords_and_hosts()
        msgs = [m for m in msgs if m]
        self.battles += [m for m in msgs if m]
        if len(self.battles) > 120:
            del self.battles[:-120]
        return msgs

    def _ring_at(self, node: str, against: str) -> List[Army]:
        """The hosts sitting round or burning `node` that are `against`'s
        enemies: the player's besiegers at a lord's town, or a lord's at
        the player's. Two lords at each other's walls are nobody's business
        but theirs, so a lord's host coming home to a lord's siege walks in
        as it always has."""
        out = []
        for x in self.armies:
            if x.at != node or x.state not in (BESIEGING, RAIDING):
                continue
            if against == PLAYER and x.owner != PLAYER:
                out.append(x)
            elif against != PLAYER and x.owner == PLAYER:
                out.append(x)
        return out

    def _field_day(self) -> List[str]:
        """Hosts that came up to relieve a place give battle in the open.

        One fight a place, both sides pooled: every host that came up
        against every host in the ring. The relief attacks -- it is the
        side that has to get through -- and the ring holds its lines under
        its own order. In the open there is no wall, so the storm's oil and
        pitch have nothing to be poured over, and the fight is the same
        arithmetic every field battle has always used. If you are on either
        side and playing your battles, the day waits on it like a storm.
        """
        if self.pending is not None:
            return []
        msgs: List[str] = []
        for node in sorted({a.at for a in self.armies if a.state == RELIEVING}):
            relief = [a for a in self.armies if a.at == node and a.state == RELIEVING]
            if not relief:
                continue
            side_owner = relief[0].owner
            ring = self._ring_at(node, against=side_owner)
            if not ring:
                for a in relief:
                    a.state = GARRISON
                msgs.append(f"{relief[0].name} finds the lines before "
                            f"{self.world.node_name(node)} empty and walks in")
                continue
            msgs += self._field_battle(node, relief, ring)
            if self.pending is not None:
                break
        return msgs

    def _field_side(self, hosts: List[Army]) -> Side:
        """Every host of one side as one line, dressed as the player's are."""
        pooled: Dict[str, float] = {}
        for x in hosts:
            for k, n in x.units.items():
                pooled[k] = pooled.get(k, 0.0) + n
        if hosts[0].owner != PLAYER:
            return Side(pooled)
        lead = hosts[0]
        return Side(pooled,
                    attack_mult=(self.progress.mult("attack")
                                 * self.kin.mult("attack", lead.uid)
                                 * manly.attack_bonus(self.lord, lead.uid)),
                    defense_mult=self.progress.mult("defense"))

    def _field_battle(self, node: str, relief: List[Army],
                      ring: List[Army]) -> List[str]:
        att, dfn = self._field_side(relief), self._field_side(ring)
        lead, foe = relief[0], ring[0]
        orders = (lead.order if lead.owner == PLAYER else lordly.sort_of(lead.home).fights,
                  foe.order if foe.owner == PLAYER else lordly.sort_of(foe.home).fights)
        name = self.world.node_name(node)
        battle = open_battle(att, dfn, rng=self.rng, place=name, orders=orders,
                             field=self.field_at(node), walled=False)
        if self.battles_mode == "play":
            self.pending = PendingBattle(
                battle=battle, kind="field", army=lead.uid, where=node,
                side="attacker" if lead.owner == PLAYER else "defender",
                title=name, day=self.day,
                stationed=[x.uid for x in relief], foes=[x.uid for x in ring])
            return [self.note(f"*** BATTLE IS JOINED BEFORE {name.upper()}. "
                              f"The day waits on it. ***", MOMENTOUS)]
        battle.run()
        battle.close()
        return self._after_field(battle.res, node, relief, ring, att, dfn)

    @staticmethod
    def _share_out(hosts: List[Army], side: Side) -> None:
        """Give a pooled line's survivors back to the hosts that made it up,
        each keeping its share of what is left of each kind."""
        before: Dict[str, float] = {}
        for x in hosts:
            for k, n in x.units.items():
                before[k] = before.get(k, 0.0) + n
        for x in hosts:
            for k in list(x.units):
                have = before.get(k, 0.0)
                x.units[k] = side.units.get(k, 0.0) * (x.units[k] / have) if have else 0.0
            x.prune()

    def _after_field(self, res, node: str, relief: List[Army], ring: List[Army],
                     att: Side, dfn: Side) -> List[str]:
        """What follows a battle in the open before a besieged place."""
        name = self.world.node_name(node)
        lead, foe = relief[0], ring[0]
        msgs = [f"BATTLE BEFORE {name.upper()}: the {res.winner} holds the ground "
                f"after {res.rounds} rounds",
                self._box_score(f"{lead.name} relieves {name}", res, lead.owner, foe.owner)]
        self.scored(lead.owner, won=res.winner == "attacker")
        self.scored(foe.owner, won=res.winner == "defender")
        self._share_out(relief, att)
        self._share_out(ring, dfn)
        if res.winner == "attacker":
            # The ring is broken. Its hosts fall back the way they came.
            for x in ring:
                # Marked as falling back even when nothing is left to fall
                # back: the day's loop buries a host with no men, and it
                # must not find a dead one still sitting at the wall.
                x.siege_days = 0
                x.state = RETURNING
                if x.size > 0:
                    self.march(x.uid, x.home)
            msgs.append(f"The siege of {name} is broken: the host of "
                        f"{self.world.node_name(foe.home)} falls back")
            if foe.owner == PLAYER and self.lord.riding in [x.uid for x in ring]:
                msgs += self._lord_fell()
            for x in relief:
                self._come_inside(x, node)
            if foe.owner != PLAYER and foe.owner in self.world.towns:
                self.court.write(foe.owner, "beaten", 22.0, self.day)
                self.court.reckon(foe.owner, 25.0)
        else:
            # Held or stood off: the relief could not get through. What is
            # left of it slips inside if this is its own gate, and goes home
            # if it is not; the ring stays where it sat.
            how = ("breaks off" if res.broken_off == "attacker"
                   else "is thrown back" if res.winner == "defender" else "cannot get through")
            msgs.append(f"{lead.name} {how} before {name}")
            if lead.owner == PLAYER and self.lord.riding in [x.uid for x in relief]:
                msgs += self._lord_fell()
            for x in relief:
                x.state = RETURNING
                if x.size <= 0:
                    continue
                if x.home == node:
                    self._come_inside(x, node)
                    msgs.append(f"what is left of {x.name} slips inside the walls")
                else:
                    x.state = RETURNING
                    self.march(x.uid, x.home)
        return msgs

    def _come_inside(self, x: Army, node: str) -> None:
        """A host that has fought its way to the gate goes through it: yours
        stands in the place as a garrisoned host, a lord's stands down into
        his town's garrison as any host of his does at home."""
        if x.owner == PLAYER or node not in self.world.towns:
            x.state = GARRISON
            x.siege_days = 0
            return
        town = self.world.towns[node]
        for k, n in x.units.items():
            town.garrison[k] = town.garrison.get(k, 0.0) + n
        if x in self.armies:
            self.armies.remove(x)

    def _arrive(self, a: Army) -> str:
        """What happens when a host walks up to a place."""
        node = a.at
        if node in self.world.shrines:
            sh = self.world.shrines[node]
            a.state = GARRISON
            a.siege_days = 0
            if sh.taken:
                if a.owner != "player":
                    self.march(a.uid, a.home)
                return f"{a.name} reaches {sh.name}. The shrine is already stripped."
            return (f"{a.name} reaches {sh.name}. "
                    f"{C.RELIC_DAYS} days to lift {sh.relic}.")
        if a.owner == "player":
            if self.world.is_friendly(node):
                ring = self._ring_at(node, against=PLAYER)
                if ring:
                    # The besiegers are between him and the gate. He stands
                    # off tonight and they must turn and fight him at dawn.
                    a.state = RELIEVING
                    return self.note(
                        f"*** {a.name} comes up before {self.world.node_name(node)}. "
                        f"The host of {self.world.node_name(ring[0].home)} must turn "
                        f"and fight at dawn. ***", MOMENTOUS)
                a.state = GARRISON
                return f"{a.name} reaches {self.world.node_name(node)}"
            town = self.world.towns[node]
            a.state = BESIEGING
            return (f"{a.name} sits down before {town.name} "
                    f"({town.wall_hp:.0f} of wall, {describe(town.garrison)} within)"
                    + self._declare(town))

        if node == a.home and node in self.world.towns:
            if self._ring_at(node, against=a.owner):
                # Your lines are between him and his own gate. He does not
                # walk through them: he stands off, and you fight at dawn.
                a.state = RELIEVING
                return self.note(
                    f"*** A host out of {self.world.node_name(node)} comes up behind "
                    f"your lines -- {describe(a.units)}. Battle at dawn. ***", MOMENTOUS)
            # A host that gets home stands down into its own town's garrison,
            # so the lord can call it out again another year.
            town = self.world.towns[node]
            for k, n in a.units.items():
                town.garrison[k] = town.garrison.get(k, 0.0) + n
            if a in self.armies:
                self.armies.remove(a)
            return ""
        s = self.world.settlements.get(node)
        if s is not None:
            # A captain who cannot carry the walls does not throw his men at
            # them: he burns the country instead and rides home richer. This
            # is the half of medieval war that actually happened.
            # A captain who cannot carry the walls does not throw his men at
            # them -- and some lords never mean to try the walls at all. The
            # Fox came for the harvest and said so a season ago.
            shy = 0.9 + 1.6 * lordly.sort_of(a.home).raids
            if host_strength(a.units) < host_strength(s.units) * shy:
                a.state = RAIDING
                s.raided = True
                return (f"Riders out of {self.world.node_name(a.home)} are loose "
                        f"in the country around {s.name}! {describe(a.units)}")
            a.state = BESIEGING
            s.besieged = True
            return (f"A host out of {self.world.node_name(a.home)} is before "
                    f"{s.name}! {describe(a.units)}")
        town = self.world.towns.get(node)
        if town is None or town.owner == a.owner:
            a.state = GARRISON
            return ""
        a.state = BESIEGING
        whose = " (sworn to you)" if town.mine else ""
        return (f"{self.world.node_name(a.home)} lays siege to {town.name}{whose}")

    SIEGE_PATIENCE = 21          # days a host will sit at a wall it cannot break
    MAX_RIVAL_WARS = 2           # wars between other lords running at once

    #: Warband's two rules for a lord's siege: he stays while he outnumbers
    #: the men inside by this much, and hunger does his work for him; below
    #: it, he lifts. And nobody sits for ever.
    SIEGE_ODDS = 1.75
    SIEGE_LIMIT = 90

    def _inside(self, a: Army) -> float:
        """The strength of the men behind the wall this host is sitting at."""
        town = self.world.towns.get(a.at)
        if town is not None:
            return host_strength(town.garrison) + sum(
                host_strength(x.units) for x in self.armies
                if x is not a and x.owner == "player" and x.at == a.at and town.mine)
        s = self.world.settlements.get(a.at)
        return host_strength(s.units) if s else 0.0

    def _siege_holds(self, a: Army) -> bool:
        """Whether a lord's host keeps its lines another day."""
        if a.siege_days > self.SIEGE_LIMIT:
            return False
        if a.siege_days <= self.SIEGE_PATIENCE or a.siege_power > 0:
            return True           # hunger wants its three weeks; engines work
        return host_strength(a.units) >= self.SIEGE_ODDS * self._inside(a)

    #: Days before word of a siege reaches a lord's other towns, and the
    #: share of a garrison he will strip to answer it.
    RELIEF_NEWS = 3
    RELIEF_SHARE = 0.5

    def _relieve_day(self) -> List[str]:
        """A lord with more than one town sends men to the one under siege.

        In Warband a lord whose castle is besieged comes back for it; here a
        lord was never anywhere else, so what comes is half the garrison of
        whichever other town of his is nearest and not itself ringed. Up
        against your lines it stands off and you fight it at dawn; against
        another lord's it walks in, and the odds outside change.
        """
        msgs: List[str] = []
        ringed = {x.at for x in self.armies if x.state == BESIEGING}
        for b in sorted((x for x in self.armies if x.state == BESIEGING),
                        key=lambda x: x.uid):
            town = self.world.towns.get(b.at)
            if town is None or town.mine or b.siege_days < self.RELIEF_NEWS:
                continue
            holder = town.owner or town.key
            if holder == b.owner or holder not in self.world.towns:
                continue
            if any(x.home == town.key and x.state == MARCHING and x.owner != b.owner
                   for x in self.armies):
                continue                     # already on the road
            # His own other towns, and those of any lord sworn to him.
            friends = {holder} | {p for p in self.court.partners(holder)
                                  if p != b.owner}
            sources = sorted(
                (k for k, t in self.world.towns.items()
                 if k != town.key and (t.owner or k) in friends and not t.mine
                 and k not in ringed and k in self.world.coords),
                key=lambda k: (self.world.distance(k, town.key), k))
            if not sources:
                continue
            src = self.world.towns[sources[0]]
            # A partner sends less than a lord sends to his own.
            share = self.RELIEF_SHARE * (1.0 if (src.owner or src.key) == holder else 0.6)
            send = {k: v * share for k, v in src.garrison.items() if v * share >= 0.5}
            if host_strength(send) < 0.25 * host_strength(b.units):
                continue                     # not enough to be worth the road
            for k, n in send.items():
                src.garrison[k] -= n
            src.garrison = {k: v for k, v in src.garrison.items() if v >= 0.5}
            sender = src.owner or src.key
            lord = self.world.towns[sender].lord
            a = Army(uid=self.next_army_uid, name=f"{lord}'s relief", owner=sender,
                     units=send, at=src.key, home=town.key)
            self.next_army_uid += 1
            self.armies.append(a)
            self._set_march(a, src.key, town.key, send)
            if b.owner == PLAYER:
                msgs.append(self.note(
                    f"Out of {src.name} a relief marches for {town.name} -- "
                    f"{describe(send)}, {a.days_left:.0f} days out", MOMENTOUS))
        return msgs

    #: Warband's lord does not go through a breach unless he has the men for
    #: it: half again the strength of whoever is behind it -- until he has
    #: sat so long that going in is better than going home.
    STORM_ODDS = 1.5
    STORM_DESPERATE = 60

    def _dares(self, a: Army, holder) -> bool:
        """Whether a lord's host goes in today. Yours goes when you say."""
        if a.owner == PLAYER or a.siege_days > self.STORM_DESPERATE:
            return True
        return host_strength(a.units) >= self.STORM_ODDS * host_strength(holder.units)

    def _siege(self, a: Army) -> List[str]:
        a.siege_days += 1
        if a.owner != "player":
            breaks = not self._siege_holds(a)
        else:
            breaks = a.siege_power <= 0 and a.siege_days > self.SIEGE_PATIENCE
        if breaks:
            # Hunger and boredom break more sieges than arrows do.
            a.siege_days = 0
            where = self.world.node_name(a.at)
            if a.owner == "player":
                self.march(a.uid, a.home)
                return [f"{a.name} has nothing to break the walls of {where} with "
                        f"and breaks up"]
            if a in self.armies:
                self.armies.remove(a)
            return [f"The host outside {where} breaks up and goes home"]
        if a.at in self.world.towns:
            return self._siege_town(a, self.world.towns[a.at])
        s = self.world.settlements.get(a.at)
        return self._siege_settlement(a, s) if s else []

    def _shrine_day(self) -> List[str]:
        """Hosts standing at a shrine lift what is in it, given long enough.

        There is no garrison to fight -- the contest is simply whether you
        were willing to send men somewhere that defends nothing.
        """
        msgs: List[str] = []
        for key, sh in self.world.shrines.items():
            if sh.taken:
                continue
            here = [a for a in self.armies if a.at == key and a.state == GARRISON]
            if not here:
                continue
            if len({a.owner for a in here}) > 1:
                # Two parties at one shrine and nobody is praying. Somebody has
                # to leave, and it is decided the usual way.
                here.sort(key=lambda x: host_strength(x.units), reverse=True)
                winner, loser = here[0], here[1]
                res = fight(Side(winner.units), Side(loser.units), rng=self.rng,
                            place=sh.name, field=self.field_at(key))
                winner.prune()
                if res.winner == "attacker":
                    beaten, kept = loser, winner
                else:
                    beaten, kept = winner, loser
                msgs.append(f"Men come to blows at {sh.name}; "
                            f"{beaten.name} is driven off")
                self.scored(kept.owner, won=True)
                self.scored(beaten.owner, won=False)
                if beaten.owner == "player":
                    self.march(beaten.uid, beaten.home)
                elif beaten in self.armies:
                    self.armies.remove(beaten)
                kept.siege_days = 0
                continue
            a = here[0]
            a.siege_days += 1
            if a.siege_days > C.RELIC_DAYS * 3 and a.owner != "player":
                # Nobody waits at a shrine for ever.
                self.march(a.uid, a.home)
                continue
            if a.siege_days < C.RELIC_DAYS:
                continue
            sh.holder = a.owner
            a.siege_days = 0
            who = "You have" if a.owner == "player" else \
                f"{self.world.node_name(a.owner)} has"
            # Somebody else's pilgrimage is not an event in your reign. It goes
            # in, because in the relic chapter it is the whole argument, but it
            # does not shoulder your own years out of the way.
            msgs.append(self.note(f"*** {who} lifted {sh.relic} from {sh.name}. ***",
                                  MOMENTOUS if a.owner == "player" else ROUTINE))
            # Everyone goes home afterwards. A party left standing at a shrine
            # is a lord who counts as having his host out for ever, and a lord
            # whose host is out never declares on anybody.
            self.march(a.uid, a.home)
        return msgs

    #: Chance per day that some lord remembers the shrines are unguarded.
    SHRINE_RACE_ODDS = 0.010     # measured: the five go between roughly day 120
                                 # and day 800, which leaves a real window to
                                 # contest rather than a scramble in the first
                                 # season and nothing afterwards
    SHRINE_COOLDOWN = 150        # days before one lord goes relic-hunting again
    SHRINE_GRACE = 90            # nobody thinks of the shrines before this

    def _shrine_race(self) -> List[str]:
        """Somebody else also wants the bones.

        Without this the shrines are a standing gift to whoever bothers, which
        is not a contest. A lord with ambition and no war on will send a small
        party, and a small party is enough -- there is nothing there to fight.
        """
        if self.day < self.SHRINE_GRACE:
            return []
        free = [k for k, sh in self.world.shrines.items() if not sh.taken]
        if not free or self.rng.random() > self.SHRINE_RACE_ODDS:
            return []
        busy = {a.owner for a in self.armies}
        # A pilgrimage is a party of spearmen, not a war: it must not spend the
        # ambition a lord has been saving to move on his neighbour, or the
        # march quietly stops rearranging itself.
        # And it must not be the lord who is about to move on a neighbour: a
        # party away at a shrine counts as his host being out, so choosing the
        # most ambitious man on the march would quietly keep the peace.
        lords = [t for k, t in self.world.towns.items()
                 if not t.mine and k not in busy
                 and 20.0 < t.ambition < C.HOSTILITY_WAR * 0.6
                 and self.day - t.last_pilgrimage > self.SHRINE_COOLDOWN]
        if not lords:
            return []
        town = lords[self.rng.randrange(len(lords))]
        # Do not send men where somebody is already standing: that is how a
        # march ends up with seven parties at one shrine and no lord at home.
        standing = {a.at for a in self.armies}
        open_ones = [k for k in free if k not in standing]
        if not open_ones:
            return []
        target = min(open_ones, key=lambda k: self.world.distance(town.key, k))
        party = {"spearman": max(6.0, 14.0 * town.muster)}
        a = Army(uid=self.next_army_uid, name=f"{town.lord}'s pilgrimage",
                 owner=town.key, units=party, at=town.key, home=town.key,
                 errand="pilgrimage")
        self.next_army_uid += 1
        self.armies.append(a)
        self._outfit(a, town.key)
        self._set_march(a, town.key, target, party)
        town.last_pilgrimage = self.day
        return [f"{town.lord} of {town.name} sends men to "
                f"{self.world.shrines[target].name}"]

    def muster_cap(self) -> float:
        """How many soldiers your holdings keep at the ordinary price."""
        return lg.cap_for(len(self.world.settlements) + len(self.world.vassals()))

    def muster_cost(self) -> float:
        """The multiplier on what your soldiers cost, for being too many."""
        return lg.overage(float(self.soldiers),
                          len(self.world.settlements) + len(self.world.vassals()))

    RAID_PATIENCE = 12           # days a host will work a country before going home

    #: How much of a besieging host is standing over its own siege works at
    #: any moment, and so what a sortie actually has to fight through.
    #: A siege train is guarded by a detachment, not by the army. Set at a
    #: third, a sortie had to beat sixty-three men to reach a ram in a
    #: two-hundred-man host, which meant the gate was never worth opening.
    #: Of a besieger's baggage, what a successful sortie puts to the torch.
    #: Men who have got in among the engines are standing in the camp, and
    #: his stores are the other thing there is to put a match to.
    #:
    #: A third, which is a great deal against an ordinary besieger carrying
    #: a fortnight -- it leaves him nine days -- and next to nothing against
    #: the one in the siege scenario, who sat down with a year. That is the
    #: intended shape: burning the baggage is how you lift a siege laid by
    #: somebody who was passing, and not how you lift one laid by a man who
    #: came to stay.
    SALLY_BURN = 0.34

    SALLY_GUARD = 0.16

    def shore(self, settlement_key: str = "", on: bool = True) -> str:
        """Work the breach while it is being made.

        Slower than peacetime masonry, nearly twice the stone a yard, and it
        costs men -- masons on a wall somebody is shooting at. Worth it
        against a siege train that is barely out-pacing you and worth
        nothing against one that is not, which is the shape a lever should
        have.
        """
        s = self.world.settlements.get(settlement_key or self.home().name)
        if s is None:
            s = self.home()
        s.shoring = bool(on)
        if not on:
            return f"{s.name}: the masons come off the wall"
        stone = s.market.stock.get("stone", 0.0)
        return (f"{s.name}: masons to the breach"
                + (f" -- {stone:.0f} of stone in store" if stone >= 1
                   else " -- and no stone to do it with"))

    def shut_gates(self, settlement_key: str = "", on: bool = True) -> str:
        """Close your own gates to the roads.

        No cart comes in and none goes out, so nothing you earn on the road
        you earn, and nothing on the road reaches you. It is the only
        answer to the sickness and it is meant to hurt: a fortnight of no
        trade against a chance of a season of no people.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if s.shut == on:
            return (f"{s.name}'s gates are already shut" if on
                    else f"{s.name}'s gates are already open")
        s.shut = on
        if on:
            return (f"{s.name} shuts its gates. No cart comes or goes, and "
                    f"nothing on the road reaches you.")
        return f"{s.name} opens its gates again. The carts may run."

    def _ground_at(self, node: str) -> Dict[str, int]:
        """The country round a place, wherever the map happens to keep it.

        One reader for both questions -- what a battle here is fought over
        and what a host here can eat -- so the two can never disagree about
        what a place is. Somewhere the map never drew country for gets some
        off its own name, because `fields_of({})` is zero and a map with
        towns that feed nobody is a map where every host starves.
        """
        s = self.world.settlements.get(node)
        if s is not None and s.terrain:
            return dict(s.terrain)
        t = self.world.towns.get(node)
        if t is not None and t.ground:
            return dict(t.ground)
        return carto.ground_from_name(node) if node else {}

    def _larder(self, a: Army) -> Tuple[str, float]:
        """The nearest granary that would send carts to this host, and how
        far the carts have to come. A host's own lord's towns only: nobody
        victuals the man besieging him."""
        mine = ([k for k in self.world.settlements] if a.owner == PLAYER
                else [a.owner] if a.owner in self.world.towns else [])
        mine += [k for k, t in self.world.towns.items()
                 if t.owner == a.owner and k not in mine]
        where = a.at or a.bound_for
        best, far = "", 1e9
        for key in mine:
            if key not in self.world.coords or where not in self.world.coords:
                continue
            d = 0.0 if key == where else self.world.distance(key, where)
            if d < far:
                best, far = key, d
        return best, far

    #: Days of the town's own eating that an army may not touch. Eight, which
    #: on the opening town is about a third of the larder -- enough that a
    #: host marches out with a full baggage train, and not so much that the
    #: town is left with nothing. A host that emptied the larder on its way
    #: through the gate would be a tax on raising one at all, and the town
    #: starving behind you is not a cost anybody chose.
    LARDER_FLOOR = 8.0

    def _draw_rations(self, key: str, want: float) -> float:
        """Take rations out of a granary, in whatever it keeps them as.

        Densest food first: cheese and bread travel and a cart of raw wheat
        is mostly cart. Written the other way round at first, which had a
        host march out with the town's apples and leave the bread -- the
        opposite of what a baggage train is for, and it stripped the variety
        the town's mood is partly made of.

        Counted in the same nourishment the townsfolk are fed in, so
        victualling an army is visibly the bread the town would have eaten.
        An army that fed itself out of nowhere would make the whole granary
        chain decorative.
        """
        if want <= 0:
            return 0.0
        market = None
        keep = 0.0
        s = self.world.settlements.get(key)
        if s is not None:
            market = s.market
            per_head, _mood = C.RATION_LEVELS[s.ration_level]
            keep = per_head * s.population * self.LARDER_FLOOR
        else:
            t = self.world.towns.get(key)
            market = t.market if t is not None else None
        if market is None:
            return 0.0
        dense = sorted((k for k in RATION_GOODS if good(k).nourish > 0),
                       key=lambda k: -good(k).nourish)
        on_hand = sum(market.stock.get(k, 0.0) * good(k).nourish for k in dense)
        spare = max(0.0, on_hand - keep)
        want = min(want, spare)
        got = 0.0
        for good_key in dense:
            if got >= want - 1e-9:
                break
            per = good(good_key).nourish
            have = market.stock.get(good_key, 0.0)
            if have <= 0:
                continue
            take = min(have, (want - got) / per)
            market.take(good_key, take)
            got += take * per
        return got

    def _outfit(self, a: Army, from_key: str) -> None:
        """Fill a host's baggage out of the granary it is leaving.

        Every host, whoever raised it -- theirs as well as yours, and the
        relic parties too. An AI that starves itself is not an opponent, and
        a test found exactly that: the war hosts were provisioned here and
        the pilgrimages were not, because they are made somewhere else. One
        call, at every place an army comes into the world.
        """
        a.stores = min(supply.capacity(a.size),
                       a.stores + self._draw_rations(from_key,
                                                     supply.capacity(a.size)))

    def _feed_host(self, a: Army) -> List[str]:
        """One host's morning.

        A garrison sitting in one of your own towns is not fed here: the
        town already feeds it, because `Settlement._feed` counts soldiers in
        the population that eats. Charging it twice would make a garrison
        the most expensive thing in the game to own.
        """
        where = a.at or a.bound_for
        if a.state == GARRISON and where in self.world.settlements:
            a.fed = "in quarters"
            return []
        men = a.size
        if men <= 0:
            return []
        larder, far = self._larder(a)
        # A host that has stopped has a road behind it; one on the march
        # does not, because carts cannot catch a moving army.
        settled = a.state in (BESIEGING, GARRISON, RAIDING)
        share = supply.convoy_share(far, settled) if larder else 0.0
        carts = 0.0
        if share > 0:
            asked = share * men * supply.MARCH_RATION
            carts = self._draw_rations(larder, asked)
        grazed = self.world.grazed.get(where, 0.0)
        ration, a.stores, grazed = supply.eat(
            men, a.stores, ground=self._ground_at(where),
            season=self.season, grazed=grazed, carts=carts)
        if where:
            self.world.grazed[where] = grazed
        a.fed = ration.words()
        msgs: List[str] = []
        if ration.deserted >= 0.5:
            gone = self._thin(a, ration.deserted)
            if gone >= 1 and (a.owner == PLAYER or self.day % 3 == 0):
                msgs.append(f"{a.name} is short of food -- {gone:.0f} men "
                            f"gone in the night")
        return msgs

    def _thin(self, a: Army, men: float) -> float:
        """Take men off a host, spread over what it has. They go home rather
        than die: a starved host is beaten without a battle, which is most
        of what starving one is for."""
        total = a.size
        if total <= 0 or men <= 0:
            return 0.0
        gone = 0.0
        for key in list(a.units):
            share = a.units[key] / total
            off = min(a.units[key], men * share)
            a.units[key] -= off
            gone += off
        a.prune()
        return gone

    def field_at(self, node: str) -> Field:
        """Where and when a battle here would be fought.

        The ground comes off the map -- the same slots the cartographer laid
        down and the same ones that chose the roofline -- and the weather
        off the day, so both are things the player can look at before he
        commits rather than things he reads about afterwards. A place he has
        never been is still country: `going_of` falls back to the name.
        """
        ground = self._ground_at(node)
        return Field(going=going_of(ground, node),
                     weather=sky_on(self.season, self.day, self.seed),
                     place=self.world.node_name(node) or node)

    def fire_baggage(self, settlement_key: str = "", men: int = 0) -> str:
        """Out of the gate at his wagons rather than at his engines.

        The small party's answer, and the reason the size of a sortie is a
        decision at all. At the works you have to beat the watch standing
        over the engines, so too few men is men thrown away. Here you have
        to beat nobody: you have to arrive, fire the wagons and get back, so
        the only thing that matters is not being seen -- and the fewer you
        send the likelier that is and the less it costs you when it is not.

        It does nothing to his rams. What it does is make his own supply the
        thing that runs out first, which is how most sieges that failed
        actually failed, and which was not a thing that could be done to
        anybody until hosts had to eat.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if not s.besieged:
            return f"{s.name} is not besieged"
        foe = self._besieger_of(s)
        if foe is None:
            return "there is nobody outside to go at"
        have = sum(s.units.values())
        if have < 1:
            return f"{s.name} has nobody to send out"
        share = 1.0 if men <= 0 else max(0.05, min(1.0, men / have))
        going = {k: v * share for k, v in s.units.items() if v * share >= 0.5}
        if not going:
            return "too few to be worth opening the gate for"
        if foe.stores <= 1.0:
            return (f"there is nothing left in that camp to burn -- "
                    f"{self.world.node_name(foe.owner)} is living off the country")

        odds = sortie_odds(share, self.field_at(self._key_of(s)).weather,
                           foe.siege_days, s.sorties)
        caught = self.rng.random() < odds.surprise
        s.sorties += 1
        said = [f"{s.name} sends men over the wall at the wagons -- "
                + ("nobody sees them go" if caught
                   else "and the camp is up before they are halfway")]
        if caught:
            burnt = min(0.85, military.RAID_BURN_BASE
                        + military.RAID_BURN_PER * share) * foe.stores
            foe.stores = max(0.0, foe.stores - burnt)
            left = supply.days_left(foe.size, foe.stores)
            said.append(f"The baggage of {self.world.node_name(foe.owner)} "
                        f"burns: {left:.0f} days of food left in that camp")
            # Not free. Somebody has to hold the wagon line while the rest
            # work, and men who go out at night do not all come back.
            lost = self._thin_garrison(s, going, 0.10)
            if lost >= 1:
                said.append(f"{lost:.0f} did not come back")
        else:
            # A running fight to the gate rather than a battle, against
            # whatever turned out -- which for a small party is everybody.
            out = Side(dict(going),
                       attack_mult=self.progress.mult("attack")
                       * self.kin.mult("attack", -1),
                       defense_mult=self.progress.mult("defense"))
            guard = {k: n * odds.roused for k, n in foe.units.items()
                     if UNITS[k].siege_power <= 0 and k != "engineer"}
            them = Side({k: v for k, v in guard.items() if v >= 0.5})
            res = fight(out, them, rng=self.rng,
                        max_rounds=military.RAID_ROUNDS,
                        place=f"the wagon lines before {s.name}",
                        field=self.field_at(self._key_of(s)))
            for key in list(s.units):
                s.units[key] -= going.get(key, 0.0)
                s.units[key] = max(0.0, s.units[key] + out.units.get(key, 0.0))
            for key in list(foe.units):
                met = guard.get(key, 0.0)
                if met:
                    foe.units[key] = max(0.0, foe.units[key] - met
                                         + them.units.get(key, 0.0))
            foe.units = {k: v for k, v in foe.units.items() if v >= 0.5}
            said.append(self._box_score(f"{s.name} raids the wagons", res,
                                        PLAYER, foe.owner))
            said.append("They are driven off the wagon lines with nothing fired")
        self.battles += said
        return "\n".join(said)

    def _besieger_of(self, s: Settlement) -> Optional[Army]:
        """The host sitting round this town, or None."""
        outside = [a for a in self.armies
                   if a.owner != PLAYER and a.at == self._key_of(s)
                   or (a.owner != PLAYER and a.state == BESIEGING
                       and self.world.node_name(a.at) == s.name)]
        return max(outside, key=lambda a: a.size) if outside else None

    def _thin_garrison(self, s: Settlement, went: Dict[str, float],
                       rate: float) -> float:
        """Take a toll off the men who went out, spread over what went."""
        gone = 0.0
        for key, n in went.items():
            off = min(s.units.get(key, 0.0), n * rate)
            s.units[key] = max(0.0, s.units.get(key, 0.0) - off)
            gone += off
        s.units = {k: v for k, v in s.units.items() if v >= 0.5}
        return gone

    def sally(self, settlement_key: str = "", men: int = 0) -> str:
        """Out of the gate at the siege works.

        The other lever, and the opposite of shoring: you give up the wall
        entirely for one fight in the open, to get at the engines. Win and
        the rams and the engineers are gone and the siege has to start
        again; lose and you have spent the garrison that was holding the
        wall-walk.

        A gamble, and for a long time it was not one: it met a fixed share
        of the besieging host whatever the defender did, so any garrison
        walked out, beat a detachment it outnumbered, burnt the rams and
        went back in -- a hundred wins out of a hundred, measured. What it
        turns on now is whether the camp is caught, and that is bought and
        sold with things the player chooses: how many men he sends, what the
        sky is doing, how long the besieger has been sitting there, and
        whether he has tried this before. See `military.sortie_odds`.

        The trade at the middle of it is the size of the party. A small one
        slips out and may not be enough to do the work; a large one does the
        work and is watched forming up.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        if not s.besieged:
            return f"{s.name} is not besieged"
        outside = [a for a in self.armies
                   if a.owner != "player" and a.at == getattr(s, "key", "")
                   or (a.owner != "player" and a.state == BESIEGING
                       and self.world.node_name(a.at) == s.name)]
        if not outside:
            return "there is nobody outside to sally against"
        foe = max(outside, key=lambda a: a.size)
        have = sum(s.units.values())
        if have < 1:
            return f"{s.name} has nobody to send out"
        share = 1.0 if men <= 0 else max(0.05, min(1.0, men / have))
        going = {k: v * share for k, v in s.units.items() if v * share >= 0.5}
        if not going:
            return "too few to be worth opening the gate for"
        # No battlement: that is the whole cost of coming out from behind it.
        out = Side(dict(going),
                   attack_mult=self.progress.mult("attack")
                   * self.kin.mult("attack", -1),
                   defense_mult=self.progress.mult("defense"))
        # What turns out to meet you. Caught, it is the guard over the
        # engines; roused, it is most of his host, in the open, with no wall
        # at your back. The roll is made here rather than read off the odds
        # so that the odds shown before are the odds actually run.
        odds = sortie_odds(share, self.field_at(self._key_of(s)).weather,
                           foe.siege_days, s.sorties)
        caught = self.rng.random() < odds.surprise
        s.sorties += 1
        met_share = odds.quiet if caught else odds.roused
        works, guard = {}, {}
        for key, n in foe.units.items():
            if UNITS[key].siege_power > 0 or key == "engineer":
                works[key] = n
            else:
                guard[key] = n * met_share
        met = {k: v for k, v in list(works.items()) + list(guard.items())
               if v >= 0.5}
        them = Side(dict(met))
        if caught:
            # Among them before they have formed. This is what makes a small
            # party worth sending: without it, stealth bought you nothing you
            # could fight with, and the only answer was to send everybody.
            out.attack_mult *= military.SORTIE_CAUGHT_ATTACK
            them.morale *= military.SORTIE_CAUGHT_MORALE
        # The works are outside the gate, so a sortie is fought on the town's
        # own ground and under the day's own sky -- which is the argument for
        # going out in a hard frost and not in April.
        out_field = replace(self.field_at(self._key_of(s)),
                            place=f"the works before {s.name}")
        res = fight(out, them, rng=self.rng, orders=(getattr(s, "order", "") or STORM,
                                                     foe.order), field=out_field)
        said = [f"{s.name} opens the gate -- "
                + ("the camp is asleep" if caught
                   else "and the camp is up and waiting")]
        # What came back, on both sides. The guard that was not at the works
        # was never in this fight and is still out there.
        for key in list(s.units):
            s.units[key] -= going.get(key, 0.0)
            s.units[key] = max(0.0, s.units[key] + out.units.get(key, 0.0))
        for key in list(foe.units):
            fought = met.get(key, 0.0)
            if fought:
                foe.units[key] = max(0.0, foe.units[key] - fought
                                     + them.units.get(key, 0.0))
        foe.units = {k: v for k, v in foe.units.items() if v >= 0.5}
        said.append(self._box_score(f"{s.name} sallies", res, PLAYER, foe.owner))
        if res.winner == "attacker":
            # The engines are what you came for, and they do not run. Count
            # what was standing there before rather than what is left to
            # burn: the fight itself kills most of it, and reading the
            # remainder reported a successful sortie as burning "no one".
            gone = {k: n for k, n in works.items()
                    if n - foe.units.get(k, 0.0) >= 0.5}
            for key, n in gone.items():
                gone[key] = n - foe.units.get(key, 0.0)
            for key in list(works):
                foe.units.pop(key, None)
            for key, n in works.items():
                if key not in gone:
                    gone[key] = n
            foe.siege_days = 0
            foe.siege = type(foe.siege)()
            said.append(f"The works before {s.name} are burnt"
                        + (": " + describe(gone) if gone else ""))
            # And the baggage behind them. Men who have got in among the
            # engines are standing in the camp, and a besieger's stores are
            # the other thing there is to put a torch to -- which is what
            # actually lifted sieges. It gives the defender a second way to
            # spend a sortie: burn his month rather than his rams.
            burnt = foe.stores * self.SALLY_BURN
            if burnt > 0:
                foe.stores -= burnt
                days = supply.days_left(foe.size, foe.stores)
                said.append(f"His baggage burns with them -- "
                            f"{days:.0f} days of food left in that camp")
        else:
            said.append(f"The sally is thrown back under the walls of {s.name}")
        self.battles += said
        return "\n".join(said)

    def order_host(self, uid: int, key: str) -> str:
        """Tell a host how to fight before it has to."""
        from .military import ORDERS, order as order_of, order_note
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != "player":
            return "that host is not yours to order"
        if key not in ORDERS:
            return (f"there is no order called {key!r}; try "
                    + ", ".join(ORDERS))
        a.order = key
        return f"{a.name}: {order_of(key).name}. {order_note(a.units, key)}"

    def raid(self, uid: int) -> str:
        """Order a host of yours to burn the country instead of the walls."""
        a = self.army(uid)
        if not a:
            return f"no host {uid}"
        if a.owner != "player":
            return "that host is not yours to order"
        if a.state not in (BESIEGING, GARRISON, RAIDING):
            return f"{a.name} is on the road; it must arrive first"
        if self.world.is_friendly(a.at):
            return f"{a.name} stands in friendly country -- there is nothing to burn"
        a.state = RAIDING
        a.siege_days = 0
        return f"{a.name} looses on the country around {self.world.node_name(a.at)}"

    def _raid(self, a: Army) -> List[str]:
        a.siege_days += 1
        if a.siege_days > self.RAID_PATIENCE:
            a.siege_days = 0
            where = self.world.node_name(a.at)
            if a.owner == "player":
                self.march(a.uid, a.home)
                return [f"{a.name} has stripped the country round {where} and turns for home"]
            if a in self.armies:
                self.armies.remove(a)
            return [f"The raiders around {where} ride off with what they could carry"]
        if a.at in self.world.towns:
            return self._raid_town(a, self.world.towns[a.at])
        s = self.world.settlements.get(a.at)
        return self._raid_settlement(a, s) if s else []

    def _raid_settlement(self, a: Army, s: Settlement) -> List[str]:
        """Somebody burning *your* country. The walls do not enter into it."""
        msgs: List[str] = []
        s.raided = True
        raiders = Side(a.units)
        garrison = Side(s.units, attack_mult=self.progress.mult("attack"),
                        defense_mult=self.progress.mult("defense"))
        # Everything a settlement has outside its walls is what is at risk.
        outside = sum(b.spec.jobs for b in s.buildings
                      if b.complete and b.spec.terrain in ("fertile", "forest",
                                                           "hills", "clay", "coast"))
        worked, _hurt, lost, lines = raid_day(
            raiders, garrison, out_of_doors=6.0 * max(1.0, outside), rng=self.rng)
        s.raid_pressure = max(s.raid_pressure, worked)
        a.units = {k: v for k, v in raiders.units.items() if v >= 0.5}
        s.units = {k: v for k, v in garrison.units.items() if v >= 0.5}
        # Stores carried off, people driven off the land.
        for k in list(s.market.stock):
            s.market.take(k, s.market.stock[k] * C.RAID_LOOT * worked)
        s.population = max(4.0, s.population * (1.0 - C.RAID_FLIGHT * worked))
        # Raiders carry torches. This is the cheapest way there is to hurt a
        # town you cannot take, and the reason a stone town sleeps better.
        # Burning your fields is a reason anybody on the march will accept.
        self.court.give_ground(a.owner, "raided", self.day)
        if self.rng.random() < C.RAID_TORCH * worked:
            msgs.extend(s.kindle(self.rng, 1 + int(2 * worked)))
        if self.day % 4 == 0:
            msgs.append(f"{s.name} is being raided: {lines[0]}")
        if lost:
            msgs.append(f"Sortie from {s.name}: "
                        f"{describe({k: round(v) for k, v in lost.items()})} cut down")
        return msgs

    def _raid_town(self, a: Army, town) -> List[str]:
        """You, burning somebody else's country. Loot comes home as coin."""
        msgs: List[str] = []
        if a.owner == "player":
            self.kin.did("merciful", -0.05)
            self._betray_friend(town.key)
        raiders = Side(a.units,
                       attack_mult=(self.progress.mult("attack")
                                    * self.kin.mult("attack", a.uid))
                       if a.owner == "player" else 1.0)
        garrison = Side(dict(town.garrison))
        worked, _hurt, lost, lines = raid_day(
            raiders, garrison, out_of_doors=90.0 * town.prosperity, rng=self.rng)
        a.units = {k: v for k, v in raiders.units.items() if v >= 0.5}
        town.garrison = {k: v for k, v in garrison.units.items() if v >= 0.5}
        # A raid does not take a town; it makes the town poorer and the lord
        # angrier, which is the point of it.
        town.prosperity = max(0.35, town.prosperity - C.RAID_PROSPERITY * worked)
        if a.owner == "player" and not town.mine:
            # Written down at last: `raided_them` was in the book and nothing
            # ever put it there, so burning a lord's country cost you nothing
            # he would remember past his temper.
            self.court.write(town.key, "raided_them", -3.0 * worked, self.day)
            self.court.reckon(town.key, 1.0 * worked)
            if self.court.ground_for(town.key, self.day) is None:
                others = [k for k, x in self.world.towns.items()
                          if not x.mine and k != town.key]
                self.court.write_all(others, "unjust", -0.6 * worked, self.day)
        if a.owner == "player":
            loot = C.RAID_LOOT_COIN * worked * town.prosperity * town.wealth
            self.treasury += loot
            self._plunder += loot
            if self.day % 4 == 0:
                msgs.append(f"{a.name} strips the country round {town.name}: "
                            f"{loot:,.0f}c and {lines[0]}")
        if lost:
            msgs.append(f"{town.name}'s garrison sorties: "
                        f"{describe({k: round(v) for k, v in lost.items()})} lost raiding")
        return msgs

    def _siege_town(self, a: Army, town) -> List[str]:
        """Anyone besieging a foreign town -- you, or one lord besieging another."""
        msgs: List[str] = []
        player = a.owner == "player"
        besieger = Side(a.units,
                        attack_mult=(self.progress.mult("attack")
                                     * self.progress.mult("siege")
                                     * self.kin.mult("siege")
                                     * self.kin.mult("attack", a.uid)
                                     * manly.attack_bonus(self.lord, a.uid))
                        if player else 1.0,
                        defense_mult=self.progress.mult("defense") if player else 1.0)
        # Your own hosts standing in a sworn town fight for it.
        stationed = [x for x in self.armies
                     if x is not a and x.owner == "player" and x.at == town.key
                     and town.mine]
        defenders = dict(town.garrison)
        for x in stationed:
            for k, n in x.units.items():
                defenders[k] = defenders.get(k, 0.0) + n
        # An Ox on his own parapet is a different proposition from a
        # Magpie on his. What he takes, he keeps.
        # A wall that has thrown one storm back is readier for the next:
        # Warband's siege hardness, a point of battlement a little under
        # every seventeen of it, and wearing off by two a day.
        holder = Side(defenders, battlement=8.0 * (
            1.0 if town.mine else lordly.sort_of(town.key).holds)
            + town.hardened * 0.06)
        works = town.works()
        if not player:
            a.siege.plan = choose(works, siege_power=a.siege_power,
                                  engineers=a.units.get("engineer", 0.0),
                                  host=a.size, garrison=sum(town.garrison.values()),
                                  wall=town.wall_hp, wall_max=town.wall_max,
                                  patient=a.siege_days > 8, days=a.siege_days)
        wall, _la, _ld, lines = siege_day(besieger, holder, town.wall_hp, self.rng,
                                          town.name, wall_max=town.wall_max,
                                          works=works, state=a.siege,
                                          faith=town.faith())
        town.wall_hp = wall
        if player:
            town.hostility = C.HOSTILITY_WAR
        if self.day % 5 == 0 and lines and (player or town.mine):
            msgs.append(f"{a.name}: {lines[0]}")
        msgs += self._starve_town(town, a, holder, player)
        if not town.mine and holder.alive():
            msgs += self._sally_at(town, a, holder, besieger, player)
        if storms_now(a.siege.plan, wall, holder.alive()) and self._dares(a, holder):
            battle = open_battle(besieger, holder, rng=self.rng, place=town.name,
                                 orders=(a.order, lordly.sort_of(town.key).fights),
                                 field=self.field_at(town.key), works=works,
                                 state=a.siege, wall_max=town.wall_max)
            # Yours to fight if you are going in or it is yours to hold.
            # Two lords at each other's walls is nobody's business but
            # theirs, and resolves at once as it always has.
            if (player or town.mine) and self.battles_mode == "play":
                self.pending = PendingBattle(
                    battle=battle, kind="storm", army=a.uid, where=town.key,
                    side="attacker" if player else "defender",
                    title=town.name, day=self.day,
                    stationed=[x.uid for x in stationed],
                    wall_standing=wall, wall_full=town.wall_max)
                msgs.append(self.note(
                    f"*** THE STORM GOES IN AT {town.name.upper()}. "
                    f"The day waits on it. ***", MOMENTOUS))
                return msgs
            battle.run()
            battle.close()
            return msgs + self._after_storm(battle.res, a, town, holder,
                                            besieger, stationed)
        self._settle_survivors(a, town, holder, stationed)
        return msgs

    def _after_storm(self, res, a: Army, town, holder: Side, besieger: Side,
                     stationed: List[Army]) -> List[str]:
        """What follows an assault on a foreign wall, whoever fought it.

        One function for the fight resolved at once and the fight resolved
        a round at a time, because two copies of "what happens when a town
        falls" is one of them forgetting the relics.
        """
        msgs: List[str] = []
        player = a.owner == "player"
        msgs.append(f"ASSAULT ON {town.name.upper()}: the {res.winner} holds "
                    f"the ground after {res.rounds} rounds")
        msgs.append(self._box_score(f"{a.name} storms {town.name}", res,
                                    a.owner, town.key))
        self.scored(a.owner, won=res.winner == "attacker")
        self.scored(town.key, won=res.winner != "attacker")
        a.siege_days = 0
        if res.winner == "attacker":
            self.took_town(a.owner, town.key)
            if player:
                self.kin.did("merciful", -0.35)
                self.kin.teach("engineering", 14.0, self.day, post="master")
                self.kin.teach("tactics", 10.0, self.day, post="captain",
                               target=str(a.uid))
            msgs.append(self._take_town(town, a))
            if not player:
                line = lordly.says(a.owner, "takes", self.voice)
                if line:
                    msgs.append(f'    {self.world.node_name(a.owner)}: '
                                f'"{line}"')
            a.prune()
            return msgs        # the garrison is the victor's now, not the survivors'
        elif res.broken_off == "attacker":
            # A storm called off is not a storm thrown back. He is still at
            # the wall, and he has kept most of his men to try again with.
            town.hardened = min(200.0, town.hardened + 40.0)
            msgs.append(f"{a.name} calls off the storm and draws back to the "
                        f"lines before {town.name}")
        elif player:
            a.state = RETURNING
            town.hardened = min(200.0, town.hardened + 100.0)
            self.court.reckon(town.key, -20.0)
            msgs.append(f"{a.name} is thrown back from {town.name}, and the "
                        f"men on its wall have learned how it is done")
            # He was standing where the arrows were. Sometimes that tells.
            if self.lord.riding == a.uid:
                msgs += self._lord_fell()
            self.march(a.uid, a.home)
        else:
            a.state = RETURNING
            town.hardened = min(200.0, town.hardened + 100.0)
            if a.owner in self.world.towns:
                # A letter is easier to sign than to keep. Every host of
                # theirs you break takes a bite out of the reason it was
                # written, which is the one way out that is not money.
                self.court.write(a.owner, "beaten", 22.0, self.day)
                self.court.reckon(a.owner, 20.0)
                line = lordly.says(a.owner, "beaten", self.voice)
                if line:
                    msgs.append(f'    {self.world.towns[a.owner].lord}: '
                                f'"{line}"')
            self.march(a.uid, a.home)
        town.wall_hp = max(town.wall_hp, town.wall_max * 0.15)
        self._settle_survivors(a, town, holder, stationed)
        return msgs

    def _starve_town(self, town, a: Army, holder: Side, player: bool) -> List[str]:
        """A garrison that has eaten the town's larder starts to die of it.

        Warband wounds a starving garrison one day in ten; here it thins a
        little every day the granary stands under a fifth of what the town
        wants, which is a blockade's whole argument: you do not have to
        carry the wall if you can wait for the men on it to stop standing.
        """
        food = sum(v for k, v in town.market.stock.items() if good(k).nourish > 0)
        want = sum(v for k, v in town.market.target.items() if good(k).nourish > 0)
        if want <= 0 or food >= 0.2 * want:
            return []
        for k in list(holder.units):
            holder.units[k] *= 0.975
        town.garrison = {k: v for k, v in holder.units.items() if v >= 0.5}
        if self.day % 5 == 0 and (player or town.mine):
            return [f"{town.name} is starving: the granary is bare and the "
                    f"garrison thins by the day"]
        return []

    def _sally_at(self, town, a: Army, holder: Side, besieger: Side,
                  player: bool) -> List[str]:
        """A lord's garrison goes out at the lines, now and then.

        Only the player ever sallied; a lord sat behind his wall until it
        fell. Stronghold's lords keep men for exactly this. A garrison near
        the besiegers' strength goes out one day in twenty-five or so, after
        the first few days, hurts the lines and comes back lighter.
        """
        if a.siege_days < 4:
            return []
        if host_strength(holder.units) < 0.5 * host_strength(besieger.units):
            return []
        dice = random.Random(f"{self.seed}:sally:{town.key}:{self.day}")
        if dice.random() > 0.04 * lordly.sort_of(town.key).holds:
            return []
        hurt = {k: v * 0.06 for k, v in a.units.items()}
        a.units = {k: v - hurt[k] for k, v in a.units.items() if v - hurt[k] >= 0.5}
        for k in list(holder.units):
            holder.units[k] *= 0.97
        town.garrison = {k: v for k, v in holder.units.items() if v >= 0.5}
        if player:
            return [f"{town.name}'s garrison sallies against your lines at "
                    f"dawn -- {describe({k: round(v) for k, v in hurt.items() if v >= 0.5}) or 'a few men'} lost"]
        return []

    def _settle_survivors(self, a: Army, town, holder: Side,
                          stationed: List[Army]) -> None:
        """Casualties fall on the stationed hosts first, then on the town levy."""
        a.prune()
        survivors = dict(holder.units)
        for x in stationed:
            for k in list(x.units):
                share = min(x.units[k], survivors.get(k, 0.0))
                survivors[k] = survivors.get(k, 0.0) - share
                x.units[k] = share
            x.prune()
        town.garrison = {k: v for k, v in survivors.items() if v >= 0.5}

    def _siege_settlement(self, a: Army, s: Settlement) -> List[str]:
        msgs: List[str] = []
        s.besieged = True
        besieger = Side(a.units)
        at_home = self.lord.at_home and self.lord.seat in ("", s.name)
        # The wall as it was drawn, not as it was bought. A garrison is a
        # number of men and a wall is a number of yards, so what decides
        # whether the wall-walk is held is men to the yard -- which is the
        # whole price of enclosing more ground than you can man, and the
        # reason a small tight castle is an answer rather than a poor one.
        castle = s.plan()
        reading = keeps.read(castle)
        holder = Side(s.units, attack_mult=self.progress.mult("attack"),
                      defense_mult=self.progress.mult("defense"),
                      battlement=6.0 + s.effect("battlement") + s.hardened * 0.06
                      + (manly.HOME_DEFENCE if at_home else 0.0)
                      + self.kin.bonus("defence")
                      + keeps.manning(reading.density(sum(s.units.values()))))
        works = Works.of([b.key for b in s.buildings
                          if b.complete and b.spec.terrain == "rampart"])
        # Counts come off the shopping list (an oil pot is over the gate
        # wherever the gate is); shape comes off the ground.
        drawn = Works.read(castle, reading)
        works.naked, works.depth = drawn.naked, drawn.depth
        if a.owner != "player":
            a.siege.plan = choose(works, siege_power=a.siege_power,
                                  engineers=a.units.get("engineer", 0.0),
                                  host=a.size, garrison=sum(s.units.values()),
                                  wall=s.wall_hp, wall_max=s.wall_max(self.progress),
                                  patient=a.siege_days > 8, days=a.siege_days)
        wall, _la, _ld, lines = siege_day(besieger, holder, s.wall_hp, self.rng, s.name,
                                          wall_max=s.wall_max(self.progress),
                                          works=works, state=a.siege,
                                          have_pitch=s.market.stock.get("charcoal", 0) >= 5,
                                          faith=s.coverage("faith_reach"))
        if a.siege.plan == INVEST:
            s.blockaded = True
            self.court.give_ground(a.owner, "blockade", self.day)
        s.wall_hp = wall
        if self.day % 5 == 0 and lines:
            msgs.append(f"{s.name} under siege: {lines[0]}")
        s.units = {k: v for k, v in holder.units.items() if v >= 0.5}
        a.units = {k: v for k, v in besieger.units.items() if v >= 0.5}
        # A hungry town is a town whose soldiers are hungry too.
        if s.report is not None and s.report.hunger > 0.5 and s.units:
            thin = 0.02 * s.report.hunger
            had = sum(s.units.values())
            s.units = {k: v * (1 - thin) for k, v in s.units.items() if v * (1 - thin) >= 0.5}
            # They thin *with* the town: the hunger is already taking them
            # off the population by the road out, so the roll must not bury
            # them a second time as men killed at the wall.
            self._roll_moved(self._key_of(s), sum(s.units.values()) - had)
            holder = Side(s.units, attack_mult=holder.attack_mult,
                          defense_mult=holder.defense_mult,
                          battlement=holder.battlement)
            if self.day % 5 == 0:
                msgs.append(f"{s.name} is starving, and the garrison thins with "
                            f"the town -- {s.report.hunger:.0%} of the ration "
                            f"going unserved")
        if storms_now(a.siege.plan, wall, holder.alive()) and self._dares(a, holder):
            # Your own wall: whatever you told the garrison to do.
            battle = open_battle(besieger, holder, rng=self.rng, place=s.name,
                                 orders=(a.order, getattr(s, "order", "") or HOLD),
                                 field=self.field_at(self._key_of(s)),
                                 works=works, state=a.siege,
                                 have_pitch=s.market.stock.get("charcoal", 0) >= 5,
                                 wall_max=s.wall_max(self.progress))
            if self.battles_mode == "play":
                self.pending = PendingBattle(
                    battle=battle, kind="wall", army=a.uid,
                    where=self._key_of(s), side="defender", title=s.name,
                    day=self.day, wall_standing=wall,
                    wall_full=s.wall_max(self.progress))
                msgs.append(self.note(
                    f"*** THE STORM GOES IN AT {s.name.upper()}. "
                    f"The day waits on it. ***", MOMENTOUS))
                return msgs
            battle.run()
            battle.close()
            msgs += self._after_wall(battle.res, a, s, holder, besieger)
        return msgs

    def _after_wall(self, res, a: Army, s: Settlement, holder: Side,
                    besieger: Side) -> List[str]:
        """What follows an assault on your own wall, however it was fought."""
        msgs: List[str] = []
        msgs.append(self._box_score(f"{a.name} storms {s.name}", res,
                                    a.owner, PLAYER))
        self.scored(a.owner, won=res.winner == "attacker")
        self.scored(PLAYER, won=res.winner != "attacker")
        if res.winner == "attacker":
            self.took_town(a.owner, PLAYER)
        msgs.append(f"ASSAULT ON {s.name.upper()}: the {res.winner} holds the "
                    f"ground after {res.rounds} rounds")
        # Men who get over a wall set light to what is behind it, whether
        # or not they end up holding the ground.
        msgs.extend(s.kindle(self.rng, self.rng.randrange(2, 6)))
        s.units = {k: v for k, v in holder.units.items() if v >= 0.5}
        a.units = {k: v for k, v in besieger.units.items() if v >= 0.5}
        if res.winner == "attacker":
            if a.owner in self.world.towns:
                self.court.reckon(a.owner, -30.0)
            msgs.append(self._sack(s, a))
        elif res.broken_off == "attacker":
            s.hardened = min(200.0, s.hardened + 40.0)
            msgs.append(f"The storm is called off before {s.name}; the host "
                        f"draws back to its lines")
            a.siege_days = 0
        else:
            s.hardened = min(200.0, s.hardened + 100.0)
            if a.owner in self.world.towns:
                self.court.reckon(a.owner, 25.0)
            msgs.append(f"The host is broken beneath the walls of {s.name}; "
                        f"the men on it have learned how it is done")
            if a in self.armies:
                self.armies.remove(a)
            if a.home in self.world.towns:
                self.world.towns[a.home].hostility = 25.0
        s.wall_hp = max(s.wall_hp, s.wall_max(self.progress) * 0.10)
        return msgs

    # --------------------------------------------------------- the battle
    def battle_step(self, action: str = "fight", arg: str = "") -> str:
        """Do one thing in the fight the day is waiting on.

        `fight` is a round. `auto` is the rest of it. The others are the
        levers -- an order, the reserve, the oil, the pitch, breaking off --
        each of which the Battle itself decides whether you may pull, so
        the console and the picture cannot disagree about that.
        """
        pb = self.pending
        if pb is None:
            return "there is no fight waiting on you"
        b, me = pb.battle, pb.side
        if action == "close":
            if not b.over:
                return "the fight is not over"
            self.pending = None
            return "back to the day"
        if b.over:
            return "\n".join(pb.after) or "the fight is over"
        if action == "fight":
            said = "\n".join(b.step()) or "a quiet round"
        elif action == "auto":
            b.run()
            said = "\n".join(b.res.log[-3:])
        elif action == "order":
            said = b.reorder(me, arg)
        elif action == "commit":
            said = b.commit(me)
        elif action in ("oil", "pitch"):
            if me != "defender":
                said = "you are not the one on the wall"
            else:
                said = b.pour_oil() if action == "oil" else b.fire_pitch()
        elif action == "break":
            said = b.break_off(me)
        elif action == "ride":
            said = self._ride(pb, arg)
        else:
            return (f"battle: nothing called {action!r}; fight, ride, auto, order, "
                    f"commit, oil, pitch, break, close")
        if b.over:
            said += "\n" + "\n".join(self._finish_battle())
        return said

    # ------------------------------------------------------ at their head
    def _lord_in(self, pb: PendingBattle) -> str:
        """Why the lord is not in this fight to ride at their head, or ''."""
        why = self.lord.cannot_ride()
        if why:
            return why
        if pb.kind == "wall":
            if not (self.lord.at_home and self.lord.seat in ("", pb.where, pb.title)):
                return f"{self.lord.name} is not at {pb.title}"
            return ""
        mine = [pb.army] if pb.kind == "storm" else (
            pb.stationed if pb.side == "attacker" else pb.foes)
        if self.lord.riding not in mine:
            return f"{self.lord.name} is not with this host"
        return ""

    def _ride_view(self, pb: PendingBattle) -> dict:
        """What riding at their head would meet this round, for the screen
        that fights it and the console that rolls it."""
        b = pb.battle
        them = b.side("defender" if pb.side == "attacker" else "attacker")
        why = self._lord_in(pb)
        who = self.kin.lord
        valour = who.level("valour") if who is not None else 0
        horse = them.class_share().get(military.HORSE, 0.0)
        press = int(min(9, 3 + them.alive() / 25.0 + 3 * horse))
        return {"can": not why and not b.over, "why": why, "name": self.lord.name,
                "valour": valour, "hits": self.lord.hits,
                "down": manly.RIDE_HITS_DOWN, "press": press,
                "cap": self._ride_cap(them), "rode": pb.lord_rode,
                "kills": pb.lord_kills}

    @staticmethod
    def _ride_cap(them: Side) -> int:
        return max(1, min(manly.RIDE_KILL_CAP, int(them.alive() * manly.RIDE_KILL_SHARE)))

    def _roll_ride(self, pb: PendingBattle) -> Tuple[int, int]:
        """The dice ride for him where there is no screen: the console."""
        v = self._ride_view(pb)
        rng = pb.battle.rng
        p_kill = min(0.8, 0.35 + 0.05 * v["valour"])
        p_hit = max(0.08, 0.30 - 0.03 * v["valour"])
        kills = sum(1 for _ in range(v["cap"]) if rng.random() < p_kill)
        hits = sum(1 for _ in range(v["press"]) if rng.random() < p_hit)
        return kills, min(hits, manly.RIDE_HITS_DOWN)

    def _ride(self, pb: PendingBattle, arg: str) -> str:
        """Fight this round at the head of your own men.

        `arg` is what the screen saw -- "kills hits" -- or nothing, in
        which case the dice ride. Either way the engine believes only so
        much: kills are capped at an order's worth of the men facing him,
        blows count against the three that bear him down, and the round
        then runs as any round does. His men, seeing him in front, are a
        little steadier; he learns valour by doing it; and if he is borne
        down he is abed for weeks or dead where he stood.
        """
        b = pb.battle
        why = self._lord_in(pb)
        if why:
            return why
        parts = arg.split()
        if len(parts) >= 2 and all(x.lstrip("-").isdigit() for x in parts[:2]):
            kills, hits = int(parts[0]), int(parts[1])
        else:
            kills, hits = self._roll_ride(pb)
        them = b.side("defender" if pb.side == "attacker" else "attacker")
        mine = b.side(pb.side)
        kills = max(0, min(kills, self._ride_cap(them)))
        hits = max(0, min(hits, manly.RIDE_HITS_DOWN))
        # The men he cut down come off the line facing him, foot first.
        left = float(kills)
        for key in sorted(them.units, key=lambda k: (UNITS[k].unit_class != military.FOOT, k)):
            take = min(them.units[key], left)
            them.units[key] -= take
            left -= take
            if left <= 0:
                break
        them.units = {k: v for k, v in them.units.items() if v >= 0.5}
        gain = min(manly.RIDE_RALLY, manly.RIDE_RALLY_CAP - pb.lord_rally)
        if gain > 0:
            mine.morale += gain
            pb.lord_rally += gain
        pb.lord_rode += 1
        pb.lord_kills += kills
        self.lord.hits += hits
        self.kin.teach("valour", manly.VALOUR_PER_RIDE + 2.0 * kills, self.day)
        blow = ("no blow taken" if hits == 0 else "one blow taken" if hits == 1
                else f"{hits} blows taken")
        said = [f"{self.lord.name} rides at their head: "
                f"{kills} {'man' if kills == 1 else 'men'} cut down, {blow}"]
        if self.lord.hits >= manly.RIDE_HITS_DOWN:
            heir = self.kin.heir(self.day)
            fell = self.lord.borne_down(self.rng, heir.name if heir else self.lord.name)
            pb.lord_lines += fell
            said += [self.note(ln, MOMENTOUS) for ln in fell]
            if not self.lord.alive:
                who = self.kin.lord
                if who is not None:
                    pb.lord_lines += self.kin.bury(who, self.day)
                for st in self.world.settlements.values():
                    st.popularity = max(0.0, st.popularity - manly.MOURNING)
        said += b.step() or ["a quiet round"]
        return "\n".join(said)

    def _finish_battle(self) -> List[str]:
        """The fight is over: take the dressing off and let the day have it.

        The aftermath runs once, here, and is kept on the fight rather than
        the fight being thrown away -- see PendingBattle.after. The next day
        puts it away; so does `battle close`.
        """
        pb = self.pending
        if pb is None:
            return []
        if pb.settled:
            return list(pb.after)
        b = pb.battle
        b.close()
        a = self.army(pb.army)
        msgs: List[str] = []
        if a is None:
            msgs.append("the host that was going in is gone")
        elif pb.kind == "field":
            relief = [x for x in (self.army(u) for u in pb.stationed) if x]
            ring = [x for x in (self.army(u) for u in pb.foes) if x]
            if relief and ring:
                msgs = self._after_field(b.res, pb.where, relief, ring,
                                         b.attacker, b.defender)
        elif pb.kind == "wall":
            s = self.world.settlements.get(pb.where)
            if s is not None:
                msgs = self._after_wall(b.res, a, s, b.defender, b.attacker)
        else:
            town = self.world.towns.get(pb.where)
            stationed = [x for x in (self.army(u) for u in pb.stationed) if x]
            if town is not None:
                msgs = self._after_storm(b.res, a, town, b.defender, b.attacker,
                                         stationed)
        if pb.lord_rode:
            msgs.append(f"{self.lord.name if self.lord.alive else 'The lord'} rode "
                        f"{pb.lord_rode} {'round' if pb.lord_rode == 1 else 'rounds'} at "
                        f"their head and cut down {pb.lord_kills} "
                        f"{'man' if pb.lord_kills == 1 else 'men'} by his own hand")
            msgs += [ln for ln in pb.lord_lines if ln not in msgs]
        self.lord.hits = 0
        pb.after = list(msgs)
        pb.settled = True
        for line in msgs:
            if line.strip().startswith("box"):
                self.battles.append(line.strip())
        return msgs

    def battle_view(self) -> Optional[dict]:
        """The fight, as a screen needs it -- or None when the day is not
        waiting on one."""
        pb = self.pending
        if pb is None:
            return None
        b = pb.battle
        v = b.snapshot()
        mine = b.side(pb.side)
        v.update({"kind": pb.kind, "side": pb.side, "title": pb.title,
                  "day": pb.day, "after": list(pb.after),
                  "wall_standing": round(pb.wall_standing, 1),
                  "wall_full": round(pb.wall_full, 1),
                  "field": b.field_words,
                  "can": b.can(pb.side),
                  "orders": [{"key": o.key, "name": o.name, "blurb": o.blurb,
                              "rounds": o.rounds}
                             for o in military.ORDERS.values()],
                  "modifiers": self._battle_modifiers(pb),
                  "ride": self._ride_view(pb),
                  "kinds": {k: {"name": u.name, "kind": u.unit_class,
                                "counters": dict(u.counters)}
                            for k in set(b.attacker.units) | set(b.defender.units)
                            for u in [UNITS[k]]},
                  "costs": {"reorder": military.REFORM_COST,
                            "commit": military.COMMIT_PUNCH,
                            "break": military.ROUT_TOLL}})
        return v

    def _battle_modifiers(self, pb: PendingBattle) -> List[dict]:
        """Every dial your side is fighting under, as rows a screen can show.

        Shown rather than hidden, which is the one thing worth taking from
        the Paradox battle screen: the numbers are small and they are the
        whole difference in a close fight, so the player is owed them.
        """
        b = pb.battle
        mine = b.side(pb.side)
        o = military.order(b.orders[0] if pb.side == "attacker" else b.orders[1])
        rows: List[dict] = []
        if b.field_words:
            rows.append({"what": "the field", "value": b.field_words, "good": None})
        # Only the kinds you actually have: telling a garrison with no horse
        # what the mud would do to its horse is noise (see field_note).
        have = mine.class_share()
        for cls, v in sorted(mine.class_mult.items()):
            if abs(v - 1.0) > 0.004 and have.get(cls, 0.0) >= 0.02:
                rows.append({"what": f"your {cls} on this ground",
                             "value": f"{v:.2f}", "good": v > 1.0})
        rows.append({"what": f"order: {o.name}",
                     "value": f"attack {o.attack:.2f} · defence {o.defense:.2f} "
                              f"· steadiness {o.morale:.2f}",
                     "good": None})
        if mine.battlement:
            rows.append({"what": "the battlement", "value": f"+{mine.battlement:.1f}",
                         "good": True})
        w = b.works
        if w is not None and pb.side == "defender":
            if w.towers:
                rows.append({"what": "towers", "value": str(w.towers), "good": True})
            if w.oil:
                rows.append({"what": "oil over the gate",
                             "value": "spent" if b.oil_spent else "ready", "good": not b.oil_spent})
            if w.pitch:
                spent = b.pitch_spent or (b.state is not None and b.state.pitch_spent)
                rows.append({"what": "the pitch ditch",
                             "value": "burned" if spent else ("ready" if b.have_pitch else "no charcoal"),
                             "good": (not spent) and b.have_pitch})
        # Read off the snapshot, not the side: once the fight is closed the
        # side wears its pre-battle dial again and would say 1.00.
        now = b.snapshot()[pb.side]["morale"]
        rows.append({"what": "steadiness now", "value": f"{now:.2f}", "good": now >= 0.6})
        return rows

    def _sack(self, s: Settlement, a: Army) -> str:
        """A storming is a catastrophe, not a trapdoor.

        The keep is thrown down and the town gutted, but so long as you hold
        ground anywhere you are still in the game -- which is the whole argument
        for founding a second settlement before you need one.
        """
        self._sacked += 1
        keep = next((b for b in s.buildings if b.key == "keep"), None)
        # Relics go where the strongbox goes.
        for sh in self.world.shrines.values():
            if sh.holder == "player":
                sh.holder = a.owner
        loot = 0.0
        share = 0.60 if keep else 0.45
        for k in ALL_KEYS:
            taken = s.market.stock[k] * share
            s.market.stock[k] -= taken
            loot += taken * s.market.bid(k)
        s.population *= 0.65 if keep else 0.75
        s.popularity = max(0.0, s.popularity - (35.0 if keep else 25.0))
        s.units = {}
        a.state = RETURNING
        self.march(a.uid, a.home)
        if not keep:
            return f"{s.name} is sacked -- {loot:,.0f}c of stores carried off"
        for b in list(s.buildings):
            if b.spec.terrain == "rampart":
                s.demolish(b.uid)
        s.wall_hp = 0.0
        return self.note(
            f"*** {s.name.upper()} IS STORMED. The keep is thrown down and "
            f"{loot:,.0f}c carried off. Raise another, or hold what is left "
            f"of the march from somewhere else. ***", MOMENTOUS)

    def _box_score(self, title: str, res, attacker: str, defender: str) -> str:
        """What a battle actually cost, both sides, in one line.

        The log said who held the ground and nothing else -- which is the
        result without the game. A box score is the least a competition owes
        anybody who was in it.
        """
        # Every battle in the game passes through here to be reported, which
        # makes it the one honest place to count them. Counting at each of the
        # four call sites is how a tally ends up missing the fifth.
        won = getattr(res, "winner", "")
        if attacker == PLAYER and won == "attacker":
            self._battles_won += 1
        elif defender == PLAYER and won == "defender":
            self._battles_won += 1
        lost = lambda d: sum(d.values())          # noqa: E731 - a local shorthand
        att = self.world.node_name(attacker) if attacker != PLAYER else "yours"
        deff = self.world.node_name(defender) if defender != PLAYER else "yours"
        return (f"    box  {title} · {res.rounds} rounds · "
                f"{att} lost {lost(res.attacker_losses):.0f}, "
                f"{deff} lost {lost(res.defender_losses):.0f}"
                + (f", wall {res.wall_damage:,.0f}" if res.wall_damage else ""))

    def _take_town(self, town, a: Army) -> str:
        was_mine = town.mine
        # Tallies for the feats. Kept here, at the moment a town changes
        # hands, because that is the only place that knows which way it went.
        if a.owner == "player":
            self._stormed += 1
        elif was_mine:
            self._towns_lost += 1
        # Whatever bones that lord had lifted are in his minster, and his
        # minster has just changed hands.
        taker = "player" if a.owner == "player" else a.owner
        for sh in self.world.shrines.values():
            if sh.holder == town.key:
                sh.holder = taker
        loser = town.key
        town.owner = "player" if a.owner == "player" else a.owner
        town.hostility = 0.0
        town.ambition = 0.0
        town.loyalty = 35.0
        # A lord with no hall has no host. Whatever of his is still in the
        # field goes over to whoever holds the hall now, or, if that is you,
        # goes home to farms that are not his any more.
        for x in list(self.armies):
            if x is a or x.owner != loser or x.errand:
                continue
            if a.owner == "player":
                self.armies.remove(x)
            else:
                x.owner = a.owner
                x.home = a.owner if a.owner in self.world.towns else x.home
        # A fifth of the host stays behind as a garrison. A town taken and then
        # walked away from is a town somebody else takes next month.
        town.garrison = {}
        for k, n in list(a.units.items()):
            if UNITS[k].unit_class in ("siege",):
                continue
            left = n * 0.3
            if left >= 1:
                a.units[k] = n - left
                town.garrison[k] = left
        town.wall_hp = town.wall_max * 0.45
        town.prosperity = max(0.5, town.prosperity - 0.25)
        a.state = GARRISON
        if a.owner == "player":
            # Aggressive expansion. The immediate shock is what it always was;
            # what is new is that the offence is written down with a date on
            # it, so it decays where a player can watch it decay -- and so
            # that it adds up across the march instead of only ever pointing
            # at you one lord at a time. Three towns is a different decision
            # from one, and this is the mechanism that says so.
            #
            # A town taken in a war the march accepted the reason for offends
            # less than one simply seized -- which is the second half of what
            # a marriage into that house is for, and the reason a claim is
            # worth a dowry years before anybody dies.
            just = self.day - self.court.justified.get(town.key, -99999)
            lawful = 0.6 if just < self.WAR_MEMORY else 1.0
            # And a town that revolted and was retaken is not a second
            # conquest. The march priced you as the man who took Caldmoor the
            # first time; charging it again every time the garrison wavered
            # ran one lord to two hundred of ill-will and a thousand days of
            # decay, which is not a decision, it is a spiral.
            again = town.key in self.court.taken
            self.court.taken.add(town.key)
            lawful *= 0.3 if again else 1.0
            for key, other in self.world.towns.items():
                if other.mine:
                    continue
                near = self.world.distance(key, town.key)
                # Distances on this march run 30 to 190. A neighbour takes
                # it hardest; a lord four days' ride away has heard about it
                # and has other things on his mind.
                close = max(0.55, min(1.4, 90.0 / max(30.0, near)))
                # And kin mind more than strangers: a town of their own
                # people taken is a thing done to them, EU4's culture rule.
                kin = 1.3 if other.culture and other.culture == town.culture else 0.9
                self.court.write(key, "took_town",
                                 -34.0 * lawful * close * kin
                                 * lordly.sort_of(key).temper,
                                 self.day)
            self.court.reckon(town.key, 40.0)
            return self.note(
                f"*** {town.name} bends the knee. Its tolls are yours, and "
                f"{town.tribute():.0f}c a day with them. ***", MOMENTOUS)
        liege = self.world.node_name(a.owner)
        a.state = RETURNING
        self.march(a.uid, a.home)
        if was_mine:
            return self.note(f"*** {town.name} IS TAKEN FROM YOU by {liege}. "
                             f"Its tribute is theirs now. ***", MOMENTOUS)
        return f"{town.name} has fallen to {liege}"
