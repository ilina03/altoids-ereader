# main.py — Altoids Tin E-Reader
# Boot sequence, hardware init, and main event loop.
#
# State machine:
#   STATE_MENU       → scrollable book list
#   STATE_BOOK_START → title page / start or continue
#   STATE_READING    → reading view
#   STATE_FONT_SIZE  → font size picker
#   STATE_POWER_OFF  → power-off confirmation

import time
import machine
from machine import Pin, SPI, ADC

# ── Hardware setup ────────────────────────────────────────────────────────────

# SPI0 — shared by e-Paper and SD card
spi = SPI(
    0,
    baudrate=4_000_000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16),
)

# e-Paper control pins
from epaper import EPaper, DISPLAY_W, DISPLAY_H
epd_cs   = Pin(17, Pin.OUT, value=1)
epd_dc   = Pin(20, Pin.OUT, value=0)
epd_rst  = Pin(21, Pin.OUT, value=1)
epd_busy = Pin(22, Pin.IN)

epd = EPaper(spi, cs=epd_cs, dc=epd_dc, rst=epd_rst, busy=epd_busy)

# SD card chip-select (hold high until we mount)
sd_cs = Pin(15, Pin.OUT, value=1)

# Battery ADC — VSYS is on ADC3 (GP29 internal on Pico)
# Pico VSYS divides by 3 internally; full scale ≈ 4.2 V → 3 × 4.2 / 3.3 × 65535
_adc_vsys = ADC(3)

def read_battery_pct():
    """Return battery percentage 0–100 (rough estimate from VSYS voltage)."""
    raw   = _adc_vsys.read_u16()
    volts = raw * 3.3 * 3 / 65535   # VSYS = ADC reading × 3 (Pico voltage divider)
    # LiPo: ~3.0 V = 0%, ~4.2 V = 100%
    pct   = int((volts - 3.0) / (4.2 - 3.0) * 100)
    return max(0, min(100, pct))

# ── Import the rest of the firmware ──────────────────────────────────────────

import sdcard as sd
import bookmarks
from reader import BookReader
from buttons import Buttons, BTN_UP, BTN_DOWN, BTN_BACK, BTN_SELECT
from fonts import FONT_SMALL, FONT_MEDIUM, FONT_LARGE
import ui

# ── States ────────────────────────────────────────────────────────────────────

STATE_MENU       = "menu"
STATE_BOOK_START = "book_start"
STATE_READING    = "reading"
STATE_FONT_SIZE  = "font_size"
STATE_POWER_OFF  = "power_off"

# ── Globals ───────────────────────────────────────────────────────────────────

state         = STATE_MENU
current_font  = FONT_MEDIUM
reader        = BookReader()
buttons       = Buttons()

# Menu state
books         = []
menu_selected = 0
menu_scroll   = 0

# Book start state
selected_book      = None
book_start_option  = 0   # 0=start, 1=continue
bmp_cache          = None  # loaded cover BMP data

# Font size state
font_sel_idx  = 1   # 0=small, 1=medium, 2=large

# Power off state
power_off_yes = True

# ── Boot ──────────────────────────────────────────────────────────────────────

def boot():
    global books, current_font, state

    # Init display
    epd.init()
    ui.draw_splash(epd, "Booting...")

    # Mount SD card (display CS is already high)
    epd_cs.value(1)  # ensure display CS is released
    if not sd.mount(spi, sd_cs):
        ui.draw_error(epd, "SD card not found. Insert card & reboot.")
        time.sleep(5)
        machine.reset()

    books = sd.list_books()
    if not books:
        ui.draw_error(epd, "No books found on SD card.")
        time.sleep(5)
        machine.reset()

    state = STATE_MENU
    refresh_menu()


# ── Screen renderers / transitions ────────────────────────────────────────────

def refresh_menu():
    ui.draw_menu(epd, books, menu_selected, menu_scroll)


def enter_book_start(name):
    global selected_book, book_start_option, bmp_cache, state
    selected_book     = name
    book_start_option = 0
    bmp_cache         = None

    if sd.cover_exists(name):
        bmp_cache = sd.load_bmp_1bit(sd.cover_path(name))

    ch, pg = bookmarks.load(name)
    has_bm = ch is not None
    ui.draw_book_start(
        epd, name, has_bm, ch or 1, pg or 1,
        book_start_option, bmp_cache
    )
    state = STATE_BOOK_START


def enter_reading():
    global state
    reader.font_size = current_font
    ui.draw_reading(epd, reader, read_battery_pct())
    state = STATE_READING


def enter_font_size():
    global state, font_sel_idx
    font_sel_idx = ui.font_index_from_size(current_font)
    ui.draw_font_size(epd, current_font, font_sel_idx)
    state = STATE_FONT_SIZE


def enter_power_off():
    global state, power_off_yes
    power_off_yes = True
    ui.draw_power_off(epd, power_off_yes)
    state = STATE_POWER_OFF


def do_power_off():
    ui.draw_splash(epd, "Goodbye.")
    epd.sleep()
    time.sleep_ms(200)
    machine.deepsleep()   # wake requires RESET


# ── Input handlers ────────────────────────────────────────────────────────────

def handle_menu(btn):
    global menu_selected, menu_scroll, state
    total = len(books) + len(ui._MENU_EXTRA)
    ipp   = ui.menu_items_per_screen(books)

    if btn == BTN_UP:
        if menu_selected > 0:
            menu_selected -= 1
            if menu_selected < menu_scroll:
                menu_scroll = menu_selected
            refresh_menu()

    elif btn == BTN_DOWN:
        if menu_selected < total - 1:
            menu_selected += 1
            if menu_selected >= menu_scroll + ipp:
                menu_scroll = menu_selected - ipp + 1
            refresh_menu()

    elif btn == BTN_SELECT:
        if menu_selected < len(books):
            enter_book_start(books[menu_selected])
        elif menu_selected == len(books) + ui._MENU_EXTRA_NEXT:
            # NEXT PAGE — not applicable from menu; ignore or loop
            pass
        elif menu_selected == len(books) + ui._MENU_EXTRA_FONT:
            enter_font_size()

    elif btn == BTN_BACK:
        enter_power_off()


def handle_book_start(btn):
    global book_start_option, state, reader, current_font

    ch, pg   = bookmarks.load(selected_book)
    has_bm   = ch is not None

    max_opts = 2 if has_bm else 1

    if btn == BTN_UP:
        if book_start_option > 0:
            book_start_option -= 1
            ui.draw_book_start(epd, selected_book, has_bm, ch or 1, pg or 1,
                               book_start_option, bmp_cache)

    elif btn == BTN_DOWN:
        if book_start_option < max_opts - 1:
            book_start_option += 1
            ui.draw_book_start(epd, selected_book, has_bm, ch or 1, pg or 1,
                               book_start_option, bmp_cache)

    elif btn == BTN_SELECT:
        ok = reader.load(selected_book, current_font)
        if not ok:
            ui.draw_error(epd, "Cannot open book file.")
            time.sleep(3)
            state = STATE_MENU
            refresh_menu()
            return

        if book_start_option == 0 or not has_bm:
            # Start from beginning
            bookmarks.delete(selected_book)
            reader.seek_page(1)
        else:
            # Continue from bookmark
            reader.seek_chapter_page(ch, pg)

        enter_reading()

    elif btn == BTN_BACK:
        state = STATE_MENU
        refresh_menu()


def handle_reading(btn):
    global state

    if btn == BTN_UP:
        if reader.prev_page():
            bookmarks.save(selected_book, reader.current_chapter(),
                           reader.current_page_num())
            ui.draw_reading(epd, reader, read_battery_pct())

    elif btn == BTN_DOWN:
        if reader.next_page():
            bookmarks.save(selected_book, reader.current_chapter(),
                           reader.current_page_num())
            ui.draw_reading(epd, reader, read_battery_pct())

    elif btn == BTN_BACK:
        # Auto-save position when leaving reading view
        bookmarks.save(selected_book, reader.current_chapter(),
                       reader.current_page_num())
        state = STATE_MENU
        refresh_menu()

    # BTN_SELECT: no action in reading view


def handle_font_size(btn):
    global font_sel_idx, current_font, state

    if btn == BTN_UP:
        if font_sel_idx > 0:
            font_sel_idx -= 1
            ui.draw_font_size(epd, current_font, font_sel_idx)

    elif btn == BTN_DOWN:
        if font_sel_idx < 2:
            font_sel_idx += 1
            ui.draw_font_size(epd, current_font, font_sel_idx)

    elif btn == BTN_SELECT:
        new_font = ui.font_size_from_index(font_sel_idx)
        if new_font != current_font:
            current_font = new_font
            # Re-paginate if a book is active
            if selected_book and reader.book_name == selected_book:
                reader.load(selected_book, current_font)
        state = STATE_MENU
        refresh_menu()

    elif btn == BTN_BACK:
        # Cancel — keep old font
        state = STATE_MENU
        refresh_menu()


def handle_power_off(btn):
    global power_off_yes, state

    if btn == BTN_UP or btn == BTN_DOWN:
        power_off_yes = not power_off_yes
        ui.draw_power_off(epd, power_off_yes)

    elif btn == BTN_SELECT:
        if power_off_yes:
            do_power_off()
        else:
            state = STATE_MENU
            refresh_menu()

    elif btn == BTN_BACK:
        # BACK = cancel = NO
        state = STATE_MENU
        refresh_menu()


# ── Dispatch table ────────────────────────────────────────────────────────────

_HANDLERS = {
    STATE_MENU:       handle_menu,
    STATE_BOOK_START: handle_book_start,
    STATE_READING:    handle_reading,
    STATE_FONT_SIZE:  handle_font_size,
    STATE_POWER_OFF:  handle_power_off,
}

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    boot()

    while True:
        events = buttons.poll()
        for btn in events:
            handler = _HANDLERS.get(state)
            if handler:
                handler(btn)
        time.sleep_ms(10)


# Entry point
main()
