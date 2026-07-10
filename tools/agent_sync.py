#!/usr/bin/env python3
r"""agent_sync.py -- lightweight multi-agent coordination over git worktrees.

Lets several Claude Code sessions work on ONE project WITHOUT clobbering each
other's files or racing the single FreeCAD tab / build. Solo work needs none of
this -- it only kicks in when you deliberately add a second agent.

ROLES
  LEAD         the primary session. Works in the MAIN worktree on `main`. OWNS
               the build + the FreeCAD tab. Pulls in contributors' branches.
  CONTRIBUTOR  an added session. Works in its OWN git worktree on branch
               `agent/<name>` -- a SEPARATE directory, so its edits never touch
               the lead's files. It NEVER builds the shared tab; it files a
               MERGE REQUEST and the lead integrates + builds.

Only the lead ever writes assembly.step / calls show(), so there is exactly one
FreeCAD tab and one build at a time. Contributors verify with `check_overlaps`
(which never writes the assembly or opens the viewer) or ask the lead to build.

Coordination state lives in  <git-common-dir>/agent-sync/  -- inside .git, so it
is shared by every worktree and never committed:
    inbox/<branch>.json   one pending merge request per contributor branch
    build.lock            single-build mutex (auto-stolen if stale)

COMMANDS
  Contributor:
    join <name>          create + print a worktree on agent/<name> (off main)
    submit "<summary>"   commit this branch, then file a merge request
    sync                 merge the latest main into this branch (pick up merges)
    done                 (after all merged) remove this worktree
  Lead:
    inbox                list pending merge requests
    wait                 BLOCK until a request arrives, then print it (run in the BACKGROUND)
    take <name>          merge agent/<name> into the current branch
    drop <name>          discard a merge request without merging
    build [args...]      run `src.build` under the single-build lock
  Either:
    status               role, branch, worktrees, pending requests

HANDS-FREE NOTIFICATION (no human relay). The lead arms `wait` as a BACKGROUND
command; the cheap shell poll (not the model) sits idle until a contributor's
`submit` drops a request file, then exits -- which auto re-invokes the lead. The
lead then `take`s + `build`s and re-arms `wait`. The contributor never has to ping
anyone; writing the request IS the notification.

Typical flow
  human: "let's go multi-agent; the pedal-bar chat is a sub-agent named pedal"
  lead (once):  py -3.12 ../freecad/agent_sync.py wait      # <-- in the BACKGROUND; re-arm after each take
  contributor:  py -3.12 ../freecad/agent_sync.py join pedal   # -> cd the printed dir
                ...edit, then...
                py -3.12 ../freecad/agent_sync.py submit "pedal bar latch v2"   # ends the lead's wait
  lead (auto-woken): py -3.12 ../freecad/agent_sync.py take pedal   # resolve any conflicts
                     py -3.12 ../freecad/agent_sync.py build
                     py -3.12 ../freecad/agent_sync.py wait          # re-arm for the next one
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STALE_LOCK_S = 1200          # a build.lock older than this is presumed dead and stolen


# ── git helpers ───────────────────────────────────────────────────────────────
def git(*args, check=True, capture=True):
    r = subprocess.run(["git", *args], text=True,
                       capture_output=capture, cwd=os.getcwd())
    if check and r.returncode != 0:
        sys.stderr.write((r.stderr or r.stdout or "").strip() + "\n")
        raise SystemExit(f"git {' '.join(args)} failed ({r.returncode})")
    return (r.stdout or "").strip()


def common_dir() -> Path:
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))


def sync_dir() -> Path:
    d = common_dir() / "agent-sync"
    (d / "inbox").mkdir(parents=True, exist_ok=True)
    return d


def main_worktree() -> Path:
    # the first entry of `git worktree list --porcelain` is the primary worktree
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):])
    return Path(git("rev-parse", "--show-toplevel"))


def cur_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def slug(branch: str) -> str:
    return branch.replace("/", "-")


def is_dirty() -> bool:
    return bool(git("status", "--porcelain"))


# ── contributor commands ──────────────────────────────────────────────────────
def cmd_join(name: str):
    branch = f"agent/{name}"
    main = main_worktree()
    wt = main.parent / f"{main.name}-{name}"
    existing = {p for p in git("worktree", "list").splitlines()}
    if any(str(wt) in e for e in existing):
        print(f"worktree already exists: {wt}\n  cd \"{wt}\"")
        return
    branches = git("branch", "--list", branch)
    if branches:
        git("worktree", "add", str(wt), branch)
    else:
        git("worktree", "add", "-b", branch, str(wt), "main")
    print(f"created worktree for {branch}:\n  cd \"{wt}\"\n"
          f"Work there, then:  py -3.12 ../freecad/agent_sync.py submit \"<summary>\"")


def cmd_submit(summary: str):
    branch = cur_branch()
    if not branch.startswith("agent/"):
        raise SystemExit(f"submit must run on an agent/<name> branch (on '{branch}'). "
                         f"Run `join <name>` first and work in that worktree.")
    if is_dirty():
        git("add", "-A")
        git("commit", "-m", summary)
    sha = git("rev-parse", "HEAD")
    name = branch[len("agent/"):]
    req = {"branch": branch, "name": name, "summary": summary, "sha": sha,
           "worktree": str(main_worktree().parent / f"{main_worktree().name}-{name}"),
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    path = sync_dir() / "inbox" / f"{slug(branch)}.json"
    path.write_text(json.dumps(req, indent=2))
    print(f"merge request filed for {branch} @ {sha[:8]}\n"
          f"  \"{summary}\"\n"
          f"Tell the LEAD (or it will see it in `inbox`):\n"
          f"  py -3.12 ../freecad/agent_sync.py take {name}")


def cmd_sync():
    if is_dirty():
        raise SystemExit("working tree dirty -- commit/submit first, then sync.")
    git("merge", "main", "-m", "Merge main into " + cur_branch(), check=False)
    if is_dirty() or git("ls-files", "-u"):
        print("CONFLICTS while merging main -- resolve, `git add -A`, `git commit`.")
    else:
        print(f"{cur_branch()} is up to date with main.")


def cmd_done():
    branch = cur_branch()
    if not branch.startswith("agent/"):
        raise SystemExit("run `done` from your agent worktree.")
    print("From the MAIN worktree, remove this worktree with:\n"
          f"  git worktree remove \"{os.getcwd()}\"\n"
          f"  git branch -d {branch}   # once fully merged")


# ── lead commands ─────────────────────────────────────────────────────────────
def _requests():
    box = sync_dir() / "inbox"
    return sorted(box.glob("*.json"))


def cmd_wait(timeout, poll):
    """Block until >=1 merge request is pending, then print it and exit 0. The LEAD runs this in the
    BACKGROUND: the cheap shell poll (not the model) sits until a contributor's `submit` drops a request
    file, then exits -- which auto re-invokes the lead. So a contributor notifies the lead with NO human
    in the loop. Exit 2 on --timeout (re-arm to keep listening); default is to wait indefinitely."""
    box = sync_dir() / "inbox"
    deadline = (time.time() + timeout) if timeout > 0 else None
    while True:
        if _requests():
            cmd_inbox()
            return
        if deadline and time.time() >= deadline:
            print("wait: timed out, no requests yet -- re-arm `wait` to keep listening.")
            raise SystemExit(2)
        time.sleep(poll)


def cmd_inbox():
    reqs = _requests()
    if not reqs:
        print("inbox empty -- no pending merge requests.")
        return
    print(f"{len(reqs)} pending merge request(s):")
    for p in reqs:
        r = json.loads(p.read_text())
        print(f"  • {r['branch']:20s} {r['sha'][:8]}  {r['time']}  \"{r['summary']}\"")
    print("Take one with:  py -3.12 ../freecad/agent_sync.py take <name>")


def cmd_take(name: str):
    branch = f"agent/{name}"
    if cur_branch() != "main":
        print(f"WARNING: you are on '{cur_branch()}', not main. Merges normally land on main.")
    git("merge", "--no-ff", branch, "-m", f"Merge {branch}", check=False)
    if git("ls-files", "-u"):
        print(f"CONFLICTS merging {branch}. Resolve the files below, then:\n"
              f"  git add -A && git commit --no-edit\n"
              f"  py -3.12 ../freecad/agent_sync.py drop {name}   # clears the request\n"
              "conflicted:")
        print("  " + "\n  ".join(sorted(set(l.split()[-1] for l in git("ls-files", "-u").splitlines()))))
        return
    (sync_dir() / "inbox" / f"{slug(branch)}.json").unlink(missing_ok=True)
    print(f"merged {branch} into {cur_branch()}. Now build:\n"
          f"  py -3.12 ../freecad/agent_sync.py build")


def cmd_drop(name: str):
    p = sync_dir() / "inbox" / f"{slug('agent/' + name)}.json"
    if p.exists():
        p.unlink()
        print(f"dropped merge request for agent/{name}.")
    else:
        print(f"no pending request for agent/{name}.")


def cmd_build(extra):
    if Path(os.getcwd()).resolve() != main_worktree().resolve():
        raise SystemExit("build only runs in the MAIN worktree (the lead owns the single tab/build).")
    lock = sync_dir() / "build.lock"
    holder = f"{cur_branch()} pid={os.getpid()}"
    if lock.exists():
        try:
            ts = float(lock.read_text().splitlines()[1])
        except Exception:
            ts = 0.0
        if time.time() - ts < STALE_LOCK_S:
            raise SystemExit(f"another build holds {lock.name}:\n  {lock.read_text().splitlines()[0]}\n"
                             "wait for it to finish, or delete the lock if it's dead.")
        lock.unlink(missing_ok=True)          # stale -> steal
    lock.write_text(f"{holder}\n{time.time()}\n")
    try:                                          # the project's canonical build invocation
        rc = subprocess.run(["py", "-3.12", "-m", "src.build", *extra],
                            cwd=str(main_worktree())).returncode
    finally:
        lock.unlink(missing_ok=True)
    raise SystemExit(rc)


# ── either ────────────────────────────────────────────────────────────────────
def cmd_status():
    branch = cur_branch()
    role = "LEAD" if branch == "main" else ("CONTRIBUTOR" if branch.startswith("agent/") else "?")
    print(f"role: {role}   branch: {branch}   cwd: {os.getcwd()}")
    print("worktrees:")
    for line in git("worktree", "list").splitlines():
        print("  " + line)
    print(f"pending merge requests: {len(_requests())}  (see `inbox`)")


def main():
    # Contributor summaries carry arbitrary Unicode (arrows, bullets, °, Ø). The default Windows console
    # is cp1252, which raises UnicodeEncodeError on those and would KILL the lead's `wait` notifier mid
    # print. Force UTF-8 on stdout/stderr with replacement so a stray glyph never crashes coordination.
    for _s in (sys.stdout, sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    ap = argparse.ArgumentParser(prog="agent_sync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("join").add_argument("name")
    sub.add_parser("submit").add_argument("summary")
    sub.add_parser("sync")
    sub.add_parser("done")
    sub.add_parser("inbox")
    w = sub.add_parser("wait")
    w.add_argument("--timeout", type=float, default=0.0)      # 0 = wait forever
    w.add_argument("--poll", type=float, default=5.0)
    sub.add_parser("take").add_argument("name")
    sub.add_parser("drop").add_argument("name")
    b = sub.add_parser("build"); b.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("status")
    a = ap.parse_args()
    {"join": lambda: cmd_join(a.name), "submit": lambda: cmd_submit(a.summary),
     "sync": cmd_sync, "done": cmd_done, "inbox": cmd_inbox,
     "wait": lambda: cmd_wait(a.timeout, a.poll),
     "take": lambda: cmd_take(a.name), "drop": lambda: cmd_drop(a.name),
     "build": lambda: cmd_build(a.args), "status": cmd_status}[a.cmd]()


if __name__ == "__main__":
    main()
