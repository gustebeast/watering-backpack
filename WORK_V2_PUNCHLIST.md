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
  the pack. The draw on the sensor's own output is 1.4–1.9 mA against its rated
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

**Closed at 0 unconnected / 0 violations / 0 FAIL / 0 OPEN**, 59 placements, 34 BOM
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

## 23. The edge rails will arrive attached unless the order says otherwise

**Open, and it is an order-form action rather than a design change.** Standard PCBA
pads the outline to **105 x 112 mm by adding two 5 mm rails on the 95 mm sides** — the
form states this itself. The housing bay is cut for a 95 mm board.

**"Depanel boards & edge rail before delivery" is under Advanced Options and is not
currently in `ORDER.txt`.** If it is missed, five boards arrive 10 mm too wide for the
bay they were designed into, and trimming a rail off a finished assembled board by hand
is how an edge trace gets cut.

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

**13 of 59 placements changed.** The origin shifts are arithmetic, not noise, and
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

**⚠ THE PLACEMENT FILE UPLOADED TO JLCPCB ON 2026-10-06 IS STALE** — it is the
uncorrected one. The quote's prices still stand (same parts, same board), but the CPL
must be re-uploaded before ordering.
