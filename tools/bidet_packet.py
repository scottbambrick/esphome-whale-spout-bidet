"""Reference implementation of the Xiaomi Whale Spout bidet remote's RF packet (433 MHz 2-FSK).

No dependencies. Mirrors includes/bidet_seat.h; docs/protocol.md describes the format.

    python3 tools/bidet_packet.py 2a52333c        # decode a packet
    python3 tools/bidet_packet.py --encode 0x52 3 3 3   # key n4 n5 n6 -> packet

Packet = 8 nibbles: 2 a | key (2 nibbles) | n4 n5 n6 | checksum
  checksum = (sum of the first 7 nibbles) mod 16
  n4 / n5 / n6 are the remote's remembered settings of the function the key belongs to (see docs/protocol.md);
  levels 1/2/3 are coded 1/3/5, except the seat heater which is the plain level 0..3.
"""
import sys

# Burst timings in microseconds (see docs/protocol.md)
UNIT = 564
LEAD = 240
SYNC_GAP = 4524
GAP0 = 564
GAP1 = 1692
TAIL = 19900
PAD = 10000          # extra idle low tone ESPHome adds before the first burst so the CC1101 can settle
BURST_SPACING = 120000   # start to start of the two bursts of one press

KEYS = {
    0x52: "Rear",
    0xD2: "Female",
    0x32: "Dry",
    0x92: "Stop",
    0x56: "Self clean",
    0x72: "Swing (toggle)",
    0xB2: "Massage (toggle)",
    0x84: "Seat temperature",
    0xD6: "Water temperature (temperature buttons, nothing running or Rear/Female running)",
    0x36: "Dry temperature (temperature buttons while Dry runs)",
    0xD7: "Flow",
    0xD4: "Position",
}


def level_code(level):
    """Level 1/2/3 -> 1/3/5 as sent on the wire."""
    return 2 * level - 1


def level_from_code(code):
    """Wire code 1/3/5 -> level 1/2/3, or 0 if it is not a level code."""
    return (code + 1) // 2 if code in (1, 3, 5) else 0


def checksum(nibbles):
    return sum(nibbles[:7]) & 0xF


def encode(key, n4, n5, n6):
    """Build a 32-bit packet from the key byte and the three raw nibbles."""
    n = [0x2, 0xA, (key >> 4) & 0xF, key & 0xF, n4 & 0xF, n5 & 0xF, n6 & 0xF]
    n.append(checksum(n))
    value = 0
    for x in n:
        value = (value << 4) | x
    return value


def decode(packet):
    """Return dict(key, n4, n5, n6) or None if the header or checksum is wrong."""
    n = [(packet >> (28 - 4 * i)) & 0xF for i in range(8)]
    if n[0] != 0x2 or n[1] != 0xA or checksum(n) != n[7]:
        return None
    return {"key": (n[2] << 4) | n[3], "n4": n[4], "n5": n[5], "n6": n[6]}


def burst(packet):
    """One burst as signed microsecond timings: positive = high tone, negative = low tone. 84 values."""
    t = [LEAD, -UNIT]
    t += [UNIT, -UNIT] * 7          # preamble
    t += [UNIT, -SYNC_GAP]          # sync
    for i in range(31, -1, -1):     # 32 data bits, MSB first
        t += [UNIT, -(GAP1 if (packet >> i) & 1 else GAP0)]
    t += [UNIT, -TAIL]              # stop pulse + tail
    return t


def press(packet):
    """What the remote sends for one key press: the burst twice, 120 ms start to start."""
    a = burst(packet)
    a[-1] = -(BURST_SPACING - sum(abs(x) for x in a[:-1]))
    return a + burst(packet)


def parse(timings):
    """Find a packet in a list of (signed or unsigned) pulse/gap durations. Polarity does not matter:
    after the long sync gap come 32 (pulse, gap) pairs; a gap of ~564 us is 0 and ~1692 us is 1."""
    n = len(timings)
    for i in range(n - 1):
        if not 3400 < abs(timings[i]) < 5800:
            continue
        value, bits, j = 0, 0, i + 1
        while j + 1 < n and bits < 32:
            mark, gap = abs(timings[j]), abs(timings[j + 1])
            if not (300 < mark < 1000 and 300 < gap < 2400):
                break
            value = (value << 1) | (1 if gap > 1128 else 0)
            bits += 1
            j += 2
        if bits == 32:
            return value
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--encode" and len(args) == 5:
        key, n4, n5, n6 = (int(x, 0) for x in args[1:])
        print("%08x" % encode(key, n4, n5, n6))
    elif len(args) == 1:
        d = decode(int(args[0], 16))
        if d is None:
            sys.exit("not a valid packet (header 2a / checksum)")
        print("key 0x%02X (%s)  n4=%d n5=%d n6=%d" % (d["key"], KEYS.get(d["key"], "unknown"), d["n4"], d["n5"], d["n6"]))
    else:
        print(__doc__)
