"""Watering Backpack — main build script.

Run from the repo root:
  py -3.12 -m src.build              # build all parts + assembly
  py -3.12 -m src.build --part NAME  # build only one part (faster iteration)
  py -3.12 -m src.build --list       # list available part names

Produces all printed-part STEPs and an assembly.step at the repo root.

Part modules are imported in dependency order. Each printable part exposes
a top-level Workplane variable; viz-only references come from src.viz and
are added to the assembly but not exported.

PARTS maps part name -> (Workplane, output path, note).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import cadquery as cq



def _build_counter_model(n: int):
    """Extruded number floating ~60 mm above the dock. Returns None if the
    text engine isn't available (a font hiccup must not break the build)."""
    try:
        return (
            cq.Workplane("XZ")
            .center(0, 80)
            .text(str(n), 30, 6)
        )
    except Exception:                                              # noqa: BLE001
        return None


def _label_model(text: str, x_center: float):
    """Small extruded label floating above a diagram station. Returns None
    on text-engine failure (must never break the build)."""
    try:
        return (cq.Workplane("XZ")
                .center(x_center, 55)
                .text(text, 10, 3))
    except Exception:                                              # noqa: BLE001
        return None

# Shared Archive/3D tooling: cq_colors (hex/0..255/name -> cq.Color) and the
# FreeCAD live-viewer launcher. Same pattern every CadQuery project here uses.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
from cq_colors import color
from freecad_view import show

from .helpers import bump_build_counter, heal
from . import viz
from . import battery_dock as _battery_dock_mod


# ── Assembly palette ─────────────────────────────────────────────────────────
# Picked to sit on a dark FreeCAD background without disappearing and to
# keep functionally-related parts colour-coordinated. Fill in as parts are
# added.
COLOR = {
    # Backpack-side family — slate blues for the load-bearing chassis.
    "battery_dock":    "#8FA8C0",   # lighter slate — the dock plate
    # "backpack_body":   "#6B8AAB",
    # "pump_mount":      "#4F6478",

    # Hose-side family — warm tans for the hand-held wand.
    # "hose_clamshell":  "#C4A56B",
    # "joystick_pocket": "#D6BC8C",

    # Visualization-only demo parts.
    "makita_terminal": "#E1C75D",   # yellow — OEM contact block (stands out)
    "mount_ref":       "#888888",   # mid-grey — V4 reference (clearly "not us")
}


# ── Printable parts ──────────────────────────────────────────────────────────
# Map of part name → (workplane, output filename, optional note).
# Empty for now; populated as we model each part.
PARTS: dict[str, tuple[cq.Workplane, str, str | None]] = {
    "battery_dock":   (_battery_dock_mod.battery_dock, "battery_dock.step",
                       "Makita 18V LXT battery dock (parametric)"),
}


def _export(name: str) -> None:
    obj, path, note = PARTS[name]
    cq.exporters.export(obj, path)
    suffix = f"  ({note})" if note else ""
    print(f"Wrote {path}{suffix}")


def _print_diff_report() -> None:
    """Print a compact numeric comparison between our parametric dock and
    the V4 reference, so each rebuild surfaces 'how close are we' without
    needing to eyeball anything."""
    from . import battery_dock as bd
    if viz.viz_mount_ref is None:
        return
    def _vol(wp) -> float:
        # Robust: empty boolean result (no material) has 0 solids and
        # .Volume() throws — report 0.0 in that case.
        if wp is None:
            return float("nan")
        try:
            return sum(s.Volume() for s in wp.val().Solids())
        except Exception:                                          # noqa: BLE001
            return 0.0

    try:
        v4_vol = viz.viz_mount_ref.val().Volume()
        our_vol = bd.battery_dock.val().Volume()
    except Exception as e:                                         # noqa: BLE001
        print(f"[diff] skipped: {e}", file=sys.stderr)
        return
    miss_vol = _vol(viz.viz_diff_v4_minus_parametric)
    extra_vol = _vol(viz.viz_diff_parametric_minus_v4)
    print("")
    print("  -- dock-vs-V4 diff -----------------------------------")
    print(f"    V4 volume          : {v4_vol:>11,.0f} mm3")
    print(f"    parametric volume  : {our_vol:>11,.0f} mm3")
    print(f"    V4 - parametric    : {miss_vol:>11,.0f} mm3   (red:  features missing)")
    print(f"    parametric - V4    : {extra_vol:>11,.0f} mm3   (blue: extras present)")
    if v4_vol > 0:
        match_pct = 100.0 * (v4_vol - miss_vol) / v4_vol
        print(f"    V4 covered by ours : {match_pct:>10.1f}%")


# ── Diagram station layout ───────────────────────────────────────────────────
# Each "diagram" gets its own copy of the dock and sits in its own X slot so
# they never overlap and can each be read independently. Station centres are
# spaced STATION_PITCH apart; the dock is 72 wide so this leaves a clear gap.
#
# The parametric dock is built X-centred (−36..+36). The V4 reference is
# corner-mounted (0..72, centre at +36). `_to_station` returns the X-shift
# that lands a body of centre `body_cx` at station index `i`.
STATION_PITCH = 120.0


def _station_shift(i: int, body_cx: float = 0.0) -> float:
    return i * STATION_PITCH - body_cx


def _print_battery_report() -> None:
    """Report the battery fit check: nominal overlap (should be ~0 = it
    slides in) and oversize contact volume (the load-bearing surface set)."""
    def _vol(wp) -> float:
        # Robust volume: an empty intersection (no overlap) has zero solids
        # and .Volume() throws — that's the *good* case, report 0.0.
        if wp is None:
            return float("nan")
        try:
            solids = wp.val().Solids()
            return sum(s.Volume() for s in solids)
        except Exception:                                          # noqa: BLE001
            return 0.0

    nom_v = _vol(viz.viz_battery_nominal_overlap)
    con_v = _vol(viz.viz_battery_contact)
    print("")
    print("  -- battery fit (oversize-overlap method) -------------")
    print(f"    nominal overlap    : {nom_v:>11,.1f} mm3   "
          f"(want ~0 => clears at {viz.BATTERY_FIT_GAP:.2f} mm/face)")
    print(f"    contact surfaces   : {con_v:>11,.1f} mm3   "
          f"(at +{viz.BATTERY_OVERSIZE:.2f} mm/face interference)")
    if nom_v > 5.0:
        print("    WARNING: nominal overlap > 0 — battery would NOT slide in!")


def _print_terminal_report() -> None:
    """Report terminal interference: dock material sitting where the seated
    643852-2 contact block needs to be. Must reach ~0 for the terminal to
    drop in (we carve a pocket where it doesn't)."""
    interf = viz.viz_terminal_interference
    v = float("nan")
    if interf is not None:
        try:
            v = sum(s.Volume() for s in interf.val().Solids())
        except Exception:                                          # noqa: BLE001
            v = 0.0
    print("")
    print("  -- terminal (643852-2) fit ---------------------------")
    print(f"    placement (x,y,z)  : {viz.TERMINAL_PLACE}")
    print(f"    interference       : {v:>11,.1f} mm3   "
          f"(dock material to clear; want ~0)")


def _export_assembly() -> None:
    """Compose the printable part + a row of independent diagram stations."""
    build_n = bump_build_counter()
    assembly = cq.Assembly(name="watering_backpack")

    # ── Station 0 — the printable part (full colour, no overlay) ────────────
    for name, (obj, _path, _note) in PARTS.items():
        col = COLOR.get(name)
        kwargs = {"color": color(col)} if col else {}
        assembly.add(obj, name=name, **kwargs)

    # ── Station 1 — accuracy vs V4 (grey V4 + red missing + blue extra) ─────
    s1 = _station_shift(1, body_cx=36.0)        # V4 centre is at +36
    if viz.viz_mount_ref is not None:
        assembly.add(viz.viz_mount_ref.translate((s1, 0, 0)),
                     name="acc_v4_ref", color=color("#888888"))
    if viz.viz_diff_v4_minus_parametric is not None:
        assembly.add(viz.viz_diff_v4_minus_parametric.translate((s1, 0, 0)),
                     name="acc_missing", color=color("#FF3030"))   # red
    if viz.viz_diff_parametric_minus_v4 is not None:
        assembly.add(viz.viz_diff_parametric_minus_v4.translate((s1, 0, 0)),
                     name="acc_extra", color=color("#3060FF"))     # blue

    # ── Station 2 — battery fit (grey dock + green contact surfaces) ────────
    s2 = _station_shift(2, body_cx=0.0)         # dock is X-centred
    dock_obj = PARTS["battery_dock"][0]
    assembly.add(dock_obj.translate((s2, 0, 0)),
                 name="bat_dock", color=color("#888888"))
    if viz.viz_battery_contact is not None:
        assembly.add(viz.viz_battery_contact.translate((s2, 0, 0)),
                     name="bat_contact", color=color("#30C050"))   # green
    # The oversized rail is NOT drawn (it would hide the dock); its
    # intersection — the green — is the informative part.

    # ── Station 3 — terminal fit (grey dock + placed terminal + interference) ─
    s3 = _station_shift(3, body_cx=0.0)         # dock + terminal are X-centred
    assembly.add(dock_obj.translate((s3, 0, 0)),
                 name="term_dock", color=color("#888888"))
    if viz.viz_terminal_placed is not None:
        assembly.add(viz.viz_terminal_placed.translate((s3, 0, 0)),
                     name="term_part", color=color("#E1C75D"))     # yellow terminal
    if viz.viz_terminal_interference is not None:
        assembly.add(viz.viz_terminal_interference.translate((s3, 0, 0)),
                     name="term_interf", color=color("#FF3030"))   # red = must clear

    # ── Station labels (float above each station) ──────────────────────────
    for i, label in [(0, "PART"), (1, "ACCURACY"), (2, "BATTERY FIT"),
                     (3, "TERMINAL FIT")]:
        lbl = _label_model(label, _station_shift(i, 0.0))
        if lbl is not None:
            assembly.add(lbl, name=f"label_{i}", color=color("#F0A878"))

    # 3D-text build stamp over station 0.
    counter_model = _build_counter_model(build_n)
    if counter_model is not None:
        assembly.add(counter_model, name="build_counter",
                     color=color("#F0A878"))

    _print_diff_report()
    _print_battery_report()
    _print_terminal_report()


    if len(assembly.children) == 0:
        print("assembly.step skipped - no parts to assemble yet", file=sys.stderr)
        return

    assembly.save("assembly.step")
    print(f"Wrote assembly.step  [build #{build_n}]")
    show("assembly.step")


def main() -> None:
    p = argparse.ArgumentParser(prog="src.build", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--part", help="Build only this part (skips assembly).")
    p.add_argument("--list", action="store_true", help="List part names and exit.")
    args = p.parse_args()

    if args.list:
        print("assembly")
        for name in PARTS:
            print(name)
        return

    if args.part:
        if args.part == "assembly":
            _export_assembly()
            return
        if args.part not in PARTS:
            print(f"unknown part: {args.part!r}. Use --list to see options.",
                  file=sys.stderr)
            sys.exit(2)
        # Heal the workplane before exporting individual parts too.
        name = args.part
        obj, path, note = PARTS[name]
        PARTS[name] = (heal(obj), path, note)
        _export(name)
        return

    # Heal every part before export.
    for name, (obj, path, note) in list(PARTS.items()):
        PARTS[name] = (heal(obj), path, note)

    for name in PARTS:
        _export(name)
    _export_assembly()


main()
