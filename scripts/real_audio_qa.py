"""Local-only acceptance test using explicitly supplied audio files; never uploaded elsewhere."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_converter_core import find_ffmpeg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    from urllib.parse import urlsplit
    if urlsplit(args.base_url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('Real audio QA only accepts a loopback URL')
    from playwright.sync_api import sync_playwright, expect
    from mutagen import File
    result_dir = ROOT / '.test-artifacts' / 'real-results'
    result_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge')
        context = browser.new_context(viewport={'width':1440,'height':1080}, accept_downloads=True)
        page = context.new_page()
        page.goto(args.base_url)
        expect(page.locator('#workbench')).to_be_visible()
        page.locator('#file-input').set_input_files([str(Path(f).resolve()) for f in args.files])
        expect(page.locator('#file-count')).to_have_text(f'{len(args.files)} 个文件')
        page.locator('#start').click()
        deadline = time.monotonic() + 180
        job = None
        while time.monotonic() < deadline:
            job_id = page.evaluate('sessionStorage.getItem("songdown-job")')
            if job_id:
                job = context.request.get(args.base_url + '/api/jobs/' + job_id).json()
                if job.get('finished'):
                    break
            page.wait_for_timeout(500)
        if not job or not job.get('finished'):
            raise RuntimeError('Timed out waiting for uploaded samples')
        report = {'status':job['status'], 'stats':job['stats'], 'logs':job['logs'], 'outputs':[]}
        for output in job['outputs']:
            from urllib.parse import quote
            import requests
            client = requests.Session()
            for cookie in context.cookies():
                client.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
            target = result_dir / Path(output['name']).name
            with client.get(args.base_url + f'/api/jobs/{job["id"]}/files/' + quote(output['name']), stream=True, timeout=60) as response:
                response.raise_for_status()
                with target.open('wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
            check = subprocess.run([find_ffmpeg(), '-v', 'error', '-xerror', '-i', str(target), '-f', 'null', '-'], capture_output=True, timeout=90)
            tags = File(target)
            report['outputs'].append({'file':target.name,'bytes':target.stat().st_size,
                'duration_seconds':round(tags.info.length,3) if tags else None,
                'sample_rate':getattr(tags.info,'sample_rate',None) if tags else None,
                'channels':getattr(tags.info,'channels',None) if tags else None,
                'full_decode_ok':check.returncode==0 and not check.stderr.strip(),
                'decoder_errors':check.stderr.decode('utf-8',errors='replace')[:1000]})
        report_path = result_dir / ('report-' + args.base_url.rsplit(':',1)[-1] + '.json')
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        page.screenshot(path=str(result_dir / 'browser-results.png'),full_page=True)
        print(json.dumps(report,ensure_ascii=False))
        context.request.delete(args.base_url + '/api/jobs/' + job['id'],headers={'X-Requested-With':'AudioWorkbench'})
        browser.close()
        if job['stats']['success'] != len(args.files) or not all(o['full_decode_ok'] for o in report['outputs']):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
