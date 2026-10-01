"""What a patient steward would point at next: the hints, and how a game
that is over says so.

One part of the terminal console (see cli.py). `self` is the Console.
"""

from __future__ import annotations

from typing import List, Tuple

from . import config as C
from .castle import PLANS, Works
from .economics import marginal_hands
from .goods import RATION_GOODS, good, nourishment
from . import kin as kinly
from . import league as lg
from . import chancery
from . import keep as keeps
from . import render as ink
from . import rivers as waters
from .military import describe


class AdviceMixin:
    """The console's advice. Mixed into Console; see cli.py."""

    def win_text(self) -> str:
        g = self.game
        goals = g.goals
        lines = [""]
        ways = []
        if "wealth" in goals.paths:
            ways.append(f"    WEALTH    {goals.net_worth:,.0f}c of net worth with "
                        f"{goals.population} souls under your rule.")
        if "dominion" in goals.paths:
            ways.append(f"    DOMINION  {goals.towns} towns sworn to you -- "
                        f"and still held at the end.")
        if "bells" in goals.paths and goals.wonder:
            ways.append("    THE BELLS Finish the cathedral and hold it half a year.")
        word = {1: "One way", 2: "Two ways", 3: "Three ways"}.get(len(ways), "Ways")
        lines.append(f"  {word}, inside {goals.years} years:")
        lines.append("")
        lines += ways
        lines += ["",
                  f"  You lose if your debts pass {abs(goals.bankruptcy):,.0f}c, or there is",
                  "  nowhere left that you hold. Being stormed is survivable: the keep",
                  "  comes down and the town is gutted, but a lord with a second",
                  "  settlement is still a lord."]
        return "\n".join(lines)

    def _castle_hints(self, coming: bool) -> List[Tuple[float, str]]:
        """The shape of the wall, which is where they will actually come in.

        Ranked rather than appended, and ranked hard when there is a host on
        the road: a hole in your own castle is the most urgent sentence in
        the game at that moment, and it was falling off the bottom of a list
        capped at four because it happened to be written last.
        """
        s = self.settlement()
        r = keeps.read(s.plan())
        urgent = 1.0 if coming else 0.0
        out: List[Tuple[float, str]] = []
        if r.yards and not r.shut:
            out.append((62.0 + 12.0 * urgent,
                        f"The ring at {s.name} is not closed -- the hall is "
                        f"not behind anything. `castle` draws where; "
                        f"`wall <x,y> <x,y>` shuts it."))
        left = s.outside_the_wall()
        if left:
            out.append((41.0 + 17.0 * urgent,
                        f"{len(left)} building(s) at {s.name} stand outside "
                        f"the wall, and outside is what gets burned. `castle` "
                        f"names them."))
        if len(r.weak) >= 5:
            out.append((38.0 + 17.0 * urgent,
                        f"{len(r.weak)} yards on the {r.weak_side} of "
                        f"{s.name} have no tower looking down at them, which "
                        f"is where the ladders go. `tower <x,y>` fixes it; "
                        f"`castle` shows it."))
        held = r.density(sum(s.units.values()))
        if r.yards and held < keeps.HELD * 0.6:
            out.append((36.0 + 16.0 * urgent,
                        f"{s.name} has {held:.1f} men to the yard over "
                        f"{r.yards} yards of wall. Recruit, or draw a shorter "
                        f"castle -- `castle` has both numbers."))
        return out

    def _court_hints(self) -> List[Tuple[float, str]]:
        """The politics, ranked against everything else a steward might say.

        Two of these are the most urgent sentences in the game when they are
        true -- an ally waiting on an answer with a clock running, and the
        moment before the march stops quarrelling with itself.
        """
        g = self.game
        c = g.court
        out: List[Tuple[float, str]] = []
        if c.called is not None:
            left = g.CALL_DAYS - (g.day - c.called[1])
            out.append((88.0, f"{g.world.node_name(c.called[0])} has called "
                              f"you to his war and wants an answer in {left} "
                              f"day(s). `call yes` or `call no` -- and the "
                              f"march hears which."))
        if c.coalition:
            out.append((72.0, f"{len(c.coalition)} lords have signed one "
                              f"letter against you. They march together and "
                              f"none will treat alone. `court` has the three "
                              f"ways out."))
        else:
            # Stronghold's inn and EU4's letter are the same pressure: a town
            # grown past what its inn serves and a march grown past what its
            # lords will bear. The first is a hole in the ring; so is this,
            # and it ranks with it (see _castle_hints).
            tips = g.coalition_after_next()
            if len(tips) >= chancery.COALITION_NAMES:
                names = ", ".join(g.world.node_name(k) for k in tips[:4])
                out.append((74.0, f"One more town taken and {len(tips)} lords "
                                  f"sign one letter against you ({names}). "
                                  f"`court` says how close, and it costs "
                                  f"nothing to wait."))
        warm = [k for k, t in g.world.towns.items()
                if not t.mine and k not in c.allies
                and c.opinion(k, g.day) >= chancery.WARM]
        if warm and not c.allies:
            out.append((34.0, f"{g.world.node_name(warm[0])} thinks well "
                              f"enough of you to swear -- `ally {warm[0]}`. "
                              f"An ally comes when you are attacked."))
        return out

    def _kin_hints(self) -> List[Tuple[float, str]]:
        """The house is the easiest system in the game to never notice.

        Everything else announces itself -- a wall falls down, a cart stops
        earning, a granary empties. A son of sixteen with nothing to do makes
        no noise at all, and the cost of that is invisible for ten years and
        then decides a succession.
        """
        g = self.game
        out: List[Tuple[float, str]] = []
        k = g.kin
        idle = [p for p in k.living()
                if p.uid != k.head and not p.post and not p.inlaw
                and p.age(g.day) >= kinly.COMES_OF_AGE]
        if idle:
            who = idle[0]
            spare = [key for key in kinly.POSTS if not k.holder(key)]
            job = spare[0] if spare else "steward"
            where = ("" if not kinly.POSTS[job].needs
                     else " " + self._where_name(g))
            them = "him" if who.sex == "m" else "her"
            out.append((30.0, f"{who.name} is {who.age(g.day)} and has nothing "
                        f"to do. `post {who.name.split()[0].lower()} "
                        f"{job}{where}` starts {them} at something -- a skill "
                        f"only grows in the job."))
        if g.day > 180 and not any(p.married_to for p in k.people if p.alive):
            free = [p for p in k.living()
                    if not p.spouse and p.age(g.day) >= kinly.COMES_OF_AGE
                    and p.uid != k.head]
            if free:
                out.append((28.0, "Nobody of yours is married out. A match is "
                            "the only peace that does not run out -- `marry` "
                            "prices them."))
        heir = k.heir(g.day)
        lord = k.lord
        if lord is not None and lord.age(g.day) >= kinly.ELDERLY:
            if heir is None:
                out.append((62.0, f"{lord.name} is {lord.age(g.day)} and there "
                            f"is nobody behind him. The line ends where he "
                            f"does."))
            elif not heir.post:
                out.append((46.0, f"{lord.name} is {lord.age(g.day)}. "
                            f"{heir.name} takes the seat after him and has "
                            f"never held a post -- whatever they have not "
                            f"learned by then, they never will."))
        return out

    def _economy_hints(self) -> List[Tuple[float, str]]:
        """What the accounts would tell you if you asked them.

        Two of these are things the game could never say before: a shed that
        is losing money on every unit it makes looks exactly like a shed that
        is working, and a price control looks like a kindness right up until
        the shelf is empty.
        """
        g = self.game
        out: List[Tuple[float, str]] = []
        s = self.settlement()
        losing = [r for r in marginal_hands(s) if r.shut]
        if losing:
            worst = losing[0]
            verb, its = (("pays", "it costs") if len(losing) == 1
                         else ("pay", "they cost"))
            out.append((70.0, f"{ink.count(len(losing), 'shed')} of yours "
                        f"{verb} less than {its}: the {worst.name} makes "
                        f"{worst.net:,.1f}c a hand against a wage of "
                        f"{C.WAGE:.2f}c. `margin` ranks them; `close <id>` "
                        f"stops one."))
        for key, bite in sorted(g.economy.shortage.items(), key=lambda kv: -kv[1]):
            if bite > 0.15:
                out.append((88.0, f"The assize on {good(key).name} is "
                            f"{bite * 100:.0f}% under what it is worth, so "
                            f"there is none to be had at any price. `assize "
                            f"{key} off` lets it find its own."))
                break
        # Somebody said out loud that they are coming, and the whole reason
        # for saying it out loud is that you get to do something about it.
        se = g.league.season
        for f in se.fixtures:
            if f.done or f.target not in g.world.settlements:
                continue
            out.append((84.0, f"{self._name(f.who)} has said they mean to move "
                        f"on {self._name(f.target)}. `season` has the table and "
                        f"the rest of the schedule; `truce {f.who}` buys them "
                        f"off; `plans` says what they could try."))
            break
        if se.on_the_clock() == lg.PLAYER and se.undrafted():
            best = max(se.undrafted(), key=lambda p: p.grade)
            out.append((72.0, f"You are on the clock and {best.name} is the best "
                        f"man left ({best.skill} {best.grade}). `draft "
                        f"{best.name.split()[0].lower()}` takes him."))
        over = g.muster_cost()
        if over > 1.25:
            out.append((58.0, f"Your muster is past what "
                        f"{ink.count(len(g.world.settlements), 'town')} can keep: "
                        f"every soldier costs {over:.1f} times his wage. "
                        f"`standdown` or take another town."))
        # The most actionable thing there is: you are going to fall short, and
        # there are still two years to do something about it.
        left = g.goals.days - g.day
        if g.day > 150 and left > 120:
            for what, now, want, land in g.pace():
                if now <= 0 or land >= want * 0.9:
                    continue
                out.append((68.0, f"At the rate of the last season you finish "
                            f"with {land:,.0f} {what} against {want:,.0f}, and "
                            f"there are {left} days left. Something has to "
                            f"change before it is arithmetic. `status` keeps "
                            f"the count."))
                break
        a = g.accounts
        if a.inflation > 12 and g.economy.minted > 0:
            span = "a year" if a.yearly else "since you began"
            out.append((64.0, f"Prices are running {a.inflation:.0f}% {span} "
                        f"and you have struck {g.economy.minted:,.0f}c. That is "
                        f"the same sentence twice. `economy`."))
        if a.unemployment > 35 and g.day > 200:
            # And say what is standing idle for want of something other than
            # hands, because that is usually the cheaper fix than a new shed.
            stalled = sorted({b.idle_reason for s in g.world.settlements.values()
                              for b in s.buildings
                              if b.idle_reason.startswith("no ")})
            tail = (f" Meanwhile sheds stand cold for {', '.join(stalled[:2])}."
                    if stalled else "")
            out.append((52.0, f"{a.unemployment:.0f}% of your hands have "
                        f"nowhere to go. Every one of them eats and none of "
                        f"them makes anything -- raise workshops, not roofs."
                        + tail))
        return out

    def cmd_hint(self, args: List[str]) -> None:
        """What a patient steward would point at next."""
        for line in self.hints():
            self.say(f"  * {line}")

    def hints(self) -> List[str]:
        """What a patient steward would point at, in the order he would."""
        g = self.game
        out: List[str] = []
        s = self.settlement()
        p = g.progress
        food = nourishment({k: s.market.stock[k] for k in RATION_GOODS})
        days = food / max(0.2 * s.population, 1e-6)
        coming = [a for a in g.armies if a.owner != "player"]
        if coming:
            a = coming[0]
            out.append(f"{a.name} is {self._where(a)} with {describe(a.units)}. "
                       f"`garrison` shows what you have; `recruit` adds to it.")
            # What they can try is decided by what you dug, and a ditch is days
            # of work where a tower is a season -- so it is worth saying now.
            mine = Works.of([b.key for b in s.buildings
                             if b.complete and b.spec.terrain == "rampart"])
            gaps = [label for have, label in
                    ((mine.moat, "a moat stops a mine and holds a ram off for days"),
                     (mine.pitch, "a pitch ditch is four days' work and breaks one assault"),
                     (mine.pits, "killing pits make every storm cost more"))
                    if not have]
            if gaps:
                out.append(f"Nothing is dug in front of {s.name}: {gaps[0]}. "
                           f"`plans {self.here}` shows what they could try.")
        sieging = [a for a in g.armies if a.owner == "player" and a.state == "besieging"]
        if sieging:
            a = sieging[0]
            out.append(f"{a.name} is set to {PLANS[a.siege.plan].name}. "
                       f"`plans {a.at}` shows what stands against that, and "
                       f"`siege {a.uid} <plan>` changes it.")
        if days < 12:
            out.append(f"{s.name} has about {ink.count(days, 'day')} of food. Build a farm, "
                       f"a mill and a bakery -- or buy bread in from Vantry.")
        if s.popularity < 40:
            out.append(f"Mood at {s.name} is {s.popularity:.0f}. `town` lists what is "
                       f"pulling it down; rations and taxes are the two big levers.")
        if s.housing(p) < s.population + 5:
            out.append(f"No roofs to spare at {s.name} -- nobody new will come. "
                       f"Build cottages (or townhouses, from the third age).")
        jobs = sum(b.spec.jobs for b in s.buildings if b.complete and b.enabled)
        if jobs > s.workforce * 1.25:
            starved = next((b.spec.name for b in s.buildings
                            if b.complete and b.enabled and b.spec.jobs
                            and not b.staffed), "")
            if starved:
                out.append(f"{s.name} has {s.workforce:.0f} hands for {jobs} jobs and "
                           f"the {starved} has none. `work` shows the queue; "
                           f"`work <building> first` reorders it.")
        if s.count("inn") and s.coverage("ale_reach", needs_running=True) < 0.5:
            out.append(f"The inn at {s.name} is serving under half the town -- "
                       f"either the ale is not arriving or nobody is working it. "
                       f"Ale is worth up to {C.ALE_MOOD:.0f} of mood.")
        free = [sh for sh in g.world.shrines.values() if not sh.taken]
        if free and not g.relics_held() and g.day > 120:
            out.append(f"{ink.count(len(free), 'shrine')} still hold their "
                       f"relics. Six days' standing lifts one and they pay "
                       f"every day after. `relics`.")
        if g.lord.captured:
            out.append(f"{g.lord.name} is held at {g.lord.ransom:,.0f}c. "
                       f"`lord ransom` buys him back.")

        # The water is a hint rather than an alarm: it never stops you, it
        # only costs you days, and a player who has never looked at `water`
        # will not know why a four-day leg took six.
        want = g.worst_unbridged()
        if want is not None and want[2].ford_limit <= waters.WORTH_BRIDGING \
                and g.treasury > waters.BRIDGE_COST * 1.6:
            out.append(f"Your carts ford the {want[2].name} on the road to "
                       f"{g.world.node_name(want[1])}, and in spring that is "
                       f"days. `water bridge {want[0]} {want[1]}` puts a "
                       f"bridge on it for {waters.BRIDGE_COST:,.0f}c -- and "
                       f"everybody else's traffic then pays you to use it.")
        down = [b for b in g.world.bridges if b.owner == "player" and b.broken]
        if down:
            out.append(f"{down[0].name} is still in the river. "
                       f"`water mend {down[0].uid}` puts it back for "
                       f"{waters.BRIDGE_COST * waters.REBUILD_SHARE:,.0f}c.")

        idle = [c for c in g.caravans if not c.running]
        if idle:
            out.append(f"Caravan {idle[0].uid} is standing idle. `scan`, then "
                       f"`auto {idle[0].uid}` puts it on the best trade going.")
        if not p.advancing and p.next_age():
            nxt = p.next_age()
            coin = nxt.cost.get("coin", 0)
            if g.treasury > coin:
                out.append(f"You can afford the {nxt.name} ({coin:,.0f}c). "
                           f"`age` shows what else it wants; `age begin` starts it.")
        if p.age >= 2 and not p.researching and any(
                x.effect("research") for x in g.world.settlements.values()):
            out.append("The guildhall is idle. `tech` lists what it could take up.")
        if p.age >= 2 and not any(x.effect("research")
                                  for x in g.world.settlements.values()):
            out.append("No guildhall yet -- without one nothing is ever researched.")
        coastal = [x for x in g.world.settlements.values()
                   if x.terrain.get("coast") and not x.effect("port")]
        if coastal and p.age >= 2:
            out.append(f"{coastal[0].name} is on the water. A harbour there opens "
                       f"the sea, and a hull carries four carts' worth.")
        if g.world.sites and g.treasury > 6000:
            key = min(g.world.sites, key=lambda k: g.world.sites[k].coin_cost)
            site = g.world.sites[key]
            out.append(f"You could settle {site.name} for {site.coin_cost:,.0f}c. "
                       f"One hill will not hold {g.goals.population} souls.")
        # The body above is already in the order a steward would raise things,
        # so it keeps that order among itself. What the newer systems have to
        # say is ranked against it rather than appended to it: a hint that can
        # only appear on a quiet day is a system nobody is ever told about,
        # which is how the house and the accounts both went unmentioned for a
        # hundred turns each while the fourth line was about a guildhall.
        ranked = [(50.0 - 0.01 * i, text) for i, text in enumerate(out)]
        ranked += (self._kin_hints() + self._economy_hints()
                   + self._castle_hints(bool(coming))
                   + self._court_hints())
        ranked.sort(key=lambda row: -row[0])
        picked = [text for _, text in ranked][:4]
        if not picked:
            picked.append("Nothing pressing. `scan` for a better route, `war` to "
                          "see who is arming, `age` for the long game.")
        return picked
