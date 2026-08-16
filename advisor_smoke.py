"""Smoke test: does the advisory layer actually reach the API and return a
usable verdict? Replays a REAL graded flag (SFO 2026-08-09, the bust) so the
answer is checkable against known ground truth, and prints whether v2's state
injection reached the call.

Runs in Actions where ANTHROPIC_API_KEY lives. Prints only the verdict and
reasoning -- never the key.
"""
import json, os, sys
from lowno import advisor

key = os.environ.get("ANTHROPIC_API_KEY")
print("ANTHROPIC_API_KEY present:", bool(key), "| length looks sane:",
      bool(key and key.startswith("sk-ant-") and len(key) > 40))

flag = {"city": "SFO", "station": "KSFO", "ticker": "KXHIGHTSFO-26AUG09-T76",
        "ceiling": 76, "no_ask": 0.05, "quote_src": "native", "yes_bid": 95,
        "run_max": 69.98, "guide": 81, "pop": 0, "G": 5, "net_cents": 94.0}
obs_tail = [{"ts": "2026-08-09T17:53:00+00:00", "tC": 21.1},
            {"ts": "2026-08-09T16:53:00+00:00", "tC": 20.0},
            {"ts": "2026-08-09T15:53:00+00:00", "tC": 18.3}]
ladder = [{"ticker": "KXHIGHTSFO-26AUG09-T76", "cap": 76, "floor": None, "no_ask": 5},
          {"ticker": "KXHIGHTSFO-26AUG09-B76.5", "cap": 77, "floor": 76, "no_ask": 62}]

print("\n--- state pack that v2 injects ---")
print(json.dumps(advisor._state_pack(flag), indent=1))

print("\n--- live API call ---")
out = advisor.advise(flag, obs_tail, ladder)
print(json.dumps(out, indent=1)[:1200])

v = (out or {}).get("verdict")
print("\nRESULT:", "LIVE - advisor reached the API" if v not in (None, "SKIPPED")
      else "NOT LIVE - " + str(out.get("reasoning"))[:160])
print("GROUND TRUTH: this flag settled CLI 71 vs ceiling 76 -> FORECAST_BUST (a loss).")
print("A well-informed advisor should be cautious here: bias says guide runs hot at SFO.")
sys.exit(0)
