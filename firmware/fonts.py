# fonts.py — Bitmap font descriptors for small / medium / large sizes.
#
# MicroPython's built-in framebuf.text() uses a hard-coded 8×8 font and
# does not support scaling.  This module provides scaled rendering on top
# of framebuf by drawing each source pixel as an N×N filled rectangle.
#
# Font sizes:
#   SMALL  — 1× scale → 8×8 pixels per character  (~15 chars/line, ~28 lines)
#   MEDIUM — 2× scale → 16×16 pixels per character (~7 chars/line, ~14 lines)
#   LARGE  — 3× scale → 24×24 pixels per character (~5 chars/line, ~9 lines)
#
# The underlying glyph data is MicroPython's built-in 8×8 font, rendered
# via framebuf.FrameBuffer.text().  We scale at draw time.
#
# Character coverage: ASCII 0x20–0x7E (standard printable chars).

import framebuf

# ── Font size constants ───────────────────────────────────────────────────────

FONT_SMALL  = "small"
FONT_MEDIUM = "medium"
FONT_LARGE  = "large"

FONT_SIZES = [FONT_SMALL, FONT_MEDIUM, FONT_LARGE]

# Scale factor for each size
_SCALE = {
    FONT_SMALL:  1,
    FONT_MEDIUM: 2,
    FONT_LARGE:  3,
}

# Glyph source size (MicroPython built-in font)
_SRC_W = 8
_SRC_H = 8


def char_width(font_size):
    return _SRC_W * _SCALE[font_size]


def char_height(font_size):
    return _SRC_H * _SCALE[font_size]


def chars_per_line(display_width, font_size, margin=2):
    """How many characters fit per line given display width and side margins."""
    usable = display_width - margin * 2
    return max(1, usable // char_width(font_size))


def lines_per_page(display_height, font_size, status_bar_h=10, margin=2):
    """How many text lines fit in the display (excluding status bar)."""
    usable = display_height - status_bar_h - margin * 2
    return max(1, usable // char_height(font_size))


# ── Glyph extraction helper ───────────────────────────────────────────────────

# Tiny 1-bit scratch buffer used to extract a single 8×8 glyph.
_glyph_buf = bytearray(8)  # 8 rows × 1 byte = 8×8 MONO_HLSB
_glyph_fb  = framebuf.FrameBuffer(_glyph_buf, 8, 8, framebuf.MONO_HLSB)


def _extract_glyph(ch):
    """
    Render character ch into a fresh 8-byte buffer using framebuf's built-in font.
    Returns a list of 8 ints (one per row) where bit 7 = leftmost pixel.
    pixel (col) set means BLACK in our display convention.
    """
    _glyph_fb.fill(1)          # white background
    _glyph_fb.text(ch, 0, 0, 0)  # black glyph
    rows = []
    for row in range(8):
        # Read pixel by pixel — framebuf has no direct row-read API
        byte = 0
        for col in range(8):
            if _glyph_fb.pixel(col, row) == 0:  # 0 = black
                byte |= (0x80 >> col)
        rows.append(byte)
    return rows


# ── Scaled text drawing ───────────────────────────────────────────────────────

def draw_char(epd, ch, x, y, font_size, color=0):
    """
    Draw a single character onto the EPaper framebuffer at (x, y).
    color=0 → black glyph on white background (default).
    color=1 → white glyph on black background (inverted / highlight).
    """
    scale = _SCALE[font_size]
    rows  = _extract_glyph(ch if 0x20 <= ord(ch) <= 0x7E else ' ')
    bg    = 1 - color  # background is inverse of foreground

    for row_idx, row_bits in enumerate(rows):
        for col_idx in range(8):
            px_color = color if (row_bits & (0x80 >> col_idx)) else bg
            px = x + col_idx * scale
            py = y + row_idx * scale
            if scale == 1:
                epd.pixel(px, py, px_color)
            else:
                epd.fill_rect(px, py, scale, scale, px_color)


def draw_text(epd, text, x, y, font_size, color=0):
    """
    Draw a string at (x, y).  No wrapping — caller is responsible for line breaks.
    Returns the x position after the last character.
    """
    cw = char_width(font_size)
    cx = x
    for ch in text:
        draw_char(epd, ch, cx, y, font_size, color)
        cx += cw
    return cx


def draw_text_centered(epd, text, y, font_size, display_width, color=0):
    """Draw text horizontally centered on the display."""
    cw     = char_width(font_size)
    total  = cw * len(text)
    x      = max(0, (display_width - total) // 2)
    draw_text(epd, text, x, y, font_size, color)


def draw_text_right(epd, text, y, font_size, display_width, margin=2, color=0):
    """Draw text right-aligned."""
    cw    = char_width(font_size)
    total = cw * len(text)
    x     = display_width - total - margin
    if x < 0:
        x = 0
    draw_text(epd, text, x, y, font_size, color)
