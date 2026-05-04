# ui.py — Screen rendering for all UI states.
#
# All functions accept an EPaper instance and draw into its framebuffer,
# then call epd.show() to push to the display.
#
# Display dimensions (portrait, after 90° rotation):
#   Width  = 122 px
#   Height = 250 px
#
# Colour convention: 0 = black, 1 = white

import framebuf
import sdcard as sd
from epaper import DISPLAY_W, DISPLAY_H
from fonts import (
    draw_text, draw_text_centered, draw_text_right,
    char_width, char_height,
    chars_per_line, lines_per_page,
    FONT_SMALL, FONT_MEDIUM, FONT_LARGE,
)

STATUS_BAR_H = 10
MARGIN       = 2
SELECTOR     = "\x10"   # ASCII DLE ► arrow glyph (closest in 8×8 font)

# ── Battery icon ──────────────────────────────────────────────────────────────

def _draw_battery(epd, x, y, percent):
    """Draw a tiny 10×6 battery icon at (x, y) with fill level."""
    # Outline
    epd.rect(x, y, 9, 6, 0)
    # Nub
    epd.fill_rect(x + 9, y + 2, 2, 2, 0)
    # Fill
    fill_w = max(0, min(7, int(7 * percent / 100)))
    if fill_w > 0:
        epd.fill_rect(x + 1, y + 1, fill_w, 4, 0)


# ── Status bar ────────────────────────────────────────────────────────────────

def _draw_status_bar(epd, title, page_num, total_pages, battery_pct):
    """
    Draw the bottom status bar (10px tall).
    Layout: [title centered] [pg X/Y] [battery icon far right]
    """
    y = DISPLAY_H - STATUS_BAR_H
    # Separator line
    epd.hline(0, y, DISPLAY_W, 0)

    text_y = y + 1  # 1px padding

    # Battery icon (far right, 12px wide)
    bat_x = DISPLAY_W - 13
    _draw_battery(epd, bat_x, text_y + 1, battery_pct)

    # Page number (right of title, left of battery)
    pg_str = "{}/{}".format(page_num, total_pages)
    # Use tiny framebuf font (8px) for status bar — 1× scale
    cw = 8  # built-in font 8×8
    pg_x = bat_x - len(pg_str) * cw - 2
    epd.text(pg_str, pg_x, text_y, 0)

    # Title (centered in remaining space, truncated)
    max_title_chars = pg_x // cw - 1
    t = title
    if len(t) > max_title_chars:
        t = t[:max_title_chars - 1] + "~"
    title_x = max(0, (pg_x - len(t) * cw) // 2)
    epd.text(t, title_x, text_y, 0)


# ── Reading view ──────────────────────────────────────────────────────────────

def draw_reading(epd, reader, battery_pct):
    """
    Render the current page of the book.
    reader: BookReader instance (page lines already loaded via get_page_lines()).
    """
    epd.clear(1)   # white background

    font = reader.font_size
    cw   = char_width(font)
    ch   = char_height(font)

    lines = reader.get_page_lines()

    y = MARGIN
    for line in lines:
        if y + ch > DISPLAY_H - STATUS_BAR_H - MARGIN:
            break
        draw_text(epd, line, MARGIN, y, font, color=0)
        y += ch

    _draw_status_bar(
        epd,
        reader.title,
        reader.current_page_num(),
        reader.total_pages(),
        battery_pct,
    )
    epd.show()


# ── Menu screen ───────────────────────────────────────────────────────────────

_MENU_EXTRA = ["NEXT PAGE", "FONT SIZE"]
_MENU_EXTRA_NEXT = 0
_MENU_EXTRA_FONT = 1


def draw_menu(epd, books, selected_idx, scroll_offset):
    """
    Render the scrollable book list + NEXT PAGE / FONT SIZE options.

    books        : list of book name strings
    selected_idx : index in (books + _MENU_EXTRA) that is currently selected
    scroll_offset: how many items are scrolled off the top
    """
    epd.clear(1)

    # Header
    draw_text_centered(epd, "MENU", 2, FONT_MEDIUM, DISPLAY_W, color=0)
    epd.hline(0, 2 + char_height(FONT_MEDIUM) + 1, DISPLAY_W, 0)

    # Determine how many rows we can show
    item_h   = char_height(FONT_SMALL)
    header_h = 2 + char_height(FONT_MEDIUM) + 3
    max_rows = (DISPLAY_H - header_h) // item_h

    all_items = books + _MENU_EXTRA

    y = header_h
    for i in range(scroll_offset, min(scroll_offset + max_rows, len(all_items))):
        item   = all_items[i]
        is_sel = (i == selected_idx)
        arrow  = "> " if is_sel else "  "
        label  = (arrow + item)[:chars_per_line(DISPLAY_W, FONT_SMALL, MARGIN)]
        if is_sel:
            # Highlight selected row
            epd.fill_rect(0, y, DISPLAY_W, item_h, 0)
            draw_text(epd, label, MARGIN, y, FONT_SMALL, color=1)
        else:
            draw_text(epd, label, MARGIN, y, FONT_SMALL, color=0)
        y += item_h

    epd.show()


def menu_items_per_screen(books):
    item_h   = char_height(FONT_SMALL)
    header_h = 2 + char_height(FONT_MEDIUM) + 3
    return (DISPLAY_H - header_h) // item_h


# ── Book start screen ─────────────────────────────────────────────────────────

def draw_book_start(epd, book_name, has_bookmark, bookmark_ch, bookmark_pg,
                    selected_option, bmp_data=None):
    """
    Title page.
    selected_option: 0 = Start from beginning, 1 = Continue
    bmp_data: result of sdcard.load_bmp_1bit() or None
    """
    epd.clear(1)

    y = MARGIN

    # Cover art or border
    if bmp_data:
        bw, bh, pixels = bmp_data
        # Centre the 80×80 image
        img_x = (DISPLAY_W - bw) // 2
        img_y = y
        # Blit pixel-by-pixel (BMP uses 0=black in our loaded format)
        stride = (bw + 7) // 8
        for row in range(bh):
            for col in range(bw):
                byte  = pixels[row * stride + col // 8]
                white = bool(byte & (0x80 >> (col % 8)))
                epd.pixel(img_x + col, img_y + row, 1 if white else 0)
        y += bh + 4
    else:
        # Thin border rectangle in top half
        epd.rect(MARGIN, y, DISPLAY_W - MARGIN * 2, 90, 0)
        y += 4

    # Title centred
    max_cpl = chars_per_line(DISPLAY_W, FONT_SMALL, MARGIN)
    title   = book_name
    if len(title) > max_cpl:
        title = title[:max_cpl - 1] + "~"
    draw_text_centered(epd, title, y, FONT_SMALL, DISPLAY_W, color=0)
    y += char_height(FONT_SMALL) + 2

    # Separator
    epd.hline(MARGIN, y, DISPLAY_W - MARGIN * 2, 0)
    y += 4

    # Options
    opts = ["Start from beginning"]
    if has_bookmark:
        opts.append("Continue (Ch.{} pg.{})".format(bookmark_ch, bookmark_pg))

    for i, opt in enumerate(opts):
        arrow = "> " if i == selected_option else "  "
        label = (arrow + opt)[:max_cpl]
        if i == selected_option:
            epd.fill_rect(0, y, DISPLAY_W, char_height(FONT_SMALL), 0)
            draw_text(epd, label, MARGIN, y, FONT_SMALL, color=1)
        else:
            draw_text(epd, label, MARGIN, y, FONT_SMALL, color=0)
        y += char_height(FONT_SMALL) + 2

    epd.show()


# ── Font size screen ──────────────────────────────────────────────────────────

_FONT_OPTIONS = [
    (FONT_SMALL,  "Small  Aa"),
    (FONT_MEDIUM, "Medium Aa"),
    (FONT_LARGE,  "Large  Aa"),
]


def draw_font_size(epd, current_font, selected_idx):
    """
    Font size selection screen.
    current_font: the currently active font (not necessarily the highlighted one)
    selected_idx: which item the cursor is on (0=small, 1=medium, 2=large)
    """
    epd.clear(1)

    y = MARGIN
    draw_text_centered(epd, "FONT SIZE", y, FONT_MEDIUM, DISPLAY_W, color=0)
    y += char_height(FONT_MEDIUM) + 4
    epd.hline(0, y, DISPLAY_W, 0)
    y += 6

    for i, (fsize, label) in enumerate(_FONT_OPTIONS):
        arrow = "> " if i == selected_idx else "  "
        text  = arrow + label
        if i == selected_idx:
            epd.fill_rect(0, y, DISPLAY_W, char_height(FONT_SMALL), 0)
            draw_text(epd, text, MARGIN, y, FONT_SMALL, color=1)
        else:
            draw_text(epd, text, MARGIN, y, FONT_SMALL, color=0)
        y += char_height(FONT_SMALL) + 8   # extra spacing to visually show size diff

    epd.show()


def font_size_from_index(idx):
    return _FONT_OPTIONS[idx][0]


def font_index_from_size(size):
    for i, (s, _) in enumerate(_FONT_OPTIONS):
        if s == size:
            return i
    return 1  # default medium


# ── Power off screen ──────────────────────────────────────────────────────────

def draw_power_off(epd, selected_yes):
    """
    Power off confirmation.
    selected_yes: True → cursor on YES, False → cursor on NO
    """
    epd.clear(1)

    y = DISPLAY_H // 2 - 30
    draw_text_centered(epd, "POWER OFF", y, FONT_MEDIUM, DISPLAY_W, color=0)
    y += char_height(FONT_MEDIUM) + 10
    epd.hline(MARGIN, y, DISPLAY_W - MARGIN * 2, 0)
    y += 8

    for i, label in enumerate(["YES", "NO"]):
        is_sel = (i == 0 and selected_yes) or (i == 1 and not selected_yes)
        arrow  = "> " if is_sel else "  "
        text   = arrow + label
        if is_sel:
            epd.fill_rect(0, y, DISPLAY_W, char_height(FONT_MEDIUM), 0)
            draw_text_centered(epd, text, y, FONT_MEDIUM, DISPLAY_W, color=1)
        else:
            draw_text_centered(epd, text, y, FONT_MEDIUM, DISPLAY_W, color=0)
        y += char_height(FONT_MEDIUM) + 6

    epd.show()


# ── Error / splash screens ────────────────────────────────────────────────────

def draw_splash(epd, message="Loading..."):
    """Simple centered message screen — used during boot."""
    epd.clear(1)
    draw_text_centered(epd, message, DISPLAY_H // 2 - 4, FONT_SMALL, DISPLAY_W)
    epd.show()


def draw_error(epd, message):
    """Display an error message."""
    epd.clear(1)
    draw_text_centered(epd, "ERROR", 10, FONT_MEDIUM, DISPLAY_W, color=0)
    epd.hline(0, 10 + char_height(FONT_MEDIUM) + 2, DISPLAY_W, 0)
    # Wrap message
    cpl = chars_per_line(DISPLAY_W, FONT_SMALL, MARGIN)
    y   = 30
    while message and y < DISPLAY_H - 10:
        draw_text(epd, message[:cpl], MARGIN, y, FONT_SMALL, color=0)
        message = message[cpl:]
        y += char_height(FONT_SMALL) + 2
    epd.show()
