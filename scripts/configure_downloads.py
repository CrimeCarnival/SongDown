"""Configure the public netdisk link without rebuilding the website."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--code', default='')
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'downloads.json')
    args = parser.parse_args()
    try:
        url = urlsplit(args.url)
        valid = url.scheme == 'https' and url.hostname and not url.username and not url.password and not any(ord(c) < 32 for c in args.url)
    except ValueError:
        valid = False
    if not valid:
        parser.error('Provide a valid HTTPS share link without embedded credentials')
    digest = ''
    if args.archive:
        with args.archive.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
    args.output.write_text(json.dumps(dict(url=args.url, extraction_code=args.code, sha256=digest,
        title='QQ 转换服务端组件包', note='供站长维护使用；在线转换用户无需安装。'), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Public download configuration saved:', args.output)


if __name__ == '__main__':
    main()
