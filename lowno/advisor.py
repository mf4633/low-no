"""Advisor v2 -- injects the system's accumulated state into each stateless call.

The advisor is a fresh Claude call per flag: no memory across calls, no access to
the ledger, the adaptive bias layer, or the shadow findings. v1 handed it only the
flag + obs + ladder, so its expert heuristics ran without knowing what THIS system
has measured. v2 hands it three earned facts, each a direct answer to a failure the
ledger has already recorded:

  1. station_bias   -- adaptive (guide - CLI) mean + mode. Answers the SFO trap:
                       the Aug 9 bust flag had a raw guide the advisor took at face
                       value; the +5F bias would have flagged it as thin.
  2. divergence     -- model P(NO) vs market P(NO). Answers the shadow finding that
                       the market won 7/8 model-market disputes: a large divergence
                       is a RED flag, not an edge, and the advisor should weight it.
  3. bust_history   -- this station's last settled attributions. Answers narrative
                       inertia by giving the advisor the tape it can't remember.

Nothing here creates flags or overrides PASS->trade. It only enriches the context
of an advisory call that already happens. Backward compatible: if the state files
are absent (e.g. first run), the fields are omitted and behaviour equals v1.
"""
import json, os, urllib.request

MODEL = os.environ.get("LOWNO_MODEL", "claude-sonnet-4-6")
_here = os.path.dirname(__file__)


def _load(path, default):
    try:
        return json.load(open(os.path.join(_here, "..", path)))
    except Exception:
        return default


def _state_pack(flag):
    """Assemble the three earned facts for the flagged city, defensively."""
    city = flag.get("city") or flag.get("station", "")[1:]
    pack = {}

    # 1. adaptive station bias + fit mode
    summ = _load("docs/shadow_summary.json", {})
    adv = adaptive_from(adaptive_lookup(summ, city))
    if adv:
        pack["station_bias"] = adv

    # 2. model-vs-market divergence from the live edge board
    edge = _load("docs/edge.json", {})
    for c in edge.get("cities", []):
        if c.get("city") != city:
            continue
        cap = flag.get("ceiling")
        for r in c.get("rungs", []):
            if r.get("ceiling") == cap:
                d = round(r.get("p_no", 0) - r.get("p_mkt", 0), 3)
                pack["divergence"] = {
                    "model_p_no": r.get("p_no"), "market_p_no": r.get("p_mkt"),
                    "gap": d, "dist": r.get("dist"),
                    "note": ("model and market AGREE -- edge, if any, is small and real"
                             if abs(d) <= 0.15 else
                             "model-market DISAGREE >15pts -- this ledger: market won 7/8 such disputes; treat as red flag")}
                break
        break

    # 3. this station's recent settled bust attributions
    led = _load("docs/ledger.json", {})
    hist = []
    for day in led.get("days", []):
        for f in day.get("flags", []):
            if f.get("city") == city and f.get("settle") is not None:
                hist.append({"date": day["date"], "attribution": f.get("attribution"),
                             "settle": f.get("settle"), "ceiling": f["detail"].get("ceiling")})
    if hist:
        pack["bust_history"] = hist[-5:]
    return pack


def adaptive_lookup(summ, city):
    return (summ.get("adaptive") or {}).get(city)

def adaptive_from(a):
    if not a:
        return None
    return {"guide_minus_cli_meanF": a.get("bias"), "sigmaF": a.get("sigma"),
            "n_eff": a.get("n_eff"), "mode": a.get("mode"),
            "note": "add this bias to raw guide before judging pace; positive = guide runs hot"}


def advise(flag, obs_tail, ladder):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"verdict": "SKIPPED", "reasoning": "no API key configured"}
    system = open(os.path.join(_here, "..", "prompts", "advisor_system.md")).read()
    state = _state_pack(flag)
    user = ("Gate flag:\n" + json.dumps(flag, indent=1))
    if state:
        user += ("\n\nSYSTEM STATE (measured by this ledger -- weight heavily; "
                 "these answer your known failure modes):\n" + json.dumps(state, indent=1))
    user += ("\n\nLast obs (newest first):\n" + json.dumps(obs_tail[:8], indent=1) +
             "\n\nFull ladder:\n" + json.dumps(ladder, indent=1) +
             "\n\nReturn the strict JSON verdict only.")
    body = json.dumps({"model": MODEL, "max_tokens": 500, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        text = "".join(b.get("text", "") for b in resp.get("content", []))
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except urllib.error.HTTPError as e:
        # Surface the API's own error body. A bare status code sent the 2026-08-16
        # smoke test hunting; the body names the bad field directly.
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        return {"verdict": "ABSTAIN",
                "reasoning": f"advisor HTTP {e.code}: {detail}"}
    except Exception as e:
        return {"verdict": "ABSTAIN", "reasoning": f"advisor error: {str(e)[:160]}"}
