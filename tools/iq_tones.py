"""Measure the tones and timings of 433 MHz 2-FSK bursts in an RTL-SDR recording (pure Python, no numpy).

Use it to (1) measure the real remote's mark/space frequencies, and (2) check what your CC1101 actually
transmits, so you can set `cc1101_frequency` to match the remote (see docs/hardware.md).

  rtl_433 -f 433.92M -s 250k -w remote.cu8      # record: press a button a few times, then Ctrl-C
  python3 tools/iq_tones.py remote.cu8            # list the bursts, then the tones of the first one
  python3 tools/iq_tones.py remote.cu8 --burst 2  # analyse the 2nd burst instead

Prints, for the chosen burst, the two tone frequencies relative to the tuned centre (433.92 MHz), the centre
between them, the deviation, and the pulse/gap run lengths in microseconds (H = high tone, L = low tone).
Assumes complex uint8 I/Q (.cu8) at 250 kHz sample rate and a centre frequency of 433.92 MHz; change
FS / CENTRE_HZ below otherwise. Weather stations and other 433 MHz devices show up as short bursts too:
look for the ~220 ms (two-burst) or ~83 ms (one-burst) transmissions.
"""
import argparse
import math

FS = 250_000.0
CENTRE_HZ = 433_920_000.0
BLOCK = 250  # 1 ms power blocks for burst detection


def load(path):
    with open(path, "rb") as f:
        return f.read()


def find_bursts(data, min_ms=20):
    n = len(data) // 2
    mags = []
    for k in range(n // BLOCK):
        seg = data[2 * k * BLOCK: 2 * (k + 1) * BLOCK]
        total = 0.0
        for i in range(0, len(seg), 2):
            total += math.hypot(seg[i] - 127.5, seg[i + 1] - 127.5)
        mags.append(total / BLOCK)
    med = sorted(mags)[len(mags) // 2]
    thr = med * 2.5
    bursts, i = [], 0
    while i < len(mags):
        if mags[i] > thr:
            j = i
            while j < len(mags) and (mags[j] > thr or any(mags[j + d] > thr for d in (1, 2) if j + d < len(mags))):
                j += 1
            if j - i >= min_ms:
                bursts.append((i, j))
            i = j
        else:
            i += 1
    return bursts, med


def inst_freq(data, start_ms, dur_ms):
    a, b = int(start_ms * FS / 1000), int((start_ms + dur_ms) * FS / 1000)
    I = [data[2 * i] - 127.5 for i in range(a, b)]
    Q = [data[2 * i + 1] - 127.5 for i in range(a, b)]
    f = []
    for i in range(1, len(I)):
        re = I[i] * I[i - 1] + Q[i] * Q[i - 1]
        im = Q[i] * I[i - 1] - I[i] * Q[i - 1]
        f.append(math.atan2(im, re) * FS / (2 * math.pi))
    return [sum(f[i:i + 5]) / 5 for i in range(0, len(f) - 5)]  # 5-sample smoothing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--burst", type=int, default=1, help="which detected burst to analyse (1 = first)")
    ap.add_argument("--min-ms", type=int, default=20, help="ignore bursts shorter than this")
    args = ap.parse_args()

    data = load(args.file)
    bursts, med = find_bursts(data, args.min_ms)
    print("noise floor %.1f, %d bursts >= %d ms:" % (med, len(bursts), args.min_ms))
    for n, (a, b) in enumerate(bursts, 1):
        print("  %2d  t=%.3f s  duration %d ms" % (n, a / 1000, b - a))
    if not bursts:
        return
    a, b = bursts[min(args.burst, len(bursts)) - 1]
    g = inst_freq(data, a, b - a)
    srt = sorted(g)
    lo, hi = srt[int(len(g) * 0.05)], srt[int(len(g) * 0.95)]
    # tone = median of each cluster either side of the midpoint
    mid = (lo + hi) / 2
    low = sorted(x for x in g if x < mid)
    high = sorted(x for x in g if x >= mid)
    fl, fh = low[len(low) // 2], high[len(high) // 2]
    print("\nburst %d: tones relative to %.4f MHz:" % (args.burst, CENTRE_HZ / 1e6))
    print("  high tone (mark)  %+8.1f kHz  = %.4f MHz" % (fh / 1e3, (CENTRE_HZ + fh) / 1e6))
    print("  low tone  (space) %+8.1f kHz  = %.4f MHz" % (fl / 1e3, (CENTRE_HZ + fl) / 1e6))
    print("  centre            %+8.1f kHz  = %.4f MHz   deviation +-%.1f kHz" % (
        (fh + fl) / 2e3, (CENTRE_HZ + (fh + fl) / 2) / 1e6, (fh - fl) / 2e3))
    runs, cur, n = [], g[0] > mid, 0
    for x in g:
        s = x > mid
        if s == cur:
            n += 1
        else:
            runs.append((cur, n / FS * 1e6))
            cur, n = s, 1
    print("\npulse / gap run lengths (us), first 100:")
    print(" ".join("%s%d" % ("H" if c else "L", round(u)) for c, u in runs[:100]))


if __name__ == "__main__":
    main()
