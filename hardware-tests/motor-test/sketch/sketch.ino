// Motor test - UNO Q microcontroller side: ONLY the DC motor (through the Cytron Maker Drive) and the LED matrix (an arrow while the motor runs).
//
// The sketch STREAMS to Python (the direction already proven on this board). The messages are sent from loop(), never from inside a function that Python called:
//     Bridge.notify("motor", dir, ms)     when a move starts (dir +1 or -1, ms as accepted: never more than MAX_RUN_MS), and ("motor", 0, 0) when it stops
// Python can call (two integers each):
//     motor_run(dir, ms)           dir +1 = one way, -1 = the other; dir 0 or ms <= 0 = STOP. A move NEVER lasts longer than MAX_RUN_MS, and the sketch ends it by itself
//                                  even if Python or the web page goes quiet.
//     motor_speed(pwm, ramp_ms)    pwm 0..255 is clamped to MIN_PWM..255; ramp_ms (0 to 1000, 0 = none) is the SOFT START: the motor begins at MIN_PWM and climbs to
//                                  pwm over that time, which spares the 5 V rail when it is shared with the board
//
// WIRING:  Cytron Maker Drive  M1A -> D5,  M1B -> D6 (both PWM pins),  GND -> GND (shared with the UNO Q);  the motor on the motor-1 terminals;
//          the Maker Drive's own power as described in the README (a capacitor across it if it comes from the UNO Q's 5V pin).
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

const int PIN_MOTOR_A = 5, PIN_MOTOR_B = 6;
const int MAX_RUN_MS = 3000;
const int MIN_PWM = 60;                      // below this the motor just hums

Arduino_LED_Matrix matrix;
uint8_t  frame[104];                         // 13 columns x 8 rows
int      motor_pwm = 150;                    // about 60 % to begin with
int      ramp_ms = 250;                      // the soft start
int      motor_dir = 0;
int      last_duty = -1;
uint32_t motor_until = 0, motor_started = 0;
bool     announce_start = false, announce_stop = false;      // set by the functions Python calls; loop() sends the messages
int      announce_dir = 0, announce_ms = 0;

const char *const ROWS_RIGHT[8] = {".............", ".......#.....", "........#....", "..#########..", "..#########..", "........#....", ".......#.....", "............."};
const char *const ROWS_LEFT[8]  = {".............", ".....#.......", "....#........", "..#########..", "..#########..", "....#........", ".....#.......", "............."};

void show_direction(int dir) {               // an arrow while the motor runs, dark when it is stopped
  memset(frame, 0, sizeof(frame));
  if (dir != 0) {
    const char *const *rows = dir > 0 ? ROWS_RIGHT : ROWS_LEFT;
    for (int r = 0; r < 8; r++) for (int c = 0; c < 13; c++) if (rows[r][c] == '#') frame[r * 13 + c] = 255;
  }
  matrix.draw(frame);
}

void apply_motor(int dir, int duty) {        // the pin that must be off is switched off first
  if (dir > 0) { analogWrite(PIN_MOTOR_B, 0); analogWrite(PIN_MOTOR_A, duty); }
  else         { analogWrite(PIN_MOTOR_A, 0); analogWrite(PIN_MOTOR_B, duty); }
  last_duty = duty;
}

void motor_stop() {
  analogWrite(PIN_MOTOR_A, 0);
  analogWrite(PIN_MOTOR_B, 0);
  last_duty = -1;
  if (motor_dir != 0) announce_stop = true;
  motor_dir = 0;
  show_direction(0);
}

int motor_run(int dir, int ms) {
  if (dir == 0 || ms <= 0) { motor_stop(); return 0; }
  if (ms > MAX_RUN_MS) ms = MAX_RUN_MS;
  motor_dir = dir > 0 ? 1 : -1;
  motor_started = millis();
  motor_until = motor_started + (uint32_t)ms;
  apply_motor(motor_dir, ramp_ms > 0 ? MIN_PWM : motor_pwm);          // a soft start begins low and climbs (see loop)
  show_direction(motor_dir);
  announce_start = true; announce_dir = motor_dir; announce_ms = ms;
  return ms;
}

int motor_speed(int pwm, int ramp) {
  if (pwm < MIN_PWM) pwm = MIN_PWM;
  if (pwm > 255) pwm = 255;
  motor_pwm = pwm;
  ramp_ms = ramp < 0 ? 0 : (ramp > 1000 ? 1000 : ramp);
  return motor_pwm;
}

void setup() {
  pinMode(PIN_MOTOR_A, OUTPUT);
  pinMode(PIN_MOTOR_B, OUTPUT);
  analogWrite(PIN_MOTOR_A, 0);               // the motor is OFF from the very first moment
  analogWrite(PIN_MOTOR_B, 0);
  matrix.begin();
  matrix.setGrayscaleBits(8);
  show_direction(0);
  Bridge.begin();
  Bridge.provide_safe("motor_run", motor_run);
  Bridge.provide_safe("motor_speed", motor_speed);
}

void loop() {
  uint32_t now = millis();
  if (motor_dir != 0 && (int32_t)(now - motor_until) >= 0) motor_stop();      // the sketch ends every move by itself
  if (motor_dir != 0 && ramp_ms > 0) {                                        // the soft start: climb from MIN_PWM to the chosen speed
    uint32_t el = now - motor_started;
    int duty = el >= (uint32_t)ramp_ms ? motor_pwm : MIN_PWM + (int)((long)(motor_pwm - MIN_PWM) * (long)el / ramp_ms);
    if (duty != last_duty) apply_motor(motor_dir, duty);
  }
  if (announce_start) { announce_start = false; Bridge.notify("motor", announce_dir, announce_ms); }   // the start message first, then the stop message
  if (announce_stop) { announce_stop = false; Bridge.notify("motor", 0, 0); }
  delay(1);
}
