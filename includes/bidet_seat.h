#pragma once
#include <vector>
#include <cstdint>
#include <cstdlib>
#include "esphome/components/remote_base/remote_base.h"

// Xiaomi Whale Spout bidet seat remote - 433 MHz 2-FSK packet builder.
// Protocol notes: docs/protocol.md
//
// Packet = 8 nibbles: 2 a | key (2 nibbles) | n4 n5 n6 | checksum
//   n4 = water temperature code, dry temperature code, 0, or the seat level depending on the key (mode below)
//   n5 = flow code, n6 = position code   (level 1/2/3 -> 1/3/5)
//   checksum = (sum of the first 7 nibbles) mod 16
// Timings (us): + = high tone (mark), - = low tone (space). Each press is sent twice, 120 ms apart.

// mode 0: n4 = water temperature code, 1: n4 = 0 (self clean, massage), 2: n4 = seat level 0..3,
// 3: n4 = dry temperature code. Keys: 0xD6 water temperature, 0x36 dry temperature (the remote's temperature
// buttons send one or the other depending on whether Dry is running).
inline std::vector<int32_t> bidet_packet(int key, int mode, int temp, int dry, int flow, int pos, int seat) {
  auto code = [](int level) { return 2 * level - 1; };
  uint8_t n[8] = {0x2, 0xA, (uint8_t) ((key >> 4) & 0xF), (uint8_t) (key & 0xF), 0,
                  (uint8_t) code(flow), (uint8_t) code(pos), 0};
  n[4] = mode == 0 ? code(temp) : mode == 2 ? seat : mode == 3 ? code(dry) : 0;
  int sum = 0;
  for (int i = 0; i < 7; i++) sum += n[i];
  n[7] = sum & 0xF;

  std::vector<int32_t> burst;
  burst.reserve(85);
  burst.push_back(240);   // short lead-in pulse (transmitter ramp-up on the real remote)
  burst.push_back(-564);
  for (int i = 0; i < 7; i++) {  // preamble
    burst.push_back(564);
    burst.push_back(-564);
  }
  burst.push_back(564);   // sync
  burst.push_back(-4524);
  for (int i = 0; i < 8; i++) {  // 32 data bits, MSB first
    for (int b = 3; b >= 0; b--) {
      burst.push_back(564);
      burst.push_back((n[i] >> b) & 1 ? -1692 : -564);
    }
  }
  burst.push_back(564);   // stop pulse
  burst.push_back(-19900);

  // two bursts, 120 ms start to start (83 ms on + 37 ms off): extend the first tail by ~37 ms
  std::vector<int32_t> out;
  // The CC1101 needs a few ms after cc1101.begin_tx (calibration + PLL settling) before it modulates
  // correctly, so start with 10 ms of low tone so the first pulses are not lost.
  out.push_back(-10000);
  out.insert(out.end(), burst.begin(), burst.end());
  out.back() = -(19900 + 37100);
  out.insert(out.end(), burst.begin(), burst.end());
  return out;
}

// ---- Receive side: decode the real remote's packets (heard through the CC1101 on GDO2) ----

// Latest valid packet heard; picked up by the interval in the YAML.
struct BidetRx {
  volatile bool pending = false;
  volatile uint32_t packet = 0;
};
inline BidetRx bidet_rx;

// Level code on the wire (1/3/5) -> level 1..3, or 0 when it is not a valid level code.
inline int bidet_level(int code) { return (code == 1 || code == 3 || code == 5) ? (code + 1) / 2 : 0; }

// Split a 32-bit packet into key / n4 / n5 / n6 and check the header (2a) and checksum.
inline bool bidet_decode(uint32_t p, int &key, int &n4, int &n5, int &n6) {
  int n[8];
  for (int i = 0; i < 8; i++) n[i] = (p >> (28 - 4 * i)) & 0xF;
  if (n[0] != 0x2 || n[1] != 0xA) return false;
  int sum = 0;
  for (int i = 0; i < 7; i++) sum += n[i];
  if ((sum & 0xF) != n[7]) return false;
  key = (n[2] << 4) | n[3];
  n4 = n[4];
  n5 = n[5];
  n6 = n[6];
  return true;
}

// Looks at every frame the remote_receiver sees. Polarity does not matter: after the long sync gap the
// data is 32 (pulse, gap) pairs, a gap of ~564 us = 0 and ~1692 us = 1.
class BidetRxDumper : public esphome::remote_base::RemoteReceiverDumperBase {
 public:
  bool dump(esphome::remote_base::RemoteReceiveData src) override {
    const auto &raw = src.get_raw_data();
    int n = (int) raw.size();
    for (int i = 0; i + 1 < n; i++) {
      int sync = std::abs(raw[i]);
      if (sync < 3400 || sync > 5800) continue;
      uint32_t p = 0;
      int bits = 0;
      for (int j = i + 1; j + 1 < n && bits < 32; j += 2) {
        int mark = std::abs(raw[j]), gap = std::abs(raw[j + 1]);
        if (mark < 300 || mark > 1000 || gap < 300 || gap > 2400) break;
        p = (p << 1) | (gap > 1128 ? 1 : 0);
        bits++;
      }
      if (bits == 32) {
        bidet_rx.packet = p;
        bidet_rx.pending = true;
        return false;
      }
    }
    return false;
  }
  bool is_secondary() override { return false; }
};
inline BidetRxDumper bidet_rx_dumper;
