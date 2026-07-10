/*
 * Watering-backpack pump controller
 * QuinLED-ESP32 (ESP32-WROOM-32) + BTS7960 H-bridge + single-axis analog joystick.
 *
 * FORWARD-ONLY: flow direction (fill vs. suck) is set by the manual X-port
 * reversing valve, so the pump only ever runs ONE way. The joystick sets pump
 * SPEED on one axis; deflection the "reverse" way is ignored:
 *     centre (within deadband) -> off
 *     pushed forward           -> pump on, duty ~ deflection
 *     pushed the other way     -> ignored (off)
 *
 * Only the RPWM (forward) half of the BTS7960 is driven; LPWM (reverse) is held
 * LOW and unused. Both enable inputs (R_EN + L_EN, wired together to EN_PIN) are
 * driven HIGH while the pump is commanded and dropped LOW at idle — a true
 * coast/disable. If the stick's "on" direction is backwards, flip the `offset`
 * comparison in loop() (or just turn the joystick 180°).
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
 */
#include <Arduino.h>

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
constexpr int DEADBAND  = 300;               // counts around centre treated as off (~7%)
constexpr int RAMP_STEP = 4;                 // max duty change per 5 ms loop (soft start/stop)

int joyCentre = ADC_MAX / 2;                 // re-measured at boot (see setup)
int curDuty   = 0;                           // 0..DUTY_CAP (forward only)

// Drive the pump forward only — RPWM carries the duty; LPWM (reverse) stays low.
void driveMotor(int duty) {
  ledcWrite(RPWM_PIN, constrain(duty, 0, DUTY_CAP));
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, LOW);                // driver disabled until commanded
  ledcAttach(RPWM_PIN, PWM_FREQ, PWM_RES);
  pinMode(LPWM_PIN, OUTPUT);
  digitalWrite(LPWM_PIN, LOW);             // reverse pin unused — held low
  driveMotor(0);                           // start stopped

  analogReadResolution(ADC_RES);
  // Centre calibration — assumes the joystick is at REST when the board powers on.
  long sum = 0;
  for (int i = 0; i < 64; i++) { sum += analogRead(JOY_PIN); delay(2); }
  joyCentre = (int)(sum / 64);
  Serial.printf("Pump controller ready. Joystick centre = %d / %d\n", joyCentre, ADC_MAX);
}

void loop() {
  int raw    = analogRead(JOY_PIN);
  int offset = raw - joyCentre;            // signed deflection from centre
  int target = 0;

  // Forward only — deflection the "reverse" way (offset <= 0) is ignored.
  if (offset > DEADBAND) {
    int mag  = offset - DEADBAND;
    int span = (ADC_MAX - joyCentre) - DEADBAND;
    if (span < 1) span = 1;
    int duty = (int)((long)mag * PWM_MAX / span);     // 0..PWM_MAX (linear past deadband)
    target   = constrain(duty, 0, PWM_MAX);
  }

  // Soft-ramp toward the target so the pump doesn't slam on/off (inrush, water hammer).
  if      (curDuty < target) curDuty = min(target, curDuty + RAMP_STEP);
  else if (curDuty > target) curDuty = max(target, curDuty - RAMP_STEP);

  // Enable the driver while it's commanded or still spinning down; disable
  // (coast) once fully centred/stopped.
  digitalWrite(EN_PIN, (target != 0 || curDuty != 0) ? HIGH : LOW);
  driveMotor(curDuty);

  static uint32_t last = 0;
  if (millis() - last > 250) {
    last = millis();
    Serial.printf("raw=%4d  offset=%+5d  duty=%+4d\n", raw, offset, curDuty);
  }
  delay(5);
}
