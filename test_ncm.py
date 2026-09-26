import struct
import tempfile
import unittest
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from ncm_decoder import decode_ncm, ConversionCancelled
from audio_converter_core import ConversionOptions, run_conversion


def fixture(audio):
    key = b'test-audio-key'
    encrypted = AES.new(b'hzHRAmso5kInbaxW', AES.MODE_ECB).encrypt(pad(b'neteasecloudmusic' + key, 16))
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) % 256
        box[i], box[j] = box[j], box[i]
    payload = bytearray()
    for i, value in enumerate(audio):
        j = (i + 1) % 256
        payload.append(value ^ box[(box[j] + box[(box[j] + j) % 256]) % 256])
    u32 = lambda n: struct.pack('<I', n)
    return (b'CTENFDAM\0\0' + u32(len(encrypted)) + bytes(x ^ 100 for x in encrypted)
            + u32(3) + b'xxx' + bytes(5) + u32(12) + u32(3) + b'img' + bytes(9) + payload)


class NcmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input' / '子目录' / '歌曲.NCM'
        self.source.parent.mkdir(parents=True)
        self.out = self.root / 'output'

    def test_formats_chunks_and_skip(self):
        for header, suffix in [(b'ID3', '.mp3'), (b'fLaC', '.flac'), (b'\xff\xfb', '.mp3')]:
            audio = header + bytes(range(256)) * 600
            self.source.write_bytes(fixture(audio))
            target, created = decode_ncm(self.source, self.out)
            self.assertTrue(created)
            self.assertEqual(target.suffix, suffix)
            self.assertEqual(target.read_bytes(), audio)
            self.assertFalse(decode_ncm(self.source, self.out)[1])
            target.unlink()

    def test_bad_inputs_leave_no_output(self):
        valid = fixture(b'ID3' + bytes(100))
        for data in [b'bad', valid[:20], valid[:65], fixture(b'unknown')]:
            self.source.write_bytes(data)
            with self.assertRaises(ValueError):
                decode_ncm(self.source, self.out)
            self.assertFalse(self.out.exists())

    def test_cancel_cleans_temp(self):
        self.source.write_bytes(fixture(b'ID3' + bytes(150000)))
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 3
        with self.assertRaises(ConversionCancelled):
            decode_ncm(self.source, self.out, cancelled)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_batch_stats_and_paths(self):
        self.source.write_bytes(fixture(b'fLaC' + bytes(100)))
        self.source.with_name('bad.ncm').write_bytes(b'bad')
        options = ConversionOptions(self.root / 'input', self.out,
            convert_mflac=False, convert_mgg=False, convert_ogg=False,
            copy_lrc=False, convert_ncm=True)
        stats = run_conversion(options)
        self.assertEqual((stats.total, stats.success, stats.failed), (2, 1, 1))
        self.assertTrue((self.out / '子目录' / '歌曲.flac').exists())
        stats = run_conversion(options)
        self.assertEqual((stats.skipped, stats.failed), (1, 1))

if __name__ == '__main__':
    unittest.main()
