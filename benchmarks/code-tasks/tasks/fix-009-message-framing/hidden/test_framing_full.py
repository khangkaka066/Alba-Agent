import unittest

from framing import decode_frame, decode_stream, encode_frame


class FramingFullTests(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(encode_frame("abc"), b"\x00\x03abc")
        self.assertEqual(encode_frame(""), b"\x00\x00")

    def test_non_ascii_header(self):
        self.assertEqual(encode_frame("\u00e9"), b"\x00\x02\xc3\xa9")
        self.assertEqual(encode_frame("h\u00e9llo")[:2], b"\x00\x06")

    def test_emoji(self):
        frame = encode_frame("\U0001f600")
        self.assertEqual(frame[:2], b"\x00\x04")
        self.assertEqual(decode_frame(frame), ("\U0001f600", 6))

    def test_round_trip_mixed(self):
        for text in ["plain", "caf\u00e9 \u2603", "\u65e5\u672c\u8a9e", "a\U0001f600b"]:
            decoded, end = decode_frame(encode_frame(text))
            self.assertEqual(decoded, text)
            self.assertEqual(end, 2 + len(text.encode("utf-8")))

    def test_size_limit_counts_bytes(self):
        self.assertEqual(len(encode_frame("a" * 65535)), 65537)
        self.assertEqual(len(encode_frame("\u00e9" * 32767)), 2 + 65534)
        with self.assertRaises(ValueError):
            encode_frame("a" * 65536)
        with self.assertRaises(ValueError):
            encode_frame("\u00e9" * 32768)

    def test_stream(self):
        texts = ["one", "d\u00e9j\u00e0 vu", "", "\u2603"]
        data = b"".join(encode_frame(t) for t in texts)
        self.assertEqual(decode_stream(data), texts)
        self.assertEqual(decode_stream(b""), [])

    def test_offset(self):
        data = encode_frame("ab") + encode_frame("\u00e9")
        first, nxt = decode_frame(data)
        second, end = decode_frame(data, nxt)
        self.assertEqual((first, second, end), ("ab", "\u00e9", len(data)))

    def test_incomplete(self):
        frame = encode_frame("h\u00e9llo")
        with self.assertRaises(ValueError):
            decode_frame(frame[:-1])
        with self.assertRaises(ValueError):
            decode_frame(b"\x00")
        with self.assertRaises(ValueError):
            decode_stream(frame + b"\x00")


if __name__ == "__main__":
    unittest.main()
