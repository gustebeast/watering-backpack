# v2 main board — circuit design

One board. Drives both pumps, runs the ESP32, reads the joystick and tank level,
sounds the full alert. Fab **JLCPCB**; prefer Basic/Preferred parts.

Part numbers below are **candidates, not confirmed lines** — every one needs a
same-day stock check against JLCPCB's library before layout, per
`cadkit/PCB_README.md` §5. Where a requirement matters more than a specific part,
the requirement is stated first.

---

## Supply and the voltage that sets everything

Source is a **Makita 18 V LXT pack**: ~20 V fresh, ~15 V depleted, and it is the
*only* rail on the board. v1's 12 V buck is deleted (see DESIGN_V2 §6).

That 20 V ceiling is the number that drives part selection, and it is where v1's
BOM came closest to an error: parts rated 24 V max sit 4 V from the top of a fresh
pack before any switching spike. **Everything on the battery rail is specified
≥40 V.**

| rail | source | feeds |
|---|---|---|
| **VBAT** 15–20 V | pack, after fuse + reverse-polarity FET + TVS | pump FETs, level sensor |
| **3V3** | synchronous buck from VBAT | ESP32, joystick, buzzer, logic |

There is no 5 V rail. The level sensor takes 5–24 V, so it runs **straight off
VBAT** rather than forcing a third regulator — this is why its output must be
open-collector (below).

---

## 1. Pump drive — two low-side switches, no H-bridge

Each pump runs **one direction only**; direction is chosen by *which pump is
energised*. So each needs a single switched leg, not four quadrants. This is the
change that deletes the BTS7960.

**Per pump (×2):**

- **N-channel MOSFET** — **≥60 V V<sub>DS</sub>**, ≤10 mΩ R<sub>DS(on)</sub> at
  4.5 V V<sub>GS</sub>, DPAK/TO-263 on a copper pour.
  *Why 60 V and not 40:* a brushed motor is an inductive load, and the freewheel
  path clamps the spike to roughly V<sub>BAT</sub> + V<sub>f</sub>, but only while
  the diode is conducting. 40 V leaves ~20 V of margin over a fresh pack; 60 V
  leaves 40. The part costs the same.
  At 7.5 A and 5 mΩ this dissipates **~0.28 W** — against ~0.9 W for a BTS7960
  half. Both of v1's hot parts are gone.
- **Gate driver** — single-channel, ≥1 A, e.g. UCC27517 class. Not optional: a
  3.3 V GPIO switching a ~10 nC gate at 20 kHz spends too long in the linear
  region, and the loss lands in the FET.
- **Schottky freewheel diode** — ≥60 V, ≥15 A, low V<sub>f</sub>, D2PAK.
  Plain, not synchronous: it conducts only during off-time, and usage is mostly
  full-on, so the complexity of a second FET and a half-bridge driver buys little.
  Size it for the full 7.5 A anyway — at 50 % duty it carries ~3.75 A average and
  dissipates ~1.5 W, which is the board's largest single heat source.
- **Bulk electrolytic** close to each FET. Two pumps PWMing at 20 kHz pull real
  ripple current, and the loop that matters is battery → FET → pump → diode.

**Duty is capped in firmware to synthesise 12 V from an 18–20 V pack.** PWM
already chops the supply, so the motor does not care — but the cap must track the
pack voltage, which is what the divider below is for.

## 2. Logic supply

- **Synchronous buck, VBAT → 3.3 V, ~1 A**, **rated ≥40 V in**.
  Candidates: LMR14020 / LMR14030 (40 V), TPS54360 (60 V), MP4560 (55 V).
  **Explicitly rejected:** MP2315, AP63203 and the other 24 V-max parts — a fresh
  pack is 20 V and inductive spikes exceed that.
  1 A covers the ESP32's ~500 mA WiFi TX bursts with margin; average draw is
  ~100 mA.

## 3. MCU

- **ESP32-WROOM-32E.** Module, not bare silicon — crystal, antenna, shielding and
  FCC pre-certification for ~$2. Expect an *Extended* part at JLCPCB (small
  one-time setup fee).
- **Antenna keepout:** no copper under the antenna, module overhanging a board
  edge. And orient it **away from the tank** — five gallons of water is an
  excellent RF absorber, and measured RSSI already swung −29 to −79 dBm across one
  session.
- **6-pin programming header** with TX/RX/EN/IO0/3V3/GND and DTR/RTS for
  auto-reset. **No USB-C**: a connector is a water-ingress path on an outdoor
  device, and OTA covers everything after bring-up.

## 4. Sensing

- **Battery voltage divider → ADC1.** Two jobs: hold effective pump voltage
  constant as the pack sags, and expose sag in telemetry. *This would have
  diagnosed v1's mid-run slowdown in thirty seconds* — instead it cost a session
  and the leading theory (buck thermal foldback) was disproved only by touching
  the part. Scale 20 V → <3.3 V with margin; ~100 kΩ top leg so it costs no
  meaningful idle current.
- **Joystick** — 5-pin JST-PH to the existing KY-023, powered from **3V3, not 5 V**,
  so the output stays inside ADC range. **RC filter at the ADC pin**: this is the
  only noise defence available, since there is no joystick board to buffer at the
  source. ~1 kΩ + 100 nF (≈1.6 kHz corner — far above a hand, far below switching).
- **Tank level** — JST-PH to the XKC-Y25. Powered from **VBAT**; output configured
  **NPN open-collector** and pulled up to 3V3 on this board.
  *Open-collector is load-bearing:* the sensor runs at 18 V, and an
  open-collector output only ever pulls down, so the GPIO sees a safe level with
  no divider. Configured push-pull it would put 18 V into a pin.
- *Optional:* low-side shunt per pump → ADC, for current telemetry.

## 5. Alert

- **Active magnetic buzzer**, **3 V rated** (3V3 is the only logic rail), driven
  through a small NPN/NMOS — ~30 mA is beyond a GPIO.
  Active, not passive: it needs DC, not a driven waveform. Not a speaker: that
  needs an amplifier.
  Filling happens with the **pump off** and the user standing at the tank, so it
  does not have to out-shout anything; ~85 dB is ample. Sound port faces **down**
  (it is also a water path).

## 6. Protection

- **Inline ATC fuse** (10 A, existing 8110K3 + 7460K45) in the battery **+** lead,
  off-board.
- **Reverse-polarity P-FET** on VBAT — the Makita terminal is keyed, so this is
  insurance rather than necessity, but it is cheap and a miswire kills everything
  downstream.
- **TVS on VBAT** — standoff above 20 V, clamping well below the FETs' 60 V.
  SMBJ24A class (24 V standoff, ~39 V clamp) fits that window.
- **ESD on every connector a cable reaches** (joystick, level sensor) per
  PCB_README §5.

## 7. Connectors — terminal blocks, not JST

| net | part | pitch | note |
|---|---|---|---|
| battery in | 2-pos terminal | 5.08 mm | permanent — killswitch is at the Makita dock |
| pump A / pump B | 2-pos terminal each | 5.08 mm | 7.5 A each |
| joystick | 5-pos terminal | 3.5 mm | to the existing KY-023 |
| level sensor | 4-pos terminal | 3.5 mm | VBAT, GND, OUT, MODE |
| programming | 6-pin 2.54 mm header | | TX/RX/EN/IO0/3V3/GND + DTR/RTS |

**Why terminals over JST here.** JST earns its place where a joint is plugged and
unplugged often, or where space is tight. Neither applies: every one of these is
landed once at assembly and then left alone, and the board sits in a ~70 mm side
pocket with room to spare.

The decisive argument is PCB_README §3 — *"check that BOTH halves are in stock
before comparing anything else... a joint where you supply both halves is the case
the catalogue is worst at."* A JST joint is a header, a housing, crimp contacts
and a 2 mm crimp tool. **A terminal block is one part with no mating half.**

**Prefer push-in (spring-cage) over screw.** Two motors are bolted to the same
frame as this board; screw clamps back off under vibration and spring-cage does
not. It is also faster to land a wire with no screwdriver and no torque question.

**5.08 mm for the pump legs.** 3.5 mm parts are typically rated 8-10 A, which is
too close to 7.5 A to be comfortable. Signal connections are fine at 3.5 mm.

**Terminals provide NO strain relief** — a tugged cable pulls out of the clamp or
snaps at it, so the anchor is in the housing: `src/housing.py` puts a buttress rib
on the back plate under the board's bottom edge with a 10 × 7 mm tie slot through
it (`TIE_*`), and the cables reach it through a single down-facing chase
(`CHASE_Y0/Y1`) at y 134..158, between J3 and J4. Tie the bundle to that rib, not
to the terminals.

The chase is the ONLY opening in the bay and it faces down, because an opening is
a water path and the tank sits directly above it. The level sensor's lead leaves
through it too and climbs the outside of the housing — longer than going straight
up through the roof, which is the point.

**J1–J4 are rotated 180 degrees from where they want to be.** MEASURED, not
inferred: Phoenix's own STEP model for the PT-1,5 family
(`TerminalBlock_Phoenix.3dshapes/...PT-1,5-4-3.5-H...step`) has 43 mm3 of material
in the first 1.5 mm behind its **+Y** face and 184 mm3 behind its −Y face, of 197
possible. The hollow face is the wire entry, so entry is at footprint **+Y**, with
the solder pads at y=0.

J1–J4 sit at board y=−41 on the bottom edge at rot 0, so their entries face board
+Y — inward, which is world +Z, UP. Every power wire (battery and both pumps) plus
the joystick therefore leaves its connector running up the inside of the bay and
has to double back ~90 mm to reach the chase at the bottom, in a bay the board
fills in Y with ~11 mm of clearance under its edge. It also defeats the tie rib: a
tie there cannot relieve a cable that loops upward before it arrives.

They want **rot 180**. The body moves 1.4 mm toward the board edge (footprint y
−3.1..+4.5 becomes −4.5..+3.1), landing at y −45.5..−37.9 against an edge at −50,
so it fits — but it moves four courtyards and needs a re-route back to "0
unconnected, 0 violation(s)" before it can be believed.

**J5 is correct as placed.** At board y=+41 on the top edge, rot 0 already points
its entry at the edge. An earlier note in this repo's history claimed the opposite
— that J5 was the wrong one and J1–J4 were fine. That was inferred from the
footprint's fab outline, which does not mark the entry face. It is wrong; the
measurement above supersedes it.

**They are through-hole**, so either a THT assembly surcharge at JLCPCB or hand
soldering. Terminal blocks are large forgiving parts, so hand soldering is trivial
— the same call already made for the KY-023.

**`board_geom.HEIGHT` raises on a missing footprint**, deliberately, so that a part
with no height cannot be silently dropped from the CAD. Terminal footprints need
entries — project override via `Boards(height=...)` first, promoted into cadkit's
table once there is a drawing worth citing.

**Supply track widths sized from current, not left at the signal default** — the
pump legs carry 7.5 A.

---

## Status and what blocks what

`cadkit`'s new PCB tooling (`board_geom`, `board_check`, `kicad_geom`,
`kicad_silk`) **consumes a routed board** — it keeps KiCad and the CAD agreeing on
one board. It does not design one. So this circuit still has to become a KiCad
project: schematic → footprints → placement → routing → `geom.json`.

**That reorders the mechanical work.** PCB_README is explicit: *"Model from the
routed board, never from the placement table"* — a hand-typed placement can only
be checked against itself, and it always agrees. So the PCB pocket in
`src/pump_frame.py` cannot be drawn to a guessed outline; it waits on the routed
board's real geometry.

Open question before layout: whether the board is **generated programmatically**
(as public-steel-guitar does) or **hand-routed in the KiCad GUI**. KiCad 10.0 with
`python.exe` and `kicad-cli` is installed here, so either works.
