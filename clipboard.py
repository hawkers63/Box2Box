"""Put text and HTML on the Windows clipboard at once, for "Copy for a post".

A plain-text editor (Reddit's Markdown box, Discord, Notepad) takes the text; a rich editor (such as the SI
forums') takes the HTML table. Tk's own clipboard holds text only, so this writes both through the Windows API.
"""

from __future__ import annotations

import sys
import time

_HEADER = ("Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\n"
           "StartFragment:{2:010d}\r\nEndFragment:{3:010d}\r\n")
_PREFIX = "<html><body>\r\n<!--StartFragment-->"
_SUFFIX = "<!--EndFragment-->\r\n</body></html>"


class ClipboardError(Exception):
    """Nothing could be put on the clipboard."""


def cf_html(fragment: str) -> bytes:
    """The "HTML Format" clipboard payload for an HTML fragment. Its header gives byte offsets (UTF-8) to the
    whole document and to the fragment, which is what a pasting program reads."""
    prefix, body, suffix = _PREFIX.encode("utf-8"), fragment.encode("utf-8"), _SUFFIX.encode("utf-8")
    start_html = len(_HEADER.format(0, 0, 0, 0).encode("ascii"))
    start_fragment = start_html + len(prefix)
    end_fragment = start_fragment + len(body)
    end_html = end_fragment + len(suffix)
    header = _HEADER.format(start_html, end_html, start_fragment, end_fragment).encode("ascii")
    return header + prefix + body + suffix


def copy(text: str, html: str) -> bool:
    """Put the text and the HTML fragment on the clipboard. Returns True when both went, False when only the
    text did; raises ClipboardError when nothing could be written (or not on Windows)."""
    if sys.platform != "win32":
        raise ClipboardError("the two-format clipboard is Windows only")
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes, user32.RegisterClipboardFormatW.restype = [wintypes.LPCWSTR], wintypes.UINT
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    gmem_moveable, cf_unicodetext = 0x0002, 13

    def put(fmt: int, data: bytes) -> bool:
        handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):     # the clipboard owns the memory only on success
            kernel32.GlobalFree(handle)
            return False
        return True

    for _ in range(10):                                  # another program may hold the clipboard for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        raise ClipboardError("the clipboard is in use by another program")
    try:
        user32.EmptyClipboard()
        windows_text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        if not put(cf_unicodetext, (windows_text + "\0").encode("utf-16-le")):
            raise ClipboardError("the text could not be put on the clipboard")
        html_format = user32.RegisterClipboardFormatW("HTML Format")
        return bool(html_format) and put(html_format, cf_html(html) + b"\0")
    finally:
        user32.CloseClipboard()
