# Pre-order validation — four independent passes, run by agents

**Status: QUEUED.** Runs after (1) the terminal row lands on the −Y edge and
(2) the internal wiring is modelled. The owner set that order.

Source: the pedal steel lead's pre-order checklist. It is written for that
project's boards — several bench boards, an STM32 and some CH32V parts — so it is
**adapted** here rather than copied. This repo has one board and one MCU.

**Why "after" is also right engineering, not just the owner's call:** passes 1–3
read the *netlist*, which the J5 work does not change, but pass 4 and any placement
claim read the CPL, which it does. Reviewing a placement that is about to move
would produce a report that is stale before it is read. The netlist being stable
is also why these four can all start the moment the merge lands.

**The point of an agent here is ignorance.** Each reviewer gets what the *fab*
gets — netlist, BOM, placement — plus the makers' datasheets, and must not read
`elec/main.py`. A reviewer who has read the generator will re-derive the
generator's own assumptions and agree with them. That agreement is worth nothing;
it is the same mistake as a hand-typed copy of the board agreeing with itself,
which this repo already has scars from.

---

## 1. Pin-by-pin review against the datasheets

One reviewer, no knowledge of the generator. For **every** chip and connector,
write a row: `pin number → datasheet pin name → net`, and flag anything that
contradicts the maker's reference circuit.

Parts: U1 LMR14020SDDA, U2 ESP32-WROOM-32E, U3/U4 UCC27517, Q1/Q2 (TO-252),
D1 SMCJ24A, D2/D3 (TO-263), J1–J6, F1, F2, BZ1.

Hunting specifically for the classic first-spin killers:

* a package variant whose pin order differs from the one assumed
* a **bottom view read as a top view** — the single most expensive drawing error
* an enable or mode pin left floating that the datasheet requires driven
* a feedback divider that sets the **wrong output voltage**

That last one has a live hook here: the buck's feedback is 100k over 29k4, and
`elec/main.py` derives it as `100k × 0.75 / (3.3 − 0.75) = 29.41k`. The reviewer
should derive the output voltage **from the datasheet's own equation and the
parts on the BOM**, and say what it comes to — not check the arithmetic already
written down.

## 2. ESP32 pin-function check

The lead's version uses CubeMX for the STM32 and WCH's tables for the CH32V. Ours
is an **ESP32-WROOM-32E**, so the equivalent is Espressif's datasheet v2.1 pin
tables plus the module's own restrictions. Every signal must land on a pin that
can actually perform its function:

* **ADC2 cannot be read while WiFi is on.** This board has two analogue inputs —
  VBAT_SENSE and JOY_FILT — and a WiFi part. If either sits on an ADC2 pin, that
  is a re-spin, not a firmware workaround.
* **GPIO34–39 are input-only** and have no pull-ups. Anything driven on those is
  dead silicon.
* **GPIO6–11 are the module's internal flash bus** and are not ours to use.
* **Strapping pins** (0, 2, 5, 12, 15) must boot to the right state — M8 already
  argues this, so the reviewer should test the argument, not restate it.

Deliverable is the **pin-setup firmware**, written now: it is the check and it is
the start of the firmware this machine needs anyway. `firmware/` already exists.

## 3. Voltage on every pin against its rating — A NEW RULE

The lead is right that no rule covers this. A scripted pass assigns every net its
worst-case voltage and fails any pin rated below it.

Worst case on this board is **not** the nominal 18 V: a fresh Makita LXT pack is
~20 V, and D1 is a 24 V TVS chosen to clamp above that. Bands: VBAT / VBAT_RAW /
VBAT_LVL and the two motor legs at 20 V (24 V clamped), +3V3 at 3.3 V, VGATE at
its Zener, GND at 0.

⚠ **This belongs in canonical `../cadkit`, not the vendored copy.** Adding a rule
by hand to `cadkit/` here is exactly the drift that collided with the pedal steel
project's A13 and cost a day. Edit canonical, commit, then
`py -3.12 ../cadkit/tools/propagate.py`. Take the next free rule ID there — do not
assume one. And **make it fail before believing it**: a 20 V net on a 16 V part, a
pin with no rating at all, and a board where every rating is absent should each
produce a different answer.

## 4. Custom footprints against the datasheet land pattern

Everything in this repo's own library was drawn by hand and has never been checked
against a maker's recommended land pattern. JLCPCB's previewer covered the parts
whose placement frames fitted automatically; it did not cover these.

* `wbp:SOIC-8-1EP-FABDRILL` — U1's land, including the six 0.3 mm thermal vias
  through the exposed pad
* `wbp:ESP32-WROOM-32E-FABDRILL` — U2, including the twelve 0.7 mm plated holes
  in the thermal pad and the antenna keepout
* the three whose frames the automatic pad-**number** fit refused and which were
  resolved by hand on pad **position**: `TO-252-3_TabPin2` (Q1/Q2),
  `TO-263-2` (D2/D3), `FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165` (F2)

For the last three the hand reasoning is in `elec/fab_frames.json` under each
entry's `by` field. The reviewer should check the **land against the datasheet**,
which is a different question from whether our land matches the fab's library —
both can agree and both still be wrong.

---

## Reporting

Each agent returns findings only, with the datasheet page or table cited for every
claim. A finding with no citation is an opinion. Findings land in
`WORK_V2_PUNCHLIST.md`, numbered, and anything accepted rather than fixed is named
and measured — never lumped.
