"""The host: raising men, the muster roll, splitting and joining hosts,
marching them, and what they eat on the road.

Part of the wall (see hall_wall.py). `self` is the GameState, so
nothing here holds state of its own.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import config as C
from .chronicle import NOTABLE, ROUTINE
from . import feats as feats_mod
from .goods import RATION_GOODS, good
from . import league as lg
from .league import PLAYER
from .military import (BESIEGING, GARRISON, MARCHING, RAIDING, describe,
                       Army, can_recruit, host_size, host_speed,
                       recruit_cost, unit)
from . import supply


class HostMixin:
    """GameState's host. Mixed into WallMixin; see hall_wall.py."""

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

    def muster_cap(self) -> float:
        """How many soldiers your holdings keep at the ordinary price."""
        return lg.cap_for(len(self.world.settlements) + len(self.world.vassals()))

    def muster_cost(self) -> float:
        """The multiplier on what your soldiers cost, for being too many."""
        return lg.overage(float(self.soldiers),
                          len(self.world.settlements) + len(self.world.vassals()))

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
