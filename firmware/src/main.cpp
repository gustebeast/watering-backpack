/*
 * Watering-backpack pump controller — v2 board
 * ESP32-WROOM-32E + two low-side pump FETs + single-axis analog joystick.
 *
 * TWO PUMPS, ONE AXIS. A diaphragm pump cannot be reversed — its check valves
 * are passive — so DESIGN_V2.md §1 puts two of them in anti-parallel across
 * shared tees and direction becomes which pump you run:
 *
 *     stick hard FORWARD -> pump A, tank -> pot   (water the plant)
 *     stick hard BACK    -> pump B, pot  -> tank  (suck the line back)
 *     stick near centre  -> neither
 *
 * The idle pump's own check valves seal its branch. Running both at once would
 * make them fight through the shared tees and pull 2 x 7.5 A off one pack, so
 * the interlock is structural: drivePumps() is the only thing that can raise a
 * gate, and it writes BOTH pins on every call. Every direction change also
 * passes through "neither" and waits out DIR_DEAD_MS, so there is no A->B edge
 * in the state machine at all.
 *
 * tools/check_pump_dirs.py drives traces through a transcription of that state
 * machine — including the flick straight from hard-forward to hard-back, which
 * crosses the release band faster than the release vote can see it.
 *
 * PUMP VOLTAGE IS REGULATED. The pumps are 12 V and the pack is 15-20 V, so the
 * duty ceiling tracks the pack through the VBAT divider on IO35 and holds the
 * average armature voltage at 12 V (see "Pump voltage regulation"). Until this
 * existed, RUN_DUTY was PWM_MAX and every engage put the whole pack across a
 * 12 V pump.
 *
 * THIS IS NOW v2-ONLY. It will not drive v1's QuinLED + BTS7960 rig: that had
 * one pump and a manual X-port valve, and the enable pin this used to hold HIGH
 * (IO4) is connected to nothing on the v2 board, so it is gone.
 *
 * TANK-FULL ALARM. IO14 reads the capacitive level sensor and IO27 beeps the
 * buzzer while it reads full. That is the spigot-fill overflow alarm from
 * elec/CIRCUIT.md §5 — "filling happens with the pump OFF and the user standing
 * at the tank" — so it runs independently of `armed`, which inhibits the pumps.
 *
 * It is deliberately NOT an interlock on either pump. DESIGN_V2.md §7 accepts
 * false positives because for FILLING they are cheap ("stop early, look, carry
 * on"), but a false positive that blocked pump B would block retract, leaving a
 * primed line to drip — not cheap, and not a trade that section asked for.
 *
 * The debounce is asymmetric and tools/check_level_alarm.py is where it is
 * checked: the tank rides on someone's back and §7 puts the sensor BELOW the
 * full line on purpose, so the threshold gets crossed early and often.
 *
 * Pins, from elec/main.py — the schematic is the authority, not this comment:
 *   IO26  -> pump A gate driver   (tank -> pot)
 *   IO25  -> pump B gate driver   (pot  -> tank)
 *   IO35  -> VBAT_SENSE, off the R20/R21 divider (ADC1, input-only)
 *   IO34  -> joystick SIG, after its RC filter   (ADC1, input-only)
 *   IO14  -> tank level, open-collector, R23 pulls it up to 3V3
 *   IO27  -> buzzer, through Q3
 *   EN / IO0 / RXD0 / TXD0 -> programming header
 *
 * ── NOISE REJECTION ──────────────────────────────────────────────────────────
 * This joystick's wiper sits on ~100 counts of RMS noise (peaks past +-450),
 * roughly 7x a healthy pot. Measured characteristics that drove the design here:
 *
 *   - Noise is WHITE: mean|sample-to-sample diff| / stdev came out at 1.128, the
 *     exact ratio for uncorrelated Gaussian noise. So it averages down as sqrt(N)
 *     and its excursions are single-sample events.
 *   - Excursions over the deadband last 1-2 samples (never longer).
 *   - Noise amplitude is FLAT across stick travel and does NOT scale with wiper
 *     position, which excludes both pot source impedance and 3V3 supply noise,
 *     and points at the ground reference. It is a hardware fault; everything
 *     below is a workaround that makes the controller immune to it, not a cure.
 *
 * The original failure mode was noise RECTIFYING into motion: the control law
 * was forward-only, so symmetric noise became a one-sided command, and the ramp
 * integrator ratcheted those one-sided kicks upward into a slow, self-sustaining
 * pump creep. The control law now closes that off:
 *
 * (The law is no longer one-sided -- reverse is live -- so symmetric noise no
 * longer rectifies. It does mean there are now TWO ways to false-trigger rather
 * than one, so the spurious-engage rate below doubles: ~1.2e-10 per window
 * instead of ~6e-11, or roughly one per year of continuous running instead of
 * one per two. Both are noise against the vote clearing it in ~25 ms, and a
 * spurious REVERSE while a pump is running only ever stops it, which is the
 * safe direction.)
 *
 *   1. K-of-N MAJORITY VOTE on the raw samples decides on/off. Because the noise
 *      is white, samples are independent, so requiring 6 of the last 10 samples
 *      past the threshold drives the false-trigger rate to ~1 per 2 years while
 *      costing only a 50 ms window. A smoothing filter would have needed ~185 ms
 *      of lag for worse rejection.
 *   2. HYSTERESIS — separate engage (300) and release (180) thresholds, so the
 *      decision cannot chatter at the boundary.
 *   3. NO INTERMEDIATE DUTY. The stick is used hard-forward or hard-back, so
 *      engaged means RUN_DUTY and nothing else. A slow trickle is no longer a
 *      state the controller can represent, which is a stronger guarantee than
 *      making it improbable.
 *   4. The ramp integrator no longer spans the on/off edge — it only shapes the
 *      soft start. Stopping is an immediate cut, which is both the responsive and
 *      the safe direction.
 *
 * Switch-on latency is ~50 ms of vote plus ~105 ms of soft-start ramp; switch-off
 * is ~25 ms and immediate.
 *
 * ── REMOTE DEBUG ─────────────────────────────────────────────────────────────
 * WiFi is strictly a diagnostic side-car. The control loop runs first and
 * unconditionally, so the backpack works with no network, a wrong password, or no
 * AP in range — nothing on the control path blocks on WiFi.
 *
 *   OTA flashing : ArduinoOTA. Motor forced OFF before an update is accepted.
 *   Telemetry    : raw TCP on port 23. Reports stats over EVERY loop sample
 *                  (~200/s) for BOTH the raw and filtered signals, so the
 *                  filter's effect can be measured directly.
 *   ARM / DISARM : `d` inhibits the motor while telemetry keeps running. Stored
 *                  in NVS and SURVIVES REBOOT — an OTA push reboots the board,
 *                  and coming back armed mid-test would spray water.
 *
 * ADC1 is used for the joystick (GPIO34) — the half of the ESP32 ADC that stays
 * usable while the radio is on.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include <math.h>
#include "secrets.h"
#include "pins.h"

// ── Pin map ──────────────────────────────────────────────────────────────────
// Lives in pins.h, which carries the module-pin table out of elec/out/main.net
// and the datasheet reason for every pin's mode. JOY_PIN, VBAT_PIN, LEVEL_PIN,
// BUZZ_PIN, PUMP_A_PIN, PUMP_B_PIN, PWM_FREQ, PWM_RES and ADC_RES come from
// there; pinsInit() in pins.cpp is what configures them.
//
// One low-side MOSFET per pump, each behind its own non-inverting gate driver,
// so PWM high = that pump runs. No H-bridge and NO ENABLE PIN: a diaphragm pump
// cannot be reversed (DESIGN_V2 §1 — the check valves are passive), so direction
// is WHICH PUMP YOU RUN. v1's EN on IO4 is connected to nothing on the v2 board
// and is gone.

// ── PWM (LEDC, pin-based API = Arduino-ESP32 3.x) ────────────────────────────
constexpr int PWM_MAX  = (1 << PWM_RES) - 1;
constexpr int DUTY_CAP = PWM_MAX;            // lower to cap max pump speed (e.g. 200)

// ── Pump voltage regulation ──────────────────────────────────────────────────
// The pumps are 12 V. The pack is 15-20 V. elec/CIRCUIT.md §1: "Duty is capped
// in firmware to synthesise 12 V from an 18-20 V pack. PWM already chops the
// supply, so the motor does not care -- but the cap must track the pack voltage,
// which is what the divider below is for."
//
// Nothing was tracking it. RUN_DUTY is PWM_MAX, so every engage put the whole
// pack across a 12 V pump: 1.7x rated on a fresh one. The divider has been on
// the board the entire time -- R20/R21, 100k/18k into IO35, with C11 across the
// bottom leg -- and no line of firmware read it.
//
// For a PWM'd brushed motor with a freewheel path the average armature voltage
// is duty x V_pack, which is what makes the cap a one-liner:
//
//     pack 20.0 V -> cap 153  (60 %)
//     pack 18.0 V -> cap 170  (67 %)
//     pack 15.0 V -> cap 204  (80 %)
//
// CIRCUIT.md gives the divider a second job as well -- "expose sag in telemetry.
// This would have diagnosed v1's mid-run slowdown in thirty seconds" -- so the
// pack voltage and the live cap are both on the 's' status line.
constexpr float PUMP_V_NOM  = 12.0f;         // pump nameplate
constexpr float RDIV_TOP_K  = 100.0f;        // R20, from elec/main.py
// !! 10k, AND IT WAS 18k HERE LONG AFTER THE BOARD STOPPED BEING 18k. Punchlist
// finding 33 took R21 to 10k (elec/main.py RDIV_TOP, RDIV_BOT) to keep the whole
// 15-21 V range inside the ADC's linear band. The punchlist claimed "the quality
// declaration, the assert and THE FIRMWARE'S SCALING all follow automatically"
// from that one constant. The first two do. This one is hand-typed, and it did
// not follow.
//
// What a stale 6.5556 did, measured across the pack range:
//
//   real pack   IO35     this file read   plausible?   duty cap   motor saw
//   15.00 V     1.364    8.94 V           NO -> 20 V   153        9.00 V
//   16.78 V     1.525    10.00 V          yes          255        16.78 V
//   20.00 V     1.818    11.92 V          yes          255        20.00 V
//
// Above ~16.8 V the cap saturates at PWM_MAX and every engage puts the WHOLE PACK
// across a 12 V pump -- 1.67x rated, which is verbatim the failure the comment
// below says this cap exists to prevent. Below that it reads as a divider fault
// and under-drives instead. A fresh pack would most likely have blown the 10 A
// ATO blade before it cooked the pump, which is luck, not design.
//
// !! THIS CONSTANT IS A COPY OF A BOARD VALUE AND NOTHING COMPARES THEM.
// tools/check_pin_map.py ties this firmware to the schematic, but only by PIN
// NUMBER -- it never reads a component value, so no gate in the repo covers this
// line. If the divider moves again, this is the second place to change.
constexpr float RDIV_BOT_K  = 10.0f;         // R21
constexpr float VBAT_SCALE  = (RDIV_TOP_K + RDIV_BOT_K) / RDIV_BOT_K;   // 11.000
// Plausibility window. An open divider reads ~0 and a shorted one reads full
// scale, and in either case the cap falls back to the value for the HIGHEST
// expected pack -- the LOWEST duty. A sensor fault must never be able to raise
// the duty, which is why the fallback is not PWM_MAX.
constexpr float VBAT_PLAUS_LO = 10.0f;
constexpr float VBAT_PLAUS_HI = 22.0f;       // the divider saturates at 21.6
constexpr float VBAT_ASSUMED  = 20.0f;       // fresh pack: the safe assumption
constexpr int   VBAT_EVERY_N  = 20;          // 5 ms loop -> read every ~100 ms
constexpr float VBAT_EMA_A    = 1.0f / 16.0f;   // slow; the pack sags slowly

// ── Joystick / control tunables ──────────────────────────────────────────────
constexpr int ADC_MAX   = (1 << ADC_RES) - 1;   // 4095  (ADC_RES: pins.h)
// Soft-start rate, in duty counts per 5 ms loop. This shapes only the RISE to full
// speed; it is NOT on the switch-on latency path in any meaningful sense and it is
// not used at all when stopping (stopping is an immediate cut). Keeping some ramp
// matters: slamming a stalled pump motor to full duty draws several times running
// current, and the resulting battery sag can brown out the ESP32 through the TSR.
// 12 gives ~105 ms from stopped to full. The original firmware used 4 (~320 ms),
// which already felt instantaneous, so there is margin to slow this down if the
// pump ever trips the supply.
// The ramp IS the flow control. There is no proportional stick, so dose is set by
// how long the stick is held: a quick flick gives a small plant a splash-free
// trickle, a longer hold winds up to full.
//
// START_DUTY is the duty the pump snaps to the instant it engages — the floor below
// which this pump does not push useful water, so a flick lands ON it rather than
// somewhere underneath it where nothing comes out. It therefore sets the SMALLEST
// dose a flick can deliver. RAMP_MS sets how fast it climbs above that floor.
//
// Resulting dwell -> duty, at these values:
//     flick ~200 ms ->  79 (31%)    ~400 ms -> 123 (48%)
//           ~700 ms -> 189 (74%)    1000 ms+ -> 255 (full)
//
// Both are estimates — the pump's true minimum useful duty has never been measured,
// and START_DUTY is the likelier of the two to be wrong. The previous value ramped
// to full in 106 ms, which made every flick a full-power burst.
// REVERTED to the pre-dose-metering behaviour at the user's request, while an
// unexplained mid-run slowdown is investigated. These two values reproduce the old
// integer ramp exactly: (255<<8)*5/106 = 3079 Q8 = 12.03 duty counts per 5 ms loop,
// which was the old RAMP_STEP of 12. A flick is once again a full-power burst.
//
// NOTE: telemetry taken under load shows this revert cannot be the cause of that
// slowdown — duty ramped 42/93/146/200/255 and then held at 255 for ~8 s until
// release, with one engage transition and no dip. Restore RAMP_MS=1000 /
// START_DUTY=35 to get dose metering back.
constexpr int RAMP_MS    = 106;              // time from START_DUTY to full
constexpr int START_DUTY = 0;                // no floor — ramp from a standstill

// Duty is carried in Q8 fixed point because the useful rates are fractions of a duty
// count per 5 ms loop: this ramp is 0.73 counts/loop, which integer stepping cannot
// represent at all — it would floor to 0 and the ramp would never start.
constexpr int32_t RAMP_STEP_Q8 =
    ((int32_t)(PWM_MAX - START_DUTY) << 8) * 5 / RAMP_MS;
static_assert(RAMP_STEP_Q8 >= 1, "ramp rounds to zero — RAMP_MS too large");
static_assert(START_DUTY >= 0 && START_DUTY < PWM_MAX, "START_DUTY out of range");

// ── TWO SEPARATE SIGNAL PATHS ────────────────────────────────────────────────
// On/off responsiveness matters; fine speed control does not. Those two jobs have
// opposite filtering needs, so they get separate paths off the same ADC reading:
//
//   FAST PATH  (on/off)  — K-of-N majority vote on the RAW samples. No smoothing
//                          filter, so no filter lag. Latency is just the vote
//                          window: ~30-50 ms to start, ~15-25 ms to stop.
//   SMOOTH PATH (duty)   — median + EMA. Lag here is harmless: the pump's own
//                          inertia and the soft-start ramp dominate anyway.
//
// A smoothing filter on the on/off decision would have cost ~185 ms of lag. The
// vote gets BETTER noise rejection than that filter for a fraction of the delay,
// because a binary decision can exploit the fact that the noise is white and
// therefore independent sample to sample (measured: hf/sd = 1.128).

// Thresholds. Engage high, release low, so the decision cannot chatter at the edge.
constexpr int DEADBAND_ON   = 300;           // offset needed to start the pump
constexpr int DEADBAND_OFF  = 180;           // ...and to keep it running once started

// Engage vote: K of the last N raw samples must exceed DEADBAND_ON.
// Measured false-crossing rate at rest is p = 0.0082 per sample. With white noise
// the samples are independent, so P(6 of 10) ~= 6e-11 per window; at 200 windows/s
// that is one spurious engage roughly every 2 years of continuous running. And it
// would be self-limiting anyway — the release vote below would clear it in ~25 ms,
// so the worst case is a brief blip, never the sustained creep we were chasing.
constexpr int VOTE_N_ON  = 10;               // 50 ms window
constexpr int VOTE_K_ON  = 6;
// Release vote: deliberately faster and looser. A false release just stops the
// pump, which is both the safe direction and trivially recoverable.
constexpr int VOTE_N_OFF = 5;                // 25 ms window
constexpr int VOTE_K_OFF = 3;

// ── Tank level and the full alarm ───────────────────────────────────────────
// DESIGN_V2.md §7: an XKC-Y25-class capacitive sensor clamped to the OUTSIDE of
// the tank wall, slightly below the true full line, because "false positives are
// cheap (stop early, look, carry on) but a false negative means overflow".
// elec/CIRCUIT.md §5 gives it the buzzer: "Filling happens with the pump OFF and
// the user standing at the tank", so this is the spigot-fill overflow alarm.
//
// POLARITY IS NOT A GUESS. elec/main.py ties the sensor's MODE wire to GND
// (gnd += j_lvl["GND"], j_lvl["MODE"]), and MODE shorted to GND selects the
// part's NORMALLY-CLOSED mode: no liquid -> output HIGH, liquid -> output LOW.
// (MODE left floating would instead select normally-open, which inverts it.) So
// with R23 pulling up to 3V3, a LOW on this pin means liquid at the sensor.
// The manufacturer's warning not to "use the black wire as GND" is about not
// using it as the power RETURN in place of the blue wire; shorting it to GND to
// pick the mode is the documented configuration.
constexpr bool LEVEL_FULL_IS_LOW = true;
// Confirm times, CHOSEN and labelled as such per cadkit/AGENTS.md. The part's own
// response time is ~500 ms, and this tank is being carried on someone's back, so
// the water sloshes across the threshold constantly. Assert faster than it
// clears: an overflow is time-critical, a stale alarm is only annoying.
constexpr uint32_t LEVEL_ASSERT_MS = 500;
constexpr uint32_t LEVEL_CLEAR_MS  = 2000;
// A beep, not a solid tone. The buzzer is ACTIVE (CIRCUIT.md §5: "it needs DC,
// not a driven waveform") so this switches it on and off whole rather than
// synthesising anything -- and a pattern says "alarm" where a continuous note
// just sounds like a fault.
constexpr uint32_t BUZZ_ON_MS  = 200;
constexpr uint32_t BUZZ_OFF_MS = 800;

// ── Direction ───────────────────────────────────────────────────────────────
// DESIGN_V2 §1: two pumps in anti-parallel sharing both lines through tees, pump
// A tank->pot and pump B pot->tank, with the idle pump's own check valves
// sealing its branch. So this is a THREE-state controller, and the one thing it
// must never do is run both at once: they would fight through the shared tees,
// and both FETs would be pulling 7.5 A off the same pack.
enum Dir : int8_t { DIR_NONE = 0, DIR_A = 1, DIR_B = -1 };

// Dead time between one pump stopping and either being allowed to start.
// CHOSEN, not measured, and labelled as such per cadkit/AGENTS.md: the check
// valves are passive and want the differential across them to collapse before
// the other pump pulls on the same tee. DESIGN_V2 §1's stated open risk is an
// air pocket parked in a tee branch, and slamming straight into reverse while
// the column is still moving is how you drag an air slug across one.
constexpr uint32_t DIR_DEAD_MS = 250;

// Invariants the direction logic rests on, checked by the compiler rather than
// trusted. The last two matter most: the release vote has to be able to fire
// inside its own window, and the engage window has to fit the 16-bit shift
// registers the votes are counted in.
static_assert(DIR_A != DIR_B && DIR_NONE == 0, "the three states must be distinct");
static_assert(DIR_A == -DIR_B, "A and B must be opposite signs for dir=-dir to hold");
static_assert(DEADBAND_OFF < DEADBAND_ON, "release must be inside engage, or it chatters");
static_assert(VOTE_K_ON <= VOTE_N_ON && VOTE_K_OFF <= VOTE_N_OFF, "unreachable vote");
static_assert(VOTE_N_ON <= 16 && VOTE_N_OFF <= 16, "vote window exceeds its uint16_t");

// Duty commanded while engaged. The stick is used hard-forward or hard-back in
// practice, so there is no proportional mapping: engaged means run, at this duty.
// Lower it to cap pump speed (and save battery) — it is a one-line OTA push.
constexpr int RUN_DUTY  = PWM_MAX;

// Median + EMA on the raw signal. DIAGNOSTIC ONLY — deliberately NOT on the control
// path. Keeping it costs nothing and lets the telemetry keep reporting how bad the
// underlying hardware noise is over time, which is worth watching given the fault
// was never actually repaired. MEDIAN_N must be odd.
constexpr int MEDIAN_N  = 5;
constexpr int EMA_SHIFT = 3;

// ── Networking / telemetry ───────────────────────────────────────────────────
constexpr uint16_t LOG_PORT       = 23;
constexpr uint32_t WIFI_RETRY_MS  = 15000;
constexpr uint32_t LINE_MS        = 250;
constexpr uint32_t STATS_MS       = 1000;

int  joyCentre = ADC_MAX / 2;                // re-measured at boot (see measureCentre)
int  curDuty   = 0;                          // 0..DUTY_CAP (forward only)
bool armed     = true;                       // false = motor inhibited, telemetry live
bool otaActive = false;

int32_t dutyQ8 = 0;                          // current duty, Q8 fixed point

Dir      runDir      = DIR_NONE;             // which pump, if any, is commanded
uint32_t lastStopMs  = 0;                    // when it last went to DIR_NONE
// The dead time is between a STOP and the next start, not a boot delay. Without
// this flag, lastStopMs = 0 gates the first engage until millis() passes
// DIR_DEAD_MS -- which on real hardware it already has by the first loop, so the
// bench and the model would have disagreed about the one thing being tested.
// A flag rather than seeding lastStopMs backwards, because millis() - 250 wraps
// when millis() < 250 and would gate forever.
bool     everStopped = false;

bool     tankFull    = false;                // debounced
bool     levelRawHit = false;                // this pass, before debouncing
uint32_t levelSince  = 0;                    // when the raw state last changed

// Pack voltage and the duty ceiling it implies. Both start at the SAFE end: as
// if the pack were fresh, so the very first engage after boot is capped even if
// no ADC reading has landed yet.
float vbatV   = VBAT_ASSUMED;
bool  vbatOK  = false;                       // a plausible reading has been seen
int   vbatCap = (int)(PWM_MAX * PUMP_V_NOM / VBAT_ASSUMED);

Preferences prefs;
WiFiServer  logServer(LOG_PORT);
WiFiClient  logClient;

// The format attribute is load-bearing, not decoration: without it a mismatch
// between this format string and its arguments compiles silently, and an %s fed an
// int dereferences it as a pointer and crashes the board. That happened three times
// while developing this file before the attribute was added.
void logf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

void logf(const char *fmt, ...) {
  char buf[288];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  if (n < 0) return;
  Serial.print(buf);
  if (logClient && logClient.connected()) logClient.print(buf);
}

// ── Signal chain: median-of-N, then EMA ──────────────────────────────────────
int     medBuf[MEDIAN_N];
int     medIdx  = 0;
bool    medSeeded = false;
int32_t emaQ8   = 0;                         // EMA state in Q8 fixed point

int medianFilter(int v) {
  if (!medSeeded) { for (int i = 0; i < MEDIAN_N; i++) medBuf[i] = v; medSeeded = true; }
  medBuf[medIdx] = v;
  medIdx = (medIdx + 1) % MEDIAN_N;
  int s[MEDIAN_N];
  memcpy(s, medBuf, sizeof(s));
  for (int i = 1; i < MEDIAN_N; i++) {       // insertion sort — N is 5, this is free
    int k = s[i], j = i - 1;
    while (j >= 0 && s[j] > k) { s[j + 1] = s[j]; j--; }
    s[j + 1] = k;
  }
  return s[MEDIAN_N / 2];
}

int filterSample(int raw) {
  int med = medianFilter(raw);
  emaQ8 += (((int32_t)med << 8) - emaQ8) >> EMA_SHIFT;
  return (int)(emaQ8 >> 8);
}

void seedFilters(int v) {
  for (int i = 0; i < MEDIAN_N; i++) medBuf[i] = v;
  medIdx = 0; medSeeded = true;
  emaQ8 = (int32_t)v << 8;
}

// ── Statistics (Welford + mean absolute difference) ──────────────────────────
// `hf` is the mean |sample-to-sample difference|. It measures HIGH-FREQUENCY
// noise only: electrical noise is uncorrelated sample to sample so it registers
// fully, while slow movement (a hand on the stick) nearly cancels. Plain stdev
// cannot separate the two. For white Gaussian noise hf ~= 1.128 * sd.
struct Accum {
  uint32_t n = 0;
  int      mn = INT32_MAX, mx = INT32_MIN;
  double   mean = 0, m2 = 0;
  int      prev = -1;
  double   diffSum = 0;
  uint32_t nDiff = 0;

  void add(int v) {
    n++;
    if (v < mn) mn = v;
    if (v > mx) mx = v;
    double d = v - mean;
    mean += d / n;
    m2   += d * (v - mean);
    if (prev >= 0) { diffSum += fabs((double)(v - prev)); nDiff++; }
    prev = v;
  }
  double sd() const { return n > 1 ? sqrt(m2 / n) : 0.0; }
  double hf() const { return nDiff ? diffSum / nDiff : 0.0; }
  void reset() { int keep = prev; *this = Accum(); prev = keep; }
};

struct Stats {
  Accum    raw, filt;
  uint32_t rawOver = 0, filtOver = 0;   // samples whose |offset| exceeded DEADBAND_ON
  uint32_t runLen = 0, maxRun = 0;      // consecutive RAW crossings (the old failure path)
  int      dutyMax = 0;
  // The bottom line. With the stick at rest this must stay 0: every increment is
  // the vote deciding the pump should start when nobody asked it to.
  uint32_t engages = 0;

  void add(int r, int f, int rOff, int fOff, int duty) {
    raw.add(r);
    filt.add(f);
    if (abs(rOff) > DEADBAND_ON) { rawOver++; if (++runLen > maxRun) maxRun = runLen; }
    else runLen = 0;
    if (abs(fOff) > DEADBAND_ON) filtOver++;
    if (duty > dutyMax) dutyMax = duty;
  }
  void reset() {
    uint32_t keepRun = runLen;
    raw.reset(); filt.reset();
    rawOver = filtOver = 0; maxRun = 0; dutyMax = 0; engages = 0;
    runLen = keepRun;
  }
};
Stats stats;

// Deliberately writes the pins directly rather than going through drivePumps:
// a safety stop should not depend on the duty-cap arithmetic being sane.
void allStop() {
  curDuty = 0;
  runDir  = DIR_NONE;
  ledcWrite(PUMP_A_PIN, 0);
  ledcWrite(PUMP_B_PIN, 0);
}

// analogReadMilliVolts applies the chip's factory ADC calibration. The raw
// 12-bit count is markedly nonlinear near both rails, and at 20 V the divider
// sits at 3.05 V -- right in the compressed region -- so a raw count would bias
// the cap in the dangerous direction.
void readVbat() {
  float v = analogReadMilliVolts(VBAT_PIN) * 0.001f * VBAT_SCALE;
  if (v >= VBAT_PLAUS_LO && v <= VBAT_PLAUS_HI) {
    if (!vbatOK) { vbatV = v; vbatOK = true; }   // seed, don't crawl down from 20
    else         { vbatV += (v - vbatV) * VBAT_EMA_A; }
  } else {
    vbatOK = false;                              // fall back to the safe end
    vbatV  = VBAT_ASSUMED;
  }
  int cap = (int)(PWM_MAX * PUMP_V_NOM / vbatV + 0.5f);
  vbatCap = constrain(cap, 1, PWM_MAX);          // a pack under 12 V gets it all
}

// The ONLY place either gate gets a non-zero duty, and it writes BOTH pins every
// call -- so "run A" is always also "B off". The interlock cannot be forgotten at
// a call site because there is no call site that can set one pin alone.
// Debounced tank-full. Asymmetric on purpose: see LEVEL_ASSERT_MS.
void readLevel() {
  bool hit = (digitalRead(LEVEL_PIN) == LOW) == LEVEL_FULL_IS_LOW;
  uint32_t now = millis();
  if (hit != levelRawHit) { levelRawHit = hit; levelSince = now; }
  uint32_t need = hit ? LEVEL_ASSERT_MS : LEVEL_CLEAR_MS;
  if (hit != tankFull && (now - levelSince) >= need) tankFull = hit;
}

// Beeps while the tank reads full. Independent of `armed`, which inhibits the
// PUMPS -- the tank can overflow from the spigot with the pumps disarmed, which
// per CIRCUIT.md §5 is exactly when someone is standing there filling it.
// Silenced mid-OTA so a reflash is not done to a screaming board.
void updateBuzzer() {
  static uint32_t phase = 0;
  static bool on = false;
  if (!tankFull || otaActive) {
    if (on) { on = false; digitalWrite(BUZZ_PIN, LOW); }
    phase = millis();
    return;
  }
  uint32_t now = millis();
  if (now - phase >= (on ? BUZZ_ON_MS : BUZZ_OFF_MS)) {
    on = !on;
    phase = now;
    digitalWrite(BUZZ_PIN, on ? HIGH : LOW);
  }
}

void drivePumps(Dir dir, int duty) {
  int d = constrain(duty, 0, min(DUTY_CAP, vbatCap));
  ledcWrite(PUMP_A_PIN, dir == DIR_A ? d : 0);
  ledcWrite(PUMP_B_PIN, dir == DIR_B ? d : 0);
}

void setArmed(bool on) {
  armed = on;
  prefs.putBool("armed", armed);       // survives reboot, including an OTA reflash
  if (!armed) allStop();
  logf("\n*** PUMP %s ***%s\n", armed ? "ARMED" : "DISARMED",
       armed ? "" : "  (motor inhibited, telemetry still live)");
}

// Centre calibration. Uses the MEDIAN of a large sample set rather than a mean:
// with ~100 counts of noise and occasional far outliers, a mean of 64 samples was
// only good to ~13 counts and was skewed by spikes. A 129-sample median lands
// within a few counts and ignores outliers entirely.
void measureCentre() {
  constexpr int N = 129;
  static int buf[N];
  for (int i = 0; i < N; i++) { buf[i] = analogRead(JOY_PIN); delay(1); }
  for (int i = 1; i < N; i++) {
    int k = buf[i], j = i - 1;
    while (j >= 0 && buf[j] > k) { buf[j + 1] = buf[j]; j--; }
    buf[j + 1] = k;
  }
  joyCentre = buf[N / 2];
  seedFilters(joyCentre);
  logf("Joystick centre = %d / %d  (median of %d)\n", joyCentre, ADC_MAX, N);
  if (joyCentre < 1200 || joyCentre > 2900) {
    logf("WARNING: centre is implausible — was the stick held at boot? Use 'c' to redo.\n");
  }
}

void handleCommand(char c) {
  switch (c) {
    case 'd': setArmed(false); break;
    case 'a': setArmed(true);  break;
    case 'c':
      logf("Recalibrating centre — leave the stick at rest...\n");
      measureCentre();
      break;
    case 's':
      logf("state=%s dir=%s deadtime=%lums centre=%d duty=%d "
           "| vote on=%d/%d off=%d/%d thr=%d/%d runduty=%d "
           "| ramp=%dms startduty=%d | pack=%.2fV%s cap=%d | tank=%s(pin %s) "
           "| on-lat~%dms off-lat~%dms | rssi=%d ip=%s up=%lus\n",
           armed ? "ARMED" : "DISARMED",
           runDir == DIR_A ? "A(tank>pot)" : runDir == DIR_B ? "B(pot>tank)" : "none",
           (unsigned long)DIR_DEAD_MS, joyCentre, curDuty,
           VOTE_K_ON, VOTE_N_ON, VOTE_K_OFF, VOTE_N_OFF,
           DEADBAND_ON, DEADBAND_OFF, RUN_DUTY,
           RAMP_MS, START_DUTY, (double)vbatV, vbatOK ? "" : "?", vbatCap,
           tankFull ? "FULL" : "ok", digitalRead(LEVEL_PIN) ? "HIGH" : "LOW",
           VOTE_K_ON * 5, VOTE_K_OFF * 5,
           WiFi.RSSI(), WiFi.localIP().toString().c_str(), millis() / 1000UL);
      break;
    case 'b':
      // Bench bring-up for the two things that cannot be verified anywhere but
      // on the hardware: that the buzzer is wired and audible, and that the
      // level sensor's polarity really is the NC mode the schematic selects.
      // Wet the sensor and watch pin= flip; if "full" reads backwards, flip
      // LEVEL_FULL_IS_LOW -- it is one constant.
      logf("buzzer 1 s | level pin=%s -> %s (LEVEL_FULL_IS_LOW=%d)\n",
           digitalRead(LEVEL_PIN) ? "HIGH" : "LOW",
           tankFull ? "FULL" : "not full", (int)LEVEL_FULL_IS_LOW);
      digitalWrite(BUZZ_PIN, HIGH); delay(1000); digitalWrite(BUZZ_PIN, LOW);
      break;
    case 'R':
      logf("Rebooting...\n");
      allStop();
      delay(100);
      ESP.restart();
      break;
    case '?':
      logf("cmds: a=arm  d=disarm  c=recalibrate centre  s=status  R=reboot\n");
      break;
    default: break;
  }
}

void netSetup() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(NET_HOSTNAME);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);   // async — we never block on this

  ArduinoOTA.setHostname(NET_HOSTNAME);
  // An EMPTY OTA_PASSWORD means "no authentication". It must not be passed to
  // setPassword(), which MD5-hashes its argument — hashing "" yields a non-empty
  // digest, which switches the auth path ON with a blank password and makes every
  // update fail. Skip the call entirely instead.
  if (sizeof(OTA_PASSWORD) > 1) {
    ArduinoOTA.setPassword(OTA_PASSWORD);
    logf("OTA: password required.\n");
  } else {
    logf("OTA: UNAUTHENTICATED — anyone on this LAN can reflash this board.\n");
  }
  // Safety: never reflash with a pump live. Both gates would otherwise be left
  // with undefined drive across the reboot, with the pumps attached.
  ArduinoOTA.onStart([]() {
    otaActive = true;
    allStop();
    logf("\nOTA update starting — motor forced off.\n");
  });
  ArduinoOTA.onEnd([]() {
    allStop();
    logf("OTA complete, rebooting.\n");
  });
  ArduinoOTA.onError([](ota_error_t err) {
    otaActive = false;
    allStop();
    logf("OTA FAILED (error %u) — motor left off.\n", (unsigned)err);
  });
  ArduinoOTA.begin();
  logServer.begin();
  logServer.setNoDelay(true);
}

void netLoop() {
  static uint32_t lastRetry = 0;
  static bool     wasUp     = false;

  bool up = (WiFi.status() == WL_CONNECTED);
  if (up != wasUp) {
    wasUp = up;
    if (up) {
      MDNS.begin(NET_HOSTNAME);
      MDNS.addService("telnet", "tcp", LOG_PORT);
      logf("WiFi up: %s  (%s.local)  rssi=%d dBm\n",
           WiFi.localIP().toString().c_str(), NET_HOSTNAME, WiFi.RSSI());
    } else {
      logf("WiFi lost.\n");
    }
  }
  if (!up) {
    if (millis() - lastRetry > WIFI_RETRY_MS) {
      lastRetry = millis();
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;
  }

  ArduinoOTA.handle();

  if (logServer.hasClient()) {
    if (logClient && logClient.connected()) logClient.stop();
    logClient = logServer.accept();
    logClient.setNoDelay(true);
    logClient.printf("watering-backpack — %s.  cmds: a=arm d=disarm c=recal s=status R=reboot\n",
                     armed ? "PUMP ARMED" : "PUMP DISARMED");
  }
  while (logClient && logClient.connected() && logClient.available()) {
    handleCommand((char)logClient.read());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  // Every connected pin into its legal mode, with the datasheet reason for each
  // recorded next to it in pins.cpp. Outputs land LOW before anything else runs;
  // both pump gates are held LOW as plain outputs BEFORE the LEDC channels
  // attach, so neither pump can twitch while the peripheral is set up.
  pinsInit();
  ledcAttach(PUMP_A_PIN, PWM_FREQ, PWM_RES);
  ledcAttach(PUMP_B_PIN, PWM_FREQ, PWM_RES);
  allStop();

  prefs.begin("pump", false);
  armed = prefs.getBool("armed", true);

  // ADC width and per-pin attenuation are set by pinsInit(), above.
  readVbat();                          // seed before any engage is possible
  Serial.printf("Pump controller ready. State = %s | pack %.2f V -> duty cap %d%s\n",
                armed ? "ARMED" : "DISARMED", vbatV, vbatCap,
                vbatOK ? "" : " (SENSE IMPLAUSIBLE - assuming a fresh pack)");
  measureCentre();                     // also seeds the median + EMA state

  netSetup();
}

void loop() {
  // ── Control law: runs first, every pass, regardless of network state ───────
  int raw  = analogRead(JOY_PIN);
  int filt = filterSample(raw);

  // Pack voltage, decimated. It moves on the scale of minutes, and the joystick
  // owns the fast path on the same ADC block.
  static uint8_t vbatTick = 0;
  if (++vbatTick >= VBAT_EVERY_N) { vbatTick = 0; readVbat(); }

  // Tank level and its alarm. Deliberately NOT an interlock on either pump --
  // see the note above readLevel's constants and the header.
  readLevel();
  updateBuzzer();

  int rawOffset  = raw  - joyCentre;   // drives the on/off vote — the control path
  int offset     = filt - joyCentre;   // diagnostic only, reported but never acted on

  // ── Fast path: K-of-N majority vote, no smoothing, so no filter lag ───────
  // Three histories now, because both polarities are live. The release vote is
  // on the MAGNITUDE -- it used to be a signed "fell below +180", which quietly
  // meant any rearward deflection read as released, which is exactly how
  // forward-only was implemented.
  static uint16_t fwdHist = 0, revHist = 0, nearHist = 0;
  fwdHist  = (uint16_t)((fwdHist  << 1) | (rawOffset >  DEADBAND_ON ? 1 : 0));
  revHist  = (uint16_t)((revHist  << 1) | (rawOffset < -DEADBAND_ON ? 1 : 0));
  nearHist = (uint16_t)((nearHist << 1) | (abs(rawOffset) < DEADBAND_OFF ? 1 : 0));
  int nFwd  = __builtin_popcount((unsigned)(fwdHist  & ((1u << VOTE_N_ON)  - 1)));
  int nRev  = __builtin_popcount((unsigned)(revHist  & ((1u << VOTE_N_ON)  - 1)));
  int nNear = __builtin_popcount((unsigned)(nearHist & ((1u << VOTE_N_OFF) - 1)));

  Dir wasDir = runDir;
  if (runDir == DIR_NONE) {
    bool fwd = (nFwd >= VOTE_K_ON), rev = (nRev >= VOTE_K_ON);
    // Both votes passing at once is not physically possible on one axis, so it
    // means something is wrong with the stick or its wiring. Start neither.
    if (fwd != rev &&
        (!everStopped || (millis() - lastStopMs) >= DIR_DEAD_MS)) {
      runDir = fwd ? DIR_A : DIR_B;
    }
  } else {
    // Release on the near vote OR on the opposite direction's engage vote. That
    // second clause is not belt-and-braces: a fast flick from hard-forward to
    // hard-back crosses the +-DEADBAND_OFF band in well under the 25 ms the
    // near vote needs, and without it the pump would keep running the WRONG WAY
    // with the stick held hard over the other side.
    bool opp = (runDir == DIR_A) ? (nRev >= VOTE_K_ON) : (nFwd >= VOTE_K_ON);
    if (nNear >= VOTE_K_OFF || opp) {
      runDir = DIR_NONE; lastStopMs = millis(); everStopped = true;
    }
  }
  // Every direction change therefore passes through DIR_NONE and waits out
  // DIR_DEAD_MS. There is no A->B edge anywhere in this state machine.
  bool engaged    = (runDir != DIR_NONE);
  bool wasEngaged = (wasDir != DIR_NONE);

  // Engaged means run at RUN_DUTY; there is no intermediate level, so neither
  // pump can sit at the slow trickle that started all this. That failure mode
  // stays structurally impossible rather than merely unlikely.
  //
  // Capped by the pack voltage, not just RUN_DUTY. The ramp has to respect it
  // too: clamping only inside drivePumps would let dutyQ8 wind up to 255 and
  // sit there, so the moment a sagging pack raised the cap the output would
  // jump instead of ramping.
  int target = engaged ? min(RUN_DUTY, vbatCap) : 0;

  if (armed && !otaActive) {
    if (!engaged) {
      dutyQ8  = 0;                     // switch-off: immediate cut, no spin-down ramp
      curDuty = 0;
    } else {
      if (!wasEngaged) {
        // Snap to the useful-flow floor, then wind up from there. A flick lands
        // ON this value rather than somewhere below it where nothing comes out.
        dutyQ8 = (int32_t)START_DUTY << 8;
      } else if (dutyQ8 < ((int32_t)target << 8)) {
        dutyQ8 += RAMP_STEP_Q8;
        if (dutyQ8 > ((int32_t)target << 8)) dutyQ8 = (int32_t)target << 8;
      }
      curDuty = (int)(dutyQ8 >> 8);
    }
    drivePumps(runDir, curDuty);
  } else {
    // Disarmed or mid-OTA: motor off, but keep reading and reporting the joystick
    // so it can be characterised with no water moving.
    if (curDuty != 0) allStop();
  }

  if (engaged && !wasEngaged) stats.engages++;
  stats.add(raw, filt, rawOffset, offset, curDuty);

  // ── Telemetry ─────────────────────────────────────────────────────────────
  static uint32_t last = 0, lastStats = 0;
  if (millis() - last > LINE_MS) {
    last = millis();
    logf("raw=%4d filt=%4d offset=%+5d duty=%+4d %s%s\n", raw, filt, offset, curDuty,
         runDir == DIR_A ? "A tank>pot" : runDir == DIR_B ? "B pot>tank" : "off       ",
         armed ? "" : " [DISARMED]");
  }
  if (millis() - lastStats > STATS_MS) {
    lastStats = millis();
    logf("STATS n=%lu raw=%d..%d mean=%.1f sd=%.1f hf=%.1f fsd=%.1f fhf=%.1f "
         "over_deadband=%lu fover=%lu maxrun=%lu dutymax=%d engages=%lu\n",
         (unsigned long)stats.raw.n, stats.raw.mn, stats.raw.mx, stats.raw.mean,
         stats.raw.sd(), stats.raw.hf(), stats.filt.sd(), stats.filt.hf(),
         (unsigned long)stats.rawOver, (unsigned long)stats.filtOver,
         (unsigned long)stats.maxRun, stats.dutyMax, (unsigned long)stats.engages);
    stats.reset();
  }

  netLoop();
  delay(5);
}
