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

Everything a board declares lives in its generator, under `BOARD_NOTES["quality"]`:

```python
"quality": {
    # A1 -- every supply net: where it enters, where it goes, how many amps
    "power_paths": [
        {"net": "+24V", "from": "J1.2", "to": ["U5.5", "J7.2"], "amps": 3.0},
        {"net": "+3V3", "from": "U6.5", "to": "U1.19", "amps": 0.25},
    ],
    "temp_rise_c": 10, "copper_oz": 1, "inner_oz": 0.5,          # defaults
    "max_drop_mv": 50,                     # default; or per path: {"max_drop_mv": 20}
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
must not drop more than `max_drop_mv` (50 mV) at that current. A net that looks like a
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

**Fix.** Size the net in `net_widths`, or lay the path as declared copper (`tracks`), or
pour it. Then check **M3** (the return path).

### A2 — Every supply pin has a capacitor beside it

**Rule.** Each IC pin (`U*`) on a supply net has a capacitor to ground on that net within
`ic_mm` (5 mm). Each connector pin (`J*`, `P*`) on a supply net — every power input and
output of the board — has one within `connector_mm` (25 mm).

**Why.** A load that steps its current pulls the rail down for as long as the inductance
between it and the nearest charge lasts. The capacitor is that charge; a capacitor on the
far side of the board is a capacitor on a different rail. Power entering or leaving the
board arrives down a cable, which is the worst inductance in the system.

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
and for a connector decide explicitly which face the drawing shows.

---

## Manual checks

Sign each in `quality["manual"]` with what you checked against. If a rule does not apply
to the board, sign it with the reason ("no external connectors").

- **M1 — Mating connectors agree pin for pin.** For every cable and board-to-board joint,
  write out pin N at one end and what it reaches at the other, viewed from each
  connector's own mating face. Check the cable type (straight vs crossed, ribbon pin 1
  stripe), that an unshrouded or unkeyed connector cannot be plugged reversed or offset
  without marking, and that the pin order is held in ONE shared constant, not typed twice.
- **M2 — Polarised two-pad parts face the right way.** Diodes, LEDs, TVS, electrolytic and
  tantalum capacitors: the cathode/negative pin in the generator is the pad the footprint
  numbers as that pin (KiCad diodes: pad 1 = K), and the part's reel orientation is in the
  rotation check for the fab.
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
  between domains, and regulator dissipation (Vin − Vout) × I against the package.
- **M6 — High-speed buses are matched and have an unbroken reference.** Clocked parallel
  buses and anything above ~50 MHz or with fast edges (ULPI, SDIO, RGMII, SPI at tens of
  MHz) are in `match` groups with a budget derived from the bit time. Each runs over a
  continuous plane: no crossing a split, a slot, or a gap in the pour; a layer change has
  a ground via beside it.
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
  cable reaches; reverse-polarity and over-current protection on the power input; nothing
  outside the enclosure can back-feed a rail.
- **M11 — It fits and can be assembled.** The CAD check passes on the mated envelope
  (`solid(mated=True)`); every connector can be plugged with the board installed; tails
  clear along the install stroke; mounting holes have laminate round them and no copper
  under the screw head; parts the fab cannot place are zero.
- **M12 — The order is right.** Every part number read off its listing and in stock
  today, with what it mates to; rotations checked in the fab's previewer for every
  polarised and multi-pin part; board name and revision in silk; order-form settings
  (mask colour, mark removal, rail edges) written down.

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
| 2026-10-04 | (design review, before first order) | four classes of fault named as the ones to stop before a board is ordered: supply choke points, missing surge capacitance, unmatched high-speed traces, mirrored pinouts | A1, A2, A3, A4, M3, M4, M6 |
