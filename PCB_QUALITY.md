# PCB quality rules

**The one place PCB lessons go.** Every board, in every project, is held to this list by
the same pass, so a lesson learned ordering one board is checked on every board after it.

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/quality.py elec/out/<board>
```

`pcbflow/finish.py` runs it at the end of every board run (its last line ends
`| quality: N FAIL, M OPEN`), the fab package carries the report as `QUALITY.txt`, and a
project that wants the gate hard passes `require_quality=True` in its `elec/fab.py`. A
board is quality-clean at **`0 FAIL, 0 OPEN`**. The full result is also written to
`elec/out/<board>.quality.json`. `pcbflow/example/blinky.py` is a board that passes.

DRC proves the copper matches the netlist and clears itself. It does not say the board is
any good. That is what this list is for.

* **`A<n>` — automated.** A function in `cadkit/pcbflow/quality.py`. Reports `ok`, `FAIL`
  or `WAIVED`.
* **`M<n>` — manual.** Something only a reader can check. The designer — a person or an
  LLM — does the check and **records what they looked at** in the board's notes. Until
  then the item is `OPEN` on every run. "Checked" is not a sign-off; "LMR16006 datasheet
  SNVSA24 fig. 14: L 22 µH, Cout 22 µF, FB 100k/19.1k → 5.02 V" is.

## For the designer (LLM or human): how to run the pass

1. Route the board (`finish.py`). Read the quality block at the end.
2. For each `FAIL`: fix the **design** (move the part, widen the copper, add the
   capacitor), regenerate, re-route. Waive only when the rule genuinely does not apply,
   and say why — a waiver prints on every run.
3. For each `OPEN`: do the check against the primary source (datasheet, drawing, the
   mating part), then sign it in the generator with the evidence.
4. Do not order at anything but `0 FAIL, 0 OPEN`.

## Hard and soft

Every `FAIL` line is tagged.

* **`[hard]`** — no board has a good reason to keep it. It cannot be waived (the script
  ignores a waiver written for one). Change the design, or correct the declaration.
* **`[soft]`** — a default. **Follow it unless the rule's own "Break it when" list names
  your case**; then waive it (`quality.waive`, or the rule's own key) with evidence a
  reader can check: the part, the datasheet line, the measured number. If your case is
  not on the list, it is a fix — and if you believe the list is missing a real case, that
  is a change to this file (see "Adding a learning"), not a waiver.

Never a reason, for any rule: "the autorouter did it", "there was no room", "it is only
just over", "it worked on the last board", "it is a prototype". The first two are
placement problems to solve in the generator; the rest are how respins happen.

Manual rules have the same two kinds, marked in the list below: **must hold** rules are
signed only by showing the thing is true; **decide** rules may also be signed as a
decision not to do it, with the reason and what is relied on instead.

Everything a board declares lives in its generator, under `BOARD_NOTES["quality"]`:

```python
"quality": {
    # A1 -- every supply net: where it enters, where it goes, how many amps
    "power_paths": [
        {"net": "+24V", "from": "J1.2", "to": ["U5.5", "J7.2"], "amps": 3.0},
        {"net": "+3V3", "from": "U6.5", "to": "U1.19", "amps": 0.25},
    ],
    "temp_rise_c": 10, "copper_oz": 1, "inner_oz": 0.5,          # defaults
    "max_drop_pct": 2,                     # default; or "max_drop_mv", also per path
    "not_power": ["+VREF_SENSE"],          # looks like a rail by name, carries no current
    # A2 -- how close a bypass capacitor must be, and the pins that need none
    "decoupling": {"ic_mm": 5.0, "connector_mm": 25.0,
                   "exempt": {"U3.4": "open-drain output pin named V+, not a supply"}},
    # A3 -- a pair that is deliberately not length-matched
    "unmatched_ok": {"CAN_P": "500 kbit/s over 40 mm: a bit is 2 ns/mm away from mattering"},
    # A4 -- where each multi-pin part's pinout was read; key by ref, value or footprint
    "pinouts": {"CH32V307WCU6": "WCH CH32V307 DS v2.3 table 2-1 (QFN68), top view",
                "J1": "JST XH B4B-XH-A drawing, pin 1 at the polarising tab, top view"},
    # M-rules -- the evidence, per rule id
    "manual": {"M1": "J1 <-> harness XH_PINOUT (elec/harness.py), both crimped 1:1; ..."},
    # a FAIL that does not apply here: "<rule>:<subject>" -> why
    "waive": {"A2:U7.3": "U7 is the LDO; C12 on its output is 6.1 mm away across the tab"},
}
```

---

## Automated checks

### A1 — Supply paths carry their current, with no choke point

**Rule.** Every net that carries supply current declares its path (`power_paths`: entry
pad, load pads, amps). Along the best copper path between them, the narrowest point must
be wide enough for that current (IPC-2221 at the declared temperature rise; inner layers
need about twice the width of outer ones), **and** the track resistance along the path
must not drop more than `max_drop_pct` (2 %) of the rail the net's name states — or
`max_drop_mv`, per board or per path, where that is the wrong measure (50 mV when the name
states no voltage). A net that looks like a
rail by name and declares nothing **fails** — so a new rail cannot be added without
stating its current. A net whose name says it is not connected (`_NC`) is not a rail.

**Why.** A supply is as good as its narrowest millimetre. Autorouters lay every net at
the default width, and a post-route repair can join two halves of a rail with a hairline:
one board's analog rail was "0 unconnected" through 62 mm of 0.127 mm track, 0.6 Ω to its
converters. Another's trunk carried half the fleet's current through 0.25 mm.

**How it is checked.** The net's copper becomes a graph (track segments by width, vias as
their barrel's equivalent width, pours as unlimited) and the widest-bottleneck path from
`from` to each `to` is found. The report names the narrowest point and the pad it is
nearest. The drop is the least-resistance path's track resistance (pours counted as zero).
Parallel vias and parallel tracks are not summed — add them up yourself and waive with
the arithmetic if that is the design.
A path may say `"split": true` when its `amps` is what the listed pads draw **together**
(the supply pins of one IC): the drop is then solved on the whole copper network with the
current shared equally between those pads, so a trunk is charged with what is downstream
of it and no more. The narrowest-point check still uses the full figure.

**Fix.** Size the net in `net_widths`, or lay the path as declared copper (`tracks`), or
pour it. Then check **M3** (the return path).

**How strict.** **Hard:** a rail with no declared path (declare it, or list the net in `not_power` if
it carries no current); a path whose ends are not pads on the net; a path with no copper.
**Soft:** the width and the drop. *Break it when:* (a) the narrow point is a neck no
longer than about 2 mm between wide copper — IPC-2221 is a long-trace figure and a short
neck sheds its heat into the copper either side: waive with the neck's length; (b) the
current is shared by parallel tracks or vias the script does not sum: waive with the
arithmetic; (c) the current is a brief peak, not continuous: declare the continuous
figure and say what the peak is; (d) the load tolerates the drop: set `max_drop_mv` on
that path with the load's minimum voltage. *Do not break it* for a rail feeding a
regulator's input near its dropout, an analog reference, or anything whose current you
have not actually added up (**M33**).

### A2 — Every supply pin has a capacitor beside it

**Rule.** Each IC pin (`U*`) on a supply net has a capacitor to ground on that net within
`ic_mm` (5 mm). Each connector pin (`J*`, `P*`) on a supply net — every power input and
output of the board — has one within `connector_mm` (25 mm). A rail that only passes
between connectors, with no part on it, is reported and not failed.

**Why.** A load that steps its current pulls the rail down for as long as the inductance
between it and the nearest charge lasts. The capacitor is that charge; a capacitor on the
far side of the board is a capacitor on a different rail. Power entering or leaving the
board arrives down a cable, which is the worst inductance in the system.

**Fix.** Beside the pin, on the pin's own layer, with the capacitor's ground via right
at its pad: the loop through the via is part of the distance.

**How strict.** **Soft**, with the longest list of any rule — because it is the one most often waived wrongly.

**Deciding a failure: fix it, or exempt it?** The default is to FIX: move or add the
capacitor. Work down this list and stop at the first line that matches the pin.

1. *The part's datasheet names a capacitor for this pin* (a value, "as close as
   possible", a layout figure) → **fix**, and use the datasheet's value. No exemption.
2. *The pin is an analog supply, a reference, a PLL/oscillator supply, or a regulator's
   input, output or internal-regulator pin (VCAP, VDDA, VREF, AVDD, DVDD-out)* → **fix**.
   These are the pins where distance matters most.
3. *The part switches fast or draws current in steps: an MCU, FPGA, PHY, hub, codec's
   digital supply, motor or LED driver, radio, anything clocked above about 1 MHz* →
   **fix**. Two supply pins side by side may share one capacitor (the rule measures
   distance, so that already passes).
4. *A connector that brings power in from, or sends it out down, a cable to a load* →
   **fix** (within `connector_mm`), and see **M16** for damping.
5. *The part is slow and small — a single logic gate, an analog switch, a low-speed
   op-amp or comparator, a sensor sampled at kHz — AND its datasheet asks only for "a
   bypass capacitor", AND one is on the same rail within about 10 mm with a short, wide
   connection* → **exempt** that pin, naming the capacitor and the distance.
6. *The pin is named like a supply but is not one* (an open-drain output called `V+`, a
   sense input, an enable tied to the rail) → **exempt**, saying what the pin is.
7. *The board has an unbroken power plane and ground plane as adjacent layers under the
   part, and the pin drops into them with its own via* → the limit may be raised for
   that board (`ic_mm`, to 8) with that sentence as the reason. Not on a two-layer board,
   and not for the pins in lines 1 and 2.

Anything not on lines 5–7 is a fix. "The router put it there", "no room" and "it is only
0.4 mm over" are not reasons: the first two are placement problems to solve in the
generator, and a pin 0.4 mm over is fixed by moving one part 0.4 mm.

An exemption is written per pin, with evidence a reader can check:

```python
"decoupling": {"exempt": {
    "U12.5": "SN74LVC1G3157 analog switch, static select line; datasheet asks only for a "
             "bypass cap; C41 on +3V3 at 7.2 mm over a 0.5 mm track",
}}
```

**How it is checked.** Pad-centre to capacitor-pad distance, capacitors counted only if
their other pad is on a ground net. An IC is judged pin by pin, a connector once per net.
It checks **presence and distance, not value** — values and ratings are **M4**. A big
package with supply pins on all four sides needs a capacitor per side, not one per rail:
that is what a row of failures on one IC is telling you.

### A3 — Pairs are declared, matched, and stay a pair

**Rule.** Any two nets named as a differential pair (`X_DP`/`X_DM`, `X_P`/`X_N`,
`XD+`/`XD-`) are in a `match` group with a skew budget, `same_layer`, and a via budget —
or `unmatched_ok` says why not. Every `match` group must then pass: skew inside budget,
one layer set, vias inside budget.

**Why.** Skew between the two halves of a pair turns signal into common-mode noise; a
pair split across layers no longer has the impedance the stack-up was designed for, and
an autorouter does exactly that when the direct path is congested. A group with an unmet
budget on an unrouted net measures incompleteness, not mismatch — route first.

**How it is checked.** `pcbflow/verify.py` on the declared groups, plus a name scan for
pairs nobody declared. It cannot find a high-speed **bus** by name — that is **M6**.

**How strict.** **Hard:** a declared group that fails. The budget is yours — if it was wrong, correct the
budget and say why in the group's `why`; do not waive your own declaration.
**Soft:** whether a named pair needs matching at all. *Break it* (`unmatched_ok`) *when*
the skew you could possibly have is a small fraction of a bit time — write the
arithmetic (CAN at 1 Mbit/s over 40 mm; full-speed USB over 20 mm). *Do not break it*
for high-speed USB, any pair over about 10 Mbit/s, or a pair that runs more than a few
centimetres.

### A4 — Pinouts: every pin exists, and every multi-pin part cites its source

**Rule.** Every pin the netlist connects exists as a pad on the footprint. Every part
with three or more pads cites, in `quality.pinouts`, the document its pinout was read
from. One citation covers every instance of the same part.

**Why.** A mirrored or shifted pinout passes ERC, DRC and every other check in this
file: the netlist is self-consistent and wrong. The classic causes are a bottom-view
drawing read as top view, a connector numbered from the mating face, a package variant
with a different pin order, and a footprint whose pad numbers do not follow the
datasheet's. No script can read a datasheet, so the script enforces the next best thing:
that someone did, and wrote down which page.

**How it is checked.** Netlist pins against footprint pads; then the citation. The
reading itself is the designer's — do it pin by pin, against the maker's own document,
and for a connector decide explicitly which face the drawing shows. **M28** is the same
check for the exact part variant.

**How strict.** **Hard**, all of it. A pin with no pad is a broken connection, and a pinout is cited or
it has not been checked. There is no board on which "I did not look it up" is correct.

### A5 — The netlist says what the designer meant

**Rule.** No named net reaches only one pad, and no two nets differ only in case or
punctuation (`CAN_H` / `CANH`).

**Why.** A mistyped label is a wire that looks connected in the source and is not on the
board; ERC-clean and DRC-clean, because both ends are "legally" unconnected.

**How it is checked.** Pad count per named net (auto-named and `_NC` nets excepted;
deliberate ones go in `quality.single_pin_ok`), and net names folded to letters and
digits.

**How strict.** **Hard:** two nets that differ only in case or punctuation — rename one.
**Soft:** a single-pad net. *Break it* (`single_pin_ok`) *when* the pin is deliberately
brought to nothing and the name is its documentation (a spare GPIO, a test signal with no
pad yet). Better still, name it `…_NC`, which the rule already accepts.

### A6 — USB-C: each CC pin has its own resistor

**Rule.** On every USB-C receptacle, CC1 and CC2 are different nets, and each has its own
5.1 kΩ 1 % to ground (a device), or a pull-up or a controller IC (a source / PD port).

**Why.** A shared resistor works with a plain cable and fails with an e-marked one: the
cable's Ra parallels it, the source sees an audio accessory and supplies nothing. A
shipped single-board computer needed a respin for exactly this.

**How it is checked.** The nets on pads A5 and B5 and the resistors on them.

**How strict.** **Hard:** CC1 and CC2 on one net; a resistor to ground that is not 5.1 kΩ; two on one
pin. **Soft:** a CC pin with nothing on it. *Break it when* the port is a pure
pass-through whose CC lines are wired straight to another USB-C receptacle (then the far
end terminates them — say which connector), or the receptacle is used for power only
from a fixed supply that is always on. *Do not break it* for any port a standard USB-C
source or host will be plugged into: without the resistor it supplies nothing.

### A7 — I2C buses have one pair of pull-ups

**Rule.** Every net named `SDA` / `SCL` has a pull-up to a supply on this board, and the
parallel value is at least 1 kΩ (3 mA sink at 3.3 V). A bus pulled up on another board
waives it, saying where.

**Why.** No pull-up is a dead bus; a pull-up on every board and module in parallel is more
than the pins can sink. Both are common, and neither shows until bring-up. The upper
bound (rise time against bus capacitance) is **M20**.

**How it is checked.** Resistors from the net to a supply net, values read from the BOM
value text.

**How strict.** **Soft.** *Break it when* the bus's one pair of pull-ups is on another board — name the
board and the resistors, and confirm no third board adds its own; or the IC's internal
pull-ups are used deliberately on a short, slow bus — say which register enables them.
*Do not break* the 1 kΩ floor unless every device on the bus is rated for the larger sink
current (Fast-mode Plus, 20 mA), with the datasheet lines.

### A8 — Exposed pads are connected and have vias

**Rule.** Every footprint with an exposed pad has that pad on a net, with at least one via
inside it.

**Why.** The pad is usually the part's main ground and its only heat path; unconnected, a
regulator overheats or an RF/USB part has no ground. Paste coverage and the via count the
datasheet asks for are **M25**.

**How it is checked.** The largest SMD pad of any footprint named `…-1EP…`, its net, and
the vias on that net inside it.

**How strict.** **Soft.** *Break it when* the datasheet says the pad may or must be left unconnected
(cite it), or the part dissipates so little that the datasheet's own thermal figures put
it far inside its limit without vias (write the milliwatts) and the pad is still
connected to its net by copper on its own layer. *Do not break it* for a regulator, a
driver, a PHY or any part whose exposed pad is its only ground.

### A9 — Crystals sit beside the pins they drive

**Rule.** Each crystal pad is within `crystal_mm` (10 mm) of the oscillator pin it
connects to.

**Why.** Placement by looks puts the crystal where it is tidy. The trace is then stray
load capacitance (the frequency is off), an antenna, and a pickup for whatever runs beside
it; marginal oscillators fail to start. The load-capacitor arithmetic is **M24**.

**How it is checked.** Pad-to-pin distance on each crystal net that reaches an IC
directly. A via on a crystal net is reported as a note: worth removing, not worth a
re-route on its own at the frequencies these boards use.

**How strict.** **Soft**, narrowly. *Break it when* the part is not a bare crystal but an oscillator
module with a driven output (then it is a clock trace: series resistor at the module,
**M20**), or the maker's own layout guide for this part shows a longer run (cite the
figure). *Do not break it* for a bare crystal because of placement convenience: the load
capacitance and start-up margin were computed for a short trace.

### A10 — A USB device presents no more than 10 µF on VBUS

**Rule.** On a USB-C port wired as a device (a resistor to ground on CC), the capacitors
directly on the connector's VBUS net total no more than 10 µF. Under 1 µF is reported as
a note, not a failure.

**Why.** The USB 2.0 specification (section 7.2.4.1, inrush) limits what a device may
connect at plug-in: more than 10 µF can trip the host's over-current protection or sag
the hub's rail. Bulk capacitance belongs behind a load switch or a soft-started
regulator. The 1 µF lower figure is common guidance; confirm it against the
specification before treating it as a limit.

**How it is checked.** The sum of capacitor values with one pad on the receptacle's VBUS
net and the other on ground.

**How strict.** **Hard:** a capacitor whose value cannot be read (write it parseably).
**Soft:** the 10 µF limit. *Break it when* the port is only ever fed by a dedicated
supply, never a host or hub (say so — and it then should not be called a USB port), or
the excess sits behind a load switch, soft-start or series element that the script has
counted as "directly on VBUS" wrongly (name the element).

### A11 — One value, one spelling

**Rule.** No resistance or capacitance appears on a board under two spellings in the same
package (`100n` and `0.1uF`; `4.7k` and `4k7`).

**Why.** Two spellings are two BOM lines: two feeders at the assembler, two part numbers
to source, and two parts that can be changed independently when they were meant to be
one. It is also the cheapest sign that a value was typed rather than derived.

**How it is checked.** Values parsed to a number and grouped by footprint. A qualifier
after the value (`10k 0.1%`, `10uF/16V`) makes it a different part on purpose; whether it
needs to be one is **M42**.

**How strict.** **Hard.** Spell it one way. (A different tolerance or rating is not a different
spelling: write it as a qualifier after the value.)

### A12 — The board is inside what the fab says it can make

**Rule.** The finished board's own copper, holes and silk text — measured, not read from
its design-rule file — are inside the fab's published minimums: narrowest track, smallest
via hole and its ring, plated-hole annular ring, smallest non-plated hole, hole-to-hole
spacing (via to via, and a pad hole to anything), hole edge to another net's track, SMD
pad-to-pad gap, silk text height and stroke. No via hole sits inside an SMD pad unless the
order is for filled-and-capped vias (`quality.fab` `via_in_pad`).
Excepted: an exposed pad (vias belong in it, **A8**), a pad with no paste (a test pad), and
any land of 4 mm² or more — a 0.3 mm barrel through a 1.6 mm board holds about a quarter of
the paste printed on 4 mm², and half of what a small crystal or 0603 pad gets. A large land
is exempt only for as many barrels as it can feed: the open vias in it, added up, may hold
no more than a quarter of the paste printed on it (area × 0.12 mm). Two 0.4 mm vias in a
1.3 × 4.5 connector land are over half of it — put the vias beside the land instead.

**Why.** The numbers a board is routed to are typed into its rule file by someone, and
DRC then proves the board against *those*. On the first boards this was run on, the rule
file was looser than the fab's page in five places (pad-hole spacing 0.25 against 0.45,
plated hole to track 0.25 against 0.28, silk height 0.8 against 1.0, silk stroke, SMD
pad gap) and every label on every board was under the height the fab calls legible. A
clean DRC said nothing about any of it.

**How it is checked.** The table `FAB` in `quality.py` holds one fab's standard-service
numbers with the date its page was read; `quality.fab` overrides any of them for a board
ordered elsewhere or on a costlier option (say where the number was read). Each check
reports the worst place and how many places fail. Copper-to-edge and track-to-track
spacing are left to DRC, whose loaded values the pipeline sets tighter than the fab's.
A via drilled smaller than the fab's no-surcharge size is a note, so the order form is
filled in to match.

**How strict.** **Hard:** rings, holes, track width, pad gaps — the fab either makes it or
does not, and a board outside the table comes back as an engineering query or a scrap
panel. If the order really is on a finer process, state that process's numbers in
`quality.fab`; that is a declaration, not a waiver. **Soft:** silk height and stroke.

### A15 — A signal's return does not have to go round a cut in the plane

**Rule.** A signal track that runs over a ground pour on another layer does not straddle a
cut in that pour longer than `return_slot` (default 5.0 mm). A cut is ground copper,
then none, then ground copper again, measured along the track. A track that simply runs
off the edge of the pour is not a cut and is not counted.

**Why.** Return current does not take the shortest path; above a few tens of kHz it takes
the path of least inductance, which is the copper directly under the signal. Every track
routed on the plane layer cuts that copper for its whole length, so a plane layer that is
also a routing layer is a plane with slots in it — and on a two-layer board it always is.
Where a signal crosses a slot, its return has to travel to the end of the slot and back,
and the loop that opens up is the area between the two paths. That loop radiates, and it
receives; it is the usual reason a board passes on the bench and fails in a case next to
a motor. None of it shows in DRC, in a netlist, or in a connectivity check: the copper is
all where the schematic says it should be.

The board this came from has one B.Cu ground pour and 455.89 mm of B.Cu signal copper cut
through it. The plane under the power section turned out to be solid — which is the thing
that mattered and had only ever been asserted — and the widest cut any signal straddles is
3.03 mm, two tracks side by side. Both of those are now numbers instead of opinions.

**How it is checked.** Every non-ground track longer than 1 mm is sampled every 0.25 mm
and each sample tested against the filled ground polygons on every other copper layer.
Only straddled gaps count. `quality.return_slot` sets the limit; `quality.return_slot_ok`
lists nets exempted, and an entry is expected to say what carries that signal's return
instead. A board with no ground pour gets a note saying so, and no claim.

**How strict.** **Soft.** A long cut is usually a routing accident and reroutes cheaply,
but there are honest reasons for one — a deliberately split plane between domains, a
signal whose return is carried by its own pair rather than the plane. Those are written
down, not waived silently. **A15 measures for every signal what M6 asks about by hand for
fast buses**; M6 keeps the part A15 cannot measure, which is whether the edge rate makes
the loop matter.
*Break it when:* (a) the fab's own page for the service being ordered gives a smaller
figure (put it in `quality.fab`); (b) the label has no site at the legible size anywhere
in reach and the choice is a small label or none — `kicad_silk` then places it at 0.8 mm
and says so; waive naming those labels, and only if what they say is not needed to
assemble or wire the board correctly (a board name, a test-pad name). *Do not break it*
for a polarity mark, a pin-1 mark, or the only statement of a connector's pin order: if
that does not fit at the legible size, make room.


### A14 — No via drinks a solder joint

**Rule.** A via whose centre falls inside a pasted SMD land does not have a barrel that
can hold half or more of the solder paste printed over that land. Measured as volume: the
barrel is pi x (drill/2)^2 x `board_thickness`, the deposit is the land's area times
`stencil_foil`.

**Why.** An open plated barrel under a solder joint is a capillary, and reflow is exactly
the condition it wants. The solder does not vanish -- it ends up on the far side of the
board, which is no help to the joint it left. IPC-7093 says a via in a land is filled and
capped, or is not there.

Two things made this invisible until the exported files were read. First, the board model
says the vias are **tented**: KiCad reports `IsOnLayer(F_Mask)` false for every via inside
a pad, because it adds no mask opening of its *own*. The pad's aperture is already open
over it. On the board this came from, F.Mask exported as 208 dark flashes -- one per pad
on the layer -- and not one clear flash anywhere, so there is no mask island inside any
aperture and every one of those barrels is open under the paste. Second, as an **area**
ratio a 0.3 mm barrel in an 0603 land reads 8 % of the pad and looks like nothing. As a
volume it is 0.113 mm3 against a 0.103 mm3 deposit: **110 %**. Four such vias survived a
quality pass that was looking for them.

**How it is checked.** Every via centre is tested against every SMD pad that opens the
paste; a pad with no paste (a bare test pad) has no joint to starve and is skipped.
`quality.stencil_foil` and `quality.board_thickness` set the two constants;
`quality.via_in_land_ok` lists lands exempted, which is where an order placed with the
vias filled and capped is declared. `cadkit/pcbflow/unwick.py` runs after routing and
moves what it can -- it insists on a mask dam between via and land, and refuses a move
longer than `via_land_move_max` (1.5 mm), because a ground return that walks 4 mm to
avoid wicking is the worse board.

**How strict.** **Hard** at half the deposit or more: that is a joint the assembler cannot
make reliably, and no board has a good reason to keep one. Under half it is reported with
its worst case and passes. The honest escape is not a waiver but a declaration -- order
the vias filled and capped and say so in `via_in_land_ok`. **Tenting is not an escape**,
for the reason above.

---

### A13 — Every pin and every channel is accounted for

**Rule.** The board declares which pins it leaves unconnected, and for each repeated
structure how many distinct nets its pins are on. The pass fails on any difference, in
either direction.

**Why.** A netlist that is wrong but internally consistent passes everything else. Two
channels wired to the same four driver outputs are simply fewer nets: it routes clean,
DRC is clean, and every rule above is satisfied, because those all ask whether the board
agrees with the netlist. Only a number the DESIGN means, written beside the board, can
disagree with it. (A loop that read an index left over from the loop above did exactly
this: 24 return nets where 32 were meant, eight driver outputs idle, nothing red.)

**How it is checked.** On the routed board:

* *Unconnected pins.* Every numbered pad of a part with three or more pins that has no
  net (or is alone on its net) must be named in `quality.unconnected`, with a reason; and
  every pin named there must really be unconnected. Keys are `"REF.PIN"` patterns
  (`"J*.MP"`, `"U14.5"`) with the reason as the value, or a part pattern with a pin list:
  `"U6": {"pins": "7 8 9 12", "why": "spare GPIO, left floating as inputs"}`.
* *Groups.* `quality.net_groups` is a list of
  `{"name": ..., "pins": ["PD*.2"], "nets": 20, "each": 1}`: the pins the patterns match
  must sit on exactly `nets` distinct nets, with exactly `each` of them on every net (leave
  `each` out when the nets are meant to differ), and `pins_count` pins must match when it
  is given. A group can instead name its NETS:
  `{"name": ..., "nets_like": "ULPI_D[0-7]", "count": 8, "pads": 2}` asks for exactly
  `count` nets whose whole name matches, each with exactly `pads` pads on it (both ends
  present, nothing extra). Declare one for every structure that is repeated: sensor channels, driver
  outputs, LED zones, the ways of each connector, the lanes of a bus, chip selects.

Write both from the DESIGN (the datasheet's channel count, the number of strings, frets,
motors), not by copying what the board happens to have. A declaration read off the board
proves nothing.

**How strict.** **Hard**, all of it. There is no waiver: if the board is wrong the generator is
fixed, and if the declaration is wrong it is corrected to what the design means. A board
with nothing repeated says so with an empty `net_groups` list; leaving the key out fails.

## Manual checks

Sign each in `quality["manual"]` with what you checked against. If a rule does not apply
to the board, sign it with the reason ("no external connectors"). M1–M12 apply to
nearly every board; M13 onward are each about one kind of circuit. **The script marks a
rule `n/a` itself when the board has none of the parts that circuit needs** (no inductor:
no switching-regulator rules; no IC: no strap pins, op-amps or errata; no crystal, no
USB, no transistor, no switch, likewise) — the table is `NOT_APPLICABLE` in
`quality.py`. Anything it cannot tell from the parts list stays `OPEN` for you. Thresholds quoted here are starting points
from published guidance: where a part's own datasheet says otherwise, the datasheet wins.

**Which manual rules must hold, and which are decisions.**

| kind | rules | how to sign |
|---|---|---|
| **must hold** | M1 mating connectors, M2 polarity, M4 capacitor ratings, M5 absolute ratings, M7 application circuit, M8 config pins defined, M14 inductor saturation, M15 regulator stability, M18 back-powering, M19 gate drive, M24 crystal load, M26 signal direction, M27 strap pins, M28 exact-part pinout, M32 connector series, M33 power budget, M34 levels and polarities, M37 files match the board, M39 unused pins | Only by showing it is true: the two things compared and the document read. If it is not true, the board changes. |
| **decide** | M3 return path, M6 bus matching, M9 programming and probing, M10 protection, M11 fit, M12 order, M13 regulator layout, M16 hot-plug, M17 ferrites, M20 termination, M21 converter ground, M22 op-amp limits, M23 USB details, M25 thermal pads, M29 fab capability, M30 assembly tier, M31 markings, M35 errata, M36 output limiting, M38 stress and access, M40 design record, M41 debounce, M42 lifecycle | By showing it is done — or by recording the decision not to: what was left out, why this board does not need it, and what is relied on instead ("no TVS: the connector is inside the enclosure and mates only to our own harness; the trunk's TVS is on the supply board"). A decision is not "skipped". |

A **decide** rule is still broken only for a reason about THIS board's use: where it
lives, what it plugs into, how fast it runs, how much it dissipates. Cost, time and board
area are reasons to choose a different part or placement, not to drop protection or
access the bring-up will need.

- **M1 — Mating connectors agree pin for pin.** For every cable and board-to-board joint,
  write out pin N at one end and what it reaches at the other, viewed from each
  connector's own mating face. Check the cable type (straight vs crossed, ribbon pin 1
  stripe), that an unshrouded or unkeyed connector cannot be plugged reversed or offset
  without marking, and that the pin order is held in ONE shared constant, not typed twice.
  **Nets follow the footprint's own maker's drawing, and a mating part's numbering is
  translated explicitly.** Where the other half is somebody else's product (a power
  supply's plug, a module's header, a computer's port, a cable with its own contact
  order), its pin numbers are NOT the numbers on our pads: two makers of the same
  interface number the same contacts differently. Read both drawings, write the table
  physical position -> our pad -> net at the connector, and say which document each
  column came from. "Pin 1 +V" copied from the mating part's sheet onto our pad 1 is
  the fault this line exists for.
- **M2 — Polarised two-pad parts face the right way.** Diodes, LEDs, TVS, electrolytic and
  tantalum capacitors: the cathode/negative pin in the generator is the pad the footprint
  numbers as that pin (KiCad diodes: pad 1 = K), and the part's reel orientation is in the
  rotation check for the fab.
  A placement frame fitted by pad NUMBER is not evidence of orientation: the fab's library
  may number the same lands the other way (or split a terminal into two lands), and the
  fit then turns the part to suit the numbers. For every polarised part record which
  terminal the fab's footprint calls pin 1, from its library or from the mark its
  previewer draws, against the terminal our pad 1 is.
- **M3 — The return path matches the supply path.** For each `power_paths` entry, the
  ground return from the load back to the entry is a pour or copper at least as wide, and
  does not neck through a single via or a slot in the plane. High-current returns do not
  share a narrow path with a sensitive reference.
- **M4 — Capacitor values and ratings suit the load.** Each regulator has the input and
  output capacitance its datasheet requires (and the ESR it requires). Each load that
  steps current (motor driver, LED string, radio, relay) has bulk capacitance sized for
  the step. Voltage ratings carry margin for DC bias: a ceramic at its rated voltage has
  lost most of its capacitance — use ≥ 2× the rail.
- **M5 — Nothing is run past its ratings.** Every part on a rail survives that rail's
  WORST case — a fresh battery, a supply's tolerance, an inductive spike, a hot-plug —
  with margin. Check absolute-maximum voltage on every pin a rail can reach, GPIO levels
  between domains. (Heat is **M25**.)
- **M6 — High-speed buses are matched and have an unbroken reference.** Clocked parallel
  buses and anything above ~50 MHz or with fast edges (ULPI, SDIO, RGMII, SPI at tens of
  MHz) are in `match` groups with a budget derived from the bit time. Each runs over a
  continuous plane: **A15** measures every signal's return for cuts in the pour, so what
  is left here is the judgement it cannot make -- whether this bus's edge rate makes the
  loop matter, and whether a layer change has a ground via beside it.
- **M7 — Each IC's circuit matches its datasheet application.** Feedback dividers give the
  intended voltage, inductor and compensation values are in the recommended range, enable
  and mode pins are tied (not floating), crystals have the load capacitors their CL
  requires, exposed pads are connected as the datasheet says.
- **M8 — Every configuration pin has a defined state.** Reset, boot-mode, address and
  strap pins have pull-ups or pull-downs and come up in the state you want before
  firmware runs; unused inputs are not floating; open-drain lines have a pull-up.
- **M9 — The board can be programmed and probed.** Debug/programming pads, reset and boot
  access on every MCU; a labelled test pad on each rail and on each signal the bring-up
  guide tells someone to probe; ground somewhere a clip can reach.
- **M10 — External connections are protected.** ESD/TVS on every pin a hand or a long
  cable reaches, placed at the connector — nearer its pins than any capacitor or ferrite
  on the same line; reverse-polarity and over-current protection on the power input; nothing
  outside the enclosure can back-feed a rail.
- **M11 — It fits and can be assembled.** The CAD check passes on the mated envelope
  (`solid(mated=True)`); every connector can be plugged with the board installed; tails
  clear along the install stroke; mounting holes have laminate round them and no copper
  or part under the screw head, washer or standoff — measured hardware, both faces, which
  differ; parts the fab cannot place are zero.
- **M12 — The order is right.** Every part number read off its listing and in stock
  today, with what it mates to (lifecycle and alternates are **M42**); rotations checked in the fab's previewer for every
  polarised and multi-pin part; board name and revision in silk; order-form settings
  (mask colour, mark removal, rail edges) written down.
- **M13 — Switching regulators are laid out as the datasheet draws them.** The input
  capacitor sits at VIN/PGND on the part's own layer with no via in that loop (the "hot
  loop"); the switch node is short and no bigger than it must be, never a heatsink; the
  feedback divider is AT the FB pin and its trace runs nowhere near the switch node or
  under the inductor; the bootstrap and VCC capacitors are at their pins. Compare the
  placed board against the datasheet's layout figure, side by side.
- **M14 — Inductors do not saturate.** Peak current = load + half the ripple (ripple is
  usually 20–40 % of load); the inductor's saturation current exceeds that with margin,
  ideally exceeds the regulator's current limit. Read how the maker defines Isat (20 %,
  30 % inductance drop): the numbers are not comparable across makers.
- **M15 — Regulators are stable with the capacitors actually fitted, and have headroom.**
  The output capacitor's ESR is inside the range the datasheet's stability section gives
  (1117-family parts need ESR and can oscillate on ceramics alone; "ceramic-stable" parts
  have a maximum ESR and a minimum EFFECTIVE capacitance). Effective capacitance is read
  off the maker's DC-bias curve at the rail voltage — a small-package ceramic near its
  rated voltage can be a fraction of its marking. Input minimum minus output exceeds the
  dropout at full load.
- **M16 — A hot-plugged supply input survives the plug.** A live cable plugged into
  low-ESR ceramics rings toward twice the supply voltage. Every cable-fed input has
  damping (an electrolytic or polymer in parallel, or a series-R ceramic) and/or a TVS,
  and 2 × the supply is under the lowest absolute maximum on that net. Inrush through any
  switch or fuse is inside its rating.
- **M17 — Ferrite-bead filters are damped and not saturated.** A bead and a ceramic make a
  resonant peak that AMPLIFIES noise below the bead's crossover: compute it, and add
  damping (a larger capacitor with series resistance) if it lands in a band that matters.
  The bead's rated current is well above the load: its impedance falls with DC bias.
- **M18 — No pin is driven while its IC is unpowered.** For every signal between two
  power domains or two separately powered boards: if one side can be up while the other
  is down, a series resistor, a powered-off-tolerant buffer or guaranteed sequencing stops
  the signal back-powering the dead rail through the pin's protection diode.
- **M19 — Each MOSFET is fully on at the voltage that drives it, and off in reset.** The
  datasheet gives Rds(on) AT or BELOW the gate drive actually available (Vgs(th) is the
  250 µA point, not "on"). Every gate driven by a pin that floats in reset has a
  pull-down (or pull-up, for a P-channel) so the load is off until firmware says so —
  also when the driving cable is unplugged. The gate never sees more than its rated Vgs
  (a 24 V signal on a ±20 V gate needs a clamp or divider), and has a series resistor
  where the driver or the layout could ring it.
- **M20 — Buses are terminated and pulled once, at the right places.** I2C pull-up value
  is inside both bounds: at least (VDD − 0.4 V) / 3 mA, at most rise time / (0.8473 × bus
  capacitance). CAN has exactly two 120 Ω terminations, at the two ends of the bus, and
  stubs are short. Fast clocks (MCLK, BCLK, SCK at MHz and up) have a series resistor at
  the DRIVER pin if the trace is long enough to ring.
- **M21 — Converters and their analog inputs have a quiet ground.** An ADC/DAC/codec's
  analog and digital ground pins join at the part on one unbroken plane (no split under
  it, unless its datasheet says otherwise). Analog and reference traces run over solid
  ground, away from inductors, switch nodes and clocks, crossing them at right angles if
  at all. The reference pin's capacitor is at the pin.
- **M22 — Every op-amp section is inside its limits.** Unused sections are wired as a
  follower with the input at mid-supply, never left floating and never with the inputs
  shorted together. The signal stays inside the input common-mode range and the output
  swing AT the load (rail-to-rail parts still distort near the rails). An output that
  drives a cable, a filter capacitor or an ADC's sampling capacitor has a series
  isolation resistor.
- **M23 — USB is complete.** The ESD clamp is at the connector, before anything else. The
  pair has few vias (at most four per line for USB 2.0, the same number on each half,
  a ground via beside each layer change) and no stubs (a through-hole receptacle entered
  so its pin is not one). The D+ pull-up and any series resistors are fitted or internal, as the PHY's
  datasheet says, and any series resistors sit at the IC. The clock meets USB's accuracy (±0.25 % full speed; far tighter for high
  speed). VBUS is not fed backwards from a self-powered board.
- **M24 — Crystals have the load capacitors their CL requires.** C1 = C2 = 2 × (CL −
  Cstray), Cstray 2–5 pF; the oscillator's drive/gain margin covers the crystal's ESR (the
  MCU maker's oscillator note has the test). Traces are short and symmetric, with nothing
  routed under or beside them — on ANY layer — and ground around. The crystal sits
  between the IC and its load capacitors, not beyond them; the load capacitors are
  C0G/NP0; a powered oscillator has its own bypass capacitor.
- **M25 — Thermal pads carry the heat they must.** Each exposed pad is on the net the
  datasheet names (not always ground) and has the via count and
  size the datasheet asks for, solid (not thermal-relief) connection, and paste in a
  windowpane (roughly 50–80 % coverage) rather than one full opening. Each regulator's and
  driver's junction temperature at full load is computed and under its limit. A tab or
  heatsink is on the net the datasheet says the tab is (often NOT ground), and is not
  left floating by accident.
- **M26 — Signals named by direction land on the opposite direction.** For every UART,
  SPI and similar link: a net named TX reaches exactly one transmitter and the far end's
  RECEIVER. Name nets by function and direction (`MCU_TX_TO_PI`), then read both ends'
  pin functions in their datasheets.
- **M27 — Nothing else loads a strap, boot or debug pin.** List every part on each
  boot-strap, reset and debug net. An LED, a pull-up to the wrong rail or a peripheral's
  output on a strap pin forces the wrong mode at reset; a debug pin reused as GPIO can
  lock the programmer out. The debug header has those pins to itself.
- **M28 — The pinout is that of the EXACT part being placed.** Same package, different
  maker, different pin order: SOT-23 transistors and SOT-223 / SOT-89 regulators vary
  (some regulators' tab is the OUTPUT, not ground — check what copper it sits on). Read
  the datasheet of the specific part number in the BOM, and re-read it for any
  substitution the fab proposes.
- **M29 — The board is buildable by THIS fab.** **A12** measures the tracks, holes, rings,
  pad gaps and silk against the fab's table; this rule is the rest. The table's numbers
  are current (re-read the fab's capability page if its date is more than a few months
  old, and for the service actually being ordered: layer count, copper weight, finish).
  Small two-pad
  parts have matching copper on both pads (thermal spokes on a pad that sits in a pour),
  or they tombstone.
- **M30 — The assembly order has no surprises.** Every placed part is one the service can
  place in the chosen tier (some parts force a costlier tier or a minimum board size);
  the count of extra-fee part lines is known; the board is inside the service's size
  limits or panelised with rails, and its size has been checked against the fab's price
  breaks (a millimetre over one costs a tier); the option to review the production files before build
  is ticked. Every row of the assembly BOM names the fab's own part number -- none is left
  for the order page to match (`pcbflow/fab_package.py` refuses to write a package with an
  uncoded row) -- each code was READ on the fab's catalogue for its package, value, voltage,
  dielectric and tolerance on the rail it sits on, and on the order page every row shows a
  selected part and none shows quantity 0. The placement file is in the FAB's footprint
  frames (`pcbflow/fab_frames.py` measures each part's angle and origin from the fab's
  library pads): every part in the package's ROTATION-CHECK.txt "not corrected" list has
  been looked at in the fab's preview, a through-hole or right-angle part sits on its
  holes with its body on our outline, and the price shown has no option carried over
  from the previous board ordered (via size, material, electrical test, build time).
  The assembly tier quoted is the one the design was costed at: at JLCPCB, parts on the
  back, a solder mask that is not green, or a single part marked "Standard only" each
  move the whole board from the economic tier to the standard one (a larger setup fee,
  a stencil charge, a fee per part type), and the page says so only when the BOM is in.
- **M31 — Markings survive assembly.** Pin-1 and polarity marks are visible with the part
  fitted (outside the body, not under it); text is at least the fab's minimum height and
  stroke and not over pads, holes or the board edge; the board's name and revision are
  on it (`kicad_silk.py` prints both). Every LED, button, switch and connector a person uses says what it is for,
  and connector pins that will be wired or probed carry their signal names (with
  direction where it is not obvious: `RX <`, `TX >`).
- **M32 — Connectors are the series the harness uses, and rated for it.** Pitch measured
  on the footprint equals the series' pitch (2.50 is not 2.54, XH is not PH); contact
  current and wire gauge suit the circuit; the housing's pin 1 is where the footprint's
  pad 1 is, checked against the maker's drawing from the correct face. Print the board
  1:1 and offer the real connector to it before ordering. A standard connector (USB,
  audio jack) is numbered as its standard numbers it, and every connector that carries a
  single-ended signal also carries a ground.
- **M33 — Every rail has a power budget.** Worst-case current of every load on each
  rail, added up, is inside the regulator's rating with margin (50 % on a first board),
  and those are the amps declared in `power_paths`. Connectors and cables on the rail are
  inside their contact rating at that current.
- **M34 — Levels and polarities are right at both ends.** Each signal's high and low are
  valid for the pin that receives it. Every enable, reset, chip-select and interrupt is
  the polarity the receiving part wants (active-high vs active-low read in BOTH
  datasheets). Each differential pair's P goes to P. Every open-drain output has a
  pull-up. Each op-amp's feedback returns to the inverting input. An auto-direction level
  shifter does not face a pull-up or pull-down it cannot overdrive.
- **M35 — The errata have been read.** Each MCU, PHY, codec and regulator with a published
  errata sheet has had it read against the pins and peripherals this board uses.
- **M36 — Power leaving the board is limited.** Any supply the board offers to a cable or
  a socket (a USB port, a sensor feed, a rail to another board) has a current limit or
  fuse, so a short at the far end does not take the board's own rail down or burn the
  cable.
- **M37 — The files sent are the board that was checked.** Zones were refilled and DRC
  re-run immediately before export; gerbers and drill were exported together, from that
  state (`fab_package.py` does both and checks the drill file against the board); the package was opened in an independent gerber viewer and looked at, layer by
  layer, with the drills over the copper. Stack-up, finish and any controlled impedance
  are stated on the order.
- **M38 — Nothing is stressed, and everything can be reached.** Ceramic capacitors are
  clear of break-off tabs, V-scores and screw heads, and lie parallel to the nearest edge
  that will flex. Every pluggable connector has room for its plug AND the fingers or tool
  that mate it; test points have room for a probe. Each mounting hole is deliberately
  grounded or deliberately isolated. Indicators and controls face the side a person sees.
- **M39 — Unused pins are treated as the datasheet says.** Every unused INPUT is
  terminated: logic inputs tied high or low (through a resistor where the pin could ever
  become an output, as on an MCU or a transceiver), comparator inputs held apart so the
  output is steady, MCU pins configured in firmware as outputs or as inputs with a pull.
  Unused outputs that need a load (current outputs, amplifier and reference outputs) have
  one. Spare MCU pins worth having later are brought to a pad.
- **M40 — The design record says what must not change.** Every value is one that can be
  bought (preferred-number series; 5.1 k exists, 5 k does not). A part chosen for a
  critical parameter says so in the generator, with the parameter and "do not
  substitute"; a part needing a heatsink, or a tab that is electrically live, says so
  where the part is defined.
- **M41 — Switches and buttons are debounced on purpose.** Each mechanical contact is
  debounced in hardware (RC and a Schmitt input) or in firmware, and the generator says
  which. A contact that wakes, resets or interrupts is debounced in hardware.
- **M42 — Every part can be bought, and bought again.** Each part's lifecycle status is
  active (not "not for new designs", not obsolete) and its lead time is acceptable; this
  was checked when the part was chosen, before layout, and is checked again at order
  time. A part with a single maker has a named alternate that fits the same footprint and
  pinout, or the generator says there is none. The count of distinct part numbers has
  been looked at: same value and package at different ratings or tolerances collapse to
  the stricter one, and an odd value next to a common one (120 nF beside 100 nF) is
  questioned.

---

## Adding a learning

When a board comes back and something was wrong — or a review finds something no rule
caught — **the fix is not finished until it is a rule here.** In the canonical cadkit
repo:

1. **Write it in the log below**: the date, the board, what happened, what it cost.
2. **Decide whether a script can see it.**
   * It can → add a function to `pcbflow/quality.py` under `@rule("A<n>")` returning
     `(subject, ok, text)` rows, and an `### A<n> — title` section above with Rule / Why /
     How it is checked. The script refuses to run if the code and this file disagree.
   * It cannot → add one `- **M<n> — Title.** what to check, against what.` line to the
     manual list. Make it a check someone can actually perform and sign with evidence.
   * Often both: automate the part that can be (presence, distance, width) and leave the
     judgement (value, rating) as a manual rule that names the automated one.
3. **Run it over the existing boards.** A new rule that fails old boards is the rule
   working; fix them or waive them with reasons.
4. Commit, then `py -3.12 tools/propagate.py` so every project has it.

Never renumber a rule: boards sign and waive by id.

## Learnings log

| date | board | what happened | rule |
|---|---|---|---|
| 2026-09-30 | a bus tee | the router laid a trunk rail as 28 mm of 0.25 mm default track: ~55 mΩ per board, ten in series | A1 |
| 2026-10-01 | an optical sensor board | an analog rail read "0 unconnected" with its regulator on one island and every load on another, joined by 62 mm of 0.127 mm repair track | A1 |
| 2026-10-02 | a ribbon between two of our own boards | the two ends were designed with different connectors and different pin orders | M1 |
| 2026-10-04 | (survey of published design-review checklists and first-board post-mortems) | the faults reviewers report most: regulator layout and stability, converter grounding, USB-C CC resistors, I2C pull-ups, crystal load capacitors, loaded strap pins, mistyped net labels, same-package pin-order variants, swapped TX/RX, fab-capability and assembly-tier surprises | A5, A6, A7, A8, M13–M32 |
| 2026-10-04 | (second survey: a widely used open review checklist, a first-board mistakes guide, vendor notes read in full) | power budget per rail, level and polarity of every control signal, errata, current-limited outputs, exporting stale files, board-edge stress on ceramics, crystals placed far from the MCU. Numbers confirmed at source: I2C rise-time bound and 3 mA / 0.4 V sink; USB 2.0 four vias per line and equal count per half; regulator feedback routed away from the inductor | A9, M33–M38 |
| 2026-10-04 | (third survey: a community review FAQ for schematics, read by the owner and summarised here in our own words) | USB device inrush capacitance, unused inputs and outputs, gate over-voltage and series resistance, live tabs and heatsinks, connectors without a ground, values that cannot be bought, undebounced contacts | A10, M39–M41; M19, M25, M32 extended |
| 2026-10-04 | (same community FAQ: its layout and bill-of-materials pages, summarised in our own words) | crystal traces changing layer and load capacitors on the wrong side of the crystal, protection parts placed after the capacitor instead of at the connector, hardware keep-out differing per face, unlabelled controls and connector pins, one value typed two ways, parts that are obsolete or single-sourced at order time | A11, M42; A9, M10, M11, M23, M24, M31 extended |
| 2026-10-04 | (design review, before first order) | four classes of fault named as the ones to stop before a board is ordered: supply choke points, missing surge capacitance, unmatched high-speed traces, mirrored pinouts | A1, A2, A3, A4, M3, M4, M6 |
| 2026-10-04 | the same gerber read, carried on into the mask and paste layers | the board model called every via tented, and the exported F.Mask had 208 apertures and no islands at all, so ten barrels sat open under solder paste; measured as pad AREA the worst read 8 %, measured as paste VOLUME it read 110 % | **A14** (new, measured); `unwick.py` added to the post-route steps; M29 keeps the parts A14 does not measure |
| 2026-10-04 | the exported gerbers of a two-layer board, rendered layer by layer by a reader that is not KiCad | the ground pour was the return for every signal on the board and was also a routing layer, carrying 455.89 mm of signal copper cut through it; nothing measured whether a return had to go round a cut, and M6 only asks it of fast buses | **A15** (new, measured); M6 narrowed to the edge-rate judgement A15 cannot make |
| 2026-10-04 | the fab's own capability page, read against the rule files of seven routed boards | the rule file is typed by a person and DRC only proves the board against it; five of its values were looser than the fab's, and all silk was under the fab's legible height | **A12** (new, measured); M29 narrowed to what A12 cannot measure; `kicad_silk` and the layout's reference text raised to 1.0 mm |
| 2026-10-06 | a control board, in a dry run of the fab's order page | generic passives were sent with no part number, "chosen at order time"; the fab's matcher read KiCad's `C_0402_1005Metric` as 01005 and picked parts its cheaper assembly service does not place, so they came up unselected at quantity 0 and the order would have built the board without them | M30 extended; `fab_package` refuses an uncoded row, keys passives on (value, footprint) and writes the plain package name |
| 2026-10-06 | five boards walked through the fab's order page | the placement file carried our footprints' origins and angles and the fab places its own: a 1x20 header previewed 24 mm off its holes (our origin is pin 1, theirs the middle), and a right-angle two-row header previewed with its pins pointing into the board (the two libraries number its rows opposite ways, which no pad fit can see). The form also kept the previous board's paid options | M30 extended; `pcbflow/fab_frames.py` (new) writes the placement file in the fab's frames and the package lists what it could not measure |
| 2026-10-06 | ten more boards walked through the fab's order page to the quote | (1) every part on an all-back-side board previewed a half turn out: the fab turns a back-side part over left to right, KiCad top to bottom. (2) two BOM rows naming one part number left one row at quantity 0. (3) a row whose designators mix prefixes arrives unticked. (4) the assembly TIER is decided by things that are not in the BOM: back-side assembly, a black solder mask and one "Standard only" part each force the dearer tier | `fab_frames.apply` turns back-side parts half round; the package writes one BOM row per part number and lists the rows that have to be ticked; M30 names the tier |
| 2026-10-06 | a 24 V inlet and twenty photodiodes, both found in the fab's previewer | (1) the inlet's nets were assigned from the SUPPLY's pin table onto the JACK's pad numbers; the two makers number the four contacts differently and the board shorted the supply. (2) the photodiode's footprint numbered anode 1, the maker and the fab number the cathode lands 1 and 4, and the placement frame had been matched by number: all twenty a half turn out | M1 names the translation and asks for the position -> pad -> net table; M2 says a number fit is not orientation evidence |
| 2026-10-06 | a fret-light board: two pairs of frets wired to the same four driver outputs | a loop in the generator read an index left over from the loop above. 24 nets where 32 were meant and eight outputs idle; routed, DRC-clean, quality-clean, because every check compared the board with its own netlist | A13: the board declares its unconnected pins and its nets per group, and the pass fails on any difference |
