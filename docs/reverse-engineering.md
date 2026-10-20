# How the protocol was reverse engineered

A short write-up of the method, in case you have a different model or want to check the work. All you need is
an RTL-SDR and `rtl_433`.

## 1. Is it RF? On which frequency?

The remote was not infrared (no IR LED, nothing on a phone camera) and the seat has no Wi-Fi. An RTL-SDR with
a 433 MHz antenna and any waterfall (SDR++, SDRangel, `rtl_433 -f 433.92M`) showed a burst at **433.9 MHz**
every time a button was pressed. 433.92 MHz is the standard ISM centre; the remote sits about 12 kHz below it.

## 2. Capture the packets with rtl_433

```
rtl_433 -f 433.92M -s 250k -A 2>&1 | grep -E "Detected|view at|codes"
```

`-A` is the pulse analyser. Things learnt:

* The remote is **FSK, not OOK**. rtl_433's OOK flex decoder (`-X ... m=OOK_PPM...`) showed nothing; the
  analyser, which always runs, still shows the bursts as "Detected FSK package".
* rtl_433 prints each burst twice (whole, then again split at the sync gap) and its own `codes :` line is
  unreliable (`{9}800`, `{42}8000...`). Ignore it.
* Decode the **triq pulse row** instead. The "view at https://triq.org/pdv/#AAB0..." link encodes the pulse
  widths; in the row, after the lead-in and preamble tokens, 32 data tokens follow where one token value means
  a 564 us gap (bit 0) and the other a 1692 us gap (bit 1).
* Other devices on 433 MHz show up in the same capture (a weather station's long packets, neighbours). They
  are easy to tell apart: the remote's burst is 42 pulses of 564 us.

Press **one button at a time**, several times, and write down which. Identical bits on every press means a
fixed code. Each press produced two identical bursts 120 ms apart.

## 3. Work out the structure

Collect the packets for every button, in different remote states, and compare:

* The first byte `2a` never changed.
* The last nibble is the **sum of the others mod 16**; verified on every packet.
* Changing temperature / flow / position changed the nibbles in the middle; pressing the same function button
  after changing a setting showed which nibble belonged to which setting, and that levels are sent as 1/3/5.
* The remote also changes behaviour with context (which function is running), so the "temperature" buttons
  turned out to use two different key codes. This was found only when receiving live (see below) and
  pressing temperature buttons while Dry, then Rear, was running. If two buttons you think are the same
  produce different codes, test them in every mode.

The result is in [protocol.md](protocol.md), and `tests/test_packets.py` holds every captured packet.

## 4. Measure the signal precisely

For replaying, the exact frequency, deviation and timings matter. Record raw IQ:

```
rtl_433 -f 433.92M -s 250k -w remote.cu8
python3 tools/iq_tones.py remote.cu8
```

The tool measures the two tone frequencies and the pulse and gap lengths. That gave mark +21.9 kHz, space
-46.5 kHz from 433.92 MHz and the 564 us unit time.

## 5. Replay and verify

With the CC1101 in asynchronous serial mode and GDO0 driven by ESPHome's `remote_transmitter` (see
[hardware.md](hardware.md)): record what *your* transmitter produces with the same tool, compare timings and
tone frequencies against the real remote, and fix the frequency offset. The seat's **beep** confirms it
accepted a command.

## 6. Listen live

Once the CC1101 can also receive (GDO2), log every decoded packet with its key and nibbles and run experiments
while pressing buttons on the real remote. That is how the per-function settings (Rear and Female having
independent temperature/flow/position, Dry its own temperature) were worked out: change one setting, press
each function, see which packets changed. Useful experiments:

* set a setting to level 1, 2, 3 in turn, pressing each function between (does the nibble follow?);
* press the level buttons with nothing running, then while each function runs;
* press Stop between experiments to end the running function.
