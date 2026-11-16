// Finger Count on the Board: the microcontroller has nothing to do in this app (the camera, the network and the web page all run on the Linux side).
// This empty sketch is here so that App Lab has a sketch to build and the Bridge starts; the door and the LED matrix come in a later app.
#include <Arduino_RouterBridge.h>

void setup() {
  Bridge.begin();
}

void loop() {
  delay(10);
}
