"""Build an offline Windows bundle from explicitly staged public dependencies.

Prepare cache with official python-3.13.15-embed-amd64.zip, wheels/ and
qmdec/ (clean upstream checkout). No user profile or media are copied.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from package_source import FILES, ROOT

PYTHON_HASH = 'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qq-archive', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=ROOT / '.release/components-cache')
    parser.add_argument('--output', type=Path, default=ROOT / '.release/SongDown-Windows-Components.zip')
    args = parser.parse_args()
    cache = args.cache.resolve()
    embed = cache / 'python-3.13.15-embed-amd64.zip'
    if sha(embed) != PYTHON_HASH:
        parser.error('Official Python archive SHA256 mismatch')
    wheels = sorted((cache / 'wheels').glob('*.whl'))
    if not any(p.name.startswith('qmdec-') for p in wheels):
        parser.error('Missing qmdec wheel')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='songdown-bundle-', dir=args.output.parent) as temp:
        base = Path(temp) / 'SongDown'
        runtime = base / 'runtime'
        app = base / 'app'
        runtime.mkdir(parents=True)
        with zipfile.ZipFile(embed) as z:
            z.extractall(runtime)
        (runtime / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../app\n', encoding='utf-8')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile',
            '--target', str(runtime / 'Lib/site-packages'), *map(str, wheels)], check=True)
        for name in FILES:
            target = app / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        ffmpeg = next((runtime / 'Lib/site-packages/imageio_ffmpeg/binaries').glob('*.exe'))
        bundled = app / 'input/Tools/ff.exe'
        bundled.parent.mkdir(parents=True)
        shutil.copy2(ffmpeg, bundled)
        shutil.copy2(args.qq_archive, base / 'QQMusic.rar')
        notices = base / 'licenses'
        notices.mkdir()
        shutil.copy2(cache / 'qmdec/README.md', notices / 'qmdec-README.md')
        shutil.copy2(cache / 'FFmpeg-COPYING.GPLv3', notices / 'FFmpeg-COPYING.GPLv3')
        (notices / 'SOURCES.txt').write_text(
            'Python: https://www.python.org/downloads/release/python-31315/\n'
            'qmdec 0.2.0 MIT: https://github.com/Sophomoresty/qmdec/tree/c4b22f0e5683f99fda079f1cd9e9f6cdd39d1ce9\n'
            'Python package licenses: runtime/Lib/site-packages/*.dist-info/\n'
            'FFmpeg binary: imageio-ffmpeg 0.6.0 Windows wheel, executable copied without modification.\n'
            'FFmpeg build/source information: https://github.com/imageio/imageio-ffmpeg and https://www.gyan.dev/ffmpeg/builds/ and https://github.com/FFmpeg/FFmpeg/tree/n7.1\n'
            'QQMusic.rar: supplied by site operator; version 19.51. Not claimed as an official installer.\n', encoding='utf-8')
        result = subprocess.run([str(ffmpeg), '-version'], capture_output=True, check=True)
        (notices / 'FFmpeg-build.txt').write_bytes(result.stdout)
        result = subprocess.run([str(ffmpeg), '-L'], capture_output=True, check=True)
        (notices / 'FFmpeg-license.txt').write_bytes(result.stdout + result.stderr)
        common = '@echo off\r\ncd /d "%~dp0"\r\nset "PYTHONIOENCODING=utf-8"\r\nset "USERPROFILE=%~dp0private-profile"\r\n'
        (base / 'start_server.bat').write_bytes((common +
            'set "WEB_DATA_DIR=%~dp0private-jobs"\r\n"%~dp0runtime\\python.exe" "%~dp0app\\run_web.py" --host 127.0.0.1 --port 8765\r\npause\r\n').encode('ascii'))
        (base / 'update_qq_cookie.bat').write_bytes((common +
            '"%~dp0runtime\\python.exe" "%~dp0app\\update_cookie.py"\r\npause\r\n').encode('ascii'))
        shutil.copy2(ROOT / 'deploy/LOCAL_QQ.md', base / 'READ-ME-FIRST.md')
        manifest = {'python': '3.13.15 x64', 'frida':'16.7.10', 'qq_bundled':'19.51, unverified for decryption',
            'qq_verified_separately':'22.05 / 2205.23.22.21',
            'qq_archive_sha256':sha(args.qq_archive),
            'wheels':{p.name:sha(p) for p in wheels},
            'files':{p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*')) if p.is_file()}}
        (base / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        subprocess.run([str(runtime / 'python.exe'), '-c',
            'import sys,flask,waitress,frida,Crypto,qmdec.cli; import web_app; print(sys.version); print(frida.__version__)'], check=True)
        with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(base.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    z.write(path, 'SongDown/' + path.relative_to(base).as_posix())
    digest = sha(args.output)
    args.output.with_suffix('.zip.sha256').write_text(digest + '  ' + args.output.name + '\n', encoding='ascii')
    print(args.output, args.output.stat().st_size, digest)


if __name__ == '__main__':
    main()
