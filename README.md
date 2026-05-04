# Altoids Tin E-Reader — Firmware & Setup Guide

A pocket e-reader running MicroPython on a Raspberry Pi Pico 2 W,
fitted inside a standard Altoids tin.

---

## Hardware Summary

| Component | Part |
|-----------|------|
| MCU | Raspberry Pi Pico 2 W (RP2350) |
| Display | Waveshare 2.13" e-Paper V4 — 250×122 px |
| Storage | Micro SD card via SPI |
| Power | TP4056 USB-C + LiPo 752540 500 mAh 3.7 V |
| Buttons | 4× tactile switches, 2×2 grid, 10 kΩ pull-up |

---

## Firmware Files

| File | Purpose |
|------|---------|
| `main.py` | Boot, hardware init, main event loop |
| `epaper.py` | Waveshare 2.13" V4 SPI driver |
| `sdcard.py` | SD mount + file helpers (wraps community `sdcard` driver) |
| `reader.py` | Text loading, word-wrap pagination, chapter detection |
| `ui.py` | All screen renderers |
| `buttons.py` | Debounced button polling |
| `bookmarks.py` | Per-book reading position save/load |
| `fonts.py` | Scaled bitmap font rendering (small / medium / large) |

### Required third-party driver

Copy the community MicroPython SD card driver onto your Pico as **`sdcard.py`**
before flashing these files. You can find it at:

```
https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/storage/sdcard/sdcard.py
```

> **Rename it to `sdcard_drv.py`** if you want to avoid a name clash with
> this project's `sdcard.py` wrapper — then update the import at the top of
> `sdcard.py` accordingly (`import sdcard_drv as _sd`).

---

## Flashing the Firmware

1. Hold BOOTSEL on the Pico and plug into USB → it appears as a mass-storage drive.
2. Drag the latest `RPI_PICO2-*.uf2` MicroPython firmware onto the drive.
3. Use **Thonny** (or `mpremote`) to copy all `.py` files to the Pico's root (`/`).
4. Insert the prepared SD card, power on, done.

---

## SD Card Setup

Format the SD card as **FAT32**.  Create this directory structure:

```
/books/
    pride_and_prejudice.txt
    pride_and_prejudice.bmp    ← optional pixel-art cover (80×80 px)
    frankenstein.txt
    frankenstein.bmp
/bookmarks/                    ← created automatically by firmware
```

### Book text file format

Each `.txt` file must follow this exact structure:

```
Pride and Prejudice          ← Line 1: book title
Jane Austen                  ← Line 2: author name
                             ← (blank line or start of text)
It is a truth universally…   ← Body text begins here
```

- Encoding: **UTF-8**
- Line endings: LF or CRLF (both handled)
- Chapter headings: any line beginning with the word **"Chapter"** (case-insensitive)
  or a bare Roman numeral (e.g. `IV`) is treated as a chapter boundary.
- Pagination is calculated automatically based on the selected font size.

### Where to find free e-books

[Project Gutenberg](https://www.gutenberg.org/) provides thousands of books
as plain UTF-8 `.txt` files — copy the "Plain Text UTF-8" download directly.

You may need to delete the Gutenberg header/footer preamble and ensure the
first two lines are **title** and **author**.

---

## Creating Pixel-Art Covers

Covers are optional 80×80 px black-and-white BMP images displayed on the
title page when opening a book.

### With Piskel (free, browser-based)

1. Go to [piskelapp.com](https://www.piskelapp.com) → Create sprite.
2. Resize canvas to **80×80**.
3. Draw your cover in black and white (use the palette to lock to 2 colours).
4. Export → **Download PNG**.
5. Convert the PNG to a 1-bit BMP:
   - In **GIMP**: Image → Mode → Grayscale → Image → Mode → Indexed (2 colours)
     → File → Export As → `.bmp`
   - Or use **ImageMagick**: `magick cover.png -resize 80x80 -monochrome cover.bmp`

### With Aseprite

1. New file → Width: 80, Height: 80, Color Mode: **Indexed**, Palette: 2 colours.
2. Draw your art.
3. File → Export As → `<book_name>.bmp` (check "1 bpp" / monochrome in options).

### Naming

The BMP file **must have the same base name** as the `.txt` file:

```
frankenstein.txt  →  frankenstein.bmp
```

Place both in `/books/` on the SD card.

---

## Button Reference

```
┌─────────┬──────────┐
│   UP    │  SELECT  │
├─────────┼──────────┤
│  BACK   │  DOWN    │
└─────────┴──────────┘
```

| Screen | UP | DOWN | BACK | SELECT |
|--------|----|------|------|--------|
| Menu | Scroll up | Scroll down | Power-off screen | Confirm |
| Book start | Toggle option | Toggle option | Back to menu | Confirm |
| Reading | Previous page | Next page | Back to menu | — |
| Font size | Previous size | Next size | Cancel | Confirm |
| Power off | Toggle YES/NO | Toggle YES/NO | Cancel (NO) | Confirm |

---

## Adding New Books — Quick Steps

1. Format your `.txt` so **line 1 = title**, **line 2 = author**.
2. Copy the file to `/books/` on the SD card.
3. Optionally create an 80×80 monochrome BMP with the same base name.
4. Insert the SD card and power on — the book appears in the menu automatically.

---

## Power & Battery Notes

- Charging: plug a USB-C cable into the TP4056 board through the drilled hole.
  Do **not** power on the reader while charging (LiPo safety).
- The battery percentage shown in the status bar is a rough estimate from the
  VSYS ADC reading (3.0 V = 0%, 4.2 V = 100%).
- "Power Off" puts the Pico into deep sleep (`machine.deepsleep()`).
  Press the RESET button (or re-plug power) to wake it.
- e-ink displays retain the last image with zero power — safe to power off at
  any time.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "SD card not found" | Check wiring; ensure FAT32 format; confirm community `sdcard` driver is on Pico |
| "No books found" | Verify `/books/` directory exists and contains `.txt` files with correct format |
| Display stays blank | Check SPI wiring; confirm e-Paper VCC=3.3 V (not 5 V) |
| Buttons unresponsive | Check 10 kΩ pull-up resistors to 3.3 V on each button pin |
| Garbled text | Ensure `.txt` files are saved as UTF-8 (not Latin-1) |
| Cover not showing | BMP must be exactly the same base name as the `.txt`; must be ≤ 80×80 px monochrome |
