# bookmarks.py — Save and load reading position per book.
#
# Bookmark file format (plain text, one line):
#   chapter,page
# e.g. "3,12"  means chapter 3, page 12 within that chapter.
#
# Files live at:  /sd/bookmarks/<book_name>.txt

import sdcard as sd


def save(book_name, chapter, page):
    """
    Persist the current reading position.
    chapter and page are 1-based integers.
    Returns True on success.
    """
    path    = sd.bookmark_path(book_name)
    content = "{},{}".format(chapter, page)
    return sd.write_text(path, content)


def load(book_name):
    """
    Load the stored reading position for book_name.
    Returns (chapter, page) as ints if a valid bookmark exists,
    or (None, None) if no bookmark is found or the file is malformed.
    """
    path = sd.bookmark_path(book_name)
    if not sd.file_exists(path):
        return (None, None)

    raw = sd.read_text(path).strip()
    if not raw:
        return (None, None)

    try:
        parts = raw.split(",")
        chapter = int(parts[0])
        page    = int(parts[1])
        return (chapter, page)
    except (IndexError, ValueError):
        return (None, None)


def has_bookmark(book_name):
    """Return True if a valid bookmark exists for this book."""
    ch, pg = load(book_name)
    return ch is not None


def delete(book_name):
    """Remove the bookmark for book_name (e.g. when starting from beginning)."""
    path = sd.bookmark_path(book_name)
    try:
        import os
        os.remove(path)
        return True
    except OSError:
        return False
