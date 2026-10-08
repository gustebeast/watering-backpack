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
| 13 | **The printed line filter vs the two strainers that came with the pumps.** | **OPEN** — fully specified now; one purchase decision left, and it is the owner's |
| 14 | **The two tees §1 has always needed are not on the BOM at all.** | **OPEN** — size settled at 1/2"; the thread depends on 13 |
| 15 | **DESIGN_V2 §5 called for 5/8" tubing that §2 of the BOM had already decided against.** | **RESOLVED** — 1/2", settled by the fitting the owner bought |

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

> ✅ **CLOSED 2026-10-05 — the owner decided: "Let's go with the two MNPT tees,
> skip the printed screen."** What that changed in the repo is listed at the end
> of this finding.

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

**All three of the things that used to block this are answered.** They were the
tubing size, the 3/8" transition, and the mesh.

1. ~~The tubing size is not settled~~ — **1/2"**, finding 15 below. So the tee is
   a **1/2" barb × 1/2" barb × 1/2"-14 MNPT** tee, and nothing about the size is
   open any more.
2. ~~The printed filter is also the 3/8" → 1/2" transition~~ — it is, and the
   answer is a **single 1/2" × 3/8" barb reducer at the probe end of the green
   line**. That is *not* the v1 mistake: v1's sin was four reducers necking the
   whole system to its narrowest element (DESIGN_V2 §4), and this is one, at the
   end, on the section the pot fixes at 3/8" anyway.
3. **Mesh, accepted and named rather than resolved away:** §4's screen is 0.25 mm
   (≈60 mesh) and the strainer is 50, so the change is **slightly coarser**. §4's
   own sizing is driven by face velocity and open area, not by particle size — the
   number it argues for is 0.96 in² of open area at ≤1 ft/s — and 50 mesh is still
   finer than anything a pumice pot sheds that a diaphragm pump would mind.

### 13a — the strainer is DIRECTIONAL, and that decides which fitting goes where

> ✅ **CLOSED 2026-10-05** with 13, which it was the sourcing half of. The
> orientation conclusion below is now what DESIGN_V2 §4 says, not a proposal.

The owner, 2026-10-05: *"The stock filter has a female thread on one side and male
on the other. The filtering direction goes from male to female, with female to male
working as a cleaning cycle."* And, correcting a first telling of it: *"the fitting
I have is female to 3/8 barb, it should be in the BOM I sent earlier."*

It is: **McMaster 5346K56 — 3/8" hose barb × 1/2 NPT female**, which this BOM carries
struck through, superseded by the Shurflo swivels. It is not superseded any more.

**Orientation first, because it does not depend on the fittings.** §4's argument is
that the filter **collects on the drain and is swept clean on the fill**, so that
"sand migrates forward one pot per cycle — pumice fines returning to pumice." Apply
that to each tee separately, because the dirty side is not the same side at both:

> **Green tee — MALE end faces the POT.** Dirty water enters at the wand on retract,
> so retract is male→female (collecting) and dispense is female→male (sweeping the
> debris back out toward the pot). Reversed, the drain would run in the cleaning
> direction and the pot's sand would pass straight through pump B into the tank.
>
> **Tank tee — MALE end faces the TANK.** *(This corrects an earlier reading of this
> finding, which said the male end faced the tee.)* The thing a strainer at the tank
> protects is **pump A**, and what threatens pump A is the tank's own settled
> sediment, drawn in on fill. So fill is male→female (collecting) and drain is
> female→male — pushing what it caught back into the tank, where it settles out
> again. Facing it the other way makes the tank the thing being protected, which
> nothing asked for, and sweeps the sediment toward pump A instead of away from it.

**Both strainers therefore present their FEMALE end to the tee**, and that is what
makes the fittings come out even. One part on each side, and they are parts that
already exist:

| | strainer MALE end | strainer FEMALE end (tee side) |
|---|---|---|
| **green tee** | **McMaster 5346K56** — FNPT × 3/8" barb. Owned. | barb × barb × **1/2"-14 MNPT** tee leg, screwed straight in. |
| **tank tee** | **SFFN1-1220-01** — FNPT × 1/2" barb. §2 bought a 5-pack; four are fitted, so the spare is already in the drawer. | the same tee, same leg. |

So the purchase is **two identical barb × barb × 1/2"-14 MNPT tees and nothing
else** — no adapters, no couplers, no second thread handedness, and no hose stub
between a strainer and a tee. That is a better outcome than this finding reached on
its first pass, when the owned fitting was taken to be male × barb.

**And it closes finding 13's loose end.** 13 noted that deleting the printed housing
leaves the 1/2" → 3/8" step at the probe with nowhere to live. It lives in the
5346K56: that fitting *is* the step, and it is on the green strainer's male end,
which is exactly where the branch is allowed to narrow (§5 — the probe is 3/8"
anyway, so the branch's narrowest element does not move).

⚠ **One caution, and it is the owner's own measurement.** The 5346K56 is the brass
fitting behind *"my fittings are quite hard to thread"* (§2). Brass male-tapered into
plastic is what was hard; here it is brass FEMALE onto the strainer's plastic male
thread, which is the gentler direction of the same mismatch but still not plastic on
plastic. Tape it and stop at hand-tight plus a little — the strainer body is the
cheap part, but it is also the part that cracks.

**What the decision changed, so nothing is half-changed:**

- `src/line_filter.py` — **deleted.** With it, `src.test_pieces.test_screen_slice`,
  the coupon that existed only to answer whether a 0.2 mm nozzle renders its 0.25 mm
  slots. A coupon for a part nobody prints invites someone to print it and conclude
  something. git has both.
- `src/build.py` — `line_filter_screen` is out of `printed_parts()`, with the reason
  in place of the part.
- `DESIGN_V2.md` §4 — retitled *"two bought strainers at the tees,
  self-backflushing"* and rewritten. The backflushing argument is unchanged, because
  it was never the thing that was wrong; what it now applies to is the stock part the
  owner actually tested. The four costs are named there, including the one that is a
  genuine loss — see below.
- `bom_consolidated.md` — §3 carries the two tees (finding 14); the 5346K56 is
  un-dropped and moved up to §3 as the 1/2" → 3/8" step; §7b lost the screen row and
  its two paragraphs; the filament figure fell 299 g → 294 g and `check_bom.py` is
  what noticed; the screen is recorded in *Dropped* with why it was a good part.
- **The cost that is a real loss, named rather than lumped:** §4's printed housing was
  deliberately **unopenable**, because a threaded joint on a suction line is an
  air-leak path and priming is this project's headline problem. Two strainers at the
  tees add **four** threaded joints on suction lines. Accepted — they are taped
  tapered pipe threads, not the twist-off cap the argument was aimed at, and the
  system re-primes every cycle by design — but if priming regresses, these are the
  first joints to suspect.
- Still open, and now geometric rather than a purchase: **finding 16**.

### 14 — the two tees have never been on the BOM

> ✅ **CLOSED 2026-10-05, and BOUGHT 2026-10-06.** 13 decided what the tee IS, so
> this could be fixed: `bom_consolidated.md` §3 carries **two tees, barb × barb ×
> 1/2" male NPT, 1/2" hose-ID barbs** — **U.S. Plastic 62128, $0.91 ea, ordered**.
> The absence was the finding; the purchase was just a purchase, and it is done.
> (First sourced to Avidity Science 1610-2845-011 at $1.80 and re-sourced on
> freight: UPS-only, $20 to ship $3.60 of fittings. Kept as the fallback.)

Found while sourcing 13, and it is older than 13: §1 has needed two tees since the
anti-parallel arrangement was chosen, `src/plumbing.py` models both of them
(`TANK_TEE` at x +73, `GREEN_TEE` at x −73) and `check_plumbing.py` routes six
hoses through them — and `bom_consolidated.md` has never listed either one. Not
struck through, not deferred, not open: absent. The CAD gates cannot catch it
because a tee is a bought fitting and they measure printed geometry.

It is cheap to fix and is deliberately **not** being fixed in the same breath as
13, because 13 decides what the tee IS — plain barb × barb × barb if the printed
filter stays, barb × barb × **1/2"-14 MNPT** if the strainers go in. The **size**
is no longer open: 1/2", by finding 15.

### 15 — §5 asked for 5/8" tubing that §2 of the BOM had already decided against

**RESOLVED**, and not by argument. DESIGN_V2 §5 was titled *"Tubing — 5/8"
everywhere except the probe"*; `bom_consolidated.md` §3 bought 1/2" and carried a
⚠ guessing that §5 was "probably right because it is the broader, later
statement". Neither traced to the owner, whose only size instruction was *"the
green line has to stay 3/8 but all the other lines can change"* — which pins the
probe and frees everything else.

What settled it is that **§2 had already chosen, with reasons, and §5 never
noticed**: the pump-port fitting is SEAFLO SFFN1-1220-01, 1/2"-14 FNPT × **1/2"
barb**, and the owner has now bought five of them. A 5/8" tube does not grip a
1/2" barb. The main run is 1/2".

Two things fall out that were not written down anywhere:

- **§5's headline claim was backwards.** It justified 5/8" as *"one reducer
  instead of four"*. With 1/2" barb swivels on both ports of both pumps, going
  5/8" needs a step at **all four** — it would have reinstated exactly the thing
  it claimed to remove.
- **The owned hose clamps would not have fitted.** McMaster 5574K13 is 1/2"–3/4"
  ID; 5/8" ID vinyl is commonly 7/8" OD, outside that range. The 5/8" line would
  have cost new clamps as well as new pump fittings.

The residual is real and is recorded in DESIGN_V2 §5 rather than buried: at
3.0 GPM, 1/2" runs **4.90 ft/s** against the 2–3 ft/s a suction line wants, where
5/8" would have made 3.14. Accepted because the runs are short, the suction is
flooded (§2), and the pump's own port bore is ~0.51" — so the ports are a 1/2"
restriction whatever the hose is. Friction goes as roughly d⁻⁴⋅⁷⁵, so the
3/8" → 1/2" step already won 3.9× of the 11.3× that 3/8" → 5/8" would have.

### 16 — the strainers have a LENGTH, and it has never been measured

Opened by 13 closing. While the filter was printed and unplaced, its size was
nobody's problem: `src/build.py` exported it, `components()` did not carry it, and
§4 gave it no position on purpose. Two bought strainers at the tees do have a
position — inline on each tee's third leg — and therefore a length that has to fit.

**What the model says is available**, from `src/plumbing.py`:

| leg | run | straight available |
|---|---|---|
| green tee → wand | `GREEN_TEE` (−73, 262, **84**) straight down to `GREEN_EXIT` (−73, 262, **−40**), no bends | **124 mm**, and it leaves the pack, so a strainer can also hang below it |
| tank tee → Uniseal | `TANK_TEE` (+73, 262, **84**) up to **z 234**, with one corner at the top at `BEND_R` = 50 | **≈100 mm** |

**What is not known is the 51S01's length.** It is a tape-measure job on a part that
is already in the drawer, which is why this is a finding and not a blocker. The tank
leg is the tight one at ≈100 mm, and it is tight in a way the green leg is not: the
green leg's strainer can hang outside the pack, the tank leg's is boxed in between the
tee and the Uniseal, and `UNISEAL_Z` is set by *"seal needs wall either side of the
bore"*, so it is not free to move up.

**This is a gate-shaped hole, not just an unknown.** `check_plumbing.py` routes six
hoses and measures clearances, and it has no concept of an inline fitting occupying
length on a run — so it will keep passing whatever the measurement turns out to be.
If the number comes back near 100 mm, the fix is to teach the checker about inline
fittings rather than to eyeball it; if it comes back at 60 or 70, the honest thing is
still to record the figure here so the next person does not re-derive it.

### 17 — the level sensor drives its output to the SUPPLY, and the board assumed otherwise

Found while sourcing a US link, which is the only reason it surfaced: nothing in this
repo reads a vendor page, so no gate here could have caught it.

**What the board assumes.** `elec/main.py` feeds J5's V+ from **VBAT behind F1** — the
pack, 15 to 20 V — and reads the output on **IO14** through **R23, a 10k pull-up to
3V3**. R23's comment says what that rests on:

> *"Level sensor: runs at VBAT and its output is OPEN-COLLECTOR, so this pull-up to
> 3V3 is what keeps 18 V out of the GPIO. Push-pull mode would destroy it."*

`CIRCUIT.md` §7 makes the same argument and calls it load-bearing. The argument is
sound. **The premise is false.**

**What the parts actually specify.** Two pages, read 2026-10-05:

| source | input voltage | output HIGH |
|---|---|---|
| Amazon B074PVF341, titled "XKC-Y25-**NPN** … DC **5-24V**" | its own spec table says **DC 5~12V** | **"InVCC"** |
| Trumsense, manufacturer page for the **-V** | **DC 5-24V** | **"5-24V"** |

Both say the HIGH level is the **supply rail**. So "NPN" on these modules does not mean
a bare open collector reaching the pin — there is an internal pull-up to Vcc, and R23
loses to it. **At 18 V of supply, IO14 sees 18 V.** That is the destructive case
CIRCUIT.md names, and it is the default behaviour of the whole family, not a
mis-configuration.

And the listing titled 5-24V contradicts itself in its own specification table at
5~12V — which would have been destroyed by this board's supply even if the output had
been safe. **Two independent disqualifications in one listing.** A second listing
(B0GZ257F8T, "XKC-Y25-NPN-24V") is $44.68 with zero reviews and a 2-to-3-week ship,
and is not worth the risk premium.

**THE FIX, and it is two components in the sensor lead.** An NPN inverter makes the
sensor look like exactly what the board was designed for:

    sensor yellow (OUT) ─├ 10k ──── B      (10k and the 2N3904 are both OWNED, §8)
                               NPN (MMBT3904 / 2N3904, both already on this BOM)
    J5 OUT ───────────────── C          E ──── GND

- **R23 is the collector pull-up**, used exactly as designed. The pin cannot exceed
  3V3 no matter what the sensor does, so this is immune to the variant question
  entirely — and to the next listing that contradicts itself.
- **Base drive is not marginal, and — BOTH PARTS ARE ALREADY OWNED.** §8 of the BOM
  bought a **2N3904** and **10 kΩ** resistors for the cat-bed project and they are
  ticked. Use the 10k rather than buying a 22k: Ib is 1.43 mA at 15 V and 1.93 mA
  at 20 V, so at hFE 100 the transistor can sink 143–193 mA against the **0.33 mA**
  R23 actually needs (3.3 V / 10k) — saturated by a factor of ~400 at the bottom of
  the pack. ⚠ **R23 IS 300k NOW, NOT 10k -- see finding 30**, which raised the
  pull-up to hold a fault clamp under IO14's absolute maximum. That only makes
  this inverter easier: the collector has to sink **11 uA** rather than 0.33 mA,
  so the saturation factor gains another order of magnitude, and the MMBT3904's
  own Vce(sat) at 11 uA is far below the 0.2 V that finding 30's low-level margin
  was computed against. The two findings are consistent, and this line is
  corrected rather than left to read as 10k.
  The draw on the sensor's own output is 1.4–1.9 mA against its rated
  1–100 mA, so nothing is stressed at either end. **This fix costs nothing and
  needs no order.** (22k also works, 65–88 mA of sink; there is just no reason to
  buy one.)
- **Then tie the sensor's black MODE wire to VBAT rather than to J5's MODE
  terminal**, and the inversion cancels: MODE high → yellow goes HIGH when liquid is
  sensed → the NPN pulls IO14 LOW when liquid is sensed → which is exactly what
  `LEVEL_FULL_IS_LOW` already encodes. **No firmware change, no board change, no
  re-order.** J5's MODE terminal is left empty; it is only tied to GND on the board
  and nothing needs it.

**So what to buy is now simple, and it is the part the BOM originally named.** The
**-V** is the variant rated **5–24 V**, which is the only spec that still matters once
the inverter is in the lead — ironically the "NPN"-titled listing is the 5–12 V one.
Confirm 5–24 V **in the spec table, not the title**, and ignore the output type.

⚠ **The connector gets cut off, so the WIRE COLOURS become the only identification.**
The owner is cutting the supplied pigtail to get the cable length right (2026-10-05),
which is correct for a sealed run — but it also throws away the one thing that made
the pinout self-evident. From the manufacturer page: **brown = VCC, blue = GND,
yellow = OUT, black = M (mode)**. Verify with a meter on the part in hand before
trusting a colour, because these are re-sold by many houses.

⚠ **`CIRCUIT.md` §7 said "JST-PH to the XKC-Y25" and that was never what this board
has.** J5 is a 4-way 5.08 mm screw terminal, like the other four. Corrected.

### 18 — the tees neck the line to 9.27 mm, and §5 is the section that cares

Opened by reading the drawing for the tee bought in finding 14, which is the only
reason it is a number rather than a shrug. Thogus drawing **TT3888**, variant
**/P** (polyethylene — U.S. Plastic 62128):

| | inches | mm | |
|---|---|---|---|
| barb crest OD | 0.610 | 15.49 | 1/2" vinyl is 12.70 ID, so it stretches on properly — this is a real hose barb |
| **bore** | **0.365** | **9.27** | **53 % of the hose's area** |
| thread | — | — | MALE 1/2"-14 NPT, confirmed on the drawing itself |

**§5 of DESIGN_V2 exists to stop exactly this**, so it gets measured rather than
accepted quietly. At 3.0 GPM the throat runs **9.2 ft/s** against the hose's 4.9, and
as a contraction-plus-expansion pair (K ≈ 0.45 on the throat's velocity head):

> **0.26 psi per tee. 0.51 psi — 1.19 ft of head — over the two tees every flow path
> crosses.**

**Accepted, and here is the honest reason.** Against a 55 psi pump 0.5 psi is
nothing, but this project's headline problem is priming, not pressure, and 1.19 ft of
extra *suction* lift is the number that could have mattered. It does not, because §2
puts the tank **above** the pumps, so the suction is flooded rather than lifted — the
tees spend head the geometry already gives away for free. And it is unavoidable in
kind: every barbed fitting bores smaller than its hose, the owned SFFN1-1220-01
swivels included, and the pumps' own ports are ~0.51". A 9.27 mm throat 20 mm long is
a minor loss, not a line size.

**What would make it matter**, written down so the trade is not re-derived: moving the
tank below the pumps, or adding the check valve finding 12 deliberately omitted —
either turns a flooded suction into a lifted one, and then 1.19 ft comes out of a
budget instead of out of slack.

⚠ **Not the same as the trap it looks like.** `U.S. Plastic 37861`, which I briefly
recommended for the Uniseal's hose end, is a *poly-pipe insert*: barb 0.406" ID ×
**0.665" OD**, sized for ≈0.600" ID poly pipe, so its crest is ~2.8 mm oversize on
1/2" vinyl and it would not go on. 62128 is a hose-barb fitting and 37861 is a
pipe-insert fitting; the catalogue calls both of them "1/2 inch".

### 19 — the Uniseal's fitting stack overruns the hose's bend by ~29 mm

Finding 16 said the gate has no concept of an inline fitting occupying length on a
run, and named the two tee legs. **This is the same hole at the other end of the same
hose, and here it is not close.** It surfaced only because the owner wrote the
assembly out in order — Uniseal, PVC, PVC-to-FNPT, MNPT-to-barb, hose — which is a
stack of four rigid things before the hose starts, and nothing had added them up.

**The run, from `src/plumbing.py`:** `tank_down` leaves the Uniseal at
(73, **173**, 234), turns at (73, **262**, 234) and drops to `TANK_TEE` at
(73, 262, 84). So the horizontal leg is **89 mm**, and `BEND_R` is **50**, which this
module's own docstring says it needs *"on BOTH sides of the corner"*. That leaves
**39 mm** for everything rigid.

**The stack, outward from the tank wall:**

| | mm | source |
|---|---|---|
| PVC stub proud of the wall | ~25 | estimate — has to seat in the adapter socket |
| 1/2" PVC female adapter, net of the socket | ~13 | **estimate** — not yet a part number |
| 62017 beyond the FNPT face | 29.9 | **measured**: Thogus TA1088/P overall 1.69", ~13 mm of thread engaged |
| **barb tip off the wall** | **~68** | |

89 − 68 = **21 mm of hose before the corner centre, against the 50 mm the bend needs.
Short by 29 mm.** Two of the three figures are estimates, so the number is ±10 mm —
but the shortfall is three times that, and the one measured figure is the biggest.

**THE FIX IS A DIFFERENT FITTING, NOT A LONGER PACK.** Swap the straight 62017 for an
elbow (**62043**, Thogus TE2088/P) and the line turns down *at* the tank, which puts
the rigid stack on the leg that has room:

| | available | needs | |
|---|---|---|---|
| vertical drop, z 234 → 84 | **150 mm** | 100 (50 either side of one bend) | **fits, 50 spare** |
| horizontal at the bottom, y 211 → 262 | **51 mm** | 50 | fits, and only just |

So the elbow converts a 29 mm shortfall on the tight axis into 1 mm of slack on the
roomy one. That second row is tight enough to be the next thing that bites, and it is
the honest reason this finding is not closed by buying a part.

**What is actually still owed:** `src/plumbing.py` routes `tank_down` as a bare
centreline and `check_plumbing.py` measures hose against hose. Neither knows a fitting
has length, so **both will keep passing either layout**. Teaching the model about
inline fittings is the fix for 16 and 19 together — one list of (position, length)
along a run, checked against the straight each bend needs. Until then these two
findings are the only record that the model is optimistic at six places: two tee legs,
the Uniseal, and the three joints in between.

⚠ **Buy both 62017 and 62043.** $1.30 for the pair, against a freight charge many
times that for whichever one the assembly turns out to want.

### 20 — the level sensor's lead is 500 mm and the run is about 700

The owner, picking the part: *"It comes with a connector but I just assume cut it and
use our screw terminals so we can get the cable length right."* Cutting the connector
is right. **The assumption underneath it is backwards** — this lead is not long
enough to shorten.

**The listing is explicit**: EC Buying XKC-Y25-V, *"Line length: 500mm (± 10mm)"*.

**The run, from the model.** The Scepter stands on the lumber deck at `DECK_Z` 208
and `TANK_H` is 478, so its rim is at **z 686**. A *tank-full* sensor sits near that
rim — call it 30 mm down, **z 656**. J5 is in the PCB bay at `PCB_Z_C` **74.75**.

| | mm |
|---|---|
| vertical, sensor to J5 | **581** |
| `CIRCUIT.md` §7 routes it *"out the chase and then up the OUTSIDE of the case"*, so add the dip through the chase and the reach to the tank face | ~120, loose |
| **needed** | **~700** |
| supplied | **500** |
| | **short by ~200** |

Even putting the sensor at mid-tank height (z ≈ 450) gives ~495 mm needed against 500
supplied, so it is marginal at *every* plausible sensor height and short at the
realistic one. The 30 mm figure is an assumption; the shortfall is not sensitive to it.

**So the joint count goes up by one on the one lead that is already the most exposed
thing in the machine.** `elec/main.py`'s own comment on F1 says it: this lead *"leaves
the sealed bay through the chase and then climbs the OUTSIDE of the case to the tank
— so it is the one wire that gets rubbed, pinched and walked past."* A splice there
is not a detail.

**What to do, in order:**

1. **Solder it and seal it properly** — adhesive-lined heatshrink per conductor, then
   one outer sleeve, sited where it is clamped rather than mid-span. Not a crimp butt
   connector, and not a Wago on the outside of a pack that lives in the weather.
2. **Or buy a 1 m variant.** Several XKC-Y25 listings offer a "1M" lead option in the
   dropdown. Worth checking before clicking buy — it removes the splice for the same
   money, and the splice is the only thing this finding is really about.
3. **F1 is the reason this is a finding and not an alarm.** The sensor feed is behind
   a resettable PTC precisely because this lead is the one that chafes, so a splice
   that eventually shorts trips F1 rather than the pack. The protection already
   anticipated a fault on this wire; this finding just notes we are now adding one
   more place for it to start.

### 21 — CLOSED: all five terminals are on the −Y edge, and the board still passes everything

*(Raised as "J5 is on the WRONG EDGE of the board, against a requirement stated in
words". It was. The requirement, from the owner, verbatim and never withdrawn:)*

> *"Avoid moving the wiring connections to other sides of the board since it'll be
> convenient to have them all in the same side facing down."*

**Found while starting the wiring model the owner asked for**, which is the point of
drawing cables: you cannot route one without asking where it leaves from. J5 sat on
the **+Y** edge — world z 120.0 against the other four at 28.0 — so a four-conductor
cable had to climb 92 mm down the face of the board inside the sealed bay to reach the
only exit. Not a plan-view problem: 92 mm of **height**.

**Two documents said otherwise and both were wrong,** and the code already knew.
`src/housing.py` said *"the level sensor's lead leaves through this chase too"* and
`CIRCUIT.md` §7 said the same, while `_edge_connector_span()` **filtered J5 out**
(`if y0 > -PCB_L / 4.0: continue`, commented *"not on the bottom border"*). The chase
was sized from four terminals while the prose claimed five. **Both now agree with the
board**: the span measures 106.922…194.582 and J5 is in it.

**No gate caught it, and that is the finding behind the finding.**
`elec/cad_geom_check.py` checks the routed board against the CAD, `check_overlaps.py`
weighs solids, the quality pass reads the board. **An internal cable that no model
draws is in none of them.**

#### What it actually took

Not a re-space. The terminal **order** had to change, and that was the blocker the
working notes stopped on: J1 is the pack inlet and the only VBAT_RAW terminal, and
sitting it between the two pump terminals put a higher-priority VBAT_RAW stub
(x −14.65…−8.45) exactly across **VBAT's riser A** (x −12.0…−9.7), the path both
pumps' VBAT must take to D2's cathode tab. Both alternatives were shut — 0.61 mm to
PUMP_A_LO's column on the left, 0.36 mm to Q2's courtyard on the right — and the tab
could not be fed from the left either, PUMP_A_LO's bar being across that approach.

Final order **J5, J2, J3, J1, J4**: the two pump terminals adjacent so one VBAT bus
serves both, and the pack and its fuse beyond them. Courtyards, 0.5 mm gaps:

| | courtyard mm | placement x |
|---|---|---|
| J5 level (4-way) | 21.41 | −36.30 |
| J2 pump A | 11.26 | −19.50 |
| J3 pump B | 11.26 | −7.75 |
| J1 pack | 11.26 | +4.00 |
| J4 joystick (5-way) | 26.49 | +28.40 |
| **sum** | **81.68** into 91.00 usable | |

**VBAT cannot reach C1 along the bottom, and the first plan was wrong.** A column at
x −38…−35.5 rising from the bus would have to cross the pad band at y −48.3…−45.7,
where J5.2's pad occupies x −40.14…−37.54. The gap between J5.2 and J5.3 is 2.48 mm,
**1.68 after clearance, against the 3.18 mm IPC-2221 wants at 7.5 A.** So VBAT rises
**right of J5** instead, in the 6.84 mm between J5.4's GND pad (−27.38) and J2.2's
PUMP_A_LO pad (−18.46) — J2.1 being VBAT, the riser may land on its own net's pad
rather than clear it.

Every edge is a measured clearance, not a round number:

| edge | against | clear |
|---|---|---|
| bus top **−48.8** | J5's pads (−48.3) and J1.1's | 0.50 |
| bus bottom **−54.0** | the board outline | 2.00 |
| riser right of J5 **−20.74** | J5.4's GND pad −27.38 / J2.2's −18.46 | in the 6.84 mm gap |
| PUMP_A_LO link top **−29.3** | D2's tab pad bottom −28.90 | 0.40 |
| PUMP_A_LO bar right **−19.49** | D2's tab left edge −19.09 | 0.40 |
| PUMP_A_LO column right **−15.26** | VBAT_RAW's left edge −14.65 | 0.61 |
| VBAT riser B right **+14.60** | J4's courtyard +15.16 | 0.56 |
| VBAT riser B left **+8.10** | J1.2's GND pad +7.84 | 0.26 |

Bus height **5.2 mm** against the 3.18 IPC-2221 wants at 7.5 A.

#### ⚠ VBAT FILLED AS TWO ISLANDS, AND NO CLEARANCE ARITHMETIC WOULD HAVE CAUGHT IT

The left column was first drawn 2.5 mm wide (x −38.0…−35.5) to thread between D1's
pads. It passed every clearance check and **severed anyway**, because F1.1 — a pad on
**VBAT's own net** — sits inside it, and thermal relief around a same-net pad in a
2.5 mm channel leaves **0.13 mm a side**, below the fill's minimum width. Foreign-pad
clearance arithmetic cannot see this: the offending pad is not foreign. Widened to
**4.1 mm**, which also picks up D1.1 directly. Recorded because the next narrow pour
channel will look just as safe.

#### What moved, and what deliberately did not

Thirteen placements moved: J5 J2 J3 J1 J4 F2 C21 C17 C20 C16 F1 C18 R23. Two support
pads moved from y −50 to y −40 — a BOSS_D 10.4 boss at −50 lands on J5's new solder
tail at x −43.92 and J4's at +38.56.

**C1, C2, D1, Q1, Q2, D2 and D3 never moved.** Bulk capacitance stays at the switches,
the TVS stays at the entry. That was the owner's condition — *"so long as it doesn't
negatively impact the performance of the board"* — and it is the reason each pour
became an **L** (a column up from the terminal, a link below the diode's tab, then the
original bar on the tab and anodes) rather than a straight run.

#### The progression, because the middle of it is instructive

| step | unconnected | violations |
|---|---|---|
| first cut of the reorder | 8 | 2 (11 FAIL) |
| pours re-derived | 1 | 0 |
| VBAT column widened to 4.1 | 0 | 0 |
| R23 moved to the receiver | **4** | 0 |
| R23 reverted, A15 exempted | **0** | **0** |

**A better FAIL count was a worse board.** Moving R23 to the receiver cleared the A15
return-slot finding honestly — a pull-up on an open-collector line does belong at the
receiver — and cost 4 unconnected, because the router then took an F.Cu diagonal for
LEVEL across the power section and severed PUMP_A_LO and VBAT. Reverted, and the
remaining finding is accepted as **25** below rather than bought with routing damage.

**Closed at 0 unconnected / 0 violations / 0 FAIL / 0 OPEN**, 70 placements, 34 BOM
lines, 17 frames corrected and 0 unfitted. The board did not grow: still 95 × 112.

---

### 25 — ACCEPTED: ESP_RX_FROM_PROG crosses a 7.17 mm return slot, against a 5.00 limit

**A15 measures the widest ground-return gap any signal crosses.** One net fails:
`ESP_RX_FROM_PROG` at **7.17 mm against the 5.00 limit**, cut at board
(+27.66, +29.97).

**What forms the slot:** the MCU's fan-out bundle on the +Y side — PWM_A, PWM_B,
BUZZ, IO0, a 1.00 mm +3V3 trace and LEVEL — running side by side between U2 and the
board edge. LEVEL is in that bundle *because* J5 moved to the −Y edge, so this finding
is a direct cost of closing 21 and is recorded as one.

**All four corridor lanes were tried and none is routable.** `notes["corridors"]` lays
a 5-segment Manhattan pre-route across a barrier; the lane at **y −44.0 was placeable
and broke the board** — 10 unconnected, 3 violations — because that band carries
VBAT's leftward run. The other three had no room. All four are written into
`elec/main.py` beside the exemption so the next attempt does not repeat them.

*(Two process notes, because both cost time. `notes["corridors"]` is only read inside
the `local_nets` block — a board that defines no local nets accepts the key, ignores
it, and says nothing. And the corridor is laid during `finish.py`, not `main.py`, so
the confirmation line is not where you first look. I briefly credited the corridor
with a 0-unconnected result that actually came from removing the R9/TP2 stub.)*

**Why it is acceptable, named and measured rather than lumped:** `ESP_RX_FROM_PROG` is
J6's UART **receive** line, 115200 baud, live **solely while a USB-serial adapter is
plugged into the programming header**. It carries no signal at all in operation — the
machine runs with J6 empty. A return-path discontinuity costs edge-rate fidelity and
radiated emissions; at 115200 baud on a bench, with the board in a hand rather than on
a backpack, neither is a failure mode. **Every operational net passes**: the widest an
operating signal crosses is 3.02 mm, by JOY_FILT.

**The exemption has been made to fail — six ways.** It is net-scoped
(`return_slot_ok`), and `a15fail.py` runs the real A15 rule against the real routed
board with only that dict varied:

| case | result |
|---|---|
| as shipped, ESP_RX_FROM_PROG exempted | passes; widest 3.02 mm by JOY_FILT, 13 crossings |
| no exemption at all | **the 7.17 mm finding returns** |
| exempt an operational net instead (PWM_A) | ESP_RX still fails |
| exempt LEVEL instead — the net J5's move put in the bundle | ESP_RX still fails |
| exempt a net that does not exist | ESP_RX still fails |
| exempt **everything** | passes differently — widest 2.56 mm by +3V3 |

An exemption that would also swallow an operational net is not an exemption, it is a
disabled gate. This one names one net and **cannot cover for another**.

---

### 26 — CLOSED: moving J5 ate the board's Z retention, and the CAD gate caught it

**Found by `py -3.12 -m src.build` refusing to run** immediately after 21 landed:

> *a Z stop is only 2.3 mm long (min 4.0): the cable chase at 104.9..196.6 has eaten
> the floor it needs*

The cable chase is **derived from the routed terminals**, which is what makes it
correct and what made this bite. With five terminals on that edge the group spans
106.922…194.582 — 87.66 mm of the laminate's 95.0 — and with `CHASE_MARGIN` either
side the chase becomes **104.922…196.582: 91.7 mm, running 1.01 mm PAST the
laminate's +Y edge**, because J5's own outline ends 0.99 mm short of the board edge.
The two Z-stop bands derived from it came out **2.35 mm and inverted** (197.58, 194.57
— a negative length).

**Lowering the 4.0 mm minimum was the wrong answer, and the measurement says why.**
The chase exclusion was never protecting the ribs from the chase **cut**: the chase
removes the bottom wall over z 13.35…15.75, the −Z rib lives at z **16.05…18.45**,
and they clear by `RET_STOP_CLR`. The ribs were never in it.

**What was in the cable's way is the rib's OVERHANG.** It reached to
`BOARD_X1 - RET_STOP_OVER` = **−201.2**, which is 2.4 mm outboard of the laminate's own
face at **−198.8** — out in the space the terminal bodies and their cables occupy. A
rib crossing the chase with that overhang would stand in the descent path of the very
wires the chase exists for.

**The fix is an invariant, not a clearance guess.** The −Z rib now stops **at** the
laminate's outboard face: every connector body and every cable is outboard of
`BOARD_X1`, every part of that rib is inboard of it, so the two cannot meet — and the
laminate's full 1.6 mm thickness is still spanned, which is all a stop has to do. The
2.4 mm of margin it gives up bought nothing the laminate's own thickness did not
already provide. The **+Z** rib sits 115 mm up in Z from the chase, where there is no
cable to obstruct, and keeps its overhang.

Both therefore run the laminate's full length. **The stop is now 93.0 mm — longer than
the two-band scheme ever achieved**, on a board whose bottom edge is now entirely
connectors, and it is one continuous rib per Z edge instead of four short ones.

**Made to fail five ways, each by its own assert:** the −Z rib given the +Z pair's
overhang; the −Z rib stopping 1 mm short of the laminate; the ribs sunk into the
chase's Z band (the assumption that was implicit before and is now checked); the band
shortened back to a bump; the band running off the end of the laminate. All five
caught, and the file imports clean afterwards.

Verified after: 10/10 `tools/check_*.py` pass, **0 unintended overlaps**, every shipped
part still prints without support, and `cad_geom_check` reports 59/59 routed parts
where the CAD draws them.

### 27 — OPEN: two documents describe strain relief that does not exist

`elec/CIRCUIT.md` §7 says `src/housing.py` "puts a buttress rib on the back plate
under the board's bottom edge with a 10 × 7 mm tie slot through it (TIE_*)", and the
**signed quality item M38** repeats it: *"Strain relief is deliberately NOT at the
terminals ... which is why it is at the housing's buttress rib and its 10 × 7 mm tie
slot."*

**TIE_ appears 0 times in `src/housing.py`.** That file says so in its own words: the
ribs are *"gone at the user's request and nothing replaced them."* Same class as the
four-mounting-holes prose — a sign-off citing geometry that is not there.

Two more stale numbers in the same paragraph: the chase is given as **y 134..158,
"between J3 and J4"**. It is **104.9..196.6** and spans the whole row, because it is
derived from five terminals now, not four.

**The engineering gap underneath is real, and finding 21 made it bigger.**
`housing.py` names it: the wire slot is genuine relief for the battery pair, which
turns 90° against a close-fitting hole, but *"it is not relief for the leads that
arrive down the chase from the tank side (the level sensor, the joystick)"*. J5's
four-conductor lead is now on that same edge, so **three** unrelieved cables land
straight on a screw clamp, not two.

### 28 — CLOSED: lead_exit() refuses the question it was answering wrongly

`cadkit.board_geom.Boards.lead_exit()` is documented as *"the point a cable should be
drawn from"*. For J1–J5 it returned a point **15.67 mm off the board's FACE, pointing at
the lid** — the top-entry answer — when every one of those mouths faces **world −Z**, 6.65
mm above the chase.

**The cause was a 7-character prefix lookup.** `lead_exit` sees `Horizontal` in the fpid
and enters its side-entry branch, then keys `side_plug_run` on `name[:7]`, which for
`TerminalBlock_Phoenix_MKDS-3-...` is the string **"Termina"**. Nothing registers that
key, the lookup returned `None`, and the function **fell back to the top-entry formula
without a word**. Built on it, five cables would have been drawn leaving perpendicular to
the board, missing the chase entirely, and the model would have **passed** — a wrong
direction is still a valid point, so nothing downstream can tell it from a right one.

**Fixed in canonical cadkit** (`e8ebc68`), two changes:

1. **A side-entry part with no registered plug run RAISES.** The message names the fpid,
   says every prefix it tried, and tells the caller either to register the mated plug's
   run or — if the direction is a convention rather than a measurement — to declare it in
   the caller and say why there. *A helper that guesses the wrong direction in silence is
   worse than one that refuses.*
2. **The lookup is the longest registered PREFIX, not `name[:7]`.** Both keys in
   `SIDE_PLUG_RUN` happen to be exactly seven characters, so the slice worked by
   coincidence and would silently miss a key of any other length.

**Made to fail, and made to stay out of the way** — all five terminals refuse; `JST_PH_`
and `JST_XH_` are still registered; the one top-entry `J*` on the board is untouched; and
a run registered under a **25-character** prefix now *resolves*, which `name[:7]` could
never do. That last case then raises `_side_mouth`'s own refusal — *"the footprint origin
sits mid-body, so which end is the mouth cannot be read from the geometry"* — which is
exactly what finding 28 predicted from CIRCUIT.md §7's indeterminate 5.35 vs 5.95 mm. **The
two refusals agree**, and neither of them guesses.

`src/wiring.py` still **declares** the entry face (`ENTRY_FACE = "board -Y"`) with the
+Y-up/+Y-down reasoning, which is the right answer for a convention, and asserts the one
thing a convention can be held to: every mouth over the chase and within 20 mm of it.


### 29 — CLOSED: the pack pair fits; the model was drawing it gathered through a slot that is one layer deep

**The wiring model's first real catch, and what it caught was the MODEL.** With the
harness in `components()`, `check_overlaps.py` reported **15.1 mm³ wire_pack ↔
housing** at x −193.2..−190.0, **z 4.70..11.30** — the back plate at the wire slot,
which is **5.00 mm tall (z 5.50..10.50)**. A gathered 2 × 14 AWG bundle is **6.60 mm**
and does not fit.

**But the harness does fit, and `src/wiring.py`'s own comment had already said why
before the gate was run:** the slot is **one layer deep**, so the conductors cross it
**side by side**, not gathered. Two 3.30 mm conductors lying flat are **3.30 tall and
6.60 wide** — which is exactly what the slot was sized for, and what finding 3's
17.8 mm side-by-side arithmetic assumed all along. The gathered diameter is still the
right model for the four runs that do **not** cross the plate, where a cable really is
gathered.

**Fixed by drawing the cable as it lies.** `LAID_FLAT` names the cables that cross the
slot — only the pack pair does — and those are emitted as one solid per conductor,
each bending on its own radius. Two new asserts hold it: a laid-flat conductor must be
no taller than the slot, and its conductors laid side by side no wider. **That is the
check whose absence let a 6.60 mm round bundle be drawn through a 5.00 mm slot.**

**Result: the harness is now IN the overlap gate** — 23 components weighed,
**0 unintended overlaps** — so from here a cable is checked against the housing, the
lid, the board and every other cable by the same gate as everything else. The
2.0 mm³ `wire_pack ↔ pcb` reading at the mouth resolved itself in the same change:
with per-conductor lanes the wires straddle the clamp instead of sitting dead-centre
in its body, so no `intended()` entry was needed after all.

#### ⚠ AND THE RIB HALF OF THIS FINDING WAS MINE, AND IT WAS WRONG

This finding was first written claiming that finding 26's now-continuous −Z stop
crosses the wire slot's Y span and blocks the pack pair, and that **finding 26 had
overclaimed its invariant**. **Both claims are withdrawn.** The geometry does not
support them and the measurement never did:

* The reported clash was at **x −193.2..−190.0 — the plate**. The rib lives at
  **x −193.2..−198.8**. Different region; the gate never pointed at the rib.
* The turn's arc centre is at **(x −197.53, z 17.9)**, so where the cable crosses the
  rib's x band it is at **z ≈ 8.08**, not 17.9. It only reaches the rib's height at
  **x −207.43**, which is 8.6 mm outboard of the rib's outer edge. The arc leans
  *away* from the board, not across it.
* So the 6.4 mm "band between the slot and the rib's underside" that this finding did
  its arithmetic in **is not a band the cable ever occupies.**

**Finding 26's invariant stands as written** — every connector body and every cable is
outboard of `BOARD_X1` where the rib is inboard of it — and the pack pair does not
violate it, because it drops to slot height *before* it travels inboard rather than
after. The exception I inserted into finding 26 has been removed.

**The error was reasoning about a bend instead of measuring one**, after the gate had
already told me where the volume was. I put the arc's centre on the wrong side of the
corner, which puts the whole arc 9.9 mm too high. Recorded because it is the same
mistake as the render-read in finding 24, one level up: **the gate gave a coordinate
and I argued past it.**

### 30 — CLOSED: LEVEL reaches IO14 unprotected, and the fix had to be sized against the Schottky's MAXIMUM Vf, not a typical curve

**Found by validation pass 1** (independent pin-by-pin review against the makers'
datasheets, by a reviewer with no access to `elec/main.py`). Highest severity of
anything the four passes produced.

`J5.3` (LEVEL) reaches **U2 pin 13 = IO14** with nothing in the path but R23's 10 k
pull-up to +3V3. **No series resistor, no clamp diode, no divider.** And `J5.1` on
the *same screw terminal block* carries **VBAT_LVL — the unregulated pack at
18–21 V**, behind F1's PTC.

The module's limit is **VDD + 0.3 V ≈ 3.6 V** (ESP32-WROOM-32E datasheet v2.1,
**Table 15**, p. 28; abs max 3.6 V in **Table 13**).

**Why this reads as an omission rather than a decision:** every other external input
on this board is protected. JOY_FILT has R22 1 k + C12 100 n. VBAT_SENSE has the
100 k/18 k divider. LEVEL has neither, and it is the input whose cable is the most
exposed conductor in the machine — the one M36 already singles out for leaving the
sealed bay and climbing the outside of the case to the tank.

**What puts 21 V on IO14 on a built board:** a slip between adjacent screws on a
5.08 mm block; a wet connector bridging J5.1 to J5.3; or a level sensor whose output
is a voltage rather than a dry contact. Any of the three destroys the module.

A second, smaller note from the same finding: IO14 is **MTMS/HS2_CLK** (v2.1
Table 3) and is driven by the chip during boot, so a sensor that is a hard short to
GND makes the pad drive into a short for the first milliseconds.

**The fix is a series resistor into IO14 plus a clamp to 3V3/GND** — four parts:
R23 (pull-up), R26 (series), C22 (filter) and **D7, a BAT54S, the only new BOM line**.

⚠ **A divider cannot do this, and that was worked through before the clamp was
accepted.** The fault arrives at J5.3 and **bypasses the pull-up**, so the ratio that
divides 21 V to 3.3 is not the ratio that reads an open collector as a logic low. The
two demands pull opposite ways:

| | needs | because |
|---|---|---|
| read a released open collector as HIGH | R<sub>bot</sub> ≫ R<sub>top</sub> | the pull-up is the only thing raising the node |
| hold a 20 V fault under 3.6 V | R<sub>top</sub> ≥ 4.55·R<sub>bot</sub> | the fault enters past the pull-up |

No pair of resistors satisfies both. **The clamp is not a belt-and-braces addition; it
is the only topology that works.**

#### ⚠ The first attempt was 100k/10k, and A16 refused it — correctly

The obvious values read well on a typical Schottky curve: 10 k of series resistance puts
1.6 mA into the clamp at a 20 V fault, which looked like ≈0.33 V of V<sub>f</sub> and a
pin at ≈3.63 V. **30 mV over a 3.6 V absolute maximum, in a fault rather than in
operation** — and a paragraph was written arguing that was acceptable.

**A16 would not take it, and the refusal is the useful part.** Its `accepted` mechanism
signs for a pin run over its **steady** rating; it explicitly will **not** absorb a
transient over a **peak** one, and emits a hard failure if you try
(`cadkit/pcbflow/quality.py`). That distinction is right: a steady rating is a derating
curve and a peak rating is where the part stops being a part. **The gate forced the
circuit to change instead of the paperwork.**

#### What the real constraint turned out to be

**V<sub>f</sub> IS the entire budget, and that is structural rather than a matter of
picking better values.** The pin's limit is VDD + 0.3 and the clamp holds the pin at
VDD + V<sub>f</sub>, so **both sides move with VDD and it cancels** — whether the
regulator sits at 3.25 or 3.35 V changes nothing. What is left is one question: is the
Schottky's forward drop under 0.3 V at the fault current? And because V<sub>f</sub> is
**logarithmic** in current, **halving the current is worth 24 mV**. There is no amount of
series resistance that buys comfortable margin.

Designed against the datasheet's **maxima** (0.24 V @ 0.1 mA, 0.32 V @ 1 mA, 0.40 V @
10 mA) rather than a typical curve, and graded on four constraints at once:

| R<sub>p</sub> / R<sub>s</sub> | pulled-low level | 20 V fault | 38.9 V double fault | node Z | survives V<sub>ce(sat)</sub> of |
|---|---|---|---|---|---|
| 100k / 10k | 0.482 V | **3.637 ✗** | 3.664 ✗ | 9.1k | 0.5 V |
| 200k / 30k | 0.604 V | 3.599 (1 mV!) | 3.626 ✗ | 26.1k | 0.4 V |
| **300k / 49k9** | **0.642 V** | **3.581 ✓** | 3.608 ✗ | 42.8k | **0.44 V** |
| 470k / 100k | 0.744 V | 3.557 ✓ | **3.584 ✓** | 82.5k | **0.3 V ✗** |

**470k/100k is the only row that survives the double fault, and it is still the wrong
answer** — it fails to see a logic low if the sensor's saturation voltage is 0.3 V, and
a damp terminal leaking OUT-to-GND through 470 kΩ pulls its node under V<sub>IH</sub>.
**V<sub>ce(sat)</sub> and moisture are normal operation; the double fault is a
conjunction of two independent faults.** Normal operation wins.

**300k is spelled as three 100k in series (R23, R27, R28)** so the board adds **no
resistor BOM line** — 100k is already a Basic part here, and 49k9 was already a Basic
code in `fab.py` left over from the sense divider. **D7 remains the only new line.**

#### ⚠ What this deliberately does not cover, named rather than left to be found

The TVS clamping a surge **while** the sensor wire is bridged to the pack: 38.9 V on
LEVEL, 0.707 mA through the clamp, V<sub>f</sub> max 0.308 → **3.608 V, 8 mV over**.
It is declared that way in A16 rather than rounded away, and the ESP32's own input
protection conducts in parallel at that point, which can only help and **is not
counted**.

**And the second half of finding 30 is fixed for free:** IO14 is MTMS/HS2_CLK and the
chip drives it during boot, so a sensor that is a hard short to ground used to be a pad
driving into a short. It now drives into 49k9.

#### Two gates moved because of this

- **`tools/check_pin_map.py` failed, and it was right to.** LEVEL no longer touches
  IO14 — LEVEL_IO does, behind R26 — so the gate reported *"net n_lvl reaches no u_mcu
  pin"*, which was **literally true and the wrong answer**: a series resistor does not
  change which pin the sensor reaches. It now follows two-terminal parts — **but only
  where neither end is a rail**, and that restriction is the whole difficulty. C22 is a
  two-terminal part from LEVEL_IO to GND, so propagating through everything would let
  GND inherit IO14, and GND touches a two-terminal part on nearly every net on the
  board — after which **every net reaches every pin and the gate can no longer disagree
  with anything.** Three synthetic boards now run on every invocation, including the
  capacitor-to-ground case, because a walk that is too generous reports every pin as
  correct.
- **The 300k string's joints are not at 3.3 V in a fault**, which is the one thing
  splitting the pull-up changed electrically. With 20 V on LEVEL, current runs
  **backward** up the string into +3V3, so the joints sit at 8.9 and 14.4 V. An 0603 is
  a 75 V part and nothing else touches them, but declaring them at 3.3 V would have been
  a reading nobody did.

### 31 — CLOSED, and the finding does NOT stand: the VGATE shunt holds, because only one pump ever switches

**Pass 1 raised this as a droop risk and it was right to make us check — but its
premise is wrong, and the check it asked for is the thing that settles it.** Recorded
in full rather than quietly dropped, because an independent reviewer's wrong finding
is still evidence about what the design record fails to make obvious.

**What pass 1 computed.** VGATE is a shunt: R9 1k5 from VBAT, clamped by D5 BZT52C10
(9.4–10.6 V, 500 mW), feeding both UCC27517s. Available current = (VBAT − 10)/1500 →
**5.3 mA at 18 V**, 3.3 mA at 15 V, 7.3 mA at 21 V. Demand = **2 ×** Qg × fSW ≈
**4 mA at 20 kHz** — therefore marginal at nominal and in deficit at a sagging pack.
It explicitly flagged that the PWM frequency was not derivable from the fab files and
**asked for it to be checked against the firmware.** It is 20 kHz
(`firmware/src/pins.h`: `PWM_FREQ = 20000`), which is exactly the frequency the
finding was pointed at.

**⚠ THE ERROR IS THE FACTOR OF 2, AND THIS BOARD STRUCTURALLY FORBIDS IT.** The two
pumps are **mutually exclusive** — they would fight through the shared tees and pull
2 × 7.5 A off one pack. `firmware/src/main.cpp` makes the exclusion structural in
`drivePumps`, and `tools/check_pump_dirs.py` is the gate that holds it, raising
`BOTH PUMPS DRIVEN` if it ever stops being true. CIRCUIT.md §7 states the consequence
for a different reason entirely: *"J1 never sees both pumps."*

So the switching demand is **one** FET's Qg × fSW, not two. And CIRCUIT.md §2 had
already costed it: *"the drivers' quiescent plus Qg×fsw, **about 1.5 mA with one pump
running at 20 kHz**"*.

| pack | shunt delivers | demand, one pump at 20 kHz | margin |
|---|---|---|---|
| 21 V fresh | 7.3 mA | ≈1.5 mA | 4.9× |
| 18 V nominal | 5.3 mA | ≈1.5 mA | 3.5× |
| **15 V flat** | **3.3 mA** | ≈1.5 mA | **2.2×** |

**The shunt holds at every pack voltage, including a flat one.**

**And the second half of the finding was already answered in the design record, with
the same numbers.** Pass 1 reported the standing drain as a discovery; CIRCUIT.md §2
states it: *"It costs 3.3 mA of standing current at a flat pack and 6.7 mA at a fresh
one, which is nothing beside the ESP32's 100 mA and the level sensor's own draw; this
machine has no low-power idle state to protect. A 60 V LDO would be tidier and would
not idle, if you would rather spend the part."* That is the same arithmetic, the
decision already taken, and the alternative already named. **Accepted, not newly
found.**

#### The one number that is genuinely unpinned, and it does not change the answer

The hinge is whether IRLR3636's **Qg = 49 nC is quoted at VGS 4.5 V or 10 V.** Pass 1
read it as 4.5 V and doubled it to ≈100 nC at the 10 V rail; CIRCUIT.md's 1.5 mA
total implies ≈49 nC at 10 V. Pass 1's own caveats say its WebFetch quota ran out,
and IR PD-96224 was not re-read for this. **Taken both ways:**

* 49 nC at 10 V → 0.98 mA switching + ≈0.5 mA quiescent = **1.5 mA**, margin 2.2× at a flat pack
* ≈100 nC at 10 V → 2.0 mA switching + 0.5 quiescent = **2.5 mA**, margin **1.3×** at a flat pack

**Either way the shunt holds with one pump running**, so the finding closes on the
worse of the two readings. Worth pinning the Qg condition when the datasheet is next
open, because 1.3× at a flat pack is thin enough that a future frequency increase
would need re-checking — and `PWM_FREQ` is one editable constant with no gate tying
it to this budget. **That missing gate is the real residue of this finding**, and it
is the thing to fix rather than the circuit.

#### Why a correct review produced a wrong finding, which is worth more than the finding

Pass 1 was given the netlist, the BOM, the placement and the datasheets, and
deliberately **not** `elec/main.py` or `CIRCUIT.md` — that ignorance is the whole
design of the pass. Mutual exclusion is a **firmware and gate** property; it is
invisible in the fab package. So a reviewer reading only what the fab reads will
assume two switching FETs every time, and should. The cost of independence is findings
like this one; the benefit is finding 30, which no amount of reading our own documents
would have produced. **Both come from the same ignorance and it is not possible to
keep one without the other.**

### 32 — CLOSED, by moving the barrels rather than by tenting them: U1's thermal vias were pasted over, and tented on the wrong side

**Pass 1, reading the gerbers rather than the footprint source.** In
`wbp:SOIC-8-1EP-FABDRILL`, pad 9 is a 2.29 × 3.0 mm land with six 0.3 mm plated vias
at (±0.65, −1), (±0.65, 0), (±0.65, +1). The paste is four F.Paste-only windows of
0.96 × 1.25 mm at (±0.57, ±0.75), spanning x 0.09…1.05 and y 0.125…1.375 — which
**encloses the four vias at (±0.65, ±1.0)**. Confirmed in F_Mask, which carries the
full EP opening at 64.0/−70.0, aperture 2.29 × 3.0: the vias are **open, unfilled
and untented**, with paste printed straight over them.

Solder wicks through at reflow, reducing EP solder volume and leaving bumps on B.Cu.
TI SNVSAA5B **Table 4-1, p. 3**: pin 9 is "the major heat dissipation path of the
die. Must be connected to ground plane on PCB."

**Consequence: a degraded, not absent, heat path** — fine at the few hundred mA the
3V3 rail actually draws, a thermal-shutdown risk if it is ever loaded near 2 A.

**The board's own ESP32 footprint does this correctly, which looked like the useful
part of the finding:** there the vias sit *between* the paste pads, 0.7 mm off.

#### ⚠ PASS 4 CONFIRMED IT INDEPENDENTLY AND FOUND IT WORSE IN TWO WAYS

**It is six holes, not four.** The four at (±0.65, ±1.0) are *fully* enclosed by the
apertures; the remaining two at (±0.65, 0) are **clipped by 0.025 mm at each aperture
edge**. So **all six are touched by printed paste.** Confirmed in
`main-F_Paste.gtp`: exactly 4 apertures at (63.43/64.57, 69.25/70.75) around U1's
centre (64.0, 70.0).

**And they are tented on the WRONG SIDE, which is the stronger mechanism.**
`main-F_Mask.gts` has a single 2.29 × 3.00 opening at (64.0, 70.0) enclosing all six
0.70 mm via pads — so the holes are mask-**open** on the component side.
`main-B_Mask.gbs` has **zero** openings there — so they are **fully tented on the far
side**. TI **SLMA002H p. 9** states component-side tenting is preferred and warns that
tenting from the opposite side instead gives **increased voiding visible in x-ray, from
flux outgassing and air entrapment**. Ours therefore loses solder down six open holes
**and seals the gas in.**

**The fix is no longer "copy the ESP32 footprint", because pass 4 found that one has
its own version of the same defect** — see finding 39. Both footprints need the same
two edits: shrink/relocate the via pads so they clear the paste, and tent the barrels
**on the component side**. And see finding 38: U1's exposed pad is also 25 % undersized
and starved of paste, so this is one of four deficits stacked in the same direction.

### 33 — CLOSED on 10k, a value the finding never considered: the VBAT_SENSE divider saturated above ~20.3 V

**Passes 1 and 2 reached this separately**, which is what makes it worth acting on:
pass 1 from the divider arithmetic, pass 2 from the ADC's characterised range.

R20 100 k / R21 18 k gives a gain of 18/118 = **0.15254** into U2 pin 7 (IO35,
**ADC1_CH7**). At a full pack:

| pack | at IO35 |
|---|---|
| 18 V nominal | 2.75 V |
| **20.3 V** | **≈3.1 V — ADC1 11 dB full scale** |
| 21.0 V fresh | **3.20 V** |

**No damage** — Table 15 allows VDD + 0.3 — but everything above about **20.3 V reads
as the same saturated value**, and that is precisely the end of the range a
"battery full" reading needs. Pass 2 adds that `analogReadMilliVolts` with
`ADC_11db` is factory-characterised to roughly 3100 mV, and that 3.05–3.20 V sits
well above the 150–2450 mV **linear** suggestion, so the reading is compressed
before it is clipped.

⚠ **AND THE ERROR IS IN THE DANGEROUS DIRECTION.** Compression reads the pack
**low**, which **raises** the duty cap — the same failure direction `main.cpp`'s own
clipping comment warns about. So this is not merely a cosmetic range issue.

#### ⚠ THE OBVIOUS FIX COSTS A BOM LINE. CHANGE THE BOTTOM LEG, NOT THE TOP.

Both passes proposed raising the top leg — 150 k/18 k or 180 k/18 k. **That is the
finding-22 trap, and it caught me too: I wrote "changes no BOM line count" before
reading the BOM.** `100k` is **one line shared by four parts — R1, R20, R6 and R7**
(`100k,"R1,R20,R6,R7",0603,C25803`). Moving R20 off it creates a **second** line while
100 k is still needed for the other three: **+1 line, about +$1.28 of feeder**, to fix
a reading error.

`18k` is **R21 alone** (`18k,R21,0603,C25810`). So changing the **bottom** leg is
value-for-value and the line count is identical.

Derived against the ADC's own numbers — 11 dB full scale ≈**3.100 V**, linear
suggestion **0.150–2.450 V**:

| divider | ratio | 15 V flat | 18 V nom | **21 V fresh** | clamp 38.9 V |
|---|---|---|---|---|---|
| **100k/18k as built** | 0.15254 | 2.288 | 2.746 | **3.203 — clipped** | 5.93 |
| 100k/15k | 0.13043 | 1.957 | 2.348 | 2.739 — on scale, past linear | 5.07 |
| 100k/13k | 0.11504 | 1.726 | 2.071 | 2.416 — just inside linear | 4.48 |
| **100k/12k — recommended** | 0.10714 | 1.607 | 1.929 | **2.250** | **4.17** |

**100k/12k puts the entire 15–21 V operating range inside the ADC's linear band**
(1.607–2.250 V against 0.150–2.450), with 0.85 V of headroom to full scale instead of
being 0.10 V over it. 12 k is E24 and ordinary. 13 k also works and is tighter; 15 k
clears the clipping but leaves the top of the range in the compressed region, which is
the half of the problem that actually biases the duty cap.

**It improves finding 36's transient at the same time** — the clamped 38.9 V arrives at
IO35 as **4.17 V instead of 5.93 V** on a 3.6 V pin. Same divider, both ends, one
change. That is the argument for doing it rather than living with it.

**The ratio is already derived, not typed**, so the edit is one string:
`RDIV_TOP, RDIV_BOT = "100k", "18k"` at `elec/main.py:39`, with `SENSE_RATIO` spelled
from it on line 43 and A16's `net_volts` for VBAT_SENSE reading through it — so the
quality declaration, the assert and the firmware's scaling all follow automatically.

⚠ **NOT APPLIED, and the one thing missing is a part code, which I will not invent.**
`REQUIRE_CODES` means a value needs an LCSC code that is actually stocked and Basic;
guessing one is the fabrication this repo has scars from. **The remaining step is to
look up a Basic 0603 12 k (or 13 k) and confirm it is stocked, then change the one
string and re-run the chain.** Everything else about the change is derived.

Pass 2's alternative stands in the meantime: **a bench check of `readVbat()` against a
meter at a full pack during bring-up** is enough to order the board on, because nothing
here is a damage mechanism — only a reading one. Pass 2's
alternative is a bench check of `readVbat()` against a meter at a full pack during
bring-up, which is enough to order the board on.

### 34 — Three lower-severity notes from pass 1, recorded rather than actioned

**a. No high-frequency ceramic directly at U1's VIN.** The nearest VBAT bypass to
U1 pin 2 is C15 (4.7 µF, **1206**) at 4.3 mm; C17/C20 (10 µF 1206) and C1/C2 (100 µF
electrolytic) are further. TI SNVSAA5B Table 4-1 p. 3, VIN: "Path from VIN pin to
high frequency bypass CIN and GND must be as short as possible", reinforced in §7.4.
A 1206 X7R has markedly more loop inductance than an 0603 100 n. Effect: more SW-node
ringing and EMI and more stress on the internal high-side FET, at 500 kHz on a 21 V
input. **A 100 n 0603 beside pins 2/7 would cost one BOM line** — and per finding 22
that is the real price, about $1.28, not the part.

**b. IO0 has no external pull-up.** U2 pin 25 goes only to J6 pin 6, so boot-mode
selection relies on the internal pull-up with a header stub attached. Standard
devkits fit 10 k. Pass 2 independently confirmed the **boot state is correct**
(wpu → 1 → SPI Boot Mode, v2.1 §4 Table 4 and Table 6), so this is a robustness
note, not a defect — and pass 1 said so itself, having no datasheet requirement to
cite for the resistor.

**c. No reverse-battery protection beyond D1 and F2.** Reversing J1 forward-biases
the SMCJ24A and relies on the ATO fuse clearing; C1/C2 are polarised and the pumps
see reverse voltage until it does. Conventional for this topology, but worth a
**conscious** decision given J1 is a screw terminal a person wires by hand in a
garden — which is exactly the case where a connector *can* be mated backwards.

### 35 — CLOSED: pre-order validation passes 1 and 2 ran, and most of what they checked was right

**Two of the four passes in `VALIDATION_AGENTS.md` are complete.** Both were run by
reviewers with **no access to `elec/main.py`**, which was the whole point: a reviewer
who has read the generator re-derives the generator's assumptions and agrees with
them.

**The feedback divider — the live hook the pass was pointed at — is correct, derived
from the datasheet's own equation rather than from our arithmetic.** VFB = 0.750 V
typ (SNVSAA5B §5.5, p. 5; 0.744–0.756 at 25 °C). §6.3.5 Eq. 1:
VOUT = 0.75 × (1 + RFBT/RFBB) = 0.75 × (1 + 100 000/29 400) = **3.301 V**, worst case
**3.21–3.39 V** with 1 % parts — inside the module's 3.0–3.6 V (v2.1 Table 14) and
under the 3.6 V abs max. RFBB 29.4 k is inside the recommended 10 k–100 k.

**The bottom-view-as-top-view trap was tested by SOLVING THE TRANSFORM, not by
looking.** From the gerbers, U2's pad 1 at (144.0756, 68.2839) and pad 25 at
(127.5656, 85.7839) give a transform with **determinant +1 — a plain 270° rotation,
not a mirror** — and numbering runs counter-clockwise from top-left exactly as v2.1
Figure 3 draws it. Pitch 1.27 mm, rows at ±8.75. **The antenna overhangs the board
edge and no copper sits in the keep-out.**

**D2/D3 were the reviewer's top suspect and they are correct**, which also disposes of
an alarm raised mid-review. LCSC C260296 is **MBRB2060CT, a dual common-cathode
Schottky**, not a 2-pin part: onsemi MBRB2060CT/D p. 1 cites **CASE 418B STYLE 3 =
anode / cathode / anode / cathode(tab)**. The netlist puts pins **1 and 3 both on
PUMP_x_LO** (anodes paralleled) and pad 2 on VBAT — correct freewheel orientation for
a low-side switch. The land was checked too, not just the name: our `TO-263-2` places
pads 1 and 3 at **5.08 mm** with pad 2 as the 9.4 × 10.8 tab, and onsemi's own
soldering footprint (CASE 418B-04 p. 2) is "2× 3.504 × 1.016, 5.080 PITCH" — the
D2PAK-3 of this device has only the two outer leads. **A sub-agent flagged this part
as a mismatch against a 15 A / 0.59 V expectation; the parent resolved it against the
netlist and the land, and the flag was wrong.** Recorded because the alarm was
circulated before the resolution was.

**Pass 2's headline: no re-spin on pin functions.** VBAT_SENSE is on IO35 =
**ADC1_CH7** and JOY_FILT on IO34 = **ADC1_CH6** (v2.1 §3.2 Table 3; ESP32 Series DS
v5.3 Appendix A.4 Table IO_MUX rows 10/11). **Both analogue inputs are on ADC1, so
the ADC2-is-unusable-with-WiFi trap never applies** — the single highest-value check
in that pass. The ADC2 pads that are populated carry digital roles only.

**All five strapping pins boot to the right value, four of them by being deliberately
unpopulated** (v2.1 §4 Table 4: the internal weak pull sets the level when a pin is
"not connected to any circuit"): IO0 wpu→1 → SPI Boot; IO2 wpd→0, only consulted
when IO0=0; **IO12/MTDI wpd→0 → VDD_SDIO 3.3 V, which the module's flash requires
and nothing on this board can pull up**; IO15/MTDO wpu→1 → boot log on U0TXD, wanted
for bring-up over J6; IO5 wpu→1 → SDIO slave timing, don't-care.

⚠ **AND THE SIGN-OFF'S OWN ARGUMENT WAS WEAKER THAN THE RESULT.** M8 argued "no pump
gate or the buzzer lands on a strapping pin" — true, but it only tests the pins that
*are* used. The question that matters is what the five strapping pads see at reset,
which is the table above. The conclusion survives; the reasoning has been replaced
with one that actually addresses it.

**Also confirmed, each against its datasheet:** U3/U4's IN− tied to GND is what
SLUSAY4D explicitly requires for non-inverting use ("OUT held LOW if IN- is unbiased
or floating"), and with "Output Held Low When Input Pins Are Floating" plus R6/R7's
100 k gate pulldowns **the pumps cannot self-start while the ESP32 is in reset**.
UART0 is **not** crossed (pin 35 TXD0 → J6.3, pin 34 RXD0 ← J6.4 via R25). EN has
R3 + C8, satisfying Table 3's "do not leave the pin floating". Diode polarity was
resolved from the library's F.Fab cathode bar rather than assumed, giving D6
cathode→SW (correct for a non-synchronous catch diode), D1 cathode→VBAT,
D4 cathode→+3V3, D5 cathode→VGATE. Q1/Q2 gate/drain/source and the ±16 V VGS limit
against a 10 V rail. L1's ripple computes to 0.56 A pk-pk at 21 V/500 kHz, peak
2.28 A against Isat 4.6 A, and min on-time 314 ns against the 75 ns limit (§5.6).
F2 is in the pack lead with **D1 on the fused side** — the right order.

**Pass 2 also closed a gate gap it was not asked to find.** `tools/check_pin_map.py`
had rules for ADC1, ADC2, input-only and strapping pins but **none for GPIO6–11, the
module's internal flash bus** (v2.1 Table 3 note 2; module pins 17–22 are NC). A
firmware pin moved onto 6–11 would have passed. `FLASH_BUS` added. The netlist puts
nothing there, so this is a gate gap, not a board defect.

**And the deliverable is the firmware, which is the check.** `firmware/src/pins.h`
and `pins.cpp` name all twelve connected module pins with a datasheet reason each,
and preserve one ordering that matters: **both gates are driven LOW as plain outputs
before `ledcAttach`**, because `ledcAttach` leaves the pad driven from a channel whose
duty is undefined until the first `ledcWrite`. Pass 2 also established that the
**no-twitch guarantee during boot is hardware, not firmware** — IO25/26/27/14 are
`oe=0, ie=0` with no internal pull from reset until `pinsInit()` runs (DS v5.3
Appendix A.4, "At Reset" column), so what holds the pumps off is UCC27517's internal
IN+ pull-down plus R6/R7, and what holds LEVEL at "not full" is R23.

#### ⚠ What these two passes could NOT verify, named rather than glossed

Pass 1's WebFetch quota ran out after the critical parts. **Not read from their own
datasheets:** SMCJ24A (C310039 — the clamp-coordination check above used Littelfuse
SMCJ-series figures Vwm 24 / Vbr min 26.7 / **Vc 38.9 V** from memory; every
downstream part survives 38.9 V, but **confirm those three numbers**, because M26 and
finding 31's headroom both lean on them), MMBT3904 (C20526 — pinout taken as the
standard SOT-23 NPN B/E/C, which the circuit corroborates), D6 (C7428237, 60 V/3 A
from the BOM comment and the LCSC listing only), F1 (C69680), F2's holder (C207061),
BZ1 (C252936), and the Phoenix MKDS blocks. For D2/D3 it used onsemi's and Vishay's
MBRB2060CT datasheets rather than SMC/Sangdest's own, which LCSC would not serve as
text — the pin style and 5.08 mm two-lead footprint are JEDEC CASE 418B and not
vendor-specific, but the SMC drawing is the one to glance at to make it airtight.

**Passes 3 and 4 are still running** (the new voltage-vs-pin-rating rule in canonical
cadkit, and the custom footprints against the makers' land patterns). Pass 4 was
holding for its own research sub-agent's citations rather than report three parts
uncited, which is the right instinct and is why it is not here yet.

---

### 36 — CLOSED: validation pass 3 built the missing rule, and it found two pins M5 never mentioned

**The lead's pass 3 was right that no rule covered voltage against rating.** There is
one now: **A16, "No pin sees more than it is rated for"**, in **canonical**
`../cadkit` (commit `652cc8b`) and propagated to **11/11 consumers with no repo
skipped** — not hand-edited into the vendored copy, which is the drift that collided
with the pedal steel project's A13 and cost a day. A16 was the next genuinely free
id, confirmed against `RULES` in `quality.py` rather than assumed.

**Nothing is baked into the rule.** A project declares two things in
`BOARD_NOTES["quality"]`, in the same style as `power_paths` and `pinouts`:

* `net_volts`: net name **or fnmatch pattern** → steady `v`, transient `peak`, and a
  `why`. Exact key beats pattern, most-literal pattern wins. **An undeclared net is a
  hard FAIL**, so the rule cannot be defeated by silence.
* `pin_volts`: `ref.pin` / `ref` / `value` / `footprint` (or pattern) → `max`, `peak`,
  per-pin overrides, and a **required `src`** wherever there is a number.
  `"max": "none"` plus a `why` declares "no net-to-ground rating applies here" and
  **prints** — 14 such pins on this board (the test pads, L1's winding, U1's
  BOOT/RT/SS).

One default only: a capacitor whose BOM value already carries its rating (`10u/25V`)
is read there. **`ZENER-10V` and a `3V` buzzer are deliberately NOT parsed — an
operating point is not a limit**, and that distinction is the kind of thing that makes
a rule trustworthy rather than merely green.

**Steady state and clamped transient are separate claims against separate ratings**,
which is the design decision worth recording: steady over-rating is **hard**; a
transient over-rating is **soft** and answerable only by a declaration naming what
makes it inapplicable — the part *is* the clamp, the rating is an *interruption*
rating, the datasheet gives a transient figure, or the surge reaches the pin only
through an impedance its own clamp absorbs.

#### Made to fail — six ways, on temp copies of the real board

| case | answer |
|---|---|
| unbroken board | **no failure, and a measurement**: 119 pins graded, 105 against a number, tightest steady margin **0.3 V at U2.10 (PWM_B), 3.3 V on a 3.6 V pin** |
| 20 V net on a 16 V part | hard: names part, pin and both numbers; **a waiver is ignored** |
| one pin's rating deleted | **hard FAIL, not OPEN** — justified: OPEN is for questions a script cannot ask, and here it asked a named pin and got no answer |
| every rating absent | hard: "not one of the 119 pins on a live net has a NUMBER … A16 can make **NO CLAIM**" |
| no net voltages at all | hard: "an unmade check, not a clean board", and nothing is graded |
| transient raised to 100 V | **44 soft** clamped-transient failures and **zero** steady-state ones — a different, correct answer |

The unbroken case passing is the half that makes the harness mean anything, and the
"no claim" case is the one that matters most: a rule whose data is missing must say so
rather than report a clean board. That is the same failure mode as `fab_frames.derive`
saving an empty table (finding 24).

#### ⚠ The two real findings — both pins M5 judged against the clamp and never named

M5 weighed five parts against D1's 38.9 V clamp. **Writing the declaration found two
more it had missed.** Both survive, and the reasons are now per-pin declarations read
on **every** run rather than prose, and appended to M5's sign-off:

**1. F1 is the one part on VBAT rated UNDER the clamp — a 30 V PPTC against 38.9 V.**
(`PTC-30V-200mA`, on VBAT and VBAT_LVL.) It survives because **a PPTC's voltage rating
is a withstand rating for the TRIPPED device.** It is not tripped during a surge —
milliseconds against a thermal time constant of seconds — so it is a sub-ohm resistor
in series with the load and the 38.9 V is across the pair. The only time it holds off a
voltage is after it opens, and what is behind it then is the **20 V pack**, because
D1's failure mode is a short that crowbars the rail. Steady state clears by 10 V.

**2. The clamp does not stop at the rail: U2.7 (IO35) sees 5.93 V on a 3.6 V pin.**
38.9 V × 18/118 through the sense divider. It survives because it arrives through
**100 k**: the pin's own ESD diode holds the node near 3.9 V while taking ≈20 µA, and
the tap's RC (100k∥18k × C11 = **1.5 ms**) is the same order as the 10/1000 µs
waveform D1's VC is specified on, so the node never reaches 5.93 V. The DC case —
which is what a 3.6 V absolute maximum is written for — is **3.05 V** and is asserted.

⚠ **Note how finding 2 here and finding 33 are the same divider seen from two ends.**
A16 says its transient is survivable; pass 2 and pass 1 say its *steady* reading
saturates above 20.3 V. Both are true, and the 150k/18k change finding 33 proposes
would improve both margins at once. That is the argument for doing it.

**Every figure in the declaration is either one of `elec/main.py`'s own constants or a
cited reading** — `VBAT_MAX`, `TVS_CLAMP`, `VGATE_V`, `PUMP_FET_VDS_MIN/VGS_MAX`,
`FREEWHEEL_VR_MIN`, `BUCK_VIN_ABSMAX`, `BUCK_CATCH_VR_MIN`, `LVL_FUSE_V_MIN` — with
three added rather than retyped: `SENSE_RATIO` (spelled from `RDIV_TOP`/`RDIV_BOT`),
`BOOT_SW_MAX` and `BUCK_CTRL_ABSMAX`, both 5.5 V from **SNVSAA5B rev B**, the revision
M35's own reading caught.

**Citations carried in `src`:** TI SNVSAA5B §5.1 (VIN/EN/SW 44 V; FB and BOOT-to-SW
5.5 V, rev B); TI SLUSAY4D §8.1/8.3 (UCC27517 VDD 20 V abs, 18 V rec, inputs 20 V and
**not** restricted by VDD); Espressif v2.1 Table 13 (3.6 V); Littelfuse SMCJ24A
(VWM 24, VBR 26.7, **VC 38.9 at 38.6 A** — which also answers pass 1's open caveat
that those three numbers were quoted from memory); Littelfuse FLR 178.6165 holder
**80 V/30 A, so F2 is NOT under the clamp**; onsemi MMBT3904 (VCEO 40, VEBO 6.0);
1N4148W 75 V; and the LCSC lines in `elec/fab.py` for the two capacitors whose value
string carries no rating. Resistors use class figures; the WJ500V terminals and the
2.54 header use conservative declared figures, **stated as such in `src`**.

**Board result: 0 unconnected, 0 violations, quality 0 FAIL, 0 OPEN** (1 pre-existing
waiver). A16 itself: **151 rows checked, 0 FAIL.**

#### Two things to know about the propagation

* `public-steel-guitar/elec/out/can_tee` — the only other project with a routed board
  — was **already at 5 FAILs and 22 OPENs**, and A16 adds a 6th because it declares no
  `net_volts`. **A new rule failing an old, already-unclean board is the documented
  behaviour, not a regression**, but that project now owes A16 a declaration.
* Running that board's pass **overwrote its untracked `can_tee.quality.json`**. Harmless
  (it is a build artifact) but recorded, because a validation pass that writes into
  another project's tree is the kind of side effect that should never be a surprise.

**M5 was narrowed to the judgement A16 cannot make**, rather than left overlapping it,
and the learnings log carries a row. Pass 4 — the custom footprints against the
makers' land patterns — is the one pass still outstanding.

---

### 37 — CLOSED: F2's 1.4 mm holes could not accept the holder's own pins, and the fab's pad-hole floor then capped the cure

**Validation pass 4, and it is a hard assembly stop — the part physically will not go
in.** Littelfuse 178.6165.0002 datasheet **p. 2 ("Dimensions", bottom view)**: terminal
pin **width 1.4 ±0.1 mm**.

| | ours | Littelfuse | deviation |
|---|---|---|---|
| drill | **1.400 mm** | not published | — |
| finished hole after plating | ≈1.32–1.35 mm | — | — |
| pin **width alone** | — | 1.4 ±0.1 (→ **1.5 max**) | **−0.15 to −0.65 mm short** |

**A nominal 1.4 mm drill finishes at ≈1.33 mm plated — smaller than the pin's width
before its thickness is considered at all.** Taking the front view's 1.2 mm as
thickness, the pin diagonal is √(1.4²+1.2²) = **1.845 mm** nominal and **1.985 mm**
worst case, so the hole wants ≈2.0 mm. **Even on the most generous reading** (a thin
0.8 mm stamped terminal) the diagonal is 1.61–1.70 mm. **Under every interpretation the
hole is undersized.**

**Knock-on, which is why this is a re-spin and not a drill tweak:** at a 2.0 mm drill
our 2.2 mm pads give a **0.10 mm annular ring**, below the ≈0.13 mm PTH minimum at
JLCPCB class — so the pads must grow to **≥2.3–2.4 mm** too. At 2.4 mm pads on the
2.5 mm row pitch the two rows within a terminal merge (0.1 mm gap, same net —
acceptable, but effectively a slot).

⚠ **Stated plainly: Littelfuse publishes NO recommended PCB layout.** p. 2's
"Recommended Assembly" is two cross-sections carrying **no numbers at all** — no pad
diameter, no hole diameter, no annular ring, no plating callout, no keepout, no
courtyard. **This finding is derived from the published PIN dimension, not read off a
land pattern.** So: **measure the physical holder before committing the new drill.**
The owner has this part in hand, which makes that a five-minute job with calipers and
the only responsible way to pick the number.

**Why nothing caught it:** every gate this repo has checks our geometry against
*itself* or against the fab's rules — annular ring, hole-to-hole, clearance. **Not one
of them compares a hole to the pin that has to go through it**, because the pin's size
lives in a datasheet and nothing had read it. That is exactly the gap pass 4 existed to
close, and it is the single most expensive thing the four passes found.

### 38 — CLOSED: U1's exposed pad had four deficits stacked in the same direction

**Pass 4, against TI SNVSAA5B package drawing 4214849/B (p. 31 outline, p. 32 example
board layout, p. 33 example stencil) and app note SLMA002H §2.4 pp. 8–10.**

| item | ours | TI | deviation |
|---|---|---|---|
| EP copper | 2.29 × 3.00 (6.87 mm²) | **2.95 × 4.90** (14.46 mm²) | **−52 % copper** |
| EP mask opening | 2.29 × 3.00 | **2.71 × 3.40** (9.21 mm²) | **−25 % solderable** |
| mask definition | mask = copper exactly | **solder-mask defined** (copper larger) | not SMD |
| thermal paste | 4 windows = 4.80 mm² | **solid 2.71 × 3.40 = 9.21 mm²**, "100 % printed coverage" | **52 % of TI's volume** |
| thermal vias | 6 × ⌀0.30 | **8 × ⌀0.20**, 1.30 pitch both axes | +0.10 dia (2.25× hole area), −2 vias |

**And the land is smaller than the package's own maximum exposed pad.** Our 2.29 × 3.00
opening sits between the package's min (2.11 × 2.80) and **max (2.71 × 3.40)**, so a
max-size part's exposed pad **overhangs our mask opening by 0.21 mm per side in X and
0.20 in Y, landing on solder mask.** SLMA002H p. 9 and the p. 32 drawing both say to
define the SMD pad to the **maximum** exposed-pad size. Between min- and max-size parts
the joint therefore varies lot to lot — rocking, tilt, poor wetting.

**Net: a thermal pad 25 % undersized, getting 52 % of the prescribed paste, with six
open holes draining it (finding 32), gas-trapped by far-side tenting — on a 2-LAYER
board**, where SLMA002H §2.3 p. 4 notes the surface layers are all the heat removal
there is. Findings 32's two items are mask/stencil gerber edits; these need the
footprint re-cut to TI's 2.95 × 4.90 copper and 2.71 × 3.40 SMD opening.

**Separately — U1's signal pads are 0.40 mm too long, all of it inboard (yield risk).**

| | ours | TI | deviation |
|---|---|---|---|
| pad | **1.95 × 0.60** | **1.55 × 0.60** | **+0.40 length** |
| pitch | 1.270 | 1.27 | exact ✓ |
| outer-edge span (toe) | 6.90 | 6.95 | −0.05, negligible |
| inner-edge span (heel) | 3.00 | 3.85 | **−0.85** |
| **lead pad ↔ EP solder gap** | **0.355** | **0.570** | **−0.215, −38 %** |

The toe is right; **all 0.40 mm goes inboard, under the body, toward the exposed pad.**
TI's own p. 32 note says the EP is mask-defined specifically "to prevent shorting to
leads", and we have eroded that gap by 38 %. Compounding: our signal paste is
**+26 %** per lead at the same time the EP gets **−48 %** — so **the leads will float
the package off a paste-starved thermal pad while carrying surplus solder 0.355 mm from
it.**

### 39 — CLOSED: 2.124 mm of board remained under the ESP32's antenna, and the pad-39 vias drained its thermal joint

**Pass 4 derived the antenna geometry independently from Edge.Cuts and the gerbers.
It confirms the earlier overhang reading and CORRECTS it: the overhang is partial.**

| | |
|---|---|
| board outline | x 52.5..147.5, y 44..156 |
| antenna tip → board | x **151.566** |
| board edge | x **147.5** |
| **antenna overhang** | **4.066 mm** |
| antenna-area boundary (the 6.19 line) | x **145.376** |
| **FR4 left under the antenna** | **2.124 of 6.19 mm = 34.3 %** |

**Copper is fully compliant with margin, and that part is a genuinely good result.**
Zero F.Cu beyond x 145.376 in y 53.0..101.1; the **B.Cu plane is notched to exactly
145.3756 — 0.000 mm margin**, cut to the footprint's own keepout polygon; no tracks,
vias or silk in the band. Lateral extent ±24 mm against Espressif's **Min 15**, and
15.0 mm past the tip against **Max 1** (ESP32 Hardware Design Guidelines **§1.4.8,
Fig. 25**). We exceed both.

**Board MATERIAL is not compliant.** §1.4.8 gives exactly two acceptable options:
(a) preferred — antenna **outside the base board** (Fig. 23 marks only the two
**corner** positions ✓); (b) fallback — **cut the base board away on both sides and
below the antenna**, back flush to the 6.19 line. Fig. 25's keepout is labelled
"Clearance Area" and the outline is **notched through it** — it is board-material-free,
not merely copper-free. **We satisfy neither**: the antenna is 66 % off the board but
2.124 mm of laminate remains — and that remainder is the antenna **root**, next to the
body, **the most dielectric-sensitive part of the meander.** Secondary: U2 sits
**mid-edge**, 24.03 mm from the nearest corner, and Fig. 23 marks only corner
positions ✓.

**Two fixes, both free before ordering, and they cost different things — so this is
the owner's choice, not mine:**
* **shift U2 outboard by 2.124 mm** (origin x 138.8156 → 140.9396), leaving pads 1/38
  at 146.95, i.e. 0.55 mm inside the edge — tight but manufacturable. Costs a
  **re-route** of a board that currently passes everything.
* **notch Edge.Cuts back 2.124 mm** across the 18 mm module width. No re-route, but it
  changes the **board outline**, which the housing bay is cut to — so it costs a
  housing change and a re-run of the geometry gate.

⚠ **And it is three-dimensional:** §1.4.8 asks for **≥15 mm clearance in all
directions** around the antenna *inside the enclosure*. That is a constraint on the
printed housing that nothing in `src/housing.py` has ever checked.

**Also, the pad-39 thermal joint has U1's disease in a different form.** Our array
geometry reproduces Fig. 13 **exactly** (see finding 40), but the **via pads** do not:
ours are **0.700 mm** on a 0.300 drill where Espressif draws **⌀0.25 with no separate
pad**, placed in the 0.5 mm gaps. 0.45 + 0.35 = 0.80 > the 0.700 centre distance, so
**our via pads overlap the squares by 0.10 mm and fill the gaps Espressif deliberately
leaves.** Confirmed in the gerbers: F.Mask has **21** openings there (9 squares + 12
via circles) and B.Mask has **12** — so the nine discrete masked islands Espressif
intends have become **one continuous perforated patch with 12 barrels open on BOTH
sides.** Molten solder has an uninterrupted path to the far side. Fix: via pads
≤0.55 mm and tent the barrels component-side.

### 40 — CLOSED: pass 4's positives, and it INVERTS what finding 24 concluded about the frames

**The ESP32 land is an exact 1:1 reproduction of Espressif Fig. 13 (v2.1 p. 43) on
every published dimension** — 38 perimeter pads, 1.270 pitch, 17.500 side-row c-c,
19.000 outer span, 16.510 pad 1→14, 11.430 bottom-row span, **7.490** module-edge to
pad-1 centreline, **6.190** antenna depth, 3.700 × 3.700 pad-39 envelope, 0.9 × 0.9 on
1.400 pitch, **7.500** and **10.290** pad-39 centre offsets, 12 vias on the gap
mid-points. **No deviation anywhere except the via pads of finding 39.** For a
hand-drawn footprint that is the strongest single result in the audit.

**Q1/Q2 match Infineon's PG-TO252-3-901 drawing to within 0.05 mm on every dimension**
— lead pad 2.20 × 1.20 *identical*, tab 6.40 × 5.80 *identical*, overall across 5.800
*exact*, pitch 4.560 vs 4.580, tab-to-lead centre 6.300 vs 6.350, clear gap 2.000 vs
2.050.

#### ⚠ AND THAT INVERTS FINDING 24's CONCLUSION ABOUT THE HAND-ENTERED FRAMES

`elec/fab_frames.json` records Q1/Q2's hand reasoning as a residual of **"0.31 mm on
the leads and 0.62 on the tab"** against **the fab's library** footprint, and finding 24
presents that as our deviation to be excused. **It is not ours.** Against **Infineon**
we are within **0.05 mm**. So the 0.31–0.62 mm belongs to **the fab's library**, and
**our land is the one that matches the manufacturer** — which means a disagreement in
the fab's 3D previewer is **evidence against the fab's footprint, not against ours.**

The same logic applies to the `TO-263-2` note ("the fab draws the tab 1.44 mm further
from the leads than we do"): our two-lead-plus-tab topology matches **onsemi CASE
418B-04 p. 2** ("2× 3.504 × 1.016, 5.080 PITCH"), with our pitch **5.080 exact**. The
fab's library is the deviant one there too.

**This is worth more than the measurement itself.** Finding 24 closed M2 by fitting our
lands to the **fab's** library and recording the residuals as ours to justify. Pass 4
asked the question finding 24's own prose flagged and could not answer — *"the reviewer
should check the land against the datasheet, which is a different question from whether
our land matches the fab's library — both can agree and both still be wrong"* — and
the answer came back the other way round.

**F2's grid is exactly right; only the diameters are wrong** (finding 37): column pitch
3.500, inner gap 5.800, span 12.800, row pitch 2.500, post 2.900 from each inner column
and 1.250 from each row — all dead on Littelfuse p. 2. **And `fab_frames.json`'s F2
reasoning is correct on both counts:** the 2.4 mm NPTH does sit at the grid's own centre
(x 6.400 of 0..12.8, y 1.250 of 2.5) so a half-turn maps it onto itself, and the
terminals need no handedness.

**Lower-severity, recorded not actioned:** F2's **2.4 mm NPTH against a 2.4 ±0.05 post**
is nominal-on-nominal interference and wants ≈2.6–2.7 (yield). **Q1/Q2's middle-lead
pad gets a 2.64 mm² paste aperture with no lead to wet it** — Infineon draws no such
pad — so it reflows into a free solder bead 1.08 mm from the gate and source; clearance
is fine (same net as the tab), the fix is **stencil-only: delete that F.Paste aperture,
keep the copper**. **Mask-coincident rather than mask-defined** board-wide
(`pad_to_mask_clearance 0`) — cosmetic, ≈±0.05 mm registration. **D2/D3 lead pads
+1.10 mm** vs onsemi (+42 % paste on a 10 A leg) — cosmetic. **Tab stencil coverage
90.4 % (DPAK, vs Infineon's own 87.3 %) and 94.1 % (D2PAK)** — the D2PAK's is
effectively solid, where 50–80 % is usual for a tab that size, so expect some voiding
and skew; no published figure to fail against. **D2/D3 have ZERO thermal vias within
6 mm of the tab on a 2-layer board** — layout rather than land pattern, flagged.
**And the library has drifted from the board:** both `.kicad_mod` files declare EP via
pads of 0.5/0.6 mm where **both board instances are 0.699998** — no fab consequence
(0.20 mm ring), but findings 32/38/39 must be applied to **both** the library and the
board.

**Scope correction worth recording:** only **two** of the five are actually hand-drawn
(`SOIC-8-1EP-FABDRILL`, `ESP32-WROOM-32E-FABDRILL`). `TO-252-3_TabPin2`, `TO-263-2` and
the fuse holder are **KiCad 10.0 stock footprints used unmodified**, verified pad-for-pad
against the installed library. And **three of the five parts have no manufacturer land
pattern at all** — Infineon's is a separate drawing rather than the datasheet, and SMC
and Littelfuse publish none — so for D2/D3 and F2 the comparison rests on package
outlines plus onsemi's equivalent-case footprint, which pass 4 marked as the limit on
those conclusions.

---

### 41 — CLOSED: every cable is modelled end to end, on cadkit's own helpers

**This was the owner's own request, and it is the request that found finding 21** — you
cannot route a cable without asking where it leaves from. `src/wiring.py` models all five
field cables as **solids**, every conductor separately, and `src/build.components()`
appends them so `check_overlaps.py` weighs them against the housing, the lid, the board,
the timber, the hoses and each other. **32 components, 0 unintended overlaps, 15
conductors, 5389 mm of wire to buy.**

Two corrections from the owner shaped this, and both were right:

**1. It was not using the cadkit octagon helper.** `cadkit/cables.py` already existed and
this file had reinvented a round sweep. It now imports `oct_cable`, `bundle_paths` and
`path_length`. That matters for a reason the helper's own docstring states: a sphere
meeting two cylinders along a shared circle is the tangent case OCCT handles worst, and
**it fails silently** — the fuse returns one valid solid with material missing from the
middle (645 of 1776 mm³, once). Octagonal prisms, across-flats = the conductor OD so the
real round cable fits inside, rolled 22.5° so a flat faces each principal direction.

**2. Only the pack pair was complete.** The other four stopped at the chase. All five now
run to their real destination: the pack pair across the plate's wire slot and along the
back of it to the Makita block; the two pump pairs to the **actual motor lead tips**,
found by cylinder radius and axis, the same idiom as `pump_frame._pump_bores`; the
joystick and the level sensor out of the bay and up to the wand and the tank.

#### The gate finding 21 never had

Every mouth is asserted **over the chase** and **within 20 mm of it**, the second message
saying why: *"that is not a drop into the chase, it is a climb down the board — which is
exactly finding 21."* Measured as built: **all five mouths sit 6.65 mm above the bay
floor**, a straight drop with no bend at all. That is *why* the −Y edge is the right edge,
and it is now a number rather than a belief.

**Made to fail ten ways, all ten caught** — a mouth off the chase in Y (finding 21
itself); a mouth 92 mm up the board (J5's actual old position); the pack pair declared not
to cross the plate; a conductor thicker than the slot; the slot's own 17.8 mm
justification broken; the fan-out band poking into the lid's skirt; a lane sitting on the
line every cable drops down; two cables sharing a band level *and* crossing in plan; a
pump's conductors paired to leads by index; and the pack pair given no room to turn.

The tenth case is the interesting one, because it **failed to fail twice**. The splay
check lived inside `routes()`, which nothing called until a CAD build — so a harness that
probes by importing could not reach it, and reported MISSED on an assert that was
perfectly correct. `ROUTES = routes()` now runs at import, like the band-crossing gate
beside it. *An assert that only runs inside a 20-second build is not a gate.*

#### Four things the model found that nothing else would have

**1. `lead_exit()` is the wrong answer — see finding 28.** The one canonical helper for
"where does a cable leave this connector" returns a **top-entry** point for all five
terminals, silently: it sees "Horizontal" in the fpid, takes the side-entry branch, keys
on `name[:7]` = `"Termina"`, misses, and falls through. Built on it, five cables would
have left perpendicular to the board and missed the chase entirely. The entry face is now
**declared** (`ENTRY_FACE = "board -Y"`) rather than inferred, because the inference it
would have to make rests on 0.6 mm of a simplified block and gets it backwards.

**2. A gathered bundle through a one-layer-deep slot — see finding 29.** 15.1 mm³, and
the fix was to draw the cable **as it lies**: side by side, because the slot is 5 mm tall.

**3. A constant world offset is not a bundle.** Holding the pack pair's Y offset through a
run that then turns *onto* Y put both conductors on one centreline — **1057 mm³ of cable
through cable**. `bundle_paths` offsets in the bundle's own cross-section instead, which
is precisely the failure its docstring describes. Three more of the same family followed
and each was fixed by deriving rather than picking: the lid's skirt reaches **z 10.55**,
*below* the bay floor, so a lane at 11.0 was inside it (`BAND_CEIL` now reads the skirt);
all five cables drop at the same x, so a lane near it clipped the drops (`LANE_X0` is now
derived from the drop line); and J5 climbed at a hand-picked x that landed 0.5 mm from
J4's lane (it now climbs on its own lane). A lane is one index, three derived numbers.

**4. Index order is not position order.** Which side of the bundle a conductor emerges on
depends on the section frame's handedness at the last segment. Paired to the motor leads
by index, pump A's two conductors swapped sides and crossed **through each other** for 2.8
mm — 36.4 mm³, found by the overlap gate. Nearest-lead pairing plus the splay assert
above; order-independent, and it fixes itself if a lane or a pump moves.

#### And one thing it proved, which is the better kind of result

**The pack pair's 100 mm run between the plate and the timber is clear, and nobody had
ever checked.** It is the obvious place to pinch a 7.5 A pair: the plate bolts **flat** to
the posts, so the nominal gap where they meet is **zero**. Probed with a 3.30 mm conductor
at `BACK_X + 2` across the whole path (y 40..170, z 8..60): **no timber anywhere**; and
sweeping +X from the plate's back face at the slot, mid-run and the dock finds **none
within 200 mm**. The frame is slender members and the plate meets it only at the wood
screws, so the leads run in open air between them. Asserted now, and drawn, so the overlap
gate keeps watching it.

**Residual, honest:** the pair stops **1.0 mm short** of the contact block rather than
inside it. A lead really does enter its terminal, but the bought block models no solder
tabs, so stopping at the envelope claims "the pair reaches the dock with a path" without
asserting anything about geometry that is not drawn. Lengths are therefore **floors**:
5389 mm is what the centrelines measure, not what you should cut.

---

### 42 — OPEN: the Makita terminal has NO retention along X, and v1's came from the slide-on joint

The owner asked whether v1's terminal retention relied on the housing being a slide-on
part with joinery. **It did, and that is exactly what v2 removed.**

**v1** (`git show 54a1e93^:src/backpack_housing.py`): the dock had a through-'t' pocket
that located the block in plan, and `_dock_transform` trimmed the dock's back at the
connector's flange-back plane and pre-shifted it so that *"trimmed back (the flange) lands
on the wall, flush — the wall retains the connector with no separate pads."* The housing
was `dock(joinery=True)` with `_dovetail_tenons` cutting the matching rails; sliding the
housing on brought the wall up behind the flange. **Pocket in front, wall behind — two
faces, one of them delivered by the joint.**

**v2** unioned the dock into the single printed housing, so there is no joint and no
separate wall arriving from behind. Then, because the block could no longer be dropped in
during assembly, `_terminal_window()` cut the back plate open so it could be inserted from
the **rear** — which removed the only thing that ever held it along X.

**Measured on the current model, not argued:**

| probe | result |
|---|---|
| seated housing ↔ terminal contact | **0.000 mm³** |
| slide ±8 mm in X, 1 mm steps | **0.0 mm³ at every step — completely free** |
| ±Y, ±Z | **blocked both ways** by the 't' pocket |
| push +2 mm inboard | hits the **timber**, 669.3 mm³ |
| pull outboard | **nothing at all** |

The block's bbox spans x −205.25..−183.00 and the plate only occupies −193.2..−190.0. So
the wood is an **accidental** backstop with roughly 2 mm of slop, and the direction with
no stop at all — outboard — is the direction friction drags the block every time the pack
is withdrawn. Y and Z are fine; X is unretained, and the load along X is the one load the
part actually sees.

**Also wrong, and found while measuring this:** `_terminal_window()`'s docstring claims
the cutter makes *"flange lips ... mitred 45 degree seats"*. `_terminal_t_cutter()`
explicitly does not — its own comment says *"The cut passes fully through Z, so there is
no Z wall to clear."* A docstring describing a feature that is not cut is worse than no
docstring, because it is what the next reader will check against.

**Not fixed here, and deliberately not guessed at.** The candidates are a printed cap or
retaining lip over the flange after insertion (M2, so it goes with the existing hardware),
or reinstating a captive face by splitting the dock's back off as its own part. Both change
the printed housing and the print orientation it was validated in, which is a change to
make on purpose rather than at the end of a wiring session. What is now true is that the
gap is **named and measured** instead of remembered.


### 43 — CLOSED, and it was five times the finding it was raised as: the vendored cadkit had been forked, not copied

Raised as a stale merge plus one hand edit. `diff -r` against canonical said otherwise:
**eight files diverged beyond line endings and one file existed only downstream.** A
vendored copy is supposed to be a copy, so every one of those was either a fix the other
ten consumers were missing, or a fix that had been lost — and the first propagation
attempt **crashed**, which is how the largest of them was found at all.

#### Lifted UPSTREAM, because they were cadkit's work sitting in the wrong tree

| file | what it was | why it had to go up |
|---|---|---|
| `pcbflow/route.py` | three defects in post-route bring-up-pad siting | the worst put a test pad on a VBAT track: **a 27.8 mm short from the battery to a GPIO** |
| `pcbflow/layout.py` | zone `poly` + `priority`; a connectivity pointer held across a rebuild | the pour mechanism **this board's VBAT and pump rails are built on** |
| `pcbflow/close_last.py` | two vias 0.067 mm apart are one via | DRC grades it `hole_to_hole` "actual 0.0000 mm" and calls it a **WARNING** |
| `pcbflow/fab_package.py` | a requirement-shaped value is not an orderable part | a part nobody had sourced read as **sourced** |
| `pcbflow/unwick.py` | a via in a solder land drains the joint | **299 lines, entirely generic**, downstream-only |
| `board_geom.py` | `D_SMC` has a height | DO-214AB, dim D max |

Two commits upstream (`2356e19`, `a9e0f12`), each carrying the measurements with it.

**The crash is the part worth keeping.** Propagating canonical over the vendored
`layout.py` made the board build die with `ValueError: too many values to unpack (expected
3)` on `notes["zones"]`. That is a four-element zone entry meeting a three-tuple unpack —
i.e. **the project's own pour regions, which nothing upstream knew about**. Had the
conflict resolved the other way, or had nobody run the board after propagating, the loss
would have been silent until the next spin. *A fork announces itself only when you try to
merge it; the longer you wait the more it announces.*

**And canonical was wrong where downstream was right.** `conn = board.GetConnectivity()`
held across `BuildConnectivity()` — the exact use-after-free `layout.py` documents at
length in two *other* places — was still live in a third, upstream, after being fixed
downstream. Two complete routing runs had already been thrown away on its symptom
(`'SwigPyObject' object is not iterable`, and once `LoadBoard()` itself returning a bare
SwigPyObject, because a freed object takes out SWIG's type registry process-wide).

#### Superseded by canonical, deliberately not lifted

`board._pcbflow_removed` parked removed vias on the board object; canonical's module-level
`_REMOVED` is the same fix with the **right lifetime** — the process, not one board. A14
(paste-only apertures), A15 (nearest ground layer in the stack-up) and A16's signed
bounded `accepted` are all newer upstream than the vendored copies.

**The vendored tree is now byte-identical to canonical** (`diff -r --strip-trailing-cr`,
exit 0) for the first time in this project's history.

#### What the nine upstream commits cost to absorb: one new gate, and it was not free

The lettering work (`3b43c0e`) gave `check_board()` an `ink=` argument: **every label the
routed board prints must have ink in the solid the assembly places.** The first run
reported **104 disagreements**, every F-side label on the board — because `pcb_silk()`
was being *added to the viewer* and never *checked against anything*. The owner's note had
been "there is no silkscreen in cad"; drawing it answered the note, and only this hook
makes it a claim. `elec/cad_geom_check.py` now has an `_ink()` hook returning both faces in
the **housing's** frame, and the board reads **104 / 104**.

**Made to fail four ways, all four caught:** no ink at all (0/104 — the state the gate was
in this morning); only the front face drawn (98/104, naming the six back legends); the ink
posed in the board's frame instead of the housing's (0/104); and the ink shifted **2 mm**
(60/104). That last number is the useful one — it says the gate has real positional
resolution and is not merely counting parts.

**Residual:** nothing. Board **0 unconnected, 0 violations, 0 FAIL, 0 OPEN**; CAD 59/59
parts and 104/104 labels; all ten `check_*.py` pass; 32 components, 0 unintended overlaps.


### 44 — the owner asked whether one 18 V pack can run the motors AND the ESP32. It can, and here is the arithmetic — with three things that were not checked

**Verdict first: the scheme is sound, and the parts of it most likely to be wrong are
already right.** What follows is what held up, then three gaps, one of which is a real
unchecked margin on a part that is already in the cart.

#### What holds, and why

**The buck cannot be browned out by the motors.** This is the fear the question is really
about and it is the easiest one to retire. VBAT runs 15–20 V and the LMR14020's input range
reaches down to 4.5 V, so even an absurd sag leaves the 3V3 rail alone. The buck is asked
for `BUCK_IOUT = 0.6 A` of a rated 2.0 A, against an ESP32 that bursts ~500 mA on WiFi TX
and averages ~100 mA. **There is no operating point where the motors starve the MCU.**

**Switching noise on the shared rail does not reach the MCU in any amount that matters.**
The pumps chop 7.5 A at 20 kHz, and the ripple that puts on VBAT is the chopped current
times the source impedance — roughly 3.7 A RMS into ~60 mΩ of pack plus a very short
14 AWG pair, so of order **0.2 V p-p on a 15–20 V rail**. Behind a buck with 500 kHz
switching and 22 µF of output, that is microvolts at the ESP32. The analog inputs are the
exposed ones, and they are already handled: both sit on **ADC1** because ADC2 is unusable
with WiFi up, and JOY_FILT has its own RC.

**The gate rail is real and sized.** VGATE is a 1k5 dropper and a 10 V Zener, not a third
regulator, and it exists because the UCC27517 is a 4.5–18 V part and 3V3 is under its UVLO
(audit finding 2). At a **flat** pack the dropper delivers `(15 − 10) / 1500 = 3.33 mA`
against a declared 1.5 mA of driver quiescent plus Qg × fsw, and `elec/main.py` asserts
that inequality rather than trusting it. R9's own dissipation is asserted too, at 67 mW of
a 125 mW 0805.

**One pump at a time is what makes several of these numbers true**, and it is enforced in
firmware and gated by `tools/check_pump_dirs.py` — not merely intended.

#### Gap 1 — the input electrolytics' RIPPLE CURRENT is not checked anywhere, and it is marginal

**This is the one worth acting on.** The pump's low-side switch chops the *source* current
while the freewheel diode keeps the *motor* current continuous. So C1/C2 and the pack see a
square wave, and its RMS content is

> I_rms = I_pump × √(D(1−D))

The firmware holds effective motor voltage constant as the pack sags, so duty sits around
**0.6–0.8**, giving **3.0–3.7 A RMS** — and at 20 kHz the **electrolytics**, not the
ceramics, are the capacitive branch that carries it. C17/C20 are 10 µF 1206 parts whose
impedance at 20 kHz is ~0.8 Ω; they are there for the switching *edges* and for local
charge, and they do not help here. Splitting the chopped current between the pack (~60 mΩ)
and two 100 µF electrolytics (~0.2 Ω including ESR) puts of order **0.8–0.9 A RMS in the
pair, ~0.4 A each.**

Comparable 100 µF 50 V parts are rated **229–389 mA at 120 Hz**, which at 20 kHz becomes
roughly 300–580 mA each with the usual frequency multiplier. **So the estimate lands inside
the band where the datasheet decides it, and nothing in this repo reads that datasheet.**
`FUSE_ATC_A`-style arithmetic exists for the fuse, the inductor's Irms and Isat, the
output capacitance's ESR and the Zener's shunt — the input capacitors' ripple rating is the
one figure in the power path with **no number and no gate.**

Said plainly: this is a **lifetime** question, not a does-it-work question. An electrolytic
run over its ripple rating does not fail on the bench, it fails in a year with a dried-out
ESR, and it is the single most common failure of an 18 V motor-drive board. **Read C371283's
Irms before ordering** — and if it is under ~500 mA, the answer is more bulk, not a bigger
cap: the ripple divides between branches, so a second pair halves each part's share.

#### Gap 2 — nothing asserts the 10 A fuse HOLDS 7.5 A

`FUSE_ATC_A = 10.0` appears exactly twice in `elec/main.py`, and both uses are the dock
**inrush I²t**. The steady case — does a 10 A ATO blade carry 7.5 A continuously, inside a
sealed bay, without nuisance-blowing — **is not checked at all.** 7.5/10 = **75 %**, which
is precisely the conventional ceiling for a fuse's continuous duty, and that ceiling is
quoted at 25 °C ambient. The bay is sealed and contains the pumps' switches.

This is not a re-spin — the holder and the blade are both the owner's existing parts, and
the fix if it ever nuisance-blows is a 15 A blade in the same holder. It is recorded
because *the figure that decides it has never been written down*, and a fuse that opens on
a hot day reads to the user as a dead machine.

#### Gap 3 — CIRCUIT.md called the buck "Synchronous", in the one line that names the topology

§2 read **"Synchronous buck, VBAT → 3.3 V"**. The LMR14020 is not synchronous; it has a
high-side switch and an **external catch diode**. The table in §Supply, §6 and audit finding
4a all said so — and 4a is the record of the board being laid out **with no catch diode at
all**, because somebody believed this sentence. *The word had already cost a part once.*
Corrected, with the reason, so the one place a reader could pick up the wrong topology now
points at the finding instead.

#### What was checked and found already correct, recorded so it is not re-reviewed

The 40 V floor on every part on the battery rail against a 20 V fresh pack and a 38.9 V TVS
clamp; the TVS's I²t against the fuse's; the catch diode's reverse rating against the clamp;
the buck's duty and minimum on-time at the highest input; the inductor's Isat against the
regulator's own current limit rather than against the load; the level sensor's PTC voltage
against a fresh pack; and the FET's 60 V against an inductive clamp at VBAT + Vf. **None of
those needed changing, and all of them are asserted in the file that chooses the part.**

---

### 45 — CLOSED: J3 leaves through the port like J1, and the slot's own arithmetic was never holding the harness

The owner's call: *"Let's have J3 wiring go through the port as well instead of going
around. That'll make it more similar to J1."* It does, it is **86 mm shorter**, and it
turned up two things that had nothing to do with routing.

#### It moves the model TOWARDS finding 3 rather than away from it

Finding 3 sized the plate's wire slot at **17.8 mm**, and the arithmetic behind that figure
was **J1, J2 and J3 laid side by side**. Until today only J1 actually crossed — 6.6 mm of
the 17.8 — and the gate holding the 17.8 was asserting a **hand-written tuple** of those
three refs. So it was holding *finding 3's sizing sum*, which no longer described anything,
while the live harness went unchecked. A figure nobody could falsify, in the gate whose
whole job was to falsify it (M10's lesson again).

Now there are two numbers and they are separate:

| | what it is | value |
|---|---|---|
| `SLOT_SIZED_FOR` | finding 3's claim: J1+J2+J3, still named, still has to fit | **17.8 mm** |
| `_LAID_W` | what crosses **today**, derived from `crosses_plate` | **12.2 mm** |

Both are asserted, and `_LAID_W <= SLOT_SIZED_FOR` is the one that matters: *growing* past
what the slot was justified for fails; J3 taking it from 6.6 to 12.2 does not.

#### The route, and the thing the gate found in it

J3's mouth is at **y 155.82**, already inside the slot's 127..167, so like J1 it drops
straight down and straight out with **no sideways move under the bay at all**.

Then it stops being like J1, and the overlap gate said so immediately: **246.8 mm³ of
conductor inside the wood, per conductor.** J1 can turn and run down the back of the plate
because the dock is at y 46 and that side is open. Going the other way meets the frame's +Y
end plank, which at `DOCK_RUN_X` is **solid timber from y 172 to 210 at every height** —
probed on a y-z grid at ten heights from z 8 to z 200, with no way over, under or through.

So the route steps **inboard in X first**, into the gap between that plank and the pump
assembly, and `PASS_X` is **derived from the pump** rather than picked: the pump assembly is
the harder of the two limits because it is 200 mm deep in Y (it spans y 2..208), which is
also the reason no cable can cross the machine *inside* the frame and why the cross-machine
run happens beyond y 210 at `CROSS_Z`.

#### Three gates that were self-selecting, and are not now

1. **The slot asserts named J1 in the code as well as in the message.** Two cables use the
   slot, so a check that only ever looked at J1 would have said nothing about J3 — the
   same shape of mistake as the slot-fit asserts that once looped over a list they also
   selected. Both are now `for _ref in LAID_FLAT`.
2. **`FAN_ORDER` was a hand-written tuple.** It is now the **complement of
   `crosses_plate`**, with asserts that the two sets partition the cables and do not
   intersect. Listing it was how J3 could change route and still be handed a lane, a band
   height and a turn offset that nothing used.
3. **Nothing checked that two cables in one slot are in different places in it.** They lie
   flat, side by side, so what separates them is Y: half of each bundle's laid width plus
   air, derived from the mouths. J1 and J3 have **11.75 mm of mouth spacing against 6.1 mm
   of half-widths**.

**Made to fail — fourteen cases across the two harnesses, all fourteen caught.** The four
new ones: a port cable's mouth outside the slot's Y span; two port cables' bundles
overlapping inside the slot; the pass lane derived outboard of the back plate; and a cable
both crossing the plate and taking a lane in the band.

**And three existing cases had to be repaired, which is the useful part.** Each failed for
its own reason and none of them because an assert was wrong:

* *"the pack pair is declared not to cross the plate"* replaced the **first**
  `crosses_plate=True`. That emptied the port when J1 was the only crossing cable; now it
  leaves J3 crossing, so **the case stopped testing what it names**. It replaces every flag.
* *"the slot's own sizing justification is broken"* thickened 16 AWG to 3.20 mm and now
  fires on **J3's bend into the slot** instead — see the residual below. Perturbation
  reduced to 2.85 mm so it reaches the sum it is aiming at.
* *"the pack pair has no room to turn"* expected the words *"cannot make that corner"*, and
  generalising the assert to every port cable changed them to *"the corner"*. **A gate whose
  harness matches on message text is a gate whose message is part of its interface.**

#### Residual, measured and thin

**J3's turn into the slot has 0.4 mm of margin.** It is declared `flex=True` — worn, walked
past, pulled — so it gets the 5×-OD bend radius: 2.80 × 5 = **14.0 mm needed against the
14.4 mm** of drop from mouth to slot. It passes, and the assert holds it, but it is the
tightest number in this file and anything that raises the bay floor or thickens that
conductor takes it out. **Not fudged by reclassifying J3 as `fixed`**, which is the obvious
way to buy 5.6 mm and would be a lie about a cable that leaves the machine.

Clean afterwards: **32 components, 0 unintended overlaps**, 5157 mm of conductor (down from
5389), and all ten `check_*.py` plus the CAD/fab agreement pass.

---

### 46 — CLOSED: both footprint generators asserted a hole-to-hole floor, and both had the wrong number

**Findings 37 and 38 were fixed, and each fix was then caught by A12 for the same
reason: a generator that checks its own geometry against a floor it got wrong is a gate
that reports `ok` while being wrong.** Both `elec/make_f2_footprint.py` and
`elec/make_u1_footprint.py` asserted `HOLE_MIN = 0.25`. The fab publishes **two**
numbers — a generic hole-to-hole and a **pad**-hole-to-hole — and a pad hole needs more
laminate beside it because it carries an annular ring and a mask relief. **A12 grades at
0.45.**

| | drill | pitch | laminate between | A12 |
|---|---|---|---|---|
| U1 thermal vias, 4 across on an even 0.70 pitch | 0.30 | 0.70 | **0.400 mm** | FAIL, 8 places |
| F2, two pads per terminal | 2.10 | 2.50 | **0.400 mm** | would have failed |

**F2's was invisible, and the reason is the lesson.** A12 grades the ROUTED board, and
the routed geometry still named the stock land, so A12 was dutifully measuring 1.40 mm
holes while the generator on disk produced 2.10 mm ones. Only U1 showed up. **A gate
that reads the routed board cannot see a change that has not been routed yet** — which
is fine, as long as nobody reads one clean run as a clean part.

**U1's fix is free; F2's is not.** The via row was never required to be evenly spaced,
so it spread to the widest four positions the EP copper still contains: `±0.42, ±1.18`,
leaving 0.54 and 0.46 mm, with 1.18 + 0.25 of pad = 1.43 against the 1.475 half-width.
F2's pitch is the **part's**, so the DRILL is what had to give, and the two floors push
against each other:

    the pin wants   1.921 diagonal + 0.10 slide + 0.07 plating = 2.091 -> 2.10 drill
    the fab allows  2.50 pitch - 0.45 of laminate              =         2.05 drill

**2.05 it is**, and the slide drops from the 0.10 asked for to **0.059 mm against the
worst-case pin** (0.136 against the nominal 1.40 × 1.20). That still admits the part,
which is the test that matters, and 2.10 is not manufacturable at this pitch at any
price. The alternative — merging each terminal's pad pair into a plated slot, which is
legal because they are one net — changes the land's topology to buy 0.04 mm of slide and
was not taken.

#### ⚠ And then floating point decided the hole size, twice

Capping the drill by the pitch introduced **two** bugs of the same shape, in opposite
directions, and the first one shipped a hole that would not have fitted:

1. `math.floor((2.5 - 0.45) / 0.05)` — the division evaluates to **40.99999999999999**,
   so `floor` returned 40 and the generator quietly produced a **2.00 mm** drill: 1.930
   finished against a 1.921 pin, **nine microns**, which is not a fit. It printed
   `ok` and the assert passed, because the assert was checking the same wrong number.
2. With a `1e-9` guard added, the matching assert then **rejected the very drill the
   line above had just derived as the largest legal one** — `2.5 - 2.05` is
   `0.44999999999999996`, so a bare `>=` against 0.45 fails.

**A geometric floor compared at full double precision is a floor nothing can sit exactly
on.** Both sides carry an explicit tolerance now, each with the failing literal written
into the comment, because the next person to see `0.44999999999999996` should not have to
rediscover why it is there.

#### The gate that did not exist: `tools/check_hole_fit.py`

Finding 37 got all the way to a cart because **nothing in this repo compared a hole to a
pin**. Every geometry check compares the board to ITSELF or to the fab's rules — annular
ring, hole-to-hole, clearance, courtyard — and all of them passed on a land the part
cannot enter, because the pin's size lives in a datasheet and nothing read it.

The new gate walks every footprint the routed board places, reads the plated drills out
of the footprint file, and requires a **declared pin with a source**; an undeclared hole
is a hard failure, because an undeclared hole is not a hole that fits, it is a hole
nobody checked. It runs **its own fail case on every run** — the stock Littelfuse land,
still on disk in KiCad's library — so it cannot quietly become a gate that only ever
says `ok`.

**It had two bugs of its own before it was believed, and both are the kind it exists to
catch.** (1) It took `hypot(w, t)` for every pin, which is right for a stamped blade and
wrong for a round lead: it charged a 1.0 mm round terminal pin 1.414 mm of hole and
failed three terminal blocks and a pin header that have fitted their stock lands for
decades. **Shape is declared now, not assumed.** (2) It filtered on the geom's `tht`
field, which sounds exactly right and is not — `tht` is about modelled leg tails for the
CAD, not about drilled pads — so two parts were invisible to it. Chasing that revealed
C1 and C2 are **SMD** electrolytics with no holes at all, and the pin declaration
written for them was itself a false record. **A gate reading a field that merely sounds
like the one it wants is the same class of defect as the one it was written to catch.**

#### ⚠ And the rename cost F2 its fab placement frame — which caught a REAL one on D7

`fab_frames.json` is keyed on **LCSC code + footprint name**, so renaming the land to
`-PINFIT` orphaned F2's fitted entry and the next package shipped **two** parts as *"not
measured"*. Re-running the fitter is what surfaced the thing that actually mattered:

| part | frame | consequence of getting it wrong |
|---|---|---|
| **D7** BAT54S | **rot 180** — was shipping at 0 | **a diode straight from +3V3 to GND**: a dead short on power-up |
| **F2** holder | **will not fit** | swaps two fuse terminals, i.e. nothing |

**D7 is the catch.** It was added in the same session as the clamp, its CPL line said
`0.000000`, and a BAT54S is wired by its pin map — pin 3 is the series junction, so a
half turn makes the part a short across the rail. **That is exactly the failure the
comment in `elec/main.py` warns about, and it would have shipped.** The frame is
measured now and the CPL carries `180.000000`.

**F2's refusal is a fitter defect, not a land defect, and it is harmless.** Every pad of
the `-PINFIT` land is at the stock coordinate byte for byte — only `size` (2.20 → 2.30)
and `drill` (1.40 → 2.05) changed — yet the stock land fits C207061 and this one is
reported *"up to 2.90 mm from ours"*. **The fitter is pairing pads with pad size as part
of the match.** It is recorded rather than worked around, because the frame table is
generated and hand-editing it is the thing that must not happen.

It does not block the order because **F2 is symmetric where it counts**: a fuse's two
terminals are interchangeable, the 12.8 × 2.5 mm pad grid maps onto itself under a half
turn, the 2.4 mm spigot sits at the grid's exact centre and keys nothing, and a quarter
turn does not fit the holes at all. **The part is hand-soldered into plated holes, so the
board orients it** — the only rotation a fab could get wrong is the one that changes
nothing.


## 22. One part puts the whole board on the dearer assembly tier — $69 of a $194 quote

**Found by uploading `main.zip` to JLCPCB and reading the quote** (2026-10-06, full
line items in [docs/jlcpcb-quote.md](docs/jlcpcb-quote.md)). The board priced at
**$193.64 for 5** — $38.73 each, assembled.

The upload itself validated cleanly and that is worth saying first: 2 layers, 112 x 95
mm, and **34 of 34 BOM rows matched the code we gave**, none guessed by the fab's
matcher. That is the `REQUIRE_CODES` gate paying for itself the day after it was fed.

**U2, the ESP32-WROOM-32E (C701342), is flagged "Standard Only".** JLCPCB will not
place it on Economic assembly, and the form will not let the project advance until
either the part is deselected or the whole board moves to Standard. Standard then
charges, in the quote's own lines:

| | Standard | Economic |
|---|---|---|
| Setup fee | **$25.75** | ~$8.24 (measured on the pedal steel project) |
| Feeders Loading | **$43.40** | *this line does not exist* |
| X-Ray Inspection | **$8.25** | — |
| Components, same BOM | **$88.11** | ~$68 (Standard buys in bigger multiples) |
| Board outline | **105 x 112** (two 5 mm rails added) | 95 x 112 |

**Accepted, not fixed, and measured rather than lumped:** about $69 of the total is
attributable to that one part. The alternative is Economic plus hand-soldering a
25.5 x 18 mm castellated module five times, and assembled boards were the point.
`ORDER.txt` already said "whichever of Economic / Standard lists all the sourced SMT
parts", so the tier was anticipated — what was not anticipated is the size of it.

**The one real saving this surfaced is the opposite of the obvious one.** Feeders cost
about **$1.28 per distinct part number**, so BOM LINES are the cost driver, not parts.
R2's 29k4 is the only Extended passive and looked like an easy win; replacing it with
an all-Basic 51k/15k divider would make the BOM one line LONGER and cost about $1.28
plus a re-route to save $0.00. **Do not do it.** Recorded beside the part in
`elec/fab.py` so it is not re-derived.

**And the via question is closed.** The suspicion was a 0.25 mm via surcharge. The
board's 86 vias are already 0.6 mm on a 0.3 mm drill, and the quote says
`Via Covering $0.00`. Nothing to recover.

## 23 - CLOSED: the depanel option is in ORDER.txt and selected on the quote

**Closed 2026-10-07, and it was the one pre-order item that bricks five assembled
boards, tracked by an entry that read "Open" and said the opposite of the truth.**
`elec/out/fab/main/ORDER.txt` carries it on the `tier:` line -- "TICK 'Depanel boards
& edge rail before delivery' or the boards arrive too wide for the bay" -- and
`docs/jlcpcb-quote.md` records it SELECTED on the 2026-10-07 quote at **$3.31**, a
line item on the order form rather than a prediction. The text below is kept because
its arithmetic is still the reason the option matters.

⚠ AND THE MARGIN IS NOT THE 10 mm THIS ENTRY IMPLIED. The bay cavity is 105.24 mm
in Y, so a 105.0 mm un-depaneled outline leaves **0.24 mm** of total slack against the
**2.00 mm** the board must slide to clear the retention lip -- and it fouls the +Y wall
by 3.00 mm on the way in. It does not present as an obvious 10 mm miss; it presents as
a board that will not go in, or will not stay in.

**Was open, and it is an order-form action rather than a design change.** Standard PCBA
pads the outline to **105 x 112 mm by adding two 5 mm rails on the 95 mm sides** — the
form states this itself. The housing bay is cut for a 95 mm board.

**"Depanel boards & edge rail before delivery" is under Advanced Options.** If it is
missed, five boards arrive 10 mm wider than the bay they were designed into -- see the
0.24 mm note above for how little of that it takes -- and trimming a rail off a finished
assembled board by hand is how an edge trace gets cut.

## 24. CLOSED — the frames are measured: 17 placements corrected, 0 unfitted

*(Raised as "every orientation-critical part is unmeasured, and a render is the
only evidence". It was, and the render was mine, and it was wrong — see below.)*

**MEASURED 2026-10-06 — and twelve of them were wrong.** `fab_frames.derive` now
runs, and what it found would have ruined the assembly:

| part | was | corrected to |
|---|---|---|
| **J4** (5-way field terminal) | — | origin **+10.16 mm** |
| **J5** (4-way, level sensor) | — | origin **+7.62 mm** |
| **J6** (programming header) | 90° | **0°**, origin +6.35 mm |
| **U2** (ESP32-WROOM-32E) | 270° | **180°**, origin +3.68 mm |
| **U1** (LMR14020 buck) | 0° | **270°** |
| **U3, U4** (UCC27517 gate drivers) | 0° | **180°** |
| **Q3** (MMBT3904) | 0° | **180°** |
| J1, J2, J3 (2-way terminals) | — | origin +2.54 mm each |
| BZ1 (buzzer) | — | origin +3.80 mm |

**13 placements changed, of 70.** (This said "13 of 59". 59 was never this board's
total; it is 70 now, after the level inverter, two output capacitors and the IO0
strap.) The origin shifts are arithmetic, not noise, and
they are the exact failure the module's docstring predicts: KiCad puts a connector's
origin on **pin 1** and the fab's library puts it at the **row centre**. J4's 10.16 =
(5−1)×5.08/2; J5's 7.62 = (4−1)×5.08/2; J6's 6.35 = (6−1)×2.54/2. J4 was two whole
pitches off its own pads.

**⚠ AND THE RENDER-READ THAT SAID OTHERWISE WAS MINE, AND IT WAS WRONG.** Finding 24
was first written saying the JLCPCB 3D preview had been looked at and "nothing was
visibly wrong". The preview was rendered from the UNCORRECTED placement file, so
twelve parts were not on their pads when I said they were. A 90° ESP32 and a
10 mm terminal offset were on the screen and I read past them. That is the whole
case for M2's rule in `cadkit/PCB_QUALITY.md`, now proven on this board rather than
quoted: **a person looking at a render is not a measurement.**

**What it took to get the number, which is its own finding.** The endpoint cadkit
shipped — `easyeda.com/api/products/<code>/components` — has been 403 at CloudFront's
edge for everyone, and `derive` handled that by logging each failure and then saving
an EMPTY table, which reads as "nothing needed measuring". Fixed in canonical cadkit
(`ec2c852`) against `pro.easyeda.com`, propagated to all 11 consumers. The report's
own instruction was also wrong: it said to run `fab.py --frames`, a flag no project
implements.

**THE LAST FIVE ARE CLOSED TOO — 17 corrected, 0 not fitted.** Each refusal had a
different cause and not one of them was an orientation problem. The fit matches pads
by NUMBER and refuses on a large residual, which is right — fitting disagreeing
numbering turns the part to suit the numbers — but a machine places a BODY, so each
was re-fitted on pad POSITION at the four rotations.

| part | cause of the refusal | correction | residual |
|---|---|---|---|
| **Q1, Q2** TO-252 | our land has a **middle lead pad** (numbered 2, the drain, same net as the tab); the fab's footprint has none — it merges that lead into the tab, so matching it charged 2.43 mm for a pad that is missing nothing | **90°**, −1.74 mm | 0.31 mm leads, 0.62 tab — **all along x, 0 across**: 14 % of a 2.20 mm lead's *length* |
| **D2, D3** TO-263 | none — the numbering already agreed at 180°. The residual is **land design**: the fab draws the tab 1.44 mm further from the leads than we do | **180°**, −2.84 mm | 0.48 mm leads, 0.96 tab — all along x: 10 % of a 4.60 mm lead, 10 % of a 9.40 mm tab, 0 % across |
| **F2** fuse holder | our eight holes carry **two** numbers (one per terminal, four holes each) and the fab numbers them 1–8, so fewer than two numbers are shared | **180°**, +6.40 / −1.27 mm | **0.016 mm** on seven of eight, 0.111 on the last |

**⚠ F2 IS WHERE M2 BIT, AND IT WAS DECIDED RATHER THAN ASSUMED.** A half turn on a
symmetric 2 × 4 hole grid is ambiguous *from the holes alone* — both rotations fit to
0.016 mm, so the pad cloud cannot tell you which is right. It was settled on the one
feature that is not symmetric: our **2.4 mm non-plated spigot sits at x +6.400, which
is the hole grid's own centre** (the grid spans 0.0–12.8), so a half turn maps it onto
itself. The rotation cannot be wrong, and a fuse conducts either way, so the two
terminals need no handedness either. That spigot is the same feature the pour geometry
in M37 was built around.

All three are written into `elec/fab_frames.json` as **hand-entered** frames carrying
their reasoning, and `ROTATION-CHECK.txt` marks each `[hand-entered frame]` so nobody
later mistakes a judgement for a measurement.

**M2 IS CLOSED ON THE POLARISED PARTS TOO — and it did NOT need the previewer.**
I had written that it did: *"a look at the order page, not a measurement this repo can
make."* That was wrong, and wrong in the direction that matters, because a two-pad
polarised part is the one case where nothing else can save you. The pad cloud is
mirror-symmetric, so unlike Q1/D2/F2 above it cannot be re-fitted on POSITION either —
and C1 and C2 are 100 µF electrolytics across an 18 V battery, which vent if they go in
backwards.

What I had missed is that the fab's footprint carries **more than pads**. The same
`dataStr` that `fab_frames` reads for pad positions also holds silkscreen (layer 3),
document (13) and **COMPONENT_MARKING (layer 49)** geometry, and layer 49 holds a single
point: **the fab's own pin-1 dot**. That is the fab stating which land is pin 1, in the
fab's own data. Reading it is a measurement.

`elec/fab_polarity.py` reads it for all six, twice over, and requires the two readings
to agree:

| | our pad 1 | why it must be (from the NETS, not a pin name) | R1 pin-1 dot | R2 silk ink |
|---|---|---|---|---|
| **C1, C2** `C371283` | **+** | pad 1 on VBAT, pad 2 on GND | their pad 1, **2.1×** | their pad 1, 9 % |
| **D1** `C310039` | **K** | SMCJ24A unidirectional TVS clamping VBAT to GND: pad 1 is on VBAT, so pad 1 is the cathode or the TVS is a short | their pad 1, **2.8×** | their pad 1, 16 % |
| **D4** `C81598` | **K** | buzzer flyback: pad 1 on +3V3, pad 2 on the drive node | their pad 1, **4.6×** | their pad 1, 72 % |
| **D5** `C2103` | **K** | zener clamping VGATE: pad 1 on VGATE, pad 2 on GND | their pad 1, **4.0×** | their pad 1, 86 % |
| **D6** `C7428237` | **K** | buck catch diode: pad 1 on SW — the cathode goes to the switch node | their pad 1, **3.2×** | their pad 1, 3 % |

All six agree: **the fab's pin 1 is our pad 1**, so the rot-0 frames were right and the
numbering means the same thing on both sides. Ours is asserted from the **nets**, not
from a pin name — `GetPinFunction()` is empty on a board built from a netlist, and a net
is the better witness anyway: it says what the terminal has to be for the circuit to
work at all.

**R2's weakness, named and measured rather than hidden:** the silk-ink reading is
decisive on D4 (72 %) and D5 (86 %), but only **3 % on D6** and 9 % on the capacitors,
because a cathode band is a single line and the document layer puts a "+" at the *other*
end. So R2 is **not** allowed to confirm anything on its own — the gate turns on R1,
which is 2.1× or better everywhere, and R2's only power is to **veto**: if it
contradicts R1, that part fails and needs a person.

**The gate has been made to fail — six ways, on the real fetched data**, each corrupting
one thing and each caught: the fab numbering the other land pin 1; the dot sitting
between the pads (not decisive); layer 49 carrying no dot; layer 49 carrying two; the
silk contradicting the dot; and the fab's pad numbers not matching ours. Uncorrupted,
it still passes — otherwise the harness proves nothing.

`fab_polarity.py` is project-local for now. It is generic enough to belong in canonical
`cadkit/pcbflow` beside `fab_frames`, and that is worth doing, but upstreaming it means
propagating to eleven consumers and is its own job.

### 47 — CLOSED: the overfill alarm's polarity was ungated, and the gate's own docstring was the stale source

Found while correcting two sign-off entries (M20, M35) that both described **a
protection mechanism this board does not have**. Three separate defects, all pointing
at the same sentence.

**1. `tools/check_level_alarm.py` validated the alarm with the flag as an INPUT.** Its
eight properties all start from `HIT = full_low`, so the suite passes with
`LEVEL_FULL_IS_LOW` set *either way* — and that flag is the whole question of whether
the buzzer sounds on a full tank or an empty one. It was **wrong in this repo** until
the inverter went on the board, and nothing said so. A gate that takes the answer as a
parameter is not checking it.

**2. The claim it rested on, measured.** `check_pin_map.py`'s docstring said: *"the
firmware sets INPUT_PULLUP and the board also fits R23 to 3V3 ... parallel pull-ups ...
the external one is what keeps the open-collector sensor's 18 V rail off the pin."*
Every clause is false of this board:

| the claim | measured |
|---|---|
| firmware sets `INPUT_PULLUP` on IO14 | `pinMode(LEVEL_PIN, INPUT)` — `firmware/src/pins.cpp:170` |
| "parallel pull-ups" | there is no internal pull, so there is no pair |
| R23 is 10k | R23 is **100k** |
| R23 pulls up LEVEL | R23 is the **+3V3 end** of a series string and is not on LEVEL: `+3V3 → R23 → LEVEL_PU1 → R27 → LEVEL_PU2 → R28 → LEVEL` = **300k** |
| the pull-up keeps the pack off the pin | **no pull-up can.** The XKC-Y25 drives its HIGH to InVCC and would win. **Q4 and R29** cap the pin; the 300k only sources the 11 µA Q4's collector sinks |

That docstring was cited by M20 and M35 **as their authority**, which is the worst
version of this defect: a gate whose documentation lies about what it gates, loaned out
to two sign-off entries as evidence.

**3. `elec/CIRCUIT.md`'s whole tank-level entry still drew the pre-respin circuit** —
an inverter **spliced into the sensor lead**, the black MODE wire moved to **VBAT**, and
the way marked MODE **left empty**. After the respin that is precisely the wiring that
**inverts the overfill alarm**, printed as the build instruction, on a board whose
terminal is silkscreened MODE. Rewritten to the built thing: four wires, four ways,
straight across, MODE on GND, `LEVEL_FULL_IS_LOW = false`, and the old table kept
visible as the trap it was.

**THE FIX IS A GATE, NOT A NOTE.** Check 9 of `check_level_alarm.py` **derives** the
expected flag from `elec/out/main.net`:

* J5's **MODE way** picks the sensor's output sense — on GND it is normally closed, so
  no liquid → sensor HIGH;
* each **grounded-emitter stage** between J5's OUT way and the module pin flips that
  sense again (the walk refuses to travel through GND or a rail, so R30's hold-off and
  the 300k string's far end are dead ends, not paths);
* the result is compared with the firmware.

It retypes nothing: way labels come out of `elec/main.py`'s own `gen.part()` call, the
module pin out of `check_pin_map.py`'s WROOM-32E table, and `LEVEL_PIN` out of
`pins.h`. Measured on the board as built: *J5 way 3 (OUT) → U2 pin 13 (IO14), 1
inverting stage; MODE on GND; no liquid → pin LOW, so FULL is HIGH* → `false`, which is
what the firmware says.

**Made to fail five ways, each caught, each a pass before:** the firmware flag flipped;
MODE moved to VBAT (the old build note's wiring — derives `true`); Q4 deleted (0 stages
— derives `true`); Q4's emitter lifted off GND; and J5's MODE label renamed. The last
two return **`None`**, printed as `?` and **counted as a failure** — a check that cannot
read the board has not passed it. One round of the harness itself had to be thrown
away: it edited the netlist with literal strings that did not match its whitespace, so
two of the five tests were doctored by accident and one reported a pass it had not
earned. A harness that silently does nothing proves the gate works.

**One real defect in the derivation, found by that harness:** a transistor sits on both
the net the walk arrives on and the net it leaves by, so Q4 was counted **twice** and
the two inversions cancelled — giving `FULL IS LOW`, a *wrong* answer rather than a
missing one. Stages are now counted once per reference.

### 48 — CLOSED: finding 5 raised VBAT_MAX and nothing fired, because the figure that mattered most was prose

Finding 5 corrected `VBAT_MAX` from 20.0 to 21.0 — a Makita "18 V" pack is 5S, so it
is 5 × 4.2 = **21 V off the charger**. The constant changed, every gate stayed green,
and **twenty sites went on saying 20 V**, including one that was not decoration.

**The one that mattered.** M16 signs the board against hot-plug ringing: a cable-fed
supply rings to about twice the source voltage, and VBAT *is* cable-fed because the
pack docks live at the Makita holder. The entry read *"2 × 20 V = 40 V against ... U1's
44 V VIN ... leaves 4 V — it passes, but on the RECOMMENDED maximum of 40 V it passes
by nothing at all."* At 21 V:

| | written | measured at VBAT_MAX = 21.0 |
|---|---|---|
| ring | 40.0 V | **42.0 V** |
| margin on U1's 44 V absolute max | 4.0 V | **2.0 V** — halved |
| against the 40 V *recommended* max | "passes by nothing at all" | **exceeds it by 2.0 V** |

So the figure did not just drift, it **changed standing**: the ring is now outside the
part's recommended operating range rather than exactly at its edge. The board is still
sound, and for a reason that was already written down — the SMCJ24A clamps at 38.9 V,
*below* the ring, with C1/C2's electrolytic ESR damping the LC underneath — but the
sign-off was quoting a margin that no longer existed.

**Why nothing fired: the ring was prose.** `BUCK_VIN_ABSMAX = 44.0` and
`BUCK_VIN_RECMAX = 40.0` were both real constants with asserts on `TVS_CLAMP`, but
*2 × VBAT_MAX* was a sentence in a sign-off entry. **A figure that no gate reads stops
being true.** It is now derived in `elec/main.py`:

```python
BUCK_VIN_RING = 2.0 * VBAT_MAX   # V, undamped hot-plug ring on a cable-fed input
assert BUCK_VIN_RING < BUCK_VIN_ABSMAX
assert TVS_CLAMP < BUCK_VIN_RING   # a clamp ABOVE the ring never conducts
```

The second assert is the less obvious one and is the one that catches a lazy fix: drop
`VBAT_MAX` far enough and the TVS stops clamping on a plug event at all, which would
leave M16's damping argument *empty* while every number in it still looked fine.
**Both were made to fail:** lowering `BUCK_VIN_ABSMAX` to 41.0 gives *"a 42.0 V
hot-plug ring on a 21.0 V pack exceeds U1's 41.0 V VIN absolute maximum"*, and
`VBAT_MAX = 19.0` gives *"the TVS clamps at 38.9 V but the ring only reaches 38.0 V,
so it never conducts"*. Raising `VBAT_MAX` to 22.5 to test the first one is
**pre-empted by an upstream assert on R9's dissipation** (104 mW in an 0805 at 83 % of
rating), which is worth knowing: the rail already has a guard above it.

**The other nineteen, recomputed rather than find-and-replaced.** Several carried
*derived* numbers, so swapping 20 for 21 would have left the arithmetic wrong in a new
way:

| | was | now |
|---|---|---|
| `FREEWHEEL_DUTY` comment | 0.40, conducts 40 % | **0.43, conducts 42.9 %** |
| buck inductor ripple | 0.55 A | **0.56 A** |
| peak at the 0.6 A load | 0.876 A | **0.878 A** |
| C1/C2 50 V derating ratio | 2.5× | **2.38×** |
| the 1k5 dropper's current | 6.7 mA | **7.3 mA** |
| `VBAT_PIN`'s divider output (`pins.cpp`) | 1.82 V | **1.91 V** (100k/10k, VBAT/11 — still clear of the 11 dB span, so the attenuation choice stands) |

Plus plain-prose sites in `CIRCUIT.md`, `DESIGN_V2.md`, `fab.py`, `main.cpp` and the
J1 terminal's own description, and the firmware comment that **quotes** CIRCUIT.md §1
verbatim — which had to move with it, or the quotation marks would be lying.

Two sites deliberately still say 20 V: the `elec/main.py` comment and the M16 sentence
that **quote the retired text** in order to name what was wrong.

Board after the sweep: **0 unconnected, 0 violations, 0 FAIL, 0 OPEN**, 70 placements,
all gates pass, build #516.

### 49 — OPEN (copper): an unlanded or severed joystick lead can start a pump, and nothing holds JOY_RAW

> **UPDATE 2026-10-08 — STILL OPEN, AND STILL COPPER. The free half is taken.** The
> firmware already tested the measured centre against a 1200–2900 band and printed
> *"WARNING: centre is implausible"* — and then armed on the next `a` anyway, which is a
> warning scrolling past a console nobody is reading by the time the stick is touched.
> It now **REFUSES** to arm on a centre it has already called implausible, says the
> measured value and the remedy (land J4, let go, `c`, then `a`), and reports
> `DISARMED/NO-CENTRE` on the status line so "why did `a` do nothing" has an answer.
>
> **And the same refusal is on the BOOT path, which is the case that actually happens.**
> The stored armed flag is read straight out of `prefs` rather than through `setArmed()`,
> so a board the owner armed last session came up ARMED without ever passing the guard
> — and this finding's field failure is precisely that board with a lead off: boots
> armed, calibrates against a float, first drift is a pump. It is disarmed on boot now,
> with the reason printed.
>
> **This does not close the finding and must not be read as closing it.** The band is a
> plausibility test, not a presence test: a floating node can settle inside 1200–2900 and
> the guard then passes a calibration that is still wrong. Only the two 100k biasing
> `JOY_RAW` to mid-rail make an unlanded lead read CENTRE rather than drift. That is the
> fix, it is copper, and it is deliberately not in this revision.

Found in the first-contact pass, which asked what happens with no joystick connected.

**Measured on the netlist:** `JOY_RAW` is **`J4.3` and `R22.1`, and nothing else.** No
pull-up, no pull-down, no bias. J4's other live candidates are not available either —
ways 2, 4 and 5 (GND, VRX, SW) are all tied to GND on the board, so there is no second
axis and no switch to use as presence detection.

**The failure, step by step.** With the lead off, the node behind R22/C12 floats at an
ADC input. `measureCentre()` takes a 129-sample median *of the float* and adopts it as
centre. Leakage and temperature then move a floating 100 nF node by far more than
`DEADBAND_ON`, which is **300 counts of 4095 ≈ 0.24 V**, and 6 of 10 samples over that
threshold is an engage vote. So: **a pump starts with no hand anywhere near the stick.**

**It is not only a bench condition.** A severed or pulled-off joystick lead does exactly
the same thing, and [finding 27](#27) says that lead is one of **three** that land on a
screw clamp with no strain relief, on a machine carried on someone's back. The bench case
is the one that bites first; the field case is the one that matters.

**Why a simple pull is the wrong fix, which is the interesting part.** The obvious
remedy — 100 k to GND — pins an unlanded `JOY_RAW` to **0 V**, and 0 V is not "no
command", it is **full deflection one way**. A pull-up to 3V3 is full deflection the
other way. Either one converts an undefined input into a confident wrong one, which is
worse than the float.

**The fix is a mid-rail bias:** two resistors from 3V3 and GND to `JOY_RAW`, so an
unlanded stick reads **centre** and commands nothing. At 100 k each — **a value already
on this board, so no new BOM line and no new feeder fee** — the Thévenin source is
50 k against the KY-023's ≈ 10 k pot, which pulls a real reading toward mid-rail by
roughly 5 % of its offset from centre: well inside a deadband that is calibrated at boot
anyway. Cost: two 0603 placements and a short route into an existing analog node.

**DELIBERATELY NOT DONE, and said rather than smuggled.** The board is being ordered and
this is copper: two parts, two placements, a route into the quietest net on the board
(M21 — C12 sits 3.117 mm from U2.6 on purpose, and the ADC's quiet reference is a signed
item). It wants its own pass with the overlap gate, A2, A16 and M21 re-read, not a
last-minute insertion.

**What was done instead, at zero copper:** a board with **no stored preference now boots
DISARMED** (`prefs.getBool("armed", false)`, was `true`). `setArmed()` writes that key,
so it is a **first-boot default only** — arming once sticks across reboots and across an
OTA reflash, and nothing about normal use changes. A factory-fresh board therefore will
not drive a pump until someone sends `a`, which removes the bench case entirely and
leaves the field case (a lead pulled off a board that has been armed) open and named.

**Bring-up stages around it**: `BRINGUP.md` lands the joystick at stage 4 and confirms
both directions **while still disarmed**, and does not fit F2's blade or land a pump
until stage 5. The staging is not advisory — it is what makes this finding harmless on
the bench.

### 50 — CLOSED: the bring-up procedure shipped with two steps that cannot be performed in the state they specify

`BRINGUP.md` was written in one pass and pushed. Walking it back against the netlist and
the firmware's control flow — rather than re-reading the prose — found **two steps that
ask for readings the board does not produce**, both introduced by the pass that wrote it.
That is the defect a procedure exists to prevent, so both are recorded in the file
itself rather than quietly corrected.

**Stage 2: measurements with the fuse out.** The step said to leave F2's blade **out**
and then asked for 3V3, VGATE and both gate voltages. Measured on the netlist, `VBAT` is
the **far side of F2** and carries `U1.2`/`U1.3` (VIN and EN), `R9.1` (the VGATE
dropper), `TP2` and both pump terminals; `VBAT_RAW` is only `J1.1`, `F2.1`, `C21.1`. With
the blade out **the whole board is dead** and TP2 reads 0 V. F2 is the pack's isolator
and nothing finer: out for stages 0–1, in at stage 2. What makes stage 2 safe is that
nothing which can move is landed and the firmware boots disarmed — not the fuse. The pack
is now read at **J1's own screw** with the blade out and at **TP2** with it in, which
also turns a bad fuse or holder into a visible difference between two readings.

**Stage 4: a direction field that is never computed.** The step said to confirm both
directions "while still disarmed" by watching `s` report `dir=A` and `dir=B`. It never
will: the direction vote sits inside `if (armed && !otaActive)` in `loop()`, so a
disarmed board leaves `runDir` at `DIR_NONE` and `s` prints `dir=none` however hard the
stick is pushed. **An operator following that step concludes the joystick is broken.**
What *is* live while disarmed is the raw reading — `readVbat()` and `readLevel()` are
called at the top of `loop()`, outside the armed branch, and the periodic telemetry line
prints `raw= filt= offset=` with a `[DISARMED]` marker. Stage 4 now judges the stick by
**`rawoff=`** against ±300 (`DEADBAND_ON`, the same threshold the vote uses once armed),
and says explicitly that `dir=none` here is by design.

**One firmware change came out of it, at zero copper.** `s` printed `centre=` and
`duty=` but **not the live reading**, so the one command you reach for when a board
boots and does nothing could not show the joystick at all. The last reading is now kept
at file scope and `s` reports `joy raw= filt= rawoff= off=`, and appends
`(none: disarmed, judge by rawoff)` to the direction field when the motor is inhibited,
so the console explains itself without the operator holding this file. Builds clean,
+196 bytes of flash (78.3 % of the app slot, unchanged to one decimal).

**Stages 3, 5 and 6 were walked the same way and are correct.** Stage 3's three level
states hold, including unplugged-reads-FULL, because `readLevel()` is outside the armed
branch; stage 5's off-latency of ~15 ms is `VOTE_K_OFF × 5`; stage 6's `rssi=`/`ip=`
come from the same `s`.

**The method is the reusable part**, and it is the same one that caught the stale pour
areas and the prose ring voltage: do not re-read the document, re-derive each claim from
the file that owns it. For a procedure that means asking, of every step, *is the board in
a state where this reading exists?* Two of six stages failed that question.

### 51 — CLOSED (does not gate the order): the five `track_dangling` warnings, measured instead of carried

These five have been reported as "known `unwick` tails" for several passes without
anybody saying where they are or what they touch. Before ordering copper, measured.

**What they are.** Five tracks on **GND, F.Cu**, of 0.8500, 0.8500, 0.9494, 0.9502 and
0.9502 mm, each with one end unconnected. They are the residue of
`cadkit/pcbflow/unwick.py` retiring a via and not trimming the stub that fed it — the
defect is in the tool, not in this board's design.

**Where they are.** All five sit in the cluster around **x 137–141, y 73–78**, which is
inside U2's footprint, in the thermal-pad stitching region (U2's exposed pad is 21 pad
objects, per M25/M29).

**Why that is the question worth asking.** A short ground stub is inert almost anywhere
— but copper under a PCB antenna detunes it even when the copper is ground and properly
connected, so "it is only GND" would not have settled it. Checked properly:

* **There are NO copper rule areas on this board at all** — zero zones with
  `GetIsRuleArea()`. The antenna's relief is the **board outline**, which is why
  [finding 39](#39) cut the board back instead of drawing a keepout.
* That relief is the **4.6 × 4.6 mm cutout at x 140.70–145.30, y 47.70–52.30** (15.9 mm²,
  which `finish.py` re-checks every run and reports as `1 cutout(s) match`).
* The stubs are at **y 73–78**, about **21 mm** from that cutout. Not in it, not near it.

**Verdict: order the board.** Five sub-millimetre tails on the ground net, one end
connected to the plane, 21 mm from the only relief on the board and inside a region that
is already dense ground stitching. At 2.4 GHz a 0.95 mm stub is under a hundredth of a
wavelength; on a net that is a plane it is not a stub in any meaningful sense. They cost
nothing, they shade nothing, and they are warnings rather than violations — `finish.py`
still reports **0 violations**.

**The fix belongs upstream, not here.** `unwick` should trim the feeding segment when it
retires a via, which is a change to canonical `cadkit` and therefore a change to eleven
consumers. Doing it now would re-route this board for a cosmetic gain on the day it is
being ordered, so it is deliberately left. What has changed is that the five are no
longer carried as an unexamined line in a status summary: the number, the net, the layer,
the lengths and the distance to the only thing that could have made them matter are all
written down, so the next person does not have to re-derive them to decide the same way.

### 52 — CLOSED: the board is lettered in Rennie Mackintosh PSG, and the face made the two pump terminals identical before it was fixed

Owner's request, 2026-10-08: letter the silkscreen in the same face the
public-steel-guitar boards use, set up the same way. The `.otf` was supplied from that
project's `elec/fonts/` and installed per-user.

**The plumbing is a project-local `elec/silk.py`**, which `finish.py` picks up
automatically because a project's own `silk.py` beats the shared `cadkit/kicad_silk.py`
(see its `_step`). The licensed font is **not** in this repository and must not be; it
has to be installed for a build to produce the boards as ordered, and `fallback: true`
means a clone without it still finishes — in KiCad's stroke font, **saying so loudly**.

**1.5 mm is measured here, not inherited.** The glyph ink was rendered through pcbnew's
`TransformTextToPolySet` and measured directly, because `GetBoundingBox()` on a text
object returns the text BOX and reports the cap height and the thinnest bar as the same
number — which measures nothing:

| size | cap height | thinnest ink (the bar of `_`) | |
|---|---|---|---|
| 1.4 | 1.308 mm | **0.1431 mm** | **fails** JLCPCB's 0.15 mm floor |
| 1.5 | 1.401 mm | **0.1533 mm** | clears it, by 0.0033 mm |

So 1.5 is the **smallest size this face can be lettered at**, with no smaller fallback.
`_` is the thinnest glyph and this board's labels are full of it; the next thinnest is
`I` at 0.1701 mm. That this lands on the steel guitar's own 0.153 mm is corroboration,
not the source.

**⚠ AND AT 1.5 mm THE FULL NET NAMES STOP FITTING, WHICH MADE J2 AND J3 IDENTICAL.**
`kicad_silk` letters a way with its full net name where that fits and a short word where
it does not, and `_short()` derives that word from **the tail after the last
underscore**. `PUMP_A_LO` and `PUMP_B_LO` both end in `_LO`, so:

| | before the fix | after |
|---|---|---|
| J2 (pump A) | `1 VBAT` / **`2 LO`** | `1 VBAT` / **`2 PA`** |
| J3 (pump B) | `1 VBAT` / **`2 LO`** | `1 VBAT` / **`2 PB`** |
| every GND way | `G` | `GND` |
| J1 | `1 RAW` / `2 G` | `1 RAW` / `2 GND` |
| J5 | `1 LVL` / `2 G` | `1 LVL` / `2 GND` |

**The two terminals a person must tell apart printed the same two words**, on a machine
that pumps liquid, and M26/M1's whole argument is that the wiring is readable off the
silk. Not a legibility complaint — an actively misleading drawing. Fixed by declaring
`silk_short` in `BOARD_NOTES` (the notes are consulted *before* the derivation), with a
word per way that is distinct from every other and says what the way is. `SENSE_RAW`
became `OUT` while there, because J5's way is **labelled** OUT and the net name is
incidental to whoever is holding the screwdriver.

**The face IMPROVED connector labelling, which was not the expectation.** A17 before: two
connectors with their pinout on the other face only (J1 and J6). After: **five of six
have a word at every way on their own side**, and only J6 remains back-only. Shorter
words need less room than the long names did even at the bigger size — which is also why
**J1's `back_only` declaration had to be deleted**, A17 failing hard on it as stale. That
deletion is **face-dependent and says so at the site**: revert the face, the long names
return, J1's front runs out of room, and the declaration must come back. An earlier pass
in this project got this wrong in the other direction by emptying `connector_labels` to
clear a declaration that was only transiently stale.

**Made to fail four ways** — a declaration is worth what its guards have been seen to do:

1. family not installed, `fallback` on → letters in the stroke font and prints the
   warning, `FACE_MISSING` set;
2. family not installed, `fallback` off → refuses, rather than letting KiCad substitute
   a face silently;
3. `glyphs` not declared → refuses (this is a display face: ITC drew `+` as a TH
   ligature, and `+5V` has plotted as `TH5V` on real boards with every check passing);
4. `widths` told to expect the **un-redrawn ITC** ratio of 1.42 → fires, reporting the
   installed file at 0.97. That is positive evidence the installed file is the redrawn
   PSG one, not merely a family-name match.

The first harness for this proved nothing and was thrown away: it called a `_face`
function that does not exist (the real one is `_set_face`), so all four tests reported
"accepted" vacuously. Second time this session a harness has had to be rewritten for
not actually exercising the thing it tested.

**State:** all **139** silk texts in Rennie Mackintosh PSG at 1.5 mm, no stroke-font
fallback; A18 reports **0 clipped of 345** silk objects; A19 confirms all 139 use only
the 48 characters verified as drawn in this file. `silk_overlap` went 1 → 3, and the two
new ones are each a designator over **its own part's** outline (R26 on R26, C14 on C14)
— the mildest kind, since both objects print and the label is unambiguously on the right
part. 0 unconnected, 0 violations, 0 FAIL, 0 OPEN; build #521.

**Residual, named:** the distinctness of the short words is a design choice that **no
gate checks**. Add a third net ending in `_LO`, or a second starting `VBAT_`, and the
collision comes back silently. The words are declared in one place with the reason, which
is the cheapest available mitigation, not a guarantee.

### 53 — CLOSED: four files called R23 a 10k pull-up on a net it is not on, and the bench test expected the pin backwards

Found 2026-10-08 while looking for last-minute changes before the boards are ordered.
Nothing here moves copper; the board is bit-for-bit the same. Every defect is a figure
or a sentence, and the costly one is the last.

**`tools/check_part_values.py` is new, and `main.cpp` had asked for it by name.** At
`RDIV_BOT_K`: *"THIS CONSTANT IS A COPY OF A BOARD VALUE AND NOTHING COMPARES THEM …
no gate in the repo covers this line."* It now checks three kinds of claim, all derived
from `elec/out/main.net`:

1. **firmware constants that copy board facts** — `RDIV_TOP_K`/`RDIV_BOT_K` against
   R20/R21, and the VBAT plausibility window against `elec/main.py`'s `VBAT_MIN`/`MAX`;
2. **every component value claimed in prose** in the firmware and the live documents;
3. **the duty cap `BRINGUP.md` tells an operator to expect**, recomputed from `PWM_MAX`
   (derived from `PWM_RES` in `pins.h`), `PUMP_V_NOM` and the pack range;
4. **the pack range `CIRCUIT.md` publishes** in its rail table, against `VBAT_MIN`/`VBAT_MAX`;
5. **a slash pair must share a net** — `R26/C19` is not a filter if the two parts touch
   nothing in common.

**And `CIRCUIT.md` had kept the old pack ceiling, one line under the new one.** It opens
*"**21 V fresh** (5S × 4.2 V off the charger)"* and then said *"That 20 V ceiling is the
number that drives part selection … parts rated 24 V max sit **4 V** from the top of a
fresh pack"*. The real margin is **3 V** — the sentence was advertising one a third
larger than the board has, in the document that says of itself that this number drives
part selection. Punchlist 48's sweep moved `elec/main.py` and the sign-off and stopped
there. Eight passages re-taken at 21.0 V: the rail table (15–20 → 15–21), the FET
margin (20 → 19 V), the rejected-parts note, the buck's ripple (0.55 → **0.5563 A**,
which `elec/main.py` derives), the catch diode's floor (1.25 × 20 = 25 → **26.25 V**),
the ADC divider's scale and the TVS standoff. The rail table is the one line a regex can
hold, so it is check 4 now — **and so is the sentence itself**: *"a fresh Makita pack is
20 V and inductive spikes exceed that, so 24 V-max parts are rejected"* appeared in
`CIRCUIT.md`, `DESIGN_V2.md` **and** `bom_consolidated.md`, and the BOM's level-sensor
line sized a 5–24 V part against *"the pack's 18–20 V"*. The conclusion survives at 21 V;
the margin each was advertising did not. Three prose claims checked against `VBAT_MAX`
every run now.

**The cap figures are new in `BRINGUP.md` and that is the point of them.** `cap=` is the
only thing standing between a 21 V pack and a 12 V pump, and stage 2 — pack docked, no
pump wired — was the last stage at which it could be checked for free. It wasn't being
checked at all: the first thing that would have demonstrated the cap was a motor turning.
Stage 2 now says to work it out from the meter (`cap = 255 × 12 ÷ pack`: **146** at
21.0 V, 170 at 18.0, 204 at 15.0), and names the two readings that mean the sense path
has *failed* rather than drifted — a trailing `?` on `pack=` with `SENSE IMPLAUSIBLE`,
and `cap=255` above 12 V. Three constants in two files produce those numbers, so a gate
recomputes them rather than trusting the table, and it fails if the row stops naming the
figure at `VBAT_MAX` — the end of the range the meter is actually on.

| what it found | was | is |
|---|---|---|
| `VBAT_ASSUMED` | 20.0 V — **below** `VBAT_MAX` | 21.0 V |
| `VBAT_PLAUS_HI`'s stated reason | "the divider saturates at 21.6" (the **18k** divider) | *> `VBAT_MAX`, with 1 V to spare* |
| R23, in four files | "a 10k pull-up to 3V3" | **100k, and not on LEVEL** |
| the level filter cap | C19 (22 µF, on 3V3) | **C22** (100n, 16 Hz corner) |
| the `b` bench test | "dry pin=HIGH" | **dry pin=LOW** |
| "a dead sensor stops the pump" | twice | **the buzzer sounds; nothing is interlocked** |

**`VBAT_ASSUMED` is the one with teeth.** It is the assumption used when the sense path
reads implausibly, and it sets the duty cap: `cap = PWM_MAX × 12 / v`, so assuming
**less** than the real pack **raises** the cap. At 20.0 the cap was 153 and a real 21 V
pack would have seen **12.60 V across a 12 V pump** — a 5 % overdrive in exactly the
fault case the cap exists for. The sweep that took `VBAT_MAX` to 21.0 (finding 48) moved
the board and left this behind.

**⚠ And the bench test expected the pin backwards.** The comment beside the `b` command
said *"DRY must read HIGH and WET must read LOW … Expected here: dry pin=HIGH"* — four
lines under the chain that gives the other answer. `BRINGUP.md`'s table is right, check 9
derives it right, `LEVEL_FULL_IS_LOW = false` says it, and ten lines below sat the
warning **not** to flip the constant but to go and look at the MODE wire, then Q4/R29/R30,
then the 300k string. An operator following it would have seen the correct reading,
believed the board was miswired, and started taking apart hardware that was working.

**Check 10 of `check_level_alarm.py`** now reads the polarity back out of the prose —
`pin=LOW -> not full`, `dry … pin=`, `LOW means liquid` — across the firmware,
`BRINGUP.md`, `CIRCUIT.md`, the sign-off and the BOM, and compares each with check 9's
derivation. 7 claims read today; **zero claims read is a FAIL**, because a check whose
patterns have stopped matching has quietly become decoration. ⚠ **Its first version
passed vacuously**: in a `.py` file the whole line is inside a string literal, so a plain
double quote marks the *source*, and `quality_signoff.py` excused every claim it made —
including the inverted one. Only the typographic pair counts in Python sources now.
That is the third harness this session that had to be rewritten for agreeing with itself.

**Both were made to fail** against copied trees, so the gate runs unmodified and cannot be
weakened to make a test pass: 15 cases and 7 cases respectively, including the R21 stale
copy, a value changed on the *board* with the prose left behind, the pump's nameplate and
the PWM resolution each moving without the printed caps following, the `.py` quote trap,
and the netlist absent — which must **die**, not skip.

**Residual, named:** `check_part_values`'s `unparsed` branch is a belt for a widened token
regex, not a guard that has been seen to fire.

### 54 — CLOSED: every silk line on the board was 0.12 mm, and an outline font's "stroke" is not its ink

Same pass. Two holes of the same shape, both in `cadkit` and both fixed upstream
(canonical, then `propagate.py`; this board and ten others).

**A12 has measured silk TEXT for height and stroke since the beginning and had never
looked at a silk GRAPHIC.** Measured here: **all 264** of them — every part outline, every
polarity band, every pin-1 mark — were KiCad's default **0.12 mm**, which is 80 % of the
fab's own stated 0.15 mm minimum, *while the text beside them had been deliberately sized
so its thinnest glyph cleared 0.15*. A fab does not reject thin silk; it prints it thin,
broken, or not at all, and whichever happens the plot that was reviewed is not the board
that arrives.

`silkfit.thicken_ink()` raises them, reading the floor out of **quality's own fab table**
rather than a second copy of 0.15, and runs before `fit_refs` so the fitter dodges the
final ink. **It cost nothing**, which is the measurement that mattered: `silk_overlap`
stayed at **3**, A18 still reports nothing clipped, 0 unconnected, 0 violations.

**⚠ And `GetTextThickness()` is not an outline font's ink.** KiCad draws a TrueType face
from the glyph's own outlines. The field still holds a number — **0.30 mm** on all 139 of
this board's face texts — and A12 was reading it as the stroke and passing. The real
thinnest ink is **0.1533 mm**, measured through `TransformTextToPolySet` when the face was
chosen (finding 52) and read by nothing since. At 1.2 mm the same face would ink 0.12 mm
**with that check still reading 0.30 and still passing** — an assert that can only check
its own arithmetic, which is the third one of those this repo has found.

The stroke measurement now applies to stroke-font text only. An outline face's ink must be
measured and **declared per size** in `BOARD_NOTES["silk_ink"]` — `{1.5: 0.1533}` here —
and an undeclared size **fails** rather than noting, because a note is a figure nobody
read.

**M31 had rotted with it** and is re-measured: it said *"all 17 board-level silk items are
at 1.0 mm height and 0.15 mm stroke"*, which the face change falsified in both numbers.
140 silk texts now — 139 in Rennie Mackintosh PSG at 1.5 mm, and BZ1's stock `+` polarity
mark at 1.0 mm in the stroke font, on the floor for both. Its `138 / 138` CAD-label
corroboration is **139 / 139**, having now gone stale twice, which is the argument for
reading it rather than quoting it. Its "the ONE remaining silk_overlap" is **three**,
named: F2 over C21's designator, and R26 and C14 each over their own part's outline.

~~**⚠ THE PLACEMENT FILE UPLOADED TO JLCPCB ON 2026-10-06 IS STALE** — it is the
uncorrected one. The quote's prices still stand (same parts, same board), but the CPL
must be re-uploaded before ordering.~~

**DONE 2026-10-08, and not as two files.** The whole current `main.zip` went up, all
sixteen of them, because the copper and drill had moved too and re-uploading the CPL
alone would have ordered the old board with the new parts list. 34 of 34 matched, and
this time the match was diffed against `main-bom.csv` rather than read off the screen:
70 references, 34 lines, zero substitutions, with the comparison made to fail on a
planted wrong code for U2 first. The board is in the cart at $200.98; see
`docs/jlcpcb-quote.md`. Nothing is ordered.


### 55 — CLOSED: the FreeCAD tab stopped refreshing on every build, and the build printed it as a success

Found by being asked to open the tab. `src/build.py` sets `out` to
`assembly.step`'s path at the top of `main()`, saves to it, and then — 140 lines
later, inside the **board retention gate** — reuses the same name for a scratch
solid: `out = _swept(slid, (-1.0, 0.0, 0.0), 30.0)`. So the last two statements
in `main()` were handed a `cq.Workplane` instead of a path.

**Nothing was lost on disk.** `asm.save(out)` runs before the clobber, so
`assembly.step` was always written correctly. What broke is the two lines after:

* `print("Wrote %s …")` printed `Wrote <cadquery.cq.Workplane object at 0x…>`.
  **This is the whole defect in one line, and it reads as success** — it says
  "Wrote", it has a build number after it, and it is the last line of a
  200-line log.
* `show(out)` could not resolve a path. `show()` is documented *"Never raises"*
  and means it: it caught the `TypeError`, printed one line to stderr —
  `[freecad] viewer skipped: _path_normpath: path should be string, bytes or
  os.PathLike, not Workplane` — and returned `False`. Confirmed directly by
  calling `show()` with a Workplane.

So the shared hub silently stopped being refreshed by builds. The failure was
**not** silent in the strict sense — it printed — but stderr is unbuffered and
stdout is block-buffered when piped, so that one line sorts to a random place
in the middle of the log, nowhere near the "Wrote" line that contradicts it.
A warning that lands 180 lines from the statement it falsifies is not a warning.

**Fixed two ways.** The retention gate's scratch solid is `slid_sweep` now, so
the name is not shared. And because a `show()` that returns `False` is invisible
by construction, the tail of `main()` now asserts `isinstance(out, str)` before
using it and prints `*** THE FREECAD TAB DID NOT REFRESH ***` if `show()` comes
back false. **Made to fail:** the clobber was reinstated and the build stopped
with `AssertionError: the STEP path was overwritten before show(): got
<cadquery.cq.Workplane object …>. Some gate above reused the name `out` as a
scratch solid.`

### 56 — OPEN (mechanical, no copper): the battery cannot be lifted out — the access notch is 2.18 mm short

**`py -3.12 -m src.build` exits 1 and has been doing so**, on the *battery
access* gate:

```
=== battery access gate ===
  wood     *** BLOCKS THE PACK, 161 mm3 ***
  housing  clear
  tank     clear
  the pack needs 93 mm of lift to clear its rails
```

DESIGN_V2 lists this gate among the seven the build runs and says *"all exit
non-zero on failure"*, and it was written for exactly this: *"the pack could not
be lifted out. It fits in the dock, and that is not the same thing."*

**It is not a misplaced notch, it is a short one, and the number is exact.**
Intersecting the pack's lift-out sweep with the wood and measuring the result:

| | |
|---|---|
| fouling volume | **161.3 mm³** |
| x | −205.500 … −201.800 (3.700 mm — the outer plank's outboard edge) |
| y | **7.820 … 10.000 (2.180 mm)** |
| z | 188.000 … 208.000 (20.000 mm — the full plank thickness) |

3.700 × 2.180 × 20.000 = 161.3 mm³, which is the gate's figure to the last digit,
so the fouling is one rectangular prism and nothing else is touching.

`src/lumber_frame.py` puts the notch at `NOTCH_Y0 = 10.0`, `NOTCH_Y1 = 96.0`.
The sweep needs wood gone from **y ≥ 7.82**, so the notch's front end stops
2.18 mm before the pack does. Everything else about it is right — the outboard
limit, the depth, the 86 mm length, and both the housing and the tank are clear.

**Not fixed here**, because it is a change to a frame dimension that
`bom_consolidated.md` also states in words ("10–96 mm from the front") and the
owner cuts the wood. The fix is to move `NOTCH_Y0` forward past 7.82 with
clearance and re-take the sentence in the BOM; the gate then proves it.

⚠ **This is a CAD/woodwork finding and touches no copper, no firmware and no
fab output.** The board in the cart is unaffected.
