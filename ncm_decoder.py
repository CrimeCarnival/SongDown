"""Streaming NCM audio extraction; preserves the original MP3/FLAC bytes.

Format reference: https://github.com/taurusxin/ncmdump
Container metadata and artwork are skipped, not injected into the audio.
"""
from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path
from typing import Callable


class ConversionCancelled(Exception):
    pass


def decode_ncm(source: Path, output_dir: Path,
               cancelled: Callable[[], bool] | None = None) -> tuple[Path, bool]:
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError as exc:
        raise RuntimeError("缺少 NCM 依赖，请运行 python -m pip install pycryptodome") from exc

    def check_cancel():
        if cancelled and cancelled():
            raise ConversionCancelled()

    check_cancel()
    with source.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size

        def read_exact(count):
            if count < 0 or count > size - stream.tell():
                raise ValueError("NCM 文件已截断或字段长度无效")
            value = stream.read(count)
            if len(value) != count:
                raise ValueError("NCM 文件已截断")
            return value

        def uint32():
            return struct.unpack("<I", read_exact(4))[0]

        def skip(count):
            if count > size - stream.tell():
                raise ValueError("NCM 文件已截断或字段长度无效")
            stream.seek(count, 1)

        if read_exact(8) != b"CTENFDAM":
            raise ValueError("不是有效的 NCM 文件")
        read_exact(2)
        key_size = uint32()
        if not 0 < key_size <= 4096 or key_size % 16:
            raise ValueError("NCM 密钥长度无效")
        encrypted = bytes(value ^ 0x64 for value in read_exact(key_size))
        key = unpad(AES.new(b"hzHRAmso5kInbaxW", AES.MODE_ECB).decrypt(encrypted), 16)
        if not key.startswith(b"neteasecloudmusic") or len(key) <= 17:
            raise ValueError("NCM 密钥无效")
        key = key[17:]
        box = list(range(256))
        position = 0
        for index in range(256):
            position = (position + box[index] + key[index % len(key)]) & 255
            box[index], box[position] = box[position], box[index]
        mask = bytes(box[(box[j] + box[(box[j] + j) & 255]) & 255]
                     for j in ((i + 1) & 255 for i in range(256)))
        skip(uint32())  # Encrypted metadata.
        read_exact(5)  # CRC32 and reserved byte.
        image_space, image_size = uint32(), uint32()
        if image_size > image_space:
            raise ValueError("NCM 封面长度无效")
        skip(image_space)

        def decrypt_chunk(chunk):
            return bytes(value ^ mask[i & 255] for i, value in enumerate(chunk))

        # Chunk size must be a multiple of the 256-byte repeating mask.
        first = decrypt_chunk(stream.read(65536))
        if first.startswith(b"fLaC"):
            suffix = ".flac"
        elif first.startswith(b"ID3") or (len(first) >= 2 and first[0] == 255 and first[1] & 0xE0 == 0xE0):
            suffix = ".mp3"
        else:
            raise ValueError("NCM 音频为空、损坏或不是支持的 MP3/FLAC 格式")
        target = output_dir / (source.stem + suffix)
        if target.exists():
            return target, False
        output_dir.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".ncm-", suffix=".tmp", delete=False) as out:
                temp = Path(out.name)
                out.write(first)
                while True:
                    check_cancel()
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    out.write(decrypt_chunk(chunk))
            check_cancel()
            # Exclusive publication prevents overwriting a file created concurrently.
            try:
                if os.name == "nt":
                    os.rename(temp, target)  # Windows rename never overwrites.
                else:
                    os.link(temp, target)
            except FileExistsError:
                return target, False
            return target, True
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
