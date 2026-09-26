"""Browser QA. Install playwright and its browser separately; server must be running."""
import argparse
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_converter_core import find_ffmpeg
from test_ncm import fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--channel', default='msedge')
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    artifacts = ROOT / '.test-artifacts'
    artifacts.mkdir(exist_ok=True)
    demo = artifacts / '演示专辑'
    demo.mkdir(exist_ok=True)
    for ext in ['mp3', 'flac', 'ogg']:
        target = artifacts / ('tone.' + ext)
        subprocess.run([find_ffmpeg(), '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.5', '-y', str(target)], check=True)
        if ext in {'mp3', 'flac'}:
            (demo / ('测试-' + ext + '.ncm')).write_bytes(fixture(target.read_bytes()))
        else:
            (demo / '测试-ogg.ogg').write_bytes(target.read_bytes())
    (demo / '测试-mp3.lrc').write_text('[00:00.00]测试歌词', encoding='utf-8')
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel if args.channel else None)
        context = browser.new_context(viewport={'width':1440, 'height':1080}, accept_downloads=True)
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.goto(args.base_url)
        expect(page.locator('#workbench')).to_be_visible()
        expect(page.locator('.task-option input[value=ncm]')).to_be_enabled()
        expect(page.locator('.task-option input[value=mgg]')).to_be_disabled()
        page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#folder-input').set_input_files(str(demo))
        expect(page.locator('#file-count')).to_have_text('4 个文件')
        page.locator('#start').click()
        expect(page.locator('#job-status')).to_have_text('已完成', timeout=30000)
        expect(page.locator('#download-all')).to_be_visible()
        expect(page.locator('#result-files audio')).to_have_count(3)
        audio = page.locator('#result-files audio').first
        audio.evaluate('(a) => { a.load(); }')
        for _ in range(50):
            if audio.evaluate('(a) => a.readyState') >= 1:
                break
            page.wait_for_timeout(100)
        assert audio.evaluate('(a) => a.duration') > 0
        with page.expect_download() as event:
            page.locator('#download-all').click()
        download = event.value
        target = artifacts / 'results.zip'
        download.save_as(str(target))
        with zipfile.ZipFile(target) as archive:
            assert len(archive.namelist()) == 4
            assert archive.read('演示专辑/测试-flac.flac') == (artifacts / 'tone.flac').read_bytes()
        page.screenshot(path=str(artifacts / 'converted.png'), full_page=True)
        # Refresh restores the previous task within the same browser session.
        page.reload()
        expect(page.locator('#download-all')).to_be_visible()
        page.locator('#delete-job').click()
        expect(page.locator('#result-panel')).to_be_hidden()
        expect(page.locator('#notice')).to_contain_text('已删除')
        page.locator('#file-input').set_input_files([str(demo / '测试-mp3.ncm')])
        page.locator('#file-input').set_input_files([str(demo / '测试-mp3.ncm')])
        expect(page.locator('#notice')).to_contain_text('已在列表中')
        page.locator('#clear-files').click()
        expect(page.locator('#file-count')).to_have_text('0 个文件')
        expect(page.locator('#start')).to_be_disabled()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button', name='选择文件', exact=False).first.focus()
        expect(page.locator('#pick-files')).to_be_focused()
        assert not errors, errors
        assert all(url.startswith(args.base_url) for url in requests), requests
        browser.close()
    print('Browser QA passed: folder upload, conversion, audio playback metadata, ZIP, restore, delete, duplicate, clear, responsive layout, no external requests.')


if __name__ == '__main__':
    main()
