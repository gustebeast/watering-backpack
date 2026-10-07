# J5 to the −Y edge — pour re-derivation, working notes

Branch `j5-minus-y`. Not mergeable. Main stays orderable.

## Settled: the two pump pours

New pads: J2.2 PUMP_A_LO at x −16.96, J3.2 PUMP_B_LO at +6.54. Q1, Q2, D2 and D3
do **not** move, so each pour becomes an L: a column up from the terminal, a link
left/right **below** the diode's tab, then the original bar on the tab and anodes.

Every edge below is a measured clearance, not a round number:

| edge | against | clear |
|---|---|---|
| link top **−29.3** | D2's tab pad bottom −28.90 | 0.40 |
| bar bottom **−32.9** | C17's courtyard top (after moving C17 to y −36.5) | 1.91 |
| bar right **−19.49** | D2's tab left edge −19.09 | 0.40 |
| column right **−15.26** | VBAT_RAW's new left edge −14.65 | 0.61 |

    PUMP_A_LO  (−33.7,−20.6) (−19.49,−20.6) (−19.49,−29.3) (−15.26,−29.3)
               (−15.26,−48.4) (−18.66,−48.4) (−18.66,−32.9) (−33.7,−32.9)
    PUMP_B_LO  ( −9.3,−20.6) (  2.40,−20.6) (  2.40,−29.3) (  8.24,−29.3)
               (  8.24,−48.4) (  4.84,−48.4) (  4.84,−32.9) ( −9.3,−32.9)

## Settled: VBAT cannot reach C1 along the bottom, and the earlier plan was wrong

I had written "bus at y −54.0..−48.8 under J5's pads, then up the original left
column at x −38..−35.5". **That does not connect.** The column would have to cross
the pad band at y −48.3..−45.7, and J5.2's pad occupies x −40.14..−37.54 there.
What is left between J5.2 and J5.3 is 2.48 mm, and 1.68 mm after clearances —
against the 3.18 mm IPC-2221 wants at 7.5 A.

The route that does work, measured:

1. bus **y[−54.0,−48.7]** under J5 (5.3 mm, clears J5's pads by 0.4)
2. rise **right of J5.4** at x[−26.98,−23.74] — 3.24 mm, the only gap on that row
   wide enough: J5.4's pad ends at −27.38 and J2.1's starts at −23.34
3. left at **y[−33.4,−29.8]**, under Q1's courtyard (−29.36) by 0.44
4. up the original column **x[−38.0,−35.5]** to C1.1 at −37.70, between D1.1
   (−40.40) and D1.2 (−33.60) at the top

This also forces **C17 to y −36.5** (clear of step 3) and **F1/C18 to y ≈ −38.5**
— below step 3 and above J5's courtyard top at −40.56, which is the only band they
fit in.

## ⚠ THE OPEN BLOCKER: VBAT_RAW now sits where VBAT's riser A used to

J1 moved right to x −7.75, so its VBAT_RAW stub moved with it to x[−14.65,−8.45].
**That is exactly where VBAT's riser A ran** (x −12.0..−9.7) to reach D2's cathode
tab from the bus. The two cannot share it, and the alternatives are both shut:

* left of it — PUMP_A_LO's column is at x[−18.66,−15.26], leaving 0.61 mm
* right of it — Q2's courtyard starts at −8.81, leaving 0.36 mm

And D2's tab cannot be fed from the left either: PUMP_A_LO's bar x[−33.7,−19.49]
y[−32.9,−20.6] is across that approach.

**So the terminal ORDER is the next thing to change, not the pour.** J1 is the pack
inlet and the only VBAT_RAW terminal; sitting it between the two pump terminals
puts a higher-priority stub across the path both pumps' VBAT must take. Candidate
order to evaluate next: **J5, J2, J3, J1, J4** — the two pump terminals adjacent so
one VBAT bus serves both, and J1 and its fuse beyond them. That moves F2, C21 and
the VBAT_RAW zone again, and needs the whole set of clearances above re-measured.

Nothing here is believed until the gates say so.
