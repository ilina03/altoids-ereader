# epaper.py — Waveshare 2.13" e-Paper V4 Driver
# For Raspberry Pi Pico 2 W (RP2350) / MicroPython
# Display: 250×122px, SPI, rotated 90° in software → 122px wide × 250px tall (portrait)

import time
from machine import Pin, SPI
import framebuf

# ── Physical display dimensions ───────────────────────────────────────────────
EPD_WIDTH  = 122   # physical columns
EPD_HEIGHT = 250   # physical rows

# After 90° rotation in software:
#   DISPLAY_W = 122  (portrait width)
#   DISPLAY_H = 250  (portrait height)
DISPLAY_W = EPD_WIDTH
DISPLAY_H = EPD_HEIGHT

# ── Waveshare 2.13" V4 commands ───────────────────────────────────────────────
DRIVER_OUTPUT_CONTROL          = 0x01
BOOSTER_SOFT_START_CONTROL     = 0x0C
GATE_SCAN_START_POSITION       = 0x0F
DEEP_SLEEP_MODE                = 0x10
DATA_ENTRY_MODE_SETTING        = 0x11
SW_RESET                       = 0x12
TEMPERATURE_SENSOR_CONTROL     = 0x1A
MASTER_ACTIVATION              = 0x20
DISPLAY_UPDATE_CONTROL_1       = 0x21
DISPLAY_UPDATE_CONTROL_2       = 0x22
WRITE_RAM_BW                   = 0x24
WRITE_VCOM_REGISTER            = 0x2C
WRITE_LUT_REGISTER             = 0x32
SET_DUMMY_LINE_PERIOD          = 0x3A
SET_GATE_TIME                  = 0x3B
BORDER_WAVEFORM_CONTROL        = 0x3C
SET_RAM_X_ADDRESS_START_END    = 0x44
SET_RAM_Y_ADDRESS_START_END    = 0x45
SET_RAM_X_ADDRESS_COUNTER      = 0x4E
SET_RAM_Y_ADDRESS_COUNTER      = 0x4F
TERMINATE_FRAME_READ_WRITE     = 0xFF

# Full refresh LUT for V4
LUT_FULL_UPDATE = bytes([
    0x80, 0x60, 0x40, 0x00, 0x00, 0x00, 0x00,
    0x10, 0x60, 0x20, 0x00, 0x00, 0x00, 0x00,
    0x80, 0x60, 0x40, 0x00, 0x00, 0x00, 0x00,
    0x10, 0x60, 0x20, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x03, 0x03, 0x00, 0x00, 0x02,
    0x09, 0x09, 0x00, 0x00, 0x02,
    0x03, 0x03, 0x00, 0x00, 0x02,
    0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00,
    0x15, 0x41, 0xA8, 0x32, 0x30, 0x0A,
])


class EPaper:
    """
    Driver for Waveshare 2.13" e-Paper V4.
    Uses MicroPython framebuf for rendering; portrait orientation (122×250).

    Pixel convention: 0 = black, 1 = white  (framebuf MONO_HLSB)
    The display RAM convention is: bit=1 → white, bit=0 → black.
    """

    def __init__(self, spi, cs, dc, rst, busy):
        self.spi  = spi
        self.cs   = cs
        self.dc   = dc
        self.rst  = rst
        self.busy = busy

        # Buffer: MONO_HLSB, 1 bit per pixel, rows of (width) bits padded to bytes
        # Width=122 → 16 bytes per row (⌈122/8⌉=16, but Waveshare uses 16 too)
        self._buf_width  = DISPLAY_W          # 122
        self._buf_height = DISPLAY_H          # 250
        self._buf_stride = (DISPLAY_W + 7) // 8  # 16 bytes per row

        buf_size = self._buf_stride * self._buf_height   # 16 × 250 = 4000 bytes
        self._buf = bytearray(buf_size)
        self.fb   = framebuf.FrameBuffer(
            self._buf, DISPLAY_W, DISPLAY_H, framebuf.MONO_HLSB
        )

    # ── Low-level helpers ─────────────────────────────────────────────────────

    def _cs_low(self):
        self.cs.value(0)

    def _cs_high(self):
        self.cs.value(1)

    def _send_command(self, cmd):
        self.dc.value(0)
        self._cs_low()
        self.spi.write(bytes([cmd]))
        self._cs_high()

    def _send_data(self, data):
        self.dc.value(1)
        self._cs_low()
        if isinstance(data, int):
            self.spi.write(bytes([data]))
        else:
            self.spi.write(bytes(data))
        self._cs_high()

    def _wait_busy(self, timeout_ms=10000):
        """Block until BUSY pin goes LOW (display ready)."""
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while self.busy.value() == 1:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            time.sleep_ms(10)

    def _hw_reset(self):
        self.rst.value(1)
        time.sleep_ms(10)
        self.rst.value(0)
        time.sleep_ms(10)
        self.rst.value(1)
        time.sleep_ms(10)

    # ── Initialisation ────────────────────────────────────────────────────────

    def init(self):
        """Hardware init sequence for Waveshare 2.13" V4 full refresh."""
        self._hw_reset()
        self._wait_busy()

        self._send_command(SW_RESET)
        self._wait_busy()

        # Driver output: MUX=249 (0xF9), GD=0, SM=0, TB=0
        self._send_command(DRIVER_OUTPUT_CONTROL)
        self._send_data(0xF9)
        self._send_data(0x00)
        self._send_data(0x00)

        # Data entry mode: X-increment, Y-increment (AM=0)
        self._send_command(DATA_ENTRY_MODE_SETTING)
        self._send_data(0x03)

        # RAM X range: 0 → 15  (16 bytes × 8 = 128 ≥ 122)
        self._send_command(SET_RAM_X_ADDRESS_START_END)
        self._send_data(0x00)
        self._send_data(0x0F)

        # RAM Y range: 0 → 249
        self._send_command(SET_RAM_Y_ADDRESS_START_END)
        self._send_data(0x00)
        self._send_data(0x00)
        self._send_data(0xF9)
        self._send_data(0x00)

        # Border waveform: follow LUT
        self._send_command(BORDER_WAVEFORM_CONTROL)
        self._send_data(0x05)

        # Temperature sensor: internal
        self._send_command(TEMPERATURE_SENSOR_CONTROL)
        self._send_data(0x80)

        # Load LUT
        self._send_command(WRITE_LUT_REGISTER)
        self._send_data(LUT_FULL_UPDATE)

        self._set_ram_ptr(0, 0)
        self._wait_busy()

    def _set_ram_ptr(self, x, y):
        self._send_command(SET_RAM_X_ADDRESS_COUNTER)
        self._send_data(x & 0x0F)
        self._send_command(SET_RAM_Y_ADDRESS_COUNTER)
        self._send_data(y & 0xFF)
        self._send_data((y >> 8) & 0x01)

    # ── Drawing API ───────────────────────────────────────────────────────────

    def clear(self, color=1):
        """
        Fill framebuffer.
        color=1 → white (display default), color=0 → black.
        """
        self.fb.fill(color)

    def show(self):
        """
        Invert buffer bits (framebuf 0=black, display RAM 0=black — same),
        write to display RAM, trigger full refresh.

        framebuf MONO_HLSB: 0=black pixel, 1=white pixel
        Display RAM:        0=black,       1=white   → same convention ✓
        """
        self._set_ram_ptr(0, 0)
        self._send_command(WRITE_RAM_BW)
        self.dc.value(1)
        self._cs_low()
        self.spi.write(self._buf)
        self._cs_high()

        self._send_command(DISPLAY_UPDATE_CONTROL_2)
        self._send_data(0xF7)
        self._send_command(MASTER_ACTIVATION)
        self._wait_busy()

    def sleep(self):
        """Put display into deep sleep to save power."""
        self._send_command(DEEP_SLEEP_MODE)
        self._send_data(0x01)
        time.sleep_ms(100)

    # ── Convenience wrappers around framebuf ──────────────────────────────────

    def pixel(self, x, y, color):
        self.fb.pixel(x, y, color)

    def fill_rect(self, x, y, w, h, color):
        self.fb.fill_rect(x, y, w, h, color)

    def rect(self, x, y, w, h, color):
        self.fb.rect(x, y, w, h, color)

    def hline(self, x, y, w, color):
        self.fb.hline(x, y, w, color)

    def vline(self, x, y, h, color):
        self.fb.vline(x, y, h, color)

    def text(self, s, x, y, color=0):
        """Built-in 8×8 framebuf font. color=0=black on white background."""
        self.fb.text(s, x, y, color)

    def blit(self, fbuf, x, y, key=-1):
        self.fb.blit(fbuf, x, y, key)
