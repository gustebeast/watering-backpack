"""Printed-circuit boards in the CAD, READ BACK FROM THE ROUTED BOARD.

The KiCad side (`cadkit/kicad_geom.py`, run under KiCad's own Python) writes one
`<board>.geom.json` per routed `.kicad_pcb`: the outline polygon and its cutouts, the
laminate thickness, and for every footprint its position, rotation, side, F.Fab BODY
box, courtyard, through-hole pad extent -- plus the board-level silkscreen text. This
module is the CadQuery side: it turns that file into solids and answers the questions a
housing asks (where is that connector's mouth, how far do the tails hang, where does
the lead leave).

    from cadkit.board_geom import Boards
    BOARDS = Boards("elec/geom")                 # the folder the exporter writes to
    pcb   = BOARDS.solid("controller")           # laminate + every part body + THT tails
    env   = BOARDS.solid("controller", mated=True)   # ...with plugs seated: what to clear
    m     = BOARDS.mouth("controller", "J1")     # a panel connector's mouth, board frame
    ink   = BOARDS.silk("controller")            # the lettering, as its own part

`cadkit/board_check.py` then closes the loop: it probes the solid your project actually
places in the assembly against the same file, so a board the CAD draws wrongly -- a part
missing, a board mirrored, a cutout forgotten -- fails a gate instead of shipping.

WHY READ IT BACK AT ALL. A board modelled from a hand-typed table of anchors can only be
checked against the numbers it was typed from, and that comparison always agrees with
itself. On the project this came from it agreed while two panel connectors' bodies
stopped 0.54 mm short of the board edge (their COURTYARDS were flush; a courtyard is the
keep-out, not the part), a barrel jack faced along the board instead of out of the panel,
and a USB-C hole was cut 7.85 mm above its receptacle. None of that is visible in a copy
of the placements. All of it is visible in the routed board.

WHAT KiCad DOES NOT CARRY lives in the tables below, keyed by FOOTPRINT NAME, because it
is a fact about the PART and the same on every board in every project:

    HEIGHT    how tall the body stands above the board face          (required)
    TAIL      how far through-hole legs hang below it, 0.0 = SMD     (required by tails())
    THT_LEGS  one box per leg, for a part whose legs are far apart   (optional)
    PANEL     a panel connector's mouth, axis height, nose, opening  (optional)

A footprint with no HEIGHT raises rather than being left out: a part with no height is a
part the CAD would silently not draw. Add what your project needs by passing dicts to
`Boards(...)` -- they are laid OVER the shared tables -- and promote a new part's entry
here once it has a source worth citing.

FRAME. A board's own frame: centred on its Edge.Cuts bounding box in XY (+Y UP -- the
exporter flips KiCad's), underside at z = 0, front-side parts rising +Z. Place the
result in your assembly with an ordinary translate/rotate.
"""
from __future__ import annotations

import json
import math
import os

import cadquery as cq

from . import pcb as _pcb

# ── BODY HEIGHT above the board face, per footprint ──────────────────────────────────
# 0.0 means bare copper (a test pad, a solder jumper): nothing stands there, and saying
# so here keeps it out of every solid without a special case at each call site.
HEIGHT = {
    # chip passives, diodes, small-signal packages: package maximum heights
    "C_0402_1005Metric": 0.55, "R_0402_1005Metric": 0.50, "R_0603_1608Metric": 0.55,
    "C_0603_1608Metric": 0.90, "R_0805_2012Metric": 0.65,
    "C_0805_2012Metric": 1.45, "C_1206_3216Metric": 1.60, "C_1210_3225Metric": 1.80,
    "L_0603_1608Metric": 0.95, "Fuse_1206_3216Metric": 1.10,
    "Fuse_0805_2012Metric": 1.10,                # 0805 PTC: 1.0 max body + fillet
    "D_SMA": 2.20, "D_SMB": 2.45, "D_SOD-123": 1.10, "D_SOD-523": 0.75,
    "SOT-23": 1.30, "SOT-23-5": 1.45, "SOT-23-6": 1.10,
    "TO-252-2": 2.40,                            # DPAK: 2.38 max seated height
    "SOT-363_SC-70-6": 1.10,                       # TI DCK, SCES424O section 11
    "SOIC-8_3.9x4.9mm_P1.27mm": 1.75, "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm": 1.75,
    "TSSOP-14_4.4x5mm_P0.65mm": 1.20, "TSSOP-16_4.4x5mm_P0.65mm": 1.20,
    "TSSOP-20_4.4x6.5mm_P0.65mm": 1.20,
    "HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm_Mask2.75x3.43mm": 1.20,   # TI PWP max
    "QFN-16-1EP_3x3mm_P0.5mm_EP1.45x1.45mm": 0.80,
    "QFN-28-1EP_4x4mm_P0.4mm_EP2.4x2.4mm": 0.90,
    "QFN-68-1EP_8x8mm_P0.4mm_EP5.2x5.2mm": 0.90,
    "HVQFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm": 0.80,
    "Texas_RNX0012_VQFN-HR-12_2x3mm_P0.5mm": 0.90,          # TI RNX0012B, 0.8 +0.1
    "Crystal_SMD_3225-4Pin_3.2x2.5mm": 0.90,
    # inductors, relays, LEDs
    "L_Taiyo-Yuden_NR-30xx": 1.50, "L_Bourns-SRN6028": 2.80,
    "L_TDK_VLS6045EX_VLS6045AF": 4.50,
    "L_Sunlord_SWPA4030S": 3.00,                            # 4.0 x 4.0 x 3.0
    "Relay_DPDT_FRT5_SMD": 5.10,
    "Relay_DPDT_Omron_G6K-2F-Y": 5.20,                      # Omron: 10 x 6.5 x 5.2
    "XINGLIGHT_XL-5050RGBW": 1.60,                          # LCSC C7371891: 5.0x5.0x1.6
    "LED_0603_1608Metric": 0.80, "LED_0805_2012Metric": 1.10,   # TYPICAL chip-LED maxima, not one part's drawing
    # JST: top entry bodies, and side entry (cadkit.pcb carries the drawings' numbers)
    "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical": 7.0,
    "JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical": 7.0, "JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical": 7.0,
    "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical": 6.0,              # JST ePH p.2, top entry
    "JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical": 6.0,
    "JST_PH_B8B-PH-K_1x08_P2.00mm_Vertical": 6.0,
    "JST_PH_S4B-PH-SM4-TB_1x04-1MP_P2.00mm_Horizontal": 5.5,   # cadkit.pcb PH_SIDE_H
    "JST_PH_S6B-PH-SM4-TB_1x06-1MP_P2.00mm_Horizontal": 5.5,
    "JST_PH_S8B-PH-SM4-TB_1x08-1MP_P2.00mm_Horizontal": 5.5,
    "JST_XH_S4B-XH-SM4-TB_1x04-1MP_P2.50mm_Horizontal": 5.75,  # JST eXH p.4
    "JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal": 6.1,            # JST eXH p.5, side entry THT
    "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal": 2.95,  # JST SH side view: 6.25 x 2.95
    # headers and sockets
    "PinSocket_2x20_P2.54mm_Vertical": 8.5,        # the Pi-HAT socket's body = its standoff
    "PinHeader_1x20_P2.54mm_Vertical": 8.54,       # 2.54 insulator + 6.0 of pin
    "PinHeader_2x07_P1.27mm_Horizontal": 4.0,      # HX PZ1.27-2x7P: LISTED 3.9, no drawing
    "IDC-Header_2x07_P2.54mm_Horizontal": 10.0,    # ESTIMATE: generous standard body
    # panel connectors (see PANEL for their mouths)
    "Jack_6.35mm_Neutrik_NMJ4HCD2_Horizontal": 15.67,     # Neutrik's STEP: body top
    "Jack_6.35mm_Neutrik_NMJ6HCD2_Horizontal": 15.67,     # same housing, two more contacts
    "Kycon_KPJX-4S-S": 15.0,                       # 14.4 of body + the 0.6 top boss
    "USB_A_Receptacle_GCT_USB1046": 6.60,
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": 3.25,   # HRO's model: shell z 0.05..3.25
    "TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm": 10.5,
    # controls and contacts
    "Alps_RKJXT1F42001": 8.30,                     # the 17x17 CASE only, off Alps' 3D model;
                                                   # collar to 10.20, D-shaft 11.10..17.10
    "Xinyangze_YZF0002-38080-02": 3.80,            # pogo BARREL; the plunger is not in F.Fab
    # bare copper: no body
    "TestPoint_Pad_D1.5mm": 0.0, "TestPoint_Pad_D1.0mm": 0.0,
    "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm": 0.0,
    "SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm": 0.0,
}

# ── TAIL LENGTH below the board, per footprint; 0.0 = surface mount ──────────────────
# The other side of HEIGHT and needed for the same reason: KiCad does not carry it, and a
# part that has it goes straight through anything mounted against the board's underside.
# tails() REQUIRES an entry for every footprint on the board it is asked about, so a new
# part forces the decision instead of defaulting to "no tail" and being wrong silently.
TAIL = {
    "Alps_RKJXT1F42001": 3.5,                    # ten terminals + the position lug
    "PinHeader_1x20_P2.54mm_Vertical": 3.0,
    "IDC-Header_2x07_P2.54mm_Horizontal": 3.0,
    "PinHeader_2x07_P1.27mm_Horizontal": 1.5,    # ESTIMATE: ~3 mm tail less a 1.6 board
    "R_0402_1005Metric": 0.0, "C_0402_1005Metric": 0.0, "C_0805_2012Metric": 0.0,
    "R_0603_1608Metric": 0.0, "LED_0603_1608Metric": 0.0, "LED_0805_2012Metric": 0.0,
    "C_0603_1608Metric": 0.0, "R_0805_2012Metric": 0.0,
    "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical": 3.4, "JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical": 3.4, "JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical": 3.4,   # cadkit.pcb XH_POST_TAIL
    "TestPoint_Pad_D1.5mm": 0.0, "TestPoint_Pad_D1.0mm": 0.0,
    "C_1206_3216Metric": 0.0, "Fuse_1206_3216Metric": 0.0,
    "Fuse_0805_2012Metric": 0.0, "TO-252-2": 0.0,
    "SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm": 0.0,
    "XINGLIGHT_XL-5050RGBW": 0.0,
    "HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm_Mask2.75x3.43mm": 0.0,
    "Texas_RNX0012_VQFN-HR-12_2x3mm_P0.5mm": 0.0, "L_Sunlord_SWPA4030S": 0.0,
    "JST_PH_S6B-PH-SM4-TB_1x06-1MP_P2.00mm_Horizontal": 0.0,
    # through-hole JST posts stand 3.4 mm below the seating plane, top or side entry
    "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical": 3.4, "JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical": 3.4,
    "JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal": 3.4,
    "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal": 0.0,
    "Xinyangze_YZF0002-38080-02": 0.0,
}

# ── ONE BOX PER LEG, for a part whose through-hole legs are far apart ────────────────
# solid() draws a THT part's tails as ONE slab under the bounding box of its through-hole
# pads, which is right for a pin row and wrong for a part like a barrel jack: eleven lands
# spanning 13 x 18.6 mm make a slab whose empty corner collides with things no leg touches.
# A footprint listed here gets one box per leg instead:
#   (x, y, size_x, size_y) in the FOOTPRINT's own frame -- KiCad's, +Y down, as the
#   .kicad_mod has it -- each the HOLE the leg passes through.
THT_LEGS = {
    "Kycon_KPJX-4S-S": [
        (-2.9, -14.65, 0.6, 2.7), (2.9, -14.65, 0.6, 2.7),      # pins 1, 2
        (-2.5, -11.0, 0.6, 2.7), (2.5, -11.0, 0.6, 2.7),        # pins 3, 4
        (-7.8, -16.0, 0.6, 2.7), (7.8, -16.0, 0.6, 2.7),        # rear shell legs
        (-7.8, -7.5, 2.2, 2.2), (7.8, -7.5, 2.2, 2.2),          # front shell legs
        (0.0, -5.5, 2.2, 1.0),                                  # shell tab
        (-2.5, -7.5, 1.7, 1.7), (2.5, -7.5, 1.7, 1.7),          # the two plastic pegs
    ],
}

# ── PANEL CONNECTORS: the facts a panel is cut to ───────────────────────────────────
#   mouth   the mouth's direction in the footprint's OWN frame (KiCad's, +Y DOWN)
#   axis_h  mouth axis above the board's top face
#   nose    what stands IN FRONT of the F.Fab body, along the mouth: ("round", d, length)
#   opening the panel hole: ("round", d) | ("stadium", w, h) | ("rect", w, h[, z_centre])
#   mount   "rear": the body's shoulder bears on the panel's INSIDE and a nut clamps it;
#           "through": the body itself passes into the panel toward its outer face
# A rear-mount part may also carry:
#   stub    (d, length) in front of the shoulder, INSIDE the F.Fab outline
#   nut     (head A/F, head thickness, shank d, shank length)
#   clamp   the panel thickness the nut clamps
#   boss_d / cbore_d   the pad behind the panel, and the face counterbore for the nut
PANEL = {
    # Neutrik NMJ4HCD2, off Neutrik's STEP and drawing ST-NMJ4HCD2: bore axis 8.14 above
    # the PCB; a 3.0 mm O11.4 stub in front of the shoulder, which F.Fab draws as the last
    # 3.0 of the outline; a nose nut (2.05 hex head, A/F 11, on a 3.74 shank) that clamps
    # a 3.0..4.7 panel against the shoulder. cbore 15.6 = a thin-wall 11 mm socket + 0.2.
    "Jack_6.35mm_Neutrik_NMJ4HCD2_Horizontal": dict(
        mouth=(1.0, 0.0), axis_h=8.14, nose=None, stub=(11.4, 3.0),
        nut=(11.0, 2.05, 9.0, 3.74), clamp=4.0, boss_d=18.8, cbore_d=15.6,
        opening=("round", 11.8), mount="rear"),
    # the TRS sibling: Neutrik's D-series housing is common to both
    "Jack_6.35mm_Neutrik_NMJ6HCD2_Horizontal": dict(
        mouth=(1.0, 0.0), axis_h=8.14, nose=None, stub=(11.4, 3.0),
        nut=(11.0, 2.05, 9.0, 3.74), clamp=4.0, boss_d=18.8, cbore_d=15.6,
        opening=("round", 11.8), mount="rear"),
    # HRO TYPE-C-31-M-12, off HRO's model: shell 8.94 x 3.20 on the board, axis 1.65 up,
    # mouth = footprint +Y. The opening is OVERMOLD-sized (USB-C plug overmold max
    # 12.35 x 6.50), so a plug can follow a receptacle that sits back from the face.
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": dict(
        mouth=(0.0, 1.0), axis_h=1.65, nose=None,
        opening=("stadium", 12.8, 7.0), mount="through"),
    # Kycon KPJX-4S-S, drawing rev A17: body 16.0 x 13.4 x 14.4 (15.0 over the top boss),
    # axis 7.1 above the PCB, and a O12.9 x 4.0 nose in front of the body. Mouth = +Y.
    "Kycon_KPJX-4S-S": dict(
        mouth=(0.0, 1.0), axis_h=7.1, nose=("round", 12.9, 4.0),
        opening=("round", 13.5), mount="through"),
}

# A top-entry JST with its plug seated -- what a housing has to leave room for.
XH_MATED_H = 9.8          # JST's "assembled board height" for B*B-XH-A + XHP
PH_MATED_H = 8.0          # ESTIMATE: 6.0 body + the PHR's reach; confirm off JST ePH
# The protrusion below the board of an untrimmed 2.00/2.54 header post. Trimming is an
# assembly step nobody specifies, so the untrimmed case is the one that has to fit.
THT_TAIL = _pcb.XH_POST_TAIL                  # 3.4
# A SIDE-ENTRY connector's plug leaves through the board edge: how far the mated pair
# reaches past the socket body, by footprint-name prefix.
SIDE_PLUG_RUN = {"JST_PH_": _pcb.PH_PLUG_RUN, "JST_XH_": 7.5}

SILK_T = 0.02            # ink, drawn proud of the laminate so it is a solid of its own
SILK_CAP = 0.72          # a KiCad text "size" is its capital height; a font size is its em


def fp_name(fpid: str) -> str:
    """'Library:Footprint' -> 'Footprint' -- the key every table here uses."""
    return fpid.split(":")[-1]


def _box(w, l, h, x=0.0, y=0.0, z=0.0) -> cq.Workplane:
    """A w x l x h box CENTRED on (x, y, z)."""
    return cq.Workplane("XY").box(w, l, h).translate((x, y, z))


def _rot(v, deg):
    """A footprint-frame vector (KiCad, +Y down) into the board frame (+Y up), for a
    footprint at KiCad orientation `deg` (counter-clockwise as drawn on screen)."""
    t = math.radians(deg)
    lx, ly = v
    x = lx * math.cos(t) + ly * math.sin(t)
    y = -lx * math.sin(t) + ly * math.cos(t)
    return (round(x, 9), round(-y, 9))


class Boards:
    """Every routed board in one geom folder, with the part facts to draw them.

    `height`, `tail`, `tht_legs` and `panel` are laid OVER this module's tables, so a
    project adds its own parts (or overrides a figure) without editing cadkit. The merged
    tables are the instance's `.HEIGHT`, `.TAIL`, `.THT_LEGS`, `.PANEL`.
    """

    def __init__(self, geom_dir, *, height=None, tail=None, tht_legs=None, panel=None,
                 xh_mated_h=XH_MATED_H, ph_mated_h=PH_MATED_H, tht_tail=THT_TAIL,
                 side_plug_run=None):
        self.geom_dir = os.fspath(geom_dir)
        self.HEIGHT = dict(HEIGHT, **(height or {}))
        self.TAIL = dict(TAIL, **(tail or {}))
        self.THT_LEGS = dict(THT_LEGS, **(tht_legs or {}))
        self.PANEL = dict(PANEL, **(panel or {}))
        self.xh_mated_h, self.ph_mated_h, self.tht_tail = xh_mated_h, ph_mated_h, tht_tail
        self.side_plug_run = dict(SIDE_PLUG_RUN, **(side_plug_run or {}))
        self._cache = {}

    # ── reading ──────────────────────────────────────────────────────────────────
    def load(self, board: str) -> dict:
        """The routed board's exported geometry (see cadkit/kicad_geom.py). Cached: the
        file is read once per process."""
        if board not in self._cache:
            path = os.path.join(self.geom_dir, board + ".geom.json")
            with open(path, encoding="utf-8") as fh:
                self._cache[board] = json.load(fh)
        return self._cache[board]

    def footprint(self, board: str, ref: str) -> dict:
        for f in self.load(board)["footprints"]:
            if f["ref"] == ref:
                return f
        raise KeyError("%s has no %s -- was the board re-routed and re-exported?"
                       % (board, ref))

    def tails(self, board: str):
        """[(ref, fab, tail)] for every footprint with a body, tail 0.0 for surface mount."""
        out = []
        for f in self.load(board)["footprints"]:
            if not f["fab"]:
                continue
            name = fp_name(f["fpid"])
            if name not in self.TAIL:
                raise KeyError("%s: no TAIL for %s -- say whether it has through-hole legs, "
                               "because anything against the board's underside has to clear "
                               "them" % (board, name))
            out.append((f["ref"], f["fab"], self.TAIL[name]))
        return out

    def holes(self, board: str):
        """[(x, y, d)] the board's cut holes (its mounting holes), board frame."""
        out = []
        for h in self.load(board).get("holes", []):
            # the BOX centre, not the vertex mean: KiCad spaces an arc's points unevenly,
            # and the mean of one board's came out 0.8 mm off its hole
            xs, ys = [p[0] for p in h], [p[1] for p in h]
            out.append(((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0,
                        max(max(xs) - min(xs), max(ys) - min(ys))))
        return out

    def silk_boxes(self, board: str, side: str = "F"):
        """[(x0, x1, y0, y1)] of every board-level label on that side, in solid()'s frame."""
        return [tuple(lab["box"]) for lab in self.load(board).get("silk", [])
                if lab["side"] == side]

    # ── where things are ─────────────────────────────────────────────────────────
    def mouth(self, board: str, ref: str) -> dict:
        """Where a panel connector's mouth is, in the board frame: direction, the body's
        FRONT along that direction, the axis's position across it, and its height above
        the board top. Plus the part's PANEL facts as `spec`."""
        f = self.footprint(board, ref)
        spec = self.PANEL[fp_name(f["fpid"])]
        d = _rot(spec["mouth"], f["rot"])
        x0, x1, y0, y1 = f["fab"]
        if abs(d[0]) > 0.5:          # mouth along X
            front = x1 if d[0] > 0 else x0
            across = (y0 + y1) / 2.0     # the axis sits mid-body across the mouth
        else:
            front = y1 if d[1] > 0 else y0
            across = (x0 + x1) / 2.0
        return dict(dir=d, front=front, across=across, axis_h=spec["axis_h"], spec=spec)

    def _side_mouth(self, board, f):
        """(axis, lo, hi, origin, towards_hi) for a side-entry part: the mating axis is
        whichever of X/Y the footprint is turned onto, and the mouth is the end of the
        body FARTHER FROM THE ORIGIN -- the pad row sits behind the mouth. Read off the
        geometry rather than off `rot`, which only has to be right about which axis."""
        x0, x1, y0, y1 = f["fab"]
        ax = "x" if abs(round(f["rot"]) % 180 - 90) < 1e-6 else "y"
        lo, hi = (x0, x1) if ax == "x" else (y0, y1)
        o = f["x"] if ax == "x" else f["y"]
        if abs((hi - o) - (o - lo)) < 1.0:
            raise ValueError("%s %s: the footprint origin sits mid-body, so which end is "
                             "the mouth cannot be read from the geometry" % (board, f["ref"]))
        return ax, lo, hi, o, (hi - o > o - lo)

    def lead_exit(self, board: str, ref: str):
        """Where a LEAD LEAVES connector `ref`, in the board frame -- the point a cable
        should be drawn from.

        A top-entry part lets go straight up off its mated plug. A SIDE-ENTRY part does
        not: its plug leaves through the board edge, so the answer is the mouth end of
        the body pushed out by the mated plug's run, at the contact axis (mid-body in z).
        """
        f = self.footprint(board, ref)
        t = self.load(board)["thickness_mm"]
        name = fp_name(f["fpid"])
        h = self.HEIGHT[name]
        x0, x1, y0, y1 = f["fab"]
        # the BODY's centre, not the footprint origin: the origin sits at the pad row,
        # which for a side-entry part is at the back
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if "Horizontal" not in f["fpid"]:
            if name.startswith("JST_XH_"):
                h = self.xh_mated_h
            elif name.startswith("JST_PH_"):
                h = self.ph_mated_h
            return (cx, cy, t + h)
        run = self.side_plug_run.get(name[:7])
        if run is None:
            return (cx, cy, t + h)
        ax, lo, hi, _o, towards_hi = self._side_mouth(board, f)
        out = (hi + run) if towards_hi else (lo - run)
        z = t + h / 2.0
        return (out, cy, z) if ax == "x" else (cx, out, z)

    # ── solids ───────────────────────────────────────────────────────────────────
    def plate(self, board: str) -> cq.Workplane:
        """The laminate itself: the routed OUTLINE (an L where the board has a mounting
        ear) minus its cutouts -- not the outline's bounding box."""
        g = self.load(board)
        t = g["thickness_mm"]
        poly = g.get("outline_poly")
        if not poly:
            w, l = g["outline_mm"]
            return _box(w, l, t, z=t / 2.0)
        plate = cq.Workplane("XY").polyline([tuple(p) for p in poly]).close().extrude(t)
        for h in g.get("holes", []):
            plate = plate.cut(cq.Workplane("XY").polyline([tuple(p) for p in h]).close()
                              .extrude(t + 2.0).translate((0, 0, -1.0)))
        return plate

    def bodies(self, board: str, refs) -> cq.Workplane:
        """Just the named parts' bodies, in the board's own frame -- for a board the CAD
        draws in more than one colour (LEDs that should read as lit). Pair it with
        solid(skip=refs): two parts with no shared volume, which an overlap gate requires
        of anything drawn twice."""
        g = self.load(board)
        t, want = g["thickness_mm"], set(refs)
        out = None
        for f in g["footprints"]:
            if f["ref"] not in want or not f["fab"]:
                continue
            h = self.HEIGHT[fp_name(f["fpid"])]
            x0, x1, y0, y1 = f["fab"]
            z0 = -h if f["side"] == "B" else t
            b = _box(x1 - x0, y1 - y0, h, x=(x0 + x1) / 2.0, y=(y0 + y1) / 2.0,
                     z=z0 + h / 2.0)
            out = b if out is None else out.union(b)
        if out is None:
            raise KeyError("%s has none of %s" % (board, sorted(want)[:6]))
        return out

    def silk(self, board: str, side: str = "F"):
        """The board's own lettering as ONE part, in solid()'s frame -- separate, so a
        viewer can colour it ink-white against the mask and hide it. Read from the routed
        board, so it cannot say something the fab's ink does not. None where the board
        has no lettering on that side."""
        g = self.load(board)
        t = g["thickness_mm"]
        out = []
        for lab in g.get("silk", []):
            if lab["side"] != side:
                continue
            lines = lab["text"].split("\n")
            pitch = lab["size"] * 1.62                     # KiCad's line spacing
            for k, line in enumerate(lines):
                if not line.strip():
                    continue
                w = (cq.Workplane("XY").text(line, lab["size"] / SILK_CAP, SILK_T,
                                             halign="center", valign="center")
                     .translate((0.0, ((len(lines) - 1) / 2.0 - k) * pitch, 0.0))
                     .rotate((0, 0, 0), (0, 0, 1), lab["angle"])
                     .translate((lab["x"], lab["y"], t)))
                out += ([s for s in w.vals() if s.Volume() > 0]
                        if hasattr(w.val(), "Volume") else [])
        if not out:
            return None
        solids = []
        for s in out:
            solids += s.Solids()
        return cq.Workplane("XY").newObject([cq.Compound.makeCompound(solids)])

    def solid(self, board: str, mated: bool = False, omit: tuple = (),
              skip=()) -> cq.Workplane:
        """The board in its OWN frame: every part its routed F.Fab body extruded to its
        HEIGHT, through-hole tails below, and a panel connector's nose / stub / nut.

        `mated=True` stands every JST at its PLUGGED envelope -- taller for top entry,
        longer past the board edge for side entry: what a housing has to clear.

        `omit` and `skip` are NOT the same exclusion. `omit` = THIS INSTANCE DOES NOT FIT
        THAT PART (a DNP header on the last board of a chain): nothing draws it. `skip` =
        the part IS fitted and SOMEONE ELSE DRAWS IT (see bodies), so it can be another
        colour. Merge them and either a DNP part reappears or a part is drawn twice.
        """
        g = self.load(board)
        t = g["thickness_mm"]
        skip = set(skip)
        out = self.plate(board)
        missing = sorted({fp_name(f["fpid"]) for f in g["footprints"]
                          if f["fab"] and fp_name(f["fpid"]) not in self.HEIGHT})
        if missing:
            raise KeyError("%s: no HEIGHT for %s -- a part with no height is a part the "
                           "CAD would silently leave out" % (board, ", ".join(missing)))
        for f in g["footprints"]:
            if f["ref"] in omit:
                continue
            if not f["fab"] or f["ref"] in skip:
                continue
            name = fp_name(f["fpid"])
            h = self.HEIGHT[name]
            if mated and name.startswith("JST_XH_") and "Vertical" in f["fpid"]:
                h = self.xh_mated_h
            elif mated and name.startswith("JST_PH_") and "Vertical" in f["fpid"]:
                h = self.ph_mated_h
            if h <= 0.0:
                continue
            legs = self.THT_LEGS.get(name)
            if legs:
                # each leg where it is, not one slab under all of them (see THT_LEGS)
                for fx, fy, sx, sy in legs:
                    ox, oy = _rot((fx, fy), f["rot"])
                    wx, wy = (abs(v) for v in _rot((sx, sy), f["rot"]))
                    out = out.union(_box(wx, wy, self.tht_tail, x=f["x"] + ox,
                                         y=f["y"] + oy, z=-self.tht_tail / 2.0))
            elif f.get("tht"):
                tx0, tx1, ty0, ty1 = f["tht"]
                out = out.union(_box(tx1 - tx0, ty1 - ty0, self.tht_tail,
                                     x=(tx0 + tx1) / 2.0, y=(ty0 + ty1) / 2.0,
                                     z=-self.tht_tail / 2.0))
            x0, x1, y0, y1 = f["fab"]
            # a side-entry part grows ALONG the board when mated, not upward
            run = self.side_plug_run.get(name[:7]) if (
                mated and "Horizontal" in f["fpid"]) else None
            if run:
                ax, _lo, _hi, _o, towards_hi = self._side_mouth(board, f)
                if towards_hi:
                    if ax == "x":
                        x1 += run
                    else:
                        y1 += run
                else:
                    if ax == "x":
                        x0 -= run
                    else:
                        y0 -= run
            z0 = -h if f["side"] == "B" else t
            spec = self.PANEL.get(name)
            if spec and spec.get("stub"):
                # the body box stops at the SHOULDER; the stub is a cylinder, not the
                # body's full width -- drawn as a box it could never pass its panel hole
                m = self.mouth(board, f["ref"])
                sd, sl = spec["stub"]
                assert m["dir"][0] > 0.99, "a stubbed panel part must face +X"
                x1 = m["front"] - sl
                ax_z = t + m["axis_h"]
                out = out.union(cq.Workplane("YZ").circle(sd / 2.0).extrude(sl)
                                .translate((x1, m["across"], ax_z)))
                af, ht, shd, shl = spec["nut"]
                head0 = x1 + spec["clamp"]              # the head bears on the clamp's face
                out = out.union(cq.Workplane("YZ").polygon(6, af / math.cos(math.pi / 6))
                                .extrude(ht).translate((head0, m["across"], ax_z)))
                out = out.union(cq.Workplane("YZ").circle(shd / 2.0).extrude(shl)
                                .translate((head0 - shl, m["across"], ax_z)))
            out = out.union(_box(x1 - x0, y1 - y0, h, x=(x0 + x1) / 2.0,
                                 y=(y0 + y1) / 2.0, z=z0 + h / 2.0))
            if spec and spec["nose"]:
                m = self.mouth(board, f["ref"])
                kind, d, length = spec["nose"]
                assert kind == "round" and abs(m["dir"][0]) > 0.5
                sx = m["front"] if m["dir"][0] > 0 else m["front"] - length
                out = out.union(cq.Workplane("YZ").circle(d / 2.0).extrude(length)
                                .translate((sx, m["across"], t + m["axis_h"])))
        return out
