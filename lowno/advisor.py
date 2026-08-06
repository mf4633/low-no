"""Optional Claude advisory layer. ADVISES flags; never creates them, never
overrides a PASS into a trade. Runs only when ANTHROPIC_API_KEY is set.
Costs: one small request per flagged city-hour (pennies/day at ~1 flag/day)."""
import json, os, urllib.request

MODEL = os.environ.get("LOWNO_MODEL", "claude-sonnet-4-6")

def advise(flag, obs_tail, ladder):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"verdict": "SKIPPED", "reasoning": "no API key configured"}
    system = open(os.path.join(os.path.dirname(__file__), "..", "prompts",
                               "advisor_system.md")).read()
    user = ("Gate flag:\n" + json.dumps(flag, indent=1) +
            "\n\nLast obs (newest first):\n" + json.dumps(obs_tail[:8], indent=1) +
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
    except Exception as e:
        return {"verdict": "ABSTAIN", "reasoning": f"advisor error: {str(e)[:120]}"}
