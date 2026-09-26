#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ 音乐 .mgg 加密文件批量解密并转换为 .mp3。

用法:
    python convert_mgg_to_mp3.py -i input -o output
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from audio_converter_core import ConversionOptions, run_conversion


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QQ 音乐 .mgg 加密文件批量解密并转换为 .mp3",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-i", "--input", default="input", help="输入目录（递归查找 .mgg）")
    parser.add_argument("-o", "--output", default="output", help="输出目录（保持相对结构）")
    parser.add_argument("--keep-intermediate", action="store_true", help="保留解密后的中间音频文件")
    parser.add_argument("--no-lrc", action="store_true", help="不复制 .lrc 歌词文件")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    options = ConversionOptions(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        convert_mflac=False,
        convert_mgg=True,
        convert_ogg=False,
        copy_lrc=not args.no_lrc,
        keep_intermediate=args.keep_intermediate,
    )
    stats = run_conversion(options, log=logging.info)
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
