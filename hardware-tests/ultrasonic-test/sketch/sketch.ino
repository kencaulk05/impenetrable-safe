// Ultrasonic sensor test - UNO Q microcontroller side: ONLY the HC-SR04 ultrasonic sensor, and the LED matrix as a distance bar.
//
// The sketch STREAMS to Python (the direction already proven on this board):
//     Bridge.notify("distance", filtered_mm, raw_mm)     every 60 ms; filtered = the middle value of the last 5 readings, -1 if fewer than 3 are usable;
//                                                        raw = the last single reading, -1 if no echo came back
// Python can call (two integers; the second is ignored where it is not needed):
//     led(mode, arg)     mode 0 = every LED off, mode 5 = a bar arg columns wide (0 to 13); anything else = off
//
// WIRING (the UNO Q's digital pins are 3.3 V logic):
//     HC-SR04:   GND -> GND,  TRIG -> D7,  ECHO -> D8 (see the README: through a divider if the sensor runs from 5 V),
//                VCC -> 3V3 to try first (the classic HC-SR04 may need 5V)
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

const int      PIN_TRIG = 7, PIN_ECHO = 8;
const uint32_t ECHO_TIMEOUT_US = 25000;     // 25 ms is about 4.3 m
const uint32_t SAMPLE_MS = 60;              // the HC-SR04 needs about 60 ms between readings
const int      MIN_MM = 20, MAX_MM = 4000;  // the HC-SR04 reads 2 cm to 4 m; anything outside is ignored by the filter

Arduino_LED_Matrix matrix;
uint8_t  frame[104];                        // 13 columns x 8 rows
int      readings[5] = {-1, -1, -1, -1, -1};
uint8_t  next_reading = 0;
uint32_t last_sample = 0;

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

int set_led(int mode, int arg) {
  memset(frame, 0, sizeof(frame));
  if (mode == 5) {
    int w = arg < 0 ? 0 : (arg > 13 ? 13 : arg);
    for (int c = 0; c < w; c++) for (int r = 2; r < 6; r++) frame[r * 13 + c] = 255;
  }
  matrix.draw(frame);
  return mode;
}

void setup() {
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  matrix.begin();
  matrix.setGrayscaleBits(8);
  set_led(0, 0);
  Bridge.begin();
  Bridge.provide_safe("led", set_led);
}

void loop() {
  uint32_t now = millis();
  if (now - last_sample >= SAMPLE_MS) {                                       // one reading every 60 ms
    last_sample = now;
    int d = measure_mm();
    readings[next_reading] = d;
    next_reading = (next_reading + 1) % 5;
    Bridge.notify("distance", median_valid(), d);
  }
  delay(1);
}
