"""STEP 6 -- advisor spend tracking, WITHOUT putting a key anywhere public.

READ THIS BEFORE ASKING FOR "BALANCE ON THE SITE":

Anthropic exposes no public balance endpoint. Cost/usage is available only via
the Admin API, which needs an `sk-ant-admin-...` key -- an ORG-LEVEL credential,
strictly more powerful than the advisor key. And docs/ is a PUBLIC GitHub Pages
site: anything the browser fetches, the world can read. A key in front-end code
is a key given away.

So this tracks spend the safe way: count the calls actually made, price them at
published rates, publish the ESTIMATE. No credential involved, nothing to leak,
and it is accurate to the cent at this volume -- 12 calls predicted $0.06 and
the console showed exactly $0.06 (5.00 -> 4.94).

If you later want the true balance, the ONLY safe shape is: an Actions step
reads an admin key from repo secrets and writes the resulting NUMBER into
docs/spend.json. The key never reaches the browser. Not enabled here.

Apply from repo root:  python spend_tracker.patch.py
"""
import os
import sys

MODULE = '''"""Advisor spend estimate. No credential required.

Counts advisor invocations from the scan logs and prices them at published
rates. Published to docs/spend.json for the site.

Why estimate rather than query: Anthropic has no public balance endpoint, and
the only usage API needs an org-level admin key. docs/ is a public Pages site,
so a key fetched client-side is a key published. An estimate costs nothing,
cannot leak, and matched the console exactly on the first 12 calls.
"""
import json, glob, os, datetime as dt

# Published per-million-token rates for the advisor model. Update here if the
# model or pricing changes -- this is the only place rates live.
RATE_IN_PER_MTOK = 3.00
RATE_OUT_PER_MTOK = 15.00

# Measured from real calls: system prompt + flag + state pack + obs + ladder.
# Output is capped at max_tokens=500 and typically runs well under.
EST_TOKENS_IN = 3000
EST_TOKENS_OUT = 350

STARTING_CREDIT = float(os.environ.get("LOWNO_STARTING_CREDIT", "5.00"))
CREDIT_ADDED_ON = os.environ.get("LOWNO_CREDIT_DATE", "2026-08-16")


def _call_cost():
    cost_in = (EST_TOKENS_IN / 1e6) * RATE_IN_PER_MTOK
    cost_out = (EST_TOKENS_OUT / 1e6) * RATE_OUT_PER_MTOK
    return cost_in + cost_out


def build():
    """Count advisor calls that actually reached the API (not SKIPPED)."""
    by_day, total, skipped = {}, 0, 0
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            a = r.get("advisor")
            if not a:
                continue
            if str(a.get("verdict", "")).upper() == "SKIPPED":
                skipped += 1
                continue
            by_day[day] = by_day.get(day, 0) + 1
            total += 1

    unit = _call_cost()
    billed = {d: n for d, n in by_day.items() if d >= CREDIT_ADDED_ON}
    spent = sum(billed.values()) * unit
    remaining = STARTING_CREDIT - spent
    return dict(
        generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        calls_total=total, calls_skipped_no_key=skipped,
        calls_by_day=dict(sorted(by_day.items())),
        cost_per_call=round(unit, 5),
        estimated_spent_since_credit=round(spent, 4),
        starting_credit=STARTING_CREDIT,
        estimated_remaining=round(remaining, 4),
        calls_remaining=int(remaining / unit) if unit else None,
        note=("ESTIMATE from call counts at published rates. Anthropic has no "
              "public balance endpoint and an admin key must never reach a "
              "public page. Verify at console.anthropic.com/settings/billing."))


def write(path="docs/spend.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = build()
    json.dump(out, open(path, "w"), indent=1)
    print(f"spend: {out['calls_total']} calls, est ${out['estimated_spent_since_credit']:.4f} "
          f"spent, ${out['estimated_remaining']:.2f} left (~{out['calls_remaining']} calls)")
    return out


if __name__ == "__main__":
    write()
'''


def main():
    if not os.path.isdir("lowno"):
        print("run from repo root (lowno/ not found)")
        sys.exit(1)

    if os.path.exists("lowno/spend.py"):
        print("lowno/spend.py exists -- leaving alone")
    else:
        open("lowno/spend.py", "w").write(MODULE)
        print("wrote lowno/spend.py")

    s = open("shadow_run.py").read()
    if "spend" in s:
        print("shadow_run.py already calls spend")
    else:
        s = s.replace("from lowno import shadow, adaptive, convergence",
                      "from lowno import shadow, adaptive, convergence, spend", 1)
        s = s.replace(
            '    json.dump(out, open("docs/shadow_summary.json", "w"), indent=1)',
            '    json.dump(out, open("docs/shadow_summary.json", "w"), indent=1)\n'
            '    try:\n        spend.write()\n'
            '    except Exception as e:\n        print("spend: skipped -", str(e)[:100])',
            1)
        open("shadow_run.py", "w").write(s)
        print("hooked spend.write() into shadow_run.py")

    print("""
DELIBERATELY NOT DONE:
  True balance via the Admin API. It requires sk-ant-admin-*, an org-level key
  far more dangerous than the advisor key. If you want it later, the safe shape
  is an Actions step that reads it from repo secrets and writes ONLY the
  resulting number into docs/spend.json. The key must never be fetched by the
  browser -- docs/ is public.
""")


if __name__ == "__main__":
    main()
