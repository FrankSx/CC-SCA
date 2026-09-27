import unittest
from sca_arsenal import covert_channel as cc


class TestCovert(unittest.TestCase):
    def test_crc16_known(self):
        # CRC-16/CCITT-FALSE check value for b"123456789" is 0x29B1
        self.assertEqual(cc.crc16(b"123456789"), 0x29B1)

    def test_bits_bytes_roundtrip(self):
        data = bytes(range(256))
        self.assertEqual(cc.bits_to_bytes(cc.bytes_to_bits(data)), data)

    def test_frame_layout(self):
        f = cc.frame(b"AB")
        self.assertEqual(f[0], cc.SYNC)
        self.assertEqual(f[1], 2)
        self.assertEqual(len(f), 2 + 2 + 2)

    def test_frame_integrity(self):
        f = cc.frame(b"payload!")
        self.assertEqual(f[-2:], cc.crc16(b"payload!").to_bytes(2, "big"))


if __name__ == "__main__":
    unittest.main()
