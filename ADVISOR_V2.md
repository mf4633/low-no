# Advisor v2 -- state-injecting advisory layer (2026-08-11)

## What changed
v1 handed the Claude advisory call only {flag, obs_tail, ladder}. The call is
stateless -- fresh Claude per flag, no memory, no access to the ledger. So the
advisor's expert heuristics ran BLIND to what this system has measured.

v2 injects three earned facts into each call, each answering a recorded failure:

| Injected fact | Source | Failure it answers |
|---|---|---|
| `station_bias` (guide-CLI mean, sigma, mode) | docs/shadow_summary.json adaptive | SFO Aug 9 bust: raw guide 81 taken at face value; +4.8F bias makes it a boundary flag |
| `divergence` (model P(NO) vs market P(NO)) | docs/edge.json | shadow finding: market won 7/8 model-market disputes -- big gap = red flag, not edge |
| `bust_history` (station's last 5 settled attributions) | docs/ledger.json | narrative inertia: gives the stateless call the tape it can't remember |

Backward compatible: if a state file is missing, that field is omitted and
behaviour equals v1. Never creates flags, never turns PASS into a trade.

## Before/after (real graded flag, SFO 2026-08-09, ceil 76 @ 5c)
- v1 advisor saw: guide 81, run_max 64.4, PoP 0 -> looks like comfortable NO room
- v2 advisor also sees: station_bias +4.8F (guide runs hot) -> corrected guide ~76
  against a 76 ceiling = boundary coin-flip, not comfortable. The bias is exactly
  the fact whose absence let the bust flag look tradeable.

## Measurement boundary
Ledger now stamps `advisor_version: 2`, `advisor_v2_since: 2026-08-11`. Flags
before this date were judged blind (v1); on/after, state-fed (v2). Do not pool
advisor-concur statistics across the line -- they are two experiments. The v2
promotion clock starts 2026-08-11.

## Paper only. Frozen gate unchanged. This edits only what the advisor SEES.
