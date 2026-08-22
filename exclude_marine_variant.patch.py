"""STEP 3 -- add an `exclude_marine` scored variant to shadow_run.py.

Motivation, from the ledger as of 2026-08-19: six flags, 4-2. EVERY loss is SFO,
both FORECAST_BUST (guidance hot, marine layer capped it). Continental stations
are 3-0. The edge board ALREADY refuses to size SFO (`dist: marine/unfit`,
half-Kelly LCB forced to 0) -- but the GATE has no station exclusion, so the
system keeps flagging the one station its own model won't touch.

This does NOT change the frozen gate. It adds a nightly-scored variant so the
question is measured rather than argued. Note the real cost: SFO produced HALF
the flags. Excluding it improves the record and halves the sample rate, pushing
promotion later. That tradeoff is the point of scoring it instead of assuming.

Apply:  python exclude_marine_variant.patch.py    (from repo root)
"""
import io, sys

MARKER = "exclude_marine"
TARGET = "shadow_run.py"

OLD = '''        score_rule("frozen_G4",            lambda o: o["G"] >= 4),'''
NEW = '''        score_rule("frozen_G4",            lambda o: o["G"] >= 4),
        # Marine-layer stations are bimodal (burn-off vs. cap); a Gaussian cannot
        # price them and prob.py already zeroes their size. As of 2026-08-19 every
        # loss in the ledger is SFO. Scored, not enforced -- SFO is also half the
        # flag supply, so exclusion trades accuracy for sample rate.
        score_rule("exclude_marine",       lambda o: o["G"] >= 4 and o["city"] not in MARINE_CITIES),
        score_rule("floor96_ex_marine",    lambda o: 96 <= o["price"] <= 98 and o["city"] not in MARINE_CITIES),'''

CONST = '''MARINE_CITIES = {"SFO", "LAX"}   # keep in sync with lowno.prob.MARINE

'''

def main():
    src = open(TARGET).read()
    if MARKER in src:
        print("already applied; nothing to do")
        return
    if OLD not in src:
        print("ERROR: anchor not found in shadow_run.py -- apply by hand.")
        print("Add these two lines to the `variants = [` list:")
        print(NEW)
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    # insert the constant after the imports
    lines = src.split("\n")
    for i, l in enumerate(lines):
        if l.startswith("from lowno") or l.startswith("import "):
            last_import = i
    lines.insert(last_import + 1, "\n" + CONST.rstrip())
    open(TARGET, "w").write("\n".join(lines))
    print("patched shadow_run.py -- added exclude_marine + floor96_ex_marine variants")
    print("verify with: python -c \"import ast;ast.parse(open('shadow_run.py').read())\"")
    print("then run:    python shadow_run.py")

if __name__ == "__main__":
    main()
