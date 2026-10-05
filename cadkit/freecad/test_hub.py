# -*- coding: utf-8 -*-
"""Regression test for the hub's tab bookkeeping, runnable with plain CPython.

    py -3.12 cadkit/freecad/test_hub.py

freecad_viewer.py can only be imported inside FreeCAD (FreeCAD / FreeCADGui / ImportGui /
PySide), and FreeCAD's own headless binary has no GUI modules either -- so those four are
STUBBED here and the module is imported on top of them. What that buys is the part worth
guarding: the reconcile logic that decides when a tab is opened, adopted, reloaded or
forgotten.

WHY THIS EXISTS. The hub stopped keeping `_hub["projects"]` and now reads provenance off the
documents themselves, which is what lets new code take over running tabs without
re-importing them. That change is invisible until it is wrong -- the failure modes are a
DUPLICATE tab, a tab that silently stops following its STEP, and a reload that fires on
every tick -- and it is vendored into every project that uses cadkit. A fake FreeCAD is
cheap; finding this by hand in seven repos is not.

The Meta stub is deliberately COPY-ON-READ like the real property (verified against FreeCAD
1.1.1 with freecadcmd): code that mutates what Meta hands back, instead of reassigning the
whole dict, must fail here exactly as it would in FreeCAD.
"""

import os
import sys
import types
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))

FAILED = []
PASSED = [0]


def check(cond, what):
    if cond:
        PASSED[0] += 1
    else:
        FAILED.append(what)
        print("  FAIL: %s" % what)


# -- the fake FreeCAD --------------------------------------------------------
class FakeDoc(object):
    def __init__(self, name):
        self.Name = name
        self.Label = name
        self.Objects = []
        self.FileName = ""
        self.recomputes = 0
        self._meta = {}

    # Meta is copy-on-read in FreeCAD: mutating the result is a no-op.
    def _get_meta(self):
        return dict(self._meta)

    def _set_meta(self, v):
        self._meta = dict(v)

    Meta = property(_get_meta, _set_meta)

    def getObject(self, name):
        for o in self.Objects:
            if o.Name == name:
                return o
        return None

    def removeObject(self, name):
        self.Objects = [o for o in self.Objects if o.Name != name]

    def recompute(self):
        self.recomputes += 1

    def saveAs(self, path):
        self.FileName = path


class FakeParam(object):
    def SetBool(self, *a):
        pass

    def SetInt(self, *a):
        pass

    def GetUnsigned(self, key, default=0):
        return default


class FakeConsole(object):
    def PrintMessage(self, *a):
        pass

    def PrintError(self, *a):
        pass

    def PrintWarning(self, *a):
        pass


class FakeApp(types.ModuleType):
    def __init__(self):
        types.ModuleType.__init__(self, "FreeCAD")
        self.docs = {}
        self.ActiveDocument = None
        self.imports = []          # every ImportGui.insert, in order
        self.Console = FakeConsole()

    def listDocuments(self):
        return dict(self.docs)

    def getDocument(self, name):
        if name not in self.docs:
            raise NameError("no document %r" % name)
        return self.docs[name]

    def newDocument(self, name):
        d = FakeDoc(name)
        self.docs[name] = d
        self.ActiveDocument = d
        return d

    def activeDocument(self):
        return self.ActiveDocument

    def closeDocument(self, name):
        self.docs.pop(name, None)

    def setActiveDocument(self, name):
        self.ActiveDocument = self.docs.get(name)

    def ParamGet(self, *a):
        return FakeParam()


class FakeTimer(object):
    def __init__(self):
        self.started = None
        self.stopped = False
        self.timeout = self

    def connect(self, fn):
        self.fn = fn

    def start(self, ms):
        self.started = ms

    def stop(self):
        self.stopped = True


def _install_stubs():
    app = FakeApp()
    sys.modules["FreeCAD"] = app

    gui = types.ModuleType("FreeCADGui")
    gui.getDocument = lambda name: None          # no view -> camera code is skipped
    gui.getMainWindow = lambda: None             # no window -> shortcuts are skipped
    gui.SendMsgToActiveView = lambda *a: None
    gui.runCommand = lambda *a: None
    gui.Selection = types.SimpleNamespace(getSelection=lambda: [])
    sys.modules["FreeCADGui"] = gui

    imp = types.ModuleType("ImportGui")
    imp.insert = lambda step, docname: app.imports.append((step, docname))
    sys.modules["ImportGui"] = imp

    qtcore = types.ModuleType("QtCore")
    qtcore.QTimer = FakeTimer
    qtcore.Qt = types.SimpleNamespace(ApplicationShortcut=0)
    qtgui = types.ModuleType("QtGui")
    qtgui.QKeySequence = lambda *a: None
    qtgui.QShortcut = object
    pyside = types.ModuleType("PySide")
    pyside.QtCore = qtcore
    pyside.QtGui = qtgui
    sys.modules["PySide"] = pyside
    sys.modules["PySide.QtCore"] = qtcore
    sys.modules["PySide.QtGui"] = qtgui
    return app


APP = _install_stubs()
sys.path.insert(0, _HERE)
import freecad_viewer as V                                          # noqa: E402


# -- fixtures ----------------------------------------------------------------
TMP = tempfile.mkdtemp(prefix="cadkit_hub_test_")


def make_step(project, text="solid"):
    """A fake project folder with a STEP in it, so _doc_name behaves normally."""
    d = os.path.join(TMP, project)
    if not os.path.isdir(d):
        os.makedirs(d)
    p = os.path.join(d, "assembly.step")
    with open(p, "w") as f:
        f.write(text)
    return p


def touch(path, text):
    with open(path, "w") as f:
        f.write(text)


# -- tests -------------------------------------------------------------------
print("provenance round-trip")
step_a = make_step("proj_a")
doc = APP.newDocument("tmp_round_trip")
V._stamp_doc(doc, step_a, 123.5, 77)
prov = V._doc_prov(doc)
check(prov is not None, "a stamped doc reads back as ours")
check(prov["step"] == os.path.abspath(step_a), "step path round-trips")
check(abs(prov["mtime"] - 123.5) < 1e-9, "mtime round-trips exactly")
check(prov["size"] == 77, "size round-trips")
check(V._doc_prov(APP.newDocument("tmp_unstamped")) is None,
      "an unstamped doc is not ours")
APP.closeDocument("tmp_round_trip")
APP.closeDocument("tmp_unstamped")

print("Meta really is copy-on-read (so the stub cannot hide a mutate-in-place bug)")
d2 = APP.newDocument("tmp_cow")
V._stamp_doc(d2, step_a, 5.0, 1)
m = d2.Meta
m["cadkit_mtime"] = "999.0"
check(V._doc_prov(d2)["mtime"] == 5.0, "mutating the returned dict changes nothing")
APP.closeDocument("tmp_cow")

print("_tracked reflects FreeCAD, not a cache")
step_b = make_step("proj_b")
V._open_project(step_a)
V._open_project(step_b)
name_a, name_b = V._doc_name(step_a), V._doc_name(step_b)
check(set(V._tracked()) == {name_a, name_b}, "both projects are tracked")
check(len(APP.imports) == 2, "each project imported exactly once")

print("opening the same project twice does not duplicate a tab")
before = len(APP.imports)
V._open_project(step_a)
check(len(APP.imports) == before, "a second open imports nothing")
check(len(APP.docs) == 2, "no duplicate document was created")

print("a closed tab is simply gone")
APP.closeDocument(name_b)
check(set(V._tracked()) == {name_a}, "closing a tab drops it from _tracked")
V._tick()
check(True, "_tick survives a tab disappearing")

print("an unstamped tab is ADOPTED, not duplicated")
step_c = make_step("proj_c")
name_c = V._doc_name(step_c)
legacy = APP.newDocument(name_c)          # as an older hub would have left it
before = len(APP.imports)
V._open_project(step_c)
check(len(APP.docs) == 2, "adopting created no second document")
check(len(APP.imports) == before, "adopting re-imported nothing")
check(V._doc_prov(legacy) is not None, "the adopted tab now carries provenance")
check(V._doc_prov(legacy)["mtime"] == 0.0,
      "adopted with mtime 0 so the next tick refreshes it once")

print("the watch loop: stable-then-reload, and stamps only on success")
V._tick()                                  # mtime 0 != on-disk -> arms pending
check(len(APP.imports) == before, "the first tick after adopting only arms the check")
V._tick()                                  # stable -> reload
check(len(APP.imports) == before + 1, "the second tick reloads it")
check(abs(V._doc_prov(legacy)["mtime"] - os.path.getmtime(step_c)) < 1e-6,
      "the new mtime is stamped on the document")
before = len(APP.imports)
V._tick()
V._tick()
check(len(APP.imports) == before, "an unchanged file never reloads again")

print("a changed file reloads exactly once")
touch(step_c, "solid changed")
os.utime(step_c, (1e9, 1e9))               # force a distinct mtime
V._tick()
check(len(APP.imports) == before, "a changed file waits one tick for stability")
V._tick()
check(len(APP.imports) == before + 1, "then reloads")
V._tick()
V._tick()
check(len(APP.imports) == before + 1, "and does not reload again")

print("a failed reload is retried, not swallowed")
before = len(APP.imports)
touch(step_c, "solid again")
os.utime(step_c, (2e9, 2e9))
real_insert = sys.modules["ImportGui"].insert
boom = [1]


def flaky(stepp, docname):
    if boom[0] > 0:
        boom[0] -= 1
        raise RuntimeError("import blew up")
    real_insert(stepp, docname)


V.ImportGui.insert = flaky
V._tick()
V._tick()                                   # attempt 1 -> raises
check(abs(V._doc_prov(legacy)["mtime"] - 2e9) > 1.0,
      "a failed reload does NOT stamp the mtime")
V._tick()
V._tick()                                   # attempt 2 -> succeeds
V.ImportGui.insert = real_insert
check(abs(V._doc_prov(legacy)["mtime"] - os.path.getmtime(step_c)) < 1e-6,
      "the retry lands and stamps")

print("a code update re-adopts the PREVIOUS hub's tabs from .status")
# The failure this guards is silent: tabs left by an older hub carry no stamp, so without
# this the watch loop just stops following them and they never refresh again.
step_d = make_step("proj_d")
name_d = V._doc_name(step_d)
old_tab = APP.newDocument(name_d)              # a tab the previous hub owned
hb = os.path.join(TMP, "hb")
V._hub["heartbeat"] = hb
# ⚠ THE RECORDED MTIME IS OFF BY LESS THAN AN EPSILON, ON PURPOSE. .status used to be
# written with %.6f while real mtimes carry finer digits, so adoption stamped a value that
# compared unequal to the file and every adopted tab RE-IMPORTED its STEP on the next tick
# -- the exact cost adoption exists to avoid. The offset is written explicitly rather than
# by re-rounding a real mtime, because whether %.6f actually loses anything depends on the
# filesystem: this test passed in the canonical checkout and failed from the vendored copies
# for that reason alone. A fixed offset provokes it everywhere.
with open(hb + ".status", "w") as f:
    f.write("%s %s %s\n" % (name_d, repr(os.path.getmtime(step_d) - 3e-7), step_d))
    f.write("a_closed_project_viewer 1.0 %s\n" % step_d)   # tab is gone: must be ignored
before = len(APP.imports)
n = V._adopt_from_status()
check(n == 1, "adopted exactly the one tab that is still open")
check(V._doc_prov(old_tab) is not None, "the previous hub's tab is watched again")
check(abs(V._doc_prov(old_tab)["mtime"] - os.path.getmtime(step_d)) < 1e-6,
      "stamped with the mtime it already had, so nothing is re-imported")
check(len(APP.imports) == before, "adopting from .status imported no geometry")
V._tick()
V._tick()
check(len(APP.imports) == before, "and an up-to-date adopted tab does not reload")
check(V._adopt_from_status() == 0, "running it again adopts nothing (idempotent)")
APP.closeDocument(name_d)

print("shutdown detaches the timer so a reloaded copy can take over")
V._hub["timer"] = None
inbox = os.path.join(TMP, "inbox")
os.makedirs(inbox)
V.start_hub(inbox_dir=inbox, initial_step=None)
t = V._hub["timer"]
check(t is not None and t.started == V.POLL_MS, "start_hub armed a timer")
V.shutdown()
check(t.stopped, "shutdown stopped that timer")
check(V._hub["timer"] is None, "and dropped the reference, so a re-run arms a fresh one")
V.start_hub(inbox_dir=inbox, initial_step=None)
check(V._hub["timer"] is not None and V._hub["timer"] is not t,
      "a re-run after shutdown builds exactly one new timer")

print("every blocking load raises the busy marker")
# The marker is what stops a build mistaking a long import for a wedged watcher. An inbox
# open used to be the one blocking load that did not raise it -- measured at 35s of frozen
# heartbeat for a 128 MB assembly, which is well past the staleness limit.
V._hub["heartbeat"] = hb
inbox2 = os.path.join(TMP, "inbox2")
os.makedirs(inbox2)
V._hub["inbox"] = inbox2
step_e = make_step("proj_e")
with open(os.path.join(inbox2, "req.txt"), "w") as f:
    f.write(step_e)
seen = {}
real_open = V._open_project


def watched_open(stepp):
    seen["busy_during_open"] = os.path.exists(hb + ".busy")
    return real_open(stepp)


V._open_project = watched_open
V._scan_inbox()
V._open_project = real_open
check(seen.get("busy_during_open") is True,
      "an inbox-driven open raises .busy while it blocks")
check(not os.path.exists(hb + ".busy"), "and clears it afterwards")

print("the two code stamps agree")
sys.path.insert(0, os.path.dirname(_HERE))
import freecad_view as L                                            # noqa: E402
# ── the stamp must not depend on the checkout's line endings ─────────────────────
# Canonical cadkit holds these files LF, every vendored copy CRLF. Hashing raw bytes made
# identical code look "stale" across checkouts, and a stale hub gets its macro re-run.
_LF, _CRLF = bytes([10]), bytes([13, 10])
_eol = os.path.join(TMP, "eol")
for _kind, _nl in (("lf", _LF), ("crlf", _CRLF)):
    os.makedirs(os.path.join(_eol, _kind))
    for _n in ("freecad_viewer.py", "view.FCMacro"):
        _raw = open(os.path.join(_HERE, _n), "rb").read().replace(_CRLF, _LF)
        with open(os.path.join(_eol, _kind, _n), "wb") as _f:
            _f.write(_raw.replace(_LF, _nl))
_keep = L._HERE
_stamps = []
for _kind in ("lf", "crlf"):
    L._HERE = os.path.join(_eol, _kind)
    _stamps.append(L._code_stamp())
L._HERE = _keep
check(_stamps[0] == _stamps[1], "code stamp is the same for LF and CRLF copies of the code")
check(_stamps[0] == L._code_stamp(), "normalised stamp equals this checkout's stamp")

# ── claims are exclusive, and expire ────────────────────────────────────────────
_khb = L._HEARTBEAT
L._HEARTBEAT = os.path.join(TMP, "claim.heartbeat")
check(L._claim("launching", 60.0), "first launcher gets the launch claim")
check(not L._claim("launching", 60.0), "second launcher is refused while the claim is fresh")
os.utime(L._HEARTBEAT + ".launching", (1.0, 1.0))
check(L._claim("launching", 60.0), "a stale claim is taken over")

# ── a refresh is never fired at a hub that is mid-load ──────────────────────────
_fired = []
_saved = (L._refresh_hub, L._freecad_count, L._code_is_stale, L._freecad_exe,
          L._compat_marker, L._INBOX)
L._refresh_hub = lambda exe, step: _fired.append(step) or True
L._freecad_count = lambda: 1
L._code_is_stale = lambda: True
L._freecad_exe = lambda e=None: sys.executable
L._compat_marker = lambda: None
L._INBOX = os.path.join(TMP, "claim_inbox")
_s = make_step("busyproj")
with open(L._HEARTBEAT, "w") as _f:
    _f.write("x")
with open(L._HEARTBEAT + ".busy", "w") as _f:
    _f.write("open something")
check(L.show(_s) is True and not _fired, "stale code + BUSY hub: request queued, no refresh")
check(len(os.listdir(L._INBOX)) == 1, "the request waits in the inbox")
os.remove(L._HEARTBEAT + ".busy")
check(L.show(_s) is True and len(_fired) == 1, "stale code + idle hub: one refresh")
check(L.show(_s) is True and len(_fired) == 1, "a second build inside the window does not fire another")
(L._refresh_hub, L._freecad_count, L._code_is_stale, L._freecad_exe,
 L._compat_marker, L._INBOX) = _saved
L._HEARTBEAT = _khb

check(L._code_stamp() == V.code_stamp(),
      "launcher and hub hash the same bytes (a mismatch = a reload on every build)")

print("")
if FAILED:
    print("%d passed, %d FAILED" % (PASSED[0], len(FAILED)))
    for f in FAILED:
        print("  - %s" % f)
    sys.exit(1)
print("%d checks passed" % PASSED[0])
