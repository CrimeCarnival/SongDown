"""Only explicit public download fields may leave the server."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def public_downloads():
    path = Path(os.environ.get('SONGDOWN_DOWNLOAD_CONFIG', Path(__file__).parent / 'downloads.json'))
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            pass
    if not isinstance(data, dict):
        data = {}
    url = data.get('url', '')
    if not isinstance(url, str):
        url = ''
    try:
        parsed = urlsplit(url)
    except ValueError:
        parsed = urlsplit('')
    valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
             and not any(ord(char) < 32 for char in url))
    def text(name, fallback='', limit=200):
        value = data.get(name, fallback)
        return value[:limit] if isinstance(value, str) else fallback
    return dict(available=bool(valid), url=url if valid else '',
                title=text('title', 'QQ 转换服务端组件包'),
                extraction_code=text('extraction_code', limit=30),
                sha256=text('sha256', limit=64),
                note=text('note', '供站长维护使用；在线转换用户无需安装。'),
                qq_version='包内 19.51（未实测）；已验证 22.05 / 2205.23.22.21',
                frida_version='16.7.10',
                qq_official_url='https://y.qq.com/download/index.html')
