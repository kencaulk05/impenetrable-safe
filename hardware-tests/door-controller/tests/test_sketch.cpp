#include "stubs/Arduino.h"
#include "stubs/Arduino_RouterBridge.h"
#include "stubs/Arduino_LED_Matrix.h"
uint32_t sim_us = 0; std::vector<Notification> notifications; BridgeClass Bridge;
#include "../sketch/sketch.ino"
#include <cmath>
#include <cstdlib>
static int failures_seen = 0;
#define CHECK(cond, ...) do { bool c_ = (cond); printf("  %-4s ", c_ ? "ok" : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!c_) failures_seen++; } while (0)
static int true_mm = 96;
static void reset_world() {
  world = World(); matrix = Arduino_LED_Matrix(); sim_us = 0; notifications.clear(); Bridge = BridgeClass(); memset(frame, 0, sizeof(frame));
  for (int i = 0; i < 5; i++) readings[i] = -1;
  next_reading = 0; last_sample = 0; true_mm = 96; icon = 0;
  motor_pwm = 150; ramp_ms = 250; last_duty = -1; motor_started = 0; motor_dir = 0; motor_until = 0;
  announce_start = announce_stop = false; announce_dir = announce_ms = 0;
  world.distance_mm = [](int) { return true_mm; };
}
static void run(double seconds) { uint32_t end = sim_us + (uint32_t)(seconds * 1e6); while (sim_us < end) loop(); }
static std::vector<Notification> msgs(const char *name) { std::vector<Notification> v; for (auto &n : notifications) if (n.name == name) v.push_back(n); return v; }
static int lit() { int n = 0; for (int i = 0; i < 104; i++) n += matrix.last[i] > 0; return n; }
static void no_ramp() { Bridge.fns["motor_speed"](150, 0); }

int main() {
  printf("1. start-up\n");
  reset_world(); setup();
  CHECK(world.modes[7] == OUTPUT && world.modes[8] == INPUT && world.modes[5] == OUTPUT && world.modes[6] == OUTPUT, "D7 (trig) and D5, D6 (motor) are outputs, D8 (echo) is an input");
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0 && world.level[7] == false, "the motor is off and trig is low at start");
  CHECK(matrix.begun && matrix.bits == 8 && lit() == 0, "the matrix started and is dark (%d LEDs lit)", lit());
  CHECK(Bridge.fns.size() == 3 && Bridge.fns.count("motor_run") && Bridge.fns.count("motor_speed") && Bridge.fns.count("led"), "Python can call motor_run, motor_speed and led (%zu functions)", Bridge.fns.size());

  printf("2. the distance\n");
  reset_world(); setup(); run(1.0); auto d = msgs("distance");
  CHECK(d.size() >= 14 && d.size() <= 18 && d[0].args.size() == 2, "%zu distance messages in 1 simulated second, each with two numbers (filtered and raw)", d.size());
  CHECK(fabs(d.back().args[0] - 96) <= 1 && fabs(d.back().args[1] - 96) <= 1, "a door at 96 mm reads %.0f (filtered) and %.0f (raw)", d.back().args[0], d.back().args[1]);
  CHECK(d[0].args[0] == -1 && d[1].args[0] == -1 && fabs(d[2].args[0] - 96) <= 1 && fabs(d[0].args[1] - 96) <= 1, "the filtered value is -1 until 3 readings are in, then 96; the raw one is there from the first");
  true_mm = 123; run(0.6); CHECK(fabs(msgs("distance").back().args[0] - 123) <= 1, "pushed open to 123 mm the filtered distance follows within 0.6 s: %.0f", msgs("distance").back().args[0]);
  true_mm = 4300; run(0.6); CHECK(msgs("distance").back().args[0] == -1, "beyond 4 m (the door open, nothing in view) the filter gives -1");
  reset_world(); world.distance_mm = [](int k) { return k == 25 ? 400 : 96; }; setup(); run(3.0); d = msgs("distance");
  double worst = 0, spike = 0; for (size_t i = 6; i < d.size(); i++) worst = fmax(worst, fabs(d[i].args[0] - 96)); for (auto &m : d) spike = fmax(spike, m.args[1]);
  CHECK(spike >= 390 && worst <= 1, "one wild reading (%.0f mm raw) does not move the filtered distance (largest error %.0f mm)", spike, worst);
  reset_world(); true_mm = -1; setup(); run(0.6); d = msgs("distance");
  CHECK(d.back().args[0] == -1 && d.back().args[1] == -1 && d.size() >= 8, "no echo: both -1, still %zu messages, and the loop does not hang", d.size());

  printf("3. the motor\n");
  reset_world(); setup(); no_ramp(); int accepted = Bridge.fns["motor_run"](1, 500);
  CHECK(accepted == 500 && world.pwm[5] == 150 && world.pwm[6] == 0, "motor_run(+1, 500): D5 at %d, D6 at %d", world.pwm[5], world.pwm[6]);
  CHECK(msgs("motor").empty(), "the function Python called sends no message itself: the loop does");
  run(0.01); auto m = msgs("motor"); CHECK(m.size() == 1 && m[0].args[0] == 1 && m[0].args[1] == 500, "a moment later Python is told: motor +1 for 500 ms");
  run(0.6); m = msgs("motor"); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0 && m.size() == 2 && m[1].args[0] == 0, "the sketch stops it by itself after 500 ms, and says so");
  Bridge.fns["motor_run"](-1, 300); CHECK(world.pwm[5] == 0 && world.pwm[6] == 150, "motor_run(-1, 300) drives the other pin");
  run(0.4); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "and stops after 300 ms");
  Bridge.fns["motor_run"](1, 1000); run(0.2); Bridge.fns["motor_run"](-1, 200); CHECK(world.pwm[5] == 0 && world.pwm[6] == 150, "a new command while running swaps the direction at once (the old pin off first)");
  run(0.3); CHECK(world.pwm[6] == 0, "and it ended on the NEW timer");
  uint32_t t0 = sim_us; accepted = Bridge.fns["motor_run"](1, 100000); run(3.3); m = msgs("motor");
  double ran = (m.back().at_us - t0) / 1e6; CHECK(accepted == 3000 && world.pwm[5] == 0 && ran > 2.99 && ran < 3.1, "a request for 100000 ms is cut to %d ms and really stops after %.2f s", accepted, ran);
  Bridge.fns["motor_run"](1, 2000); run(0.1); Bridge.fns["motor_run"](0, 0); run(0.01);
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0 && msgs("motor").back().args[0] == 0, "motor_run(0, 0) stops it at once and the stop is reported");
  size_t n = msgs("motor").size(); Bridge.fns["motor_run"](0, 0); run(0.01); CHECK(msgs("motor").size() == n, "stopping a stopped motor sends nothing");
  reset_world(); setup(); no_ramp(); Bridge.fns["motor_run"](1, 2000); Bridge.fns["motor_run"](0, 0); run(0.02); m = msgs("motor");
  CHECK(m.size() == 2 && m[0].args[0] == 1 && m[1].args[0] == 0, "a start and a STOP in the same instant send both messages, the start first");
  CHECK(Bridge.fns["motor_speed"](10, 0) == 60 && Bridge.fns["motor_speed"](999, 0) == 255 && Bridge.fns["motor_speed"](200, 0) == 200, "speed 10 becomes 60, 999 becomes 255");

  printf("4. the soft start\n");
  reset_world(); setup(); Bridge.fns["motor_speed"](200, 300); Bridge.fns["motor_run"](1, 1000);
  CHECK(world.pwm[5] == 60, "the motor begins at the lowest speed (%d), not at full", world.pwm[5]);
  int prev = world.pwm[5], peak = prev; bool mono = true; uint32_t ts = sim_us;
  while (sim_us < ts + 400000) { loop(); int v = world.pwm[5]; if (v < prev) mono = false; prev = v; if (v > peak) peak = v; }
  CHECK(world.pwm[5] == 200 && peak == 200 && mono, "after the ramp it holds the chosen speed (%d), never above it, and only ever climbed", world.pwm[5]);
  run(0.7); CHECK(world.pwm[5] == 0, "the move still ends after the full 1000 ms");
  Bridge.fns["motor_speed"](150, 5000); CHECK(ramp_ms == 1000, "a ramp longer than 1000 ms is cut to 1000");

  printf("5. the sensor and the motor at the same time\n");
  reset_world(); setup(); no_ramp(); true_mm = 96; run(0.5); size_t before = msgs("distance").size(); uint32_t tm = sim_us; Bridge.fns["motor_run"](-1, 600); run(0.9);
  auto dd = msgs("distance"); double gap = 0; for (size_t i = before; i < dd.size(); i++) gap = fmax(gap, fabs((dd[i].at_us - dd[i - 1].at_us) / 1000.0 - 60.0));
  CHECK(dd.size() - before >= 13 && gap < 8, "while the motor runs the distance still streams every 60 ms (largest deviation %.1f ms, %zu readings)", gap, dd.size() - before);
  m = msgs("motor"); ran = (m.back().at_us - tm) / 1e6;
  CHECK(world.pwm[6] == 0 && ran > 0.595 && ran < 0.65, "and the motor still ends on time: %.3f s for a 600 ms move", ran);
  reset_world(); true_mm = -1; setup(); no_ramp(); run(0.3); tm = sim_us; Bridge.fns["motor_run"](1, 600); run(0.9); m = msgs("motor"); ran = (m.back().at_us - tm) / 1e6;
  CHECK(ran > 0.595 && ran < 0.66, "even when no echo comes back and each reading waits 25 ms, the motor ends on time (%.3f s)", ran);

  printf("6. the LED matrix\n");
  reset_world(); setup();
  Bridge.fns["led"](1, 0); int l1 = lit(); Bridge.fns["led"](2, 0); int l2 = lit(); Bridge.fns["led"](3, 0); int l3 = lit(); Bridge.fns["led"](4, 0); int l4 = lit();
  CHECK(l1 == 51 && l2 == 50 && l3 == 6 && l4 == 16, "picture 1 (closed padlock) lights %d LEDs, 2 (open padlock) %d, 3 (!) %d, 4 (X) %d", l1, l2, l3, l4);
  Bridge.fns["led"](0, 0); CHECK(lit() == 0, "0 is dark"); Bridge.fns["led"](9, 0); CHECK(lit() == 0, "an unknown picture is dark");
  Bridge.fns["led"](1, 0); no_ramp(); Bridge.fns["motor_run"](1, 400); CHECK(lit() == 22 && matrix.last[3 * 13 + 8] > 0, "while the motor moves +1 the matrix shows a right arrow (%d LEDs), not the padlock", lit());
  Bridge.fns["motor_run"](-1, 400); CHECK(lit() == 22 && matrix.last[1 * 13 + 5] > 0, "and a left arrow when it moves -1");
  Bridge.fns["led"](2, 0); CHECK(lit() == 22, "a new picture asked for during a move waits: the arrow stays");
  run(0.5); CHECK(lit() == 50, "when the move ends the picture asked for comes back (open padlock, %d LEDs)", lit());
  Bridge.fns["motor_run"](1, 2000); run(0.1); Bridge.fns["motor_run"](0, 0); CHECK(lit() == 50, "and after a STOP too");

  printf("\n%s\n", failures_seen == 0 ? "ALL PASSED" : "SOME CHECKS FAILED");
  return failures_seen ? 1 : 0;
}
