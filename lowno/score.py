"""Nightly scorecard with miss attribution -- the part the operator asked for
by name: 'which low-nos you were right and which you were not, with an
explanation as to why your initial assessment was off.'"""
import json, glob, datetime as dt
from .config import QUIRKS

TAXONOMY = """attribution codes:
  WIN            settled above ceiling; gate did its job
  FORECAST_BUST  guidance missed >=3F cool -- the input lied, gate honest
  BOUNDARY       settled EXACTLY at ceiling -- the tenths decided; ladder placed well
  MECHANISM      a bust mode (precip/smoke/lake/outflow) hit that the gate scored clean
  DATA_GAP       obs/guidance unverifiable at scan time -- should have been PASS
  UNGRADED       no CLI found yet"""

def attribute(flag, settle):
    if settle is None:                       return "UNGRADED"
    if settle > flag["ceiling"]:             return "WIN"
    if settle == flag["ceiling"]:            return "BOUNDARY"
    if flag.get("guide") and flag["guide"] - settle >= 3:  return "FORECAST_BUST"
    if flag.get("pop", 0) and flag["pop"] > 10:            return "MECHANISM"
    if flag.get("guide") is None:            return "DATA_GAP"
    return "MECHANISM"

def report(day_flags, settlements):
    lines = [f"# low-no scorecard -- {dt.date.today().isoformat()}", "", TAXONOMY, ""]
    wins = losses = 0
    for f in day_flags:
        s = settlements.get(f["city"])
        code = attribute(f["detail"], s)
        wins += code == "WIN"; losses += code in ("BOUNDARY", "FORECAST_BUST", "MECHANISM")
        q = QUIRKS.get(f.get("station", ""), "")
        lines.append(f"- **{f['city']}** {f['verdict']} @ {f['detail'].get('no_ask')} "
                     f"ceil {f['detail']['ceiling']} guide {f['detail'].get('guide')} "
                     f"-> CLI {s} :: **{code}**" + (f"  _{q}_" if code != "WIN" and q else ""))
    n = wins + losses
    lines += ["", f"**{wins}/{n} hit** ({(100*wins/n):.0f}%) vs 98.2% breakeven at 0.98"
              if n else "no qualified flags today -- a complete and acceptable outcome"]
    return "\n".join(lines)
