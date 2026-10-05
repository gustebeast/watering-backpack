# v2 punch list — from the 2026-10-04 CAD review

Nine items, raised against screenshots of `assembly_v2.step`. Each one is
closed only when a gate or a measurement says so, not when the code changes.
Status is maintained here; the reasoning lives next to the code.

| # | item | state |
|---|------|-------|
| 1 | Lid needs a screw access path — the 45 ramp blocks the driver | **done** |
| 2 | Lid needs a skirt; 20 mm clear on all sides before the battery mount, -Z needs a wiring hole | **done** |
| 3 | Lid's 4 M4s and their inside bosses come out; wood screws hold it | **done** |
| 4 | The extra chunk at the wiring window is unnecessary — plain wall, then cut | **done** |
| 5 | Battery-mount wings are v1 joinery, dead in v2 (one side: Y 3.00..17.30) | **done** |
| 6 | The green water line makes a strange vertical jump | **done** (and it is a blocker — see DESIGN_V2 open question 0) |
| 7 | PCB retained by plastic on all sides but -X; drop to one M4 via cadkit's hole cutter; 45 ramp -X retention on +Y edge, slot-and-rotate install | **done** |
| 8 | Wiring window is not placed to reach the four blocks on the board's bottom edge | **done** |
| 9 | Port bronner's PCB debuggability work (test pads, silkscreen); re-audit the board end to end | **done** (twelve findings, a new gate, five cadkit bugs) |

## Notes on scope

* 1, 2 and 3 are one change: the lid stops being a flanged plate with its own
  M4s and becomes a shoebox lid retained by the two +X wood screws. The earlier
  "WHY THERE IS NO PERIMETER SKIRT" finding in `src/housing.py` measured the
  skirt as impossible **inward** (a -0.06 mm gap in Y) and as having nothing to
  lap **outward** over the bay footprint. The user's measurement says otherwise
  for the outward case: 20 mm of drop is clear on all sides before the battery
  mount. That finding has to be re-measured, not assumed.
* 7 changes the overlap and overhang baselines, so both gates get re-run and
  any whitelist entry that moves gets re-measured and re-named.
* 9 is a PCB audit, not a CAD change; it ends in `elec/` and the fab gate.
  It landed as **ten net-labelled bring-up pads**, **twelve findings** in
  `elec/CIRCUIT.md` (four would have stopped the board, one would have destroyed
  it), and `tools/check_ic_pinouts.py` — the gate the audit's own conclusion
  asked for, since *nothing in the pipeline checked a pin map or a voltage*.
  Adding the pads also flushed out **five bugs in cadkit**, each of which
  produced a board that read as clean: a search graded by a rule it did not use,
  a failed search that left a pad shorting VBAT to a GPIO, a use-after-free in
  `board.Remove()`, two vias in one hole, and a fab report in which an explicit
  "undecided" declaration lost to a footprint guess.


## Round 2

| # | item | status |
|---|---|---|
| 1 | Check the retractable-cable-spool project for its wood-screw head size; make sure the lid hole passes it | **done** — Ø9.3, and our countersink was Ø9.0 |
| 2 | Remove the diamond tie slots | **done** |
| 3 | Battery wiring on the plate's +X side needs a way in: a hole -Z of the PCB box, then a 90° turn +Z | **done** |
| 4 | Oversize the ±Z board stops by 2.4 mm; put 1.6 mm of square prism on the +Y ramp's tip | **done** |
| 5 | Why is a part hanging off the edge of the board? | **answered** — deliberate, see below |

### What the measurements said

**1. The screw is bigger than the hole was.** `retractable-cable-spool/src/params.py`
carries it as "v2's validated screw geometry, verbatim": shaft Ø4.0, **head Ø9.3**,
cone 4.0 deep. Two things followed. The housing's countersink was **Ø9.0 — three
tenths SMALLER than the head**, so the head would have landed on the pocket's rim
instead of seating in it; it opens Ø9.6 now. And the lid's access bore was Ø9.5,
which clears a Ø9.3 head by a tenth of a millimetre per side — a fit, not a hole
you post a screw down on the end of a long bit. It is Ø11.0 now, which in turn
forced the lid's countersink seat from 3.0 to 3.5 mm, because a 45° cone from
Ø11 to Ø4.5 is 3.25 deep.

The 45° pocket is the right shape and not a printing accident: its half-angle is
steeper than an 82° wood screw's, so the head contacts near the mouth and pulls
flush. A shallower pocket would bottom the head out and hold the plate off the post.

**3. The wire entry had a 7 mm window and all three edges were measured.**
Z ≤ 11.0 is the bay's -Z wall; Z ≥ 4.0 is the floor plank's top, measured off the
frame solid, below which the slot opens into timber; Y 121.7..172.0 is the chase at
one end and the +Y post's inboard face at the other. The slot is 22 × 5 mm at
Y 139..161, Z 5.5..10.5, and the 90° turn needs no pocket cut for it — the chase
already removes the bay's -Z wall across that whole Y band, so once the leads are
through the plate they look straight up into the bay. Verified by sweeping a Ø4
probe along both legs against the housing *and* the lumber: clear.

**5. Nothing is wrong — U2's antenna has to leave the laminate.** The ESP32
footprint's courtyard is not the module outline; it is a T-shaped polygon that
includes the antenna fan, and the matching keepout bans tracks, vias, pads, pour
**and footprints** inside it. So the fan has to hang off a board edge rather than
lie across the board, and rot 270 puts it over the +X edge where the only thing
left under it is a mounting-hole cutout, which a keepout does not forbid. The
module body overhangs by **4.12 mm**; every one of its castellated pads is still
over laminate. The housing already accounts for it — `BOARD_Y_PLUS` is taken from
the posed board's bounding box, not the laminate, which is why the bay cavity is
wider on that side than the board is.

### Notes

* The tie slots in #2 were the screw terminals' only strain relief. The battery
  pair does not miss them: #3's slot is a close fit through a 3 mm plate with a
  90° bend against it, which is relief for the one pair carrying 7.5 A. The leads
  arriving *down* the chase from the tank side still have none, and `src/housing.py`
  now says so in as many words rather than leaving the absence to look deliberate.
* #4's stops reach 2.4 mm past the laminate's top face, leaving 17.1 mm of air to
  the lid. The retention gate's reading went from 21 mm³ of lip in the way to 88.
* The overhang gate caught a bug in #3 before the build did: the slot was extruded
  the wrong way down +X and cut a 0.5 mm blind pocket in the back of the plate
  instead of a through hole, which it reported as 104.6 mm² of flat ceiling.


## Round 3

| # | item | status |
|---|---|---|
| 1 | Make the lid opaque | **done** |
| 2 | One of the pumps is translucent too | **done** — same cause |
| 3 | Is there room for the PCB→motor wiring as well? | **done** — there was, barely; widened |
| 4 | What are the blocks on the PCB underside? | **answered** |
| 5 | Walls should be bead-width multiples, not 3 mm | **done** |
| 6 | Why doesn't the screw boss line up with the wall? | **done** — it can't, so the plate closes the gap |

**1 and 2 were one bug.** The viewer's alpha rule was
`0.35 if battery else 0.85 if "_" in nm else 1.0`, and an underscore in a name is
not a reason to see through something. It caught `housing_lid` — so the one part
whose job is to close the bay was drawn translucent, and every screenshot of the
board was taken *through* it — and `pump_a`, `pump_b`, `pcb_screw_0` and
`pcb_insert_0` as well. See-through is declared now, and only the battery (and
the tank, which always was) is.

**3. There was room, with nothing to spare.** Every terminal is on the board's
bottom edge and the chase is the bay's only exit, so J1's battery pair *and*
J2/J3's two pump pairs all come down the chase and all cross the plate — six
conductors, with the pumps 65 mm further +X again. At 14 AWG for the battery and
16 for the pumps that is 17.8 mm laid side by side, and a 5 mm slot is one layer
deep, so width is what carries them. The 22 mm slot held exactly six with no
slack and no room to be wrong about gauge. It is 40 mm now (Y 127..167), still
inside the measured Y 121.7..172.0 window.

**4. Through-hole lead tails.** Nine footprints have them — J1–J6, the buzzer,
and the two ICs' thermal vias — drawn 3.4 mm proud of the solder side. They are
the reason `STANDOFF` is 4.0: the tails end 0.6 mm short of the bay floor, and a
shorter standoff would stand the board on its own solder joints.

**5. Nothing had pinned a nozzle.** `src/housing.py` is on the bead grid now at
`NOZZLE_D = 0.8`: walls, lid and skirt 2.4 (3 beads), the back plate 3.2 (4 — the
extra bead is the countersink's, since a 2.55 mm cone would break clean through a
2.4 plate). The lid lost 15 cm³. `src/battery_dock.py` stays off-grid as hardware,
on the user's point that it has to match the pack and the Makita adapter.

**6. Those two walls can never line up.** The boss is placed by the SCREW, which
is on the post centreline at y=191; the skirt is placed by the BAY it laps, whose
outer face is at y=204. Nothing can bring them together. What was wrong was the
carried-up plate strip stopping at the boss's own face, leaving an 8.4 × 13.6 mm
notch between two walls that look like they should meet. The strip runs to the
lid's +Y edge now, so the boss ties into the skirt corner instead of cantilevering
off a tab — which matters, because that boss takes the lid's whole retention load.


## Round 4

**The step at the lid's screw boss.** Two faces, one cause.

The 81.6 mm² face is the boss's **underside**, over the 5.1 × 16 mm of it that
reached past the skirt's end to the back plate. It could not "extend a few mm
−Z": the housing's bay +Z wall sits **1.6 mm** below it in the same X band, so a
few millimetres of −Z and the lid will not go on at all.

The step was never about Z. The boss's X limit and the skirt's X limit are set by
different jobs and can never be the same number:

- the boss **must** touch the back plate — the screw clamps lid, plate and timber
  in one stack, and a gap there is a gap the lid rocks through;
- the skirt **must not** — the lid seats on the bay **rim**, and a skirt that
  bottoms out on the plate holds the lid off the one joint that is under five
  gallons of water.

The gap between those two limits *is* the step, so the fix is to make it small
rather than to remove it. Measured: the bay is 25.1 mm deep, a test skirt clears
the dock, the pack and the timber at 25.1, and fouls the plate at 26.0. The skirt
is **24.0** now (30 beads) — the last whole bead short of the plate. The lid
closes on 1.1 mm of gap and the step drops from **81.6 mm² to 17.6**.

A new assert holds it: the skirt must stay ≥ 1.0 mm clear of the plate. Nothing
downstream would have caught that one — every part still fits and the install
gate still sweeps clear while the lid quietly closes on the wrong face.

**The 115.4 mm² face is the strip, and it is load-bearing.** It is the piece
added in round 3 that carries the lid plate up behind the boss. Without it the
boss hangs off the plate by the 1.2 mm of Z where the two overlap — for the one
feature that takes the whole lid's retention load. The 7.8 mm of it beyond the
boss's own face is what ties it into the +Y skirt corner. Say the word and it
comes off, but it is doing a job.

## Round 5 — two open decisions the board cannot take for itself

Both came out of reading the **exported gerbers** against the design documents,
and neither is a bug in the board: the board is at 0 unconnected, 0 DRC
violations and 0 quality FAILs, and it is orderable as it stands. They are
places where three documents promise something the built board does not have,
and where the change needed is big enough that it is the user's call.

| # | item | state |
|---|------|-------|
| 10 | **No reverse-polarity protection on VBAT**, which `CIRCUIT.md` §6, `DESIGN_V2.md` §6 and `bom_consolidated.md` §6 all said was there | **RESOLVED** — D1 SMBJ24A → SMCJ24A |
| 11 | **The pack and both pump terminals are SCREW**, where the same BOM line argues for spring-cage on a frame shared with two motors | **RESOLVED** — clamp style is free; all five are now one screw family |

**10 is RESOLVED, and the thing that was wrong was this item's own framing.**

The P-FET was written down as "insurance rather than necessity, *because the
Makita terminal is keyed*". That was sound while the inlet was a keyed XT30.
`CIRCUIT.md` §7 then replaced it with **J1, a 5.08 mm screw terminal carrying two
identical wires** — the single easiest thing in the machine to land the wrong way
round — and nobody came back to §6. The board was built from the connector
decision; the protection decision was never re-opened. No gate on this project
can see that, and it is worth being precise about why: every gate reads the
**board**, and the claim lived in **prose**.

**What this item got wrong: it assumed protection meant a SERIES element.** That
is what made it look expensive — a series P-FET splits the VBAT pour into two
islands bridged by the part, a re-layout of the board's highest-current path on a
board at zero findings — and it is why the only alternative on offer was
restoring a keyed inlet, which contradicts §7 *and* the user's own requirement
for a no-solder screw terminal. Both options were bad because the question was
posed wrongly.

Reverse-polarity protection by **crowbar is a SHUNT**. D1 already is one: a
unidirectional TVS across VBAT–GND, on a pour and a ground plane that both
already exist. Nothing needs splitting. The only real question is whether the
part survives the job — and that is arithmetic, not layout.

**The arithmetic, and why it is I²t.** The fault current depends on the pack's
internal resistance, which is not in this repo. I²t removes that unknown: the
fuse clears on charge delivered, the diode dies on charge absorbed, both are I²t,
and the smaller one goes first at *any* fault current.

| | I²t | |
|---|---|---|
| D1 as built, **SMBJ24A** | 100 A IFSM @ 8.3 ms → **83 A²s** | loses by 1.4× |
| the fuse, **Littelfuse 257-010** 10 A ATO | **115 A²s** min. melt | |
| D1 now, **SMCJ24A** | 200 A IFSM @ 8.3 ms → **332 A²s** | **wins, 2.9×** |

⚠ The first pass at this got the answer **backwards**. Guessing "a 10 A blade
fuse is about 50 A²s" put the fuse first and had D1 survive as built. The
published minimum is 115, and the conclusion reversed on a number that was looked
up instead of remembered. The fuse figure is cited for that reason.

**The fix was one footprint.** SMCJ24A is the same TVS one package up: clamp
**38.9 V at 38.6 A, identical** to the SMBJ24A's (checked across five makers), so
nothing downstream of the clamp moves; 1500 W against 600 W; 200 A IFSM against
100 A. `D_SMB` → `D_SMC`. No series element, no split pour, no keyed connector.
`elec/main.py` carries the derivation and asserts `TVS_I2T_MARGIN > 1.5`.

**Residual, named and measured rather than lumped.** A reversed pack still runs
current backwards through each pump winding via D2/D3 and the FETs' body diodes
until the fuse opens, so the pumps briefly suck on the pressure line, and C1/C2
sit reverse-biased at D1's forward drop for that time — milliseconds, and neither
is a damage mechanism.

⚠ **AND THE FUSE IS ON THE BOARD NOW**, which is the second half of this item and
was closed after it. While the fuse was a holder in the lead, the sum above rested
on a part this repo did not contain. **F2** — Littelfuse 178.6165 FLR holder, LCSC
C207061, taking the 10 A ATC blade already owned — puts it on the laminate in series
with D1. The board grew 100 → 112 mm for it and the housing bay was re-laid; what
was given up is protection of the dock-to-board harness, which is short and inside
the sealed bay. Do not fit a larger blade: **115 A²s** is the ceiling this sum is
built on, and a larger one silently re-opens the finding.

**11 is RESOLVED.** The user's requirement is narrower than the punchlist
assumed: *any* way to land a wire without soldering, with no preference between
screw and spring cage (a JST crimp was specifically rejected as more hassle than
either). So the clamp style stopped being a constraint, and the board went the
other way from what this item proposed — to **one family, all screw**: Ningbo
Kangnex WJ500V-5.08, 2P/4P/5P. The asymmetry this item complained about is gone
because the split is gone. See `elec/CIRCUIT.md` §7 for the withdrawn preference
and for the 16.9 K rise that replaces "31 % of contact rating".

⚠ This section used to end *"10 is still open and no longer has 11 to hide
behind"*. Both are resolved now; the sentence is removed rather than left to
contradict the table two screens above it.

---

## Round 6 — the plumbing, which the board work had been walking past

Neither of these is a board finding. Both are **decisions the owner has already
taken**, written down here because the design documents still say something
else — which is the same failure mode as finding 10: a claim that lives in
prose, where no gate can reach it.

| # | item | state |
|---|------|-------|
| 12 | **§1's "the idle pump's internal check valves seal its branch" does not cover the case that matters.** | **OPEN** — built without a check valve, deliberately; the test is written down below |
| 13 | **The printed line filter vs the two strainers that came with the pumps.** | **OPEN** — topology and threads settled; blocked on the 1/2" vs 5/8" question |
| 14 | **The two tees §1 has always needed are not on the BOM at all.** | **OPEN** — blocked on the same purchase decision as 13 |

### 12 — the idle pump sees a FORWARD differential, not a reverse one

§1 cites the v1 BOM note, *"diaphragm pump check-valves block flow when off, no
siphon"*, and that note is about a **static** system: no pump running, tank
above the wand, gravity trying to push water out. A check valve holds that.

The anti-parallel arrangement is not that case. The two pumps are plumbed
**head to tail**, so when pump A runs tank→pot it raises pressure at the tee
that is pump B's **inlet** and lowers it at the tee that is pump B's **outlet**.
That is a differential in pump B's **forward** direction — the direction its
check valves are built to pass. Two pumps in PARALLEL would present the idle one
with a reverse differential, which is the case the v1 note covers; anti-parallel
inverts it.

So the worry is not a siphon. It is that part of pump A's flow short-circuits
through pump B's chambers back to the suction tee instead of going down the
wand. What limits it is that a stopped diaphragm pump is a poor flow path — the
diaphragms are held by the motor's cogging and the chambers are small — but
"poor" is not "none", and nothing here has measured it.

**Decision: build it without a check valve.** The owner's words: *"what if I
skip the test and just build it with no check valve"*. That is reasonable — the
cure (two check valves in a 5/8" line) costs pressure drop, two more joints on a
system whose headline problem is priming, and two more air traps, and the fault
it guards against is a loss of flow rate and not a failure to work at all.

**The test, so it does not have to be re-derived on the day.** With the wand in
a bucket and the tank full, run pump A at RUN_DUTY and time a measured volume;
then clamp pump B's two branch legs shut and repeat. The ratio is the bypass
fraction. Anything under about 10 % is not worth a valve. If it is large, the
cheapest fix is not a check valve either — it is a pinch clamp on the idle
pump's branch, which the firmware already knows which one is idle.

### 13 — the strainers that came with the pumps, at the tees

§4 designs a printed 1" wedge-wire screen on the green line and says the pumps'
own 50-mesh inlet strainers are redundant. The owner has since tested one:
*"I tested the one that came with the pump and it cleaned itself when run
backwards. I'm thinking we should just put the two filters at the T's on the
merged end."*

That is the same backflushing argument §4 makes for the printed screen, now with
a **measurement behind it** rather than a prediction — and it is a measurement
of the exact part, not of a part like it. Two strainers at the two tees also sit
where §4 wants filtration (everything upstream of a pump is filtered) without a
printed consumable in a sealed line.

**The topology works, and `src/plumbing.py` already settles which leg.** Each tee
has three legs: two to the pumps, and one shared — `TANK_TEE`'s third leg goes up
to the tank, `GREEN_TEE`'s goes out to the wand. A strainer in a *shared* leg sees
flow both ways:

| | tank tee's shared leg | green tee's shared leg |
|---|---|---|
| dispense | tank → tee, **filtering** | tee → wand, **backflushing** |
| retract | tee → tank, **backflushing** | wand → tee, **filtering** |

So both strainers self-clean on alternate strokes, which is §4's own argument run
twice. A strainer in a *pump* leg would not: those legs are one-directional, so one
would only ever filter and the other only ever backflush.

**The thread is settled now, and the owner's instinct was right.** Seaflo's own
page for the 51S01 (the strainer that ships with the 42-series pump): **1/2"-14
MNPT one end, 1/2"-14 FNPT the other**, 50 mesh, PA, removable clear top. So:

- the tee the owner asked for — *"two barbed fittings and one male thread"* —
  screws straight into the strainer's **FNPT** end. That ask is exactly right and
  a barb × barb × MNPT tee is a stock part;
- the strainer's **MNPT** end then wants a female barb, and the BOM already carries
  that family: SEAFLO SFFN1-1220-01 is 1/2"-14 FNPT × 1/2" barb, O-ring sealed,
  nylon — bought for the pump ports, and the 5-pack already has a spare.

**Three things still block it, and none of them is the strainer.**

1. **The tubing size is not settled** — `bom_consolidated.md` §3 carries its own
   ⚠ about this: §4 and §5 of DESIGN_V2 say 5/8", the BOM line says 1/2". It sets
   the barb on the tee, so the tee cannot be bought before it is.
2. **The printed filter is also the 3/8" → 1/2" transition** at the pot end, and
   nothing has said where that goes if the housing does. The green line is 3/8"
   where it enters the inner-pot tube, which is fixed by the pot.
3. **Mesh:** §4's screen is 0.25 mm (≈60 mesh) and the strainer is 50, so the
   change is slightly COARSER — §4 should be made to say that rather than leave
   it to be inferred.

Until all three are answered `src/line_filter.py` still builds the printed screen
and `check_plumbing.py` still routes around it. Nothing is half-changed.

### 14 — the two tees have never been on the BOM

Found while sourcing 13, and it is older than 13: §1 has needed two tees since the
anti-parallel arrangement was chosen, `src/plumbing.py` models both of them
(`TANK_TEE` at x +73, `GREEN_TEE` at x −73) and `check_plumbing.py` routes six
hoses through them — and `bom_consolidated.md` has never listed either one. Not
struck through, not deferred, not open: absent. The CAD gates cannot catch it
because a tee is a bought fitting and they measure printed geometry.

It is cheap to fix and is deliberately **not** being fixed in the same breath as
13, because 13 may change what the tee IS — plain barb × barb × barb if the
printed filter stays, barb × barb × MNPT if the strainers go in. The size is
blocked on the same 1/2" vs 5/8" question. One purchase decision settles all
three, and it is the owner's.
