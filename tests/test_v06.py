"""All tests offline, no API calls, public writes, or paid AI invocations."""
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import newsroom_v06 as v06
import google_metrics_v06 as google
import artwork_v06 as art

class NewsroomV06Tests(unittest.TestCase):
    def test_health_does_not_call_network(self):
        a=[{'name':'Core','url':'https://github.com/a/b/releases.atom','kind':'release'},
           {'name':'Other','url':'https://www.example.com/feed','kind':'news'}]
        result=v06.health_summary(a,{'Core':{'status':'ok','count':3},
             'Other':{'status':'error','last_error':'HTTPError: 403'}})
        self.assertEqual(result['healthy'],1)
        self.assertEqual(result['attention'][0]['status'],'error')
        self.assertIn('Verify canonical RSS',result['attention'][0]['suggestion'])
    def test_health_inactive_release_not_auto_dropped(self):
        a=[{'name':'Quiet','url':'https://github.com/x/y/releases.atom','kind':'release'}]
        self.assertIn('may be normal',v06.health_summary(a,{'Quiet':{'status':'stale'}})['attention'][0]['suggestion'])
    def test_pre_release_warning(self):
        d={'title':'DigiByte Core stable release now available','summary':'A detailed report on a major change and its impact on node operators.',
           'body':'## Details\n\nThe original source describes the process. ' * 70+'\n\n[Original](https://github.com/example/x)'}
        s={'id':'a'*32,'url':'https://github.com/example/x','title':'v9.0.0-beta1','kind':'release'}
        issues=v06.draft_quality(d,s)
        self.assertTrue(any('pre-release' in x for x in issues['warnings']))
    def test_published_slug_blocks(self):
        d={'title':'A report about a software library','summary':'The example software library has published several changes, according to official sources.',
           'slug':'published-page','body':'Reported source [read](https://example.com)'}
        result=v06.draft_quality(d,{},[{'url':'https://www.digibytewallet.org/news/published-page.html','title':'X'}])
        self.assertTrue(result['blockers'])
        self.assertEqual(result['status'],'BLOCKED')
    def test_duplicate_publication_detected(self):
        p={'url':'https://www.digibytewallet.org/news/foo.html','published':'2026-11-05T00:00:00Z'}
        self.assertEqual(len(v06.publication_checks([p,p])['issues']),1)
    def test_google_config_not_connected(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(google,'OUTPUT',Path(root)/'nonexistent.json'):
                r=google.public_status()
                self.assertFalse(r['ga4']['connected'])
                self.assertFalse(r['gsc']['connected'])
                self.assertFalse(r['adsense']['connected'])
    def test_google_never_writes_secrets_to_report(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(google,'STATE',Path(root)),patch.object(google,'OUTPUT',Path(root)/'report.json'),patch.object(google,'CONFIG',Path(root)/'none.json'):
                google.collect()
                data=(Path(root)/'report.json').read_text()
                self.assertNotIn('refresh_token',data)
                self.assertFalse(json.loads(data)['adsense']['connected'])
    @unittest.skipUnless(art.available(),'Pillow optional; v0.5 fallback remains available')
    def test_original_artwork(self):
        raw=art.generate('DigiByte','An example DigiByte security release'+'a'*32)
        self.assertTrue(raw.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIn(b'DGBNewsroom-v0.6',raw[:2000])
        from PIL import Image
        im=Image.open(io.BytesIO(raw));self.assertEqual(im.size,(1600,1200))

if __name__=='__main__':unittest.main()
