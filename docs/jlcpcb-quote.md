# The main board's JLCPCB quote, measured (2026-10-06, re-quoted 2026-10-07)

Asked for: upload the board, check that everything looks right, and keep the pricing
line items so savings have somewhere to be argued from. Method borrowed from the pedal
steel project, where a guessed cost model was wrong by 2x to 12x and the fix was to put
a real fab package through the real order form and read the answer.

Nothing was ordered. The quote auto-saves into the JLCPCB account under
**Projects > Quotes**, project name `main`.

## What the upload confirmed

`elec/out/fab/main.zip` uploaded clean on the first try.

| checked | fab said | we say | |
|---|---|---|---|
| layers | 2 | 2 | ✅ |
| outline | 112 x 95 mm | `BOARD_W, BOARD_L = 95.0, 112.0` | ✅ |
| BOM match | **34 of 34 parts detected, 34 confirmed** | 34 BOM lines | ✅ |
| unmatched / substituted | none | — | ✅ |
| 3D placement preview | renders — but see below; it was the UNCORRECTED placement file | — | ❌ |
| C1/C2 electrolytic polarity | both `+` left, black can right, agreeing with each other and with the silk | — | ✅ |
| J1/J2/J3/J4 | on the -Y edge, screw faces outward | the requirement | ✅ |
| J5 | **on the +Y edge, alone** | finding 21, still open | ❌ |

The BOM matching is the part worth dwelling on. All sixteen generic passives were
sourced the day before this upload, and all sixteen matched the code we gave rather
than something JLCPCB's matcher guessed from footprint text. That is the whole point of
the `REQUIRE_CODES` gate: zero rows left for the fab to interpret.

## The quote, line by line

Standard PCBA, qty 5, top side only, 24 h PCB / 4-5 day assembly, lead-free HASL,
1 oz outer, green/white, 1.6 mm, "Remove Mark".

```
PCB Price                                $12.15
  Engineering fee                         $4.00
  Via Covering                            $0.00     <-- see "the via question" below
  Surface Finish                          $1.40
  Board                                   $5.70
  Confirm Production file                 $1.05     <-- NEW, and deliberate

Standard PCBA Price                     $186.76
  Setup Fee                              $25.75
  Stencil                                 $8.27
  Panel                                   $0.00
  Large Size                              $0.00
  Components (34 items)                  $88.50
  Feeders Loading fee                    $43.40     <-- the second-largest line
  SMT Assembly                            $2.15
  Confirm Parts Placement                 $0.45     <-- NEW, and deliberate
  Hand-soldering labor fee                $3.61
  Manual Assembly                         $2.56
  X-Ray Inspection                        $8.25
  Packaging fee                           $0.51
  Depanel boards & edge rail              $3.31     <-- NEW, and NOT optional

TOTAL                                   $198.91     for 5 boards = $39.78 each
```

⚠ RE-QUOTED 2026-10-07 AND THE OLD NUMBERS ARE NOT PATCHED OUT, because what
moved is the interesting part. It was $193.64. The $5.27 difference is four
deliberate additions and one consequence, not drift:

| line | was | now | why |
|---|---|---|---|
| Confirm Production file | -- | $1.05 | the last look at the panel before it is cut |
| Confirm Parts Placement | -- | $0.45 | an engineer checks polarity and rotation |
| Depanel + edge rail | -- | $3.31 | **required**; see the warning at the end |
| Components | $88.11 | $88.50 | same 34 lines; F2's holder and the day's prices |
| SMT Assembly | $2.08 | $2.15 | more placements after the fuse went on the board |

Both "Confirm" lines were set with **"Do not confirm automatically"** ticked, so the
order WAITS rather than going into production after 48 / 72 hours unreviewed. That is
the whole reason they are being paid for; left on the default they expire into a
production run and buy nothing.

## The via question, answered and closed

The question was whether 0.25 mm vias were drawing a surcharge we could escape by going
to 0.3 mm. **They are not, and we are already at 0.3 mm.** Every one of the board's 86
vias is 0.6 mm pad on a 0.3 mm drill, which is JLCPCB's no-charge minimum, and the quote
agrees in its own words: `Via Covering $0.00`. (The count was 86 when this was
written and is **94** now -- U1's exposed pad went from six barrels to eight and the
router laid the rest; the conclusion is unchanged because the rate is zero.) There is
no saving here because the saving was already taken, presumably when the via size was chosen. Nothing to do.

## Where the money actually is

**$69 of the total is the price of one part.** U2, the ESP32-WROOM-32E (C701342),
is flagged **"Standard Only"** in the parts table. JLCPCB will not place it on Economic
assembly, and selecting it forces the whole board onto the Standard tier. What that
costs, read off the form:

* **Setup $25.75 instead of ~$8.24** (the Economic setup fee measured on the pedal steel
  project). The form states the rule itself: *"The setup fee is $25 per assembly side
  for Standard PCBA."* Top side only, so one.
* **Feeders Loading $43.40.** This line does not exist on an Economic quote at all. Over
  34 items it is **about $1.28 per distinct part number** — which makes the number of
  BOM LINES, not the number of parts, the thing that costs money.
* **X-Ray Inspection $8.25.** Standard only.
* **The board grows.** The form: *"The board size would be modified to be 105*112mm for
  Standard PCBA due to adding two 5mm edge rails on the shorter sides."* That is the
  $5.70 board charge rather than $5.20 and $1.40 of finish rather than $1.30 — small, but
  see the warning below, because the rails are not only a cost.
* **Part minimums rise.** The same BOM priced $88.11 on Standard against roughly $68 on
  Economic: C8 went from 5 pieces to 20, the 100n line from 30 to 40, C13's line from 20
  to 30, D4 from 5 to 15. Standard buys in bigger multiples.

The alternative is Economic plus hand-soldering U2, which is a 25.5 x 18 mm castellated
module — solderable on a hot plate but not a thing to do five times casually, and the
project chose assembled boards on purpose. This is recorded as a priced option, not a
recommendation.

## Savings found, and what each is worth

| | worth | verdict |
|---|---|---|
| 0.25 -> 0.3 mm vias | **$0.00** | already done; `Via Covering $0.00` |
| Leaded HASL instead of lead-free | **$1.40** | available. `ORDER.txt` justifies lead-free on *solderability* for the hand-soldered terminals — but leaded HASL is the easier of the two to hand-solder, so the stated reason argues the other way. The real reason to keep lead-free is RoHS, which a personal backpack does not need. **Left as-is; it is $1.40 and the user's call.** |
| Replace 29k4 (the one Extended passive) with an all-Basic divider | **negative** | see below |
| Drop a BOM line, any BOM line | **~$1.28** | the feeder rate; the only general lever |
| Get U2 off the Standard tier | **~$69** | needs a different MCU module or hand assembly; not a config change |

### 29k4: the measurement reverses the guess

R2 is 29k4, E96, and the only Extended part among the sixteen passives — it looked like
an obvious candidate to design out. 51k/15k and 68k/20k are both all-Basic E24 pairs
with a ratio of exactly 3.4, landing the rail on the same 3.300 V.

**Do not do it.** The quote prices feeders at about $1.28 per distinct part number, and
swapping 29k4 for a new pair ADDS a line rather than removing one — 100k has to stay for
R6/R7/R20, so the BOM goes from 34 lines to 35. The resistor itself is $0.04 for twenty.
The change would cost roughly a dollar twenty-eight and a full re-route, to save nothing.
Recorded in `elec/fab.py` beside the part so nobody re-derives the idea.

## ⚠ Before ordering

1. **The edge rails must be depaneled.** Standard PCBA pads the board to 105 x 112 mm
   with two 5 mm rails on the 95 mm sides. The housing bay is cut for a 95 mm board. The
   order form has **"Depanel boards & edge rail before delivery"** under Advanced
   Options; if it is not selected the boards can arrive 105 mm wide and will not fit.
   **In `ORDER.txt` now, and selected on the 2026-10-07 quote at $3.31** -- the form
   states the rail arithmetic itself, so this is confirmed from its own words rather
   than predicted.
2. **⚠ THE PLACEMENT FILE UPLOADED HERE IS STALE — and so is the rest of the
   package; upload the whole zip, see item 5.** The
   frames were measured after this quote (finding 24) and **13 of the board's 64
   placements moved** (this said "13 of 59"; 59 was a stale total, corrected at all
   five sites that cited it):
   J4 by 10.16 mm, J5 by 7.62, J6 by 6.35 and 90°, the ESP32 by 90° and 3.68 mm, the
   buck by 270°, both gate drivers and Q3 by 180°. The prices above still stand — same
   parts, same board, same copper — but the CPL in this quote would have been assembled
   wrong. **All 17 are corrected now and none is left unfitted** — the last five
   (Q1, Q2, D2, D3, F2) were re-fitted on pad position and hand-entered, see
   finding 24. **M2 is closed too, and without the previewer**: the six polarised
   two-pad parts (C1, C2, D1, D4, D5, D6) were checked against the fab's own layer-49
   pin-1 dot by `elec/fab_polarity.py`, and all six agree that the fab's pin 1 is our
   pad 1. Nothing orientation-related is left for a person.
   **And the "every part on its pads" line in the table above was my own misreading of
   that render**: those twelve parts were visibly off and I read past them.
3. **Check stock the day you order.** Prices here were re-read on 2026-10-07; the
   only figure NOT re-read is the shipping weight, 1.73 kg on 2026-10-06.
4. ~~**J5 is still on the wrong edge** (finding 21).~~ **CLOSED, measured on the
   placement file rather than seen in a render.** All five screw terminals now sit on
   the -Y edge -- the one that faces down over the cable chase -- at an identical
   `y = -147.000` in `main-cpl.csv`: J5 at x 63.70, J2 at 80.50, J3 at 92.25, J1 at
   104.00, J4 at 128.40. The order is J5, J2, J3, J1, J4, which puts the two pump
   terminals adjacent and keeps the pack's stub clear of VBAT's riser.

5. **What was uploaded on 2026-10-07, and why the whole zip.** The 2026-10-06 order
   carried the UNCORRECTED CPL, and the instruction written then said to re-upload the
   BOM and CPL. That was two files short: the copper and drill moved afterwards too --
   F2's holes 1.400 -> 2.050 mm, U1's exposed pad rebuilt, D7 moved off a courtyard
   overlap, and every silk designator a mask opening would have clipped moved by A18.
   Against the old package: **drill 136 -> 146 holes, F.Cu 567 -> 605 objects, F.Silk
   2656 -> 3613**. Uploading two files of sixteen would have ordered the OLD board with
   the NEW parts list, which is the one combination nothing downstream catches, because
   each file is internally valid on its own.
