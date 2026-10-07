/*
 * pins.h — the ESP32-WROOM-32E pin map for the v2 watering-backpack board,
 *          and the one function that puts every pin into its legal mode.
 *
 * WHY THIS FILE EXISTS. Writing the pin setup out, pin by pin, with the reason
 * for each mode next to it, is the only way to be forced to confront every pin
 * before the board is fabbed. A pin map that is only a list of numbers can be
 * wrong in ways no compiler and no DRC can see: an analogue signal on ADC2 with
 * WiFi up, an output on an input-only pad, a driven net on a strapping pin.
 *
 * SOURCES, and they are the only two that count:
 *   NET  = elec/out/main.net — the netlist. It is authoritative for which
 *          MODULE PIN carries which net. Every GPIO below was read out of it.
 *   DS-M = ESP32-WROOM-32E & ESP32-WROOM-32UE Datasheet v2.1
 *          §3.2 Table 3 "Pin Definitions"  (module pin -> GPIO + functions)
 *          §4   Table 4 "Default Configuration of Strapping Pins"
 *               Table 6 "Chip Boot Mode Control"
 *   DS-C = ESP32 Series Datasheet v5.3
 *          Appendix A, Table 6-1 note 2  (GPIO34-39 input-only, no pulls)
 *          Appendix A.4 Table IO_MUX, columns "At Reset" / "After Reset"
 *   IDF  = ESP-IDF v5.3, ADC Oneshot Mode Driver, "Hardware Limitations"
 *          ("ADC2 is also used by Wi-Fi.")
 *
 * THE NETLIST'S VIEW OF U2, complete. Twelve module pins are connected; these
 * are all of them. Six are firmware-controlled and get a constant below; the
 * other six are hardware-only and are listed here so that "every pin from the
 * netlist" means every pin, not every pin someone remembered.
 *
 *   mod pin | DS-M name | net            | who owns it
 *   --------+-----------+----------------+-------------------------------------
 *      1    | GND       | GND            | plane. DS-M Table 3: P (ground)
 *      2    | 3V3       | +3V3           | U1 buck out, C6/C7 local
 *      3    | EN        | EN             | R3 10k pull-up + C8 1u + J6.5 (DTR).
 *                                          DS-M Table 3: "Do not leave floating"
 *                                          — it is not floating. Not a GPIO.
 *      6    | IO34      | JOY_FILT       | JOY_PIN   (below)
 *      7    | IO35      | VBAT_SENSE     | VBAT_PIN  (below)
 *     10    | IO25      | PWM_B          | PUMP_B_PIN(below)
 *     11    | IO26      | PWM_A          | PUMP_A_PIN(below)
 *     12    | IO27      | BUZZ           | BUZZ_PIN  (below)
 *     13    | IO14      | LEVEL          | LEVEL_PIN (below)
 *     15    | GND       | GND            | plane
 *     25    | IO0       | IO0            | J6.6 only. STRAPPING — see pins.cpp
 *                                          §"Strapping pins, tested". Firmware
 *                                          must never touch it: no constant.
 *     34    | RXD0      | ESP_RX_FROM_PROG | GPIO3, U0RXD. Owned by Serial.
 *     35    | TXD0      | ESP_TX_TO_PROG   | GPIO1, U0TXD. Owned by Serial.
 *     38,39 | GND       | GND            | plane + exposed pad
 *
 *   NOT connected, and therefore NOT configured here: module pins 4 (IO36),
 *   5 (IO39), 8 (IO32), 9 (IO33), 14 (IO12), 16 (IO13), 23 (IO15), 24 (IO2),
 *   26 (IO4), 27 (IO16), 28 (IO17), 29 (IO5), 30 (IO18), 31 (IO19), 33 (IO21),
 *   36 (IO22), 37 (IO23) — and module pins 17-22 and 32, which DS-M Table 3
 *   lists as NC (note 2: GPIO6-11 are bonded to the module's own SPI flash and
 *   are not led out at all). Inventing a pin here would be inventing a net.
 */
#pragma once
#include <Arduino.h>

// ── Pin map ──────────────────────────────────────────────────────────────────
// GPIO numbers are from elec/out/main.net via DS-M Table 3. tools/check_pin_map.py
// re-derives them from the schematic source and fails if these drift.
constexpr int JOY_PIN   = 34;  // mod 6,  JOY_FILT    — ADC1_CH6, input-only
constexpr int VBAT_PIN  = 35;  // mod 7,  VBAT_SENSE  — ADC1_CH7, input-only
constexpr int LEVEL_PIN = 14;  // mod 13, LEVEL       — MTMS/ADC2_CH6, read digitally
constexpr int BUZZ_PIN  = 27;  // mod 12, BUZZ        — Q3 base via R24
constexpr int PUMP_A_PIN = 26; // mod 11, PWM_A       — U3 IN+, tank -> pot
constexpr int PUMP_B_PIN = 25; // mod 10, PWM_B       — U4 IN+, pot  -> tank

// ── Peripheral settings that pinsInit() programs ─────────────────────────────
constexpr int PWM_FREQ = 20000;  // 20 kHz — above audible, easy for the gate driver
constexpr int PWM_RES  = 8;      // 8-bit duty (0..255)
constexpr int ADC_RES  = 12;     // 12-bit SAR, the ESP32's native ADC width

// Put every connected, firmware-controlled pin into its legal mode. Safe to
// call exactly once, first thing in setup(), before anything can command a pump.
void pinsInit();
