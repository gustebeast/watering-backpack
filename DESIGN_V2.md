# Watering Backpack v2 — Architecture

Status: **architecture settled, detailed design not started.** Written 2026-10-03.

v1 worked but had three compounding problems: the pump lost prime constantly, sand
from the pumice wrecked flow and threatened the pump, and the wiring was hand-soldered
flying leads. This records what v2 changes and — more importantly — *why*, since most
of these decisions came from measurements that are easy to lose.

---

## The v1 problems, diagnosed

### Priming

**Symptom.** After ingesting air, the pump would not re-prime. Recovery required
forcing water into the green line by mouth, repeatedly.

**Root cause.** The 4-way valve had to be reachable while wearing the pack, so it sat
at chest height. That forced the water path up, down, and up again. A diaphragm pump
moves air poorly, so re-priming means evacuating the whole line — but every dip holds
a water slug, and each slug adds static head the weak air-pumping cannot overcome.
Pouring water in worked because it restored a continuous column instead of making the
pump fight slug by slug.

**The thing that reframes it:** air ingestion is not a fault to prevent. The watering
method (fill the liner, then drain it dry) ingests air at the end of *every single
retract*, by design. Re-priming is a routine operation, not an exception.

### Filtering

Pumice fines in retract (the worse case) and fertilizer sediment in dispense. The v1
filter was unreachable while worn, and sat next to electronics so it could not be
rinsed. Cleaning it drained the pump, which then would not re-prime — the two problems
fed each other.

### Flow geometry

3/8" ID tubing on a 3.0 GPM pump is **8.7 ft/s**; suction lines want 2–3 ft/s. Four
5/8"→3/8" reducers compounded it. Roughly 6 psi of avoidable friction, and on the
suction side that directly erodes the margin against cavitation.

---

## v2 decisions

### 1. Two pumps, no reversing valve

Two Seaflo 42-series pumps in anti-parallel, sharing both lines through tees:

```
                      ┌─── Pump A (tank→pot) ───┐
  Tank ──── tee ──────┤                         ├────── tee ──── Green line ──── wand
                      └─── Pump B (pot→tank) ───┘
```

One wand. The idle pump's internal check valves seal its branch — validated in the v1
BOM note: *"diaphragm pump check-valves block flow when off, no siphon."*

**Why not reverse the pump:** a diaphragm pump's check valves are passive. Reversing
motor polarity spins the motor backwards but does not reverse flow. No diaphragm pump
is bidirectional; this is structural, not a sourcing problem.

**Why not solenoid valves:** cheap solenoids are pilot-operated and need 3–7 psi of
differential to open. At the moment of switching the differential is zero, so they
never open. Direct-acting valves work at zero differential but are expensive and draw
continuous holding power at this bore.

**Why not motorize the existing Farady X-port valve:** it is a car AC/heater valve,
designed for ~2 actuations per year. v2 would actuate it ~60 times per watering
session. It is already stiff enough to be hard to turn by hand after sitting, and dry
lube did not fix it — that is a duty-cycle mismatch of ~3 orders of magnitude, not a
lubrication problem. Motorising it relocates the failure to worn seats, stall
currents, and a sheared coupler. A purpose-built motorized ball valve is the same
ball-and-seat technology and would need two 3-way units (a 5/8"-barb motorized 4-way
X-port is not readily sourced), which needs the same two tees anyway.

Cost: **+$75, +~1.2 kg**, accepted.

**Open risk:** each tee has a branch to the idle pump. Those stay water-filled via the
check valves, but must be oriented so they cannot collect an air pocket. This system
ingests air every cycle, so air traps matter more here than in a normal install.

### 2. Flip the orientation — tank above pumps

Not mainly about flooding the inlet. A **dry diaphragm chamber primes terribly; a wet
one primes well.** Tank-above-pump keeps the chambers wet between sessions, which
attacks the root of the re-prime problem.

Note the limit: with the pumps fed from the tank only in dispense, retract still lifts
from pots at knee height (~1.5–2 ft). Flipping solves dispense priming structurally
and makes retract priming merely easier.

### 3. Tank outlet — Uniseal

The Scepter's 44 mm opening is too small to get a hand inside, so a conventional
bulkhead (nut on the inside) is out. A **Uniseal** installs entirely from outside:
drill, work the seal in, push rigid pipe through. Standard on IBC totes and sealed
barrels, and holds far more head than 5 gallons. Scepter walls are flat enough.

Fallback if the Uniseal does not suit: keep the top-routed dip tube and add a **foot
valve** at its bottom so the column cannot drain back. Less robust — a slightly leaky
foot valve loses prime overnight — but needs no modification to the tank.

### 4. Filter — printed, sealed, self-backflushing

Mounted partway along the **green line**, on the frame where the line leaves the pack
(not dangling on the hose, which would snag and adds a suction-side joint that could
pull air).

The green line is the right place because it is the only line that is *both*
bidirectional *and* connected to every dirty source:

| operation | path | filter direction |
|---|---|---|
| retract from pot | sand → filter → pump → tank | filtering |
| fertilizer draw | fertilizer → filter → pump → tank | filtering |
| dispense | tank (pre-filtered) → pump → filter → pot | **backflushing** |

So the pump never sees unfiltered water, and **every fill backflushes what the
previous drain collected.** Sand migrates forward one pot per cycle — pumice fines
returning to pumice — and never accumulates. No cleaning step needed between pots.
The tank line only ever carries already-filtered water, so the pump's 50-mesh inlet
strainer is redundant. One filter, total.

Spigot water goes to the tank through its own separate fill line and bypasses the
filter entirely; municipal water is clean enough. Revisit only if filling from a rain
barrel.

**Geometry is constrained by backflushing.** A Y-strainer or spin-down collects debris
in a sump *below* the flow path, deliberately, so reverse flow does not re-entrain it
— they would filter and never self-clean. v2 needs a **straight-through cylindrical
screen with no dead volume**, so reverse flow sweeps the cake off the mesh face.

Sizing, for 3 GPM (11.55 in³/s) at ≤1 ft/s face velocity:

- open area needed: **0.96 in²** (~9× the 3/8" line bore, so negligible restriction)
- 0.25 mm slots on 0.65 mm pitch = 38% open → **2.5 in² gross**
- → **1" diameter × 0.8" long** slotted cylinder

Printed on a 0.2 mm nozzle: slots **≥ one nozzle diameter** (0.2–0.25 mm) or the
slicer drops them; 0.4 mm walls between. 0.25 mm ≈ **60 mesh**, finer than the pump's
own 50-mesh strainer. Build it wedge-wire style — vertical slots tied by solid rings
top and bottom — so the ribs are supported and it prints without supports.

**Sealed, not openable.** A threaded joint on the suction line is an air-leak path,
and priming is the headline problem. Opening it also drains that section, which is one
of the things that forced mouth-priming in v1. The housing is a cheap printed
consumable: if backflushing ever fails to clear it, print another. This is a bet that
backflushing works — and the cycle backflushes it on every fill.

Barbs: **3/8" on the pot side** (fixed by the inner-pot tube), **5/8" on the pump
side**. The housing is the transition.

### 5. Tubing — 5/8" everywhere except the probe

The 3/8" constraint is only the probe that goes down the inner-pot channel. The main
run goes to 5/8", cutting ~6 psi of friction and one reducer instead of four.

### 6. Electronics

**Delete the Pololu D42V110F12 buck.** It is the leading suspect for the
"slows down after a few seconds at full speed" fault: 12V/9A against a 7.5 A pump
peak, in a sealed box with no heatsink and no airflow — the v1 BOM itself warned
*"add a heatsink / ensure airflow."* Pololu bucks thermally fold back, which matches
both the symptom and the timescale, and explains why telemetry showed commanded duty
pinned at 255 while the pump slowed. **Not yet confirmed** — see open questions.

Instead, drive the pumps straight off the Makita pack through the BTS7960 and cap duty
to synthesize 12 V. PWM already chops the supply, so the motor does not care. This
deletes the hottest and most expensive ($60) part in the box.

**Add battery voltage sense** (divider → spare ADC) to hold effective voltage constant
as the pack drains, and to expose sag in telemetry. Would have diagnosed the slowdown
in thirty seconds.

**One BTS7960 drives both pumps:** pump A between M+ and GND, pump B between M− and
GND. `RPWM` runs A, `LPWM` runs B, never both — the same structure the firmware had
before it was made forward-only.

**PCBA instead of hand-soldered flying leads.** v1's "wires soldered to boards" is a
latent reliability problem on a device that gets carried, shaken, and splashed.

### 7. Firmware

The joystick finally works as originally intended: **forward = dispense, back =
retract**, because direction is now an electrical choice rather than a hand-turned
valve. Remove the forward-only restriction added in v1.

Carry over from v1, all of it still relevant: the K-of-N engage vote, hysteresis,
median-based centre calibration, WiFi telemetry, OTA, and the persistent disarm.

---

## Open questions

1. **Confirm the buck thermal theory.** Run continuously into a bucket for 60 s and
   see whether it fades; if so, feel the buck (it will be hot). This decides whether
   deleting the buck actually fixes the slowdown or just removes a part.
2. **PCBA fab.** JLCPCB? Their assembly library constrains part selection enough that
   picking the fab after choosing parts means redoing work. Also: keep the ESP32
   module or go bare chip, and connector family (`cadkit/pcb.py` already supports
   JST-PH side-entry).
3. **Makita pack capacity**, for runtime estimates.
4. **Uniseal size** against the Scepter wall, once a panel is measured.
5. **Ramp / dose metering.** v1's 1000 ms ramp made "feather the trigger for small
   plants" work; it was reverted to 106 ms while chasing the slowdown. If the buck
   turns out to be the cause, the slow ramp should come back.

---

## Carried over unchanged from v1

Seaflo SFDP1-030-055-42 pumps (12 V, 3.0 GPM, 55 psi), Makita 18 V pack + 643852-2
terminal, Traco TSR 1-2450E for logic 5 V, KY-023 joystick, BTS7960, ATC fuse holder +
10 A fuse, Scepter 5 gal can, Stansport frame, separate spigot fill line.

**Dropped:** Farady 4-way X-port valve, Pololu D42V110F12 buck, 5/8"→3/8" reducers
(×4 → ×1), pump inlet strainer (redundant given the green-line filter).
