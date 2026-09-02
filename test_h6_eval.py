"""Prove h6_eval.py measures what it claims, without looking at real history.

Running H6 over the poll data it is meant to judge would answer the question
instead of testing the instrument, and this harness is already the weakest of
the registered set -- it was written after two days of data existed. So it is
verified against SYNTHETIC poll logs where the truth is known by construction:
it must find a planted lag, report null on noise, refuse below its bar, and
drop every pair that is not a clean look across a single print.

Run: python test_h6_eval.py     (exits non-zero on any failure)
"""
import datetime as dt
import json
import os
import random
import shutil
import sys
import tempfile

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def row(at, city, print_at, print_f, dev, na, nb=None, ticker="T", cap=80):
    return json.dumps(dict(
        at=at.isoformat().replace("+00:00", "Z"), city=city, station="K" + city,
        last_print_at=print_at, last_print_f=print_f, stale_min=10,
        nowcast_f=(None if dev is None else print_f + dev),
        nowcast_minus_print=dev, n_neighbours=4, lead_min=20,
        rung=dict(ticker=ticker, cap=cap, na=na, nb=nb, ya=100 - na,
                  yb=None, oi=100, vol=100)))


def world(root, n_days, lag_strength, seed=7, step_min=5):
    """One print per hour, polled every `step_min` minutes.

    Price is a random walk. On the cycle that straddles a print the walk gets
    an extra kick of `lag_strength * dev`, where `dev` is the deviation that
    was visible on the cycle BEFORE the print. lag_strength 0 is the null.
    """
    rnd = random.Random(seed)
    os.makedirs(os.path.join(root, "logs", "poll"), exist_ok=True)
    start = dt.date(2026, 9, 1)
    for d in range(n_days):
        day = (start + dt.timedelta(days=d)).isoformat()
        lines = []
        for city in ("NYC", "DEN"):
            price = 50.0
            t = dt.datetime.fromisoformat(f"{day}T13:00:00+00:00")
            print_f, dev = 70.0, 0.0
            print_at = f"{day}T12:51Z"
            for k in range(6 * 10):                       # 10 hours of cycles
                t = t + dt.timedelta(minutes=step_min)
                crossed = (t.minute >= 51 and (t - dt.timedelta(minutes=step_min)).minute < 51)
                kick = 0.0
                if crossed:
                    kick = lag_strength * dev             # the planted lag
                    print_f = round(print_f + dev + rnd.gauss(0, 0.2), 2)
                    print_at = t.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%MZ")
                    dev = round(rnd.gauss(0, 1.0), 2)     # a fresh deviation opens
                price = max(2.0, min(98.0, price + kick + rnd.gauss(0, 0.4)))
                lines.append(row(t, city, print_at, print_f, dev,
                                 na=int(round(price)) + 1, nb=int(round(price)) - 1))
        with open(os.path.join(root, "logs", "poll", f"{day}.jsonl"), "w") as fh:
            fh.write("\n".join(lines) + "\n")


def run_in(root, fn):
    cwd = os.getcwd()
    try:
        os.chdir(root)
        sys.modules.pop("h6_eval", None)
        sys.path.insert(0, cwd)
        import h6_eval as H
        return fn(H)
    finally:
        sys.path.remove(cwd)
        os.chdir(cwd)
        sys.modules.pop("h6_eval", None)


def main():
    print("h6_eval on synthetic worlds\n")

    # 1. A planted lag must be found.
    root = tempfile.mkdtemp(prefix="h6a_")
    try:
        world(root, 25, lag_strength=3.0)
        v = run_in(root, lambda H: H.verdict())
        check("finds a planted lag", v.get("passed") is True, str(v)[:120])
        check("reports it as ready on a met bar", v.get("ready") is True)
        check("clears both legs of the registered bar",
              v.get("events", 0) >= 200 and v.get("days", 0) >= 20,
              f"{v.get('events')} events / {v.get('days')} days")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 2. Noise must not pass.
    root = tempfile.mkdtemp(prefix="h6b_")
    try:
        world(root, 25, lag_strength=0.0, seed=11)
        v = run_in(root, lambda H: H.verdict())
        check("reports null on a no-lag world", v.get("passed") is False,
              f"corr {v.get('across_corr')} ci {v.get('across_ci')}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 3. Below the bar it must refuse, however strong the planted effect.
    root = tempfile.mkdtemp(prefix="h6c_")
    try:
        world(root, 5, lag_strength=6.0)
        v = run_in(root, lambda H: H.verdict())
        check("refuses below the data bar even with a huge planted effect",
              v.get("ready") is False and v.get("passed") is False,
              v.get("reason", ""))
        check("refusal carries both legs' counts",
              v.get("need_events") == 200 and v.get("need_days") == 20)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 4. Pair hygiene: each rejection rule must actually reject.
    root = tempfile.mkdtemp(prefix="h6d_")
    try:
        os.makedirs(os.path.join(root, "logs", "poll"))
        t0 = dt.datetime.fromisoformat("2026-09-01T18:00:00+00:00")
        m = lambda k: t0 + dt.timedelta(minutes=k)
        P1, P2 = "2026-09-01T17:51Z", "2026-09-01T18:51Z"
        cases = [
            # (name, rows, expected events)
            ("a clean look across one print",
             [row(m(0), "NYC", P1, 70.0, 1.0, 50, 48),
              row(m(5), "NYC", P2, 71.0, 0.2, 55, 53)], 1),
            ("no print between the rows",
             [row(m(0), "NYC", P1, 70.0, 1.0, 50, 48),
              row(m(5), "NYC", P1, 70.0, 1.1, 55, 53)], 0),
            ("no real NO offer (na == 100)",
             [row(m(0), "NYC", P1, 70.0, 1.0, 100, 99),
              row(m(5), "NYC", P2, 71.0, 0.2, 55, 53)], 0),
            ("the rung changed under us",
             [row(m(0), "NYC", P1, 70.0, 1.0, 50, 48, ticker="T81"),
              row(m(5), "NYC", P2, 71.0, 0.2, 55, 53, ticker="T83")], 0),
            ("the pair straddles a poll outage",
             [row(m(0), "NYC", P1, 70.0, 1.0, 50, 48),
              row(m(40), "NYC", P2, 71.0, 0.2, 55, 53)], 0),
            ("nothing was known to be stale (dev None)",
             [row(m(0), "NYC", P1, 70.0, None, 50, 48),
              row(m(5), "NYC", P2, 71.0, 0.2, 55, 53)], 0),
        ]
        for name, rows, want in cases:
            p = os.path.join(root, "logs", "poll", "2026-09-01.jsonl")
            with open(p, "w") as fh:
                fh.write("\n".join(rows) + "\n")
            n = run_in(root, lambda H: len(H._events(H.series())))
            check(name + f" -> {want} event(s)", n == want, f"got {n}")

        # move_before must not reach back across a different print.
        with open(os.path.join(root, "logs", "poll", "2026-09-01.jsonl"), "w") as fh:
            fh.write("\n".join([
                row(m(-5), "NYC", "2026-09-01T16:51Z", 69.0, 0.5, 45, 43),
                row(m(0), "NYC", P1, 70.0, 1.0, 50, 48),
                row(m(5), "NYC", P2, 71.0, 0.2, 55, 53)]) + "\n")
        ev = run_in(root, lambda H: H._events(H.series()))
        got = [e for e in ev if e["move_across"] is not None]
        check("move_before stays inside one print window",
              len(got) == 2 and got[-1]["move_before"] is None,
              f"{len(got)} events, last move_before {got[-1]['move_before'] if got else '--'}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all checks passed -- the harness measures what it claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
