import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from site_settings import public_downloads
from conversion_errors import conversion_problem


class DownloadTests(unittest.TestCase):
    def test_public_download_whitelist_and_invalid_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'download.json'
            with patch.dict(os.environ, {'SONGDOWN_DOWNLOAD_CONFIG':str(path)}):
                self.assertFalse(public_downloads()['available'])
                for url in ['javascript:alert(1)', 'http://example.com', 'https://user:pass@example.com', 'https://[bad', 'https://example.com/\n']:
                    path.write_text(json.dumps({'url':url, 'cookie':'PRIVATE'}), encoding='utf-8')
                    result = public_downloads()
                    self.assertFalse(result['available'], url)
                    self.assertEqual(result['url'], '')
                    self.assertNotIn('cookie', result)
                path.write_text(json.dumps({'url':'https://example.com/share', 'extraction_code':'abcd'}), encoding='utf-8')
                self.assertTrue(public_downloads()['available'])
                self.assertEqual(public_downloads()['extraction_code'], 'abcd')

    def test_error_categories_do_not_leak_raw_server_details(self):
        for message, code in [('unable to access process secret', 'QQ_PERMISSION_DENIED'),
                              ('no ekey secret', 'QQ_KEY_UNAVAILABLE'),
                              ('未找到 ffmpeg secret', 'SERVER_COMPONENT_MISSING'),
                              ('md5 mismatch secret', 'AUDIO_INTEGRITY_FAILED')]:
            result = conversion_problem([message], 'mflac')
            self.assertEqual(result['code'], code)
            self.assertNotIn('secret', str(result))
