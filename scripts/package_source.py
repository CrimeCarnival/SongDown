"""Export a source-only archive, optionally updating an existing Git checkout.

Uses an explicit allowlist: never includes songs, credentials or runtime data.
"""
import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    '.gitattributes', '.gitignore', '.dockerignore', '.env.example', 'Dockerfile', 'compose.yaml',
    'README.md', 'VERIFICATION.md', 'THIRD_PARTY.md',
    'requirements.txt', 'requirements-web.txt', 'requirements-test.txt',
    'audio_converter_core.py', 'ncm_decoder.py', 'web_app.py', 'web_worker.py',
    'conversion_errors.py', 'site_settings.py', 'downloads.example.json', 'run_web.py', 'start_web.bat', 'start_local_qq.bat', 'convert_ncm.py', 'test_ncm.py',
    'GUI/app.py', 'start_gui.bat', 'main.py', 'convert_mgg_to_mp3.py',
    'convert_ogg_to_mp3.py', 'update_cookie.py', 'hook_qq_music.js',
    'web/qq-guide.html', 'deploy/LOCAL_QQ.md', 'web/index.html', 'web/style.css', 'web/app.js', 'web/icon.svg',
    'tests/test_downloads.py', 'tests/__init__.py', 'tests/test_web.py',
    'deploy/Caddyfile', 'deploy/README.md', '.github/workflows/ci.yml',
    'scripts/init_deploy.py', 'scripts/smoke_http.py', 'scripts/browser_qa.py',
    'scripts/configure_downloads.py', 'scripts/package_components.py', 'scripts/real_audio_qa.py', 'scripts/package_source.py',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.release/songdown-source.zip')
    parser.add_argument('--checkout', help='Existing Git checkout to populate with the same allowlisted sources')
    args = parser.parse_args()
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        parser.error('Missing source files: ' + ', '.join(missing))
    checkout = Path(args.checkout).resolve() if args.checkout else None
    if checkout and (not (checkout / '.git').is_dir() or checkout == ROOT):
        parser.error('Checkout must be a separate existing Git repository')
    archive_path = Path(args.output).resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            source = ROOT / name
            archive.write(source, 'SongDown/' + name)
            if checkout:
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    print(f'Exported {len(FILES)} source files to {archive_path}')


if __name__ == '__main__':
    main()
