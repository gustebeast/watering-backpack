# Consolidated Parts List — by Vendor

Two projects on one buying run. Tags keep them separate:
- 🎒 = **Watering Backpack** — now at **v2** (see [DESIGN_V2.md](DESIGN_V2.md))
- 🐱 = **Cat Bed Weight Sensor**

**v2 changed the architecture substantially.** The 4-way reversing valve is gone
(replaced by a second pump), the 12 V rail is gone (pumps run from the battery through
on-board MOSFETs), and the tubing is up-sized from 3/8" to 1/2". **The frame is now
lumber rather than printed** (§7), which leaves exactly one printed assembly: the
battery mount and PCB case (§7b). Parts that v1 bought
and v2 no longer uses are listed at the bottom rather than deleted — several were
bought and are on the shelf, and the reasoning is worth keeping.

---

## 1. Seaflo  *(🎒)*

- [x] 🎒 **Seaflo 42-Series pump — SFDP1-030-055-42 — BOTH BOUGHT.** One carried
  over from v1; the second bought for v2 (owner, 2026-10-05), $64.99–$78.99 — https://seaflodirect.com/seaflo-42-series-diaphragm-water-pressure-pump-3-0-gpm-55-psi-choose-12v-or-24v/
  - ⚠️ **Select 12V** in the Voltage dropdown (not 24V).
  - v2 runs **two pumps in anti-parallel** — one plumbed tank→pot, one pot→tank —
    instead of reversing flow through a valve. A diaphragm pump cannot be reversed
    (its check valves are passive). ⚠ This line used to carry on "and those same
    check valves seal the idle pump's branch, which is what makes this work" — that
    is true of a STOPPED system and not of the one this builds: anti-parallel presents
    the idle pump with a FORWARD differential, which its check valves pass. Built
    without a check valve deliberately; DESIGN_V2 §1 and WORK_V2_PUNCHLIST finding 12.
  - Ports are **1/2"-14 MNPT** (confirmed against Seaflo/West Marine listings).
  - ⚠️ **Bypass the internal pressure switch** on both — it cuts the pump on downstream
    pressure, fighting PWM.
  - 📦 Each pump includes a 50-mesh inlet strainer and 2× 1/2" barb adapters
    (straight; v2 uses 90° swivels instead). **Two pumps therefore put exactly two
    strainers on the shelf, which is the number §4 needs** — no spare, so neither
    is expendable. Four straight adapters come with them and go unused. ⚠ **Do not discard the strainers.** They were written
    off here as "redundant — v2 filters on the green line", and one of them has since
    been backflushed and cleared itself, which is the whole argument §4 makes for the
    printed screen. ✅ **DECIDED 2026-10-05 — they go at the two tees and the printed
    screen is not built** (WORK_V2_PUNCHLIST finding 13, closed). ⚠ **They are DIRECTIONAL**:
    they filter male→female and clean female→male (owner, measured), so the male
    end faces what each one protects against — the **pot** on the green tee, the
    **tank** on the tank tee. Both therefore show their female end to the tee.
    Fitted backwards a strainer sweeps its debris toward the pump instead of away
    from it. Finding 13a.

## 2. Seaflo — pump fittings  *(🎒, NEW in v2)*

- [x] 🎒 **SEAFLO SFFN1-1220-01 — 1/2"-14 FNPT × 1/2" barb, 90° swivel elbow — 5-pack, $12.99 — BOUGHT**
  - https://seaflodirect.com/seaflo-plastic-pex-pipe-coupling-90-degree-fitting-swivel-adapter-1-2-14-fnpt-x-1-2-barb-elbow-fitting-compatible-with-pex-or-pe-rt-pipe-corrosion-resistant-5-pack/
  - SKU `SFFN1-1220-01-5`. Material **PA66 nylon**, potable-water rated. The 5-pack is
    exactly the quantity wanted: 4 fitted (2 per pump) + 1 spare for the fit test.
  - **Why this part, three reasons:**
    1. **Swivel** — the elbow is aimed *after* tightening. NPT is tapered, so a fixed
       elbow lands wherever it seals; a swivel removes that constraint entirely and
       lets the pump bay be packaged tight. The CAD depends on this: it models one
       clearance envelope per port with the leg aimed by `PORT_CLOCK`, which is only
       legitimate because the clock angle is chosen, not inherited from the taper.
       Three of the four aim out the front; pump B's inner leg aims UP, because
       forward is pump A.
    2. **Nylon, not brass.** The pump head is moulded plastic; a brass female fitting
       bites and is how you crack a port by over-tightening. This is the answer to
       *"the filter that comes with the pump screws on easily but my fittings are quite
       hard to thread"* — the strainer is plastic on plastic and these are too.
    3. **Seals on an O-ring, not the thread taper** (no PTFE needed). A marginal taper
       seal on the suction side draws air, a standing suspect in v1's priming failures.
       It is also *why* it threads easily: the thread only holds the joint closed, so
       there is no torque-to-seal to get wrong.
  - **This replaces Shurflo 244-3926, and the swap removes the open risk.** The Shurflo
    part was a *Pentair* fitting hoped to fit a *Seaflo* pump, and the BOM had to carry
    "fit is likely but UNVERIFIED — buy one and test before relying on four", because
    nothing established that Seaflo replicated the shoulder Shurflo's O-ring seals
    against. This is Seaflo's own fitting for Seaflo's own 1/2"-14 port, so that
    question does not arise. The Pentair page was also **not purchasable** — a
    "where to buy" landing page with no listing and no cart.
  - Still unmeasured: the fitting's **dimensions**. `ELBOW_NUT_D/L` and `ELBOW_LEG_D/L`
    in `src/pump_frame.py` remain conservative estimates, and the lumber frame's
    `POST_X` — hence how far apart the posts get cut — is derived from `ELBOW_NUT_L`.
    Measure one on arrival and re-run the build: the frame should get *narrower*, not
    wider, since the estimates were set for a brass fitting.
  - **Fallback if the swivel turns out to be clocked or the barb profile is wrong:**
    SEAFLO **51F03**, 1/2"-14 FNPT × 1/2" barb angled pump fitting, $5.49 (POM/PP),
    sold in 1/2/4/10 packs and listed explicitly for Shurflo/Seaflo/Jabsco pumps —
    https://seaflodirect.com/seaflo-no-51f03-1-2-14-fnpt-x-1-2-barb-angled-universal-pump-fittings-for-shurflo-seaflo-circle-river-johnson-jabsco-flojet-remco-lippert-usa-adventure-and-other-pumps-choose-pack-size/
    Nothing in its listing calls it a swivel, so treat the clock angle as inherited
    from the taper if this one is used — which the frame is *not* currently drawn for.
  - Size: a 5/8" barb would add suction margin, but 1/2" is chosen because the port
    bore is ~13 mm regardless, v2's runs are short, and 1/2" vinyl bends to ~50 mm vs
    ~65 mm — real money in a 206 mm bay.

## 3. Tubing & plumbing  *(🎒)*

- [x] 🎒 **Two tees — U.S. Plastic item 62128, $0.91 ea — ORDERED 2026-10-06** —
  https://www.usplastic.com/catalog/item.aspx?itemid=27820
  1/2" NPT × 1/2" hose ID × 1/2" hose ID, black HDPE, 125 psi with clamps,
  −65 to 190 °F. Qty **2**, one per tee, $1.82 the pair.
  - **The thread is MALE**, which is the whole point and the page title does not say
    so: the product family it sits in is *"Black HDPE Hose Barb x **Male** Threaded
    Tees"*. Plastic, so the male leg threads into the strainer's plastic FNPT without
    §2's brass-into-plastic problem.
  - ✅ **The barbs are specified for 1/2" HOSE ID**, which was the one thing that had
    to be checked before ordering: irrigation-aisle "1/2 inch" barbs are sized for
    0.600" ID poly and would have been ~2.5 mm oversize on 1/2" vinyl. Worth ten
    seconds with a caliper on arrival anyway.
  - *Rejected on freight, not on merit:* **Avidity Science 1610-2845-011**, $1.80 ea,
    the first pick and a good part — UPS only, $20 to ship $3.60 of fittings. Kept as
    the known-good alternative if 62128 ever goes out of stock —
    https://www.avidityscience.com/fitting-barbed-tee-adapter-1-2-barb-x-1-2-barb-x-1-2-male-pipe-thread-plastic-1610-2845-011
  - ❌ **DO NOT add item 37861** — I recommended it on the same order and it is the
    wrong part twice over. Its own page calls it *"a plastic insert for adapting
    polyethylene flexible pipe"*: the barb is **0.406" ID × 0.665" OD**, sized for
    1/2" POLY pipe (≈0.600" ID), so its crest is ~2.8 mm oversize on 1/2" vinyl.
    And it is **MNPT × barb with no slip socket**, so it cannot solvent-weld to the
    Uniseal's PVC stub, which was the entire job it was suggested for. §3's Uniseal
    entry carries the correct chain.
  - ⚠ **The barb BORE is a restriction, measured not waved at** — WORK_V2_PUNCHLIST
    finding 18. Thogus drawing TT3888: crest **0.610"** (15.49 mm, so 1/2" vinyl
    stretches on properly) but bore **0.365"** (9.27 mm), 53 % of the hose area.
    0.26 psi per tee, 0.51 psi over the two each path crosses. Accepted.
  - **Why this list needed them at all, recorded because nothing else catches it:**
    §1's anti-parallel arrangement has needed two tees since it was chosen,
    `src/plumbing.py` models both (`TANK_TEE` at x +73, `GREEN_TEE` at x −73) and
    `check_plumbing.py` routes six hoses through them — and this list had never
    carried either one. No CAD gate could catch it: a tee is a bought fitting and the
    gates measure printed geometry. WORK_V2_PUNCHLIST finding 14.
  - **The male leg is what the decision bought.** The owner chose the two bought
    Seaflo 51S01 strainers over the printed screen (WORK_V2_PUNCHLIST 13), and
    finding 13a shows both strainers face their **FNPT** end at the tee — so one
    male-threaded leg screws straight into each, with no adapter and no hose stub.
  - **Nothing else is needed.** The strainers' MNPT ends take parts already in the
    drawer: the **owned McMaster 5346K56** (FNPT × 3/8" barb) on the green side,
    which is also the 1/2" → 3/8" step at the probe, and a **spare
    SFFN1-1220-01** (FNPT × 1/2" barb) on the tank side.
  - ⚠ **One thing is still unmeasured, and it is geometric, not a purchase:** each
    strainer now sits inline on its tee's third leg, and nobody has measured the
    51S01's length. The model says the green leg has **124 mm** of straight (tee at
    z 84 down to the exit at z −40, and it leaves the pack, so it can also hang
    outside) and the tank leg has about **100 mm** (z 84 up to the Uniseal at
    z 234, less the 50 mm bend radius at the top). WORK_V2_PUNCHLIST finding 16.

- [ ] 🎒 **1/2" ID vinyl tubing — UPSIZE from 3/8"** (Ace ProLine or equivalent)
  - v1 ran 3/8" at **8.7 ft/s**; suction lines want 2–3 ft/s. 1/2" brings it to 4.9 ft/s
    and cuts friction ~3× (loss scales with v²). This is the single cheapest improvement
    to v1's priming margin.
  - **The green line stays 3/8"** where it enters the inner-pot tube — that diameter is
    fixed by the pot. Only the probe; the main run is 1/2". **The transition is the
    owned McMaster 5346K56** (1/2 NPT female × 3/8" barb), screwed onto the green
    strainer's MNPT end — it used to be the printed filter housing, which §4 no
    longer builds.
  - ✅ **RESOLVED 2026-10-05 — 1/2", and this line was right all along.** This
    carried a ⚠ UNRESOLVED against DESIGN_V2 §4/§5's "5/8 everywhere except the
    probe", guessing §5 was "probably right" because it was the broader, later
    statement. It was not settled by argument: **the owner has bought the pump-port
    fitting**, SFFN1-1220-01 with a **1/2" barb**, and a 5/8" tube does not grip a
    1/2" barb. So §2 of this list had already made the decision when it chose that
    fitting, and DESIGN_V2 §5 never noticed. Both are reconciled now, and
    the 1/2" figure is now the only one in the docs. *(`src/line_filter.py` used to
    carry this reconciliation; the module is retired — see §7b.)*
    - The residual is named in DESIGN_V2 §5 rather than buried here: 1/2" runs at
      **4.90 ft/s**, above the 2–3 ft/s a suction line wants, against 5/8"'s
      3.14. It is accepted because the runs are short, the suction is flooded, and
      the pump's own port bore is ~0.51" — so the ports are a 1/2" restriction
      whatever the hose is.
- [x] 🎒 **Hose clamps — 5574K13 — ALREADY OWNED, and now definitely correct** —
  McMaster, worm-drive, smooth-band, 304 SS, **1/2"–3/4" ID**. Centres on 1/2" ID
  vinyl's ~3/4" OD. ⚠ Worth recording that this was a near miss rather than a
  comfortable fit: 5/8" ID vinyl is commonly 7/8" OD, which is **outside** this
  range, so the 5/8" line the docs used to call for would have needed new clamps
  as well as new pump fittings. The 1/2" decision (§3 above) keeps a part that is
  already in the drawer.
- [ ] 🎒 **Uniseal — 1/2" pipe size, $2.75** —
  https://www.saltwateraquarium.com/uniseal-1-2-inch-pipe-pipe-grommets-pipe-to-tank-seals-uniseal/
  **1.25" hole saw**, seals on **0.840" OD = 1/2" schedule-40 PVC**, and the vendor
  says to *"insert the pipe… to clear the inside of the seal by about 1 inch."* So it
  grips rigid PIPE, not the hose — 1/2" ID vinyl is 0.750" OD and would be loose in it.
  **The chain from tank to hose, and all of it except the Uniseal is an Ace trip:**
  1. short piece of **1/2" sch-40 PVC** — through the seal, ~1" proud inside the tank.
     Deburr and chamfer the cut end and wet it, or a square burr rolls the seal lip.
  2. **1/2" PVC FEMALE adapter, slip × FNPT**, solvent-welded to the stub outside
     the tank (primer + cement). ⚠ **FEMALE.** This step read "male adapter,
     slip × MNPT" for one revision while step 3 was also male — two male threads
     do not mate, and nothing in this repo checks a thread gender.
  3. **U.S. Plastic item 62017, $0.51** — 1/2" MNPT × 1/2" Hose ID black HDPE
     adapter, Thogus **TA1088/P** — screwed into step 2, then the hose and one of
     the owned 5574K13 clamps.
     https://www.usplastic.com/catalog/item.aspx?itemid=27798
     **Put it on the tee order.** This is the step where the poly-pipe trap bites,
     and 62017 is the same Thogus hose-ID family as the tees with the same
     verified numbers off drawing TA1088: **MALE 1/2"-14 NPT** on the drawing,
     crest **0.600"** (15.2 mm, so 1/2" vinyl stretches on), bore **0.365"** —
     identical to the tee's, so it adds no restriction the line does not already
     have. Buying it here instead of off an Ace peg is the whole point: the
     catalogue that burned us on 37861 is the one we can now read drawings from.
  *(This line used to read "size TBD once a Scepter panel is measured". The size never
  depended on the panel — it follows from the PVC stub's 0.840" OD. What the panel
  decides is only whether there is flat wall enough for a 1.25" hole.)*
  - For the tank's low outlet (flooded suction). The Scepter's 44 mm opening is too
    small to get a hand inside, so a conventional bulkhead — which needs a nut held on
    the inside — is impossible. A Uniseal installs **entirely from outside**: drill, work
    the seal in, push rigid pipe through. Standard on IBC totes and sealed barrels.
  - Fallback if it doesn't suit: keep the top-routed dip tube and add a **foot valve** at
    its bottom so the column can't drain back. Less robust (a weeping foot valve loses
    prime overnight) but needs no modification to the tank.
- [ ] 🎒 **Check valve, 1/2" barb — for the pot (green) line** — holds the suction column
  between cycles. v2 ingests air at the end of *every* retract by design, so re-priming
  is routine, not exceptional.

- [x] 🎒 **McMaster 5346K56 barbed adapter** (3/8" hose × 1/2 NPT female) —
  **OWNED, and not superseded after all.** It is struck off in *Dropped* below as
  replaced by the Shurflo swivels, and for the pump ports it is. But the owner has
  it, and finding 13a gives it the job no other fitting here can do: it screws onto
  the green strainer's plastic MNPT end and *is* the 1/2" → 3/8" step at the probe
  that §5 needs and that the printed housing used to provide. ⚠ This is the brass
  fitting behind §2's *"my fittings are quite hard to thread"* — tape it, hand-tight
  plus a little; the strainer body is what cracks.

## 4. Sensing & UI  *(🎒)*

- [ ] 🎒 **XKC-Y25 non-contact capacitive liquid level sensor — qty 1.**
  ⚠ **THE VARIANT IS LOAD-BEARING AND THIS LINE USED TO NAME THE WRONG ONE.** It
  said "XKC-Y25-V (or similar)"; "or similar" is wrong three ways and -V may be wrong
  too. The board feeds this sensor from **VBAT behind F1 (~15–20 V)** and reads it on
  **IO14 with R23, a 10k pull-up to 3V3** — which only keeps 18 V off the pin if the
  output is a true **NPN open collector**. So:
  - **5–24 V input.** Several listings are **5–12 V** sub-variants; 18 V kills those.
  - **NPN open-collector output.** Not PNP (sources the supply into the pin), not
    RS485 (no driver on this board), and **not necessarily -V**: the vendor describes
    the -V's HIGH output as "5-24V", i.e. supply-referenced — see
    WORK_V2_PUNCHLIST finding 17 before landing a wire on J5.
  - **4 wires preferred** (V+, GND, OUT, MODE). J5 is a 4-way and `elec/main.py`
    ties MODE to GND to select normally-closed, which is what the firmware's
    `LEVEL_FULL_IS_LOW` encodes. A 3-wire part fixes the polarity in the part number
    instead, and then the firmware constant has to match it.
  Links (US): https://www.amazon.com/5V-24V-Non-Contact-Sensor-Detection-XKC-Y25/dp/B0H13BXYG3
  · https://www.amazon.com/clp/B074PVF341 · https://www.newegg.com/p/1W7-00WA-021C6
  - Clamps to the **outside** of the tank wall; nothing penetrates the tank and nothing
    touches the water, which sidesteps the 44 mm opening entirely.
  - Power **directly from the battery rail** (5–24 V spec covers the pack's 18–20 V) —
    the v2 board only makes 3.3 V, so this matters.
  - Configure output **NPN open-collector**, pulled up to 3.3 V on the board. Push-pull
    mode would put 18 V into a GPIO.
  - **Mount it slightly BELOW the true full line.** A false positive is cheap (stop
    early, look); a false negative overflows. Capacitive thresholds drift with
    temperature, so bias toward tripping early.
- [x] 🎒 **KY-023 joystick — ALREADY OWNED, KEPT** — https://www.aliexpress.us/item/3256809150872159.html
  - Measured noise on battery is **sd 7–9 counts**, which is healthy. The ~120-count
    noise that cost a session to diagnose was a USB-tether artifact, not the wiper —
    there is no observed fault to justify a hall-effect replacement, and hall thumbsticks
    are consumer repair parts rather than distributor stock anyway.
  - Powered from **3.3 V, not 5 V**, so the output stays inside the ADC range.
  - Connects by a 5-pin cable to a terminal block on the main board. Only VRy is used; wire all
    five anyway (free, and leaves SW available as a mode button). The 2.54 mm housing
    doesn't latch, so **the printed mount must capture it** — that, not a new PCB, is
    the fix for v1's flying leads.

## 5. Power & protection  *(🎒)*

- [x] 🎒 **Makita 643852-2 terminal — qty 2 (one spare)**, $8.84 ea, ERP10153397 — https://www.ereplacementparts.com/parts/drill/makita/erp10153397/terminal-643852-2/
- [ ] ~~**Inline fuse holder — 8110K3**~~ — **NOT NEEDED.** The fuse moved onto the
  board as **F2** (Littelfuse 178.6165 FLR holder, LCSC C207061, on the PCBA BOM).
- [x] 🎒 **10 A blade fuse — 7460K45** — McMaster, ATC, 32 V, fast-acting, 5-pack, $3.83.
  **This is the fuse F2 holds.** The holder was chosen to suit it, so the blade itself
  is owned and never appears on the PCBA BOM.
- [x] 🎒 **M2×20 socket screws — OWNED** (McMaster 91292A013) · **M2 heat-set inserts —
  OWNED** (McMaster 94459A110, brass, 2.5 mm).

## 6. Main PCBA  *(🎒, NEW in v2 — single board)*

Fab: **JLCPCB**. Prefer Basic/Preferred library parts to avoid extended-part fees.
Exact part numbers to be fixed at layout; this is the functional list.

- 2× **N-channel MOSFET**, 40 V, low R<sub>DS(on)</sub>, DPAK/TO-263 on a copper pour —
  one per pump. **No H-bridge**: each pump runs one direction only (direction is chosen
  by *which pump* is energised), so a single switched leg replaces the BTS7960.
- 2× **gate driver** — 7.5 A at 20 kHz is not a job for a bare 3.3 V GPIO.
  UCC27517, non-inverting, and it is a **4.5–18 V part**, so it cannot run on 3V3.
- 1× **10 V, ≥0.5 W Zener (SOD-123) + 1k5 0805 + 10 µF 0805** — the **VGATE** rail
  the drivers above actually run on, shunt-regulated off VBAT. Two passives instead
  of a second regulator because the load is ~1.5 mA; it idles 3.3–6.7 mA, which this
  machine can afford. See `elec/CIRCUIT.md` finding 2.
- **Buck support passives that the datasheet requires, not optional:** a **49k9**
  RT/SYNC resistor (the pin may not float — sets 500 kHz) and a **10 nF** soft-start
  cap on pin 6, which is SS and not COMP. The feedback divider is **100k / 29k4**, not
  100k / 31k6; the latter sets 3.12 V on the rail that is also the ADC reference.
- **10× 1.5 mm bare-copper test pads**, net-labelled on the silkscreen — GND, VBAT,
  +3V3, VGATE, SW, GATE_A, GATE_B, VBAT_SENSE, JOY_FILT, LEVEL. No cost, no part, no
  placement; they are copper. They are how a defective board gets diagnosed instead
  of replaced.
- 2× **Schottky freewheel diode**. Plain, not synchronous: it conducts only during
  off-time and usage is mostly full-on.
- 1× **LMR14020SDDA buck, 18 V → 3.3 V**, 0.6 A drawn of a 2 A part, rated **≥36 V in**
  — a fresh Makita pack is 20 V and inductive spikes exceed that, so 24 V-max parts
  (MP2315, AP63203) are too close to the edge.
  ⚠ **It is NOT synchronous**, and this list said it was. A non-synchronous buck needs
  an external **catch diode** — **D6, SCHOTTKY-60V-3A in SMA** — and without it the SW
  node is driven past its −3 V rating every cycle: no 3.3 V rail, no MCU, no gate drive,
  no board. Buy the diode.
- 1× **inductor, 10 µH, ≥4.6 A saturation** (Bourns SRN6045TA-100M class). The
  saturation current is the spec that matters, not the DCR: it has to clear the
  regulator's own 3.8 A maximum current limit, or the part saturates *before* the chip
  protects it. The first choice did not, and the fix ran **down** in inductance.
- 2× **output capacitor, 22 µF 16 V 1206 X7R** (C4 + C19 = 44 µF nominal). X7R is a
  **requirement, not a preference** — the datasheet's stability equation needs 16.5 µF
  of *effective* capacitance at 3.3 V, and the DC-bias derate is the whole argument.
  Y5V in the same package would not meet it.
- 1× **ESP32-WROOM-32E** module. Expect an *Extended* part (small setup fee). Keep the
  antenna over a board edge with copper keepout — **and don't orient it into the tank**;
  5 gal of water is an excellent RF absorber.
- 1× **active magnetic buzzer** + small transistor (~30 mA is beyond a GPIO) — tank-full
  alert. Not a speaker; that needs an amplifier. Filling happens with the pump OFF and
  the user at the tank, so ~85 dB is ample. Sound port faces **down** (it's also a water
  path).
- Battery voltage divider → ADC — duty compensation as the pack drains, and sag visible
  in telemetry. Would have diagnosed v1's mid-run slowdown immediately.
- **RC filter on the joystick ADC input** — the only noise defence available, since
  there is no joystick board to buffer at the source.
- 3.3 V pull-up for the level sensor's open-collector output.
- **TVS: SMCJ24A** (24 V standoff, 38.9 V max clamp, 1500 W, IFSM 200 A) + bulk
  electrolytics at the switches. The clamp is the number every part on the rail is
  judged against, so buy this part and not "an SMCJ class part". The **C** matters:
  an SMBJ24A has the identical 38.9 V clamp and would look right on every rail sum,
  but only a third of the surge current, and the surge current is what holds reverse
  polarity (§6). LCSC C310039; alternates C224045, C284096, C151903, C10771.
- 1× **resettable PTC, 30 V 200 mA, 1206** (F1) in series with the level sensor's VBAT
  feed — resettable on purpose, because this machine is carried into a garden and a
  cartridge fuse out there is a walk home.
- **Reverse-polarity P-FET: NOT required, and the line is withdrawn rather than left
  pending.** It was specified while the battery inlet was a keyed XT30, and never
  revisited when the inlet became a 5.08 mm screw terminal with two identical wires.
  The resolution is not a new part: reverse-polarity protection by crowbar is a
  **shunt**, and D1 already is one. Sizing it by I²t against the fuse — 332 A²s for an
  SMCJ24A against the 10 A ATO's 115 A²s minimum melt, 2.9× — makes a reversed pack a
  survivable event with no series element in the 7.5 A path. Full derivation in
  `elec/CIRCUIT.md` §6.
  The fuse is **F2, on the board** (Littelfuse 178.6165 FLR holder, LCSC C207061),
  taking the 10 A ATC blade already owned. That makes the 115 A²s a figure read off a
  part the board specifies rather than a requirement on whoever wires it up. Do not
  fit a larger blade: 115 A²s is the ceiling the sum above is built on.
- 6-pin programming header with DTR/RTS. **No USB-C** — a connector is a water-ingress
  path outdoors, and OTA covers everything after bring-up.
- Connectors: **push-in terminal blocks, not JST** — 5.08 mm for battery and each
  pump (7.5 A), and 5.08 mm for the joystick (5-pos) and level sensor (4-pos) too —
  this used to say 3.5 mm for those two and the next sentence has always
  contradicted it; the board is 5.08 on all five. Every one of
  these is landed once at assembly, so JST's plug/unplug advantage doesn't apply,
  and a terminal is ONE part with no mating half to stock (PCB_README §3 warns that
  a joint where you supply both halves is where the catalogue is worst).
  **All five are one part: Ningbo Kangnex WJ500V-5.08-NP, 5.08 mm screw** — 2P
  for the pack and both pumps (C8465), 5P for the joystick (C42377750), 4P for
  the level sensor (C42377749). The old spring-cage-over-screw preference is
  withdrawn in `CIRCUIT.md` §7: a joint torqued to the specified 0.4 N·m is not
  the vibration risk a spring cage is sold against, and the cable load is carried
  by the housing tie rib, not by the clamp. At 7.5 A the contact rises 16.9 K
  over ambient against a 105 °C part limit — 38 K of margin.
  They give no strain relief, so the shroud needs a cable anchor behind them.
- *Optional:* low-side shunt per pump → ADC.

## 7. Structure — LUMBER, not printed  *(🎒)*

The frame was printed in v1 and in the first cut of v2. It is now **hardware-store
lumber**: it is a rectangular table carrying a static 21 kg, which is what framing
timber is for, and wood is stiffer per gram than PCTG, immune to the creep that
drove the material choice, and free of the whole X-build argument the printed
frame was contorted around.

- [x] 🎒 **Stansport Freighter aluminium pack frame — OWNED.** 820 × 400; shelf 340 wide
  × 250 deep.
- [x] 🎒 **Scepter 5 gal military water can — OWNED.** Base ≈ 348 × 173 mm, standing on
  **two wide ribs**, ~12 mm in from each end.
- [ ] 🎒 **38 × 38 mm beam — 1.61 m of stock** (one 8 ft / 2.4 m length covers it with
  spare). Cut list, straight out of `src/lumber_frame.py`:
  | qty | piece | length |
  |---|---|---|
  | 4 | post | 146 mm |
  | 2 | cross rail | 380 mm |
  | 2 | side rail | 134 mm |

  *The posts are 146, not 150: the frame now stands ON the pump floor, so they
  start at the floor's top face rather than at z=0.*
- [ ] 🎒 **137 × 20 mm plank — 6 × 210 mm** (1.26 m of stock): three for the deck,
  three for the pump floor. Laid front-to-back.
  **Deck** — three full planks make a 411 mm deck on the cross rails, 16 mm proud
  each side, **no ripping**; the tank only needs 348.
  **Floor** — under the posts, carrying the pumps. The two outer planks are
  **ripped to 121.5 mm** so the floor spans exactly the 380 mm frame width and
  stops at the post outer face; three full 137s would reach x = −205.5 and foul
  the electronics housing. Drill **8 × Ø4.5** for the pump M4s at the positions
  `src.pump_frame.pump_bolt_xy()` reports.
  **One notch, in the outboard plank only:** 10 mm deep × 86 mm long in its outer
  edge, 10–96 mm from the front. The battery seats by sliding down and has to lift
  93 mm to clear the dock's rails, and this plank's overhang is the roof over that
  path — without the notch the pack cannot be changed at all. The notch only eats
  overhang that laps past the rail and bears on nothing, so it costs no strength.
- [ ] 🎒 **Wood screws to join the frame** — your choice of fixing; the model does not
  prescribe one. #8 × 60 mm into end grain, or pocket screws, or corner brackets.

**Only three of the frame's numbers are chosen; the rest fall out of the stock.**
`POST_X` because the elbow swivel nuts reach |x| = 147, so 152 is the first clear
inner face. `RAIL_Z0 = 150` because of the hose that crosses *over* the pumps —
its centreline is 134 and it is 19 across, so nothing may intrude below 143.5.
`FRAME_D = 210` because the pumps are 206 long, which is also why there are no
lower cross rails: there is no y left to put one in.

**One rib is not over a rail, and that is fine — measured, not assumed.** The
cross rails sit at y 0..38 and 172..210; the tank's ribs at y 12 and 161. The
first lands on a rail; the second is bridged by the deck plank over a 134 mm
clear span. At 40.5 N per plank that is **0.15 MPa of bending against ~10 MPa
allowable for softwood** (0.45 MPa even with a 3× set-down factor) and 0.0025 mm
of deflection. The rails cannot move to meet the ribs — they are where they are
so the frame contains the 206 mm pumps.

## 7b. Printed parts  *(🎒)*

Two parts, plus two carried over from v1. `py -3.12 -m
src.build` exports them all and prints the sizes against the 255 mm bed.

| part | volume | note |
|---|---|---|
| `v2_housing` | 151 cm³ | battery mount + PCB case, one piece — the bay grew 12 mm in Z with the board (F2, the on-board blade fuse) |
| `v2_housing_lid` | 66 cm³ | shoebox cover: 28.0 mm skirt on all four bay walls (F2 is the tallest part now, 21.6 mm, and SKIRT_D is derived from it), 2.4 mm (3 beads) throughout, one wood screw (Ø9.3 head, Ø11 access bore) |
| `joystick_mount` | 7 cm³ | mounts on the shoulder strap. ✅ **ALREADY PRINTED AND ASSEMBLED** — owned as a finished part (owner, 2026-10-05), so neither it nor its five M2 fasteners is anything to buy. It stays in `printed_parts()` because the gates should keep measuring it; ~8.6 g of the filament figure below is already spent. |
| `dual_clamp_19` | 16 cm³ | hose → pack-frame pole, one M4 |

`joystick_mount` and `dual_clamp_19` attach to things this model does not draw —
the shoulder strap, and the pack frame's tubing (`plumbing.pack_frame()` is a flat
reference panel). So they carry no position in the assembly and are **outside the
interference gate**; only their print size is checked. Modelling the pack frame's
tubing is what would bring them inside it.

**`line_filter_screen` is retired, and so is its coupon.** §4 used to specify a
printed, sealed, self-backflushing screen on the green line; the owner decided on
2026-10-05 to use the two **bought** Seaflo 51S01 strainers at the two tees instead
(finding 13). `src/line_filter.py` and `src.test_pieces.test_screen_slice` are
deleted rather than left unbuilt — a coupon for a part nobody prints invites someone
to print it and conclude something. git has both. The filament figure below dropped
5 g with it, and `check_bom.py` is what noticed.

**`dual_clamp_23` is retired.** It gripped a 23 mm *valve* body, and §1 of
DESIGN_V2 is "two pumps, no reversing valve" — there is no valve, and nothing in
v2 is 23 mm across. It was being exported and billed here at 17 cm³ regardless.

- [ ] 🎒 **PCTG filament — ~294 g** for the set (239 cm³ at 1.23 g/cm³), plus waste.
  In shade. Tougher than PETG at the stress risers that matter here and Tg ~85 °C.
  **Not PLA** — sustained load near PLA's 60 °C Tg creeps.
  *The battery dock is no longer printed on its own; it is fused into the housing.*
- [ ] 🎒 **M4 x 45 bolts + nyloc nuts × 8** — the pumps bolt through the floor planks.
  Each pump has four Ø4 mounting holes on a 73 × 83 mm pattern (exact, from the drawing);
  the floor is 20 mm plank, so M4×45 clears bracket + plank + nut. Nuts go on
  UNDERNEATH, so bolt the pumps down before the floor goes on the frame.
- [ ] 🎒 **M4 heat-set insert × 1** (Ø6.0 × 5.0 pocket) — it holds the board down.
  **Not × 8.** Four held the lid onto four Ø10 pillars, and the lid is a shoebox
  lid now, held by its skirt and one wood screw. Three of the other four held a
  board that a hooked lip on the +Y wall and four Z stops hold for nothing.
- [ ] 🎒 **M4 × 6 socket screw × 1** — board → boss → back plate (4.4 mm of bite
      in a 5 mm insert). **Not × 8, and not × 4.** The board goes in by tilting it,
      sliding its +Y edge under the retention lip and lowering the -Y edge onto its
      standoffs; this screw is at the -Y bottom corner, the end the lip does not
      reach. To take it out: screw out, slide 2 mm toward -Y, lift.
      × 6 and not × 8: the insert ends 6.6 mm in, so the extra 2 mm of screw bought
      no engagement — it only forced the bore to within 0.6 mm of the back face. At
      × 6 the bore stops 1.5 mm short and the bay's back wall stays closed.
*The PCB bay is closed except for the down-facing cable chase and the four
wood screws, which their own heads fill. All eight insert bores used to run clean
through the back wall — four into the open air between the posts — which is eight
water paths into the electronics on a machine carrying five gallons above them.
There is one bore now.*

- [ ] 🎒 **Cable ties — 2.5 mm × 100 mm, a handful**. The two diamond floor slots
      they used to thread are gone, so there is no printed anchor at the moment.
      The **battery pair** does not need one: it threads a 22 × 5 mm slot through
      the 3 mm back plate and turns 90° against it, and a bend through a close
      hole is real relief on the one pair carrying 7.5 A. The leads that come
      *down* the chase from the tank side — level sensor, joystick — still land
      straight on a terminal clamp with nothing holding them.
- [ ] 🎒 **#8 flat-head wood screws × 3**, ≥ 25 mm — housing → posts. **Ø9.3 head**,
  Ø4.0 shaft, 4 mm cone — the same screw the retractable-cable-spool project
  validated (`src/params.py`, WOOD_SCREW_*). Ø4.5 clearance with a **Ø9.6**
  countersink, 0.3 mm of clearance on a printed cone, so the heads sit flush
  inside the housing. *(It was Ø9.0 — three tenths SMALLER than the head, which
  would have landed on the pocket rim instead of seating in it.)*
- [ ] 🎒 **#8 flat-head wood screw × 1**, ≥ 32 mm — the **+y +z** one, which now also
  holds the LID. It passes through the lid's retention boss (3 mm at the far end),
  the housing's back plate (3 mm) and then into the post, so it needs ~3 mm more
  than the other three; 32 mm leaves 25 mm in the wood. Its head lands in the BOSS's
  countersink, not the housing's, and it is driven down a **Ø11** access bore through
  the lid — 1.7 mm clear of the Ø9.3 head, because this is a hole you post a screw
  down, not one you fit it in. You need a bit at least 30 mm long past the chuck.
  **Back this screw out to take the lid off** — that, and the skirt, is what retains it.
  The housing keeps its own countersink at that position so it can still be mounted
  on its own, lid off, during assembly.

## 8. DigiKey  *(all 🐱 — unchanged)*

- [x] 🐱 **Crydom CX240D5 SSR** — $21.62 — https://www.digikey.com/en/products/detail/sensata-crydom/CX240D5/139586
  - Driven via transistor: GPIO →[1kΩ]→ 2N3904 base; emitter→GND; collector→SSR ctrl(−); ctrl(+)→+5V.
- [x] 🐱 **Interlink FSR 406** — DK# 1027-1002-ND, MPN 30-73258, $10.08
- [x] 🐱 **2N3904**, **10 kΩ**, **1 kΩ** resistors — $0.34 total

---

## Dropped — bought for v1, not used in v2

Kept here rather than deleted: most are on the shelf, and the reasons are the design.

- ~~**Farady 4-Way X-Port reversing ball valve, 5/8" barb**~~ — replaced by the second
  pump. Two reasons, either sufficient: (1) it had to be hand-reachable, which forced the
  chest-height routing that *caused* the priming failure — a diaphragm pump evacuates air
  poorly and every dip in that path held a water slug it couldn't push through;
  (2) it's a car AC/heater valve rated for ~2 actuations a year, against the ~60 per
  session v2 would ask. It is already stiff enough to be hard to turn by hand, and dry
  lube didn't fix it — that's a duty-cycle mismatch of three orders of magnitude, not a
  lubrication problem.
- ~~**Pololu D42V110F12 buck, 12 V/9 A, $59.95**~~ — v2 drives the pumps straight from
  the battery through the board's MOSFETs with duty capped to synthesise 12 V. PWM
  already chops the supply, so the motor doesn't care. Deletes the most expensive and
  hottest part in the box. *(It was also the leading suspect for v1's mid-run slowdown —
  12 V/9 A against a 7.5 A pump, sealed box, no heatsink, and the v1 BOM itself warned
  "add a heatsink / ensure airflow". **Disproved**: the buck was cool. The slowdown is
  still unexplained; battery sag and suction-side cavitation are the open candidates.)*
- ~~**Traco TSR 1-2450E (5 V/1 A)**~~ — superseded by a single-stage 18 → 3.3 V buck on
  the board.
- ~~**BTS7960 43 A H-bridge**~~ — two unidirectional pumps need two switched legs, not
  four quadrants.
- ~~**McMaster 5346K56 barbed adapters** (3/8" hose × 1/2 NPT female)~~ — dropped
  for the pump ports, where the Shurflo swivels replace them, and they are the
  brass fittings that thread hard into the plastic. **Un-dropped for one job** and
  moved up to §3: finding 13a.
- ~~**Beduan 5/8"→3/8" barb reducers ×4**~~ — v1 necked the whole system down to its
  narrowest element in four places. v2 runs 1/2" throughout with one transition, inside
  the printed filter housing.
- ~~**McMaster 4912K34 ball valve**~~ — dropped during v1. Killswitch is unplugging the
  Makita battery; the diaphragm check valves block flow when off, so there's no siphon.
- ~~**Printed green-line filter screen** (`line_filter_screen`, `src/line_filter.py`,
  and the `test_screen_slice` coupon)~~ — not bought, *designed*, and dropped
  2026-10-05 for the two bought Seaflo 51S01 strainers at the tees. It was the right
  part: §4's self-backflushing argument is sound and the owner's own backflush test
  is what proved it. The strainers satisfy the same argument with parts already in
  the drawer, no 0.25 mm slot printability bet, and no undecided housing. 13/13a.
- ~~**YF-S201 flow sensor**~~ — dropped during v1; open-loop PWM was sufficient.

---

*Last updated: 2026-10-03 (v2 architecture)*
