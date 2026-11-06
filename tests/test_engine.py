import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HERE=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('dgb_engine',HERE/'engine.py')
e=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e)

ATOM=b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Release candidate for DigiByte Core</title><link rel="alternate" href="https://github.com/DigiByte-Core/digibyte/releases/tag/v8.26"/><updated>2026-11-06T06:00:00Z</updated><summary>Review release notes; no claim of official launch.</summary></entry>
<entry><title>Bad entry</title><link rel="alternate" href="https://attacker.invalid/article"/></entry>
</feed>'''

class TestEngine(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        e.STATE=Path(self.tmp.name)
        e.DBFILE=e.STATE/'stories.sqlite3'
        self.old_sources=e.SOURCES
        e.SOURCES=e.STATE/'sources.json'
        e.SOURCES.write_text(json.dumps([{'name':'Core','url':'https://github.com/DigiByte-Core/digibyte/releases.atom','kind':'release'}]))
    def tearDown(self):
        e.SOURCES=self.old_sources
        self.tmp.cleanup()
    def test_deduplication_and_draft(self):
        self.assertEqual(e.scan_once(lambda _:ATOM)['new'],1)
        self.assertEqual(e.scan_once(lambda _:ATOM)['new'],0)
        st=e.story_list()[0]
        self.assertEqual(st['source'],'Core')
        self.assertNotIn('attacker.invalid',str(e.story_list()))
        d=e.draft_for(st['id'])
        self.assertIn('VERIFY BEFORE PUBLISHING',d['body'])
        self.assertIn('github.com',d['body'])
        self.assertEqual(e.story_list()[0]['status'],'drafted')
        self.assertEqual(e.get_draft(st['id'])['title'],d['title'])
        e.dismiss(st['id'])
        self.assertEqual(e.story_list()[0]['status'],'dismissed')
    def test_manual_domain_restrictions(self):
        self.assertTrue(e.allowed_manual('https://www.reddit.com/r/Digibyte/comments/abc'))
        for url in ['http://github.com/user/repo','https://evil.invalid/x','https://127.0.0.1/data','https://github.com.evil.invalid/x','https://github.com@evil.invalid/path']:
            self.assertFalse(e.allowed_manual(url),url)
        st=e.add_manual({'title':'Community reports a possible wallet issue','url':'https://x.com/someaccount/status/123','note':'Unverified'})
        self.assertTrue(e.story_list()[0]['manual'])
        self.assertEqual(st['kind'],'lead')
    def test_reject_doctype(self):
        with self.assertRaises(ValueError):list(e.atom_entries(b'<!DOCTYPE foo><feed/>','Core','release'))
    def test_http_guard(self):
        server=e.Server(('127.0.0.1',0),e.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            port=server.server_port
            with urlopen('http://127.0.0.1:%s/api/health'%port) as r:
                self.assertFalse(json.load(r)['publishing_enabled'])
            url='http://127.0.0.1:%s/api/manual'%port
            data=json.dumps({'title':'A verified source item','url':'https://github.com/test/test','note':'x'}).encode()
            bad=Request(url,data=data,headers={'Content-Type':'application/json','Origin':'http://evil.invalid','X-Newsroom-CSRF':e.CSRF})
            with self.assertRaises(HTTPError) as ex:urlopen(bad)
            self.assertEqual(ex.exception.code,403)
            good=Request(url,data=data,headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:%d'%port,'X-Newsroom-CSRF':e.CSRF})
            with urlopen(good) as r:self.assertEqual(r.status,201)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
