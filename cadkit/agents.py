# -*- coding: utf-8 -*-
"""cadkit.agents — WHO OWNS WHICH PART, shared across every worktree.

The multi-agent model this supports (see cadkit/AGENTS.md): each contributor owns
a PORTION of the model, iterates on it in their own worktree, and renders it to
THEIR OWN FreeCAD tab. Only the lead builds the whole instrument.

That only works if "which portion is mine?" is answered somewhere both the tools
and the humans can see. The obvious place — a config block in the project's
scratch-view script — is the wrong one: it is a TRACKED file, so two agents each
editing the same three lines conflict on every single merge request, forever. The
conflict is not even meaningful; it is two agents correctly describing different
work.

So a scope lives HERE instead, in the same per-repo coordination state as the
merge inbox: shared by every worktree (it is under the common .git), never
committed, and keyed by the agent's own branch so nobody edits anybody else's
entry. Registering a scope is a local act with no diff, which is exactly right
for a fact about who is sitting at which desk today.

    from cadkit.agents import current_agent, get_scope

    scope = get_scope()                  # this worktree's owner, or None
    mod, attr = scope["module"], scope["attr"]

Deliberately NOT durable across a fresh clone, for the same reason the worktrees
and the inbox are not: it describes the current sitting, not the design. The
design lives in the code.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__ = ["current_agent", "scopes_path", "load_scopes", "get_scope",
           "set_scope", "clear_scope", "LEAD"]

LEAD = "lead"          # the name the main worktree registers under


def _git(*args, cwd=None):
    r = subprocess.run(["git", *args], text=True, capture_output=True,
                       cwd=cwd or os.getcwd())
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def current_agent(cwd=None) -> str:
    """This worktree's agent name: 'lead' on main, else the bit after 'agent/'.

    Derived from the branch rather than stored, so a worktree cannot disagree with
    itself about who it belongs to."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if not branch or branch == "main":
        return LEAD
    return branch[len("agent/"):] if branch.startswith("agent/") else branch


def scopes_path(cwd=None) -> Path | None:
    """The shared registry file, or None if git cannot answer (never raises)."""
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    if not common:
        return None
    d = Path(common) / "agent-sync"
    d.mkdir(parents=True, exist_ok=True)
    return d / "scopes.json"


def load_scopes(cwd=None) -> dict:
    """{agent: scope} for the whole repo. Unreadable/absent -> {}."""
    p = scopes_path(cwd)
    if p is None or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_scope(agent=None, cwd=None):
    """One agent's scope dict (default: this worktree's), or None if unregistered."""
    return load_scopes(cwd).get(agent or current_agent(cwd))


def set_scope(module, attr="assembly", replaced=(), note="", pose="", crop="",
              agent=None, cwd=None) -> dict:
    """Register/replace THIS agent's scope. Returns the stored dict.

    `replaced` names the context parts the live one supersedes, so the scratch view
    does not draw an old part beside its successor."""
    p = scopes_path(cwd)
    if p is None:
        raise RuntimeError("not in a git repo — cannot record a scope")
    name = agent or current_agent(cwd)
    scopes = load_scopes(cwd)
    scopes[name] = {"module": module, "attr": attr, "replaced": list(replaced),
                    "note": note, "pose": pose, "crop": crop}
    p.write_text(json.dumps(scopes, indent=2, sort_keys=True), encoding="utf-8")
    return scopes[name]


def clear_scope(agent=None, cwd=None) -> bool:
    """Drop an agent's scope (finished the part / handed it on). True if one went."""
    p = scopes_path(cwd)
    if p is None:
        return False
    scopes = load_scopes(cwd)
    if (agent or current_agent(cwd)) not in scopes:
        return False
    scopes.pop(agent or current_agent(cwd))
    p.write_text(json.dumps(scopes, indent=2, sort_keys=True), encoding="utf-8")
    return True
