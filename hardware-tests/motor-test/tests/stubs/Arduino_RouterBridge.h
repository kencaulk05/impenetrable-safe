#pragma once
#include "Arduino.h"
#include <map>
#include <string>
#include <vector>
struct Notification { std::string name; std::vector<double> args; uint32_t at_us; };
extern std::vector<Notification> notifications;
class BridgeClass {
 public:
  std::map<std::string, int (*)(int, int)> fns;            // the functions Python can call, by name
  void begin() {}
  void provide_safe(const char *name, int (*f)(int, int)) { fns[name] = f; }
  template <typename... A> void notify(const char *name, A... a) {
    Notification n; n.name = name; (n.args.push_back((double)a), ...); n.at_us = sim_us; notifications.push_back(n);
  }
};
extern BridgeClass Bridge;
