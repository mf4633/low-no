"""Open a GitHub Issue for each QUALIFIED flag. Called by scan.py.

No-ops silently when GITHUB_TOKEN is absent (local runs) so nothing breaks
outside Actions. Dedupes by ticker+date against open issues.
"""
import json, os, urllib.request, urllib.error


def _api(path, method="GET", payload=None):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    url = f"https://api.github.com/repos/{repo}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "lowno-notify"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")
    except Exception as e:
        print("notify: api error", str(e)[:120])
        return None


def _already_open(ticker):
    got = _api("/issues?state=open&labels=flag&per_page=100")
    if not got:
        return False
    return any(ticker in (i.get("title") or "") for i in got)


def notify_flag(city, verdict, detail, advisor=None):
    ticker = detail.get("ticker") or f"{city}-{detail.get('ceiling')}"
    if _already_open(ticker):
        print(f"notify: issue already open for {ticker}")
        return
    d = detail
    size = (d.get("size") or {})
    model = (d.get("model") or {})
    depth = (d.get("depth") or {})
    adv = advisor or {}
    price = d.get("no_ask")
    title = f"{verdict}: {city} <={d.get('ceiling')} @ {price} ({ticker})"
    body = f"""**PAPER ONLY -- no order has been placed.**

| field | value |
|---|---|
| station | {city} |
| rung | <= {d.get('ceiling')} F |
| NO ask | {price} |
| G (guide - ceiling) | {d.get('G')} |
| guide | {d.get('guide')} |
| PoP | {d.get('pop')} |
| running max at flag | {d.get('run_max')} |
| net cents after fee | {d.get('net_cents')} |
| depth <=98c | {depth.get('depth_le_max')} contracts (${depth.get('notional_le_max')}) |
| depth at best | {depth.get('depth_at_best')} |
| model P(exceed cap) | {model.get('p_exceed_cap')} ({model.get('p_source')}) |
| empirical P | {model.get('p_empirical')} (n={model.get('emp_n')}) |
| advisor | {adv.get('verdict')} p={adv.get('p_exceed')} |
| size cap | {size.get('max_position_frac')} of bankroll |

**Reminder of the win condition:** this NO position pays only if the daily
maximum **EXCEEDS** {d.get('ceiling')} F. It is not a bet that temperatures stay low.

{('**WARN:** ' + d.get('WARN')) if d.get('WARN') else ''}

Advisor reasoning:
> {str(adv.get('reasoning') or 'n/a')[:600]}

Ledger context as of 2026-08-20: 6 flags, 4W-2L. Every loss has been SFO
(FORECAST_BUST). Real-money equivalent would be -9.0% under the 5% cap.
Nothing is proven; no band's Wilson LCB clears its fee breakeven.
"""
    out = _api("/issues", "POST", {"title": title, "body": body, "labels": ["flag"]})
    if out:
        print(f"notify: opened issue #{out.get('number')} for {ticker}")
