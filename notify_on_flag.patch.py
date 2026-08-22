"""STEP 5 -- notify on QUALIFIED flags via a GitHub Issue.

Problem this solves: there is currently NO notification path. A flag fires
during an hourly scan (e.g. 17:57Z), commits to the repo, renders on the site --
and nothing tells you. All six flags to date were discovered after the fact. If
these ever become real trades, the entry window closes while you're unaware.

Why GitHub Issues rather than email/Pushover: no new account, no new secret, and
the GitHub mobile app already pushes issue notifications to your phone. Uses the
per-run GITHUB_TOKEN, which dies with the job.

Design notes:
  * Fires ONLY on QUALIFIED (and DEAD_SCAVENGE) -- not on every scan.
  * De-duplicates by ticker: the same rung flags on multiple cycles as price
    decays (SFO flagged 3x on 2026-08-09). One issue per ticker per day.
  * Body carries the numbers you'd need to decide: price, G, PoP, run_max,
    depth, model p, advisor verdict, and the size the 5% cap allows.
  * Labels the issue `flag` so you can filter, and closes nothing -- you close
    it yourself once you've looked.

Apply from repo root:  python notify_on_flag.patch.py
"""
import json, os, sys

NOTIFIER = '''"""Open a GitHub Issue for each QUALIFIED flag. Called by scan.py.

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
'''

SCAN_OLD = '''            if depth is not None and isinstance(detail, dict):
                detail["depth"] = depth'''

SCAN_NEW = '''            if depth is not None and isinstance(detail, dict):
                detail["depth"] = depth'''

CALL_ANCHOR = '''    os.makedirs("logs", exist_ok=True)'''

CALL_NEW = '''    # Notify on qualifying flags. Best-effort: a notification failure must never
    # break a scan or lose data, so this is wrapped and logged, not raised.
    try:
        from . import notify
        for _r in results:
            if _r.get("verdict") in ("QUALIFIED", "DEAD_SCAVENGE"):
                notify.notify_flag(_r.get("city"), _r["verdict"],
                                   _r.get("detail") or {}, _r.get("advisor"))
    except Exception as _e:
        print("notify: skipped -", str(_e)[:120])

    os.makedirs("logs", exist_ok=True)'''

WF_OLD = '''      - name: hourly scan
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python -m lowno.scan'''

WF_NEW = '''      - name: hourly scan
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python -m lowno.scan'''


def main():
    if not os.path.isdir("lowno"):
        print("run this from the repo root (lowno/ not found)")
        sys.exit(1)

    # 1. write the notifier module
    if os.path.exists("lowno/notify.py"):
        print("lowno/notify.py already exists -- leaving it alone")
    else:
        open("lowno/notify.py", "w").write(NOTIFIER)
        print("wrote lowno/notify.py")

    # 2. hook it into scan.py
    s = open("lowno/scan.py").read()
    if "from . import notify" in s:
        print("scan.py already hooked")
    elif CALL_ANCHOR in s:
        s = s.replace(CALL_ANCHOR, CALL_NEW, 1)
        open("lowno/scan.py", "w").write(s)
        print("hooked notify into lowno/scan.py")
    else:
        print("WARNING: anchor not found in scan.py. Add this before the logs")
        print("directory is created in scan_once():")
        print(CALL_NEW)

    # 3. grant the workflow issue-write + pass the token through
    wf = ".github/workflows/lowno.yml"
    w = open(wf).read()
    changed = False
    if "issues: write" not in w:
        w = w.replace("permissions: { contents: write, pages: write }",
                      "permissions: { contents: write, pages: write, issues: write }", 1)
        changed = True
    if "GITHUB_REPOSITORY: ${{ github.repository }}" not in w and WF_OLD in w:
        w = w.replace(WF_OLD, WF_NEW, 1)
        changed = True
    if changed:
        open(wf, "w").write(w)
        print(f"updated {wf} (issues: write + token env)")
    else:
        print(f"{wf} already configured (or anchors differ -- check by hand)")

    print("""
VERIFY BEFORE PUSHING
  python -c "import ast;[ast.parse(open(f).read()) for f in ['lowno/notify.py','lowno/scan.py']]"
  python -c "import yaml;yaml.safe_load(open('.github/workflows/lowno.yml'))"

TEST WITHOUT WAITING FOR A REAL FLAG
  Temporarily lower GATE['min_g_deg'] in lowno/config.py to 0.5, dispatch one
  scan, confirm an issue opens, then PUT IT BACK. The gate is frozen for the
  test window -- a permanent change would invalidate the measurement.

TURN ON PHONE PUSH
  GitHub mobile app -> Settings -> Notifications -> enable for this repository.
  Issues you are not subscribed to won't push, so either watch the repo or add
  yourself as assignee in the payload above.
""")


if __name__ == "__main__":
    main()
