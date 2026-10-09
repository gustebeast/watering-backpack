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

One wand. The idle pump's internal check valves seal its branch when **nothing is
running** — validated in the v1 BOM note: *"diaphragm pump check-valves block flow
when off, no siphon."*

⚠ **That note does not cover the case this arrangement actually creates, and the
sentence above used to be written as if it did.** The v1 note is about a STATIC
system: gravity trying to push water out of a wand below the tank, which a check
valve holds. Anti-parallel is not that case. Plumbed head to tail, a running pump A
raises pressure at the tee that is pump B's *inlet* and lowers it at the tee that is
pump B's *outlet* — a differential in pump B's **forward** direction, which is the
direction its check valves exist to pass. Two pumps in *parallel* would see the
reverse differential the v1 note describes; anti-parallel inverts it.

The risk is therefore not a siphon but a **bypass**: part of pump A's flow
short-circuiting through pump B's chambers instead of going down the wand. What
limits it is that a stopped diaphragm pump is a poor flow path, and nothing here has
measured how poor. **Built without a check valve, deliberately** — the cure costs
pressure drop, two more joints on a system whose headline problem is priming, and two
more air traps, against a fault that costs flow rate rather than function. The
measurement that would settle it is written down in `WORK_V2_PUNCHLIST.md` finding 12
so it does not have to be re-derived on the day.

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

**Deck height is set by a hose, not by the pumps.** The rails sit at z=150, not
the ~124 that merely clears the 119 mm pumps. Pump B's inner port has its swivel
nut reaching into pump A's half, so that line cannot run forward at port height
without passing through pump A — measured at 8190 mm3 by `tools/check_plumbing.py`.
Its only way out is OVER the pumps, and a 19 mm line needs 9.5 mm either side of
its centreline. The alternative was a ~21 mm gap *between* the pumps, which buys
the same clearance out of WIDTH; width is the scarce axis (the posts already
overhang the 340 mm shelf) and height is not, so it came out of height.

### 3. Tank outlet — Uniseal

The Scepter's 44 mm opening is too small to get a hand inside, so a conventional
bulkhead (nut on the inside) is out. A **Uniseal** installs entirely from outside:
drill, work the seal in, push rigid pipe through. Standard on IBC totes and sealed
barrels, and holds far more head than 5 gallons. Scepter walls are flat enough.

Fallback if the Uniseal does not suit: keep the top-routed dip tube and add a **foot
valve** at its bottom so the column cannot drain back. Less robust — a slightly leaky
foot valve loses prime overnight — but needs no modification to the tank.

### 4. Filter — two bought strainers at the tees, self-backflushing

**DECIDED 2026-10-05.** This section used to specify a *printed*, sealed,
self-backflushing screen on the green line, and `src/line_filter.py` built it. It is
now **the two 50-mesh inlet strainers that came with the pumps, one at each tee** —
`WORK_V2_PUNCHLIST.md` findings 13 and 13a, both closed. The argument below did not
change; what changed is that the owner backflushed one of the stock strainers and it
cleared itself, which is this section's own argument made about the *exact part*
rather than about a part like it. The printed screen, its housing, and the
`test_screen_slice` coupon are gone — recorded in `bom_consolidated.md` §7b and its
*Dropped* list.

#### Why a filter on the green line at all, and why it self-cleans

The green line is the only line that is *both* bidirectional *and* connected to every
dirty source:

| operation | path | filter direction |
|---|---|---|
| retract from pot | sand → filter → pump → tank | filtering |
| fertilizer draw | fertilizer → filter → pump → tank | filtering |
| dispense | tank (pre-filtered) → pump → filter → pot | **backflushing** |

So the pump never sees unfiltered water, and **every fill backflushes what the
previous drain collected.** Sand migrates forward one pot per cycle — pumice fines
returning to pumice — and never accumulates. No cleaning step between pots.

**Geometry is constrained by backflushing, and the stock strainer satisfies it.** A
Y-strainer or spin-down collects debris in a sump *below* the flow path, deliberately,
so reverse flow does not re-entrain it — those filter and never self-clean. What is
needed is a straight-through cylindrical screen with no dead volume, which is exactly
what the 51S01 is, and the owner's backflush test is the proof rather than the
expectation.

#### Where they go, and which way round

One at each tee, inline on the tee's third leg: the green tee's leg down to the wand,
the tank tee's leg up to the Uniseal. Not dangling on the hose — that snags and adds
a suction-side joint that can pull air.

⚠ **They are DIRECTIONAL, and the handedness is set by the paragraphs above.** The
51S01 filters male→female and cleans female→male (owner, measured on the part). The
filter must collect on the drain and be swept clean on the fill, so the **male** end
faces whatever each strainer protects against — and that is not the same side at the
two tees:

- **Green tee: male toward the POT.** Dirty water enters at the wand on retract, so
  retract collects and dispense sweeps the debris back out toward the pot.
- **Tank tee: male toward the TANK.** What that one protects is **pump A**, and what
  threatens pump A is the tank's own settled sediment, drawn in on fill. So fill
  collects and drain sweeps it back into the tank to settle out again.

Either one fitted backwards runs its collecting stroke as a cleaning stroke and sweeps
the debris *toward* the pump instead of away from it.

Both therefore show their **female** end to the tee, and that is what makes the
fittings come out even — one male-threaded tee leg screws straight into each, with no
adapter and no hose stub. Worked through, with the fitting on each end, in finding 13a.

#### What the change costs, named

- **50 mesh instead of ≈60 mesh.** The printed screen's 0.25 mm slots were slightly
  finer than the strainers' 50 mesh. Accepted: the thing being excluded is pumice sand
  and fertilizer grit, and one mesh step does not decide whether the pump survives it.
- **Two tees have to be bought** — barb × barb × 1/2"-14 MNPT, 1/2" barbs. They were
  never on the BOM anyway (finding 14, closed), so this decision is what finally put
  them there rather than an extra cost it created.
- **The strainers' length is not measured, and it now matters.** Each one occupies
  inline length on its tee's third leg. The model gives the green leg 124 mm of
  straight and the tank leg about 100 mm. Finding 16.
- **No longer sealed.** The printed housing was deliberately unopenable, because a
  threaded joint on a suction line is an air-leak path and priming is the headline
  problem. Each strainer adds two threaded joints on a suction line. Accepted, and it
  is the real cost of this change: they are tapered pipe threads with tape, not the
  twist-off cap the argument was against, and the system already re-primes every cycle
  by design. Watch these two joints first if priming regresses.

**Spigot water** goes to the tank through its own separate fill line and bypasses the
filter entirely; municipal water is clean enough. Revisit only if filling from a rain
barrel.

**Barbs: 3/8" on the pot side** (fixed by the inner-pot tube), **1/2" everywhere
else**. The transition is the owned McMaster 5346K56 (1/2 NPT female × 3/8" barb) on
the green strainer's male end — the job the printed housing used to do. (This said
5/8" until 2026-10-05; see §5.)

### 5. Tubing — 1/2" everywhere except the probe

The 3/8" constraint is only the probe that goes down the inner-pot channel, and that
one is the owner's: *"the green line has to stay 3/8 but all the other lines can
change."* The main run is **1/2"**.

⚠ **This section used to read "5/8" everywhere except the probe" and it was wrong
by the time anyone read it.** The 5/8" was an inference from the friction argument
— nobody ever asked for it — and §2 of `bom_consolidated.md` had already decided
the other way, with reasons, when it chose the pump-port fitting. **The owner has
now bought that fitting**: SEAFLO SFFN1-1220-01, 1/2"-14 FNPT × **1/2" barb**,
five of them, four fitted and one spare. A 5/8" tube does not grip a 1/2" barb, so
the main run is 1/2" and the question is closed by a purchase rather than by an
argument. The contradiction had been sitting in three files, flagged in two of them.

**The numbers, so the trade is on the record rather than implied.** At 3.0 GPM:

| ID | velocity | friction vs 3/8" |
|---|---|---|
| 3/8" (v1) | 8.71 ft/s | — |
| **1/2" (v2)** | **4.90 ft/s** | **3.9× lower** |
| 5/8" (not taken) | 3.14 ft/s | 11.3× lower |

So 1/2" captures the large majority of the available improvement — friction goes
as roughly d⁻⁴⋅⁷⁵, so most of it is won in the first step up. **The residual, named:**
4.90 ft/s is still above the 2–3 ft/s a suction line wants, which 5/8" would have
reached. What makes that acceptable here is that v2's runs are short, the tank sits
*above* the pumps so the suction is flooded (§2), and the pump's own port bore is
~13 mm ≈ 0.51" — the ports are a 1/2" restriction whatever the hose is, so 5/8"
tubing would have bought its margin everywhere except at the four places the flow
actually has to squeeze through. "One reducer instead of four" — the old §5's
headline claim — was exactly backwards: with 1/2" barb swivels on both ports of
both pumps, going 5/8" needs a step at **all four**.

### 6. Electronics — one PCBA

v1's hand-soldered flying leads are a latent failure on something carried, shaken and
splashed. v2 is a single assembled board; the joystick and level sensor stay as the
modules they already are, on connectors.

**The two-pump decision deletes the H-bridge.** Each pump now runs in exactly one
direction — direction is chosen by *which pump is energised*, not by polarity. So each
needs a single switched leg, not four quadrants: one N-channel MOSFET + gate driver +
Schottky freewheel diode. A BTS7960 half dissipates ~0.9 W at 7.5 A; a 3 mOhm 40 V FET
dissipates ~0.17 W. Both of v1's hot parts (buck and bridge) are gone.

**Main board**
- 2x MOSFET pump drivers (40 V, low Rds(on), DPAK on copper pour; gate driver, not a
  bare GPIO, at 7.5 A and 20 kHz). Plain Schottky freewheel rather than synchronous:
  it only conducts during off-time, and usage is mostly full-on.
- 18 V -> 3.3 V buck, **LMR14020SDDA**, 0.6 A drawn of a 2 A part. Rated **>= 36 V in**
  — a fresh Makita pack is 21 V and inductive spikes exceed that, so common 24 V-max
  parts are too close to the edge. Single stage; this also deletes the Traco TSR.
  ⚠ **NOT synchronous**, which this line claimed for months and which nearly cost the
  board. The LMR14020 has one high-side switch and needs an external **catch diode** —
  D6, a 60 V 3 A SMA Schottky — because without it the SW node is driven past its -3 V
  rating every cycle and there is no 3.3 V rail at all, so no MCU, no joystick and no
  gate drive. It was found by reading the datasheet's layout figure against the placed
  board rather than by any check, because nothing on a schematic looks wrong when a
  part is simply absent. The inductor is **10 uH / 4.6 A saturation**: the first choice
  saturated below the regulator's own 3.8 A current limit, and the fix ran *down* in
  inductance. Output capacitance is C4 + C19 = 44 uF nominal, which is what the
  datasheet's equation 13 needs once X7R's DC bias derate is allowed for — the
  dielectric is a stated requirement, not a preference, because the derate is the whole
  argument.
- ESP32-WROOM-32E module (crystal, antenna, shielding, FCC pre-cert; bare silicon buys
  nothing here)
- Battery voltage divider -> ADC: duty compensation as the pack drains, and sag visible
  in telemetry
- **Active magnetic buzzer** + small transistor (its ~30 mA is beyond a GPIO) for the
  tank-full alert. Not a speaker — that would need an amplifier. Filling happens with
  the pump OFF and the user standing at the tank, so ~85 dB is ample.
- Tank level input: 3.3 V pull-up for the sensor's open-collector output
- **RC filter on the joystick ADC input** — the only noise defence available, since
  there is no joystick board to buffer at the source
- TVS (**SMCJ24A**, 38.9 V max clamp — same clamp as the SMBJ24A it replaced, 1500 W and 200 A IFSM instead of 600 W and 100 A) and bulk electrolytics near the switches. The package was chosen by the reverse-polarity sum, not the transient one: see `elec/CIRCUIT.md` §6.
  ⚠ **The reverse-polarity P-FET is NOT on the built board.** It was called optional
  because the battery inlet was keyed; the inlet is now a screw terminal, which is not.
  The consequence and the backstop are written up in `elec/CIRCUIT.md` §6. It is
  **closed**: the crowbar is sized by I²t against the fuse, and the fuse is **F2 on
  the board** now rather than a holder in the lead, so the sum rests on a part this
  repo contains instead of on a condition imposed on whoever wires it up.
- **F2, a 10 A ATC blade fuse on the board** — Littelfuse 178.6165 FLR holder taking
  the ATC blade already owned (McMaster 7460K45). It cost 12 mm of board length and a
  bay re-layout; what it bought is that the reverse-polarity argument above is now a
  **board property**. What it gives up is protection of the dock-to-board harness,
  which is short and inside the sealed bay. **C21**, 10 µF at the pack pad, is the
  only charge in front of it.
- **F1**, a 30 V 200 mA resettable PTC, in series with the level sensor's VBAT feed —
  that lead leaves the sealed bay and climbs the outside of the case, so it is the one
  conductor that gets rubbed and pinched, with a Makita pack behind it.
- 6-pin programming header with DTR/RTS. **No USB-C** — a connector is a water-ingress
  path outdoors, and OTA covers everything after bring-up. Its silk reads
  `3V3 / GND / ESP_TX / ESP_RX / EN / IO0`: the old `TXD`/`RXD` matched every adapter's
  own labels, so wiring like-to-like wired output into output.
- Connectors — **screw terminal blocks, not XT30 or JST** (the reasoning is
  `elec/CIRCUIT.md` §7). ONE family across all five: Ningbo Kangnex WJ500V-5.08,
  5.08 mm throughout — 2-pin for J1/J2/J3 (pack, pump A, pump B), 5-pin for J4
  (joystick), 4-pin for J5 (level sensor), on Phoenix MKDS-3 footprints whose
  F.Fab outline is a strict superset of the WJ500V body. J1-J4 all leave the
  board's -Y edge, which faces down in the housing; J5 and J6 are on +Y.
  The earlier split (MKDS-3 screw for power, PT-1,5 3.5 mm push-in for signals)
  is gone: the user's requirement is any no-solder wire attachment, and two
  families bought one vibration property at the cost of a second drawing, a
  second wire range and a second entry-face rule.
- Optional: low-side shunt per pump -> ADC (would have diagnosed the v1 slowdown
  immediately)

**Joystick: keep the existing KY-023 module.** Measured noise on battery is sd 7-9
counts, which is healthy — the ~120-count noise that cost a session to diagnose was a
USB-tether artifact, not the wiper. There is no measured fault to justify replacing it.

Rejected, and why: a **hall-effect thumbstick** would remove wiper wear, but the fault
it fixes has not been observed here. **Industrial hall sticks** (APEM TS series) are
$120 with a 12-week lead. **An encoder + printed lever** would be fully reflowable and
sealed with a digital output, but cannot match a gimbal's compact bidirectional spring
return — and a printed flexure *creeps*, which would reintroduce centre drift, the exact
symptom that opened this investigation. Hall thumbsticks are also consumer repair parts,
not distributor stock, so none of this is PCBA-assemblable anyway.

**Wire all five KY-023 pins** even though only VRy is used — it costs nothing and leaves
SW available as a mode button. The 2.54 mm housing on the module end does not latch, so
**the printed mount must capture the connector** so it cannot vibrate loose. That is the
real fix for v1's flying leads; a new PCB was not required to get it.

### 7. Tank level — single full/not-full, non-contact capacitive

An **external capacitive sensor** (XKC-Y25 class) clamped to the *outside* of the tank
wall at the full line. Nothing penetrates the tank and nothing touches the water, which
sidesteps the 44 mm opening entirely — the binding constraint on every other approach.

- Powered **directly from the battery rail** (5-24 V spec covers the pack's 15-21 V), so
  it needs no 5 V rail — important, since the board now only makes 3.3 V.
- Configure the output **NPN open-collector** and pull it up to 3.3 V on the main board.
  The sensor runs at 18 V but an open-collector output only pulls down, so the GPIO sees
  a safe level with no divider. Push-pull mode would put 18 V into a GPIO.
- Printed bracket clamping it flat to the wall; consistent contact matters more than
  force, since a gap shifts sensitivity. Scepter HDPE is a few mm, well inside the
  0-20 mm range.

**Mount it slightly BELOW the true full line.** False positives are cheap (stop early,
look, carry on) but a false negative means overflow, and capacitive thresholds drift
with temperature. Tripping early gives margin in the direction that actually costs
something.

Rejected: a conductivity probe needs alternating-polarity excitation to avoid
electrolysis and still fouls as fertilizer salts film the electrodes — it drifts rather
than fails, so it would be diagnosed twice. A float switch is more reliable than either
but must pass through the 44 mm opening and needs a sealed-ish top plug. Non-contact
won on assembly simplicity, with the false-positive risk accepted explicitly.

This also simplifies the top plug back to just **vent + spigot fill line**.

### 8. Firmware

The joystick finally works as originally intended: **forward = dispense, back =
retract**, because direction is now an electrical choice rather than a hand-turned
valve. Remove the forward-only restriction added in v1.

Carry over from v1, all of it still relevant: the K-of-N engage vote, hysteresis,
median-based centre calibration, WiFi telemetry, OTA, and the persistent disarm.

---

## What checks this design, and what each one is for

Fifteen gates. Every one of them exists because something it now catches had already
got through, so the list below says what each was *written for* rather than what
it nominally covers. All exit non-zero on failure, so any of them works in CI.

`py -3.12 -m src.build` runs seven of them itself:

| gate | written because |
|---|---|
| overlap | parts that interpenetrate. The whitelist is three entries and each carries its measured volume; three more were dropped once measuring showed they were whitelisting 0.0 mm³ — i.e. standing ready to hide the first real clash |
| battery access | the pack could not be lifted out. It fits in the dock, and that is not the same thing: it needs 93 mm of lift |
| install/removal | the same question for the lid and the contact block, both of which can fit where they end up and still be impossible to get there |
| pump mount | the pumps bolted to nothing at all. Checks all 8 holes are open, land in wood, and that the feet still touch the floor |
| board retention | checked BOTH ways, because one way is not a check: the board must not lift straight off (the +Y lip holds 21 mm³ of it) and must come out after sliding 2 mm toward -Y. A board that cannot be got out is one you cut up to reflash |
| board seating | the board must be WHERE ITS OWN MOUNTING HOLES ARE. It was not, on both axes at once, and neither error was an overlap: the ESP32's antenna overhang shifted it 2.06 mm off the drilled holes in Y and the lead tails floated it 3.4 mm clear of its bosses in X |
| routed-board agreement | the CAD must draw the board that was actually routed, not a typed placement. PCB_README: *"a hand-typed copy can only be checked against itself, and it always agrees"* |

Standalone:

| gate | written because |
|---|---|
| `tools/check_v2_overhangs.py` | it was checking 3 of the 5 parts shipped, and its classifier judged a 270° arc by one sampled normal. Now enumerates `printed_parts()` and takes the pose from there, so coverage and build direction cannot drift from the exporter |
| `tools/check_pin_map.py` | six GPIOs typed in three places — firmware, `elec/main.py`, CIRCUIT.md — with nothing requiring them to agree. Also enforces the ESP32 rules (ADC1 for analog, no outputs on 34–39, no gates on strapping pins) against the role the firmware *actually uses* |
| `tools/check_bom.py` | the BOM's volumes and cut list are generated fact written by hand. Both had gone stale within a day of the edits that moved them |
| `tools/check_pump_dirs.py` | "never both pumps at once" has to hold, not usually hold. Transcribes the firmware and fails if the C++ it claims to transcribe changed |
| `tools/check_plumbing.py` | a route that cannot be bent, or one that passes through something. Every hose-to-fitting contact now carries a MEASURED ceiling: the bare pair list it replaced was hiding a hose drawn curving through 45 mm of rigid elbow, sixty times its neighbours' reading |
| `tools/check_level_alarm.py` | the tank is carried on someone's back, so the sensor is crossed constantly. The debounce *is* the feature and a still bucket cannot test it. Check 9 also derives `LEVEL_FULL_IS_LOW` from the netlist, because the other eight take it as an input and passed with it set either way (finding 47) |
| `tools/check_part_values.py` | `main.cpp` asked for it by name: *"THIS CONSTANT IS A COPY OF A BOARD VALUE AND NOTHING COMPARES THEM … check_pin_map.py ties this firmware to the schematic, but only by PIN NUMBER"*. R21 had already gone 18k → 10k on the board with the firmware's copy left behind, which reads a 15 V pack as 8.94 V and falls back to the fresh-pack duty cap. Checks the firmware's copies against the netlist, every component value claimed in prose, the duty-cap figures `BRINGUP.md` tells an operator to expect, the pack range `CIRCUIT.md` publishes in its rail table, and that a slash pair like `R26/C22` names two parts that actually share a net — which is how C19, a 3V3 decoupler, was found standing in for the level filter |
| `tools/check_silk_face.py` | the board was PLOTTED in Rennie Mackintosh PSG and DRAWN in the CAD kernel's default face, and every gate passed for as long as that lasted — `cad_geom_check` counts labels by probing for ink where each is printed and read 139 / 139 throughout, because a label in the wrong typeface is still a label with ink in it. Checks that the declared face resolves on this machine, that the kernel actually applies it (otherwise nothing else means anything), that the installed file is the REDRAWN one and not ITC's original whose "+" is a TH ligature — both carry the same family name — that `src/housing.py` hands it to the Boards that draws, that `silk_cap` is the measured 0.6670 and not cadkit's 0.72 default, and that the face has a glyph for every character the board prints, since OCC silently substitutes another font when it does not |
| `tools/check_bead_grid.py` | every wall, plate, lid and skirt in the housing was 3.0 mm, which at a 0.8 nozzle is 3.75 beads — so Arachne, not the drawing, chose the section of every load-bearing wall in the part. Nothing had pinned a nozzle diameter at all. Off-grid lengths are allowed where AGENTS.md allows them, but each must name its kind (hardware / clearance / standards) and its reason, and the gate fails on an exemption that has gone stale as readily as on an off-grid wall |
| `tools/check_ic_pinouts.py` | a gate driver whose pinout was wrong on four of five pins, putting a GPIO on its supply and a 4 A output onto the 3.3 V rail — and every stage downstream agreed, because every stage downstream was derived from it. Checks pin maps against datasheet tables cited by document and page, each supply pin against its part's operating window, each rail against the voltage it is meant to BE (3.12 V is inside every part's window and still wrong), and every numbered pad on the routed board for a net — which is how two floating anode leads and the ESP32's whole thermal ground were found |

⚠ **AND ONE THING THESE GATES DO NOT DO: NONE OF THEM COMPILES THE FIRMWARE.** Three of them transcribe or derive from `firmware/src`, so they fail when the C++ text they quote changes — but a firmware-only edit that simply does not build passes every `tools/check_*.py` in this table. The build is verified by `cd firmware && pio run -e main-usb`, which is a **separate step and has to be run deliberately** (measured 2026-10-08: clean, RAM 16.0 %, Flash 78.3 % — 1,026,150 of 1,310,720 bytes of one app slot). A compile gate is deliberately NOT in the suite: it would need PlatformIO present, and a gate that SKIPS when its tool is missing is the `ok=None` defect finding 47 removed from A18 — counted as neither a pass nor a failure while printing as one. Better a named gap than a gate that lies. PlatformIO also refuses at link time if the image exceeds the app partition, so the size ceiling has an owner even though this table does not hold it.

Two habits go with them, and they matter more than the list:

- **A gate is not finished until it has been made to fail.** Every one above was
  verified by reverting the defect it was written for and confirming it bites.
  Two were found to be *vacuous* that way — asserts that could only ever check
  their own arithmetic — and one had a tolerance wider than the error it existed
  to catch.
- **Accepted findings are named and measured, never lumped.** The overhang gate's
  `ACCEPTED` table and `pcbflow`'s `pcb_declared.py` both list a specific feature
  with a reason it cannot be designed out. A single total teaches everyone to read
  the number as "fine".

---

## Open questions

0. **Measure the pump elbows — one caliper reading unblocks a 38.5 mm decision.**
   `ELBOW_LEG_L = 45` is an estimate, and pump B's INNER port is the one port on
   the machine with nowhere to go but up. The hose's first corner has to sit
   `BEND_R` above wherever the elbow leg ends, and the rails cap the centreline
   at 140.5:

   | | |
   |---|---|
   | port centreline | 84.0 |
   | elbow leg ends (at the estimated 45) | 129.0 |
   | first corner must be at | 179.0 |
   | rails cap it at | 140.5 |
   | **short by** | **38.5 mm** |

   This frame accepts a **6.5 mm** elbow leg on that port, and no such fitting
   exists. Either the real leg is far shorter than 45, or `RAIL_Z0` has to go
   from 150 to ≥ 188.5 — taller posts, and the deck and tank 38.5 mm higher.
   `RAIL_Z0` is already documented as being set by this hose, so option two is
   the design's own stated dependency, not a workaround. The frame is **not**
   being raised on the strength of an estimate. `tools/check_plumbing.py` pins
   the defect at its measured 9962 mm³ meanwhile, so nothing about it can move
   quietly.

1. **Confirm the buck thermal theory.** Run continuously into a bucket for 60 s and
   see whether it fades; if so, feel the buck (it will be hot). This decides whether
   deleting the buck actually fixes the slowdown or just removes a part.
2. **PCBA fab.** JLCPCB? Their assembly library constrains part selection enough that
   picking the fab after choosing parts means redoing work.
3. **Specific hall-effect joystick part** — not yet chosen. Selection criteria: output
   range compatible with a 3.3 V ADC, spring return to centre, single axis sufficient,
   footprint that suits a printed mount. It drives `joystick_mount.step`. It does **not**
   block board layout: the joystick comes in off-board on J4, a 5-pin terminal block, so
   the main board is indifferent to which part is behind it.
3. **Makita pack capacity**, for runtime estimates.
4. **Uniseal size** against the Scepter wall, once a panel is measured.
5. **Ramp / dose metering.** v1's 1000 ms ramp made "feather the trigger for small
   plants" work; it was reverted to 106 ms while chasing the slowdown. If the buck
   turns out to be the cause, the slow ramp should come back.

---

## Carried over unchanged from v1

Seaflo SFDP1-030-055-42 pumps (12 V, 3.0 GPM, 55 psi), Makita 18 V pack + 643852-2
terminal, Traco TSR 1-2450E for logic 5 V, KY-023 joystick, BTS7960, the 10 A ATC
fuse (its *holder* did not carry over — it is **F2 on the main board** now), Scepter
5 gal can, Stansport frame, separate spigot fill line.

**Dropped:** Farady 4-way X-port valve, Pololu D42V110F12 buck, 5/8"→3/8" reducers
(×4 → ×1). *The pump inlet strainers were on this list as "redundant given the
green-line filter" until 2026-10-05; they are now the green-line filter itself — §4.*
