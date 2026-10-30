#!/usr/bin/env python3
# How much of the review's inventory (inventory.py) the reviewer has covered,
# from its /run/src/coverage.json. Used by the reviewer (desk coverage), by
# the loop that sends it back to what is left (review-loop.sh), and by the
# report.
#
#   coverage.py <inventory.json> <coverage.json> [--missing N] [--json]
#
# coverage.json: {"<item id>": {"status": "checked|finding|not-applicable|not-reached",
#                               "read": "1-420,421-980", "note": "...", "findings": ["FR-2"]}, ...}
# An item counts as covered when its status is checked, finding or
# not-applicable with a note that says something, a finding names its FR ids,
# and a file over 300 lines has "read" ranges over 90% of it. A file marked
# checked from a glance at its first screen is not an audit of it.
import json, re, sys

DONE = {"checked", "finding", "not-applicable"}


def span(ranges, total):
    seen = set()
    for a, b in re.findall(r"(\d+)\s*[-–]\s*(\d+)", str(ranges or "")):
        a, b = int(a), min(int(b), total)
        seen.update(range(a, b + 1))
    return len(seen)


def judge(item, entry):
    """'' when covered, else why not."""
    if not isinstance(entry, dict):
        return "not marked"
    st = entry.get("status")
    if st not in DONE:
        return "not reached" if st == "not-reached" else f"status {st!r}"
    if len(str(entry.get("note", "")).strip()) < 25:
        return "no note on what was checked"
    if st == "finding" and not entry.get("findings"):
        return "finding without FR ids"
    n = item.get("lines", 0)
    if item["kind"] == "file" and n > 300 and st != "not-applicable":
        got = span(entry.get("read"), n)
        if got < 0.9 * n:
            return f"read {got} of {n} lines"
    return ""


def summary(inv, cov):
    items = inv.get("items", [])
    rows = [(i, judge(i, cov.get(i["id"]))) for i in items]
    done = [i for i, why in rows if not why]
    lines_all = sum(i.get("lines", 0) for i in items) or 1
    lines_done = sum(i.get("lines", 0) for i in done)
    screens = sorted(k for k, v in cov.items() if k.startswith("screen:") and isinstance(v, dict)
                     and v.get("status") in DONE)
    findings = sorted({f for v in cov.values() if isinstance(v, dict) for f in (v.get("findings") or [])})
    return {"focus": inv.get("focus"), "items": len(items), "covered": len(done),
            "pct": round(100 * len(done) / max(len(items), 1)), "lines_pct": round(100 * lines_done / lines_all),
            "screens": screens, "findings_linked": findings,
            "missing": [{"id": i["id"], "why": why, "lines": i.get("lines")} for i, why in rows if why]}


def main():
    inv = json.load(open(sys.argv[1]))
    try:
        cov = json.load(open(sys.argv[2]))
        if not isinstance(cov, dict):
            cov = {}
    except (OSError, ValueError):
        cov = {}
    s = summary(inv, cov)
    if "--json" in sys.argv:
        json.dump(s, sys.stdout, indent=1); return
    n = int(sys.argv[sys.argv.index("--missing") + 1]) if "--missing" in sys.argv else 15
    print(f"[coverage] {s['covered']} of {s['items']} items ({s['pct']}%), {s['lines_pct']}% of the lines; "
          f"{len(s['screens'])} screens")
    for m in s["missing"][:n]:
        print(f"  - {m['id']}: {m['why']}")
    if len(s["missing"]) > n:
        print(f"  … and {len(s['missing']) - n} more")


if __name__ == "__main__":
    main()
