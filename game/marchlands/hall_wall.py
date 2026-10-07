"""The wall: hosts raised and fed, marches, sieges, storms, raids and the fight
the day stops for -- including the lord riding at their head.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.

The wall is four files by what a host is doing: hall_host (raised, fed,
marched), hall_field (open country and raids), hall_siege (at a gate) and
hall_ride (the battle the day stops for). This one keeps the day that drives
them all and the ground they all read.
"""

from __future__ import annotations

from typing import Dict, List

from .military import BESIEGING, MARCHING, RAIDING
from .military import Field, going_of, sky_on
from . import cartography as carto
from . import supply
from .hall_host import HostMixin
from .hall_field import FieldMixin
from .hall_siege import SiegeMixin
from .hall_ride import RideMixin


class WallMixin(HostMixin, FieldMixin, SiegeMixin, RideMixin):
    """GameState's wall. Mixed into GameState; see engine.py."""

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
