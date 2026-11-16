#include "stubs/Arduino.h"
#include "stubs/Arduino_RouterBridge.h"
#include "stubs/Arduino_LED_Matrix.h"
uint32_t sim_us = 0; std::vector<Notification> notifications; BridgeClass Bridge;
#include "../sketch/sketch.ino"
#include <cmath>
#include <cstdlib>
static int failures_seen = 0;
#define CHECK(cond, ...) do { bool c_ = (cond); printf("  %-4s ", c_ ? "ok" : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!c_) failures_seen++; } while (0)
static void reset_world() {
  world = World(); matrix = Arduino_LED_Matrix(); sim_us = 0; notifications.clear(); Bridge = BridgeClass(); memset(frame, 0, sizeof(frame));
  motor_pwm = 150; ramp_ms = 250; last_duty = -1; motor_started = 0; motor_dir = 0; motor_until = 0;
  announce_start = announce_stop = false; announce_dir = announce_ms = 0;
}
static void run(double seconds) { uint32_t end = sim_us + (uint32_t)(seconds * 1e6); while (sim_us < end) loop(); }
static std::vector<Notification> motor_msgs() { std::vector<Notification> v; for (auto &n : notifications) if (n.name == "motor") v.push_back(n); return v; }
static int lit() { int n = 0; for (int i = 0; i < 104; i++) n += matrix.last[i] > 0; return n; }
static void no_ramp() { Bridge.fns["motor_speed"](150, 0); }

int main() {
  printf("1. start-up: the motor is off, Python can call two functions\n");
  reset_world(); setup();
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "both motor pins are 0 at start (%d, %d)", world.pwm[5], world.pwm[6]);
  CHECK(world.modes[5] == OUTPUT && world.modes[6] == OUTPUT, "D5 and D6 are outputs");
  CHECK(matrix.begun && matrix.bits == 8 && lit() == 0, "the matrix started and is dark (%d LEDs lit)", lit());
  CHECK(Bridge.fns.size() == 2 && Bridge.fns.count("motor_run") && Bridge.fns.count("motor_speed"), "Python can call motor_run and motor_speed (%zu functions)", Bridge.fns.size());
  run(0.5); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0 && motor_msgs().empty(), "left alone, the motor stays off and nothing is sent");

  printf("2. direction, timeout and the 3-second cap\n");
  reset_world(); setup(); no_ramp(); int accepted = Bridge.fns["motor_run"](1, 500);
  CHECK(accepted == 500 && world.pwm[5] == 150 && world.pwm[6] == 0, "motor_run(+1, 500): pin D5 at %d, D6 at %d", world.pwm[5], world.pwm[6]);
  CHECK(motor_msgs().empty(), "the function Python called sends no message itself: the loop does (like the messages already proven on this board)");
  run(0.01); auto m = motor_msgs(); CHECK(m.size() == 1 && m[0].args[0] == 1 && m[0].args[1] == 500, "a moment later Python is told: motor +1 for 500 ms");
  run(0.3); CHECK(world.pwm[5] == 150, "still running after 0.3 s");
  run(0.3); m = motor_msgs();
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0 && m.size() == 2 && m[1].args[0] == 0 && m[1].args[1] == 0, "the sketch stops it by itself after 500 ms, and says so");
  Bridge.fns["motor_run"](-1, 300); CHECK(world.pwm[5] == 0 && world.pwm[6] == 150, "motor_run(-1, 300) drives the other pin: D5 %d, D6 %d", world.pwm[5], world.pwm[6]);
  run(0.4); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "and stops after 300 ms");
  Bridge.fns["motor_run"](1, 1000); run(0.2); Bridge.fns["motor_run"](-1, 200);
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 150, "a new command while running swaps the direction at once (the old pin is off first)");
  run(0.1); CHECK(world.pwm[6] == 150, "the new 200 ms timer started afresh (still running 0.1 s later)");
  run(0.25); CHECK(world.pwm[6] == 0, "and it ended on the NEW timer, not the old 1000 ms one");
  uint32_t t0 = sim_us; accepted = Bridge.fns["motor_run"](1, 100000); run(3.3); m = motor_msgs();
  CHECK(accepted == 3000 && world.pwm[5] == 0, "a request for 100000 ms is cut to %d ms", accepted);
  double ran = (m.back().at_us - t0) / 1e6; CHECK(ran > 2.99 && ran < 3.1, "and it really stopped after %.2f s", ran);
  Bridge.fns["motor_run"](1, 2000); run(0.1); Bridge.fns["motor_run"](0, 0);
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "motor_run(0, 0) stops it at once (the STOP button)");
  run(0.01); CHECK(motor_msgs().back().args[0] == 0, "and the stop is reported");
  size_t n = motor_msgs().size(); Bridge.fns["motor_run"](0, 0); run(0.01); CHECK(motor_msgs().size() == n, "stopping a motor that is already stopped sends nothing");
  Bridge.fns["motor_run"](1, 0); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "a move of 0 ms is a stop");
  Bridge.fns["motor_run"](-1, -50); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "a negative time is a stop");

  reset_world(); setup(); no_ramp(); Bridge.fns["motor_run"](1, 2000); Bridge.fns["motor_run"](0, 0); run(0.02); m = motor_msgs();
  CHECK(m.size() == 2 && m[0].args[0] == 1 && m[0].args[1] == 2000 && m[1].args[0] == 0, "a start and a STOP in the same instant send both messages, the start first (%zu messages)", m.size());
  reset_world(); setup(); no_ramp(); Bridge.fns["motor_run"](1, 2000); run(0.1); Bridge.fns["motor_run"](-1, 500); run(0.1); m = motor_msgs();
  CHECK(m.size() == 2 && m[0].args[0] == 1 && m[1].args[0] == -1 && m[1].args[1] == 500, "a new move replacing a running one announces just the new start (the old move gets no stop message)");

  printf("3. speed\n");
  reset_world(); setup();
  CHECK(Bridge.fns["motor_speed"](200, 0) == 200 && Bridge.fns["motor_speed"](10, 0) == 60 && Bridge.fns["motor_speed"](999, 0) == 255, "motor_speed: 200 stays 200, 10 becomes 60, 999 becomes 255");
  Bridge.fns["motor_speed"](200, 0); Bridge.fns["motor_run"](1, 100); CHECK(world.pwm[5] == 200, "and the new speed is used (D5 at %d)", world.pwm[5]);

  printf("4. the soft start (spares the 5 V rail when the motor shares it with the board)\n");
  reset_world(); setup(); CHECK(ramp_ms == 250, "the default soft start is %d ms", ramp_ms);
  Bridge.fns["motor_speed"](200, 300); Bridge.fns["motor_run"](1, 1000);
  CHECK(world.pwm[5] == 60 && world.pwm[6] == 0, "the motor begins at the lowest speed (D5 at %d), not at full", world.pwm[5]);
  int prev = world.pwm[5]; bool monotonic = true; int peak = prev; uint32_t t_start = sim_us;
  while (sim_us < t_start + 150000) { loop(); int v = world.pwm[5]; if (v < prev) monotonic = false; prev = v; if (v > peak) peak = v; }
  CHECK(world.pwm[5] >= 115 && world.pwm[5] <= 145, "half way through a 300 ms ramp it is half way up (%d, between 60 and 200)", world.pwm[5]);
  while (sim_us < t_start + 400000) { loop(); int v = world.pwm[5]; if (v < prev) monotonic = false; prev = v; if (v > peak) peak = v; }
  CHECK(world.pwm[5] == 200 && peak == 200 && monotonic, "after the ramp it holds the chosen speed (%d), never above it (peak %d), and only ever climbed", world.pwm[5], peak);
  run(0.7); CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "the move still ends after the full 1000 ms, ramp included");
  Bridge.fns["motor_speed"](200, 300); Bridge.fns["motor_run"](1, 100); run(0.2);
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 0, "a move shorter than the ramp (100 ms) just stops at 100 ms, at a low speed");
  Bridge.fns["motor_run"](1, 2000); run(0.2); Bridge.fns["motor_run"](-1, 2000);
  CHECK(world.pwm[5] == 0 && world.pwm[6] == 60, "reversing starts the soft start again, from the lowest speed (D6 at %d)", world.pwm[6]);
  Bridge.fns["motor_run"](0, 0); Bridge.fns["motor_speed"](150, 5000); CHECK(ramp_ms == 1000, "a ramp longer than 1000 ms is cut to %d ms", ramp_ms);
  Bridge.fns["motor_speed"](150, -3); CHECK(ramp_ms == 0, "a negative ramp is no ramp");

  printf("5. the arrow on the LED matrix\n");
  reset_world(); setup(); no_ramp();
  Bridge.fns["motor_run"](1, 400); int right_lit = lit(); bool right_side = matrix.last[3 * 13 + 8] > 0 && matrix.last[3 * 13 + 2] > 0;
  CHECK(right_lit == 22 && right_side, "moving +1 shows a right arrow (%d LEDs)", right_lit);
  Bridge.fns["motor_run"](-1, 400); int left_lit = lit();
  CHECK(left_lit == 22 && matrix.last[1 * 13 + 5] > 0 && matrix.last[1 * 13 + 7] == 0, "moving -1 shows a left arrow (%d LEDs, the head on the left)", left_lit);
  run(0.5); CHECK(lit() == 0, "when the move ends the matrix goes dark");
  Bridge.fns["motor_run"](1, 2000); run(0.1); Bridge.fns["motor_run"](0, 0); CHECK(lit() == 0, "and when it is stopped by hand");

  printf("\n%s\n", failures_seen == 0 ? "ALL PASSED" : "SOME CHECKS FAILED");
  return failures_seen ? 1 : 0;
}
