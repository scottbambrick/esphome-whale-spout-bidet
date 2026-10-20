"""Checks the reference implementation against every packet captured from a real remote.
Run: python3 -m unittest discover -s tests   (no dependencies)"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import bidet_packet as bp  # noqa: E402

# (hex packet, key, n4, n5, n6, note) - captured from the remote with rtl_433 / an RTL-SDR
CAPTURED = [
    ("2a52333c", 0x52, 3, 3, 3, "Rear, all settings at level 2"),
    ("2a525552", 0x52, 5, 5, 5, "Rear, all settings at level 3"),
    ("2a521116", 0x52, 1, 1, 1, "Rear, all settings at level 1"),
    ("2a525350", 0x52, 5, 3, 5, "Rear, flow level 2, others level 3"),
    ("2ad23334", 0xD2, 3, 3, 3, "Female"),
    ("2a32333a", 0x32, 3, 3, 3, "Dry"),
    ("2a923330", 0x92, 3, 3, 3, "Stop"),
    ("2a560551", 0x56, 0, 5, 5, "Self clean (n4 is 0)"),
    ("2a721118", 0x72, 1, 1, 1, "Swing toggle"),
    ("2ab2011b", 0xB2, 0, 1, 1, "Massage toggle (n4 is 0)"),
    ("2a36133c", 0x36, 1, 3, 3, "Dry temperature button, level 1"),
    ("2a36333e", 0x36, 3, 3, 3, "Dry temperature button, level 2"),
    ("2a365330", 0x36, 5, 3, 3, "Dry temperature button, level 3"),
    ("2ad45316", 0xD4, 5, 3, 1, "Position back"),
    ("2ad45338", 0xD4, 5, 3, 3, "Position middle"),
    ("2ad4535a", 0xD4, 5, 3, 5, "Position forward"),
    ("2ad7515b", 0xD7, 5, 1, 5, "Flow 1"),
    ("2ad7535d", 0xD7, 5, 3, 5, "Flow 2"),
    ("2ad7555f", 0xD7, 5, 5, 5, "Flow 3"),
    ("2a840552", 0x84, 0, 5, 5, "Seat temperature off"),
    ("2a841553", 0x84, 1, 5, 5, "Seat temperature 1"),
    ("2a842554", 0x84, 2, 5, 5, "Seat temperature 2"),
    ("2a843555", 0x84, 3, 5, 5, "Seat temperature 3"),
    ("2a84011a", 0x84, 0, 1, 1, "Eco = seat temperature off"),
]


class PacketTests(unittest.TestCase):
    def test_captured_packets(self):
        for hexv, key, n4, n5, n6, note in CAPTURED:
            with self.subTest(note):
                p = int(hexv, 16)
                self.assertEqual(bp.decode(p), {"key": key, "n4": n4, "n5": n5, "n6": n6})
                self.assertEqual(bp.encode(key, n4, n5, n6), p)

    def test_bad_checksum_and_header(self):
        self.assertIsNone(bp.decode(0x2A52333D))
        self.assertIsNone(bp.decode(0x3A52333C))

    def test_level_codes(self):
        self.assertEqual([bp.level_code(i) for i in (1, 2, 3)], [1, 3, 5])
        self.assertEqual([bp.level_from_code(c) for c in (0, 1, 2, 3, 4, 5)], [0, 1, 0, 2, 0, 3])

    def test_burst_shape(self):
        b = bp.burst(0x2A52333C)
        self.assertEqual(len(b), 84)                       # 42 pulses
        self.assertEqual(sum(1 for x in b if x > 0), 42)
        self.assertLess(sum(abs(x) for x in b), 90000)     # ~83 ms on air
        self.assertEqual(b[:2], [240, -564])
        self.assertEqual(b[16:18], [564, -4524])           # sync after the 7 preamble pairs

    def test_press_spacing(self):
        p = bp.press(0x2A52333C)
        self.assertEqual(len(p), 168)
        first = sum(abs(x) for x in p[:84])
        self.assertAlmostEqual(first, 120000, delta=1)     # second burst starts 120 ms after the first

    def test_parse_roundtrip(self):
        for hexv, *_ in CAPTURED:
            p = int(hexv, 16)
            self.assertEqual(bp.parse(bp.burst(p)), p)
            # and with noise before, and the polarity inverted
            noisy = [-300, 800, -1200, 500] + bp.burst(p)
            self.assertEqual(bp.parse(noisy), p)
            self.assertEqual(bp.parse([-x for x in noisy]), p)

    def test_parse_rejects_garbage(self):
        self.assertIsNone(bp.parse([564, -564] * 40))


if __name__ == "__main__":
    unittest.main()
