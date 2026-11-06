import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('v02_engine',ROOT/'engine.py')
import sys
sys.path.insert(0,str(ROOT))
e=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e)
import ai_writer as a

ATOM=b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>DigiByte Core v9.26.7</title><link rel="alternate" href="https://github.com/DigiByte-Core/digibyte/releases/tag/v9.26.7"/><updated>2026-10-06T18:18:06Z</updated><summary>Follow-up fixes in the node and wallet.</summary></entry></feed>'''

class TestAI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        e.STATE=Path(self.tmp.name); e.DBFILE=e.STATE/'stories.sqlite3'
        self.orig=e.SOURCES;e.SOURCES=e.STATE/'sources.json'
        e.SOURCES.write_text(json.dumps([{'name':'DigiByte Core releases','url':'https://github.com/DigiByte-Core/digibyte/releases.atom','kind':'release'}]))
        e.scan_once(lambda _:ATOM)
        self.story=e.story_list()[0]
    def tearDown(self):
        e.SOURCES=self.orig
        self.tmp.cleanup()
    def test_official_github_link_resolution_only(self):
        src=a.source_repos(e.load_sources())
        self.assertEqual(a.github_api_for(self.story['url'],src),'https://api.github.com/repos/DigiByte-Core/digibyte/releases/tags/v9.26.7')
        for bad in ('https://github.com.evil.test/DigiByte-Core/digibyte/releases/tag/v9.26.7',
                    'https://github.com/Other/other/releases/tag/v9.26.7',
                    'https://127.0.0.1/private', 'http://github.com/DigiByte-Core/digibyte/releases/tag/v9.26.7',
                    'https://evil.com/path','https://github.com/DigiByte-Core/digibyte/../../settings'):
            self.assertIsNone(a.github_api_for(bad,src),bad)
    def test_official_release_evidence(self):
        def fake(url):
            self.assertTrue(url.startswith('https://api.github.com/repos/DigiByte-Core/digibyte/'))
            return {'tag_name':'v9.26.7','name':'DigiByte Core v9.26.7','body':'This fixes slow chain info requests.','draft':False,'prerelease':False,'published_at':'2026-10-06T18:18:06Z'}
        v=a.fetch_official(self.story,e.load_sources(),fetcher=fake)
        self.assertIn('slow chain info',v['release_notes'])
        self.assertFalse(v['prerelease'])
    def test_ai_story_persists_and_prevents_overwrite(self):
        repeated=('The update addresses some node reliability matters, as described by the referenced release entry. '
                  'The release notes do not establish any claims beyond the described changes. '
                  'Readers should review the developer notes to understand whether this update affects their installations. ')
        body='## Overview\n\n'+repeated*3+'\n\n## What changed\n\n'+repeated*3+'\n\n## What users should check\n\n'+repeated*2
        def caller(req):
            self.assertEqual(req['model'],a.MODEL)
            self.assertEqual(req['response_format']['type'],'json_object')
            return {'choices':[{'message':{'content':json.dumps({'title':'DigiByte Core v9.26.7 addresses reliability fixes',
              'summary':'A source-linked review of DigiByte Core v9.26.7 focuses on documented changes without claiming an independent security audit.',
              'body':body,'verify':['Check official release tag','Confirm upgrade guidance']})}}]}
        def getter(url):return {'tag_name':'v9.26.7','name':'Core release','body':'Fixes some node performance issues.','published_at':'2026-10-06T18:18:06Z'}
        first=e.draft_for(self.story['id'])
        self.assertIn('VERIFY BEFORE PUBLISHING',first['body'])
        draft=e.research_story(self.story['id'],fetcher=getter,caller=caller)
        self.assertIn('Source and verification',draft['body'])
        self.assertTrue(draft['ai_generated'])
        self.assertIn('github.com/DigiByte-Core',draft['body'])
        self.assertEqual(e.draft_for(self.story['id'])['body'],draft['body'])
        self.assertEqual(e.ai_usage(self.story['id'])['story_used'],1)
        self.assertEqual(e.ai_usage()['daily_used'],1)
        e.research_story(self.story['id'],fetcher=getter,caller=caller)
        with self.assertRaisesRegex(ValueError,'rewrite limit'):
            e.research_story(self.story['id'],fetcher=getter,caller=caller)
        self.assertEqual(e.ai_usage()['daily_used'],2)
    def test_invalid_content_is_not_stored(self):
        def caller(req):return {'choices':[{'message':{'content':'{"title":"small","summary":"small","body":"short","verify":[]}'}}]}
        with self.assertRaises(a.ResearchError):
            e.research_story(self.story['id'],fetcher=lambda _: {},caller=caller)
        self.assertIsNone(e.get_draft(self.story['id']))
        self.assertEqual(e.ai_usage()['daily_used'],1)
    def test_manual_link_not_fetched(self):
        story=dict(self.story,url='https://x.com/example/status/123',source='x.com',manual=1)
        evidence=a.fetch_official(story,e.load_sources(),fetcher=lambda _: self.fail('Must not scrape X'))
        self.assertIn('not automatically fetched',evidence['retrieval'])

if __name__=='__main__':unittest.main()
