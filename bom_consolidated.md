# Consolidated Parts List — by Vendor

Two projects on one buying run. Tags keep them separate:
- 🎒 = **Watering Backpack** — now at **v2** (see [DESIGN_V2.md](DESIGN_V2.md))
- 🐱 = **Cat Bed Weight Sensor**

**v2 changed the architecture substantially.** The 4-way reversing valve is gone
(replaced by a second pump), the 12 V rail is gone (pumps run from the battery through
on-board MOSFETs), and the tubing is up-sized from 3/8" to 1/2". Parts that v1 bought
and v2 no longer uses are listed at the bottom rather than deleted — several were
bought and are on the shelf, and the reasoning is worth keeping.

---

## 1. Seaflo  *(🎒)*

- [ ] 🎒 **Seaflo 42-Series pump — SFDP1-030-055-42, $64.99–$78.99 (pick the 12V option) — BUY A SECOND** — https://seaflodirect.com/seaflo-42-series-diaphragm-water-pressure-pump-3-0-gpm-55-psi-choose-12v-or-24v/
  - ⚠️ **Select 12V** in the Voltage dropdown (not 24V).
  - v2 runs **two pumps in anti-parallel** — one plumbed tank→pot, one pot→tank —
    instead of reversing flow through a valve. A diaphragm pump cannot be reversed
    (its check valves are passive), and those same check valves seal the idle pump's
    branch, which is what makes this work. See DESIGN_V2 §1.
  - Ports are **1/2"-14 MNPT** (confirmed against Seaflo/West Marine listings).
  - ⚠️ **Bypass the internal pressure switch** on both — it cuts the pump on downstream
    pressure, fighting PWM.
  - 📦 Includes a 50-mesh inlet strainer (now redundant — v2 filters on the green line)
    and 2× 1/2" barb adapters (straight; v2 uses 90° swivels instead).

## 2. Seaflo — pump fittings  *(🎒, NEW in v2)*

- [ ] 🎒 **SEAFLO SFFN1-1220-01 — 1/2"-14 FNPT × 1/2" barb, 90° swivel elbow — 5-pack, $12.99**
  - https://seaflodirect.com/seaflo-plastic-pex-pipe-coupling-90-degree-fitting-swivel-adapter-1-2-14-fnpt-x-1-2-barb-elbow-fitting-compatible-with-pex-or-pe-rt-pipe-corrosion-resistant-5-pack/
  - SKU `SFFN1-1220-01-5`. Material **PA66 nylon**, potable-water rated. The 5-pack is
    exactly the quantity wanted: 4 fitted (2 per pump) + 1 spare for the fit test.
  - **Why this part, three reasons:**
    1. **Swivel** — the elbow is aimed *after* tightening. NPT is tapered, so a fixed
       elbow lands wherever it seals; a swivel removes that constraint entirely and
       lets the pump bay be packaged tight. `src/pump_frame.py` depends on this: it
       models one clearance envelope per port with the leg aimed along +Y, which is
       only legitimate because the clock angle is chosen, not inherited from the taper.
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
    in `src/pump_frame.py` remain conservative estimates, and `POST_X` (hence the whole
    frame width) is derived from `ELBOW_NUT_L`. Measure one on arrival and re-run the
    build — the frame should get *narrower*, not wider, since the estimates were set
    for a brass fitting.
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

- [ ] 🎒 **1/2" ID vinyl tubing — UPSIZE from 3/8"** (Ace ProLine or equivalent)
  - v1 ran 3/8" at **8.7 ft/s**; suction lines want 2–3 ft/s. 1/2" brings it to 4.9 ft/s
    and cuts friction ~3× (loss scales with v²). This is the single cheapest improvement
    to v1's priming margin.
  - **The green line stays 3/8"** where it enters the inner-pot tube — that diameter is
    fixed by the pot. Only the probe; the main run is 1/2". The printed filter housing is
    the transition (3/8" barb pot-side, 1/2" barb pump-side).
- [x] 🎒 **Hose clamps — 5574K13 — ALREADY OWNED, still correct** — McMaster, worm-drive,
  smooth-band, 304 SS, 1/2"–3/4" ID. Centres nicely on 1/2" barb + tubing OD.
- [ ] 🎒 **Uniseal — size TBD once a Scepter panel is measured**
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

## 4. Sensing & UI  *(🎒)*

- [ ] 🎒 **XKC-Y25-V (or similar) non-contact capacitive liquid level sensor — qty 1**
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
- [x] 🎒 **Inline fuse holder — 8110K3** — McMaster, ATC blade, 1–20 A, 32 V, $4.34.
  Splices into battery **+** before the board.
- [x] 🎒 **10 A blade fuse — 7460K45** — McMaster, ATC, 32 V, fast-acting, 5-pack, $3.83.
- [x] 🎒 **M2×20 socket screws — OWNED** (McMaster 91292A013) · **M2 heat-set inserts —
  OWNED** (McMaster 94459A110, brass, 2.5 mm).

## 6. Main PCBA  *(🎒, NEW in v2 — single board)*

Fab: **JLCPCB**. Prefer Basic/Preferred library parts to avoid extended-part fees.
Exact part numbers to be fixed at layout; this is the functional list.

- 2× **N-channel MOSFET**, 40 V, low R<sub>DS(on)</sub>, DPAK/TO-263 on a copper pour —
  one per pump. **No H-bridge**: each pump runs one direction only (direction is chosen
  by *which pump* is energised), so a single switched leg replaces the BTS7960.
- 2× **gate driver** — 7.5 A at 20 kHz is not a job for a bare 3.3 V GPIO
- 2× **Schottky freewheel diode**. Plain, not synchronous: it conducts only during
  off-time and usage is mostly full-on.
- 1× **synchronous buck, 18 V → 3.3 V, ~1 A**, rated **≥36 V in** — a fresh Makita pack
  is 20 V and inductive spikes exceed that, so 24 V-max parts (MP2315, AP63203) are too
  close to the edge. LMR14030 / TPS54360 class.
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
- Reverse-polarity P-FET, TVS, bulk electrolytics at the switches.
- 6-pin programming header with DTR/RTS. **No USB-C** — a connector is a water-ingress
  path outdoors, and OTA covers everything after bring-up.
- Connectors: **push-in terminal blocks, not JST** — 5.08 mm for battery and each
  pump (7.5 A), 3.5 mm for joystick (5-pos) and level sensor (4-pos). Every one of
  these is landed once at assembly, so JST's plug/unplug advantage doesn't apply,
  and a terminal is ONE part with no mating half to stock (PCB_README §3 warns that
  a joint where you supply both halves is where the catalogue is worst). Spring-cage
  over screw: two motors share this frame and screw clamps back off under vibration.
  They give no strain relief, so the shroud needs a cable anchor behind them.
- *Optional:* low-side shunt per pump → ADC.

## 7. Structure  *(🎒)*

- [x] 🎒 **Stansport Freighter aluminium pack frame — OWNED.** 820 × 400; shelf 340 wide
  × 250 deep.
- [x] 🎒 **Scepter 5 gal military water can — OWNED.** Base ≈ 348 × 173 mm, standing on
  **two wide ribs** (one at the frame edge, one at the far edge) — two line loads, which
  the frame's two cross-beams land on.
- Printed in **PCTG**, in shade. Tougher than PETG at the stress risers that matter here
  (hose openings, corners) and Tg ~85 °C. **Not PLA** — 21 kg of sustained load near
  PLA's 60 °C Tg creeps.

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
- ~~**McMaster 5346K56 barbed adapters** (3/8" hose × 1/2 NPT female)~~ — superseded by
  the Shurflo swivels. These are the brass fittings that thread hard into the plastic
  ports.
- ~~**Beduan 5/8"→3/8" barb reducers ×4**~~ — v1 necked the whole system down to its
  narrowest element in four places. v2 runs 1/2" throughout with one transition, inside
  the printed filter housing.
- ~~**McMaster 4912K34 ball valve**~~ — dropped during v1. Killswitch is unplugging the
  Makita battery; the diaphragm check valves block flow when off, so there's no siphon.
- ~~**YF-S201 flow sensor**~~ — dropped during v1; open-loop PWM was sufficient.

---

*Last updated: 2026-10-03 (v2 architecture)*
