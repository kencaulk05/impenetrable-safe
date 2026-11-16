#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
extern uint32_t sim_us;                                   // the simulated clock, in microseconds
inline uint32_t micros() { return sim_us; }
inline uint32_t millis() { return sim_us / 1000; }
inline void delay(uint32_t ms) { sim_us += ms * 1000; }
inline void delayMicroseconds(uint32_t us) { sim_us += us; }
// A tiny simulated world around the sketch's pins: D2 the button, D7 trig, D8 echo, D5 and D6 the motor.
struct World {
  int pwm[40] = {0}; bool level[40] = {false}; int modes[40] = {0};
  std::function<int(int)> distance_mm = [](int) { return 120; };      // argument: how many trigger pulses so far; returns the distance in mm, or -1 for no echo
  std::function<bool(uint32_t)> button_down = [](uint32_t) { return false; };
  int trig_pulses = 0; uint32_t trig_high_at = 0, echo_start = 0, echo_end = 0;
};
inline World world;
inline void pinMode(int pin, int mode) { world.modes[pin] = mode; }
inline void digitalWrite(int pin, int v) {
  if (pin == 7) {                                          // the trigger pin: a pulse of at least 10 microseconds starts an echo
    if (v == HIGH) world.trig_high_at = sim_us;
    else if (world.level[7] && sim_us - world.trig_high_at >= 10) {
      int d = world.distance_mm(world.trig_pulses++);
      if (d > 0) { world.echo_start = sim_us + 150; world.echo_end = world.echo_start + (uint32_t)(d * 5.8 + 0.5); } else { world.echo_start = world.echo_end = 0; }
    }
  }
  world.level[pin] = v != 0; world.pwm[pin] = v ? 255 : 0;
}
inline int digitalRead(int pin) {
  sim_us += 3;                                             // reading a pin takes a little time
  if (pin == 8) return (world.echo_end && sim_us >= world.echo_start && sim_us < world.echo_end) ? HIGH : LOW;
  if (pin == 2) return world.button_down(sim_us) ? LOW : HIGH;   // the button pulls the pin to ground
  return world.level[pin] ? HIGH : LOW;
}
inline void analogWrite(int pin, int v) { world.pwm[pin] = v; world.level[pin] = v > 0; }
