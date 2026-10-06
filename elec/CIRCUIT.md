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
| **VBAT** 15–20 V | pack, after **F2** (the on-board ATC blade fuse) + TVS. Reverse polarity is held by D1 as a **crowbar**, not by a series FET — see §6 | pump FETs, level sensor (fused), VGATE |
| **3V3** | **non-synchronous** buck from VBAT (LMR14020, catch diode D6) | ESP32, joystick, buzzer, logic |
| **VGATE** 10 V | 1k5 dropper + Zener shunt off VBAT | the two gate drivers, and nothing else |

There is no 5 V rail. The level sensor takes 5–24 V, so it runs **straight off
VBAT** rather than forcing a third regulator — this is why its output must be
open-collector (below).

**VGATE is not a third regulator either, and it was not here until the audit
below found that the gate drivers had nothing to run on.** The UCC27517 is a
4.5 V to 18 V part; 3V3 is under its UVLO. See audit finding 2.

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
  **Both power parts were previously specified by part numbers that did not meet
  this.** Recorded because the value string is the only human-readable thing in
  the BOM, and both of these read as decided while being wrong:

  | was | actual part | requirement | verdict |
  |---|---|---|---|
  | `AOD4184A-60V` | AOD4184A is **40 V** / 50 A, DPAK | ≥ 60 V | fails — and 40 V is rejected by name above |
  | `SS16H-60V-15A` | SS16H is **1 A** / 60 V, SMA | ≥ 15 A, D2PAK | fails — this leg carries ~3.75 A average, 7.5 A peak |

  The 40 V part also broke the protection coordination: the TVS below was chosen
  so its ~39 V clamp sits *under* the FET rating, and 39 of 40 V is no margin at
  all. `elec/main.py` now asserts that coupling.

  Neither is sourced, so both values carry the REQUIREMENT rather than a part
  number — `NFET-60V-10mR` and `SCHOTTKY-60V-15A` — and `elec/fab.py` counts
  both as open, which blocks an assembled order until someone satisfies the spec.
  A verified-compliant freewheel candidate, if useful: Vishay **VS-15TQ060S-M3**,
  60 V / 15 A, TO-263AB, V<sub>f</sub> 620 mV at 15 A. The FET is harder — the
  common 60 V DPAK parts sit at 19–23 mΩ at 4.5 V V<sub>GS</sub>, so meeting
  ≤ 10 mΩ needs a deliberate pick, not the first search hit.

- **Gate driver** — single-channel, ≥1 A, e.g. UCC27517 class. Not optional: a
  3.3 V GPIO switching a ~10 nC gate at 20 kHz spends too long in the linear
  region, and the loss lands in the FET.
  **It needs 4.5–18 V, so it runs off VGATE, not 3V3** — and it is the reason
  VGATE exists at all. This bullet and "There is no 5 V rail" above stood side
  by side for the life of the board without either noticing the other.
- **Schottky freewheel diode** — `SCHOTTKY-60V-15A-vf0V59`, D2PAK.
  Plain, not synchronous: it conducts only during off-time, and usage is mostly
  full-on, so the complexity of a second FET and a half-bridge driver buys little.
  ⚠ **The volts and amps were never the binding spec; V<sub>f</sub> is**, and it
  is in the value string now for the same reason the saturation current is in
  L1's `10uH/4A6sat` — the BOM line is the last place a number can still change
  the part that gets bought. "60 V, 15 A, D2PAK" is met by a wide cheap field;
  what separates them is the only term in this diode's power.
  **The duty is not the user's, and the worst case is a FULL battery.**
  `firmware/src/main.cpp` says it outright: "NO INTERMEDIATE DUTY. The stick is
  used hard-forward or hard-back, so engaged means RUN_DUTY and nothing else."
  RUN_DUTY synthesises the pump's 12 V nameplate from whatever the pack is, so
  D = 12 / V<sub>pack</sub> and the diode carries the other (1 − D). A drained
  15 V pack runs D = 0.80 and the diode conducts **20 %** of the time; a fresh
  20 V pack runs D = 0.60 and it conducts **40 %**. This line used to say "at
  50 % duty it carries ~3.75 A average and dissipates ~1.5 W" — a round number
  from before the duty was derived. The real worst case is **3.00 A average**,
  and it is *lower* than the old guess because the firmware will not run the
  pump at 50 %.
  **How hot, and what that demands of the part.** D2's tab is the cathode and
  sits on the VBAT pour, which fills as one island of 687.0 mm² (M3, measured on
  the filled board). D2 and D3 share it and never conduct together — direction
  is chosen by *which* pump is energised — so each sees the whole pour. 687 mm²
  of 1 oz copper puts a D2PAK at roughly **42 °C/W** junction-to-ambient by the
  standard pad-area curves; that figure is a **stated assumption, not a
  reading**, and it is the first number to replace when a part is chosen.
  Ambient is the sealed bay, not the garden: 35 °C outside plus the bay's own
  rise gives 50 °C. Holding T<sub>j</sub> ≤ 125 °C then allows **1.79 W**, and
  at 3.00 A average that is **V<sub>f</sub> ≤ 0.59 V at 7.5 A**. All of it is
  arithmetic in `elec/main.py` with an assert, so it cannot drift from this
  paragraph.
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

**Pin map.** These six are the firmware/board interface, and they are typed twice —
as `*_PIN` constants in `firmware/src/main.cpp` and as `u_mcu["IOnn"]` in
`elec/main.py`. `tools/check_pin_map.py` reads both sides from their own source and
fails if they disagree, so the agreement is enforced rather than remembered.

| net | GPIO | module pin | role | why this pin |
|---|---|---|---|---|
| `PWM_A` | IO26 | 11 | PWM out | pump A gate, via U3 |
| `PWM_B` | IO25 | 10 | PWM out | pump B gate, via U4 |
| `VBAT_SENSE` | IO35 | 7 | analog in | **must be ADC1** — see below |
| `JOY_FILT` | IO34 | 6 | analog in | **must be ADC1** — see below |
| `LEVEL` | IO14 | 13 | digital in | ADC2 is fine, it is read digitally |
| `BUZZ` | IO27 | 12 | digital out | through Q3 |

⚠️ **ADC2 is unusable while WiFi is up** — the radio owns that peripheral, and this
design has telemetry and OTA. That is the whole reason the two analog signals sit on
IO34/IO35 rather than somewhere more convenient, and it is the easiest rule to break
by tidying the pinout. The gate derives each pin's role from how the firmware
actually calls it (`analogRead`, `ledcAttach`, `digitalRead`, ...) rather than from a
declaration, so moving a signal to a new peripheral without moving it to a legal GPIO
is caught. It also checks GPIO 34-39 are never driven as outputs, that no pump gate
or the buzzer lands on a strapping pin, and that the module's physical-pin names
match the WROOM-32E pinout — a transposition there is a dead board that every other
check in this repo would pass.

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

  **MODE → GND, and that sets the polarity.** `elec/main.py` shorts the sensor's
  MODE wire to GND (`gnd += j_lvl["GND"], j_lvl["MODE"]`), which selects the
  part's **normally-closed** mode: *no liquid → output HIGH, liquid → output
  LOW*. MODE left floating selects normally-open instead, which inverts it. So
  on this board **a LOW on IO14 means liquid at the sensor**, which is what
  `LEVEL_FULL_IS_LOW` in the firmware encodes.

  The vendor warning not to "use the black wire as GND" is about not using MODE
  as the power *return* in place of the blue wire — shorting it to GND to pick
  the mode is the documented configuration, so the schematic is right. Recorded
  here because it is a two-source web finding, not something the schematic or
  the footprint can tell you, and getting it backwards means the alarm is silent
  during the one event it exists to catch. Confirm it on the bench with the `b`
  serial command, which prints the raw pin state next to the decoded one.
- *Optional:* low-side shunt per pump → ADC, for current telemetry.

## 5. Alert

- **Active magnetic buzzer**, **3 V rated** (3V3 is the only logic rail), driven
  through a small NPN/NMOS — ~30 mA is beyond a GPIO.
  Active, not passive: it needs DC, not a driven waveform. Not a speaker: that
  needs an amplifier.
  Filling happens with the **pump off** and the user standing at the tank, so it
  does not have to out-shout anything; the fitted part's **80 dB at 10 cm** is ample.
  (This said "~85 dB" against a part rated 80 — the conclusion survives, the figure
  was not the one on the BOM. 80 dB at 10 cm is ~60 dB at a metre, and it is a
  2.7 kHz tone, which is where hearing is most sensitive.) Sound port faces **down**
  (it is also a water path).

## 6. Protection

- **F2, a 10 A ATC blade fuse, ON THE BOARD.** Littelfuse 178.6165 FLR holder
  (20 × 6 mm, 80 V, 30 A, four solder pins per terminal), taking the standard ATC
  blade the owner already has — McMaster 7460K45, 10 A, 32 V, bought in a pack of
  five. The fuse itself is therefore not a BOM line; the holder was chosen to suit
  the fuse rather than the other way round.

  It used to be an in-line holder in the lead (8110K3). Moving it on-board cost
  12 mm of board length and a bay re-layout, and bought the thing §6's reverse-
  polarity sum needed: the fuse is a **board property** now, not a system
  requirement somebody has to remember.

  **What it stops protecting, named:** the dock-to-board harness. An in-line fuse
  in the lead covers that run; this one does not. On this machine that run is short
  and inside the sealed bay, and the long exposed lead is the pack's own, upstream
  of the dock, which no fuse of ours was ever going to cover.

  **F2 is the ONLY series element in the pack lead**, so VBAT_RAW — J1.1 to F2.1,
  9.3 mm of pour — is the only copper on the board in front of it. **C21** sits on
  it, 8.4 mm from the pad: 10 µF of ceramic at the pack entry, which is what carries
  the first microsecond of a pump step now that C1/C2's 200 µF are behind a fuse and
  its spring contacts. It is also the one capacitor a blown fuse does not isolate.
- **REVERSE POLARITY: held by D1 as a crowbar, and there is no series element.**
  This section used to promise a reverse-polarity P-FET the board does not have. The
  argument that made it optional was "the Makita terminal is keyed, so this is insurance
  rather than necessity" — true of a **keyed** inlet, and §7 then replaced the keyed XT30
  with **J1, a 5.08 mm screw terminal carrying two identical wires**, the single easiest
  thing in the machine to land the wrong way round. Nobody came back to this paragraph.
  No gate here could see it: every gate reads the **board**, and the claim lived in
  **prose**.

  **What was wrong was the framing, not just the part.** "Add protection" was read as
  "add a series element", and a series P-FET means splitting the VBAT pour into two
  islands bridged by the part — a re-layout of the board's highest-current path. But
  reverse-polarity protection by **crowbar is a SHUNT**, and D1 already *is* that shunt:
  a unidirectional TVS across VBAT–GND, landing on a pour and a ground plane that both
  already exist. Nothing has to be split. The only question is whether the part survives
  the job.

  **That question is I²t, which is why it can be answered here at all.** The fault
  current is set by the pack's internal resistance, which is not in this repo — so the
  pack is deliberately not the subject. The fuse clears on charge delivered, the diode
  dies on charge absorbed, and both are I²t; whichever is smaller goes first, at *any*
  fault current.

  | | I²t | verdict |
  |---|---|---|
  | D1 as built, **SMBJ24A** | 100 A IFSM at 8.3 ms → **83 A²s** | loses, by 1.4× |
  | the fuse, Littelfuse 257-010 10 A ATO | **115 A²s** minimum melt | |
  | D1 now, **SMCJ24A** | 200 A IFSM at 8.3 ms → **332 A²s** | **wins, 2.9×** |

  ⚠ The first version of this sum got the answer **backwards**, which is why the fuse
  figure is cited and not estimated: guessing "a 10 A blade fuse is about 50 A²s" made
  the fuse clear first and D1 survive. The published minimum is 115.

  **The fix was one footprint.** SMCJ24A is the same TVS one package up — clamp
  **38.9 V at 38.6 A, identical** to the SMBJ24A's (confirmed across five makers), so
  nothing downstream of the clamp moves; 1500 W against 600 W; IFSM 200 A against 100 A.
  No series element, no split pour, no keyed connector, and no argument with §7.
  `elec/main.py` carries the derivation and asserts `TVS_I2T_MARGIN > 1.5`.

  Residual, named: a reversed pack still runs current backwards through each pump
  winding via D2/D3 and the FETs' body diodes for as long as the fuse takes, so the
  pumps briefly suck on the pressure line, and C1/C2 sit reverse-biased at D1's forward
  drop for that time. Both are milliseconds and neither is a damage mechanism.

  ⚠ **AND THE FUSE IS ON THE BOARD NOW, WHICH CLOSES THE LAST GAP IN THIS ARGUMENT.**
  While it was in the lead, the whole sum rested on a part this repo did not contain:
  the requirement read "feed this board through a fuse of 115 A²s or less", and a board
  whose reverse-polarity protection depends on somebody else's fuse is a board with a
  promise in it, not a property. **F2** is that fuse — on the laminate, in series with
  D1, in the BOM. The 115 A²s is a number read off a part the board
  specifies now, rather than a condition imposed on whoever wires it up.
- **F1**, a 30 V
  200 mA resettable PTC, in series with J5.1 so the level sensor's cable cannot take the
  rail down or glow when it chafes (M36).
- **TVS on VBAT** — standoff above 20 V, clamping well below the FETs' 60 V. D1 is an
  **SMCJ24A**: 24 V standoff, 26.7 V minimum breakdown, **VC = 38.9 V max** at 38.6 A,
  1500 W — read off the table rather than rounded, because it is the single number every
  part on the rail is judged against (M5). The clamp is **the same 38.9 V** as the
  SMBJ24A this replaced; what the bigger package buys is surge current, and that is
  bought for the reverse-polarity job above, not for the transient one.
- **ESD on every connector a cable reaches** (joystick, level sensor) per
  PCB_README §5.

## 7. Connectors — terminal blocks, not JST

| net | part | pitch | note |
|---|---|---|---|
| battery in | 2-pos terminal | 5.08 mm | permanent — killswitch is at the Makita dock |
| pump A / pump B | 2-pos terminal each | 5.08 mm | 7.5 A each |
| joystick | 5-pos terminal | 5.08 mm | to the existing KY-023 |
| level sensor | 4-pos terminal | 5.08 mm | VBAT, GND, OUT, MODE |
| programming | 6-pin 2.54 mm header | | 3V3/GND/ESP_TX/ESP_RX/EN/IO0 — named from the **board's** end, so cross them to the adapter |

**Why terminals over JST here.** JST earns its place where a joint is plugged and
unplugged often, or where space is tight. Neither applies: every one of these is
landed once at assembly and then left alone, and the board sits in a ~70 mm side
pocket with room to spare.

The decisive argument is PCB_README §3 — *"check that BOTH halves are in stock
before comparing anything else... a joint where you supply both halves is the case
the catalogue is worst at."* A JST joint is a header, a housing, crimp contacts
and a 2 mm crimp tool. **A terminal block is one part with no mating half.**

**~~Prefer push-in (spring-cage) over screw.~~ WITHDRAWN.** It said screw clamps
back off under vibration and spring-cage does not. The user's requirement is
narrower than that argument assumed — *any* no-solder wire attachment will do —
and the preference was buying one property at the cost of a second connector
family. A screw clamp torqued to the WJ500V's specified 0.4 N·m is not the
vibration risk a spring cage is usually sold against, and the tie rib below
(**Terminals provide NO strain relief**) is what actually carries cable load.

**ONE FAMILY, ALL FIVE.** Every field terminal is now Ningbo Kangnex
`WJ500V-5.08-NP` — 2P for J1/J2/J3, 5P for J4, 4P for J5. One pitch, one
screwdriver, one wire range, one entry-face rule, one drawing to be wrong about.
J4 and J5 were 3.5 mm Phoenix PT-1,5 push-ins and the change cost them nothing:
they carry milliamps to a joystick and a level sensor.

**5.08 mm for the pump legs.** 3.5 mm parts are typically rated 8-10 A, which is
too close to 7.5 A to be comfortable.

**What 7.5 A actually does to the terminal.** Read off the customer drawing
(LCSC C8465, rev A), not the listing — the two disagree and the listing is the
optimistic one. The drawing: **UL 10 A / IEC 24 A**, 22–12 AWG, PA66 UL94V-0,
−40…**+105 °C**, contact resistance ≤ 20 mΩ, M2.5 at 0.4 N·m. The listing says
18 A for the 2P and 15 A for the 4P/5P. Three numbers, so design against the
lowest certified one: UL 10 A.

The limit that binds is not the current, it is the **insulation temperature**,
and I²R rise scales with the square of current:

- rise at 7.5 A = 30 K × (7.5 / 10)² = **16.9 K** (UL rates at a 30 K rise)
- in the sealed housing at 50 °C ambient → **66.9 °C**, against 105 °C
- **38 K of margin.** J1 is easier still: it carries one pump chopped at
  D = 0.60–0.80, so 6.7 A RMS worst case, a 13.5 K rise, 63.5 °C.

J1 never sees both pumps — `tools/check_pump_dirs.py` is the gate that holds it.

The 20 mΩ figure is an acceptance *limit*, not a working value: at 20 mΩ a
contact dissipates 7.5² × 0.020 = **1.13 W**, which is the number that matters
if a screw is left loose. A properly torqued joint is ~1 mΩ and 0.06 W. That
asymmetry is the argument for the torque spec being written down.

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

**Which face of a terminal block takes the wire.** The entry is the footprint's
local **+Y** face. Measured from Phoenix's own STEP models, as material in the
first 1.5 mm behind each long face (the hollow face is the opening):

| part | behind local +Y | behind local −Y | verdict |
|---|---|---|---|
| MKDS-3-2-5.08 (J1–J3) | 140 mm3 | 149 mm3 | **indeterminate** |
| MKDS-3-5-5.08 (J4) | — | — | same simplified block, **indeterminate** |
| MKDS-3-4-5.08 (J5) | — | — | same simplified block, **indeterminate** |
| ~~PT-1,5-5-3.5-H (J4)~~ | ~~54 mm3~~ | ~~232 mm3~~ | withdrawn — part replaced |
| ~~PT-1,5-4-3.5-H (J5)~~ | ~~43 mm3~~ | ~~185 mm3~~ | withdrawn — part replaced |

**Local +Y is the board's −Y.** `cadkit/PCB_README.md` §0: BOARD_NOTES is
millimetres, board-centred, **+Y up**, and `layout.py` flips to KiCad's +Y-down
frame. So a footprint's local +Y points at the board's −Y. Verified rather than
assumed — each terminal's local `F.Fab` box, negated, matches its placed box in
`elec/geom/main.geom.json` to within 0.5 mm, for all five.

**So rot 0 points every entry at world −Z, straight down**, which is the
direction of the bay's only opening. J1–J4 sit 20 mm above the chase and drop
into it; J5's lead runs down the board's face to the same place. Facing J5 "out"
at the top edge, which is the usual rule for an edge connector, would aim it at
a ceiling 20 mm away with nothing to pass through. **The placements are correct
as they stand — do not rotate them.**

A previous note in this file said J1–J4 wanted rot 180 and J5 was fine. It was
wrong in both halves: it had the entry face right but dropped the board/KiCad Y
flip above. It is withdrawn, and so is the note before it that claimed the
opposite.

**⚠ THE ENTRY FACE IS NOW CONVENTION FOR ALL FIVE, AND THAT IS A REGRESSION THE
ONE-FAMILY CHANGE CAUSED.** It has to be said plainly, because the change was
otherwise an improvement and it would be easy to let this ride under it.

Before: J4 and J5 were Phoenix PT-1,5, whose STEP models have real Y-axis bores,
so their entry face was *measured* (54 mm³ of material behind local +Y against
232 for J4; 43 against 185 for J5) — and J1–J3's face rested on the fact that
the two measured parts agreed with the generator's convention. After: all five
are MKDS-3 footprints, whose STEP model is a simplified block with no bores and
material symmetric within 6 % at every depth. **The two parts that carried the
measurement are gone.** Five of five now rest on convention where three did.

What is gained in exchange is not nothing: all five are the *identical part at
the identical rotation*, so whatever the entry face is, it is the same face on
all five and they cannot disagree with each other. The user's requirement — every
field wire leaving one edge — is now satisfied by construction rather than by two
STEP models happening to agree.

What settles it, and what the WJ500V drawing adds: the pin row is **4.50 mm from
one long face and 5.50 mm from the other** (body 10.00 mm deep). That asymmetry
is visible on a part in hand with a ruler, which is a better acceptance test than
any model — measure which face the wire bore opens on, and it is decided for all
five at once. **Do this before ordering a second board.** The drawing's own views
do not name the face: the side view is a closed silhouette, and reading it off
third-angle projection convention would be a guess, not a measurement.

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

---

## The part-by-part audit, and what it found

Every IC on this board was checked pin by pin against its own datasheet, and
every rail against the part it feeds. Twelve findings, four of which would have
stopped the board working and one of which would have destroyed it. They are
recorded here rather than quietly fixed, because the common thread is worth
seeing: **nothing in the pipeline checks a pin map or a voltage.** ERC checks
that pins are connected, DRC checks that copper matches the netlist, and the
netlist is a copy of the pin map it is supposed to be verifying.

### 1. The gate drivers' pinout was wrong on four of five pins

TI SLUSAY4C, page 2: the UCC27517 in DBV (SOT-23-5) is **1 VDD, 2 GND, 3 IN+,
4 IN−, 5 OUT.** The board read `{1: IN, 2: GND, 3: NC, 4: OUT, 5: VDD}`. So:

| pin | the board drove it with | it actually is |
|---|---|---|
| 1 | `PWM_A` from IO26 | **VDD** — a GPIO on the supply pin |
| 2 | GND | GND — correct, by coincidence |
| 3 | nothing | **IN+** — the real input, left floating |
| 4 | `GATE_A` to the FET | **IN−** — a gate net on an input |
| 5 | **+3V3** | **OUT** — a 4 A driver output shorted to the logic rail |

"Output Held Low when Input Pins are Floating," so neither pump could have run
even if nothing had burned. Pin 5 on +3V3 is the one that takes the board with
it.

`IN−` is now tied to GND deliberately: *"the unused input pin is not left
floating and must be properly biased to ensure that driver output is enabled for
normal operation."* Grounded IN− is the enabled state for the non-inverting path.

### 2. There was no rail the gate drivers could run on

The UCC27517 is a **4.5 V to 18 V** part. The only logic rail on this board is
3.3 V, which is under its UVLO — so even with the pinout right, both outputs
would have sat low. This document said *"There is no 5 V rail"* and specified a
UCC27517-class driver two sections apart, and the two cannot both stand. It is
implied elsewhere too: the FET requirement is "≤ 10 mΩ at **4.5 V** V<sub>GS</sub>",
a gate drive the board could not produce.

**VGATE** fixes it: a 1k5 dropper from VBAT to a 10 V Zener, with 10 µF of local
bulk. A shunt and not a regulator because the load is tiny — the drivers'
quiescent plus Q<sub>g</sub>×f<sub>sw</sub>, about 1.5 mA with one pump running
at 20 kHz — so two passives do the whole job and there is no pinout to get
wrong. It costs 3.3 mA of standing current at a flat pack and 6.7 mA at a fresh
one, which is nothing beside the ESP32's 100 mA and the level sensor's own draw;
this machine has no low-power idle state to protect. A 60 V LDO would be tidier
and would not idle, if you would rather spend the part.

10 V and not 5: inside the driver's window with margin at both ends, and it
enhances the FET harder than the 4.5 V its R<sub>DS(on)</sub> is quoted at.

### 3. The freewheel diodes were across the switch, not across the pump

D2/D3 were netted anode-to-GND, cathode-to-drain. That is the catch diode for a
**high-side** switch. This is a low-side switch with the pump returned to VBAT:
when the FET opens, the pump's inductance pushes current *into* the drain node
and it has to get back to VBAT. A diode from GND to the drain is reverse-biased
for that current and does nothing, so the drain would have flown up until the
FET avalanched — at 7.5 A, 20 kHz.

The section above budgets ~1.5 W in this diode and calls it the board's largest
heat source. As netted it would have dissipated nothing, which is the tell.

### 4. RT/SYNC was floating, which the datasheet forbids in those words

SNVSAA5B §6.3.8: *"The RT/SYNC pin can't be left floating or shorted to ground."*
It sets the switching frequency. **R8 = 49k9**, the datasheet's own table value
for 500 kHz, which with the 10 µH inductor gives 0.55 A of ripple at 20 V in.

### 4a. The buck had no catch diode, and it is not a synchronous part

The worst finding in this file, because it is not a margin — the 3.3 V rail could
not have worked, and with it the MCU, the joystick reading and the logic supply
for both gate drivers.

The LMR14020 integrates **one** switch. Its feature list says "90mΩ **high-side**
MOSFET" and §6.1 repeats it: *"It integrates a 90 mΩ (typical) high-side
MOSFET"*. There is no low-side device inside, so when that switch opens the
inductor current needs an external rectifier or it has no path at all. The
datasheet is not subtle about this:

- §6.3 describes the current freewheeling *"through freewheel diode with a slope
  of −VOUT / L"*
- §6.3 again: *"the high-side MOSFET is off and the **external low side diode**
  conducts"*
- Figure 7-1, the application circuit, carries a component **D**
- §7.2.2.5 is an entire section titled **Schottky Diode Selection**
- the layout example on the facing page labels it *"Rectifier Diode"*

This board carried L1, C15, C3, C4, C5, R1, R2, R8 and C14 — every external part
in that figure **except D**. With the switch open the SW node is driven negative
by the inductor until something breaks down, and SW's absolute minimum is
**−3 V** (§5.1).

**D6 = SCHOTTKY-60V-3A, SMA**, cathode on SW and anode on GND. The value carries
the requirement rather than a part number, as Q1/Q2 and D2/D3 do, and §7.2.2.5
sets both halves of it:

- *"The breakdown voltage rating of the diode is preferred to be 25% higher than
  the maximum input voltage"* — 1.25 × 20 V = 25 V is the floor. 60 V is used
  instead, for the reason the whole board is built on: everything on this node is
  rated past a fresh pack **and** past the TVS's 38.9 V clamp, SW's own absolute
  maximum is 44 V, and 60 V makes this the same requirement as the pump
  freewheels — one fewer number to get wrong.
- *"The current rating for the diode must be equal to the maximum output current
  ... A 2.5 A to 3 A rated diode is a good starting point"* — 3 A, against an
  average of (1 − D) × IOUT = 0.835 × 0.6 = **0.50 A**.

It is placed between pins 7 and 8, which are adjacent, with its two legs balanced
at 3.60 and 3.80 mm — see section 13 for why it, and not the inductor, gets that
place.

### 4b. The inductor saturated below the regulator's own current limit

Same section of the same datasheet, §7.2.2.3: *"The inductor current rating must
be higher than current limit"*, because *"during an instantaneous short or over
current operation event, the RMS and peak inductor current can be high"*. The
LMR14020's high-side current limit is 2.5 / 3.2 / **3.8 A** min/typ/max (§5.5).

The part fitted was a Bourns **SRN6045TA-150M**, 15 µH, Isat **3.80 A typ** — not
above the limit but equal to it, and equal to the *typical*, so half the reel
saturates below a fault the regulator is entitled to hold indefinitely. TI's own
worked example in that section pairs the same limit with "3 A RMS current and 4 A
saturation current", so this is not a strict reading of the sentence.

The fix runs **downward**, which is the counter-intuitive part: in this series
Isat falls as inductance rises, so 22 µH (3.30 A) and 33 µH (2.50 A) are both
worse. **L1 is now SRN6045TA-100M** — 10 µH ±20 %, DCR 52 mΩ, Irms 3.20 A,
Isat **4.60 A** — same series, same 6045 land, same price.

10 µH is also what the datasheet's inductance equation asks for. K_IND is "the
amount of inductor ripple current relative to the maximum output current" and
"must be 20 %–40 %"; against this part's rated 2 A that window is 6.9–13.8 µH,
and 10 sits in the middle of it (K_IND = 0.28). Sizing K_IND against *this
board's* 0.6 A load would ask for 23–46 µH instead, and every one of those
saturates below the current limit — which is how a 2 A regulator run at 0.6 A
talks you into an inductor its own fault current destroys.

Read Bourns' definitions before comparing these to another maker's: this series
quotes Isat where "inductance drops 30 %" — looser than the common 20 % — and
Irms at a 40 °C rise, not 20. `elec/main.py` carries all of it as asserts, so a
substitution has to satisfy them rather than inherit a number nobody re-read.

### 5. Pin 6 is SS, not COMP — and it had nothing on it

The LMR14020 is internally compensated and has no COMP pin. Pin 6 is soft-start.
Floating, the ramp is stray capacitance and 3 µA, which is no ramp; **C14 = 10 n**
gives a defined 2.5 ms into the 42 µF of output capacitance.

### 6. The buck's exposed pad was not on the footprint

LMR14020SDDA is an **HSOIC-8 with PowerPAD**. Datasheet pin 9: *"Major heat
dissipation path of the die. Must be connected to ground plane on PCB."* It was
drawn on a plain `Package_SO:SOIC-8` land — no pad under the pad, the part's
whole thermal path landing on solder mask. It is now `wbp:SOIC-8-1EP-FABDRILL`,
KiCad's EP2.29x3mm ThermalVias footprint with its 0.2 mm vias opened to 0.3 for
the fab floor, which is the same fix the ESP32 footprint needed and for the same
reason.

### 7. The feedback divider set 3.12 V, not 3.3

LMR14020 V<sub>FB</sub> is **0.750 V** typ (SNVSAA5B §5.5: 0.744 / 0.750 / 0.756
at 25 °C). 100k / 31k6 gives 0.75 × (1 + 100/31.6) = **3.12 V**, 5.4 % low — on
the rail that is also the ADC reference for the battery gauge and the joystick.
**R2 = 29k4** (E96) gives 3.301. The arithmetic is in `elec/main.py` now with an
assert, so the comment can no longer disagree with the part.

### 8. Every net was 0.25 mm, including the ones carrying 7.5 A

cadkit's own note: *"By IPC-2221 at a 10 °C rise, 0.25 mm of 1 oz outer copper
carries 0.88 A"*, and *"DRC compares copper to the netlist and has no concept of
current, and the netlist has no concept of width."* VBAT and both pump legs carry
7.5 A peak and ~3.75 A average and were drawn at the default.

`net_widths` now puts them at **1.2 mm**, and VGATE at 0.4. 1.2 is not the IPC
answer — 7.5 A at a 10 °C rise wants ~4.8 mm of 1 oz copper, and a track that
wide is a pour, not a track. What a width can do here is carry the *average*
(3.75 A wants ~1.9 mm at 10 °C, ~1.1 mm at 30 °C) and stop the router drawing a
0.25 mm wire between a 5.08 mm screw terminal and a D2PAK tab. These three nets
land only on MKDS-3 pads, TO-252/TO-263 tabs and 10 × 10.5 electrolytic pads —
every one of them wider than 1.2 — which is why they can take it and the
0603-populated signal nets cannot.

### 9. Nothing on the board could be measured

Not a defect in the circuit, a defect in what happens when the circuit is wrong.
Eight findings above were caught by reading datasheets; the ninth kind is caught
by a probe, and there was nowhere to put one. Every node of interest was either
under a 0603 or inside a terminal block.

**Ten test pads**, 1.5 mm bare copper, one per node worth a meter:

| pad | net | what it answers on the bench |
|---|---|---|
| TP1 | GND | the reference for the other nine |
| TP2 | VBAT | is the pack actually getting to the board |
| TP3 | +3V3 | did finding 7 get fixed — should read 3.30, not 3.12 |
| TP4 | VGATE | does finding 2's Zener rail exist, and is it 10 V |
| TP5 | SW | is the buck switching, and at finding 4's 500 kHz |
| TP6 | GATE_A | does pump A's gate swing 0 to 10 V |
| TP7 | GATE_B | same, pump B — and the pair tells you one driver from two |
| TP8 | VBAT_SENSE | does the divider match TP2 x 0.1535 at the ADC |
| TP9 | JOY_FILT | is the RC filter settling, or is it the joystick that is dead |
| TP10 | LEVEL | is the pull-up pulling, and is the float open or closed |

TP3, TP4 and TP5 are the three that fall straight out of the audit: each is the
measurement that confirms a finding above was really fixed, rather than fixed in
the source.

**Silkscreen, because a pad with no name is not a test point.** Each pad is
labelled with its NET name on the front, not its reference — `GATE_A` is what you
want to read with a probe in one hand, and `TP6` means nothing without this
table. All six connectors get their pinout on the back, which is the side you
read while wiring with the board in the housing. Seventeen labels in all.

**How the pads are placed, and why it is not in the placement table.** The pads
are put down AFTER routing (`post_route_refs`), because the point of a bare pad
is to land on copper that is already there and need no track of its own. The
coordinates in `BOARD_NOTES` are therefore *preferences* — chosen next to the
thing each pad helps bring up — and `route.py` re-searches each one against the
finished copper, keeping it as close to its preference as it can.

Seven of the ten land on existing copper. Three — SW, GATE_A, GATE_B — have no
front-copper site anywhere on the board that is also clear of a courtyard, their
nets being short runs boxed in between the FETs, the drivers and the gate
resistors. Those three arrive unconnected and `close_last.py` maze-routes a stub
out to each: 2.0 mm for SW, 7.4 mm for GATE_A, 19.5 mm for GATE_B. A stub on a
gate node is worth knowing about, so the run prints it. 19.5 mm is about 15 nH
beside the 10 ohm gate resistor, which leaves the gate loop overdamped, so it is
noted rather than fixed.

**This found a bug in cadkit, not in the board.** `route.py` searched for a clear
site using the **pad's** radius while DRC judges the result by the footprint's
**courtyard** — 0.75 mm against 1.3 mm for a D1.5 mm pad. Adding these ten pads
re-sited nine of them and five went straight into a `courtyards_overlap`
violation that the run had just created: a search whose accept test is not the
rule it is graded by. The radius is the courtyard's now, and the comment at
`cadkit/pcbflow/route.py` carries the measurement so it cannot drift back.

### 10. The freewheel diode had one of its two anode leads on no net

`Package_TO_SOT_SMD:TO-263-2` is a **three**-pad land: pads 1 and 3 are the
outer leads and pad 2 is the 101.5 mm² tab, measured off KiCad's own footprint.
D2/D3 were declared `["A", "K"]`, which nets pad 1 and the tab — and leaves
**pad 3 on no net at all**.

That matters because of what you can actually buy. At ≥ 15 A and 60 V in D2PAK
the part is usually a **common-cathode dual**, whose pad 3 is the second anode.
Half the diode would never have conducted, in the part this document calls the
board's largest heat source, carrying 7.5 A.

Netting pad 3 to the anode is right whichever part arrives: on a dual it
parallels the two halves as intended, and on a true two-lead device there is no
pin behind that pad to reach.

### 11. The ESP32's ground was two pins short of four

KiCad's own `RF_Module` symbol declares this module's GND pin as number
**`"[1,15,38,39]"`**. The board netted 1 and 38. So:

- **Pin 15 is a plain GND pin and it was floating.** Not optional.
- **Pin 39 is the underside exposed pad — 21 pads in the footprint**, one 9-land
  array plus twelve 0.3 mm thermal vias, the module's whole thermal and RF
  ground, on no net. Espressif's pin table runs 1–38 plus the optional
  P_GND/39; the module meets spec unsoldered, so this one is good practice
  rather than a defect. (The "soldering pin 39 is not recommended" line in the
  older WROOM-32 datasheet is a translation error for *not necessary*.)

`tools/check_pin_map.py` had never heard of pin 39 either — its table ran 1–38
— so when the fix landed, that gate called a grounded pin 39 "NC or unknown on
this module". A table that is the only authority on itself cannot catch a pin
missing *from* it.

### 12. A pad with no net is not an unconnected net

Findings 10 and 11 share one cause, and it is the reason both survived every
check on the board: **DRC and the 0-unconnected gate are both blind to a pad
that carries no net at all.** Unconnected-net checking compares the copper to
the netlist. A pad the netlist never mentions is not in the comparison.

Twenty-four pads on this board legitimately carry no net — unused module GPIOs,
the flash pins wired to the can's own SPI flash, the one true NC. Twenty-six did
not, and nothing in the pipeline could tell those apart, because telling them
apart needs a reason per pin and there were no reasons written down anywhere.

`tools/check_ic_pinouts.py` counts pads now, and the 24 are declared one per
line in `DECLARED_NETLESS` with why each floats. It also fails on a *stale*
declaration — a pin claimed to float that now carries a net — because an excuse
that no longer matches anything stands ready to hide the next real one.

### Three cadkit bugs the test pads flushed out

Worth separating from the circuit findings: these were in the tooling, and each
produced a board that read as clean.

1. **The post-route pad search did not use the rule it was graded by.**
   `route.py` searched for a clear site using the **pad's** radius while DRC
   judges the result by the footprint's **courtyard** — 0.75 mm against 1.3 mm
   for a D1.5 mm pad. Adding ten pads re-sited nine, and five went straight
   into a `courtyards_overlap` violation the run had just created.
2. **When the search failed, the pad was left where it was** — a coordinate
   chosen against an *older* route. That put TP10 (LEVEL) on top of a VBAT
   track: a 27.8 mm **short** from the battery to the level-sensor input, plus a
   mask bridge to D2's pad. The fallback is now a site that is merely *safe*,
   and failing that the footprint is removed and the run says so. A board
   missing one test point can still be brought up; one with VBAT on a GPIO
   cannot be powered.
3. **`board.Remove()` hands ownership to Python**, so the removed vias were
   freed the moment `drop_redundant_pth_vias` returned — while the board still
   referred to them. It surfaced fifteen lines later as `'SwigPyObject' object
   has no attribute 'Pads'`, which is what a use-after-free looks like from the
   outside. It had been removing four vias from connector pads for months and
   broke the day pin 39 got a net and the count went to ten.

A fourth, smaller: `close_last.py` emitted a layer change that immediately
reversed, putting two LEVEL vias 0.067 mm apart and two GATE_A vias 0.242 mm
apart against a 0.25 mm minimum — `hole_to_hole` at "actual 0.0000 mm", graded a
*warning*, so the error count stayed at zero. Near-coincident vias are merged
now, seeded with the vias already on the net, because the hole being crowded
need not be another new one.

And one in `fab.py`: **an explicit `OPEN_VALUES` declaration was losing to a
footprint guess.** `GENERIC` matches `Diode_SMD:D_SOD`, which is right for
"1N4148W" and wrong for a Zener nobody has sourced. The VGATE Zener was counted
as *sourced* and left out of the "cannot be ordered assembled" list — while
sitting in the BOM with a blank part number. Thirty BOM lines reported as 17
generic + 12 open, and the thirteenth was the rail that makes the pumps switch
at all.

### 13. The buck cluster was never laid out against its own datasheet

Finding 4a came out of doing this, which is the point of the rule that asks for
it: PCB_QUALITY M13 says to *"compare the placed board against the datasheet's
layout figure, side by side"*, and reading SNVSAA5B §7.4 closely enough to do
that is what turned up the missing rectifier in guidelines 4 and 5.

The cluster had never been re-laid when the bottom half of the board was rebuilt
— the note in `elec/main.py` said so in as many words, on the grounds that an
experiment on a working region costs you a routing to compare against. It was not
a working region. Measured on the routed board, pad to pad, before → after:

| guideline | connection | before | after |
|---|---|---:|---:|
| 2 | CIN to VIN | 4.43 | **3.80** |
| 2 | CIN to the GND pin | 5.44 | **3.80** |
| — | bootstrap cap to BOOT | 14.01 | **4.90** |
| 5 | catch diode K to the SW pin | — | **3.60** |
| 5 | catch diode A to the GND pin | — | **3.80** |
| 3 | SW pin to the inductor | 11.61 | **7.05** |
| 1 | FB pin to the divider's tap | 6.07 | **1.77** |
| 1 | FB pin to R1's tap | 10.93 | **2.73** |
| 4 | inductor output to COUT | 10.36 | **2.85** |
| — | RT pin to R8 | 17.67 | **2.30** |
| — | SS pin to C14 | 17.08 | **4.33** |

The whole FB node is now 3.85 mm of track, the commutation loop is 7.39 mm
outside the parts, and the smallest courtyard gap in the cluster is 0.230 mm.

**The two CIN legs are equal, and that is the shape of the whole region.** U1 is a
dual-row HSOIC, so VIN (pin 2) and GND (pin 7) sit directly opposite each other
at dy +0.635 — 4.95 mm apart across the body. No ceramic can sit beside both, so
the hot loop has a floor, and centring C15 **above** the package is what reaches
it: 3.80 mm on each side instead of 4.43 and 5.44. The bootstrap capacitor bridges
left to right for the same reason (BOOT is pin 1, SW is pin 8).

**Two deliberate deviations, both named rather than lumped.**

*D6 takes the place beside pins 7 and 8, and L1 the next one out.* That costs the
switch node about 3.5 mm. Guideline 3 wants the inductor at SW and guideline 5
wants the diode's ground short, and on this package they compete for the same
3 mm. The diode wins because it is the part that **commutates**: every cycle the
inductor current steps out of the high-side switch and into D6, so the loop
SW–D6–GND is where di/dt lives and its area sets the ringing on a node whose
rating stops at −3 V. The inductor's own current does not step at all, and
guideline 3's stated reason for keeping it close is *"to reduce magnetic and
electrostatic noise"* — a radiation argument, not a loop-area one.

*RT and SS are in none of the six guidelines.* Both carry microamps into a timing
pin, so they get what is left over, and C14 at 4.33 mm gives up nothing the
datasheet asked for.

Guideline 1's second half is measured too — *"VOUT sense path away from noisy
nodes"*: the nearest FB track comes 3.56 mm to a SW track and the nearest +3V3
track 3.53 mm, neither adjacent.

### C5 was never an output capacitor, whatever its comment said

Moving C5 to the inductor broke A2 on J6, and that is how this surfaced. C5 sat at
(−8, 26) labelled "3V3 out", and what it was actually doing was being **J6's
bypass**: A2 gives a connector 25 mm to its nearest charge, and C5's pad was the
only +3V3 ceramic inside that of J6 pin 1 — 20.9 mm, where C4 was 25.88 and
failed. So C5 is now placed for the job it has, local charge for the 3V3 that
leaves the board down the programmer's cable, exactly as C16 is for J4. **C4 is
the output capacitor** and does the high-frequency work alone, 2.85 mm from L1's
output pad.

### Still open: the antenna points at the battery

§3 above says to orient the module **away from the tank**, and in the housing it
is: the tank is 83 mm above the board and the antenna fires along −Y. What −Y
reaches instead is the Makita pack, 10–80 mm away in the same height band, which
is a lithium pack in a steel-and-plastic case. Nobody has measured it. The board
cannot be turned without putting the terminal blocks at the top of the bay, away
from the cable chase, so this is a layout question (move U2 to the other edge),
not a mounting one.

## Status and what blocks what

**The board exists.** It is generated programmatically — that answered the
generate-vs-hand-route question — and the flow is three commands:

```
py -3.12 elec/main.py                                   # netlist + board.json
<KiCad python> cadkit/pcbflow/finish.py elec/out/main    # route -> geom.json
<KiCad python> elec/fab.py main                          # -> elec/out/fab/main.zip
```

Current result: 95 x 112 mm, 1.6 mm, 69 footprints, 4 mounting holes, **0
unconnected and 0 violations** — 59 routed parts plus the ten bring-up pads of
finding 9. 32 DRC *warnings* remain: 27 silkscreen (`silk_over_copper` ×17,
`silk_overlap` ×10), most of them the net labels sitting on the copper they
name, which is where a label belongs; and five `track_dangling`. `finish.py` prints warnings but deliberately does not fail
a board on them, so these are accepted, not overlooked. What it *does* fail on is
an **unexpected violation class**, which is how finding 9's five courtyard
overlaps and the TP10 short were both caught.

Four of the ten pads — SW, GATE_A, GATE_B and LEVEL — have no exposed front
copper of their own, their nets being short runs boxed in between the FETs, the
drivers and the gate resistors. They are parked clear and `close_last.py`
maze-routes a stub to each.

`elec/out/` is generated and gitignored — only `elec/geom/main.geom.json` is
committed, because that is what the CAD consumes.

**The mechanical work is unblocked and done.** PCB_README's rule — *"Model from the
routed board, never from the placement table"* — is honoured: `src/housing.py`
sources the pocket from `Boards("elec/geom")`, never a typed placement, and
`src/build.py` runs a routed-board agreement gate that fails if the CAD and the
routed board drift apart (it checks the outline, the cutouts, and all 48 routed parts,
and it catches a mirrored solid). The PCB pocket is **not** in `src/pump_frame.py`
any more; the dead block there was removed when the housing absorbed it.

**What actually blocks what now.** Bare boards are orderable today. *Assembly* is
blocked on the thirteen `OPEN_VALUES` in `elec/fab.py` — most urgently a >=60 V,
<=10 mOhm-at-4.5 V DPAK FET and a >=60 V / >=15 A D2PAK Schottky; `fab.py` fails
the build rather than shipping a part number it cannot stand behind. **The
Schottky may be a common-cathode dual** at that rating, which is why finding 10
nets both anode leads: either kind drops in.

The thirteenth is the VGATE Zener, and it was invisible until `fab.py` was
taught that a declaration beats a footprint guess — see the cadkit note under
finding 12. Nothing
mechanical and nothing in the firmware waits on the board.
