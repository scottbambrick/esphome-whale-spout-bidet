# esphome-whale-spout-bidet

Control a **Xiaomi Whale Spout bidet toilet seat** from Home Assistant with an **ESP32 + CC1101** running
ESPHome, by speaking the seat's own **433 MHz RF remote protocol**. The ESP32 also **listens to the real
remote**, so Home Assistant always knows the seat's temperature, flow, position and heater settings.

> **Which seat?** This is for the **remote-controlled (non-Wi-Fi) Whale Spout**: the one with a small
> handheld RF remote that does **not** work with Mi Home and isn't infrared. It is *not* the Wi-Fi
> "Whale Spout Smart Toilet Seat Pro" (`xjx.toilet.pro`), which has an app. The protocol was reverse
> engineered from the remote of the remote-controlled model and verified on that seat. See
> [docs/protocol.md](docs/protocol.md) for the complete protocol write-up.

## What you get

* Buttons for **Rear**, **Female**, **Dry**, **Stop**, **Self clean**, **Swing** and **Massage**.
* Sliders for each function's own settings: **Rear** and **Female** temperature / flow / position, **Dry**
  temperature, and the **seat heater** (0 = off, 1-3). Moving a slider while a function runs changes it live.
* **Two-way state**: the ESP32 decodes the real remote, so changes made with the remote show up in Home
  Assistant (the seat itself reports nothing).
* **Access control**: the controls are locked until somebody presses a button on the real remote, so nobody
  can run the seat from the other side of the house while it's in use. See
  [docs/access-control.md](docs/access-control.md).
* **Away mode** for an automation: heater off while nobody's home, restored when somebody returns.
* A ready-made Home Assistant [dashboard](home-assistant/dashboard.json) and
  [away automation](home-assistant/away-automation.yaml).

## Hardware

* An ESP32 dev board (developed on a classic 38-pin ESP32 devkit).
* A **CC1101** 433 MHz module (EByte E07-M1101D), 3.3 V.
* A 433 MHz antenna.
* The seat's remote (to unlock the controls, and to calibrate against).

Wiring is in [docs/hardware.md](docs/hardware.md) and the header of [`example.yaml`](example.yaml).

## Quick start

1. Wire the CC1101 to the ESP32 as in [docs/hardware.md](docs/hardware.md). Check the boot log for
   `CC1101: Chip ID: 0x0014`.
2. Copy [`example.yaml`](example.yaml) and [`includes/bidet_seat.h`](includes/bidet_seat.h) into your ESPHome
   folder (keep the `includes/` path), add `api_key`, `wifi_ssid` and `wifi_password` to `secrets.yaml`, and flash.
3. **Calibrate `cc1101_frequency`.** CC1101 modules are typically tens of kHz off, and the seat's receiver
   is narrow, so this is the step that decides whether the seat reacts at all. Follow
   [docs/hardware.md#calibrating-the-frequency](docs/hardware.md#calibrating-the-frequency) with an RTL-SDR.
4. Adopt the device in Home Assistant, press **Stop** in HA and listen for the seat's beep.
5. Press any button on the real remote; the controls unlock and the **Last Remote Button** sensor shows it.
6. Optional: import [`home-assistant/dashboard.json`](home-assistant/dashboard.json) (new dashboard, raw
   configuration editor) and the [away automation](home-assistant/away-automation.yaml). Both use entity IDs
   derived from the device name; adjust them to yours.

## Entities

Everything belongs to an ESPHome sub-device called *Bidet Seat*.

| Entity | What it does |
|---|---|
| `button` Rear / Female / Dry / Stop / Self Clean / Swing Toggle / Massage Toggle | send that command (Stop is never blocked by the lock) |
| `number` Rear / Female Temperature, Flow, Position (1-3) | that function's settings |
| `number` Dry Temperature (1-3), Seat Temperature (0-3) | |
| `binary_sensor` Controls Unlocked, `sensor` Unlock Time Remaining | the lock state |
| `button` Lock Controls | re-lock immediately |
| `text_sensor` Last Remote Button, `sensor` Remote Packets Heard | what the ESP32 heard from the real remote (useful for range tests) |
| `text_sensor` Current Function | Rear / Female / Dry: the wash the temperature, flow and position settings apply to (kept across reboots) |
| `switch` Seat Heat Away Mode | for the away automation |

## How it works, briefly

* The remote sends fixed 32-bit packets by **2-FSK at 433.908 MHz**: header `2a`, a key byte, three
  "settings" nibbles and a checksum nibble, each press sent twice. The ESP32 builds the same timings with
  ESPHome's `remote_transmitter` driving the CC1101 in asynchronous serial mode.
* The settings nibbles of a Rear / Female / Dry packet are *that function's* remembered settings; the level
  buttons adjust the function last used. Listening to those packets is how Home Assistant stays in sync.
* Nothing else is needed from the seat: it never talks back.

Details, timing diagrams and every captured code are in [docs/protocol.md](docs/protocol.md); how it was
worked out is in [docs/reverse-engineering.md](docs/reverse-engineering.md).

## Tools and tests

* [`tools/bidet_packet.py`](tools/bidet_packet.py): encode/decode packets and generate/parse the burst timings.
* [`tools/iq_tones.py`](tools/iq_tones.py): measure the tones and timings in an RTL-SDR recording (for
  calibration).
* `python3 -m unittest discover -s tests`: checks the implementation against every packet captured from a real
  remote. CI also compiles `example.yaml`.

## Limitations

* Tested with one seat and one remote, on a classic ESP32. Other remote variants may use different codes.
* Reception of the remote is good at close range but not perfect; press again if a press doesn't register.
* Whether the seat takes its settings from the start packet or only from the level buttons isn't proven; the
  config works either way (see [what is not known](docs/protocol.md#what-is-not-known)).
* The temperatures in the docs come from the Wi-Fi Pro model's manual and are approximate for this model.

## Safety and legal

This controls a heated, wet appliance. Use it at your own risk; keep the access control enabled. 433 MHz
transmit power and duty rules vary by country (the default `output_power: 5` dBm is low). Not affiliated with
or endorsed by Xiaomi or Whale Spout. The Wi-Fi model's manual translation by
[blakadder](https://github.com/blakadder/whale_spout_manual) was a useful reference for the temperature levels.

MIT licensed, see [LICENSE](LICENSE).
