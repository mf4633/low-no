"""The siege: a host at the gate, relief, storms, starving a town out,
sallies and fire, and what is left of a town that falls.

Part of the wall (see hall_wall.py). `self` is the GameState, so
nothing here holds state of its own.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, List, Optional

from . import config as C
from .chronicle import MOMENTOUS
from .castle import INVEST, Works, choose, storms_now
from .goods import ALL_KEYS, good
from . import lords as lordly
from . import lord as manly
from . import keep as keeps
from .league import PLAYER
from .military import (open_battle, BESIEGING, GARRISON, HOLD, MARCHING,
                       RAIDING, RELIEVING, RETURNING, STORM, describe, UNITS,
                       Army, Side, fight, host_strength, siege_day)
from .military import sortie_odds
from . import military
from . import supply
from .settlement import Settlement
from .records import PendingBattle


class SiegeMixin:
    """GameState's siege. Mixed into WallMixin; see hall_wall.py."""

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
