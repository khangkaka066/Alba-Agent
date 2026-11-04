import unittest

from framing import decode_frame, encode_frame


class FramingTests(unittest.TestCase):
    def test_non_ascii_header(self):
        self.assertEqual(encode_frame("\u00e9"), b"\x00\x02\xc3\xa9")

    def test_round_trip(self):
        text, end = decode_frame(encode_frame("h\u00e9llo"))
        self.assertEqual(text, "h\u00e9llo")
        self.assertEqual(end, 8)


if __name__ == "__main__":
    unittest.main()
