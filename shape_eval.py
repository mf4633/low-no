"""Does shape conditioning produce BETTER probabilities? Out-of-sample.

Days are split by parity of the date. Samples are built from TRAIN days only;
Brier is scored on TEST days only. A model that merely memorises cannot win
here. Scored on peak-window cycles where BOTH models produce a number, so the
comparison is like-for-like.
"""
import json, glob, os, datetime as dt, zoneinfo
from collections import defaultdict
from lowno import empirical as E
from lowno.config import CITIES


def build(days_keep):
    """(unconditioned, rated) sample tables restricted to `days_keep`."""
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    paths = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        if day not in days_keep:
            continue
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict) or d.get("world"):
                continue
            rm, city = d.get("run_max"), r.get("city")
            if rm is None or city not in CITIES:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                        .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            paths[(day, city)].append((lt.hour + lt.minute / 60.0, lt.hour, rm))
    S, R = defaultdict(list), defaultdict(list)
    for (day, city), v in paths.items():
        s = settles.get((day, city))
        if s is None:
            continue
        v.sort(key=lambda x: x[0])   # sort on time only; cap may be None
        for i, (hf, h, rm) in enumerate(v):
            S[(city, h)].append(s - rm)
            if i == 0:
                continue
            dh = hf - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            b = E.rate_bucket((rm - v[i - 1][2]) / dh)
            R[(city, h, b)].append(s - rm)
    return S, R


def cycles(days_keep):
    """Test cycles: (city, hour, run_max, rate, settle) inside the peak window."""
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    paths = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        if day not in days_keep:
            continue
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict) or d.get("world"):
                continue
            rm, city = d.get("run_max"), r.get("city")
            if rm is None or city not in CITIES:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                        .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            cap = None
            for g in d.get("rungs", []):
                if g.get("fl") is None and g.get("cap") is not None:
                    cap = g["cap"]
                    break
            paths[(day, city)].append((lt.hour + lt.minute / 60.0, lt.hour, rm, cap))
    out = []
    for (day, city), v in paths.items():
        s = settles.get((day, city))
        if s is None:
            continue
        v.sort(key=lambda x: x[0])   # sort on time only; cap may be None
        for i in range(1, len(v)):
            hf, h, rm, cap = v[i]
            if not (E.PEAK_WINDOW[0] <= h <= E.PEAK_WINDOW[1]):
                continue
            dh = hf - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            rate = (rm - v[i - 1][2]) / dh
            out.append(dict(city=city, hour=h, run_max=rm, cap=cap,
                            rate=rate, settle=s))
    return out


MIN_SCORED = 50   # decisions needed before a Brier comparison means anything


def verdict():
    """Machine-readable gate for autonomous pilot activation.

    PASSES only on a strict held-out Brier improvement over >= MIN_SCORED
    decisions. Both conditions were fixed before any comparison was run.
    """
    try:
        r = evaluate()
    except Exception as e:
        return dict(id="H4a", ready=False, passed=False, error=str(e)[:120])
    if r is None or r["n"] < MIN_SCORED:
        return dict(id="H4a", ready=False, passed=False,
                    n=(r or {}).get("n", 0), need=MIN_SCORED,
                    reason="not enough held-out decisions with an earned shape cell")
    return dict(id="H4a", ready=True, passed=bool(r["shape"] < r["base"]),
                n=r["n"], brier_base=round(r["base"], 4),
                brier_shape=round(r["shape"], 4),
                improvement_pct=round(100 * (r["base"] - r["shape"]) / r["base"], 2)
                if r["base"] else 0.0)


def evaluate():
    """Shared core: returns dict(n, base, shape) or None."""
    days = sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    train = {d for d in days if int(d[-1]) % 2 == 0}
    test = {d for d in days if int(d[-1]) % 2 == 1}
    S, R = build(train)
    base, shape, n = [], [], 0
    for c in cycles(test):
        for off in (1, 2, 3):
            cap = c["run_max"] + off
            a = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S)
            b = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S,
                           rate=c["rate"], rated_samples=R)
            if a is None or b is None:
                continue
            if not b.get("source", "").startswith("shape"):
                continue
            y = 1.0 if c["settle"] > cap else 0.0
            base.append((a["p"] - y) ** 2)
            shape.append((b["p"] - y) ** 2)
            n += 1
    if not n:
        return dict(n=0, base=None, shape=None)
    return dict(n=n, base=sum(base) / n, shape=sum(shape) / n)


def main():
    days = sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    train = {d for d in days if int(d[-1]) % 2 == 0}
    test = {d for d in days if int(d[-1]) % 2 == 1}
    S, R = build(train)
    print(f"train days {len(train)}, test days {len(test)}")

    base, shape, n, skipped = [], [], 0, 0
    for c in cycles(test):
        # evaluate on a grid of caps around the running max, so the comparison
        # does not depend on which rung happened to be listed
        for off in (1, 2, 3):
            cap = c["run_max"] + off
            a = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S)
            b = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S,
                           rate=c["rate"], rated_samples=R)
            if a is None or b is None:
                skipped += 1
                continue
            if b.get("source", "").startswith("shape") is False:
                continue      # shape cell not earned: models identical, uninformative
            y = 1.0 if c["settle"] > cap else 0.0
            base.append((a["p"] - y) ** 2)
            shape.append((b["p"] - y) ** 2)
            n += 1

    if not n:
        print("no comparable cycles")
        return
    mb, ms = sum(base) / n, sum(shape) / n
    print(f"\nscored on {n} out-of-sample cap-decisions where a shape cell exists")
    print(f"  Brier, level+hour only : {mb:.4f}")
    print(f"  Brier, + shape         : {ms:.4f}")
    imp = 100 * (mb - ms) / mb if mb else 0
    print(f"  improvement            : {imp:+.1f}%  (lower Brier is better)")
    wins = sum(1 for a, b in zip(base, shape) if b < a)
    print(f"  shape closer on {wins}/{n} decisions ({100*wins/n:.0f}%)")


if __name__ == "__main__":
    main()
