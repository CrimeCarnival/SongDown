"""End-to-end HTTP smoke test against a running service (standard library only)."""
import argparse
import http.cookiejar
import io
import json
import secrets
import time
import urllib.error
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--token', default='')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, data=None, method=None, content_type='application/json'):
        headers = {'X-Requested-With': 'AudioWorkbench', 'Content-Type': content_type}
        with opener.open(urllib.request.Request(base + path, data=data, headers=headers, method=method), timeout=30) as response:
            return response.read()

    assert json.loads(call('/api/health'))['status'] == 'ok'
    if args.token:
        call('/api/session', json.dumps({'token': args.token}).encode(), 'POST')
    caps = json.loads(call('/api/capabilities'))
    assert caps['tasks']['ncm']['available'] and caps['tasks']['ogg']['available']
    boundary = 'SongDownSmoke' + secrets.token_hex(12)
    lyrics = '[00:00.00]SongDown HTTP smoke test'.encode()
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="tasks"\r\n\r\n["lrc"]\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="album/test.lrc"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + lyrics + f'\r\n--{boundary}--\r\n'.encode()
    job = json.loads(call('/api/jobs', data, 'POST', 'multipart/form-data; boundary=' + boundary))
    job_id = job['id']
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = json.loads(call('/api/jobs/' + job_id))
            if job['finished']:
                break
            time.sleep(0.2)
        assert job['status'] == 'completed', job
        assert job['stats']['success'] == 1
        assert call(f'/api/jobs/{job_id}/files/album/test.lrc') == lyrics
        with zipfile.ZipFile(io.BytesIO(call(f'/api/jobs/{job_id}/archive'))) as archive:
            assert archive.read('album/test.lrc') == lyrics
        print('HTTP smoke passed: session, capabilities, upload, worker, status, download, ZIP.')
    finally:
        if job.get('finished'):
            call('/api/jobs/' + job_id, method='DELETE')


if __name__ == '__main__':
    main()
