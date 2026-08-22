"""STEP 8 -- front-end panels: live flag tracker, advisor spend, system health.

Adds three sections to docs/index.html, all fed by JSON the other steps write.
Everything is read-only and client-side; no credential is fetched, because
docs/ is a public Pages site.

  1. LIVE TODAY   -- from docs/active.json. For each tracked rung: the ceiling,
     the running max, the gap left to clear, the empirical projected max range
     (q10/q50/q90), P(exceed) empirical, and whether the station is past its
     measured convergence hour. This is the panel to look at DURING the day.

  2. ADVISOR SPEND -- from docs/spend.json. Calls made, estimated cost, estimated
     remaining, calls left at current rate. Labelled ESTIMATE, with the reason.

  3. SYSTEM HEALTH -- staleness of each feed, so a silently dead pipeline shows
     up as a red row rather than a stale-but-plausible page. Extends the existing
     ledger-vs-summary banner to every file.

Apply from repo root:  python frontend_panels.patch.py
"""
import os
import sys

JS = r"""
/* ---- LIVE TODAY ---------------------------------------------------- */
fetch("active.json?cb="+Date.now()).then(r=>r.ok?r.json():null).then(a=>{
  const box=document.getElementById("livebox"); if(!box||!a||!a.tracked) return;
  if(!a.tracked.length){
    box.innerHTML=`<h2>LIVE TODAY</h2><p>No rung is flagged or near-flagging
      right now. The scanner runs hourly 09:05&ndash;19:05 ET.</p>`;
    return;
  }
  const rows=a.tracked.map(t=>{
    const proj=t.projected_max
      ? `${t.projected_max.q10}&ndash;${t.projected_max.q90} <span class="muted">(med ${t.projected_max.q50})</span>`
      : "&mdash;";
    const cleared=t.already_cleared;
    const cls=t.qualified?(cleared?"WIN":"PENDING"):"";
    return `<tr>
      <td>${t.city}</td>
      <td class="num">&le;${t.ceiling}</td>
      <td class="num">${t.run_max!=null?t.run_max.toFixed(1):"&mdash;"}</td>
      <td class="num ${cleared?"code WIN":""}">${cleared?"CLEARED":t.gap_to_clear+"&deg;F"}</td>
      <td class="num">${proj}</td>
      <td class="num">${t.p_exceed_empirical!=null?(100*t.p_exceed_empirical).toFixed(0)+"%":"&mdash;"}
          <span class="muted small">${t.emp_n?("n="+t.emp_n):""}</span></td>
      <td class="num">${t.no_ask!=null?t.no_ask:"&mdash;"}</td>
      <td class="code ${cls}">${t.qualified?t.verdict:"near-miss"}</td>
      <td class="muted small">${t.past_convergence?"decided":"open"}${t.convergence_hour!=null?" ("+String(t.convergence_hour).padStart(2,"0")+":00)":""}</td>
    </tr>`;}).join("");
  box.innerHTML=`<h2>LIVE TODAY</h2>
    <p>Rungs flagged or within 2&deg;F of flagging, updated each hourly scan
    (${a.at}). <b>Gap</b> is how much further the day must climb to clear the
    ceiling &mdash; this NO position pays only if the max <b>exceeds</b> it.
    <b>Projected</b> is the empirical remaining-climb range at this station and
    local hour added to the running max: q10&ndash;q90, a range rather than a
    false point estimate. <b>Decided</b> means the station is past its measured
    convergence hour.</p>
    <table><tr><th>city</th><th>rung</th><th>run max</th><th>gap</th>
    <th>projected max</th><th>P(exceed)</th><th>NO ask</th><th>state</th>
    <th>day</th></tr>${rows}</table>`;
});

/* ---- ADVISOR SPEND -------------------------------------------------- */
fetch("spend.json?cb="+Date.now()).then(r=>r.ok?r.json():null).then(s=>{
  const box=document.getElementById("spendbox"); if(!box||!s) return;
  const pct=Math.max(0,Math.min(100,100*s.estimated_remaining/s.starting_credit));
  box.innerHTML=`<h2>ADVISOR SPEND &mdash; ESTIMATE</h2>
   <p>Anthropic publishes no balance endpoint, and an admin key must never reach
   a public page, so this is computed from actual call counts at published rates.
   It matched the console exactly on the first 12 calls ($0.06).
   Verify at console.anthropic.com/settings/billing.</p>
   <table>
     <tr><th>calls made</th><td class="num">${s.calls_total}</td></tr>
     <tr><th>calls skipped (no key)</th><td class="num">${s.calls_skipped_no_key}</td></tr>
     <tr><th>cost per call</th><td class="num">$${s.cost_per_call.toFixed(5)}</td></tr>
     <tr><th>estimated spent</th><td class="num">$${s.estimated_spent_since_credit.toFixed(4)}</td></tr>
     <tr><th>estimated remaining</th><td class="num"><strong>$${s.estimated_remaining.toFixed(2)}</strong></td></tr>
     <tr><th>calls left at this rate</th><td class="num">${s.calls_remaining}</td></tr>
   </table>
   <div style="height:8px;background:#2A3158;margin-top:10px">
     <div style="height:8px;width:${pct.toFixed(1)}%;background:#E8A24B"></div></div>`;
});

/* ---- SYSTEM HEALTH -------------------------------------------------- */
(function(){
  const feeds=[["ledger.json","nightly grade"],["shadow_summary.json","shadow + variants"],
                ["edge.json","hourly edge board"],["active.json","live tracker"],
                ["spend.json","advisor spend"]];
  Promise.all(feeds.map(([f,label])=>
    fetch(f+"?cb="+Date.now()).then(r=>r.ok?r.json():null)
      .then(j=>({f,label,at:(j&&(j.generated||j.at))||null})).catch(()=>({f,label,at:null}))
  )).then(res=>{
    const box=document.getElementById("healthbox"); if(!box) return;
    const now=Date.now();
    const rows=res.map(r=>{
      if(!r.at) return `<tr><td>${r.label}</td><td class="muted">${r.f}</td>
        <td class="code PENDING">MISSING</td><td class="num">&mdash;</td></tr>`;
      const age=(now-new Date(r.at).getTime())/3.6e6;
      const limit=r.f==="edge.json"||r.f==="active.json"?3:26;
      const bad=age>limit;
      return `<tr><td>${r.label}</td><td class="muted">${r.f}</td>
        <td class="code ${bad?"FORECAST_BUST":"WIN"}">${bad?"STALE":"ok"}</td>
        <td class="num">${age.toFixed(1)}h</td></tr>`;}).join("");
    box.innerHTML=`<h2>SYSTEM HEALTH</h2>
      <p>Age of each published feed. Hourly feeds go stale after 3h, nightly
      after 26h. A dead pipeline that still serves a plausible-looking page is
      the failure this table exists to catch &mdash; it happened once already.</p>
      <table><tr><th>feed</th><th>file</th><th>state</th><th>age</th></tr>${rows}</table>`;
  });
})();
"""

CONTAINERS = ('<div id="livebox"></div>\n<div id="edgebox"></div>'
              '\n<div id="scorebox"></div>\n<div id="spendbox"></div>'
              '\n<div id="healthbox"></div>')


def main():
    p = "docs/index.html"
    if not os.path.exists(p):
        print("run from repo root (docs/index.html not found)")
        sys.exit(1)
    s = open(p).read()

    if "livebox" in s:
        print("panels already present -- nothing to do")
        return

    # containers: live goes ABOVE the edge board (it is the during-the-day view)
    if '<div id="edgebox"></div>' in s:
        s = s.replace('<div id="edgebox"></div>', CONTAINERS, 1)
    else:
        print("WARNING: edgebox anchor missing; appending containers to body")
        s = s.replace("</body>", CONTAINERS + "\n</body>", 1)

    s = s.replace("</script>", JS + "\n</script>", 1)
    open(p, "w").write(s)
    print("added live tracker, spend, and health panels to docs/index.html")
    print("""
ORDER ON PAGE
  LIVE TODAY -> edge board -> shadow bands -> forecaster scoreboard ->
  spend -> system health. During the day you want the first one; the rest is
  post-mortem.

VERIFY
  Open the page and confirm five new panels render. Missing JSON files show as
  MISSING in SYSTEM HEALTH rather than breaking the page -- that is intended,
  since active.json and spend.json only appear after steps 6 and 7 run once.
""")


if __name__ == "__main__":
    main()
