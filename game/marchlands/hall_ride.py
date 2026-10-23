"""The battle the day stops for: stepping it, the lord riding at their
head, the finish, and the box score.

Part of the wall (see hall_wall.py). `self` is the GameState, so
nothing here holds state of its own.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .chronicle import MOMENTOUS
from . import lord as manly
from .league import PLAYER
from .military import UNITS, Side
from . import military
from .records import PendingBattle


class RideMixin:
    """GameState's ride. Mixed into WallMixin; see hall_wall.py."""

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
