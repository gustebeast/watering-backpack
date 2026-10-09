"""Ray traced pictures for the viewer page, from the graphics card.

A browser cannot use a card's ray-tracing hardware. Blender's renderer (Cycles) can,
and denoises on it too, so the page's top lighting level asks THIS for its picture:
the local server keeps one Blender running in the background with the model loaded
(`trace_blender.py` is the half that runs inside it) and hands it each view the page
has come to rest on. A picture of the pedal steel (1.2M triangles) at window size
takes about a third of a second on an RTX card; the first one after a build also pays
for loading the model, a few seconds.

Blender is found, not installed: `CADKIT_BLENDER` if set, else `blender` on the PATH,
else the usual install folders. Without one the page simply does not offer the level,
and a published page (no local server) never does.
"""

from __future__ import annotations

import glob
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time

SCRIPT = pathlib.Path(__file__).with_name("trace_blender.py")
MARK = "@@trace "
IDLE_S = 600                    # a Blender nobody has asked in this long is let go
MAX_PX, MAX_SAMPLES = 4096, 1024


def find_blender():
    """The Blender to run, or None."""
    env = os.environ.get("CADKIT_BLENDER")
    if env:
        return env if os.path.isfile(env) else None
    found = shutil.which("blender")
    if found:
        return found
    spots = []
    for var, sub in (("LOCALAPPDATA", "Programs/Blender/*/blender.exe"),
                     ("ProgramFiles", "Blender Foundation/*/blender.exe")):
        if os.environ.get(var):
            spots += glob.glob(os.path.join(os.environ[var], sub))
    spots += glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender")
    return sorted(spots)[-1] if spots else None          # the newest by name


class Tracer:
    """One Blender for one model folder. `picture(view)` is safe to call from many
    request threads: they queue, and a view that a newer one has overtaken while it
    waited is dropped (None) instead of rendered."""

    def __init__(self, model_dir):
        self.glb = pathlib.Path(model_dir) / "assembly.glb"
        self.out = pathlib.Path(tempfile.gettempdir()) / ("cadkit_trace_%d.jpg" % os.getpid())
        self.lock = threading.Lock()
        self.proc = None
        self.loaded = None          # the model file's time when Blender last read it
        self.newest = 0
        self.used = 0.0
        self.info = {}
        self.blender = find_blender()

    available = property(lambda self: self.blender is not None)

    # ── the process ──
    def _reply(self):
        for line in self.proc.stdout:
            if line.startswith(MARK):
                return json.loads(line[len(MARK):])
        raise RuntimeError("Blender ended")

    def _ask(self, **q):
        self.proc.stdin.write(json.dumps(q) + "\n")
        self.proc.stdin.flush()
        r = self._reply()
        if not r.get("ok"):
            raise RuntimeError(r.get("error", "the tracer failed"))
        return r

    def _start(self):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            [self.blender, "--background", "--factory-startup", "--python", str(SCRIPT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=flags)
        self.info = self._reply()           # {"ready": true, "device": "OPTIX", ...}
        self.loaded = None
        threading.Thread(target=self._reap, daemon=True).start()

    def _stop(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            p.stdin.close()                 # it ends when its input does
            p.wait(5)
        except Exception:
            p.kill()

    def _reap(self):
        while True:
            time.sleep(30)
            with self.lock:
                if self.proc is None:
                    return
                if time.time() - self.used > IDLE_S:
                    self._stop()
                    return

    def _ready(self):
        """With the lock held: Blender running, and holding the model as it is now."""
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        t = self.glb.stat().st_mtime_ns
        if t != self.loaded:
            self.info.update(self._ask(op="load", glb=str(self.glb)))
            self.loaded = t
        self.used = time.time()

    # ── what the server calls ──
    def warm(self):
        """Start Blender and load the model now, so the first picture need not wait."""
        def go():
            try:
                with self.lock:
                    self._ready()
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def picture(self, view):
        """JPEG bytes of the view (the page's own description of what it shows), or
        None if a newer view arrived while this one waited its turn."""
        self.newest += 1
        mine = self.newest
        with self.lock:
            if mine != self.newest:
                return None
            try:
                self._ready()
                q = dict(op="render", out=str(self.out).replace("\\", "/"),
                         w=max(16, min(int(view["w"]), MAX_PX)),
                         h=max(16, min(int(view["h"]), MAX_PX)),
                         samples=max(1, min(int(view.get("samples", 64)), MAX_SAMPLES)),
                         cam=[float(x) for x in view["cam"]][:16], fov=float(view["fov"]),
                         near=float(view.get("near", 1)), far=float(view.get("far", 20000)),
                         hidden=[str(n) for n in view.get("hidden", ())],
                         poses={str(n): [float(x) for x in m][:16]
                                for n, m in (view.get("poses") or {}).items()},
                         printed=bool(view.get("printed")))
                for k, n in (("sun", 3), ("bg", 3)):
                    if k in view:
                        q[k] = [float(x) for x in view[k]][:n]
                if "sun_strength" in view:
                    q["sun_strength"] = float(view["sun_strength"])
                self._ask(**q)
                self.used = time.time()
                return self.out.read_bytes()
            except Exception:
                self._stop()                # start clean next time
                raise
