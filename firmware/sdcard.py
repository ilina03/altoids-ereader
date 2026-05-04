# sdcard.py — SD card mount and file helpers
# Uses the community sdcard.py driver (must be present on Pico as 'sdcard_drv.py')
# or MicroPython's built-in sdcard module where available.
#
# SD card shares SPI0 with the e-Paper display.
# SD CS  = GP15  (Pin 20)
# SD MISO = GP16  (Pin 21)  — SD only
# SD MOSI = GP19  (Pin 25)  — shared
# SD SCK  = GP18  (Pin 24)  — shared
#
# Directory structure expected on SD card:
#   /books/
#       <title>.txt
#       <title>.bmp   (optional 80×80 BW pixel-art cover)
#   /bookmarks/
#       <title>.txt   (stores "chapter,page" as plain text)

import os
import time
from machine import Pin, SPI

# Mount point used throughout the firmware
SD_MOUNT = "/sd"
BOOKS_DIR      = SD_MOUNT + "/books"
BOOKMARKS_DIR  = SD_MOUNT + "/bookmarks"

_mounted = False


def mount(spi, cs_pin):
    """
    Mount the SD card via the MicroPython sdcard driver.
    spi    — already-configured machine.SPI instance (SPI0, shared with display)
    cs_pin — machine.Pin for SD chip-select (GP15)

    The display CS must be held HIGH before calling this so it doesn't interfere.
    Returns True on success, False on failure.
    """
    global _mounted
    if _mounted:
        return True
    try:
        import sdcard as _sd
        sd = _sd.SDCard(spi, cs_pin)
        vfs = os.VfsFat(sd)
        os.mount(vfs, SD_MOUNT)
        _mounted = True
        _ensure_dirs()
        return True
    except Exception as e:
        print("SD mount failed:", e)
        return False


def _ensure_dirs():
    """Create required directories if absent."""
    for d in (BOOKS_DIR, BOOKMARKS_DIR):
        try:
            os.mkdir(d)
        except OSError:
            pass  # already exists


def is_mounted():
    return _mounted


# ── File listing ──────────────────────────────────────────────────────────────

def list_books():
    """
    Return a sorted list of book base-names (without .txt extension)
    found in /sd/books/.
    """
    if not _mounted:
        return []
    try:
        entries = os.listdir(BOOKS_DIR)
        books = [e[:-4] for e in entries if e.endswith(".txt")]
        books.sort()
        return books
    except Exception:
        return []


def book_path(name):
    return BOOKS_DIR + "/" + name + ".txt"


def cover_path(name):
    return BOOKS_DIR + "/" + name + ".bmp"


def bookmark_path(name):
    return BOOKMARKS_DIR + "/" + name + ".txt"


def cover_exists(name):
    try:
        os.stat(cover_path(name))
        return True
    except OSError:
        return False


# ── Generic file helpers ──────────────────────────────────────────────────────

def read_text(path):
    """Read entire file as UTF-8 string. Returns '' on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def write_text(path, content):
    """Write string to file. Returns True on success."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print("write_text error:", e)
        return False


def read_lines(path):
    """Read file as list of lines (stripped). Returns [] on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.rstrip("\n\r") for line in f]
    except Exception:
        return []


def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


# ── BMP loading ───────────────────────────────────────────────────────────────

def load_bmp_1bit(path):
    """
    Load an 80×80 1-bit BMP file from SD card.
    Returns (width, height, bytearray_pixels) where each byte encodes 8 pixels
    MSB-first, 0=black 1=white, rows top-to-bottom.
    Returns None on error.

    Supports: BMP with 1bpp (monochrome) or 24bpp (quantised to 1-bit).
    BMP rows are stored bottom-to-top in the file; we flip here.
    """
    try:
        with open(path, "rb") as f:
            # BMP file header (14 bytes)
            hdr = f.read(14)
            if hdr[:2] != b'BM':
                return None
            data_offset = int.from_bytes(hdr[10:14], 'little')

            # DIB header (at least 40 bytes)
            dib = f.read(40)
            width    = int.from_bytes(dib[4:8],  'little')
            height   = int.from_bytes(dib[8:12], 'little')
            bpp      = int.from_bytes(dib[14:16],'little')

            flip = True
            if height < 0:          # top-down BMP (rare)
                height = -height
                flip   = False

            f.seek(data_offset)

            if bpp == 1:
                # 1bpp: each row padded to 4-byte boundary
                row_bytes = ((width + 31) // 32) * 4
                raw_rows = []
                for _ in range(height):
                    raw_rows.append(f.read(row_bytes))
            elif bpp == 24:
                # 24bpp: read and quantise to 1-bit (avg > 127 → white)
                row_bytes = ((width * 3 + 3) // 4) * 4
                raw_rows = []
                for _ in range(height):
                    row_data = f.read(row_bytes)
                    bits = 0
                    out_row = bytearray((width + 7) // 8)
                    for x in range(width):
                        b = row_data[x * 3]
                        g = row_data[x * 3 + 1]
                        r = row_data[x * 3 + 2]
                        gray = (r + g + b) // 3
                        if gray >= 128:  # white
                            out_row[x // 8] |= (0x80 >> (x % 8))
                    raw_rows.append(bytes(out_row))
            else:
                return None  # unsupported bpp

            if flip:
                raw_rows.reverse()

            # Pack into clean (width+7)//8 bytes per row output
            out_stride = (width + 7) // 8
            pixels = bytearray(out_stride * height)
            for row_idx, row in enumerate(raw_rows):
                pixels[row_idx * out_stride:(row_idx + 1) * out_stride] = \
                    row[:out_stride]

            return (width, height, pixels)

    except Exception as e:
        print("load_bmp error:", e)
        return None
