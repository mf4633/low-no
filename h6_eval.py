"""Hypothesis 6 -- does the market price off the STALE print at KNYC and KDEN?

WHEN THIS WAS WRITTEN, AND WHAT HAD BEEN SEEN. 2026-09-02, after two days of
poll data existed (2026-08-31, 2026-09-01) but BEFORE any H6 quantity was
computed. That is weaker than H4b/H5/H7, all of which were written before their
data existed at all, so the exposure is disclosed in full at the bottom of this
docstring rather than glossed. No pairing, no price move across any print, and
no correlation of any kind had been computed when the rules below were fixed.

THE CLAIM (CANDIDATE.md, registered 2026-08-31). 21 of the 23 settlement
stations publish every 4-5 minutes; KNYC and KDEN publish hourly. Between
prints the market's most recent official reading is up to an hour old, while
the neighbour ensemble already knows where the host sits. If the market prices
off the stale print, the mispricing should be RESOLVED BY THE PRINT: the price
moves when the new number publishes, in the direction the nowcast had already
indicated. If the market is efficient, that move happened earlier, with the
information, and there is nothing left in the print.

DIRECTION. nowcast > last print = the host is running hotter than its published
number = the bottom `<= cap` bucket is more likely to be EXCEEDED = the NO
contract is worth MORE. So the lag implies a POSITIVE correlation between
`nowcast_minus_print` measured on the last cycle BEFORE a print and the NO
price change ACROSS that print.

THE PRE-DECLARED TRAP, and it is the whole reason `move_before` is computed. A
positive correlation across the print is NOT evidence of a lag on its own: if
the market moves just as much WITH the information in the cycles before the
print, then the print resolves nothing and the correlation is measuring a trend
that both windows share. The contemporaneous number is reported beside the
lagged one for exactly that comparison, as in H4b.

THE BAR IS H4b's, DELIBERATELY: >= 200 events AND >= 20 distinct days. This is
the same class of claim (does the market lag an observable we compute), on the
same instrument (the bottom-rung NO price), so it inherits the same bar rather
than a fresh one chosen after seeing how fast H6 events accrue. At ~1 print per
city-hour over two cities the events leg is not binding; the 20 distinct days
is, and poll data starts 2026-08-31.

TWO CITIES, POOLED VERDICT, PER-CITY CONTEXT. There is no control stratum here
-- both cities are hourly, that is why they are the only two polled -- so the
verdict is pooled and the per-city split is context. Pre-declared, so it cannot
be read the convenient way later: "it works at DEN but not NYC" is SUSPICIOUS,
not encouraging. DEN's nowcast is the stronger of the two (measured 2026-08-31)
and a one-city result on two cities is what a null looks like half the time.

WHAT THIS TEST CANNOT DO. It cannot promote anything. CANDIDATE.md's own H6
arithmetic is that 60 units needs ~30 days of both cities firing, which runs
past the 2026-12-31 programme stop. This is a necessary-condition test on the
information claim, exactly like H4b, and a pass here is not a trading result.

NOT TO BE TUNED. If a rule below needs to change, the change is recorded in
CANDIDATE.md with a reason, like every other correction in this project.

DISCLOSURE -- everything about the poll data that had been looked at when this
file was written:
  * row counts: 96 rows on 2026-08-31, 152 on 2026-09-01
  * city split on 2026-09-01: NYC 76 / DEN 76
  * field presence: `nowcast_f` on 148 of 152 rows, every other field 152/152
  * clock coverage: 18:20-23:39Z on 08-31, 17:15-23:36Z on 09-01, one 83-minute
    gap on 08-31; the 13:02Z cron has never delivered, so there is no morning
  * the raw schema of one row (the first of 2026-09-01), which carried
    stale_min 17, lead_min 36, nowcast_minus_print +0.23, cap 82, na 8, nb 7
That is instrumentation. Nothing relating a deviation to a price was computed.
"""
import datetime as dt
import glob
import json
import os

from curve_lag import fisher_ci, pearson

MIN_EVENTS, MIN_DAYS = 200, 20
# The poller steps every 300s. Allowing two missed cycles keeps a pair that
# straddles a print without letting an hour of unrelated drift in. Structural:
# it is the instrument's own cadence, not a number fitted to an outcome.
MAX_PAIR_MIN = 15


def _price(rung):
    """NO price in cents, or None when there is no real offer.

    `na == 100` is Kalshi's way of saying no ask exists, not a 100c price --
    treating it as one injected 46 phantom cycles into a calibration table
    once. Mid when both sides are real, ask otherwise, same rule as curve_lag.
    """
    if not isinstance(rung, dict):
        return None
    na, nb = rung.get("na"), rung.get("nb")
    if na is None or na >= 100:
        return None
    if nb is not None and 0 < nb < 100:
        return (na + nb) / 2.0
    return float(na)


def series():
    """(day, city) -> chronological list of poll rows, normalised.

    Reads logs/poll/ ONLY. Those rows are deliberately invisible to
    glob("logs/2*.jsonl"), so nothing here can reach a ladder, a band, a
    variant or the gate, and nothing there reaches this.
    """
    out = {}
    for path in sorted(glob.glob("logs/poll/*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            city, rung = r.get("city"), r.get("rung")
            price = _price(rung)
            if not city or price is None:
                continue
            try:
                at = dt.datetime.fromisoformat(r["at"].replace("Z", "+00:00"))
            except Exception:
                continue
            out.setdefault((day, city), []).append(dict(
                at=at, day=day, city=city,
                print_at=r.get("last_print_at"),
                print_f=r.get("last_print_f"),
                dev=r.get("nowcast_minus_print"),
                price=price, ticker=(rung or {}).get("ticker"),
                stale_min=r.get("stale_min"), lead_min=r.get("lead_min")))
    for k in out:
        out[k].sort(key=lambda x: x["at"])
    return out


def _events(S):
    """One event per observed PRINT TRANSITION with a clean price pair.

    A transition is two consecutive poll rows whose `last_print_at` differs:
    the host published between them. The earlier row is what the market could
    see while the print was stale; the later row is the first look after it
    landed.
    """
    events = []
    for (day, city), v in S.items():
        for i in range(1, len(v)):
            a, b = v[i - 1], v[i]
            if not a["print_at"] or not b["print_at"]:
                continue
            if a["print_at"] == b["print_at"]:
                continue                      # no print landed between these
            if a["dev"] is None:
                continue                      # nothing was known to be stale
            if a["ticker"] != b["ticker"] or a["ticker"] is None:
                continue                      # a rung change is not a repricing
            gap = (b["at"] - a["at"]).total_seconds() / 60.0
            if not 0 < gap <= MAX_PAIR_MIN:
                continue
            # The cycle before the pair, for the contemporaneous comparison.
            move_before = None
            if i >= 2:
                z = v[i - 2]
                gap0 = (a["at"] - z["at"]).total_seconds() / 60.0
                if (0 < gap0 <= MAX_PAIR_MIN and z["ticker"] == a["ticker"]
                        and z["print_at"] == a["print_at"]):
                    move_before = a["price"] - z["price"]
            realized = None
            if a["print_f"] is not None and b["print_f"] is not None:
                realized = b["print_f"] - a["print_f"]
            events.append(dict(
                day=day, city=city, at=a["at"].isoformat(),
                dev_pre=a["dev"], stale_min=a["stale_min"],
                move_across=b["price"] - a["price"],
                move_before=move_before, realized=realized))
    return events


def verdict():
    """Machine-readable gate. PASSES only when the correlation between the
    pre-print deviation and the price move ACROSS the print is positive with a
    95% CI excluding zero, on the registered bar. Both conditions fixed before
    any H6 quantity was computed."""
    try:
        events = _events(series())
    except Exception as e:
        return dict(id="H6", ready=False, passed=False, error=str(e)[:120])
    days = {e["day"] for e in events}
    if len(events) < MIN_EVENTS or len(days) < MIN_DAYS:
        return dict(id="H6", ready=False, passed=False,
                    events=len(events), need_events=MIN_EVENTS,
                    days=len(days), need_days=MIN_DAYS,
                    reason="data bar not met")
    r = pearson([e["dev_pre"] for e in events],
                [e["move_across"] for e in events])
    lo, hi = fisher_ci(r, len(events))
    return dict(id="H6", ready=True, passed=bool(lo is not None and lo > 0),
                events=len(events), days=len(days),
                across_corr=(round(r, 3) if r is not None else None),
                across_ci=[lo, hi])


def main():
    events = _events(series())
    days = {e["day"] for e in events}
    print(f"H6 events: {len(events)} (bar {MIN_EVENTS}) over "
          f"{len(days)} distinct days (bar {MIN_DAYS})")
    if len(events) < MIN_EVENTS or len(days) < MIN_DAYS:
        print("DATA BAR NOT MET -- refusing to report a result. "
              "This is the registered behaviour, not a failure.")
        return

    dev = [e["dev_pre"] for e in events]
    ra = pearson(dev, [e["move_across"] for e in events])
    print(f"\n{'window':>26} {'n':>6} {'corr':>8} {'95% CI':>18}")
    print(f"{'ACROSS the print':>26} {len(events):>6} {ra:>8.3f} "
          f"{str(fisher_ci(ra, len(events))):>18}")
    wb = [(e["dev_pre"], e["move_before"]) for e in events
          if e["move_before"] is not None]
    if len(wb) >= 4:
        rb = pearson([x for x, _ in wb], [y for _, y in wb])
        print(f"{'BEFORE it (same info)':>26} {len(wb):>6} {rb:>8.3f} "
              f"{str(fisher_ci(rb, len(wb))):>18}")

    lo, _ = fisher_ci(ra, len(events))
    print("\nverdict on the registered claim:")
    if lo is not None and lo > 0:
        print("  THE PRICE MOVES ACROSS THE PRINT in the direction the nowcast")
        print("  already indicated, 95% CI excluding zero. Necessary condition,")
        print("  NOT a trading result -- and read it beside the BEFORE row: if")
        print("  the market moved as much with the information, the print")
        print("  resolved nothing and this is a shared trend.")
    else:
        print("  No positive move across the print distinguishable from zero.")
        print("  The market is not waiting for the official number.")

    print(f"\n{'city':>8} {'n':>6} {'corr':>8}   (context, not the verdict --")
    print(f"{'':>8} {'':>6} {'':>8}    a one-city result on two cities is")
    print(f"{'':>8} {'':>6} {'':>8}    what a null looks like half the time)")
    for c in sorted({e["city"] for e in events}):
        g = [e for e in events if e["city"] == c]
        if len(g) < 4:
            continue
        rc = pearson([e["dev_pre"] for e in g], [e["move_across"] for e in g])
        print(f"{c:>8} {len(g):>6} {rc:>8.3f}" if rc is not None else
              f"{c:>8} {len(g):>6} {'--':>8}")

    # Was the nowcast even right? Context for reading a null: a deviation that
    # does not predict the next print cannot be expected to move a price.
    rr = [(e["dev_pre"], e["realized"]) for e in events
          if e["realized"] is not None]
    if len(rr) >= 4:
        r2 = pearson([x for x, _ in rr], [y for _, y in rr])
        print(f"\ndev_pre vs the print that actually landed: corr "
              f"{r2:.3f} over {len(rr)} (nowcast skill, not market behaviour)")


if __name__ == "__main__":
    main()
