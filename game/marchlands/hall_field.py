"""The field: hosts meeting in open country, raids on the fields, the
shrine race, and the orders a host is told to fight by.

Part of the wall (see hall_wall.py). `self` is the GameState, so
nothing here holds state of its own.
"""

from __future__ import annotations

from typing import Dict, List

from . import config as C
from .chronicle import MOMENTOUS, ROUTINE
from . import lords as lordly
from . import lord as manly
from .league import PLAYER
from .military import (open_battle, BESIEGING, GARRISON, RAIDING, RELIEVING,
                       RETURNING, describe, Army, Side, fight,
                       host_strength, raid_day)
from .settlement import Settlement
from .records import PendingBattle


class FieldMixin:
    """GameState's field. Mixed into WallMixin; see hall_wall.py."""

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
