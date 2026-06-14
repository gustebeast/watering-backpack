# Consolidated Parts List — by Vendor

Two projects on one buying run. Tags keep them separate:
- 🎒 = **Watering Backpack**
- 🐱 = **Cat Bed Weight Sensor**

---

## 1. McMaster-Carr  *(all 🎒)*

McMaster part numbers aren't stable to deep-link, but their site search is fast.
Search the **bold term**, then apply the filters in parentheses.

- ~~🎒 Valve — McMaster 4912K34~~ — **DROPPED.** Killswitch = unplug the Makita battery (diaphragm pump check-valves block flow when off, no siphon). Removes a joint + simplifies housing. (−$10.27)
- [x] 🎒 **Barbed adapters — both ports: 5346K56** — 3/8" hose × 1/2" NPT **female**, brass, crimp-style barb (worm-clamp works fine), **pack of 5, $23.68** — one onto each pump port (suction + forward).
  - Both ports are 1/2" MALE NPT → need female barbs → 2× 5346K56 (covered by the pack of 5).
  - Replaced the old male SS barb (5361K38) — that only worked with the now-dropped valve as a gender adapter. (−$13.34)
  - Vacuum "Not Rated" is a catalog gap, not a real concern at these gentle vacuums; tubing already passed the vacuum test.
- Tank: **open, top-routed line + small vent hole** (decided) — no bulkhead, strainer foot handled separately.
- [x] 🎒 **Hose clamps — LOCKED IN: 5574K13** — Worm-Drive, smooth-band (soft hose), 304 SS, ID range 1/2"–3/4" (centers on your ~5/8" clamped OD), pack of 10, $18.20. *(If OD-with-barb measures nearer 1/2", 5574K12 (5/16"–5/8") centers better.)*
- [x] 🎒 **Inline fuse holder — LOCKED IN: 8110K3** — Automotive inline holder, Standard/ATC blade, 1–20A, **32V** (headroom over 20V Makita; indicator models are only 12V-rated), 16 AWG leads, cover, $4.34. Splices into battery **+** lead before the buck.
- [x] 🎒 **10A blade fuse — LOCKED IN: 7460K45** — Standard/ATC (257/AF/ATC/ATO), 10A, **32V**, fast-acting, pack of 5, $3.83. Drops into the 8110K3 holder.
- [x] 🎒 **Tubing — OWNED (Ace ProLine 3/8" ID × 1/2" OD vinyl)** — passed vacuum test (stays open under full mouth vacuum), good for both pressure and suction lines. Braided **not needed**. *(Watch for line flattening only under hard dead-head reverse vacuum, e.g. clogged sieve.)*
- Tip: McMaster homepage → [mcmaster.com](https://www.mcmaster.com) → paste the search term in the top search bar; left-rail filters appear automatically.

## 2. DigiKey  *(all 🐱)*
- [x] 🐱 **Crydom CX240D5 SSR** — PCB-mount, 240 VAC / 5A, DC control, SPST-NO 4-SIP — $21.62 — https://www.digikey.com/en/products/detail/sensata-crydom/CX240D5/139586
  - **Driven via transistor** (3.3V GPIO too low for the SSR input). Topology: GPIO →[1kΩ]→ 2N3904 base; emitter→GND; collector→SSR ctrl(−); SSR ctrl(+)→+5V.
- [x] 🐱 **Interlink FSR 406** (1.5" square, solder tabs) — DK# **1027-1002-ND**, MPN 30-73258, $10.08 — https://www.digikey.com/en/products/detail/interlink-electronics/30-73258/2476470
- [x] 🐱 **2N3904 NPN transistor** (SSR driver) — $0.14 — https://www.digikey.com/en/products/detail/diotec-semiconductor/2N3904/13164701
- [x] 🐱 **10 kΩ resistor, 1/4 W** (FSR divider) — $0.10 — https://www.digikey.com/en/products/detail/stackpole-electronics-inc/CF14JT10K0/1741265 — *may re-tune for the larger FSR 406*
- [x] 🐱 **1 kΩ resistor, 1/4 W** (2N3904 base) — $0.10 — https://www.digikey.com/en/products/detail/stackpole-electronics-inc/CF14JT1K00/1741314
- *Cat-project DigiKey subtotal: **$32.04***

## 2a. Owned — fastening hardware  *(🎒)*
- [x] 🎒 **M2×20 socket screws — OWNED** (McMaster 91292A013, 18-8 SS) — **6× used** on the electronics tray: 2× ESP32 clamp beam, 2× BTS7960 board, 2× buck board (user confirmed M2 fits the BTS + Pololu holes).
- [x] 🎒 **M2 heat-set inserts — OWNED** (McMaster 94459A110, brass, 2.5mm installed) — **6× pressed flush** into the standoff/post tops (Ø3.2 pilot bores printed in the tray; Ø2.4 clearance below each for the long shank).

## 2b. Owned — logic power  *(🎒)*
- [x] 🎒 **Traco TSR 1-2450E — OWNED** — 5V/1A switching regulator, SIP-3 (≈11.7×7.6×10.2mm), 6.5–36V input. Feeds the ESP32 5V pin **straight from the fused battery rail** (not the 12V pump rail — keeps logic clean when the pump loads the buck). Closes the "no 5V source" gap found during the wiring plan. Zip-ties into the harness beside the ESP32 (tray has anchor slots).

## 3. Pololu  *(🎒)*
- [x] 🎒 **D42V110F12 buck regulator, 12V/9A** — $59.95, 12–60V input, "Active & Preferred" — https://www.pololu.com/product/5677
  - Chosen over the older D24V150F12 (15A, $79.95, Rationed): newer, cheaper, in stock, same size/pinout, higher input ceiling.
  - 9A vs 7.5A pump peak is ~1.2× headroom — fine for typical 2–5A watering, but **add a heatsink / ensure airflow** for high-pressure peaks. Real operating current is well below the 7.5A max most of the time.

## 4. AliExpress  *(all 🎒)*
- [x] 🎒 **Joystick — LOCKED IN:** KY-023 dual-axis XY module ("1-5PCS Higher Quality PS2 ... KY-023")
  - Link: https://www.aliexpress.us/item/3256809150872159.html
  - $0.99 (2PCS option), import charges included, 5.0★
  - **Buy the 3PCS or 4PCS SKU** for spares (only need the VRy axis)
  - Wiring: power from ESP32 **3.3V** (NOT 5V) → output maxes at 3.3V, safe into ADC1. VRy → GPIO 32–39.
- [x] 🎒 **BTS7960 — LOCKED IN & VERIFIED:** "Double BTS7960" 43A H-bridge module (EGBO) — $4.91/1pc ($1.93 was new-shopper promo), 4.9★, 135 reviews, 3,000+ sold — item 1005007038406337 (https://www.aliexpress.us/item/1005007038406337.html)
  - **Pick the 2PCS SKU** for a spare power stage. 43A rating ≫ 7.5A pump.
  - Wiring: **VCC → 5V** (ESP32 5V tap, NOT 3.3V), GND common; **R_EN+L_EN → tie to 5V** (enable); **RPWM = forward PWM, LPWM = reverse PWM** (never both high); R_IS/L_IS unconnected for v1.
  - **3.3V PWM confirmed working** (buyer review) → drive RPWM/LPWM straight from ESP32, no level shifter needed.
- ~~🎒 YF-S201 flow sensor~~ — **DROPPED** (not needed; open-loop PWM control is sufficient for v1).

## 5. eReplacementParts  *(🎒)*
- [x] 🎒 **Makita 643852-2 terminal — LOCKED & VERIFIED — qty 2** (one spare), $8.84 ea = ~$17.68, confirmed in stock, sold individually (supersedes 643859-8), ERP10153397 — https://www.ereplacementparts.com/parts/drill/makita/erp10153397/terminal-643852-2/

## 6. Seaflo Direct  *(🎒)*
- [x] 🎒 **Seaflo 42-Series pump — LOCKED & VERIFIED — SFDP1-030-055-42, $74.99** — https://seaflodirect.com/seaflo-42-series-diaphragm-water-pressure-pump-3-0-gpm-55-psi-choose-12v-or-24v/
  - ⚠️ **Select 12V** in the required Voltage dropdown (not 24V).
  - ⚠️ **Bypass the internal automatic pressure switch** — it cuts the pump on downstream pressure, fighting PWM + blocking reverse flow (gotcha #5).
  - 📦 Includes: **50-mesh inlet strainer** (covers the tank-side strainer you planned to source) + **2× 1/2" barb adapters** (1/2" hose, NOT 3/8" — spares only; your 3/8" reducers still needed).

---

*Last updated: 2026-05-26*
