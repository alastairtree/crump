"""Utilities for cross-platform console output.

This module provides helpers for rendering console output that works
across different platforms, particularly handling Windows encoding limitations.
"""

import platform


def get_box_char(unicode_char: str, ascii_fallback: str) -> str:
    """Get appropriate box-drawing character based on platform.

    On Windows, returns ASCII fallback to avoid UnicodeEncodeError with cp1252.
    On other platforms, returns the Unicode character for better visual output.

    Args:
        unicode_char: The Unicode character to use on non-Windows platforms
        ascii_fallback: The ASCII fallback to use on Windows

    Returns:
        The appropriate character for the current platform
    """
    if platform.system() == "Windows":
        return ascii_fallback
    return unicode_char


# Common characters
CHECKMARK = get_box_char("✓", "OK")
BULLET = get_box_char("•", "*")
HORIZONTAL_LINE = get_box_char("─", "-")
