import unittest
from sca_arsenal import polyglot


class TestPolyglot(unittest.TestCase):
    def test_roundtrip_and_validity(self):
        wasm = b"\x00asm\x01\x00\x00\x00" + bytes(range(64))
        png = polyglot.make_polyglot_png(32, 32, wasm)
        self.assertTrue(polyglot.validate_png(png))
        self.assertEqual(polyglot.extract_wasm(png), wasm)

    def test_detect_flags_wasm(self):
        wasm = b"payload"
        png = polyglot.make_polyglot_png(16, 16, wasm)
        flags = polyglot.detect_nonstandard_chunks(png)
        self.assertTrue(any(f[0] == "waSM" and f[1] for f in flags))

    def test_reject_nonpng(self):
        with self.assertRaises(ValueError):
            polyglot.extract_wasm(b"GIF89a....")


if __name__ == "__main__":
    unittest.main()
