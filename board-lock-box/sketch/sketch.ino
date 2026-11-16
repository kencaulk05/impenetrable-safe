// Finger lock box - UNO Q microcontroller side: the HC-SR04 ultrasonic sensor, the DC motor (Cytron Maker Drive) and the LED matrix, together.
//
// The sketch STREAMS to Python (the direction already proven on this board). Every message is sent from loop(), never from inside a function that Python called:
//     Bridge.notify("distance", filtered_mm, raw_mm)   every 60 ms; filtered = the middle value of the last 5 readings, -1 if fewer than 3 are usable; raw = the last reading, -1 if no echo
//     Bridge.notify("motor", dir, ms)                  when a move starts (dir +1 or -1, ms as accepted: never more than MAX_RUN_MS), and ("motor", 0, 0) when it stops
// Python can call (two integers each):
//     motor_run(dir, ms)           dir +1 = one way, -1 = the other; dir 0 or ms <= 0 = STOP. A move NEVER lasts longer than MAX_RUN_MS and the sketch ends it by itself, even if Python goes quiet.
//     motor_speed(pwm, ramp_ms)    pwm 0..255 is clamped to MIN_PWM..255; ramp_ms (0 to 1000, 0 = none) is the soft start: begins at MIN_PWM and climbs to pwm over that time.
//     pic_a(r01, r23), pic_b(r45, r67)   a PICTURE for the LED matrix: 8 rows of 13 bits (leftmost LED = the highest bit), two rows packed into each number (the first row in the upper 13 bits).
//                                  pic_a stores rows 0 to 3 and shows nothing yet; pic_b stores rows 4 to 7 and shows the whole picture, so a half-sent picture is never seen.
//                                  While the motor moves the matrix shows an arrow in its direction, and the picture comes back when the move ends.
//
// WIRING:  HC-SR04: GND -> GND, TRIG -> D7, ECHO -> D8, VCC -> 3V3 (this sensor works on 3.3 V; on 5 V the ECHO needs a divider).
//          Cytron Maker Drive: M1A -> D5, M1B -> D6 (both PWM pins), GND -> GND (shared); the motor on the motor-1 terminals; its power from the UNO Q's 5V pin (see the README).
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

const int      PIN_TRIG = 7, PIN_ECHO = 8, PIN_MOTOR_A = 5, PIN_MOTOR_B = 6;
const uint32_t ECHO_TIMEOUT_US = 25000;     // 25 ms is about 4.3 m
const uint32_t SAMPLE_MS = 60;              // the HC-SR04 needs about 60 ms between readings
const int      MIN_MM = 20, MAX_MM = 4000;  // anything outside is ignored by the filter
const int      MAX_RUN_MS = 3000;
const int      MIN_PWM = 60;                // below this the motor just hums

Arduino_LED_Matrix matrix;
uint8_t  frame[104];                        // 13 columns x 8 rows
int      readings[5] = {-1, -1, -1, -1, -1};
uint8_t  next_reading = 0;
uint32_t last_sample = 0;
int      motor_pwm = 150, ramp_ms = 250, motor_dir = 0, last_duty = -1;
uint32_t motor_until = 0, motor_started = 0;
bool     announce_start = false, announce_stop = false;      // set by the functions Python calls; loop() sends the messages
int      announce_dir = 0, announce_ms = 0;
int      pic_rows[8] = {0, 0, 0, 0, 0, 0, 0, 0};              // the picture Python asked for (13 bits per row)
bool     have_pic = false;

const char *const ROWS_RIGHT[8] = {".............", ".......#.....", "........#....", "..#########..", "..#########..", "........#....", ".......#.....", "............."};
const char *const ROWS_LEFT[8]  = {".............", ".....#.......", "....#........", "..#########..", "..#########..", "....#........", ".....#.......", "............."};

void draw_arrow(const char *const *rows) {
  memset(frame, 0, sizeof(frame));
  for (int r = 0; r < 8; r++) for (int c = 0; c < 13; c++) if (rows[r][c] == '#') frame[r * 13 + c] = 255;
  matrix.draw(frame);
}

void draw_picture() {
  memset(frame, 0, sizeof(frame));
  if (have_pic) for (int r = 0; r < 8; r++) for (int c = 0; c < 13; c++) if ((pic_rows[r] >> (12 - c)) & 1) frame[r * 13 + c] = 255;
  matrix.draw(frame);
}

void redraw() {                             // an arrow while the motor moves, otherwise the picture Python asked for
  if (motor_dir > 0) draw_arrow(ROWS_RIGHT);
  else if (motor_dir < 0) draw_arrow(ROWS_LEFT);
  else draw_picture();
}

int pic_a(int a, int b) {                   // rows 0 to 3: stored, not shown yet
  pic_rows[0] = (a >> 13) & 0x1FFF; pic_rows[1] = a & 0x1FFF;
  pic_rows[2] = (b >> 13) & 0x1FFF; pic_rows[3] = b & 0x1FFF;
  return 0;
}

int pic_b(int a, int b) {                   // rows 4 to 7: stored, and now the whole picture is shown
  pic_rows[4] = (a >> 13) & 0x1FFF; pic_rows[5] = a & 0x1FFF;
  pic_rows[6] = (b >> 13) & 0x1FFF; pic_rows[7] = b & 0x1FFF;
  have_pic = true;
  redraw();
  return 0;
}

int measure_mm() {                          // one reading in millimetres, or -1 if no echo came back
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(4);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  uint32_t t0 = micros();
  while (digitalRead(PIN_ECHO) == LOW) if (micros() - t0 > ECHO_TIMEOUT_US) return -1;
  uint32_t t1 = micros();
  while (digitalRead(PIN_ECHO) == HIGH) if (micros() - t1 > ECHO_TIMEOUT_US) return -1;
  uint32_t dt = micros() - t1;              // the echo lasts 58 microseconds for every centimetre of distance
  return (int)((dt * 10UL + 29UL) / 58UL);
}

int median_valid() {                        // the middle of the usable readings among the last 5, or -1 if fewer than 3 are usable
  int v[5], n = 0;
  for (int i = 0; i < 5; i++) if (readings[i] >= MIN_MM && readings[i] <= MAX_MM) v[n++] = readings[i];
  if (n < 3) return -1;
  for (int i = 1; i < n; i++) { int x = v[i], j = i - 1; while (j >= 0 && v[j] > x) { v[j + 1] = v[j]; j--; } v[j + 1] = x; }
  return v[n / 2];
}

void apply_motor(int dir, int duty) {       // the pin that must be off is switched off first
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
  redraw();
}

int motor_run(int dir, int ms) {
  if (dir == 0 || ms <= 0) { motor_stop(); return 0; }
  if (ms > MAX_RUN_MS) ms = MAX_RUN_MS;
  motor_dir = dir > 0 ? 1 : -1;
  motor_started = millis();
  motor_until = motor_started + (uint32_t)ms;
  apply_motor(motor_dir, ramp_ms > 0 ? MIN_PWM : motor_pwm);          // a soft start begins low and climbs (see loop)
  redraw();
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
  analogWrite(PIN_MOTOR_A, 0);              // the motor is OFF from the very first moment
  analogWrite(PIN_MOTOR_B, 0);
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  matrix.begin();
  matrix.setGrayscaleBits(8);
  redraw();
  Bridge.begin();
  Bridge.provide_safe("motor_run", motor_run);
  Bridge.provide_safe("motor_speed", motor_speed);
  Bridge.provide_safe("pic_a", pic_a);
  Bridge.provide_safe("pic_b", pic_b);
}

void loop() {
  uint32_t now = millis();
  if (motor_dir != 0 && (int32_t)(now - motor_until) >= 0) motor_stop();      // the sketch ends every move by itself
  if (motor_dir != 0 && ramp_ms > 0) {                                        // the soft start: climb from MIN_PWM to the chosen speed
    uint32_t el = now - motor_started;
    int duty = el >= (uint32_t)ramp_ms ? motor_pwm : MIN_PWM + (int)((long)(motor_pwm - MIN_PWM) * (long)el / ramp_ms);
    if (duty != last_duty) apply_motor(motor_dir, duty);
  }
  if (now - last_sample >= SAMPLE_MS) {                                       // one distance reading every 60 ms
    last_sample = now;
    int d = measure_mm();
    readings[next_reading] = d;
    next_reading = (next_reading + 1) % 5;
    Bridge.notify("distance", median_valid(), d);
  }
  if (announce_start) { announce_start = false; Bridge.notify("motor", announce_dir, announce_ms); }   // the start message first, then the stop message
  if (announce_stop) { announce_stop = false; Bridge.notify("motor", 0, 0); }
  delay(1);
}
