/*
 * pins.cpp — one line of setup per pin, and the reason it is legal next to it.
 *
 * Citation keys are defined at the top of pins.h (NET, DS-M, DS-C, IDF).
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * §1  ADC UNIT AND CHANNEL FOR BOTH ANALOGUE INPUTS  — the one that would be a
 *     board re-spin, so it is stated first and exactly.
 *
 *     VBAT_SENSE  NET: U2 pin 7   DS-M Table 3: "IO35  7  I  GPIO35, ADC1_CH7,
 *                 RTC_GPIO5"                      ->  ADC *1*, channel 7
 *     JOY_FILT    NET: U2 pin 6   DS-M Table 3: "IO34  6  I  GPIO34, ADC1_CH6,
 *                 RTC_GPIO4"                      ->  ADC *1*, channel 6
 *
 *     Both are on ADC1. IDF, "Hardware Limitations": "ADC2 is also used by
 *     Wi-Fi." Nothing on this board's analogue path touches ADC2, so WiFi
 *     telemetry and OTA cost nothing. This is the pass, not a workaround.
 *
 *     For completeness, the ADC2 pads that ARE populated on this board carry
 *     digital signals only: IO14 (ADC2_CH6) is read with digitalRead, IO25
 *     (ADC2_CH8) / IO26 (ADC2_CH9) / IO27 (ADC2_CH7) are driven. DS-C Appendix A
 *     Table IO_MUX gives those alternate analogue functions; none is selected,
 *     so the WiFi/ADC2 conflict does not reach them.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * §2  STRAPPING PINS, TESTED RATHER THAN ASSERTED.
 *
 *     DS-M §4 names five: GPIO0, GPIO2, MTDI (=GPIO12), MTDO (=GPIO15), GPIO5.
 *     DS-M Table 4 gives the level each one takes with nothing on it, because
 *     "the default values of the strapping pins ... are determined by pins'
 *     internal weak pull-up/pull-down resistors at reset if the pins are not
 *     connected to any circuit".
 *
 *     Working the actual boot state out of the netlist, pin by pin:
 *
 *     GPIO0  (mod 25) net IO0 -> J6.6 and nothing else. No resistor, no cap, no
 *            transistor on the net. With the programmer unplugged the pad sees
 *            only its own pull-up: DS-C IO_MUX row 23 gives GPIO0 "At Reset:
 *            oe=0, ie=1, wpu", DS-M Table 4 gives default 1. DS-M Table 6:
 *            GPIO0 = 1 -> SPI Boot Mode, GPIO2 "any value". So it boots from
 *            flash. With the programmer plugged in, its DTR/RTS pair drives IO0
 *            low and EN low to enter Joint Download Boot — which is the point of
 *            the header. VERDICT: correct both ways. Firmware never configures
 *            it; there is deliberately no IO0 constant in pins.h.
 *     GPIO2  (mod 24) absent from the netlist — unconnected. Internal pull-down,
 *            default 0 (DS-M Table 4; DS-C IO_MUX row 22 "oe=0, ie=1, wpd").
 *            DS-M Table 6 only consults GPIO2 when GPIO0 = 0, and in that case
 *            it needs 0, which is what it has. VERDICT: correct.
 *     GPIO12 (MTDI, mod 14) absent from the netlist — unconnected. Internal
 *            pull-down, default 0 (DS-M Table 4; DS-C IO_MUX row 18 "oe=0,
 *            ie=1, wpd"). DS-M §4.2: MTDI = 0 powers VDD_SDIO from VDD3P3_RTC,
 *            i.e. 3.3 V. The module's flash is a 3.3 V part, so 0 is the
 *            required value. This is the strapping pin that bricks a board when
 *            something pulls it up; nothing here can. VERDICT: correct.
 *     GPIO15 (MTDO, mod 23) absent from the netlist — unconnected. Internal
 *            pull-up, default 1 (DS-M Table 4; DS-C IO_MUX row 21 "oe=0, ie=1,
 *            wpu"). DS-M §4.3 Table 7: MTDO = 1 enables U0TXD boot printing,
 *            which is wanted — bring-up is over J6 and the ROM log is the first
 *            thing read. VERDICT: correct.
 *     GPIO5  (mod 29) absent from the netlist — unconnected. Internal pull-up,
 *            default 1 (DS-M Table 4; DS-C IO_MUX row 34 "oe=0, ie=1, wpu").
 *            DS-M §4.4 Table 8 uses MTDO+GPIO5 only for SDIO *slave* timing;
 *            this chip is never an SDIO slave. VERDICT: don't-care, and it has
 *            the documented default anyway.
 *
 *     So the sign-off's claim ("no pump gate or the buzzer lands on a strapping
 *     pin") is true — 25/26/27 are not strapping pins — but it is also the weaker
 *     half of the question. The half that matters is whether the five strapping
 *     pads reach the right level at reset, and all five do, four of them by
 *     being left unconnected on purpose and one by the programming header.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * §3  WHAT HAPPENS BEFORE THIS FUNCTION RUNS — the gap pinsInit() cannot close.
 *
 *     DS-C Appendix A Table IO_MUX, "At Reset" column:
 *       GPIO25 row 14: oe=0, ie=0    GPIO26 row 15: oe=0, ie=0
 *       GPIO27 row 16: oe=0, ie=0    GPIO14 row 17: oe=0, ie=0
 *     i.e. all four sit high-impedance with NO internal pull from reset until
 *     this function runs. Firmware therefore cannot be the thing that keeps a
 *     pump off during boot, and on this board it is not asked to be:
 *       PWM_A/PWM_B land on U3/U4 IN+ (UCC27517, TI SLUSAY4D), whose features
 *       list includes "Output Held Low When Input Pins Are Floating" — internal
 *       pull-down on IN+ — and R6/R7, 100k from each FET gate to GND, hold the
 *       gate down even if a driver were unpowered. Two independent reasons.
 *       BUZZ lands on R24 (1k) into Q3's base, an MMBT3904. A base fed through
 *       1k from a high-Z pad gets no base current, so Q3 is off. This is why the
 *       buzzer needs no base pull-down where the pumps needed R6/R7: a BJT's
 *       base resistor is already the pull-down's job, a MOSFET gate's is not.
 *       LEVEL is held up by R23 (10k to 3V3), which reads "not full" — the safe
 *       state — through reset, before pinsInit, and if the sensor is unplugged.
 */
#include "pins.h"

void pinsInit() {
  // ── Outputs first, to a known-safe state, before anything can command them ──

  // PUMP_A_PIN / PUMP_B_PIN — GPIO26 (mod 11) and GPIO25 (mod 10).
  // MODE: OUTPUT driven LOW, then handed to LEDC for PWM.
  // WHY: DS-M Table 3 lists both as Type "I/O", so they can drive; DS-C IO_MUX
  // rows 15 and 14 give drive strength 2'd2 (20 mA) against the UCC27517's
  // CMOS input, which needs microamps. Not input-only (DS-C Table 6-1 note 2
  // covers 34-39 only), not strapping (DS-M §4 lists 0/2/12/15/5), not part of
  // the flash bus (DS-M Table 3 note 2: GPIO6-11 are not led out, pins 17-22
  // are NC). LEDC is a GPIO-matrix peripheral, so any output-capable pad can
  // carry it — DS-M §5.2.8 LED PWM Controller, 16 channels, no fixed pads.
  // WHY LOW-THEN-ATTACH: ledcAttach leaves the pad driven from the LEDC channel
  // whose duty is undefined until the first ledcWrite. Driving the pad low as a
  // plain GPIO first means the gate driver sees a defined 0 for the whole window.
  pinMode(PUMP_A_PIN, OUTPUT); digitalWrite(PUMP_A_PIN, LOW);
  pinMode(PUMP_B_PIN, OUTPUT); digitalWrite(PUMP_B_PIN, LOW);

  // BUZZ_PIN — GPIO27 (mod 12).
  // MODE: plain OUTPUT, driven LOW. No PWM.
  // WHY: the fitted part is an ACTIVE buzzer (BZ1, 3V-ACTIVE) — it generates its
  // own 2.7 kHz, so it wants DC, not a waveform; a driven tone would beat against
  // its own oscillator. DS-M Table 3 lists IO27 as "I/O", so it can drive, and
  // 20 mA (DS-C IO_MUX row 16, 2'd2) is ample for Q3's base through R24's 1k
  // (~2.6 mA), which is the only current this pad sources — the buzzer's ~30 mA
  // comes off +3V3 through Q3's collector, not off the pad.
  pinMode(BUZZ_PIN, OUTPUT); digitalWrite(BUZZ_PIN, LOW);

  // ── Digital input ──────────────────────────────────────────────────────────

  // LEVEL_PIN — GPIO14 (mod 13), DS-M Table 3 "MTMS, ADC2_CH6, TOUCH6, ...".
  // MODE: INPUT_PULLUP.
  // WHY INPUT: it is the tank-level sense, read only. Never driven, so IO14's
  // JTAG (MTMS) and HSPICLK alternate functions are irrelevant — none is
  // selected, and with EFUSE_DISABLE_JTAG unburnt the JTAG pads are still just
  // GPIOs until a debugger is attached (DS-M §4.5).
  // WHY PULL-UP IS AVAILABLE HERE AT ALL: IO14 is a full bidirectional pad, so
  // it has the internal pull resistors that DS-C Table 6-1 note 2 says GPIO34-39
  // do NOT have — "These pins do not feature an output driver or internal
  // pull-up/pull-down circuitry". That note is why the two analogue signals had
  // to come with external dividers and why a pull-up sense input could not have
  // gone on 34-39.
  // WHY PULL-UP AND R23 BOTH: R23 (10k to 3V3) is the real pull-up and the only
  // one that exists during reset, since DS-C IO_MUX row 17 gives IO14 "At Reset:
  // oe=0, ie=0" — no pull at all. The internal one (~45k) is in parallel and
  // only matters on a bench with no sensor wired. It is NOT a substitute for
  // R23: R23 -- now one of three 100k in series, a 300k pull-up, with R26 = 100k
  // in series into this pin and D7 clamping it to the rails (finding 30) -- is
  // what lets the external NPN inverter hold the pin at 3V3 instead
  // of the sensor's InVCC = VBAT (CIRCUIT.md §4).
  // WHY NOT ANALOGUE: IO14 is ADC2_CH6, and IDF "Hardware Limitations" rules
  // ADC2 out while WiFi is up. It is read with digitalRead, so the conflict
  // never arises — this pin is the reason the ADC-unit check has to be against
  // the pin's ROLE, not merely its capability.
  // !! INPUT, NOT INPUT_PULLUP, AND THE CHANGE IS FINDING 30'S. This was
  // INPUT_PULLUP, and while the pin sat directly on the open collector that was
  // harmless -- the internal pull (~45k, 30-80k) simply paralleled the external
  // one. Finding 30 put R26 = 100k IN SERIES between LEVEL and this pin, so the
  // internal pull-up is no longer in parallel with anything: it is on the FAR
  // side of R26 and forms a divider with it. With the collector hard low:
  //
  //   internal Rpu   pin sits at
  //   30k            2.14 V
  //   45k (typ)      1.83 V
  //   80k            1.39 V
  //
  // VIL is 0.25 x VDD = 0.825 V, so the pin never comes within 0.5 V of a low at
  // any pull value -- it parks in the Schmitt dead band. LEVEL_FULL_IS_LOW would
  // never assert and tank-full would never fire. tools/check_level_alarm.py
  // passes regardless, because it drives the debounce state machine with
  // injected booleans and never models the pin's electrical level.
  //
  // The external 300k provides the high; no internal pull is wanted or helpful.
  // (M35 notes erratum GPIO-3.6 may mean the internal pull on IO14 is not there
  // at all, which would make this differ by IDF version -- worse than either
  // outcome. INPUT is deterministic.)
  pinMode(LEVEL_PIN, INPUT);

  // ── Analogue inputs (see §1 above for unit and channel) ────────────────────

  // 12-bit, the ESP32's native SAR width (DS-C §4.9.1: "two 12-bit SAR ADCs").
  analogReadResolution(ADC_RES);

  // VBAT_PIN — GPIO35 (mod 7), ADC1_CH7.
  // MODE: analogue input. NO pinMode call, deliberately.
  // WHY NO pinMode: DS-C Table 6-1 note 2 — GPIO34-39 have no output driver and
  // no internal pull-up/pull-down, so OUTPUT would be dead silicon and
  // INPUT_PULLUP a silent no-op. Arduino's analogRead path selects the ADC pad
  // function itself. The pin is held at a defined level by R20/R21 (100k/10k
  // off VBAT) regardless, which is the only pull it has or needs.
  // WHY 11 dB: the divider puts a fresh 20 V pack at 1.82 V; a narrower
  // attenuation would clip and read the pack as flatter than it is, which would
  // RAISE the duty cap. 11 dB is the full ~3.3 V span (DS-C §4.9.1).
  analogSetPinAttenuation(VBAT_PIN, ADC_11db);

  // JOY_PIN — GPIO34 (mod 6), ADC1_CH6.
  // MODE: analogue input. NO pinMode call, same reason as VBAT_PIN.
  // WHY INPUT-ONLY IS FINE: the only thing ever done to this pad is analogRead;
  // nothing in the firmware drives it, so DS-C Table 6-1 note 2 costs nothing.
  // WHY ADC1 MATTERS MOST HERE: this is the control path. A joystick on ADC2
  // would not fail loudly with WiFi up — it would return stale or zero samples,
  // and zero reads as "stick centred", which looks like working firmware.
  // The pad has no internal pull (note 2 again), so J4's 3V3 feed plus R22/C12
  // (1k + 100n, ~1.6 kHz corner) are what define it; an unplugged joystick
  // leaves it floating, which measureCentre() is what copes with.
  analogSetPinAttenuation(JOY_PIN, ADC_11db);

  // UART0 — GPIO1/TXD0 (mod 35) and GPIO3/RXD0 (mod 34), nets ESP_TX_TO_PROG
  // and ESP_RX_FROM_PROG (the latter through R25, 1k series). Not configured
  // here on purpose: Serial.begin() owns both pads, and DS-C IO_MUX rows 40/41
  // give them "At Reset: oe=0, ie=1, wpu", so the ROM bootloader's log works
  // before any of our code runs. Orientation checked against the netlist: U2
  // pin 35 is TXD0 and goes to J6.3 (the programmer's RX); U2 pin 34 is RXD0 and
  // comes from J6.4. Not crossed.
}
