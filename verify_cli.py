"""STEP 2 -- confirm every station (existing + proposed) has a CLI location.

A station whose site code is absent from the CLI index can never settle: flags
accumulate as PENDING forever and silently poison the ledger. This is exactly
the failure that made cli_max return nothing for MTR/BOU/OKX -- CLI is indexed
by SITE (SFO, DEN), not by forecast office.

    python verify_cli.py                 # checks configured stations
    python verify_cli.py BOS DFW DCA SAT # also checks proposed ones
"""
import json, sys, urllib.request

UA = {"User-Agent": "lowno-probe/1.0"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as f:
        return json.loads(f.read())

def main():
    locs = get("https://api.weather.gov/products/types/CLI/locations").get("locations", {})
    print(f"CLI index holds {len(locs)} locations\n")

    try:
        sys.path.insert(0, ".")
        from lowno.config import CITIES
        configured = sorted({c["station"][1:].upper() for c in CITIES.values()})
    except Exception:
        configured = []
        print("(could not import lowno.config -- checking only args)\n")

    proposed = [a.upper() for a in sys.argv[1:]]
    bad = []
    for label, codes in (("CONFIGURED", configured), ("PROPOSED", proposed)):
        if not codes:
            continue
        print(f"--- {label} ---")
        for c in codes:
            ok = c in locs
            n = 0
            if ok:
                try:
                    n = len(get(f"https://api.weather.gov/products/types/CLI/locations/{c}")
                            .get("@graph", []))
                except Exception:
                    n = -1
            flag = "OK " if ok and n > 0 else "BAD"
            if flag == "BAD":
                bad.append(c)
            print(f"  {flag}  {c:5} in_index={ok!s:5} recent_products={n}")
        print()
    if bad:
        print("DO NOT ADD (or fix first): " + ", ".join(bad))
        print("A station without CLI products cannot settle. Flags would sit PENDING.")
    else:
        print("All checked stations can settle.")

if __name__ == "__main__":
    main()
