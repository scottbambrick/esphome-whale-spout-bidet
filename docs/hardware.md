# Hardware

## What you need

* An **ESP32** dev board. Developed on a classic 38-pin ESP32 devkit (`esp32dev`, ESP-IDF). The RMT-based
  transmitter/receiver and the CC1101 component work on other ESP32 variants too, but only the classic ESP32
  has been tested.
* A **CC1101 433 MHz module**: developed with an **EByte E07-M1101D** (the 8-pin board with an SMA connector).
  Any CC1101 board with GDO0 and GDO2 broken out will do. 3.3 V only.
* A **433 MHz antenna**. The ESP32 and seat were about 20 cm to a few metres apart in testing; a stock
  quarter-wave whip works, a stubby one is fine at short range.
* Optional: a Zigbee/Wi-Fi **power-monitoring plug** for the seat (measures the seat heater and gives an
  energy figure).

The seat's own remote is only needed to **learn from** (and as the unlock key, see
[access-control.md](access-control.md)).

## Wiring

CC1101 module pin to ESP32 devkit GPIO (E07-M1101D numbering, verified working):

| Module pin | Name | ESP32 | Purpose |
|---|---|---|---|
| 1 | GND | GND | |
| 2 | VCC | **3V3** | **not 5 V** |
| 3 | GDO0 | GPIO4 | **transmit data** (async serial TX input) |
| 4 | CSN | GPIO5 | SPI chip select |
| 5 | SCK | GPIO18 | SPI clock |
| 6 | MOSI | GPIO23 | SPI MOSI |
| 7 | MISO | GPIO19 | SPI MISO |
| 8 | GDO2 | GPIO16 (labelled **RX2** on many boards) | **receive data** (demodulated serial) |

Notes learnt the hard way:

* **GDO0 is the transmit pin.** With the transmit GPIO wired to GDO2 instead, the seat did not respond and
  rtl_433 only saw short OOK-looking junk. GDO2 is an *output* of the chip (it carries the receive data), so
  driving it from the ESP32 is wrong.
* A single unplugged jumper (MOSI) made the chip ID read `0x0F0F` instead of `0x0014`: the log line
  `CC1101: Chip ID: 0x0014` at boot is the quickest wiring check.
* If your board labels differ, go by the silkscreen names (GDO0/GDO2/CSN/SCK/MOSI/MISO), not pin numbers.

## Calibrating the frequency

This is the step that decides whether the seat reacts at all.

The seat's receiver is narrow. A CC1101's frequency is derived from its 26 MHz crystal, and cheap modules are
typically tens of ppm off (at 434 MHz, 80 ppm is 35 kHz). The module this project was developed with
transmitted **35 kHz low** when told 433.9077 MHz, and the seat ignored it even though the timings were
perfect.

You need an RTL-SDR (or similar) and about ten minutes:

1. **Record the real remote.** Tune 433.92 MHz at 250 kS/s and press a button a few times:

   ```
   rtl_433 -f 433.92M -s 250k -w remote.cu8
   python3 tools/iq_tones.py remote.cu8
   ```

   You should see a centre near 433.908 MHz (about -12 kHz from the tuned 433.92) and a deviation of about
   ±34-35 kHz. Note the reported centre.

2. **Record your ESP32 transmitting** (press the Rear button in Home Assistant a couple of times; the
   controls must be unlocked or use Stop, which is never blocked) with the same command, and run the tool on
   that file. Note *its* reported centre.

3. **Correct the difference** in `cc1101_frequency`:

   ```
   new = current + (remote centre - your centre)
   ```

   e.g. the remote was at 433.9080 MHz, the ESP32 at 433.8725 MHz, setting 433.9077: the new setting is
   433.9077 + 0.0355 = **433.9432 MHz**.

4. Flash, record again, and check the two tone frequencies are within a couple of kHz of the remote's
   (mark about +22 kHz, space about -46.5 kHz from 433.92). The seat will beep on each accepted command.

You can also calibrate with the transmitter only: if the seat does not beep at all with correct timings,
the frequency is the first thing to adjust.

## Transmit power and regulations

`output_power: 5` (dBm) is plenty at a few metres. 433 MHz low-power-device rules vary by country (in Australia
the limit is 25 mW EIRP, 14 dBm); check yours before raising it, and note this only re-creates the seat's own
remote at the same frequency and power class.

## Antenna and range

The remote is a very low-power transmitter, so *receiving* it is the limiting direction. From 20 cm
essentially every press is heard (usually one of the two bursts is enough). Test the final mounting spot with
the "Remote Packets Heard" counter in [`example.yaml`](../example.yaml): press a button ten times and see how
many packets are counted (twenty is perfect). Transmitting to the seat is far less demanding.

## The remote's electronics (for reference)

PCB marked **"MOEXT CAP Touch Remote Control V2.2"** (20191122): a **Holtek BS66F350** touch MCU, a separate
radio chip, a **26.000 MHz** crystal and a small meander PCB antenna. Header **CN3** is `TX / GND / RX / +5V`
(a UART; never probed).
