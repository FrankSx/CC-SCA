import unittest
import numpy as np
from sca_arsenal import eviction


class TestEviction(unittest.TestCase):
    def test_buffer_and_pages(self):
        buf = eviction.new_probe_buffer(64)  # 64 pages
        self.assertEqual(buf.nbytes, 64 * 4096)
        pages = eviction.candidate_pages(buf)
        self.assertEqual(len(pages), 64)

    def test_elem_address_alignment(self):
        buf = eviction.new_probe_buffer(4)
        for p in eviction.candidate_pages(buf):
            self.assertEqual(eviction.elem_address(buf, p) % 4096, 0)

    def test_native_optional(self):
        from sca_arsenal import timing
        # must import and fail cleanly, not crash
        if not timing.native_available():
            with self.assertRaises(RuntimeError):
                eviction.calibrate_threshold(eviction.new_probe_buffer(4))


if __name__ == "__main__":
    unittest.main()
