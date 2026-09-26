"""Batch extract NCM files to their original MP3 or FLAC format."""
import argparse
from pathlib import Path

from audio_converter_core import ConversionOptions, run_conversion


def main():
    parser = argparse.ArgumentParser(description="NCM 批量转换为 MP3 / FLAC（保留原始音质）")
    parser.add_argument("-i", "--input", default="input", help="输入目录")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("--no-lrc", action="store_true", help="不复制歌词")
    args = parser.parse_args()
    stats = run_conversion(ConversionOptions(
        Path(args.input), Path(args.output), convert_mflac=False,
        convert_mgg=False, convert_ogg=False, convert_ncm=True,
        copy_lrc=not args.no_lrc,
    ), log=print)
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
