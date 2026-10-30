#!/usr/bin/env python3
# What a review must cover: the module's source, listed before the reviewer
# starts, for the review's focus. The reviewer marks every item in
# /run/src/coverage.json; the review goes on until every item is marked or
# the budget is spent, and the report says how much was covered.
#
#   inventory.py <source dir> <focus> > inventory.json
#
# Three WhisperBox reviews (2026-10-29/30) each read 16-22 of its files, a
# different sample each time, and stopped at under half the budget: every
# run found highs the one before never reached, in code all three had. A
# review that says what it covered, and covers all of it, is an audit; one
# that samples is a lottery.
import json, os, re, sys

FOCI = {
    "security": "every source file and every method the module exposes: untrusted input, crypto and keys, "
                "storage, the build and what it fetches",
    "p2p": "the network side: what it sends and receives, how peers' messages are parsed, verified, "
           "stored and synced, and what a hostile peer can do",
    "ui": "the module as a person uses it in Basecamp: every screen and feature, what the UI shows and "
          "hides, hostile input through the UI, and the methods the UI calls",
    "full": "all of the above: every source file, every exposed method, every screen",
}
SRC_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".rs", ".go", ".nim", ".py", ".js", ".mjs",
           ".cjs", ".ts", ".tsx", ".jsx", ".qml", ".sh", ".zig", ".java", ".kt", ".swift", ".sol"}
BUILD = {"CMakeLists.txt", "flake.nix", "package.json", "Cargo.toml", "go.mod", "build.gradle",
         "build.gradle.kts", "Makefile", "metadata.json"}
SKIP_DIRS = {".git", "node_modules", "third_party", "thirdparty", "3rdparty", "vendor", "external", "extern",
             "deps", "build", "dist", "out", "target", ".github", "result", "result-lgx", "android",
             "ios", "Pods", "__pycache__", ".venv", "venv"}
TEST = re.compile(r"(^|/)(tests?|spec|e2e|bench|benchmarks?|examples?|demo|docs?|scripts/test)(/|$)|(_test|\.test|\.spec|_spec)\.\w+$", re.I)
NET = re.compile(r"delivery|waku|relay|subscribe|publish|socket|libp2p|storage|http|sync|peer|catchup|rbsr|"
                 r"wire|gossip|onMessage|contentTopic|send\w*Message|receive", re.I)
UI = re.compile(r"\.(qml|jsx|tsx)$|(^|/)(ui|qml|view|views|screens?|components?)(/|$)", re.I)
INVOKABLE = re.compile(r"Q_INVOKABLE\s+[\w:<>,\s*&]+?\b(\w+)\s*\(")
# A universal-authoring module (logos-module-builder) exposes the public
# methods of its LogosModuleContext class, with no Q_INVOKABLE (WhisperBox).
CONTEXT = re.compile(r"class\s+\w+\s*:\s*public\s+LogosModuleContext\b")
PUBLIC_METHOD = re.compile(r"^\s+(?:virtual\s+|static\s+)?[\w:<>,\s*&]+?\b(\w+)\s*\([^;{]*\)\s*(?:const\s*)?(?:override\s*)?;")


def exposed(text):
    """(line, name) of every method the module exposes in this file."""
    out = []
    for i, l in enumerate(text.splitlines(), 1):
        m = INVOKABLE.search(l)
        if m:
            out.append((i, m.group(1)))
    m = CONTEXT.search(text)
    if m:
        start = text[:m.start()].count("\n") + 1
        public = True
        for i, l in enumerate(text[m.start():].splitlines(), start):
            s = l.strip()
            if s.startswith("};"):
                break
            if s in ("private:", "protected:"):
                public = False
            elif s == "public:":
                public = True
            pm = PUBLIC_METHOD.match(l)
            if public and pm and pm.group(1) not in ("operator",) and not pm.group(1).startswith("~"):
                out.append((i, pm.group(1)))
    return out


def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for f in sorted(files):
            p = os.path.join(d, f)
            if os.path.islink(p):
                continue
            yield os.path.relpath(p, root)


def lines(p):
    try:
        with open(p, errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main():
    root, focus = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "security")
    if focus not in FOCI:
        sys.exit(f"inventory: unknown focus {focus} ({', '.join(FOCI)})")
    items, methods, outside = [], [], []
    # What the module is: the folders with a metadata.json (a repository may
    # also hold a phone app, tools, a site), and the build at the top.
    roots = sorted({os.path.dirname(r) for r in walk(root) if os.path.basename(r) == "metadata.json"})
    in_module = lambda rel: not roots or "" in roots or any(rel == r or rel.startswith(r + "/") for r in roots) \
        or ("/" not in rel and os.path.basename(rel) in BUILD)
    for rel in walk(root):
        name = os.path.basename(rel)
        ext = os.path.splitext(name)[1]
        is_src, is_build = ext in SRC_EXT, name in BUILD
        if not (is_src or is_build) or TEST.search(rel) or name.endswith(".min.js"):
            continue
        p = os.path.join(root, rel)
        n = lines(p)
        if not in_module(rel):
            if n:
                outside.append(rel)
            continue
        if n == 0 or (is_src and n > 20000):     # empty, or a generated/amalgamated blob
            continue
        text = open(p, errors="replace").read() if is_src else ""
        # Every method the module exposes is a way in, whatever the focus:
        # the UI calls them, and so can any other module.
        for i, mname in exposed(text):
            methods.append({"id": f"method:{rel}:{mname}", "kind": "method", "path": rel, "line": i, "name": mname})
        net, ui = bool(NET.search(rel) or NET.search(text[:200000])), bool(UI.search(rel))
        if focus == "ui" and not (ui or is_build and name == "metadata.json"):
            continue
        if focus == "p2p" and not (net or is_build and name == "metadata.json"):
            continue
        items.append({"id": f"file:{rel}", "kind": "build" if is_build else "file", "path": rel, "lines": n})
    items += methods
    out = {"focus": focus, "scope": FOCI[focus], "items": items,
           "files": sum(1 for i in items if i["kind"] != "method"), "methods": len(methods),
           "lines": sum(i.get("lines", 0) for i in items), "module_roots": roots,
           "outside_module": outside[:200]}
    if focus in ("ui", "full"):
        out["screens"] = ("every screen and feature of the module in Basecamp: list them yourself in "
                          "coverage.json as screen:<name>, each with what you did there and a desk shot")
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
