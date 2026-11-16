"""Tests for the clipboard helper's pure part (the tests never touch the real clipboard)."""

from __future__ import annotations

import re
import unittest

import clipboard


class HtmlFormatTests(unittest.TestCase):
    def test_the_payload_offsets_point_at_the_html_and_the_fragment(self):
        fragment = "<table><tr><td>Hull City &amp; Leeds</td></tr></table>"
        payload = clipboard.cf_html(fragment)
        header = dict(re.findall(r"^(\w+):(\S+)\r?$", payload.decode("ascii", "ignore"), re.M))
        start_html, end_html = int(header["StartHTML"]), int(header["EndHTML"])
        start, end = int(header["StartFragment"]), int(header["EndFragment"])
        self.assertEqual(payload[start:end].decode("utf-8"), fragment)
        self.assertTrue(payload[start_html:].startswith(b"<html>"))
        self.assertEqual(end_html, len(payload))

    def test_offsets_count_bytes_not_characters(self):
        fragment = "<p>Atlético Mineiro · São Paulo</p>"               # accented letters take two bytes each
        payload = clipboard.cf_html(fragment)
        header = dict(re.findall(r"^(\w+):(\S+)\r?$", payload.decode("ascii", "ignore"), re.M))
        self.assertEqual(payload[int(header["StartFragment"]):int(header["EndFragment"])].decode("utf-8"), fragment)


if __name__ == "__main__":
    unittest.main()
