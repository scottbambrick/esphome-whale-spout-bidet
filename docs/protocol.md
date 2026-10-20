# Xiaomi Whale Spout bidet seat remote: RF protocol

Everything here was reverse engineered from the seat's own remote with an RTL-SDR and then **verified by
replaying it from an ESP32 + CC1101: the seat accepts the commands and follows live setting changes**. Where
something is inferred rather than observed, it says so.

> **Which seat?** This is the **remote-controlled (non-Wi-Fi) Xiaomi Whale Spout** that ships with a small
> handheld RF remote and does *not* work with Mi Home. It is **not** the Wi-Fi *Whale Spout Smart Toilet Seat
> Pro* (`xjx.toilet.pro`, model LY-ST1808-008B), which is controlled from the Mi Home app. The Pro's manual
> (translated by [blakadder](https://github.com/blakadder/whale_spout_manual)) was only used for the
> temperature values in [Levels and temperatures](#levels-and-temperatures); the functions are similar but
> nothing here has been tested against the Pro.

Contents: [Radio layer](#radio-layer) · [Burst timing](#burst-timing) · [Packet format](#packet-format) ·
[Keys](#keys) · [Settings model](#settings-model-what-n4-n5-n6-mean) ·
[Levels and temperatures](#levels-and-temperatures) · [Behaviours and quirks](#behaviours-and-quirks) ·
[Receiving](#receiving-the-remote-with-a-cc1101) · [Unknowns](#what-is-not-known)

## Radio layer

| | |
|---|---|
| Band | 433 MHz ISM |
| Centre frequency | **433.908 MHz** (mark 433.942, space 433.873) |
| Modulation | **2-FSK**, deviation about **±34-35 kHz** (tones about 68-69 kHz apart) |
| Mark / space | pulse = high tone (+deviation), gap = low tone (-deviation) |
| Carrier | on for the whole burst: the "silence" between pulses is the *low tone*, not no signal |
| Codes | **fixed**: the same button always sends the same bits (no rolling code, no pairing) |
| Repeats | each press sends the burst **twice**, starts 120 ms apart |

Measured from a raw IQ recording (`rtl_433 -w`, 250 kS/s, tuned 433.92 MHz) with
[`tools/iq_tones.py`](../tools/iq_tones.py): mark +21.9 kHz, space -46.5 kHz from 433.92 MHz, four bursts
within 0.1 kHz of each other. The figure includes the remote's own crystal error (a few kHz), which is
irrelevant when you replay with a CC1101 *calibrated against the same recording* (see
[hardware.md](hardware.md#calibrating-the-frequency)).

Because the carrier never turns off during a burst, a plain OOK/ASK decoder sees nothing useful; rtl_433's
OOK flex decoder does not decode it. See [reverse-engineering.md](reverse-engineering.md).

## Burst timing

One burst, times in microseconds. `H` = high tone, `L` = low tone (the signal is on throughout):

```
H240 L564 | 7 x (H564 L564) | H564 L4524 | 32 data bits | H564 L19900 | carrier off
 lead-in      preamble          sync                        stop pulse + tail
```

* **Lead-in**: a short 240 us pulse (the remote's transmitter ramp-up). Optional when replaying.
* **Preamble**: seven plain `H564 L564` pairs. Together with the sync pulse these are eight "0" bits.
* **Sync**: `H564` then a long low tone of **4524 us**. This is what a receiver locks on to.
* **Data bit**: `H564` followed by `L564` for a **0** or `L1692` for a **1** (measured 1692-1696). The unit
  time is **T = 564 us**; a 0 gap is 1T and a 1 gap is 3T. **MSB first**, 32 bits.
* **Stop**: one more `H564`, then a low tone of about 19.9 ms.

42 pulses per burst, about 83 ms on air. A key press is that burst **twice**, the second starting **120 ms**
after the first. The first burst's low-tone tail is therefore about 57 ms instead of 19.9 ms:

```
 burst 1 (83 ms)           low tone (37 ms, then the normal tail)       burst 2 (83 ms)        carrier off
 |<---------------------->|<------------ rest of the 120 ms --------->|<-------------------->|
 start                                                      start of burst 2 = start + 120 ms
```

[`tools/bidet_packet.py`](../tools/bidet_packet.py) generates and parses this, and the unit tests check it
against every packet captured from a real remote.

When replaying with a CC1101 in asynchronous serial mode the chip needs a few milliseconds after entering TX
(PLL calibration and settling) before it modulates correctly. The ESPHome config therefore starts every
transmission with **10 ms of low tone** (`-10000`), which the seat ignores. Without it the first pulses were
clipped and the seat did not respond.

## Packet format

32 bits, written as 8 hex nibbles `n0 .. n7`, MSB first:

```
 2  a | k1 k0 | n4 | n5 | n6 | cc
 header  key    "settings" (3 nibbles)  checksum
```

| Field | Meaning |
|---|---|
| `n0 n1` | constant `2a` |
| `n2 n3` | the **key** (which button), see [Keys](#keys) |
| `n4 n5 n6` | the remote's remembered **settings** for the function the key belongs to, see [Settings model](#settings-model-what-n4-n5-n6-mean) |
| `n7` | checksum = **(n0 + n1 + ... + n6) mod 16** |

Example, **Rear** with every setting at its middle level: `2a 52 3 3 3 c` = `2a52333c`. Sum
`2+10+5+2+3+3+3 = 28`, `28 mod 16 = 12 = c`.

Levels are sent as **1 / 3 / 5** for level 1 / 2 / 3 (default middle level = 3). The seat-heater level is the
exception: it is the plain number **0..3**.

## Keys

| Key | Button | `n4` | `n5` | `n6` | Notes |
|---|---|---|---|---|---|
| `52` | **Rear** wash | rear temperature | rear flow | rear position | |
| `D2` | **Female** wash | female temperature | female flow | female position | |
| `32` | **Dry** | dry temperature | (copy of last function) | (copy of last function) | |
| `92` | **Stop** | repeats the previous packet's `n4` | | | also cancels a self-clean |
| `56` | **Self clean** | `0` | | | one code starts *and* cancels; use Stop to cancel |
| `72` | **Swing** | | | | toggle: the same code each press, the seat decides |
| `B2` | **Massage** | `0` | | | toggle, same code each press |
| `84` | **Seat temperature** | seat level `0..3` | | | single button cycling off, 3, 2, 1, off. "Eco" is the same packet as level 0 |
| `D6` | temperature up/down (Rear / Female, or nothing running) | the new temperature | triple of the current function | | absolute level, not up/down |
| `36` | temperature up/down **while Dry runs** | the new dry temperature | | | |
| `D7` | flow up/down | | the new flow | | |
| `D4` | position up/down | | | the new position | 1 = back, 2 = middle, 3 = forward |

All level buttons send an **absolute level** (pressing "down" at level 1 re-sends level 1).

Which of `D6` / `36` the remote sends depends on what is running: the same two physical temperature buttons
send `36` while the dryer is running and `D6` otherwise. (An early capture session recorded `36` for "the"
temperature buttons because it happened to be done with Dry active; `D6` was found later.)

## Settings model: what n4, n5, n6 mean

The seat has **separate settings per function**, and the remote sends the values of the function you are
using in the three settings nibbles of every packet:

| Function | temperature | flow | position |
|---|---|---|---|
| Rear | own (`n4`) | own (`n5`) | own (`n6`) |
| Female | own (`n4`) | own (`n5`) | own (`n6`) |
| Dry | own (`n4`) | none known | none known |
| Seat heater | one global level (key `84`), plain `0..3` | | |

How the three nibbles are used, as observed:

* **A Rear / Female / Dry packet carries that function's settings.** Pressing Rear on the remote tells you
  Rear's temperature, flow and position; Female does the same for Female; Dry gives the dry temperature.
  (`2a525552` = Rear with temperature 3, flow 3, position 3; `2a521116` = all at level 1.)
* **A temperature / flow / position button packet carries the whole triple of the function being adjusted**,
  with the touched setting changed. For example after Rear (`5 5 5`) a flow press sent `n4=5 n5=3 n6=5`:
  Rear's other two values unchanged, flow now level 2.
* The temperature, flow and position buttons act on the **function last used**. The packet itself does not say
  which function (Rear and Female both use `D6/D7/D4`), so a listener has to remember the last Rear / Female /
  Dry key it saw. Dry's temperature is the exception: it has its own key (`36`).
* `n4` of **Stop** repeats whatever the previous packet had; ignore it.
* The seat reports nothing back. The remote is the only place the settings live, so **the only way to learn
  them is to listen to the remote**.

Not every key carries meaningful settings: **Self clean** and **Massage** send `n4 = 0`; **seat temperature**
(`84`) puts the seat level in `n4`, and its `n5`/`n6` are a copy of the last function's.

**Does the seat use the values in the packet, or its own memory?** Changing a slider while a function runs
(sending `D6`/`D7`/`D4`/`36` with the new value) changes the running seat immediately, so the seat obeys the
level-button packets. Whether it also takes the settings from a Rear / Female / Dry *start* packet is not
proven; the ESP32 sends the function's own values in both cases, as the remote would, so it works either way.

## Levels and temperatures

Levels go 1..3 (seat heater 0..3 where 0 is off). The temperatures below are from the translated manual of the
Wi-Fi *Pro* model and are approximate; the remote-controlled model uses the same three-level scheme and its
temperatures are expected to be similar, but have not been measured.

| Setting | Level 0 | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|
| Wash water (Rear / Female) | | about 35 C | about 37 C | about 39 C |
| Drying air | | about 36 C | about 43 C | about 50 C |
| Seat ring | off (room temp) | about 32 C | about 35 C | about 38 C |

Other behaviour from the same manual: wash and dry runs stop by themselves after about 2 minutes; leaving
the seat stops everything; the seat ring drops to a low level after sitting more than 10 minutes. The seat
draws about **46-60 W at seat-heat level 3** (measured with a power-monitoring plug) and nothing at level 0.

## Behaviours and quirks

* Every command the seat accepts is acknowledged with a **beep**: handy when testing a replay.
* Swing and Massage send the *same* code every press; the seat toggles. Self clean toggles too, but Stop is
  the reliable way to cancel it.
* There are no up/down buttons on the wire, only absolute levels.
* No rolling code, no challenge, no pairing: anyone who can transmit at 433.9 MHz can operate the seat. See
  [access-control.md](access-control.md) for how this project guards against misuse from inside the house.
* The two bursts of a press are identical; a receiver only needs to hear one.

## Receiving the remote with a CC1101

The same CC1101 can listen to the remote: GDO2 outputs the demodulated 2-FSK as a serial pulse stream
(IOCFG2 = 0x0D). The CC1101 has no squelch, so with no signal it delivers a constant stream of noise "pulses"
(about two frames a second). The decoder in [`includes/bidet_seat.h`](../includes/bidet_seat.h) therefore:

1. takes each frame ESPHome's `remote_receiver` delivers (pulses shorter than 200 us ignored, frame ends after
   8 ms of no change);
2. looks anywhere in it for the **sync gap** (3.4-5.8 ms, polarity ignored);
3. reads the 32 following `(pulse, gap)` pairs, a gap over 1128 us being a 1;
4. accepts the packet only if the header is `2a` and the **checksum** is right.

That is what makes it robust against the noise, a neighbour's weather station, and everything else on 433 MHz.
Reception from 20 cm is good but not perfect (some presses decode only one of the two bursts, or none), so
nothing important should depend on hearing a single press.

## What is not known

* Whether the seat takes the settings from the start packet or only from the level buttons (see above).
* Whether Dry has flow or position settings of its own; its packets only ever showed copies of the last
  function's values.
* The remote's header **CN3** (TX / GND / RX / +5V) was never probed; it may expose a UART.
* Other model variants of the remote (different key codes) are untested.
