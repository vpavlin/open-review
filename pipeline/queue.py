#!/usr/bin/env python3
# The review queue: submissions from Shrooms Agents and WhisperBox wait here,
# and one runner takes them one at a time, as the review lock demands, and
# only when the day's model budget can pay for a whole review.
#
#   queue.py add <repo-url> [<commit>] [<lgx-url>…] [--focus security|p2p|ui|full] [--from WHO] [--notify JSON]
#   queue.py list [--json]
#   queue.py run                  the runner (a user service on the review host)
#
# A job is a JSON file in ~/queue/{pending,running,done}. Its notify field
# says how to tell the submitter (an A2A message to an agent, a WhisperBox
# reply), done by notify.py when the review is queued, starts and ends.
import json, os, re, subprocess, sys, time, uuid

Q = os.path.expanduser("~/queue")
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("REVIEW_BASE", "https://or.vpavlin.xyz")
# What a review of each focus may spend (review.sh sets the same).
FOCI = {"security": 1.0, "p2p": 1.0, "ui": 1.0, "full": 1.8}
for d in ("pending", "running", "done"):
    os.makedirs(os.path.join(Q, d), exist_ok=True)

# The same shapes review.sh accepts (FR-4): checked here too, so a bad
# submission is refused at the door and told so.
URL = re.compile(r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~%+@:/-]*)?$")
COMMIT = re.compile(r"^([0-9a-f]{7,40}|HEAD)$")


def slug(repo, commit, focus):
    name = re.sub(r"\.git$", "", repo.rstrip("/").rsplit("/", 1)[-1])
    return re.sub(r"[^A-Za-z0-9._-]", "-", f"{name}-{commit[:12]}-{focus}")


def jobs(state):
    d = os.path.join(Q, state)
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            try:
                out.append(json.load(open(os.path.join(d, f))))
            except Exception:
                pass
    return sorted(out, key=lambda j: j.get("added", ""))


def save(job, state):
    for s in ("pending", "running", "done"):
        p = os.path.join(Q, s, job["id"] + ".json")
        if s != state and os.path.exists(p):
            os.unlink(p)
    p = os.path.join(Q, state, job["id"] + ".json")
    with open(p + ".tmp", "w") as f:
        json.dump(job, f, indent=1)
    os.replace(p + ".tmp", p)


def notify(job, event):
    if job.get("notify"):
        subprocess.run([sys.executable, os.path.join(HERE, "notify.py"), event,
                        os.path.join(Q, job["state"], job["id"] + ".json")], timeout=120)


def add(argv):
    who, how, focus = "unknown", None, "security"
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--from":
            who = argv[i + 1]; i += 2
        elif argv[i] == "--focus":
            focus = argv[i + 1]; i += 2
        elif argv[i] == "--notify":
            how = json.loads(argv[i + 1]); i += 2
        else:
            args.append(argv[i]); i += 1
    if not args:
        sys.exit("usage: queue.py add <repo-url> [<commit>] [<lgx-url>] [--from WHO]")
    repo = args[0]
    commit = args[1] if len(args) > 1 and args[1] else "HEAD"
    lgx = args[2:]
    if not URL.match(repo):
        sys.exit(f"refused: not a repository URL: {repo}")
    if not COMMIT.match(commit):
        sys.exit(f"refused: not a commit (7-40 hex characters, or HEAD): {commit}")
    for u in lgx:
        # Or a package the operator put on this host (review.sh: localfile:).
        if not (URL.match(u) or re.match(r"^localfile:[A-Za-z0-9._-]+\.lgx$", u)):
            sys.exit(f"refused: not a package URL: {u}")
    if focus not in FOCI:
        sys.exit(f"refused: not a focus: {focus} ({', '.join(FOCI)})")
    for state in ("pending", "running"):
        for j in jobs(state):
            if j["repo"] == repo and j["commit"] == commit and j.get("focus", "security") == focus:
                print(f"already {state}: {j['id']}, {BASE}/{j['slug']}/live.html")
                return
    s = slug(repo, commit, focus)
    job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "repo": repo, "commit": commit,
           "lgx": lgx, "focus": focus, "from": who, "notify": how, "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "state": "pending", "slug": s, "live": f"{BASE}/{s}/live.html", "report": f"{BASE}/{s}/"}
    save(job, "pending")
    pos = len(jobs("pending")) + len(jobs("running"))
    print(f"queued #{pos}: {repo} @ {commit}\nlive while it runs: {job['live']}\nreport when done: {job['report']}")
    notify(job, "queued")


def show(argv):
    out = {s: jobs(s) for s in ("running", "pending")}
    out["done"] = jobs("done")[-10:]
    if "--json" in argv:
        print(json.dumps(out, indent=1)); return
    for s in ("running", "pending", "done"):
        for n, j in enumerate(out[s], 1):
            extra = j.get("waiting", "") if s != "done" else j.get("result", "")
            print(f"{s:8} {n:2}. {j['repo']} @ {j['commit'][:12]} [{j.get('focus','security')}]  from {j.get('from','?')}  {extra}")


def balance():
    out = "/tmp/queue-balance.json"
    env = dict(os.environ)
    try:
        env["VENICE_INFERENCE_KEY"] = re.search(r"VENICE_INFERENCE_KEY=(.*)",
                                                open(os.path.expanduser("~/.pi/agent/.env")).read()).group(1).strip()
        subprocess.run([sys.executable, os.path.join(HERE, "balance.py"), out], env=env, timeout=60)
        return json.load(open(out))
    except Exception as e:
        return {"error": str(e)}


def run():
    while True:
        # A job left running when the runner stopped goes back to the front.
        for j in jobs("running"):
            j["state"] = "pending"; save(j, "pending")
        pending = jobs("pending")
        if not pending:
            time.sleep(30); continue
        job = pending[0]
        b = balance()
        diem = (b.get("balances") or {}).get("DIEM")
        need = FOCI.get(job.get("focus", "security"), 1.0)
        if diem is None or diem < need + 0.05:
            # Not enough for a whole review: wait for the day's allowance.
            job["waiting"] = (f"waiting for the model budget ({diem:.2f} DIEM left, a {job.get('focus','security')} review needs {need:.2f}; "
                              f"it refills {b.get('next_epoch','at 00:00 UTC')})" if diem is not None
                              else f"waiting: the budget can't be read ({b.get('error','')})")
            save(job, "pending")
            time.sleep(600); continue
        job.pop("waiting", None)
        job["state"], job["started"] = "running", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(job, "running")
        notify(job, "started")
        l = job.get("lgx") or []
        args = [job["repo"], job["commit"]] + ([l] if isinstance(l, str) else l)
        with open(os.path.expanduser(f"~/runs-{job['slug']}.log"), "w") as log:
            env = dict(os.environ, REVIEW_FOCUS=job.get("focus", "security"))
            rc = subprocess.run(["bash", os.path.join(HERE, "review.sh")] + args, stdout=log, stderr=subprocess.STDOUT,
                                env=env).returncode
        try:
            r = json.load(open(f"/srv/reviews/{job['slug']}/review.json"))
            job["result"] = r.get("pill", "")
            job["counts"] = r.get("counts", {})
            job["cost"] = r.get("cost", "")
        except Exception:
            job["result"] = f"no result (review.sh exit {rc})"
        job["state"], job["finished"] = "done", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(job, "done")
        notify(job, "done")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "add":
        add(sys.argv[2:])
    elif cmd == "list":
        show(sys.argv[2:])
    elif cmd == "run":
        run()
    else:
        sys.exit(__doc__ if False else "usage: queue.py add|list|run")
