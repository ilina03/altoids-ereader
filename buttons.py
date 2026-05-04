# buttons.py — Button polling with 50 ms debounce
# Pins: GP10=UP, GP11=DOWN, GP12=BACK, GP13=SELECT
# All buttons: pull-up config, LOW = pressed.

import time
from machine import Pin

# Button identifiers — used throughout the codebase
BTN_UP     = "UP"
BTN_DOWN   = "DOWN"
BTN_BACK   = "BACK"
BTN_SELECT = "SELECT"

# Debounce time in milliseconds
DEBOUNCE_MS = 50


class Buttons:
    """
    Polls four tactile buttons with simple time-based debounce.
    No interrupts — call poll() in the main loop.
    """

    def __init__(self):
        self._pins = {
            BTN_UP:     Pin(10, Pin.IN, Pin.PULL_UP),
            BTN_DOWN:   Pin(11, Pin.IN, Pin.PULL_UP),
            BTN_BACK:   Pin(12, Pin.IN, Pin.PULL_UP),
            BTN_SELECT: Pin(13, Pin.IN, Pin.PULL_UP),
        }
        # Track last confirmed state (True = pressed) and timestamp
        self._last_state = {k: False for k in self._pins}
        self._last_time  = {k: 0     for k in self._pins}

    def _raw_pressed(self, name):
        """Returns True if the physical pin is LOW (button held down)."""
        return self._pins[name].value() == 0

    def poll(self):
        """
        Return a list of button names that have just been newly pressed
        (rising edge after debounce).  Call this once per main-loop tick.
        """
        now = time.ticks_ms()
        fired = []
        for name in self._pins:
            raw = self._raw_pressed(name)
            was = self._last_state[name]

            if raw and not was:
                # Potential press — check debounce window
                if time.ticks_diff(now, self._last_time[name]) >= DEBOUNCE_MS:
                    self._last_state[name] = True
                    self._last_time[name]  = now
                    fired.append(name)
            elif not raw and was:
                # Button released
                self._last_state[name] = False
                self._last_time[name]  = now

        return fired

    def wait_for_press(self, timeout_ms=0):
        """
        Blocking wait for any button press.
        Returns the button name, or None if timeout (0 = wait forever).
        """
        start = time.ticks_ms()
        while True:
            events = self.poll()
            if events:
                return events[0]
            if timeout_ms and time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
                return None
            time.sleep_ms(10)

    def any_pressed(self):
        """Return True if any button is currently held down (raw, no debounce)."""
        return any(self._raw_pressed(n) for n in self._pins)
