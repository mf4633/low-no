"""The court: the other lords' turn, the chancery's letters, alliances, pacts,
coalitions, truces and gifts, and the league table they are all kept on.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from . import config as C
from .chronicle import MOMENTOUS
from . import lords as lordly
from . import chancery as court
from . import league as lg
from .league import PLAYER
from .military import (BESIEGING, RAIDING, describe, UNITS, Army,
                       host_strength, host_upkeep)
from .records import _ordinal


class CourtMixin:
    """GameState's court. Mixed into GameState; see engine.py."""

    #: How long a march counts as the same war for the purpose of who takes
    #: offence at it. Sitting down, standing up and sitting down again is one
    #: quarrel, not three, and charging for it three times would make a long
    #: siege a diplomatic catastrophe by arithmetic rather than by judgement.
    WAR_MEMORY = 200

    def _declare(self, town) -> str:
        """Sitting down in front of a lord's walls, and who minds.

        The moment a war actually begins, which is not the order to march --
        a host can be turned round on the road and nobody on this march will
        have written a letter about it. What decides the cost is whether you
        had a reason anybody else accepts: with one, the rest of them shrug;
        without one, they all take note, and so does your own town, which has
        sons in the host and no idea what any of this is for.
        """
        key = town.key
        self._betray_friend(key)
        if self.day - self.court.declared.get(key, -9999) < self.WAR_MEMORY:
            return ""                        # the same quarrel, still running
        if town.truce_days > 0:
            # A treaty torn up. Whatever he thinks of you, he now knows what
            # your seal is worth, and so does everyone he writes to.
            self.court.shake(key, -30.0)
            for other in self.world.towns:
                if other != key and not self.world.towns[other].mine:
                    self.court.shake(other, -10.0)
        self.court.declared[key] = self.day
        ground = self.court.ground_for(key, self.day)
        if ground is not None:
            self.court.justified[key] = self.day
        # Everybody minds a siege. What a ground changes is how much.
        scale = 0.45 if ground else 1.0
        others = [k for k, t in self.world.towns.items()
                  if not t.mine and k != key]
        for other in others:
            near = self.world.distance(other, key)
            close = max(0.5, min(1.3, 90.0 / max(30.0, near)))
            there = self.world.towns[other]
            kin = 1.3 if there.culture and there.culture == town.culture else 0.9
            self.court.write(other, "besieged",
                             -12.0 * scale * close * kin
                             * lordly.sort_of(other).temper,
                             self.day)
        self.court.write(key, "besieged", -45.0, self.day)
        if ground:
            return (f"\n    You have grounds: {ground.label}. The march will "
                    f"not much mind.")
        # No reason anybody accepts. Everyone takes it harder, and so does
        # your own hall.
        self.court.write_all(others, "unjust",
                             -14.0 * self.war_pressure(), self.day)
        cost = court.unjust_cost(len(others))
        for s in self.world.settlements.values():
            s.popularity = max(0.0, s.popularity - cost)
        self.kin.did("merciful", -0.12)
        return (f"\n    You have no grounds anybody will accept. "
                f"{len(others)} lord(s) take note, and your own towns lose "
                f"{cost:.0f} of mood over a war they cannot name.")

    # ------------------------------------------------------------ the league
    def _league_day(self) -> List[str]:
        """The turn of the year, and the table kept up to date inside it."""
        msgs: List[str] = []
        season = self.league.season
        year = self.year
        if not season.opened or season.year != year:
            msgs += self._open_season(year)
            season = self.league.season
        self._keep_the_table()
        return msgs

    def _open_season(self, year: int) -> List[str]:
        """Close last year's book, publish this year's, and hold the draft.

        Everything a league does at the turn of a year happens here: the table
        is frozen and remembered, the lords say who they mean to move on, and
        the men looking for a lord are set out in reverse order of finish.
        """
        msgs: List[str] = []
        old = self.league.season
        if old.opened and old.records:
            table = old.table()
            first = table[0]
            self.league.past.append({
                "year": old.year, "first": first.name or first.key,
                "table": [r.to_dict() for r in table]})
            del self.league.past[:-24]
            mine = old.records.get(PLAYER)
            if mine is not None:
                where = old.place(PLAYER)
                msgs.append(self.note(
                    f"*** The {old.year} season closes. {first.name or first.key} "
                    f"stands first of the march; you stand {_ordinal(where)} of "
                    f"{len(table)} on {mine.line()}. ***", MOMENTOUS))
                if mine.won and self.league.mark("a season's fields won",
                                                 mine.won, "you", old.year):
                    msgs.append(self.note(f"{mine.won} fields in a year is the "
                                          f"most anybody has managed."))
            order = [r.key for r in reversed(table)]
        else:
            # No table to reverse in the first spring, so it is drawn for.
            # Handing the player first pick of the first class would be a
            # head start the whole device exists to prevent.
            order = [PLAYER] + list(self.world.towns)
            self.league.rng.shuffle(order)
        season = lg.Season(year=year, opened=True, order=order)
        # The schedule. A lord who has been quietly building ambition all
        # winter says so in the spring, and you get to hear it.
        for key, t in self.world.towns.items():
            if t.mine:
                continue
            target = self._intent_of(t)
            if target:
                season.fixtures.append(lg.Fixture(
                    who=key, target=target, declared=self.day,
                    reason=self._intent_reason(t, target)))
        season.prospects = lg.draft_class(self.league.rng, year)
        self.league.season = season
        self._keep_the_table()
        msgs.append(self.note(
            f"*** The {year} season opens. {len(season.fixtures)} lords have "
            f"said where they are going, and {len(season.prospects)} men are "
            f"looking for one. `season` · `draft` ***", MOMENTOUS))
        msgs += self._run_draft()
        return msgs

    def _intent_of(self, town) -> str:
        """Who a lord means to move on, given what he wants and who is near.

        The same reading the war engine makes when the hostility finally tips;
        making it early and saying it out loud is the whole schedule.
        """
        if town.truce_days > 0:
            return ""
        mine = self._nearest_of_mine(town.key)
        # Only a lord who has actually taken against you says he is coming for
        # you. Reading a flat nought as "hostility is at least ambition" put
        # every lord on the march down as marching on your gate in the first
        # spring, which is a schedule that tells you nothing.
        if mine and town.hostility >= max(35.0, town.ambition):
            return mine
        near = [k for k in self.world.towns
                if k != town.key and not self.world.towns[k].mine]
        if not near:
            return mine or ""
        near.sort(key=lambda k: self.world.distance(town.key, k))
        return near[0]

    def _intent_reason(self, town, target: str) -> str:
        """Why he says he is going, in the words he would use."""
        if target in self.world.settlements:
            worst = [(label, v) for label, v, _d in self.court.reasons(town.key, self.day)
                     if v < 0]
            if worst:
                return worst[0][0]
            return "your wealth, and his temper"
        other = self.world.towns.get(target)
        if other is not None and other.owner == PLAYER:
            return "it is sworn to you, and thinly held"
        if (self.court.claim_live(town.key, self.day)
                or self.court.claim_live(target, self.day)):
            return "an old claim"
        return "it is the nearest he can take"

    def _keep_the_table(self) -> None:
        """The standings, recomputed from what is actually true today."""
        season = self.league.season
        vassals = set(self.world.vassals())
        mine = season.record(PLAYER)
        mine.name, mine.lord = "you", self.lord.name
        mine.towns = len(self.world.settlements) + len(vassals)
        mine.worth = self.net_worth()
        mine.muster = float(self.soldiers)
        for key, t in self.world.towns.items():
            r = season.record(key)
            r.name, r.lord = t.name, t.lord
            if t.mine:
                r.towns = 0
                continue
            r.towns = 1 + sum(1 for o in self.world.towns.values()
                              if o.owner == key)
            r.worth = 1000.0 * t.prosperity * t.wealth
            r.muster = t.muster * 60.0

    # ------------------------------------------------------------- the draft
    def _run_draft(self) -> List[str]:
        """Reverse order of finish, and everybody ahead of you picks at once.

        The player's turn stops the clock; everyone else takes the best man
        left the moment it reaches them. Finishing last is worth something,
        which is the entire point and the reason a league has one.
        """
        msgs: List[str] = []
        season = self.league.season
        while season.picking < len(season.order):
            who = season.order[season.picking]
            if who == PLAYER:
                left = season.undrafted()
                if left:
                    msgs.append(f"You are on the clock: {len(left)} men to "
                                f"choose from. `draft` shows them, "
                                f"`draft <name>` takes one.")
                    return msgs
                season.picking += 1
                continue
            left = season.undrafted()
            if not left:
                break
            best = max(left, key=lambda p: p.grade)
            best.taken_by = who
            name = self.world.node_name(who)
            msgs.append(f"{name} takes {best.name} ({best.skill} {best.grade}).")
            season.picking += 1
        return msgs

    def draft(self, name: str = "") -> str:
        """Take one of the men looking for a lord, if it is your turn."""
        season = self.league.season
        if not season.prospects:
            return "nobody is looking for a lord this year"
        if season.on_the_clock() != PLAYER:
            who = season.on_the_clock()
            if not who:
                return "the draft is done for this year"
            return (f"{self.world.node_name(who)} is on the clock, not you")
        left = season.undrafted()
        if not left:
            return "there is nobody left to take"
        if not name:
            return f"{len(left)} to choose from -- `draft <name>` takes one"
        want = name.strip().lower()
        pick = next((p for p in left if p.name.lower().startswith(want)), None)
        if pick is None:
            pick = next((p for p in left if want in p.name.lower()), None)
        if pick is None:
            return f"nobody called {name!r} among them"
        pick.taken_by = PLAYER
        season.picking += 1
        person = self.kin.add(pick.name, "f" if pick.name.split()[0][-1] in "aey"
                              else "m", born=self.day - 26 * C.DAYS_PER_YEAR)
        person.sworn = True
        person.xp[pick.skill] = lg.STEEP_FOR[pick.grade]
        said = self.note(f"{pick.name} is sworn to you -- {pick.story}, and it "
                         f"shows: {pick.skill} {pick.grade}. `post` gives him "
                         f"something to do.")
        rest = self._run_draft()
        return "\n".join([said] + rest)

    def _lords_and_hosts(self) -> List[str]:
        """The other lords take their turn.

        They grow their towns, they take offence at you at their own rates, and
        -- the part that makes the map a board rather than a backdrop -- they
        take offence at each other. A town that swallows its neighbours becomes
        a problem you did not create and will have to solve.
        """
        msgs: List[str] = []
        if not self.world.settlements:
            return msgs
        msgs += self._chancery_day()
        pressure = self.war_pressure()
        wealth_factor = min(2.5, self.net_worth() / 40000.0)
        besieged = {a.at for a in self.armies if a.state == BESIEGING}
        rival_wars = sum(1 for a in self.armies
                         if a.owner != "player" and a.bound_for in self.world.towns)

        for key, t in self.world.towns.items():
            t.grow(self.rng, besieged=key in besieged, day=self.day)
            if t.truce_days > 0:
                t.truce_days -= 1
            if t.mine:
                said = self._loyalty_day(key, t)
                if said:
                    msgs.append(said)
                revolt = self._revolt(key, t)
                if revolt:
                    msgs.append(revolt)
                continue
            self._keep_the_chest(key, t)
            if any(a.owner == key and not a.errand for a in self.armies):
                continue      # its host is already out
            # A party of spearmen away at a shrine is not "his host": counting
            # it as one made relic-hunting a pressure valve on the whole war,
            # so tuning how often the lords went for bones quietly retuned how
            # often they declared on anybody.

            if key in self.court.allies:
                continue      # a man does not march on somebody he has sworn to
            # -- offence taken at you ---------------------------------------
            if t.truce_days <= 0:
                t.hostility += (C.HOSTILITY_DRIFT * pressure * t.temper
                                * (0.5 + wealth_factor)
                                * (0.6 + 0.8 * self._week_mood(key, "temper")))
                t.hostility = max(0.0, t.hostility - t.favour * 0.02
                                  - self.kin.bonus("cooling"))
            if t.hostility >= C.HOSTILITY_WAR:
                said = self._reckon_war(key, t, pressure)
                if said:
                    msgs.append(said)
                continue

            # -- offence taken at each other --------------------------------
            t.ambition += (C.AMBITION_DRIFT * t.aggression * pressure
                           * (0.5 + self._week_mood(key, "ambition")))
            if t.ambition < C.HOSTILITY_WAR or rival_wars >= self.MAX_RIVAL_WARS:
                continue
            # Patience, Warband's way: a lord who has gathered his men and
            # found nobody weak enough settles for a little less each time,
            # rather than stand his host down and start the year again.
            prey = self._prey_for(key, 0.8 + 0.05 * min(6, t.waited))
            if prey is None:
                t.ambition = 60.0
                t.waited += 1
                continue
            t.waited = 0
            t.ambition = 0.0
            rival_wars += 1
            msgs.append(self._send_host(t, pressure, prey))
        return msgs

    # -------------------------------------------------------- the chancery
    #: How long an ally is given to answer a call before it counts as a no.
    CALL_DAYS = 12
    #: Chance a day that a foreign lord's line runs out. Over three years it
    #: is a thing that happens to about one house on the march.
    SUCCESSION_ODDS = 0.00035

    def _chancery_day(self) -> List[str]:
        """The letters. Who is talking to whom, and what they have agreed.

        Four things, in the order a chancellor would take them: the book is
        swept of what has worn out, the standing goodwill is re-read off it,
        the names on the letter are counted, and anybody waiting on an answer
        is told that no answer is an answer.
        """
        msgs: List[str] = []
        day = self.day
        c = self.court
        if day % 7 == 0:
            c.sweep(day)
        # Heralds: men whose whole trade is knowing who is angry with whom.
        # A grievance you can *name* is one you can still act on, so your own
        # grounds for war keep while theirs wear off at the usual rate.
        c.long_memory = self.progress.knows("heralds")
        # `favour` is not a number anybody sets any more. It is the sum of
        # what is in your favour, which is the only way a gift can be
        # forgotten -- and `wed` has claimed for a year that gifts are
        # forgotten while `favour` only ever went up.
        for key, t in self.world.towns.items():
            t.favour = c.goodwill(key, day)
            # And what his customs post charges, which is where the politics
            # stops being a screen and starts being money. See
            # World.toll_mood.
            t.regard = c.opinion(key, day)
            t.signed = key in c.coalition
            t.sworn_friend = key in c.allies
        # What the chancery's institutions actually do, applied once a day
        # where everything else about the march is. Each of these is a
        # mechanic rather than a percentage -- see tech.py on why that is the
        # difference between a tree that describes your town and one that
        # decides what you may do in it.
        self.world.safe_conduct = self.progress.knows("safe_conduct")
        msgs += self._drainage_day()
        msgs += self._coalition_day()
        msgs += self._peace_day()
        msgs += self._alliance_day()
        msgs += self._succession_abroad()
        return msgs

    def _coalition_day(self) -> List[str]:
        """When the lords stop quarrelling with each other and start writing.

        The signature of the thing this is borrowed from: conquest that is
        cheap once, dear twice and ruinous three times, not because any lord
        got stronger but because they started counting together. It is the
        game saying, in a way you can read in advance, that the third town is
        a different kind of decision from the first.
        """
        msgs: List[str] = []
        c, day = self.court, self.day
        theirs = [k for k, t in self.world.towns.items() if not t.mine]
        names = [k for k in c.signatories(theirs, day) if k not in c.allies]
        # Names come off as well as on. Without this a lord whose grievance
        # you had spent a year and a treasury cooling stayed on the letter
        # for as long as any three others were angry -- which made buying one
        # lord off pointless, and pointless is the one thing a lever must
        # never be.
        if c.coalition:
            still = [k for k in c.still_signed(day)
                     if k not in c.allies and not self.world.towns[k].mine]
            left = [k for k in c.coalition if k not in still]
            if len(still) < court.COALITION_NAMES:
                c.coalition = []
                c.coalition_day = -1
                msgs.append(self.note(
                    "The letter against you is not renewed. The march goes "
                    "back to quarrelling with itself.", MOMENTOUS))
            elif left:
                c.coalition = still
                msgs.append(self.note(
                    ", ".join(self.world.node_name(k) for k in left)
                    + " takes a name off the letter against you."))
        if len(names) >= court.COALITION_NAMES:
            new = [k for k in names if k not in c.coalition]
            if not c.coalition:
                c.coalition = names
                c.coalition_day = day
                msgs.append(self.note(
                    "*** The lords of the march have put their names to one "
                    "letter: " + ", ".join(self.world.node_name(k) for k in names)
                    + ". They will not treat with you one at a time while it "
                    "holds. ***", MOMENTOUS))
            elif new:
                c.coalition = sorted(set(c.coalition) | set(new))
                msgs.append(self.note(
                    ", ".join(self.world.node_name(k) for k in new)
                    + " adds a name to the letter against you.", MOMENTOUS))
        # A coalition marches together. When one of them is on the road for
        # you, the rest find their boots within the fortnight -- which is the
        # whole difference between eight quarrels and one war.
        if c.coalition and any(a.owner in c.coalition
                               and a.bound_for in self.world.settlements
                               for a in self.armies):
            for key in c.coalition:
                t = self.world.towns.get(key)
                if t is None or t.mine or t.truce_days > 0:
                    continue
                if any(a.owner == key and not a.errand for a in self.armies):
                    continue
                if c.rng.random() < 0.085:
                    msgs.append(self._send_host(t, self.war_pressure(),
                                                self._nearest_of_mine(key)))
        return msgs

    def _alliance_day(self) -> List[str]:
        """Friends, and the day you did not come.

        An ally who comes when you are attacked is an ally who calls when he
        is. Refusing is allowed and is meant to be: what it costs is that
        every other lord on the march now knows what your word is worth,
        which is a grudge that decays slower than anything else in the book.
        """
        msgs: List[str] = []
        c, day = self.court, self.day
        for key in list(c.allies):
            t = self.world.towns.get(key)
            if t is None or t.mine:
                c.allies.remove(key)
                continue
            if c.settled_view(key, day) <= 0 or c.trust_of(key) < c.TRUST_LAPSE:
                c.allies.remove(key)
                c.write(key, "ally", -10.0, day)
                why = ("does not trust your word"
                       if c.trust_of(key) < c.TRUST_LAPSE else "has cooled")
                msgs.append(self.note(f"{t.lord} of {t.name} {why} and lets "
                                      f"the alliance lapse."))
        msgs += self._aid_day()
        # Somebody marching on an ally is a call, and a call wants an answer.
        if c.called is None:
            for a in self.armies:
                if a.owner == "player" or a.bound_for not in c.allies:
                    continue
                who = a.bound_for
                c.called = (who, day)
                msgs.append(self.note(
                    f"*** {self.world.node_name(who)} calls you to the war. "
                    f"`call yes` sends what you have; `call no` does not, and "
                    f"the march will hear which. You have {self.CALL_DAYS} "
                    f"days. ***", MOMENTOUS))
                break
        elif day - c.called[1] > self.CALL_DAYS:
            # Saying nothing is saying no, and it has to go through the same
            # door as saying it: clearing `called` first and *then* asking
            # answer_call to act on it meant the clock ran out and absolutely
            # nothing happened -- no broken alliance, no grudge, no line in
            # the chronicle. A silence with no consequence is not a decision
            # the player was ever offered.
            msgs.append(self.answer_call(False))
        return msgs

    #: How long a lord's suit for peace stands, and how long an ally waits
    #: before sending men again.
    SUIT_DAYS = 20
    AID_EVERY = 120

    def _aid_day(self) -> List[str]:
        """Allies come when you are attacked -- which the alliance always
        promised and nothing did. A host of theirs marching on or sitting
        before a town of yours is the call; each ally answers it one day in
        twelve or so, and sends men under your command, marching from his
        gate to yours. You feed them: that is what an alliance costs."""
        msgs: List[str] = []
        c = self.court
        pressed = {a.bound_for or a.at for a in self.armies
                   if a.owner in self.world.towns
                   and (a.bound_for in self.world.settlements
                        or (a.at in self.world.settlements
                            and a.state in (BESIEGING, RAIDING)))}
        pressed.discard("")
        if not pressed:
            return msgs
        for key in list(c.allies):
            t = self.world.towns.get(key)
            if t is None or self.day - c.aided.get(key, -9999) < self.AID_EVERY:
                continue
            dice = random.Random(f"{self.seed}:aid:{key}:{self.day}")
            if dice.random() > 0.08:
                continue
            target = min(pressed, key=lambda k: self.world.distance(key, k))
            units = {k: v * 0.5 for k, v in
                     self._muster_enemy(t, self.war_pressure(), spread=False).items()
                     if UNITS.get(k) is None or UNITS[k].unit_class != "siege"}
            units = {k: v for k, v in units.items() if v >= 1}
            if not units:
                continue
            a = Army(uid=self.next_army_uid, name=f"{t.lord}'s men", owner=PLAYER,
                     units=units, at=key, home=target)
            self.next_army_uid += 1
            self.armies.append(a)
            self._set_march(a, key, target, units)
            c.aided[key] = self.day
            c.shake(key, 5.0)
            msgs.append(self.note(
                f"*** {t.lord} of {t.name} keeps his word: {describe(a.units)} "
                f"march for {self.world.node_name(target)} under your banner. ***",
                MOMENTOUS))
        return msgs

    def _peace_day(self) -> List[str]:
        """A lord losing his war with you says so, and asks for peace.

        EU4's war score, as small as it can be made: when the reckoning
        with one lord stands at +50 or better and none of his men is on
        the road to you, he sues -- and a truce with him is free for the
        next SUIT_DAYS days."""
        msgs: List[str] = []
        c = self.court
        c.settle_day()
        c.settle_opinions(sorted(self.world.towns), self.day)
        msgs += self._pact_day()
        for key, when in list(c.friends.items()):
            t = self.world.towns.get(key)
            if t is None or t.mine or self.day - when > self.FRIEND_DAYS:
                del c.friends[key]
                if t is not None and not t.mine:
                    msgs.append(f"{t.lord} of {t.name}: the declaration of "
                                f"friendship has run its year. `befriend` to "
                                f"renew it.")
        for key, v in list(c.score.items()):
            t = self.world.towns.get(key)
            if t is None or t.mine or v < self.sues_at(key) or t.truce_days > 0:
                continue
            if self.day - c.sued.get(key, -9999) < 90:
                continue
            if any(a.owner == key and a.bound_for in self.world.settlements
                   for a in self.armies):
                continue
            c.sued[key] = self.day
            msgs.append(self.note(
                f"*** {t.lord} of {t.name} sues for peace. `truce {t.name.lower()}` "
                f"costs nothing for {self.SUIT_DAYS} days. ***", MOMENTOUS))
        return msgs

    #: Pacts between lords: looked at monthly, lasting two years.
    PACT_EVERY = 30
    PACT_YEARS = 2
    PACT_FEAR = 0.45             # a lord this far under the strongest looks for one
    PACT_WEIGHT = 0.25           # how much of a partner's garrison deters
    FRIEND_DAYS = 360
    FRIEND_VIEW = 15.0
    FRIEND_TRUST = 40.0

    def _lord_strength(self, key: str) -> float:
        t = self.world.towns[key]
        return host_strength(t.garrison) + host_strength(
            self._muster_enemy(t, 1.0, spread=False))

    def _pact_day(self) -> List[str]:
        """Two lords who both fear the strongest swear to defend each other.

        Once a month each lord without a pact looks at the strongest lord on
        the march; if he is well under him, he looks for the nearest other
        lord who is too, and who is not at war with him, and they swear. A
        pact ends after two years, or when either house is taken or sworn
        to you.
        """
        msgs: List[str] = []
        c = self.court
        towns = self.world.towns
        for p, when in list(c.pacts.items()):
            a, b = p.split("|")
            ta, tb = towns.get(a), towns.get(b)
            if (ta is None or tb is None or ta.mine or tb.mine
                    or ta.owner == b or tb.owner == a
                    or self.day - when > self.PACT_YEARS * C.DAYS_PER_YEAR):
                del c.pacts[p]
        if self.day % self.PACT_EVERY:
            return msgs
        lords = sorted(k for k, t in towns.items() if not t.mine and not t.owner)
        if len(lords) < 3:
            return msgs
        power = {k: self._lord_strength(k) for k in lords}
        top = max(lords, key=lambda k: (power[k], k))
        for k in lords:
            if k == top or c.partners(k) or power[k] >= self.PACT_FEAR * power[top]:
                continue
            fighting = {x.bound_for for x in self.armies if x.owner == k} | {
                x.owner for x in self.armies if x.bound_for == k or x.at == k}
            others = sorted(
                (o for o in lords if o not in (k, top) and not c.partners(o)
                 and power[o] < self.PACT_FEAR * power[top] and o not in fighting
                 and o in self.world.coords and k in self.world.coords),
                key=lambda o: (self.world.distance(k, o), o))
            if not others:
                continue
            dice = random.Random(f"{self.seed}:pact:{self.day}:{k}")
            if dice.random() > 0.3:
                continue
            o = others[0]
            c.pacts[c.pair(k, o)] = self.day
            if towns[k].seen_day >= 0 or towns[o].seen_day >= 0:
                msgs.append(f"{towns[k].lord} of {towns[k].name} and "
                            f"{towns[o].lord} of {towns[o].name} swear to "
                            f"defend each other against {towns[top].name}")
        return msgs

    def befriend(self, town_key: str) -> str:
        """Declare friendship: less than an alliance, and cheaper to keep."""
        t = self.world.towns.get(town_key)
        if t is None:
            return f"there is no {town_key!r} to treat with"
        if t.mine:
            return f"{t.name} is sworn to you already"
        c = self.court
        if town_key in c.coalition:
            return f"{t.lord} has put his name to the letter against you"
        view, trust = c.settled_view(town_key, self.day), c.trust_of(town_key)
        if view < self.FRIEND_VIEW or trust < self.FRIEND_TRUST:
            return (f"{t.lord} of {t.name} will not call you a friend: he thinks "
                    f"{view:+.0f} of you and trusts your word {trust:.0f}; it "
                    f"wants {self.FRIEND_VIEW:+.0f} and {self.FRIEND_TRUST:.0f}")
        c.friends[town_key] = self.day
        c.shake(town_key, 5.0)
        return self.note(f"{t.lord} of {t.name} declares friendship with you for "
                         f"a year. He will not march on you while it holds; "
                         f"marching on him ends it, and the march hears.",
                         MOMENTOUS)

    def _betray_friend(self, key: str) -> None:
        c = self.court
        if key not in c.friends:
            return
        del c.friends[key]
        c.shake(key, -40.0)
        c.write(key, "broke_word", -30.0, self.day)
        for other, t in self.world.towns.items():
            if other != key and not t.mine:
                c.shake(other, -15.0)

    def sues_at(self, key: str) -> float:
        """The war score at which a lord asks for peace: +50, less a point
        for every eight days the war has run, down to +25."""
        return 50.0 - min(25.0, self.court.war_days.get(key, 0) / 8.0)

    def about_to_take(self, key: str) -> str:
        """A settlement of yours this lord's lines are about to carry, if
        any. Unciv's AI will not make peace the week it is going to take a
        city, and neither will he."""
        for a in self.armies:
            if a.owner != key or a.state != BESIEGING:
                continue
            s = self.world.settlements.get(a.at)
            if s is None:
                continue
            full = s.wall_max(self.progress)
            if (full > 0 and s.wall_hp < 0.25 * full) or sum(s.units.values()) < 5:
                return s.name
        return ""

    def answer_call(self, come: bool) -> str:
        """Yes or no to an ally who has called. No is a real option."""
        c = self.court
        who = c.called[0] if c.called else None
        if who is None:
            return "nobody has called you"
        c.called = None
        t = self.world.towns.get(who)
        name = self.world.node_name(who)
        if come:
            c.write(who, "came_when_called", 45.0, self.day)
            c.shake(who, 10.0)
            c.refused.pop(who, None)
            # Whoever is marching on them has now given you a reason to
            # march on him, which is the other half of what an ally is for.
            for a in self.armies:
                if a.bound_for == who and a.owner in self.world.towns:
                    c.give_ground(a.owner, "called", self.day)
            if t is not None:
                t.truce_days = max(t.truce_days, 120)
            return self.note(f"You answer {name}'s call. Whoever is at their "
                             f"gate is now your business too.", MOMENTOUS)
        # Freeciv's ally asks three times. The first no is a disappointment
        # and the second a warning; the third ends it, and everybody hears.
        c.refused[who] = c.refused.get(who, 0) + 1
        if who in c.allies and c.refused[who] < self.ALLY_PATIENCE:
            c.write(who, "broke_word", -20.0 * c.refused[who], self.day)
            c.shake(who, -10.0 * c.refused[who])
            left = self.ALLY_PATIENCE - c.refused[who]
            return self.note(
                f"You do not come when {name} calls. They write that they "
                f"are disappointed" + (" -- and that they will not ask many "
                f"more times" if left == 1 else "") + ".", MOMENTOUS)
        c.refused.pop(who, None)
        if who in c.allies:
            c.allies.remove(who)
        c.write(who, "broke_word", -60.0, self.day)
        c.shake(who, -20.0)
        others = [k for k, x in self.world.towns.items() if not x.mine and k != who]
        c.write_all(others, "broke_word", -22.0, self.day)
        self.kin.did("open", -0.2)
        return self.note(f"You do not come when {name} calls. The alliance "
                         f"ends, and every lord on the march is told.",
                         MOMENTOUS)

    ALLY_PATIENCE = 3            # calls let go by before the alliance ends

    def ally(self, town_key: str) -> str:
        """Swear to come when they are attacked, and they to you."""
        t = self.world.towns.get(town_key)
        if t is None:
            return f"there is no {town_key!r} to treat with"
        if not t.mine and self.court.trust_of(town_key) < self.court.TRUST_FLOOR_ALLY:
            return (f"{t.lord} likes you well enough, perhaps, but does not "
                    f"trust your word ({self.court.trust_of(town_key):.0f} of "
                    f"{self.court.TRUST_FLOOR_ALLY:.0f} needed). Keep it a while.")
        if t.mine:
            return f"{t.name} is sworn to you already"
        shut = self.opened("ally")
        if shut:
            return shut
        c = self.court
        if town_key in c.allies:
            return f"you are allied with {t.name} already"
        view = c.settled_view(town_key, self.day)
        if view < court.WARM:
            return (f"{t.lord} of {t.name} thinks of you as "
                    f"{court.temper(view)} ({view:+.0f}); he will not swear to "
                    f"anybody under {court.WARM:+.0f}. `court {town_key}` says "
                    f"what would move him.")
        c.allies.append(town_key)
        c.write(town_key, "ally", 30.0, self.day)
        t.truce_days = max(t.truce_days, 180)
        self.kin.teach("charm", 14.0, self.day, post="envoy")
        return self.note(f"{t.lord} of {t.name} is allied to you. He comes "
                         f"when you are attacked, and calls when he is.",
                         MOMENTOUS)

    def _succession_abroad(self) -> List[str]:
        """A house ends, and what it held has to go somewhere.

        The other reason to marry a daughter into Ostmark. It is rare and it
        is meant to be -- but it is the one way a town comes to you with
        nobody in the field, and it is the only thing in the game that makes
        a dowry look cheap in hindsight.
        """
        c = self.court
        for key, t in self.world.towns.items():
            if t.mine or c.rng.random() >= self.SUCCESSION_ODDS:
                continue
            if key not in c.claims:
                # Somebody else's cousin takes it. You hear about it and it
                # changes nothing, which is what most history is.
                t.prosperity = max(0.5, t.prosperity - 0.1)
                return [self.note(f"{t.lord} of {t.name} is dead. A cousin "
                                  f"takes the hall, and the market with it.")]
            t.owner = "player"
            t.hostility = 0.0
            t.ambition = 0.0
            c.claims.pop(key, None)
            others = [k for k, x in self.world.towns.items()
                      if not x.mine and k != key]
            c.write_all(others, "inherited", -16.0, self.day)
            return [self.note(
                f"*** {t.lord} of {t.name} is dead without an heir of his "
                f"body, and your house has the claim. {t.name} comes to you "
                f"with nobody in the field. ***", MOMENTOUS)]
        return []

    def _loyalty_day(self, key: str, town) -> str:
        """A sworn town's loyalty, a day at a time -- EU4's liberty desire
        turned the right way up. It settles toward 70 under a lord who is
        strong and near; it slides while there is a letter against you on
        the march (somebody is courting it) and while you are too weak to
        hold it. Under 50 it wavers and says so; at 0 it goes."""
        before = town.loyalty
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self._muster_enemy(town, self.war_pressure(),
                                                  spread=False))
        drift = 0.08 * (70.0 - town.loyalty) / 70.0
        if self.court.coalition:
            drift -= 0.12
        if mine < 0.45 * theirs:
            drift -= 0.2
        town.loyalty = max(0.0, min(100.0, town.loyalty + drift))
        if before >= 50.0 > town.loyalty:
            return self.note(f"{town.name} wavers in its oath ({town.loyalty:.0f} "
                             f"of 100) -- there are letters on the march, and "
                             f"your hand is not heavy enough.")
        return ""

    def _revolt(self, key: str, town) -> str:
        """A town holds its oath while the hand that took it is still visible.

        Conquest is not a purchase: a lord who takes five towns and then lets
        his host melt away will watch them leave one at a time.
        """
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self._muster_enemy(town, self.war_pressure(),
                                                  spread=False))
        if town.loyalty > 0.0:
            if mine >= 0.45 * theirs:
                return ""
            # A loyal town rides out a thin year; a wavering one does not.
            odds = C.REVOLT_CHANCE * max(0.0, 1.5 - town.loyalty / 50.0)
            if self.rng.random() > odds:
                return ""
        town.owner = ""
        town.hostility = 65.0
        town.garrison = dict(town.target_garrison())
        return self.note(f"*** {town.name} throws off its oath -- you have "
                         f"nothing left nearby to hold it with. ***", MOMENTOUS)

    def _nearest_of_mine(self, key: str) -> str:
        return min(self.world.settlements,
                   key=lambda k: self.world.distance(key, k))

    def _host_price(self, host: Dict[str, float]) -> float:
        return sum(UNITS[k].coin * n for k, n in host.items() if k in UNITS)

    FEUDAL_SERVICE = 40          # days a host serves before it is paid

    def _keep_the_chest(self, key: str, t) -> None:
        """A lord's day of accounts. Warband gives its lords a week's income
        less wages and lets a host in debt melt away; this is the same, a
        day at a time. In debt his garrison drifts off a hundredth a day and
        his men in the field faster.

        A levy owes its lord forty days in the field at its own cost -- the
        old feudal service -- and only after that does he pay wages; a host
        sitting down before a wall lives half off the country round it; and a
        lord runs a few days behind on wages before anyone walks off. Without
        these, a siege that had its ram at the gate melted in the lines before
        it was ever ready to go in: a whole host costs six times what a
        lord's country pays him a day."""
        if t.chest < 0 and t.chest == -1.0:
            t.chest = self._host_price(self._muster_enemy(t, 1.0, spread=False)) + 200.0
        field = [a for a in self.armies if a.owner == key]
        income = self._income_of(t)
        wages = 0.0
        for a in field:
            a.served += 1
            if a.served > self.FEUDAL_SERVICE:
                wages += host_upkeep(a.units) * (0.5 if a.state == BESIEGING else 1.0)
        t.chest += income - host_upkeep(t.garrison) - wages
        # And no deeper than three hosts' worth: what a lord cannot spend on
        # soldiers goes on the things lords spend money on, and a chest that
        # grew for ever would be a chest that never said no.
        cap = 3.0 * self._host_price(self._muster_enemy(t, self.war_pressure(),
                                                        spread=False))
        t.chest = min(t.chest, max(cap, 600.0))
        if t.chest < -3.0 * income:
            t.garrison = {k: v * 0.99 for k, v in t.garrison.items() if v * 0.99 >= 0.5}
            for a in field:
                a.units = {k: v * 0.985 for k, v in a.units.items() if v * 0.985 >= 0.5}
            t.chest = max(t.chest, -3000.0)

    # ------------------------------------------------- a war on you, weighed
    #: Unciv's two lines: at PREPARE he is gathering and says so; at DECLARE
    #: he marches. Below both his temper is up and he holds back.
    PREPARE = 15.0
    DECLARE = 20.0

    def _war_terms(self, t, target: str, pressure: float) -> List[Tuple[str, float]]:
        """Why a lord would or would not march on you, as a list of named
        reasons with a weight each -- Unciv's motivation-to-attack, Warband's
        assailability, Freeciv's want against fear. Named, because a lord
        who can say why is a lord a player can answer."""
        key = t.key
        c = self.court
        terms: List[Tuple[str, float]] = [("his temper is up", 12.0)]
        # His habit reads you as it reads anybody: a lord who goes for the
        # nearest goes for you when you are the nearest, and one who goes for
        # the weakest when your wall is the thinnest on the march.
        hunts = lordly.sort_of(key).hunts
        if hunts == "you":
            terms.append(("he has his eye on you", 4.0))
        elif hunts == "closest" and target in self.world.coords:
            mine = self.world.distance(key, target)
            if all(self.world.distance(key, k) >= mine for k in self.world.towns
                   if k != key and self.world.towns[k].owner != key
                   and k in self.world.coords):
                terms.append(("you are the nearest thing to him", 5.0))
        elif hunts == "gold":
            # And the richer you get, the more of a mark you are to him.
            rich = min(1.0, self.real_worth() / max(1.0, self.goals.net_worth))
            if rich > 0.25:
                terms.append(("you are worth robbing", round(10.0 * rich, 1)))
        host = self._muster_enemy(t, pressure, spread=False)
        price = self._host_price(host)
        if t.chest < price:
            share = max(0.0, t.chest) / max(price, 1.0)
            terms.append(("his chest will not pay for it", -12.0 * (1.0 - share)))
            host = {k: v * max(0.35, share) for k, v in host.items()}
        s = self.world.settlements.get(target)
        yours = 0.0
        if s is not None:
            yours = host_strength(s.units) + s.wall_hp / 12.0
        yours += sum(host_strength(a.units) for a in self.armies
                     if a.owner == PLAYER and a.at == target)
        ratio = host_strength(host) / max(1.0, yours)
        band = (20.0 if ratio >= 3 else 14.0 if ratio >= 2 else 8.0 if ratio >= 1.5
                else 3.0 if ratio >= 1 else -6.0 if ratio >= 0.7
                else -15.0 if ratio >= 0.5 else -30.0)
        terms.append((f"his host against your wall, {ratio:.1f} to 1", band))
        far = self.world.distance(key, target) if target in self.world.coords else 0.0
        if far:
            terms.append(("the distance", -min(10.0, far / 12.0)))
        beset = sum(1 for a in self.armies if a.bound_for == key and a.owner != key)
        if beset:
            terms.append(("somebody is marching on him", -10.0 * beset))
        if c.allies:
            terms.append(("your allies would come", -4.0 * len(c.allies)))
        if key in c.friends:
            terms.append(("he has declared friendship with you", -12.0))
        # What has settled in him, not what he said this morning.
        view = c.settled_view(key, self.day)
        if view <= -40:
            terms.append(("he hates you", 8.0))
        elif view <= -15:
            terms.append(("he dislikes you", 4.0))
        elif view >= 40:
            terms.append(("he thinks well of you", -8.0))
        elif view >= 15:
            terms.append(("he likes you", -4.0))
        off = c.offence(key, self.day)
        if off:
            terms.append(("what you have done on this march", min(10.0, off / 6.0)))
        if key in c.coalition:
            terms.append(("his name is on the letter", 8.0))
        war = c.score.get(key, 0.0)
        if war:
            terms.append(("how the war has gone", max(-10.0, min(10.0, -war / 10.0))))
        nature = (t.aggression - 1.0) * 10.0
        if abs(nature) >= 0.5:
            terms.append(("his nature", nature))
        if t.gathering:
            terms.append(("he has waited", min(15.0, t.gathering / 4.0)))
        return terms

    def _reckon_war(self, key: str, t, pressure: float) -> str:
        """His temper is up. Does he march?"""
        target = self._nearest_of_mine(key)
        terms = self._war_terms(t, target, pressure)
        total = sum(v for _l, v in terms)
        t.reckoning = [[label, round(v, 1)] for label, v in terms]
        t.reckoned = round(total, 1)
        t.hostility = min(t.hostility, C.HOSTILITY_WAR)
        if total >= self.DECLARE:
            t.gathering = 0
            return self._send_host(t, pressure, target)
        t.gathering += 1
        worst = min(terms, key=lambda r: r[1])
        who = t.lord if " of " in t.lord else f"{t.lord} of {t.name}"
        if total >= self.PREPARE:
            if t.gathering == 1:
                return self.note(
                    f"{who} is gathering men against you "
                    f"({total:.0f}; he marches at {self.DECLARE:.0f}). "
                    f"`court {key}` for his reasons.", MOMENTOUS)
            return ""
        if t.gathering == 1 or t.gathering % 60 == 0:
            return self.note(f"{who} is angry enough to march, and holds "
                             f"back -- {worst[0]}.")
        return ""

    def _week_mood(self, key: str, what: str) -> float:
        """A lord's humour for the week, 0 to 1. Rerolled every seven days
        rather than every morning -- Warband rerolls its lords' dice weekly
        so a man is steadily hot or steadily cool for a while, instead of
        jittering between the two, and so this does not draw on the world's
        dice either."""
        return random.Random(f"{self.seed}:{what}:{key}:{self.day // 7}").random()

    def _prey_for(self, key: str, reach: float = 0.8) -> Optional[str]:
        """A weaker neighbour worth marching on -- your vassals included.

        `reach` is how strong the neighbour may be against his own muster;
        it rises as he waits (see `waited`)."""
        me = self.world.towns[key]
        mine_strength = host_strength(self._muster_enemy(me, self.war_pressure(),
                                                         spread=False))
        best, best_score = None, 0.0
        for other_key, other in self.world.towns.items():
            if other_key == key or other.owner == key:
                continue
            if self.world.liege_of(other_key) == me.owner and me.owner:
                continue                      # not your liege-brother
            defence = host_strength(other.garrison) + other.wall_hp / 12.0
            # And a share of whoever is sworn to come for him.
            holder = other.owner or other_key
            defence += self.PACT_WEIGHT * sum(host_strength(self.world.towns[p].garrison)
                                 for p in self.court.partners(holder)
                                 if p != key and p in self.world.towns)
            if defence >= mine_strength * reach:
                continue
            score = (mine_strength * reach - defence) / max(
                40.0, self.world.distance(key, other_key))
            # And his habit: Stronghold's lords each pick a target their own
            # way, which is what makes one of them predictable and another
            # a nuisance in a different corner of the map.
            hunts = lordly.sort_of(key).hunts
            if hunts == "closest":
                score /= max(1.0, self.world.distance(key, other_key) / 40.0)
            elif hunts == "gold":
                score *= other.prosperity ** 2
            elif hunts == "you" and other.mine:
                score *= 1.6
            if score > best_score:
                best, best_score = other_key, score
        return best

    WAVE_GROWTH = 0.15           # each host at you a sixth bigger, to four

    def _send_host(self, town, pressure: float, target: str) -> str:
        host = self._muster_enemy(town, pressure)
        if target in self.world.settlements:
            grow = 1.0 + self.WAVE_GROWTH * min(4, town.waves)
            host = {k: v * grow for k, v in host.items()}
            town.waves += 1
        # Bought out of his chest, as much of it as he can pay for -- never
        # less than a third of a host, which is a raiding party at worst.
        if town.chest >= 0:
            price = self._host_price(host)
            share = max(0.35, min(1.0, town.chest / max(price, 1.0)))
            if share < 1.0:
                host = {k: v * share for k, v in host.items() if v * share >= 0.5}
            town.chest -= price * share
        a = Army(uid=self.next_army_uid, name=f"{town.lord}'s host", owner=town.key,
                 units=host, at=town.key, home=town.key)
        self.next_army_uid += 1
        self.armies.append(a)
        self._outfit(a, town.key)
        water = self._set_march(a, town.key, target, host)
        town.hostility = 0.0
        for other in self.world.towns.values():
            if other is not town:
                other.hostility = max(0.0, other.hostility - 45.0)
        if target in self.world.settlements:
            # Their host is on your land, which is the oldest reason there is.
            self.court.give_ground(town.key, "attacked", self.day)
            if town.truce_days > 0:
                self.court.give_ground(town.key, "broken_truce", self.day)
                self.court.write(town.key, "truce", -25.0, self.day)
        who = "WAR" if target in self.world.settlements else "The march"
        said = ""
        if target in self.world.settlements:
            line = lordly.says(town.key, "declares", self.voice)
            if line:
                said = f'\n    {town.lord}: "{line}"'
        return (f"{who}: {town.lord} of {town.name} marches on "
                f"{self.world.node_name(target)} with {describe(host)} -- "
                f"{a.days_left:.0f} days out"
                + (f", {water}" if water else "") + said)

    def war_pressure(self) -> float:
        return min(2.6, 1.0 + self.day / (1.7 * C.DAYS_PER_YEAR))

    def _nearest_foreign(self) -> str:
        """The foreign town closest to your seat, for a claim that has to
        land somewhere the map actually put one."""
        seat = self.home()
        here = self.world.coords.get(getattr(seat, "key", ""), (0.0, 0.0))
        best, far = "", 1e9
        for key, t in self.world.towns.items():
            if t.mine:
                continue
            x, y = self.world.coords.get(key, (0.0, 0.0))
            d = (x - here[0]) ** 2 + (y - here[1]) ** 2
            if d < far:
                best, far = key, d
        return best

    def _muster_enemy(self, town, pressure: float, spread: bool = True) -> Dict[str, float]:
        scale = town.muster * pressure * (0.6 + 0.5 * town.prosperity)
        if spread:
            scale *= 0.7 + 0.6 * self.rng.random()
        host = {"spearman": round(10 * scale), "archer": round(7 * scale)}
        if self.progress.age >= 2 or pressure > 1.6:
            host["man_at_arms"] = round(5 * scale)
        if self.progress.age >= 3 or pressure > 2.4:
            host["knight"] = round(3 * scale)
            host["ram"] = max(1, round(1.4 * scale))
            host["engineer"] = round(3 * scale)
        if self.progress.age >= 4:
            host["trebuchet"] = max(1, round(0.8 * scale))
        return {k: float(v) for k, v in host.items() if v > 0}

    # ------------------------------------------------------------ diplomacy
    def gift(self, town_key: str, coin: float) -> str:
        """Buy a lord's goodwill. Cheaper than a wall, and it does not last."""
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to send to"
        if town.mine:
            return f"{town.name} is already sworn to you"
        coin = max(0.0, float(coin))
        if self.treasury < coin:
            return f"you have {self.treasury:,.0f}c"
        self.treasury -= coin
        self._outlay += coin
        before = town.hostility
        town.hostility = max(0.0, town.hostility - coin * C.GIFT_PER_COIN)
        # "a gift is forgotten as the favour decays" is what `wed` has said
        # about this since it was written, and until the ledger existed there
        # was nowhere for it to decay: `favour` only ever went up. It does now.
        self.court.write(town_key, "gift", coin * 0.01, self.day)
        self.kin.did("open", 0.10)
        self.kin.teach("charm", 6.0, self.day, post="envoy")
        return (f"{coin:,.0f}c goes to {town.lord} of {town.name}; "
                f"his temper cools from {before:.0f} to {town.hostility:.0f}")

    def truce_cost(self, town_key: str, days: int) -> float:
        town = self.world.towns[town_key]
        # An envoy who has sat with these people before does not pay the
        # stranger's price, and neither does a lord with a name for mercy.
        # And what sort of man he is. A Magpie would rather be paid than
        # fight and prices himself accordingly; the Wolf takes your coin and
        # calls it tribute.
        # And the war itself: a lord you are beating asks less for peace,
        # one who is beating you asks more -- EU4's war score on the price.
        war = max(0.35, min(2.0, 1.0 - self.court.score.get(town_key, 0.0) / 100.0))
        # And a long war is a war both sides are tired of.
        war *= max(0.6, 1.0 - self.court.war_days.get(town_key, 0) / 500.0)
        # And how little he likes you, squared: Freeciv's AI prices a treaty
        # on the goodwill it is short of, so a lord who merely dislikes you
        # asks a little over the odds and one who hates you a great deal.
        short = max(0.0, 25.0 - self.court.settled_view(town_key, self.day)) / 100.0
        war *= 1.0 + 1.5 * short * short
        return (C.TRUCE_RATE * days * town.muster * town.prosperity * war
                * self.kin.mult("truce_cost") * lordly.sort_of(town_key).bought)

    def truce(self, town_key: str, days: int = 180) -> str:
        """Peace by the day. A lord who is paid not to march does not march."""
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to treat with"
        if town.mine:
            return f"{town.name} is sworn to you already"
        if town_key in self.court.coalition:
            # The point of the letter. Buying them off one at a time is
            # exactly what they signed it to stop you doing.
            return (f"{town.lord} has put his name to the letter against you "
                    f"and will not treat alone. `court` says what the whole "
                    f"of it would cost, and what it would take to let it "
                    f"lapse.")
        days = max(1, int(days))
        if self.court.score.get(town_key, 0.0) <= -50.0:
            return (f"{town.lord} is winning this war and knows it. He will "
                    f"talk when that changes.")
        falling = self.about_to_take(town_key)
        if falling:
            return (f"{town.lord}'s men are on the wall at {falling}. He will "
                    f"talk about peace after he has it.")
        cost = self.truce_cost(town_key, days)
        if self.day - self.court.sued.get(town_key, -9999) <= self.SUIT_DAYS:
            cost = 0.0                  # he asked
        if self.treasury < cost:
            return (f"{days} days of peace with {town.name} costs "
                    f"{cost:,.0f}c; you have {self.treasury:,.0f}c")
        self.treasury -= cost
        self._outlay += cost
        town.truce_days = max(town.truce_days, days)
        town.hostility = min(town.hostility, 40.0)
        self.kin.did("merciful", 0.10)
        self.kin.teach("charm", 8.0, self.day, post="envoy")
        line = lordly.says(town_key, "paid", self.voice)
        tail = f'\n    {town.lord}: "{line}"' if line else ""
        return (f"{town.lord} of {town.name} takes {cost:,.0f}c and swears off "
                f"the march for {days} days" + tail)

    def buy_off_coalition(self) -> str:
        """Pay the whole letter off at once, which is the only way to pay it.

        Dear on purpose. The coalition exists to make the third town cost
        something that the first two did not, and a price you can always meet
        would make it a toll rather than a decision. The cheap way out is the
        slow one: stop taking towns and let it wear off.
        """
        c = self.court
        if not c.coalition:
            return "there is no letter against you"
        cost = c.coalition_price(self.day)
        if self.treasury < cost:
            return (f"buying the whole letter off costs {cost:,.0f}c and you "
                    f"have {self.treasury:,.0f}c. Beating their hosts in the "
                    f"field is the other way, and waiting is the third.")
        self.treasury -= cost
        self._outlay += cost
        for key in list(c.coalition):
            c.write(key, "gift", c.offence(key, self.day) * 0.75, self.day)
            t = self.world.towns.get(key)
            if t is not None:
                t.truce_days = max(t.truce_days, 150)
        names = [self.world.node_name(k) for k in c.coalition]
        c.coalition = []
        c.coalition_day = -1
        self.kin.teach("charm", 25.0, self.day, post="envoy")
        return self.note(f"*** {cost:,.0f}c buys the letter back. "
                         f"{', '.join(names)} stand down, and none of them "
                         f"will say what it cost them. ***", MOMENTOUS)

    def demand(self, town_key: str) -> str:
        """Demand tribute. It works on a weaker lord and enrages any other."""
        self.court.write(town_key, "demanded", -18.0, self.day)
        town = self.world.towns.get(town_key)
        if town is None:
            return f"there is no {town_key!r} to lean on"
        if town.mine:
            return f"{town.name} already pays you"
        mine = sum(host_strength(s.units) for s in self.world.settlements.values())
        mine += sum(host_strength(a.units) for a in self.armies if a.owner == "player")
        theirs = host_strength(self.likely_host(town_key)) + town.wall_hp / 10.0
        # Freeciv's greed: what he gives, and how hard you must lean to get
        # it, goes on the goodwill he is short of -- squared, so a lord who
        # merely dislikes you haggles and one who hates you makes you prove it.
        short = max(0.0, 25.0 - self.court.settled_view(town_key, self.day)) / 100.0
        greed = 1.0 + short * short
        if mine < theirs * 1.5 * greed:
            town.hostility = min(C.HOSTILITY_WAR, town.hostility + 30.0)
            return (f"{town.lord} of {town.name} laughs at you and calls his "
                    f"levies (his strength {theirs:.0f} against your {mine:.0f})")
        paid = 220.0 * town.wealth * town.prosperity * (1.0 + self.rng.random())
        paid = min(paid, 4000.0) / greed
        self.treasury += paid
        town.hostility = min(C.HOSTILITY_WAR, town.hostility + 12.0)
        town.prosperity = max(0.4, town.prosperity - 0.04)
        return (f"{town.lord} of {town.name} pays {paid:,.0f}c and remembers it")
