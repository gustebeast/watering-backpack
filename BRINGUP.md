# Bring-up: the v2 main board, from the envelope to a running pump

**Nothing in this repository described this.** "Bring-up" appeared only in passing —
*"OTA covers everything after bring-up"*, *"ten bring-up pads"* — with no order, no
measurements and no expected numbers. This file is the order, and every step names
what to measure and what it should read.

**Read the stop rule first: at every step, if the number is not the expected one, STOP
and diagnose there.** Each stage exists so that the next one cannot damage anything,
and the staging is not advisory — it is how the two known hazards below are avoided.

## The two hazards this order is built around

**1. A pump can start with no joystick connected.** `JOY_RAW` is J4 way 3 and R22 and
nothing else — no pull-up, no pull-down, no bias. Unlanded, the ADC node floats,
`measureCentre()` calibrates against the float, and drift past `DEADBAND_ON` (300 counts
of 4095, ≈ 0.24 V) for 6 of 10 samples engages a pump. **Mitigation in firmware:** a
board with no stored preference boots **DISARMED**, so a new board will not drive a pump
until you send `a`. **Not yet fixed in copper:** finding 49.

**2. Two power sources can back-feed each other.** J6 pin 1 is the buck's own 3V3 rail.
Landing an adapter's 3V3 while the pack is docked feeds one into the other. Pick one
source per stage, as below.

## Stage 0 — before anything is powered

| measure | where | expect |
|---|---|---|
| VBAT to GND, resistance | TP2 ↔ TP1 | **not a short.** Tens of kΩ and rising as C1/C2 charge off the meter |
| 3V3 to GND, resistance | TP3 ↔ TP1 | **not a short.** Hundreds of Ω at minimum; a dead short here is an assembly fault |
| F2 | the blade holder | **blade OUT.** It isolates the pack from the whole board — see below |

⚠ **WHAT THE BLADE DOES AND DOES NOT STAGE.** VBAT is the far side of F2, and VBAT
carries U1's VIN *and* EN, R9's VGATE dropper, TP2 and both pump terminals. So the blade
out means **the entire board is unpowered** — it is the pack's isolator, nothing finer.
It comes **out** for stages 0 and 1 and goes **in** at stage 2, and from there what keeps
things safe is that nothing which can move is landed and the firmware boots disarmed.

**Two nets have no test pad, on purpose, because a screw terminal is already a probe
point:** VBAT_RAW (J1 to F2, ahead of the blade) is probed at **J1's own screw**, and
VBAT_LVL (F1 to J5, behind the level fuse) at **J5 way 1's screw** — which is how you
tell a tripped F1 from a dead sensor.

Nothing is landed on J1–J5 yet. The ten test pads are net-labelled on the silk:
TP1 GND, TP2 VBAT, TP3 +3V3, TP4 VGATE, TP5 SW, TP6 GATE_A, TP7 GATE_B,
TP8 VBAT_SENSE, TP9 JOY_FILT, TP10 LEVEL.

## Stage 1 — flash it with no pack anywhere near it

Pack **out of the dock**, F2 blade **out**. Power the board from the adapter's 3V3 on
J6 pin 1. This is enough to flash and talk; it is **not** enough to test a pump, because
the gate driver needs VGATE and VGATE comes from the pack.

Wire J6 using the names printed on the **back** silk beside the header:

| J6 | silk | adapter |
|---|---|---|
| 1 | 3V3 | 3V3 |
| 2 | GND | GND |
| 3 | `ESP_TX_TO_PROG` | **RX** |
| 4 | `PROG_RX_IN` | **TX** |
| 5 | `EN` | RTS |
| 6 | `IO0` | DTR |

⚠ **Both serial ways are named from the board's side.** `ESP_TX_TO_PROG` is an *output*
of this board, so it goes to the adapter's RX. Wiring TX to TX by matching labels is the
commonest reason a first flash fails (M26).

| step | expect |
|---|---|
| 3V3 at TP3 | **3.30 V** (the rail is asserted at 3.301 V) |
| `pio run -t upload` | connects and writes. DTR/RTS enter the bootloader by themselves; with an adapter that does not break them out, hold IO0 to GND, pulse EN to GND, release EN, start the upload, release IO0 once it connects |
| `pio device monitor` | boots, and prints **`*** PUMP DISARMED ***`** |
| `?` | lists `a d c s b R` |

**If the upload fails:** the baud is pinned to 115200 for exactly this reason, so
suspect the wiring before the board. Swap pins 3 and 4 as the first experiment.

⚠ **IF IT FLASHES AND THEN REBOOTS IN A LOOP, SUSPECT THE ADAPTER, NOT THE BOARD.**
An adapter's 3V3 usually comes from a small LDO good for 50—100 mA. Flashing is fine
because the radio is off, but `netSetup()` brings WiFi up on the first boot and an
ESP32's transmit peaks run to several hundred mA. The board's own 88 µF of output
capacitance absorbs a transient, not a sustained draw.

The symptom is named rather than silent: arduino-esp32 enables the brownout detector by
default and nothing here disables it, so the console prints **`Brownout detector was
triggered`** before each reset. Seeing that at stage 1 is an underpowered adapter.
**Do not diagnose the board from this stage — move to stage 2 and judge it on pack
power.** `monitor_filters = esp32_exception_decoder` is set so that a genuine panic,
as opposed to a brownout, arrives as a decoded backtrace instead of raw addresses.

**Firmware footprint, measured** (`pio run -e main-usb`, 2026-10-08): builds clean,
**RAM 16.0 %** (52,512 of 327,680) and **Flash 78.3 %** (1,026,150 of 1,310,720). The
flash figure is against ONE app slot of `default.csv`, which carries two so OTA can
swap between them — so the image fits with about 284 KB spare, and that margin is
what an OTA update has to keep fitting into.

## Stage 2 — the pack, still with nothing attached that can move

Adapter 3V3 **off** (leave TX/RX/GND landed to keep the console). **J2/J3 (pumps) empty,
J4/J5 empty** — that, plus the disarmed firmware, is what makes this stage safe.

Dock the pack, then fit **F2's blade**. The board is dead until you do: VBAT is on the
far side of the fuse and feeds U1's VIN, so there is no 3V3 and no VGATE to measure with
the blade out.
⚠ An earlier version of this file said "blade **still out**" here and then asked for
3V3 and VGATE anyway. It is recorded rather than quietly fixed because it is the exact
shape of error a procedure exists to prevent: a state the steps cannot be performed in.

First, with the pack docked and the blade still out:

| measure | where | expect |
|---|---|---|
| pack at the terminal | **J1's screw** ↔ TP1 | **15.0–21.0 V.** 21 V is a fresh pack off the charger, not 20 — a "18 V" Makita is 5S. This is VBAT_RAW, ahead of the fuse, which is why it reads with the blade out |

Then fit the blade, and the rest of the board comes alive:

| measure | where | expect |
|---|---|---|
| pack, board side | TP2 ↔ TP1 | **the same voltage**, within a few mV. A difference here is the fuse or its holder |
| 3V3 | TP3 | **3.30 V** |
| VGATE | TP4 | **10 V**, the zener rail |
| GATE_A | TP6 | **0 V** |
| GATE_B | TP7 | **0 V** |
| VBAT_SENSE | TP8 | **VBAT ÷ 11** — 1.91 V at a 21 V pack, 1.36 V at 15 V |
| `s` | console | `pack=` within ~0.1 V of what the meter says at TP2 |

**GATE_A and GATE_B at 0 V is the one to dwell on.** They are held there three
independent ways — the UCC27517 holds its output low with its input floating (SLUSAY4D),
its VDD UVLO holds it low below 4.5 V, and R6/R7 put 100 kΩ from each gate to GND. If
either reads anything but 0 V with the board disarmed, stop: that is the fault that
drives a pump you did not ask for.

## Stage 3 — the level sensor

Land J5, **four wires, four ways, straight across** — brown VBAT, yellow OUT, blue GND,
black MODE. The labels are the instructions; this was not always true, and the old build
note's wiring inverts the alarm (finding 47).

| measure | state | expect |
|---|---|---|
| TP10 | **J5 empty** | **≈3.3 V**, and `b` reports `FULL` — a disconnected sensor reads full *on purpose*, so a dead sensor stops the pump |
| TP10 | sensor landed, **dry** | **≈0 V**, `b` reports `pin=LOW -> not full` |
| TP10 | sensor **wet** | **≈3.3 V**, `b` reports `pin=HIGH -> FULL` |
| `b` | any | buzzer sounds for 1 s |

⚠ **If full reads backwards, do not flip `LEVEL_FULL_IS_LOW`.** Check 9 of
`tools/check_level_alarm.py` derives that constant from the netlist and will fail, and it
was never the remedy: the constant describes the board, so a backwards reading means the
board is not wired as drawn. Look at the black MODE wire first, then Q4/R29/R30, then the
300 kΩ string R23/R27/R28.

## Stage 4 — the joystick

Land J4. Only way 3 (VRY) is live; ways 2, 4 and 5 are tied to GND on the board.

| step | expect |
|---|---|
| TP9 at rest | **≈1.65 V**, about half the rail |
| `c` | recalibrates; leave the stick at rest while it runs |
| `s` | `centre=` near 2048 of 4095, and `joy rawoff=` within the deadband (±300) |
| push one way | `rawoff=` goes past **+300**; the telemetry line shows `offset=+...` |
| push the other | `rawoff=` goes past **−300** |

⚠ **`dir=` STAYS `none` THROUGHOUT THIS STAGE, AND THAT IS NOT A FAULT.** An earlier
version of this file told you to watch `s` report `dir=A` and `dir=B` here. It never
will while disarmed: the direction vote sits inside `if (armed && !otaActive)` in
`loop()`, so nothing computes a direction when the motor is inhibited. Judge the stick
by **`rawoff=`**, which is live either way — `+300` and `-300` are `DEADBAND_ON`, the
same threshold the vote uses once armed. `s` says so in its own output now, and the
periodic telemetry line carries `raw= filt= offset=` with a `[DISARMED]` marker.

Recorded rather than quietly corrected, for the same reason as stage 2: a step that
cannot be performed in the state it specifies is the defect a procedure exists to
prevent, and this file shipped with two of them.

Confirm both deflections here, disarmed, before anything can turn. **Which deflection
drives which pump is only provable at stage 5**, with a pump landed — getting A and B
swapped is a wiring error, not a firmware constant, and
`tools/check_pump_dirs.py` owns the firmware side.

## Stage 5 — first pump motion

Only now: F2 blade **in**, and land **one** pump (J2). Keep the tank lines where a
wrong direction spills into a bucket rather than into the electronics.

| step | expect |
|---|---|
| `a` | `*** PUMP ARMED ***` |
| brief deflection toward A | pump A runs; `s` shows `state=ARMED dir=A duty=` ramping |
| release | stops within the off-latency `s` reports (~15 ms) |
| `d` | `*** PUMP DISARMED ***`, and it stays disarmed across a reboot |

Then land J3 and repeat for B. The killswitch at the dock is a **switch, not a fuse** —
it opens when a person opens it. F2 is the fuse.

## Stage 6 — the network, and OTA

With USB still attached, `s` prints `rssi=` and `ip=`. Once an IP appears,
`pio run -e main-ota -t upload` works and the adapter is no longer needed.

**If it flashes and runs but never gets an IP**, in the order worth trying:

| check | meaning |
|---|---|
| no IP, and no usable `rssi=` | the radio never associated — credentials or band |
| `s` shows a real `rssi=` but no IP | associated, no DHCP lease — a router or VLAN problem, not this board |
| `rssi=` worse than about −80 dBm | it is a link-budget problem; see the antenna note below |
| the console is silent after `Brownout detector was triggered` | not a network fault at all — stage 1's underpowered-adapter case |

Two causes are specific to this board and worth knowing before you suspect the radio:

* **The credentials are not in the repository.** `firmware/src/secrets.h` is gitignored,
  so a fresh clone has no SSID or password and the board will come up, run, and never
  associate. That is the expected behaviour of a clone, not a fault.
* **The ESP32 is 2.4 GHz only.** A 5 GHz-only SSID, or a band-steering router that hands
  out one name for both, looks exactly like wrong credentials.

**The antenna has a measured keepout and it is the board outline, not a rule area.** The
module's relief is the 4.6 × 4.6 mm cutout at x 140.70–145.30, y 47.70–52.30 in board
coordinates (15.9 mm², which `finish.py` checks every run). There are **no copper rule
areas on this board at all**, so nothing but that cutout keeps copper out from under the
antenna — which is why finding 39 cut the board back rather than drawing a keepout.

**Everything up to here works without a network.** Nothing in stages 0–5 needs WiFi, so
a board that fails only this stage is a usable board with a network problem, and the
pumps, the sensor and the alarm have all already been proven on the console.

⚠ **OTA authentication is OFF** (`OTA_PASSWORD` is empty in `src/secrets.h`), so anyone
on the LAN can reflash the board. `platformio.ini` says how to turn it on.

## What this procedure cannot tell you

* **Effective capacitance under DC bias** — stated as an open item under M15.
* **The dock's contact rating** — not in this repo; M16 explains why neither quantity
  that matters depends on it.
* **Active/NRND part status** — an order-time check, not a bench one (M42).
