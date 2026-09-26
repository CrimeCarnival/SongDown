import argparse
import logging
import sys
from pathlib import Path

from audio_converter_core import ConversionOptions, run_conversion

def convert_ogg_to_mp3(input_dir, output_dir):
    options = ConversionOptions(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        convert_mflac=False,
        convert_mgg=False,
        convert_ogg=True,
        copy_lrc=True,
    )
    stats = run_conversion(options, log=logging.info)
    return 0 if stats.failed == 0 else 1

if __name__ == "__main__":
    # Set up logging to handle Unicode properly
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=str, required=True, help="Please input input directory")
    parser.add_argument("-o", "--output", type=str, required=True, help="Please input output directory")
    args = parser.parse_args()
    sys.exit(convert_ogg_to_mp3(args.input, args.output))
