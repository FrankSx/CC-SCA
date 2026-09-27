import unittest
import numpy as np
from sca_arsenal import stego


class TestStego(unittest.TestCase):
    def _img(self, w=64, h=64):
        rng = np.random.default_rng(7)
        return rng.integers(0, 256, (h, w, 4), dtype=np.uint8)

    def test_roundtrip(self):
        img = self._img()
        payload = b'{"op":"flush_reload","thr":100}' * 3
        out = stego.embed(img, payload)
        self.assertTrue((out[:, :, 3] == img[:, :, 3]).all())  # alpha untouched
        self.assertEqual(stego.extract(out), payload)

    def test_too_large(self):
        img = self._img(8, 8)
        with self.assertRaises(ValueError):
            stego.embed(img, b"X" * 500)

    def test_no_magic(self):
        img = self._img()
        with self.assertRaises(ValueError):
            stego.extract(img)

    def test_header_magic(self):
        self.assertEqual(stego.StegoHeader().magic, b"SCA1")


if __name__ == "__main__":
    unittest.main()
