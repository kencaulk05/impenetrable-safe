#include "stubs/Arduino.h"
#include "stubs/Arduino_RouterBridge.h"
#include "stubs/Arduino_LED_Matrix.h"
uint32_t sim_us = 0; std::vector<Notification> notifications; BridgeClass Bridge;
#include "../sketch/sketch.ino"
#include <cmath>
#include <cstdlib>
static int failures_seen = 0;
#define CHECK(cond, ...) do { bool c_ = (cond); printf("  %-4s ", c_ ? "ok" : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!c_) failures_seen++; } while (0)
static int true_mm = 120;
static void reset_world() {
  world = World(); matrix = Arduino_LED_Matrix(); sim_us = 0; notifications.clear(); Bridge = BridgeClass();
  for (int i = 0; i < 5; i++) readings[i] = -1;
  next_reading = 0; last_sample = 0; memset(frame, 0, sizeof(frame)); true_mm = 120;
  world.distance_mm = [](int) { return true_mm; };
}
static void run(double seconds) { uint32_t end = sim_us + (uint32_t)(seconds * 1e6); while (sim_us < end) loop(); }
static int lit() { int n = 0; for (int i = 0; i < 104; i++) n += matrix.last[i] > 0; return n; }

int main() {
  printf("1. start-up\n");
  reset_world(); setup();
  CHECK(world.modes[7] == OUTPUT && world.modes[8] == INPUT && world.level[7] == false, "D7 is an output (trig, low), D8 an input (echo)");
  CHECK(matrix.begun && matrix.bits == 8 && lit() == 0, "the matrix started and is dark (%d LEDs lit)", lit());
  CHECK(Bridge.fns.size() == 1 && Bridge.fns.count("led"), "Python can call one function: led (%zu registered)", Bridge.fns.size());

  printf("2. the distance\n");
  reset_world(); setup(); run(1.0);
  auto &n = notifications;
  CHECK(n.size() >= 14 && n.size() <= 18, "%zu distance messages in 1 simulated second (about 16 expected)", n.size());
  CHECK(n[0].name == "distance" && n[0].args.size() == 2, "each message is 'distance' with two numbers: filtered and raw");
  CHECK(fabs(n.back().args[0] - 120) <= 1 && fabs(n.back().args[1] - 120) <= 1, "a wall at 120 mm reads %.0f (filtered) and %.0f (raw)", n.back().args[0], n.back().args[1]);
  double gap = 0; for (size_t i = 1; i < n.size(); i++) gap = fmax(gap, fabs((n[i].at_us - n[i - 1].at_us) / 1000.0 - 60.0));
  CHECK(gap < 5, "readings come every 60 ms (largest deviation %.1f ms)", gap);
  CHECK(n[0].args[0] == -1 && n[1].args[0] == -1 && fabs(n[2].args[0] - 120) <= 1, "the filtered value is -1 until 3 readings are in (%.0f, %.0f), then %.0f", n[0].args[0], n[1].args[0], n[2].args[0]);
  CHECK(fabs(n[0].args[1] - 120) <= 1, "but the raw value is there from the first reading (%.0f)", n[0].args[1]);
  true_mm = 80; run(0.6);
  CHECK(fabs(n.back().args[0] - 80) <= 1, "when the door moves to 80 mm the filtered distance follows within 0.6 s: %.0f", n.back().args[0]);
  true_mm = 4300; run(0.6);
  CHECK(n.back().args[0] == -1, "beyond 4 m the filter gives -1 (it reads %.0f raw)", n.back().args[1]);
  reset_world(); world.distance_mm = [](int k) { return k == 25 ? 400 : 120; }; setup(); run(3.0);
  double worst = 0, spike = 0; for (size_t i = 6; i < n.size(); i++) worst = fmax(worst, fabs(n[i].args[0] - 120)); for (auto &m : n) spike = fmax(spike, m.args[1]);
  CHECK(spike >= 390 && worst <= 1, "one wild reading (%.0f mm raw) does not move the filtered distance (largest error %.0f mm)", spike, worst);
  reset_world(); true_mm = -1; setup(); run(0.6);
  CHECK(n.back().args[0] == -1 && n.back().args[1] == -1 && n.size() >= 8, "no echo: filtered %.0f and raw %.0f (both -1), still %zu messages, and the loop does not hang", n.back().args[0], n.back().args[1], n.size());
  reset_world(); true_mm = 10; setup(); run(0.6);
  CHECK(n.back().args[0] == -1 && fabs(n.back().args[1] - 10) <= 1, "closer than 20 mm: the filter says -1, the raw value shows %.0f", n.back().args[1]);
  reset_world(); setup(); run(0.5); true_mm = -1; run(0.4); true_mm = 150; run(0.6);
  CHECK(fabs(n.back().args[0] - 150) <= 1, "after a gap with no echo, it recovers by itself: %.0f", n.back().args[0]);

  printf("3. the LED bar\n");
  reset_world(); setup();
  Bridge.fns["led"](5, 6); CHECK(lit() == 24, "mode 5, a bar 6 columns wide: %d LEDs (6 x 4)", lit());
  Bridge.fns["led"](5, 13); CHECK(lit() == 52, "13 columns: %d LEDs (13 x 4)", lit());
  Bridge.fns["led"](5, 99); CHECK(lit() == 52, "wider than 13 is cut to 13: %d LEDs", lit());
  Bridge.fns["led"](5, -4); CHECK(lit() == 0, "a negative width is empty");
  Bridge.fns["led"](5, 3); Bridge.fns["led"](0, 0); CHECK(lit() == 0, "mode 0 turns every LED off");
  Bridge.fns["led"](9, 5); CHECK(lit() == 0, "any other mode is off");
  Bridge.fns["led"](5, 1); bool rows_ok = true; for (int r = 0; r < 8; r++) for (int c = 0; c < 13; c++) { bool on = matrix.last[r * 13 + c] > 0; if (on != (c == 0 && r >= 2 && r < 6)) rows_ok = false; }
  CHECK(rows_ok, "a bar 1 wide is the left column, rows 2 to 5 (a bar in the middle of the matrix)");

  printf("\n%s\n", failures_seen == 0 ? "ALL PASSED" : "SOME CHECKS FAILED");
  return failures_seen ? 1 : 0;
}
