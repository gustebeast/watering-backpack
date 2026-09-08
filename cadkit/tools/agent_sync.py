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
               the lead's files. It OWNS A PORTION of the model, iterates on that
               portion in ITS OWN FreeCAD tab, and files a MERGE REQUEST at each
               good checkpoint; the lead integrates and builds the whole thing.

EACH AGENT HAS ITS OWN TAB. `scope` records which portion is yours; `view` renders
it -- your part FRESH against a cached rest-of-instrument -- into a tab named after
your worktree, in seconds. The lead's tab shows the WHOLE instrument and is the only
one produced by a real `src.build`. Two agents rendering at the same moment write
different STEPs into different tabs, so there is nothing to race: the single-build
lock guards the FULL build only.

THE LEAD IS NOT A RELAY. Merge requests carry WORK, not correspondence:
  * A question for the HUMAN goes to YOUR OWN chat -- every agent has its own
    human-facing session, so ask there and wait for the answer. Do NOT bury it in
    a submit summary hoping the lead passes it along: the lead cannot answer for
    the human, and routing through it adds a whole round trip to every question.
  * A question for ANOTHER AGENT goes direct:  `msg <who> "<text>"`. It lands in
    their context on their next prompt (the hook delivers it, in every session --
    lead and contributor alike). Nobody polls, and the lead is not in the middle.
Keep the submit summary about the change: what moved, why, and how you verified.

Coordination state lives in  <git-common-dir>/agent-sync/  -- inside .git, so it
is shared by every worktree and never committed:
    mail/<branch>/*.json  direct messages awaiting that agent's next prompt
    inbox/<branch>.json   one pending merge request per contributor branch
    scopes.json           who owns which portion of the model (see cadkit.agents)
    announced.json        request shas `watch` has already reported (no re-wake loop)
    watch.lock            single-listener heartbeat
    build.lock            single-build mutex (auto-stolen if stale), FULL builds only

COMMANDS
  Contributor:
    join <name>          create + print a worktree on agent/<name> (off main)
    submit "<summary>"   commit this branch, then file a merge request
    sync                 merge the latest main into this branch (pick up merges)
    scope [--set MOD]    claim / show which portion of the model you own
    view [args...]       render YOUR portion into YOUR OWN FreeCAD tab (seconds)
    done                 (after all merged) remove this worktree
  Lead:
    inbox                list pending merge requests
    msg <who> "<text>"   send a DIRECT message to another agent ('lead' = the lead)
    mail                 read (and consume) messages sent to you
    watch                SELF-RE-ARMING listener -- prefer this over `wait` (BACKGROUND)
    wait                 one-shot block until a request arrives (needs manual re-arming)
    take <name>          merge agent/<name> into the current branch
    drop <name>          discard a merge request without merging
    build [args...]      run `src.build` under the single-build lock
  Either:
    status               role, branch, worktrees, pending requests

NOTIFICATION -- two layers, no desktop pop-ups, the human is NEVER the relay:
  1. AUTO WAKE (fully hands-free, and it STAYS armed). The lead runs `watch` once as a
     BACKGROUND command; a cheap shell poll (not the model) sits idle until a
     contributor's `submit` drops a request file, then exits -- which auto re-invokes
     the lead. A listener MUST exit to wake anyone, so before exiting it SPAWNS A
     DETACHED SUCCESSOR: the exiting process wakes the lead, the successor covers the
     window while the lead works, and nobody re-arms anything. (`wait` is the old
     one-shot form; it covers exactly one request and then the repo is deaf, which in
     practice meant the hook nagged about a down listener on nearly every prompt.)
  2. PROMPT-TIME NUDGE (covers the blind spot). The `hook` command, wired as the
     lead's `UserPromptSubmit` hook, runs on the lead's NEXT prompt -- whatever it is
     about -- and, if the inbox holds a request, injects a loud notice into the lead's
     context: take it AND (re-)arm `wait`. So a down `wait` self-heals the instant the
     lead is prompted for anything; no human has to notice or forward. (We cannot wake
     a truly idle, unarmed session with no prompt -- nothing on one machine can -- but
     the request is never lost and surfaces the moment the lead does ANYTHING.)
Plus a loud PENDING banner on every lead command (`status`/`build`/`take`). The
contributor never pings anyone by hand; `submit` files the request and both layers
carry it from there. SELF-HEAL: a request whose work already reached `main` — merged by
hand, not via `take` (the only thing that unlinks it) — is pruned on the next inbox read,
so a manual merge never leaves the hook/banner nagging forever.

Typical flow (<name> is the contributor's task, e.g. the subsystem they own)
  human: "let's go multi-agent; the second chat is a sub-agent named <name>"
  lead (once):  py -3.12 cadkit/tools/agent_sync.py watch     # <-- in the BACKGROUND; re-arms ITSELF
  contributor:  py -3.12 cadkit/tools/agent_sync.py join <name>   # -> cd the printed dir
                ...edit, then...
                py -3.12 cadkit/tools/agent_sync.py scope --set src.<your_module>  # once
                py -3.12 cadkit/tools/agent_sync.py view    # your part, your tab, seconds
                py -3.12 cadkit/tools/agent_sync.py submit "<summary of your round>"   # wakes the lead
  lead (auto-woken): py -3.12 cadkit/tools/agent_sync.py take <name>   # resolve any conflicts
                     py -3.12 cadkit/tools/agent_sync.py build        # WHOLE instrument -> lead's tab
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
          f"Work there, then:  py -3.12 cadkit/tools/agent_sync.py submit \"<summary>\"")


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
          f"If the LEAD's `wait` is armed it just woke; otherwise the `hook` surfaces this on\n"
          f"the LEAD's next prompt. Take with:\n"
          f"  py -3.12 cadkit/tools/agent_sync.py take {name}")


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
def _is_ancestor(sha: str, ref: str = "main") -> bool:
    """True if <sha> is already in <ref>'s history — i.e. the request was merged, whether via
    `take` (which unlinks it) or MANUALLY (which doesn't). The basis for self-healing the inbox."""
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                          cwd=os.getcwd(), capture_output=True).returncode == 0


def _prune_merged(paths):
    """Keep only the still-PENDING requests, UNLINKING any whose sha already reached main. Self-heal:
    an MR resolved OUTSIDE `take` (merged by hand) no longer nags the hook/banner forever — the next
    inbox read clears it. An unreadable file is left alone (never guessed away)."""
    live = []
    for p in paths:
        try:
            sha = json.loads(p.read_text()).get("sha", "")
        except Exception:
            live.append(p)
            continue
        if sha and _is_ancestor(sha):
            p.unlink(missing_ok=True)          # merged -> done -> stop reporting it
        else:
            live.append(p)
    return live


def _requests():
    box = sync_dir() / "inbox"
    return _prune_merged(sorted(box.glob("*.json")))


def _load_reqs(paths=None):
    """Read each pending request file -> list of dicts. The single place that knows the
    request schema; callers just format the dicts differently."""
    return [json.loads(p.read_text()) for p in (_requests() if paths is None else paths)]


# ── direct agent-to-agent messages ────────────────────────────────────────────
# The lead is NOT a relay. Merge requests carry WORK; questions between agents go
# here, and questions for the HUMAN go straight to that agent's own chat. Without
# this channel the only way to reach another agent was to bury a question in a
# submit summary and hope the lead passed it on -- slow, lossy, and it made the
# lead a bottleneck on conversations it wasn't part of.
def _mail_dir(branch: str, make=False) -> Path:
    d = sync_dir() / "mail" / slug(branch) if make else \
        common_dir() / "agent-sync" / "mail" / slug(branch)
    if make:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_branch(who: str) -> str:
    """'lead'/'main' -> main; 'branner'/'agent/branner' -> agent/branner."""
    if who in ("lead", "main"):
        return "main"
    return who if who.startswith("agent/") else f"agent/{who}"


def cmd_msg(to: str, text: str):
    dest = _resolve_branch(to)
    if not git("rev-parse", "--verify", "--quiet", dest, check=False).strip():
        raise SystemExit(f"no such recipient: {to} (branch '{dest}' does not exist).\n"
                         f"Agents currently on this repo:\n  " +
                         "\n  ".join(b.strip().lstrip("* ") for b in
                                     git("branch", "--list", "agent/*").splitlines()) or "  (none)")
    me = cur_branch()
    if dest == me:
        raise SystemExit("that's your own mailbox.")
    box = _mail_dir(dest, make=True)
    (box / f"{int(time.time() * 1000)}-{slug(me)}.json").write_text(
        json.dumps({"from": me, "to": dest, "text": text,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    print(f"message delivered to {dest} — it lands in their context on their NEXT prompt.\n"
          f"They do NOT get it while mid-turn, so don't block waiting on a reply.")


def _mail_paths(branch: str):
    d = _mail_dir(branch)
    return sorted(d.glob("*.json")) if d.is_dir() else []


def cmd_mail(peek=False):
    paths = _mail_paths(cur_branch())
    if not paths:
        print("no messages.")
        return
    for p in paths:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        print(f"from {m.get('from','?')}  {m.get('time','')}\n  {m.get('text','')}\n")
        if not peek:
            p.unlink(missing_ok=True)      # printed == delivered (it is in the context now)


def _hook_mail(common: Path, branch: str):
    """Read-only mail glob for the hook's hot path (no mkdir). Returns [(path, dict)]."""
    d = common / "agent-sync" / "mail" / slug(branch)
    out = []
    for p in (sorted(d.glob("*.json")) if d.is_dir() else []):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            pass
    return out


def _hook_reqs():
    """Hot path -- runs on EVERY lead prompt. ONE git call for branch + common-dir (not two),
    and a READ-ONLY inbox glob (no mkdir, unlike sync_dir()). Returns
    (branch, [request paths], common_dir); ("", [], None) if git can't answer, so the
    hook stays silent instead of erroring. The common dir comes back because the
    hook ALSO delivers mail, and re-deriving it would cost a second git call."""
    out = git("rev-parse", "--path-format=absolute", "--abbrev-ref", "HEAD",
              "--git-common-dir", check=False)
    lines = out.splitlines()
    if len(lines) < 2:
        return "", [], None
    common = Path(lines[1])
    inbox = common / "agent-sync" / "inbox"
    paths = sorted(inbox.glob("*.json")) if inbox.is_dir() else []
    # self-heal stale (already-merged) entries -- but only the LEAD's inbox is
    # meaningful, and _prune_merged shells out to git per entry, so skip that
    # work entirely in a contributor worktree (where the hook only wants mail).
    return lines[0], (_prune_merged(paths) if lines[0] == "main" else paths), common


def _print_pending_banner():
    """Loud, impossible-to-miss banner of every queued request. Printed by the lead's
    routine commands so a pending merge can't be walked past even if `wait` never fired."""
    reqs = _requests()
    if not reqs:
        return
    bar = "!" * 64
    print(bar)
    print(f"  {len(reqs)} PENDING MERGE REQUEST(S) -- take them before you move on:")
    for r in _load_reqs(reqs):
        print(f"    * agent/{r['name']:12s} {r['sha'][:8]}  \"{r['summary']}\"")
    print(f"  ->  py -3.12 cadkit/tools/agent_sync.py take <name>")
    print(bar)


_REARM = ("RE-ARM the notifier (its trip consumed it) or the NEXT submit is silent:\n"
          "  py -3.12 cadkit/tools/agent_sync.py wait      # in the BACKGROUND")


# ── the SELF-RE-ARMING listener ───────────────────────────────────────────────
# `wait` has one structural flaw as a notifier: it must EXIT to wake the lead
# (a finishing background command is the wake signal), so it covers exactly one
# request and then the repo is deaf until somebody re-arms it by hand. In practice
# that meant the hook nagged "your listener is down" on nearly every prompt.
#
# `watch` fixes it without pretending a loop can wake anyone: before exiting, it
# SPAWNS A DETACHED SUCCESSOR. The exiting process wakes the lead; the successor
# covers the window while the lead is busy. So a listener is always armed and
# nobody re-arms anything.
#
# Two things keep that from running away:
#   * ANNOUNCED SET -- a request is announced once, by sha. Without it the
#     successor would see the still-pending request its parent just reported and
#     fire instantly, forever.
#   * SINGLE-WATCHER LOCK -- a heartbeat file. A second watcher started while one
#     is alive exits quietly, so `watch` is safe to run twice by mistake.
_WATCH_LOCK_STALE_S = 30.0


def _announced_path():
    return sync_dir() / "announced.json"


def _load_announced() -> set:
    try:
        return set(json.loads(_announced_path().read_text()))
    except Exception:
        return set()


def _mark_announced(shas):
    """Record shas as reported, dropping any already merged so this cannot grow
    without bound (the same ancestor test the inbox self-heal uses)."""
    keep = {s for s in (_load_announced() | set(shas)) if not _is_ancestor(s)}
    try:
        _announced_path().write_text(json.dumps(sorted(keep)))
    except OSError:
        pass


def _watch_lock_fresh() -> bool:
    p = sync_dir() / "watch.lock"
    try:
        return (time.time() - float(p.read_text().split()[-1])) < _WATCH_LOCK_STALE_S
    except Exception:
        return False


def _touch_watch_lock():
    try:
        (sync_dir() / "watch.lock").write_text(f"pid={os.getpid()} {time.time()}")
    except OSError:
        pass


def _spawn_successor():
    """Start the next watcher DETACHED, so coverage never lapses while the lead works.

    The successor is launched with --takeover, which skips the already-armed check.
    The obvious alternative -- delete the lock so the successor passes that check --
    leaves a ~1 s window with NO lock, during which a stray `watch` would double-arm
    and every future request would be announced twice.""" 
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__),
                          "watch", "--takeover"],
                         cwd=os.getcwd(), close_fds=True, creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def cmd_watch(poll=5.0, takeover=False):
    """Block until a NOT-YET-ANNOUNCED merge request lands, print it, arm a
    successor, and exit — so the lead is woken AND the repo stays covered."""
    if not takeover and _watch_lock_fresh():
        print("a watcher is already armed (watch.lock is fresh) — nothing to do.")
        return
    while True:
        _touch_watch_lock()
        new = [r for r in _load_reqs() if r.get("sha") not in _load_announced()]
        if new:
            _mark_announced([r["sha"] for r in new])
            armed = _spawn_successor()
            bar = "!" * 64
            print(bar)
            print(f"  {len(new)} NEW merge request(s):")
            for r in new:
                print(f"    * {r['branch']:20s} {r['sha'][:8]}  \"{r['summary']}\"")
            print(f"  ->  py -3.12 cadkit/tools/agent_sync.py take <name>")
            print("  successor watcher ARMED — no re-arm needed." if armed else
                  "  WARNING: could not arm a successor; run `watch` again.")
            print(bar)
            return
        time.sleep(poll)


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
            print(_REARM)
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
    for r in _load_reqs(reqs):
        print(f"  • {r['branch']:20s} {r['sha'][:8]}  {r['time']}  \"{r['summary']}\"")
    print("Take one with:  py -3.12 cadkit/tools/agent_sync.py take <name>")


def cmd_take(name: str):
    # accept both `take branner` and `take agent/branner` -- the inbox banner
    # prints the FULL branch name, so pasting it used to build 'agent/agent/branner'
    # and (with check=False below) fail SILENTLY, printing "merged" for a no-op.
    branch = name if name.startswith("agent/") else f"agent/{name}"
    name = branch[len("agent/"):]
    if not git("rev-parse", "--verify", "--quiet", branch, check=False).strip():
        print(f"no such branch: {branch}. Pending requests:")
        cmd_inbox()
        raise SystemExit(2)
    if cur_branch() != "main":
        print(f"WARNING: you are on '{cur_branch()}', not main. Merges normally land on main.")
    git("merge", "--no-ff", branch, "-m", f"Merge {branch}", check=False)
    if git("ls-files", "-u"):
        print(f"CONFLICTS merging {branch}. Resolve the files below, then:\n"
              f"  git add -A && git commit --no-edit\n"
              f"  py -3.12 cadkit/tools/agent_sync.py drop {name}   # clears the request\n"
              "conflicted:")
        print("  " + "\n  ".join(sorted(set(l.split()[-1] for l in git("ls-files", "-u").splitlines()))))
        return
    # PROVE it landed before clearing the request: `git merge` above runs with
    # check=False (a conflict is a normal, handled outcome), so any OTHER failure
    # would otherwise be reported as a successful merge.
    if not _is_ancestor(branch, "HEAD"):
        print(f"MERGE DID NOT LAND: {branch} is still not an ancestor of HEAD. "
              f"Request kept. Investigate with:\n  git log --oneline -5 {branch}")
        raise SystemExit(1)
    (sync_dir() / "inbox" / f"{slug(branch)}.json").unlink(missing_ok=True)
    print(f"merged {branch} into {cur_branch()}. Now build:\n"
          f"  py -3.12 cadkit/tools/agent_sync.py build")
    _print_pending_banner()      # surface any OTHER queued requests before you move on
    print(_REARM)


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
    _print_pending_banner()      # a queued request the lead hasn't taken is easy to miss mid-build
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


# ── ownership: each agent iterates ITS OWN portion, in ITS OWN tab ─────────────
# The scope registry itself lives in cadkit.agents (shared by every worktree, never
# committed -- see that module for why it is not a tracked config block). agent_sync
# just puts a CLI on it, because this is where agents already look.
def _agents_mod():
    """Import cadkit.agents from a script that is run by PATH, not as a module."""
    root = Path(__file__).resolve().parents[2]      # <project>/cadkit/tools/x.py
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from cadkit import agents
    return agents


def cmd_scope(module, attr, replaced, note, clear, list_all, pose, crop):
    A = _agents_mod()
    me = A.current_agent()
    if clear:
        print(f"scope cleared for {me}." if A.clear_scope() else f"{me} had no scope.")
        return
    if module:
        sc = A.set_scope(module, attr=attr, note=note, pose=pose, crop=crop,
                         replaced=[r for r in (replaced or "").split(",") if r])
        print(f"{me} now owns {sc['module']}.{sc['attr']}"
              + (f"  (supersedes {', '.join(sc['replaced'])})" if sc["replaced"] else ""))
    scopes = A.load_scopes()
    if not scopes:
        print("no scopes registered. Claim one with:  scope --set <module> [--attr fn]")
        return
    print()
    print(f"WHO OWNS WHAT ({len(scopes)} registered)"
          + ("" if list_all else f" -- you are {me}"))
    for name, sc in sorted(scopes.items()):
        mark = " <- you" if name == me else ""
        print(f"  {name:14s} {sc.get('module','?')}.{sc.get('attr','?')}{mark}")
        if sc.get("note"):
            print(f"                 {sc['note']}")


def cmd_view(extra):
    """Render YOUR portion into YOUR OWN FreeCAD tab (the project's scratch view).

    Deliberately separate from `build`: `build` is the WHOLE instrument and stays
    the lead's, `view` is your part and is the thing you run all day. It needs no
    build lock -- each worktree writes its own STEP, and the hub names tabs after
    the folder, so two agents rendering at once land in two different tabs."""
    if Path(os.getcwd()).resolve() == main_worktree().resolve():
        raise SystemExit("`view` renders ONE agent's portion; the lead's tab shows the whole "
                         "instrument, so use `build` here.")
    A = _agents_mod()
    if A.get_scope() is None:
        raise SystemExit(
            f"{A.current_agent()} has no scope yet. Claim one first:  "
            "py -3.12 cadkit/tools/agent_sync.py scope --set src.<your_module>")
    rc = subprocess.run(["py", "-3.12", "-m", "tools.scratch_view", *extra],
                        cwd=os.getcwd()).returncode
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
    _print_pending_banner()


def cmd_hook():
    """The LEAD's `UserPromptSubmit` hook (wire it in .claude/settings.json). It runs on the
    lead's NEXT prompt -- whatever that prompt is about -- and, if the inbox holds a request,
    prints a loud notice that Claude Code injects into the lead's context. It reports
    whether a listener is actually armed (`watch` keeps one alive by spawning its own
    successor), so the banner nags to START one only when there really is none —
    a pending request that a live listener has simply not been taken from yet is not a
    fault. This is how a missing listener self-heals the moment the lead is prompted,
    with no human relay. Stays SILENT (no output) when the inbox is empty or this isn't the
    lead session, so a normal turn is never cluttered. ALWAYS exits 0 -- a hook must never
    block or fail the prompt.

    It ALSO delivers direct messages, and that half runs in EVERY session (lead and
    contributor alike) -- it is what makes agent-to-agent mail arrive without anyone
    polling. A message is unlinked once printed: it is in the recipient's context at
    that point, so re-printing it every prompt would just be noise."""
    try:
        branch, paths, common = _hook_reqs()
        if common is not None and branch:
            mail = _hook_mail(common, branch)
            if mail:
                bar = "=" * 68
                print(bar)
                print(f"[agent_sync] {len(mail)} direct message(s) for you "
                      f"({branch}). Reply with:  py -3.12 cadkit/tools/agent_sync.py "
                      f"msg <who> \"<text>\"")
                for p, m in mail:
                    print(f"  from {m.get('from','?')}  {m.get('time','')}\n"
                          f"    {m.get('text','')}")
                    p.unlink(missing_ok=True)          # printed == delivered
                print(bar)
        if branch != "main" or not paths:     # only the lead acts; silent when nothing waits
            return
        bar = "=" * 68
        out = [bar,
               f"[agent_sync] ACTION REQUIRED before you continue: {len(paths)} merge "
               f"request(s) are waiting in your inbox.",
               ("A listener is armed, so these are simply not taken yet."
                if _watch_lock_fresh() else
                "NO listener is armed - start one (it re-arms itself from then on):"
                "  ->  py -3.12 cadkit/tools/agent_sync.py watch   (in the BACKGROUND)"),
               "  take each below:   py -3.12 cadkit/tools/agent_sync.py take <name>",
               "pending:"]
        out += [f"  * agent/{r['name']}  {r['sha'][:8]}  \"{r['summary']}\"" for r in _load_reqs(paths)]
        out.append(bar)
        print("\n".join(out))
    except Exception:
        pass                              # a hook must never fail the prompt -> swallow everything


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
    w2 = sub.add_parser("watch")    # SELF-RE-ARMING listener (prefer over `wait`)
    w2.add_argument("--poll", type=float, default=5.0)
    w2.add_argument("--takeover", action="store_true",
                    help=argparse.SUPPRESS)      # internal: I am the spawned successor
    sc = sub.add_parser("scope")    # who owns which portion of the model
    sc.add_argument("--set", dest="module", metavar="MODULE",
                    help="claim a portion, e.g. src.leg_stack")
    sc.add_argument("--attr", default="assembly", help="callable on it (default: assembly)")
    sc.add_argument("--replaced", default="", metavar="A,B",
                    help="context part prefixes yours supersedes")
    sc.add_argument("--note", default="", help="one line for the other agents")
    sc.add_argument("--pose", default="", metavar="KEY",
                    help="POSES key, if your part is not authored in global coords")
    sc.add_argument("--crop", default="", metavar="KEY",
                    help="CROPS key, to cache only a region of the instrument")
    sc.add_argument("--clear", action="store_true", help="give the portion up")
    sc.add_argument("--all", dest="list_all", action="store_true")
    v = sub.add_parser("view")      # render YOUR portion into YOUR tab
    v.add_argument("args", nargs=argparse.REMAINDER)
    m = sub.add_parser("msg")       # direct agent -> agent message (NOT via the lead)
    m.add_argument("to", help="agent name, or 'lead'")
    m.add_argument("text")
    sub.add_parser("mail").add_argument("--peek", action="store_true",
                                        help="show without consuming")
    sub.add_parser("hook")          # UserPromptSubmit hook (see .claude/settings.json)
    a = ap.parse_args()
    {"join": lambda: cmd_join(a.name), "submit": lambda: cmd_submit(a.summary),
     "sync": cmd_sync, "done": cmd_done, "inbox": cmd_inbox,
     "wait": lambda: cmd_wait(a.timeout, a.poll),
     "take": lambda: cmd_take(a.name), "drop": lambda: cmd_drop(a.name),
     "build": lambda: cmd_build(a.args), "status": cmd_status, "hook": cmd_hook,
     "msg": lambda: cmd_msg(a.to, a.text), "mail": lambda: cmd_mail(a.peek),
     "watch": lambda: cmd_watch(a.poll, a.takeover), "view": lambda: cmd_view(a.args),
     "scope": lambda: cmd_scope(a.module, a.attr, a.replaced, a.note,
                                a.clear, a.list_all, a.pose, a.crop)}[a.cmd]()


if __name__ == "__main__":
    main()
