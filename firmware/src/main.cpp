/*
 * Watering-backpack pump controller
 * QuinLED-ESP32 (ESP32-WROOM-32) + BTS7960 H-bridge + single-axis analog joystick.
 *
 * FORWARD-ONLY: flow direction (fill vs. suck) is set by the manual X-port
 * reversing valve, so the pump only ever runs ONE way. The joystick sets pump
 * SPEED on one axis; deflection the "reverse" way is ignored.
 *
 * Only the RPWM (forward) half of the BTS7960 is driven; LPWM (reverse) is held
 * LOW and unused. Both enable inputs (R_EN + L_EN, wired together to EN_PIN) are
 * driven HIGH while the pump is commanded and dropped LOW at idle — a true
 * coast/disable.
 *
 * Power: feed the board 5 V (from the TSR) through the 5vF pad (PTC-fused).
 *
 * Pads (QuinLED-ESP32, chosen non-adjacent for direct soldering):
 *   IO25  left-outer  -> LPWM (reverse)
 *   IO26  right-inner -> RPWM (forward)
 *   IO4   left-outer  -> EN  (to BOTH R_EN and L_EN on the driver)
 *   IO34  right-outer -> joystick SIG (ADC1, input-only)
 *   3v3 -> joystick VCC + driver VCC,  GND pads -> joystick/board/driver GND,
 *   5vF -> board 5 V
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
 * The original failure mode was noise RECTIFYING into motion: the control law is
 * forward-only, so symmetric noise becomes a one-sided command, and the ramp
 * integrator ratcheted those one-sided kicks upward into a slow, self-sustaining
 * pump creep. The control law now closes that off:
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

// ── Pin map ──────────────────────────────────────────────────────────────────
constexpr int JOY_PIN  = 34;   // ADC1 (input-only is fine for an analog read)
constexpr int RPWM_PIN = 26;   // BTS7960 RPWM — forward
constexpr int LPWM_PIN = 25;   // BTS7960 LPWM — reverse
constexpr int EN_PIN   = 4;    // BTS7960 R_EN + L_EN (tied together) — enable/coast

// ── PWM (LEDC, pin-based API = Arduino-ESP32 3.x) ────────────────────────────
constexpr int PWM_FREQ = 20000;              // 20 kHz — above audible, OK for BTS7960
constexpr int PWM_RES  = 8;                  // 8-bit duty (0..255)
constexpr int PWM_MAX  = (1 << PWM_RES) - 1;
constexpr int DUTY_CAP = PWM_MAX;            // lower to cap max pump speed (e.g. 200)

// ── Joystick / control tunables ──────────────────────────────────────────────
constexpr int ADC_RES   = 12;
constexpr int ADC_MAX   = (1 << ADC_RES) - 1;   // 4095
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
  uint32_t rawOver = 0, filtOver = 0;   // samples whose offset exceeded DEADBAND_ON
  uint32_t runLen = 0, maxRun = 0;      // consecutive RAW crossings (the old failure path)
  int      dutyMax = 0;
  // The bottom line. With the stick at rest this must stay 0: every increment is
  // the vote deciding the pump should start when nobody asked it to.
  uint32_t engages = 0;

  void add(int r, int f, int rOff, int fOff, int duty) {
    raw.add(r);
    filt.add(f);
    if (rOff > DEADBAND_ON) { rawOver++; if (++runLen > maxRun) maxRun = runLen; }
    else runLen = 0;
    if (fOff > DEADBAND_ON) filtOver++;
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

void allStop() {
  curDuty = 0;
  ledcWrite(RPWM_PIN, 0);
  digitalWrite(LPWM_PIN, LOW);
  digitalWrite(EN_PIN, LOW);
}

void driveMotor(int duty) {
  ledcWrite(RPWM_PIN, constrain(duty, 0, DUTY_CAP));
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
      logf("state=%s centre=%d duty=%d | vote on=%d/%d off=%d/%d thr=%d/%d runduty=%d "
           "| ramp=%dms startduty=%d | on-lat~%dms off-lat~%dms | rssi=%d ip=%s up=%lus\n",
           armed ? "ARMED" : "DISARMED", joyCentre, curDuty,
           VOTE_K_ON, VOTE_N_ON, VOTE_K_OFF, VOTE_N_OFF,
           DEADBAND_ON, DEADBAND_OFF, RUN_DUTY,
           RAMP_MS, START_DUTY, VOTE_K_ON * 5, VOTE_K_OFF * 5,
           WiFi.RSSI(), WiFi.localIP().toString().c_str(), millis() / 1000UL);
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
  // Safety: never reflash with the motor live. The BTS7960 would otherwise be left
  // with undefined inputs across the reboot, with a pump attached.
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

  // Motor outputs go to a known-safe state before anything else runs.
  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, LOW);
  ledcAttach(RPWM_PIN, PWM_FREQ, PWM_RES);
  pinMode(LPWM_PIN, OUTPUT);
  digitalWrite(LPWM_PIN, LOW);
  driveMotor(0);

  prefs.begin("pump", false);
  armed = prefs.getBool("armed", true);

  analogReadResolution(ADC_RES);
  Serial.printf("Pump controller ready. State = %s\n", armed ? "ARMED" : "DISARMED");
  measureCentre();                     // also seeds the median + EMA state

  netSetup();
}

void loop() {
  // ── Control law: runs first, every pass, regardless of network state ───────
  int raw  = analogRead(JOY_PIN);
  int filt = filterSample(raw);

  int rawOffset  = raw  - joyCentre;   // drives the on/off vote — the control path
  int offset     = filt - joyCentre;   // diagnostic only, reported but never acted on

  // ── Fast path: K-of-N majority vote, no smoothing, so no filter lag ───────
  static uint16_t aboveHist = 0, belowHist = 0;
  static bool     engaged   = false;
  aboveHist = (uint16_t)((aboveHist << 1) | (rawOffset > DEADBAND_ON  ? 1 : 0));
  belowHist = (uint16_t)((belowHist << 1) | (rawOffset < DEADBAND_OFF ? 1 : 0));
  int nAbove = __builtin_popcount((unsigned)(aboveHist & ((1u << VOTE_N_ON)  - 1)));
  int nBelow = __builtin_popcount((unsigned)(belowHist & ((1u << VOTE_N_OFF) - 1)));

  bool wasEngaged = engaged;
  if (!engaged) { if (nAbove >= VOTE_K_ON)  engaged = true;  }
  else          { if (nBelow >= VOTE_K_OFF) engaged = false; }

  // Forward only — deflection the "reverse" way is ignored. Engaged means run at
  // RUN_DUTY; there is no intermediate level, so the pump can never sit at the slow
  // trickle that started all this. The original failure mode is now structurally
  // impossible rather than merely unlikely.
  int target = engaged ? RUN_DUTY : 0;

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
    digitalWrite(EN_PIN, curDuty != 0 ? HIGH : LOW);
    driveMotor(curDuty);
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
         engaged ? "ON " : "off", armed ? "" : " [DISARMED]");
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
