# reader.py — Text loading, pagination, and chapter detection.
#
# Memory strategy: load one page at a time by tracking byte offsets.
# The book file is never fully loaded into RAM.
#
# Text file format:
#   Line 0: book title
#   Line 1: author name
#   Lines 2+: body text
#
# Chapter detection: a line starting with "Chapter" (case-insensitive)
# or a Roman numeral chapter heading is treated as a new chapter.
#
# Pagination is based on character-wrap at chars_per_line width,
# then line-count per page.  Page breaks are stored as byte offsets
# into the file so we can seek directly.

import sdcard as sd
from fonts import chars_per_line, lines_per_page, FONT_SMALL, FONT_MEDIUM, FONT_LARGE
from epaper import DISPLAY_W, DISPLAY_H

STATUS_BAR_H = 10   # pixels reserved at bottom for status bar
MARGIN       = 2    # pixel margin on each side


def _wrap_line(line, width):
    """
    Break `line` into sub-lines of at most `width` characters.
    Respects word boundaries where possible.
    Returns list of strings.
    """
    line = line.rstrip()
    if not line:
        return [""]

    result = []
    while len(line) > width:
        # Try to break at last space within width
        break_at = line.rfind(" ", 0, width)
        if break_at <= 0:
            break_at = width
        result.append(line[:break_at])
        line = line[break_at:].lstrip()

    result.append(line)
    return result


class BookReader:
    """
    Manages pagination and seeking through a single .txt book file.
    Call load() before any other method.
    """

    def __init__(self):
        self.book_name  = None
        self.title      = ""
        self.author     = ""
        self.font_size  = FONT_MEDIUM

        # Page index: list of (byte_offset, chapter_num) tuples.
        # Index 0 = first page of body text.
        self._page_offsets   = []
        self._total_pages    = 0
        self._current_page   = 0      # 0-based index into _page_offsets
        self._current_chapter = 1

        self._body_offset = 0         # byte offset where body text starts

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, book_name, font_size=FONT_MEDIUM):
        """
        Parse page offsets for book_name at the given font_size.
        Must be called whenever the book or font changes.
        Returns True on success.
        """
        path = sd.book_path(book_name)
        if not sd.file_exists(path):
            return False

        self.book_name = book_name
        self.font_size = font_size

        self._read_metadata(path)
        self._build_page_index(path)
        self._current_page    = 0
        self._current_chapter = 1
        return True

    def total_pages(self):
        return self._total_pages

    def current_page_num(self):
        """1-based page number."""
        return self._current_page + 1

    def current_chapter(self):
        return self._current_chapter

    def seek_page(self, page_num_1based):
        """Jump to a specific 1-based page number."""
        idx = max(0, min(page_num_1based - 1, self._total_pages - 1))
        self._current_page    = idx
        self._current_chapter = self._page_offsets[idx][1]

    def seek_chapter_page(self, chapter, page_within_chapter):
        """
        Jump to (chapter, page_within_chapter).  Finds the first page of
        that chapter, then advances page_within_chapter-1 more pages.
        Falls back to page 1 if not found.
        """
        # Find first occurrence of this chapter
        for i, (offset, ch) in enumerate(self._page_offsets):
            if ch == chapter:
                target = min(i + page_within_chapter - 1, self._total_pages - 1)
                self._current_page    = target
                self._current_chapter = self._page_offsets[target][1]
                return
        self.seek_page(1)

    def next_page(self):
        """Advance one page. Returns False if already at last page."""
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._current_chapter = self._page_offsets[self._current_page][1]
            return True
        return False

    def prev_page(self):
        """Go back one page. Returns False if already at first page."""
        if self._current_page > 0:
            self._current_page -= 1
            self._current_chapter = self._page_offsets[self._current_page][1]
            return True
        return False

    def get_page_lines(self):
        """
        Read and return the text lines for the current page.
        Returns a list of strings (already wrapped to chars_per_line).
        Loads only the current page's worth of text from disk.
        """
        if not self._page_offsets:
            return []

        path = sd.book_path(self.book_name)
        cpw  = chars_per_line(DISPLAY_W, self.font_size, MARGIN)
        lpp  = lines_per_page(DISPLAY_H, self.font_size, STATUS_BAR_H, MARGIN)

        offset, _ = self._page_offsets[self._current_page]

        lines_out = []
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                while len(lines_out) < lpp:
                    raw = f.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    wrapped = _wrap_line(line, cpw)
                    for wl in wrapped:
                        lines_out.append(wl)
                        if len(lines_out) >= lpp:
                            break
        except Exception as e:
            print("get_page_lines error:", e)

        return lines_out

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _read_metadata(self, path):
        """Extract title and author from first two lines."""
        self.title  = ""
        self.author = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.title  = f.readline().rstrip("\r\n")
                self.author = f.readline().rstrip("\r\n")
        except Exception:
            pass

    def _build_page_index(self, path):
        """
        Scan the entire file once to build _page_offsets.
        Each entry: (byte_offset_of_first_line_on_page, chapter_number)
        This uses a minimal rolling buffer — we only keep current-page lines.
        """
        self._page_offsets = []

        cpw = chars_per_line(DISPLAY_W, self.font_size, MARGIN)
        lpp = lines_per_page(DISPLAY_H, self.font_size, STATUS_BAR_H, MARGIN)

        chapter   = 1
        line_count = 0
        page_start_offset = None

        try:
            with open(path, "rb") as f:
                # Skip title and author lines
                f.readline()
                f.readline()
                self._body_offset = f.tell()
                page_start_offset = self._body_offset

                while True:
                    pos = f.tell()
                    raw = f.readline()
                    if not raw:
                        # End of file — save last page if it has content
                        if line_count > 0:
                            self._page_offsets.append((page_start_offset, chapter))
                        break

                    line = raw.decode("utf-8", "replace").rstrip("\r\n")

                    # Chapter detection
                    stripped = line.strip()
                    if self._is_chapter_heading(stripped):
                        # Flush current page if non-empty
                        if line_count > 0:
                            self._page_offsets.append((page_start_offset, chapter))
                            line_count = 0
                        chapter += 1
                        page_start_offset = pos

                    wrapped = _wrap_line(line, cpw)
                    for _ in wrapped:
                        line_count += 1
                        if line_count >= lpp:
                            self._page_offsets.append((page_start_offset, chapter))
                            line_count = 0
                            page_start_offset = f.tell()
                            break  # next iteration will continue after this line

        except Exception as e:
            print("_build_page_index error:", e)

        if not self._page_offsets:
            self._page_offsets = [(self._body_offset, 1)]

        self._total_pages = len(self._page_offsets)

    @staticmethod
    def _is_chapter_heading(line):
        """Return True if line looks like a chapter heading."""
        if not line:
            return False
        lower = line.lower()
        if lower.startswith("chapter"):
            return True
        # Simple Roman numeral check: line is only I/V/X/L/C/D/M chars (1-8 long)
        if 1 <= len(line) <= 8 and all(c in "IVXLCDMivxlcdm" for c in line):
            return True
        return False
