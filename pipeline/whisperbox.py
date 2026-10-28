#!/usr/bin/env python3
# Community submissions through WhisperBox. A headless whisperbox_core (0.5.0,
# signed answers) runs under logosctl as a co-owner of the submission form:
# this reads the decrypted answers, queues the valid ones, sends a receipt,
# and replies privately to each submitter (queued, then the report).
# Recipe and form: atlas/whisperbox, 2026-10-28 (host/whisperbox-bot.md).
#
#   whisperbox.py identity              the bot's pubHex, for the form's addCoOwner
#   whisperbox.py join <share-link>     follow the form (once)
#   whisperbox.py poll                  read new answers every minute (a user service)
#   whisperbox.py reply <form> <confirmationId> <text>   (notify.py uses it)
import json, os, re, subprocess, sys, time

W = os.path.expanduser("~/wb-bot")
STATE = os.path.join(W, "state")
CONF = os.path.join(W, "config.json")
SEEN = os.path.join(W, "seen.json")
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, HOME=os.path.join(STATE, "home"),
           WHISPERBOX_CORE_DATA=os.path.join(STATE, "home", ".whisperbox-core"),
           LOGOSCTL_CONFIG_DIR=os.path.join(STATE, "cfg"), QT_QPA_PLATFORM="offscreen")

# Stricter than queue.py for the public: a known forge and a full commit.
REPO = re.compile(r"^https://(github\.com|gitlab\.com|codeberg\.org)/[\w.-]+/[\w.-]+/?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
LGX = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~%+@:/-]*\.lgx$")
PER_SUBMITTER = 3      # reviews waiting per signed submitter
UNSIGNED_TOTAL = 3     # and in all from unsigned (0.4.2) answers, whose sender is unknown


def call(method, *args, timeout=60):
    """A whisperbox_core method; every argument as a string (a bare 1 or true
    arrives as a number or a bool), the double-encoded result decoded."""
    out = subprocess.run(["logosctl", "call", "whisperbox_core", method, *[f"str:{a}" for a in args], "-j"],
                         env=ENV, capture_output=True, text=True, timeout=timeout).stdout.strip().splitlines()
    if not out:
        return None
    r = json.loads(out[-1]).get("result")
    try:
        return json.loads(r) if isinstance(r, str) else r
    except ValueError:
        return r


def conf():
    try:
        return json.load(open(CONF))
    except (OSError, ValueError):
        return {}


def seen():
    try:
        return json.load(open(SEEN))
    except (OSError, ValueError):
        return {}


def save_seen(s):
    with open(SEEN + ".tmp", "w") as f:
        json.dump(s, f, indent=1)
    os.replace(SEEN + ".tmp", SEEN)


def queue_counts():
    out = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "queue.py"), "list", "--json"],
                                    capture_output=True, text=True).stdout or "{}")
    waiting = (out.get("pending") or []) + (out.get("running") or [])
    return waiting


def check(answers):
    a = {x.get("questionId"): str(x.get("value", "")).strip() for x in answers if isinstance(x, dict)}
    repo, commit, lgx = a.get("repo", ""), a.get("commit", "").lower(), a.get("lgx", "")
    if not REPO.match(repo):
        return None, "the repository must be https://github.com/, gitlab.com/ or codeberg.org/ owner/name"
    if not COMMIT.match(commit):
        return None, "the commit must be the full 40-character SHA"
    if lgx and not LGX.match(lgx):
        return None, "the package must be an https URL ending in .lgx"
    return (repo.rstrip("/"), commit, lgx), None


def poll():
    while True:
        c = conf()
        if not c.get("form"):
            time.sleep(60); continue
        form = c["form"]
        try:
            got = call("getDecryptedResponses", form) or {}
        except Exception as e:
            print(f"read failed: {e}", file=sys.stderr); time.sleep(60); continue
        s = seen()
        for r in got.get("responses", []):
            cid = r.get("confirmationId")
            if not cid or cid in s:
                continue
            who = r.get("respondent", "") if r.get("verified") else "unsigned"
            sub, why = check(r.get("answers") or [])
            if sub:
                waiting = queue_counts()
                mine = [j for j in waiting if j.get("from") == f"whisperbox:{who}"]
                if len(mine) >= (UNSIGNED_TOTAL if who == "unsigned" else PER_SUBMITTER):
                    sub, why = None, ("too many reviews already waiting from unsigned answers; try again later, "
                                      "or answer from WhisperBox 0.5.0" if who == "unsigned"
                                      else f"you already have {len(mine)} reviews waiting")
            if sub:
                repo, commit, lgx = sub
                notify = json.dumps({"kind": "whisperbox", "form": form, "confirmation": cid})
                res = subprocess.run([sys.executable, os.path.join(HERE, "queue.py"), "add", repo, commit]
                                     + ([lgx] if lgx else []) + ["--from", f"whisperbox:{who}", "--notify", notify],
                                     capture_output=True, text=True)
                s[cid] = {"at": time.time(), "result": (res.stdout or res.stderr).strip()[:300]}
                if res.returncode == 0 and r.get("respondent"):
                    try: call("confirmResponse", form, r["respondent"])   # the receipt, once it's valid
                    except Exception: pass
                if res.returncode != 0:
                    reply(form, cid, f"Not queued: {(res.stderr or res.stdout).strip()[:200]}")
            else:
                s[cid] = {"at": time.time(), "result": f"refused: {why}"}
                reply(form, cid, f"Not queued: {why}.")
            save_seen(s)
        time.sleep(60)


def reply(form, cid, text):
    try:
        call("replyToResponse", form, cid, text[:900])
    except Exception as e:
        print(f"reply failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "identity":
        snap = call("snapshot") or {}
        ident = snap.get("identity") or {}
        print(json.dumps({"pubHex": ident.get("pubHex"), "address": ident.get("address"),
                          "nodeReady": snap.get("nodeReady")}, indent=1))
    elif cmd == "join":
        link = sys.argv[2]
        m = re.search(r"[?&]id=([^&]+)", link)
        print(call("joinForm", link))
        c = conf(); c.update({"share": link, "form": m.group(1) if m else c.get("form")})
        json.dump(c, open(CONF, "w"), indent=1)
    elif cmd == "poll":
        poll()
    elif cmd == "reply":
        reply(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        sys.exit("usage: whisperbox.py identity | join <share-link> | poll | reply <form> <cid> <text>")
