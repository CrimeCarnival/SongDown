"""Integration tests use valid generated audio and real converter subprocesses."""
import io
import json
import subprocess
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import MultiDict
from audio_converter_core import find_ffmpeg, _normalize_flac, _flac_streaminfo
from test_ncm import fixture
from web_app import create_app, safe_relative

HEADERS = {'X-Requested-With': 'AudioWorkbench'}


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audio_tmp = tempfile.TemporaryDirectory()
        root = Path(cls.audio_tmp.name)
        cls.ffmpeg = find_ffmpeg()
        if not cls.ffmpeg:
            raise RuntimeError('FFmpeg is required for web integration tests')
        cls.audio = {}
        for suffix in ['mp3', 'flac', 'ogg']:
            target = root / ('tone.' + suffix)
            subprocess.run([cls.ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'sine=frequency=440:duration=0.3', '-y', str(target)], check=True)
            cls.audio[suffix] = target.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.audio_tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.temp.name,
                               'SECRET_KEY': 'test-session-key', 'JOB_TIMEOUT': 20})
        self.client = self.app.test_client()
        self.manager = self.app.extensions['jobs']

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def submit(self, files, tasks, client=None, headers=None):
        data = MultiDict([('tasks', json.dumps(tasks))])
        for name, content in files:
            data.add('files', (io.BytesIO(content), name))
        response = (client or self.client).post('/api/jobs', data=data,
                    headers=HEADERS if headers is None else headers, content_type='multipart/form-data')
        response.request.environ['wsgi.input'].close()
        return response

    def wait(self, job_id):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            response = self.client.get('/api/jobs/' + job_id)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            if data['finished']:
                return data
            time.sleep(0.04)
        self.fail('Job did not finish')

    def test_real_audio_batch_preview_archive_delete(self):
        response = self.submit([
            ('专辑/保真.NCM', fixture(self.audio['flac'])),
            ('专辑/歌曲.ncm', fixture(self.audio['mp3'])),
            ('其他/测试.OGG', self.audio['ogg']),
            ('专辑/歌曲.LRC', '[00:00.00]测试歌词'.encode()),
        ], ['ncm', 'ogg', 'lrc'])
        self.assertEqual(response.status_code, 202, response.get_json())
        job_id = response.get_json()['id']
        job = self.wait(job_id)
        self.assertEqual(job['status'], 'completed', job['logs'])
        self.assertEqual(job['stats'], {'total': 4, 'success': 4, 'skipped': 0, 'failed': 0})
        archive = self.client.get(f'/api/jobs/{job_id}/archive')
        self.assertEqual(archive.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive.data)) as bundle:
            self.assertEqual(set(bundle.namelist()), {'专辑/保真.flac', '专辑/歌曲.mp3', '其他/测试.mp3', '专辑/歌曲.LRC'})
            self.assertEqual(bundle.read('专辑/保真.flac'), self.audio['flac'])
            self.assertEqual(bundle.read('专辑/歌曲.mp3'), self.audio['mp3'])
            output = Path(self.temp.name) / 'verify.mp3'
            output.write_bytes(bundle.read('其他/测试.mp3'))
            subprocess.run([self.ffmpeg, '-v', 'error', '-i', str(output), '-f', 'null', '-'], check=True, capture_output=True)
        archive.close()
        preview = self.client.get(f'/api/jobs/{job_id}/files/专辑/歌曲.mp3?preview=1', headers={'Range': 'bytes=0-99'})
        self.assertEqual(preview.status_code, 206)
        self.assertEqual(len(preview.data), 100)
        preview.close()
        response = self.client.delete(f'/api/jobs/{job_id}', headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertFalse((Path(self.temp.name) / job_id).exists())
        self.assertEqual(self.client.get(f'/api/jobs/{job_id}').status_code, 404)

    def test_partial_failure_no_broken_outputs(self):
        response = self.submit([('valid.ncm', fixture(self.audio['mp3'])),
                                ('broken.ncm', b'not ncm'), ('bad.ogg', b'not ogg')], ['ncm', 'ogg'])
        job = self.wait(response.get_json()['id'])
        self.assertEqual(job['status'], 'partial', job['logs'])
        self.assertEqual(job['stats']['failed'], 2)
        self.assertEqual([f['name'] for f in job['outputs']], ['valid.mp3'])
        self.assertFalse(list((Path(self.temp.name) / job['id'] / 'output').glob('.convert-*')))

    def test_authentication_csrf_and_session_isolation(self):
        self.app.config['ACCESS_TOKEN'] = 'correct-token-01234567890123456789'
        self.assertEqual(self.client.get('/api/capabilities').status_code, 401)
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.post('/api/session', json={'token': 'bad'}, headers=HEADERS).status_code, 401)
        self.assertEqual(self.client.post('/api/session', json={'token': self.app.config['ACCESS_TOKEN']}, headers=HEADERS).status_code, 200)
        response = self.submit([('a.lrc', b'hello')], ['lrc'])
        job_id = response.get_json()['id']
        self.wait(job_id)
        other = self.app.test_client()
        other.post('/api/session', json={'token': self.app.config['ACCESS_TOKEN']}, headers=HEADERS)
        for suffix in ['', '/archive', '/files/a.lrc']:
            self.assertEqual(other.get(f'/api/jobs/{job_id}{suffix}').status_code, 404)
        self.assertEqual(other.post(f'/api/jobs/{job_id}/cancel', headers=HEADERS).status_code, 404)
        self.assertEqual(self.client.post(f'/api/jobs/{job_id}/cancel').status_code, 403)
        self.assertEqual(self.client.post(f'/api/jobs/{job_id}/cancel', headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post(f'/api/jobs/{job_id}/cancel', headers={**HEADERS, 'Sec-Fetch-Site': 'cross-site'}).status_code, 403)

    def test_path_traversal_reserved_names_duplicates_and_mismatch(self):
        for name in ['../evil.ncm', '/evil.ncm', 'C:\\evil.ncm', 'ok/../../evil.ncm', 'CON.ncm', 'a./evil.ncm']:
            response = self.submit([(name, b'abc')], ['ncm'])
            self.assertEqual(response.status_code, 400, name)
        self.assertEqual(safe_relative('中文/歌曲.ncm').as_posix(), '中文/歌曲.ncm')
        for files in [[('x.ncm', b'a'), ('X.NCM', b'b')], [('x.ncm', b'a'), ('x.ogg', b'b')]]:
            self.assertEqual(self.submit(files, ['ncm', 'ogg']).status_code, 400)
        self.assertEqual(self.submit([('a.exe', b'abc')], ['ncm']).status_code, 400)
        self.assertEqual(self.submit([('a.ncm', b'')], ['ncm']).status_code, 400)
        self.assertEqual(self.submit([('a.ncm', b'abc')], ['ogg']).status_code, 400)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_public_qq_disabled_and_cookie_private(self):
        tasks = self.client.get('/api/capabilities').get_json()['tasks']
        self.assertFalse(tasks['mflac']['available'])
        self.assertFalse(tasks['mgg']['available'])
        self.assertFalse(tasks['cookie']['available'])
        self.assertEqual(self.client.post('/api/cookie', headers=HEADERS).status_code, 403)
        self.assertEqual(self.submit([('song.mgg', b'abc')], ['mgg']).status_code, 400)

    def test_local_mode_rejects_remote_and_bad_host(self):
        self.app.config['LOCAL_QQ'] = True
        self.assertEqual(self.client.get('/api/health', environ_overrides={'REMOTE_ADDR': '192.0.2.10'}).status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_upload_limits_quota_and_job_capacity(self):
        self.assertEqual(self.submit([('f%d.lrc' % i, b'x') for i in range(101)], ['lrc']).status_code, 400)
        self.app.config['MAX_CONTENT_LENGTH'] = 100
        self.assertEqual(self.submit([('a.ncm', b'x'*200)], ['ncm']).status_code, 413)
        self.app.config['MAX_CONTENT_LENGTH'] = 200*1024*1024
        self.manager.quota = 1
        self.assertEqual(self.submit([('a.lrc', b'abc')], ['lrc']).status_code, 503)
        self.manager.quota = 1024**3
        self.manager.max_jobs = 0
        self.assertEqual(self.submit([('a.lrc', b'abc')], ['lrc']).status_code, 429)

    def test_cancel_cleans_outputs(self):
        response = self.submit([('cancel.ncm', fixture(b'ID3' + bytes(2000000)))], ['ncm'])
        job_id = response.get_json()['id']
        self.assertEqual(self.client.post(f'/api/jobs/{job_id}/cancel', headers=HEADERS).status_code, 200)
        job = self.wait(job_id)
        self.assertEqual(job['status'], 'cancelled')
        self.assertEqual(job['outputs'], [])
        self.assertEqual(self.client.get(f'/api/jobs/{job_id}/archive').status_code, 409)

    def test_timeout_and_ttl(self):
        self.manager.timeout = 0.001
        response = self.submit([('timeout.ncm', fixture(b'ID3' + bytes(2000000)))], ['ncm'])
        job = self.wait(response.get_json()['id'])
        self.assertEqual(job['status'], 'failed')
        self.assertTrue(any('时间限制' in line for line in job['logs']))
        record = self.manager.jobs[job['id']]
        record.finished = time.time() - 4000
        self.manager.cleanup()
        self.assertEqual(self.client.get('/api/jobs/' + job['id']).status_code, 404)
        self.assertFalse(record.root.exists())

    def test_headers_and_no_external_assets(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
        self.assertNotIn(b'https://', response.data)
        response.close()
        self.assertEqual(self.client.get('/api/jobs/unknown/files/../../request.json').status_code, 404)

    def test_flac_trailer_cleanup_preserves_audio_md5(self):
        source = Path(self.temp.name) / 'trailer.flac'
        target = Path(self.temp.name) / 'clean.flac'
        source.write_bytes(self.audio['flac'] + bytes(range(256)) * 2)
        original = _flac_streaminfo(source)
        _normalize_flac(source, target)
        self.assertEqual(_flac_streaminfo(target), original)
        check = subprocess.run([self.ffmpeg, '-v', 'error', '-xerror', '-i', str(target), '-f', 'null', '-'], capture_output=True)
        self.assertEqual(check.returncode, 0)
        self.assertFalse(check.stderr)

    def test_flac_audio_corruption_never_published(self):
        source = Path(self.temp.name) / 'corrupt.flac'
        target = Path(self.temp.name) / 'clean.flac'
        data = bytearray(self.audio['flac'])
        data[-100:-60] = bytes(40)
        source.write_bytes(data)
        with self.assertRaises((ValueError, RuntimeError)):
            _normalize_flac(source, target)
        self.assertFalse(target.exists())
        self.assertFalse(list(Path(self.temp.name).glob('.flac-*')))

    def test_cookie_result_never_exposes_credentials(self):
        self.app.config['LOCAL_QQ'] = True
        with patch('web_app.capabilities', return_value={'cookie': {'available': True}}), \
             patch('update_cookie.update_cookie', return_value={'ok': True, 'cookie': 'private-cookie', 'uin': '123', 'cookie_len': 14}):
            response = self.client.post('/api/cookie', headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()), {'ok', 'message'})
        self.assertNotIn(b'private-cookie', response.data)

    def test_missing_dependencies_report_unavailable(self):
        with patch('web_app.find_ffmpeg', return_value=None):
            caps = self.client.get('/api/capabilities').get_json()['tasks']
            self.assertFalse(caps['ogg']['available'])
            self.assertTrue(caps['ncm']['available'])
            self.assertEqual(self.submit([('a.ogg', b'abc')], ['ogg']).status_code, 400)

    def test_public_startup_requires_secrets(self):
        env = {key: value for key, value in os.environ.items() if key not in {'WEB_ACCESS_TOKEN', 'WEB_SECRET_KEY'}}
        result = subprocess.run([sys.executable, 'run_web.py', '--host', '0.0.0.0'], env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'WEB_ACCESS_TOKEN', result.stderr)
        result = subprocess.run([sys.executable, 'run_web.py', '--host', '0.0.0.0', '--local-qq'], env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)

    def test_deployment_secrets_generated_once(self):
        path = Path(self.temp.name) / '.env'
        command = [sys.executable, 'scripts/init_deploy.py', '--domain', 'music.example.com', '--output', str(path)]
        first = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(first.returncode, 0)
        values = dict(line.split('=', 1) for line in path.read_text().splitlines())
        self.assertGreaterEqual(len(values['WEB_ACCESS_TOKEN']), 24)
        self.assertGreaterEqual(len(values['WEB_SECRET_KEY']), 32)
        second = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(values, dict(line.split('=', 1) for line in path.read_text().splitlines()))
        self.assertNotIn(values['WEB_ACCESS_TOKEN'].encode(), first.stdout)

    def test_ogg_cannot_open_a_playlist(self):
        # Filename spoofing must not allow FFmpeg to follow uploaded playlists.
        playlist = b'#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:1/private\n#EXT-X-ENDLIST\n'
        response = self.submit([('playlist.ogg', playlist)], ['ogg'])
        job = self.wait(response.get_json()['id'])
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['outputs'], [])


if __name__ == '__main__':
    unittest.main()
