# low-no

Hourly scanner + nightly scorecard for the low-no strategy, and nothing else.
Built Aug 6, 2026 by Michael Flynn and Claude from a 130-city-day backtest and
one expensive live week.

## The constitution (do not edit after losses)

1. **Flags only.** This repo contains no order code and must never grow any.
2. **The gate is law** (`lowno/config.py`): bottom rung only, price <= 0.98
   (net floor makes 0.97 the real executable ceiling), G >= 4F vs *verified*
   guidance, PoP <= 20, no active wx on tape, entry window 10:30-13:30 local.
   Unverified guidance = PASS. Before-window = PASS (7-9am is the worst entry
   hour of the day -- measured, not vibes).
3. **There is no lottery scanner.** By operator request there is no code path
   that flags a cheap YES. If you are reading this looking for one: that's
   the chase. Close the terminal.
4. **Expected yield is small.** Backtest: ~1 qualifying ticket/day across 10
   cities, +2.5% ROI at best gating, one boundary bust from flat. Size like
   a hobby. The nightly report's misses are the product, not an anomaly.
5. Known residual loss modes the gate cannot catch (attribution codes):
   FORECAST_BUST (DC Jul 15), BOUNDARY (settles exactly at ceiling -- the
   tenths decide), MECHANISM late arrivals. QUALIFIED flags carry a WARN
   field on the Denver-Aug-4 pace-deficit profile -- treat red flags as PASS
   unless the tape says otherwise.

## Run

```
python -m lowno.scan        # one scan, appends logs/YYYY-MM-DD.jsonl
python -m lowno.score_run   # nightly: grades flags vs CLI -> REPORT.md
```

GitHub Actions (`.github/workflows/lowno.yml`) runs the scan hourly
9a-7p ET and the scorecard nightly, committing logs + REPORT.md. Enable
Actions on the repo and it checks every hour without sleeping, without
narratives, and without a human deciding at 2:53 PM.

## v0 wiring notes
- Guidance lookup (point forecast lat/lon per station) is stubbed -> all
  forecast-class entries PASS as "unverified" until coords are added to
  config. Dead-rung scavenges work immediately. This is intentional order:
  the riskless class ships first.
- Kalshi ticker date format + cap/floor field names should be verified
  against one live response before trusting the ladder parse.
- Station quirk library (`QUIRKS`) rides along in reports.
