# -*- coding: utf-8 -*-
"""Propagate the canonical cadkit into every project that vendors it.

cadkit is VENDORED (git subtree) into each consumer project, so the copies can
DRIFT — nothing forces them identical. This is the tool that keeps them honest:
run it after committing a change to the canonical cadkit repo and it will

  1. push the canonical repo to its upstream (so there is one source of truth), then
  2. re-pull the subtree into every consumer project that vendors cadkit.

A consumer whose working tree is DIRTY is SKIPPED (never auto-stashed), so no
uncommitted work is ever disturbed — commit or stash it, then re-run. The exit
code is the number of consumers that did NOT end up in sync (skipped or failed),
so this doubles as a pre-flight gate: 0 means every consumer is current.

Layout (dev tool, like agent_sync.py): the canonical cadkit repo and its consumer
projects are sibling directories. Consumers are AUTO-DISCOVERED by signature — a
git repo with a `cadkit/step_export.py` subtree — so there is no project list to
maintain (a list would just be one more thing to drift). Outside that layout it
finds nothing and is a harmless no-op.

    py -3.12 cadkit/tools/propagate.py            # push canonical, pull into all consumers
    py -3.12 cadkit/tools/propagate.py --dry-run  # show what would happen, change nothing
    py -3.12 cadkit/tools/propagate.py --no-push   # skip the upstream push (pull only)
"""

import argparse
import pathlib
import subprocess
import sys

CANON = pathlib.Path(__file__).resolve().parents[1]   # <workspace>/cadkit
WORKSPACE = CANON.parent
SIGNATURE = ("cadkit", "step_export.py")              # marks a vendored cadkit subtree


def _git(args, cwd, check=False):
    """Run a git command, returning (returncode, combined_output)."""
    p = subprocess.run(["git", *args], cwd=str(cwd),
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s failed in %s:\n%s" % (" ".join(args), cwd,
                                                         (p.stdout + p.stderr).strip()))
    return p.returncode, (p.stdout + p.stderr).strip()


def _is_git_repo(d):
    # A primary checkout has .git as a DIRECTORY. A linked worktree has .git as a
    # FILE (a "gitdir:" pointer) — skip those: they're branches of a repo already
    # covered here, and a contributor's worktree gets current cadkit when that
    # agent runs `agent_sync.py sync`, not by the lead pulling into its branch.
    return (d / ".git").is_dir()


def _is_dirty(d):
    _, out = _git(["status", "--porcelain"], d)
    return bool(out.strip())


def _discover_consumers():
    """Every sibling repo that vendors cadkit (has cadkit/step_export.py), except
    the canonical repo itself."""
    out = []
    for d in sorted(WORKSPACE.iterdir()):
        if not d.is_dir() or d.resolve() == CANON.resolve():
            continue
        if _is_git_repo(d) and (d.joinpath(*SIGNATURE)).exists():
            out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would happen; make no changes")
    ap.add_argument("--no-push", action="store_true",
                    help="skip pushing the canonical repo to its upstream")
    ap.add_argument("--branch", default="main", help="cadkit branch (default: main)")
    a = ap.parse_args()

    if not _is_git_repo(CANON):
        print("canonical cadkit repo not found at %s" % CANON, file=sys.stderr)
        return 2

    # Guard against running a VENDORED copy: the canonical cadkit is its own
    # standalone repo (its git toplevel IS the cadkit dir), whereas a copy vendored
    # into a project has the project as its toplevel. Running the vendored copy
    # would treat the project as the workspace and find no consumers — so redirect.
    rc0, top = _git(["rev-parse", "--show-toplevel"], CANON)
    if rc0 != 0 or pathlib.Path(top.strip()).resolve() != CANON.resolve():
        print("this is a VENDORED copy of cadkit (inside %s), not the canonical repo.\n"
              "Run propagate from the standalone canonical cadkit checkout instead."
              % (top.strip() or "a project"), file=sys.stderr)
        return 2

    # Where consumers pull FROM: the canonical's upstream if it has one (the true
    # single source), else the local canonical path (offline dev).
    rc, origin = _git(["remote", "get-url", "origin"], CANON)
    source = origin.strip() if rc == 0 and origin.strip() else str(CANON)

    print("canonical : %s" % CANON)
    print("upstream  : %s" % source)

    # 1. Push canonical so consumers pull a published state, not a local-only one.
    if not a.no_push and rc == 0 and origin.strip():
        if a.dry_run:
            print("[dry-run] would push canonical -> %s (%s)" % (source, a.branch))
        else:
            prc, pout = _git(["push", "origin", a.branch], CANON)
            print("push canonical: %s" % ("ok" if prc == 0 else "FAILED\n" + pout))
            if prc != 0:
                print("aborting: consumers would pull a stale upstream", file=sys.stderr)
                return 2

    consumers = _discover_consumers()
    if not consumers:
        print("no consumer projects found next to %s" % CANON)
        return 0

    print("\nconsumers (%d):" % len(consumers))
    not_synced = 0
    for d in consumers:
        name = d.name
        if _is_dirty(d):
            print("  SKIP  %-28s dirty working tree (commit/stash, then re-run)" % name)
            not_synced += 1
            continue
        if a.dry_run:
            print("  pull  %-28s (dry-run)" % name)
            continue
        # Pull the subtree. --squash keeps consumer history to one commit per sync.
        prc, pout = _git(["subtree", "pull", "--prefix=cadkit", source, a.branch,
                          "--squash", "-m", "Sync vendored cadkit"], d)
        if prc == 0:
            state = "up to date" if "already" in pout.lower() else "updated"
            print("  OK    %-28s %s" % (name, state))
        else:
            print("  FAIL  %-28s %s" % (name, pout.splitlines()[-1] if pout else "see git output"))
            not_synced += 1

    if a.dry_run:
        print("\n[dry-run] no changes made")
        return 0
    print("\n%d/%d consumers in sync" % (len(consumers) - not_synced, len(consumers)))
    return not_synced


if __name__ == "__main__":
    sys.exit(main())
