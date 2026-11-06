import datetime as dt
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
import editorial
import ai_writer

FEED=b'''<?xml version="1.0"?><rss version="2.0"><channel><title>CoinDesk</title><item><title>Bitcoin security patch released for nodes</title><link>https://www.coindesk.com/markets/2026/11/06/bitcoin-patch</link><description>Source headline - verify primary evidence.</description><pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'''

class TestVersion03(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=(engine.STATE,engine.DBFILE,engine.SOURCES)
        engine.STATE=Path(self.temp.name)
        engine.DBFILE=engine.STATE/'stories.sqlite3'
        engine.SOURCES=engine.STATE/'sources.json'
        engine.SOURCES.write_text(json.dumps([{'name':'Sumcoin Core releases','url':'https://github.com/sumcoinlabs/sumcoin/releases.atom','kind':'release'},
                                                {'name':'CoinDesk headlines','url':'https://www.coindesk.com/arc/outboundfeeds/rss/','kind':'news'}]))
        engine.get_db().close()
    def tearDown(self):
        engine.STATE,engine.DBFILE,engine.SOURCES=self.original
        self.temp.cleanup()
    def record(self,title,kind='release',days=0):
        when=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=days)).isoformat()
        url='https://github.com/sumcoinlabs/sumcoin/releases/tag/v2.0.1'
        id='a'*32
        with engine.get_db() as c:
            c.execute("INSERT INTO stories (id,source,kind,title,url,summary,published,first_seen) VALUES (?,?,?,?,?,?,?,?)",(id,'Sumcoin Core releases',kind,title,url,'Official release feed item',when,when))
        return dict(engine.story_list()[0])
    def test_sources_and_rss_headline_only(self):
        self.assertEqual(len(engine.load_sources()),2)
        r=list(editorial.rss_entries(FEED,{'url':'https://www.coindesk.com/arc/outboundfeeds/rss/','name':'CoinDesk headlines'}))
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['kind'],'news')
        for raw in (FEED.replace(b'coindesk.com',b'evil.com'),FEED.replace(b'<rss',b'<!DOCTYPE foo><rss')):
            self.assertEqual(list(editorial.rss_entries(raw,{'url':'https://www.coindesk.com/arc/outboundfeeds/rss/','name':'CoinDesk headlines'})) if b'evil' in raw else 'unsafe', [] if b'evil' in raw else 'unsafe')
        with self.assertRaises(ValueError):list(editorial.rss_entries(FEED.replace(b'<rss',b'<!DOCTYPE foo><rss'),{'url':'https://www.coindesk.com/arc/outboundfeeds/rss/'}))
    def test_topic_priority_and_versions(self):
        item={'source':'Sumcoin Core releases','title':'Sumcoin Core v2.0.1 security release','kind':'release','published':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'new','manual':0}
        self.assertEqual(editorial.topic(item),'Sumcoin')
        self.assertGreaterEqual(editorial.priority(item),82)
        self.assertTrue(editorial.auto_eligible(item))
        b=dict(item,title='Sumcoin Core v2.0.1 patch notes')
        self.assertTrue(editorial.similar(item,b))
        old=dict(item,published='2023-11-01T00:00:00Z')
        self.assertFalse(editorial.auto_eligible(old))
        noise=dict(item,title='Update readme docs only')
        self.assertFalse(editorial.auto_eligible(noise))
        a=dict(item,id='1'*32,url='https://github.com/sumcoinlabs/sumcoin/releases/tag/v2.0.1')
        b=dict(b,id='2'*32,url='https://github.com/sumcoinlabs/sumcoin/releases/tag/v2.0.1-notes')
        groups=editorial.group_stories([a,b])
        self.assertEqual(len(groups),1)
        self.assertEqual(len(groups[0]['related_sources']),1)
    def test_artwork_and_preflight(self):
        s=self.record('Sumcoin Core v2.0.1 security release')
        art=engine.artwork_bytes(s['id'])
        self.assertTrue(art.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(struct.unpack('!II',art[16:24]),(1600,1200))
        self.assertLess(len(art),4*1024*1024)
        engine.draft_for(s['id'])
        p=engine.preview_article(s['id'])
        self.assertEqual(p['author'],'DigiByte Wallet')
        self.assertEqual(p['publication_date'],'Assigned at publication, not original source timestamp')
        self.assertIn('Disclose publisher affiliation with Sumcoin',p['warnings'])
        self.assertFalse(p['public_auto_publish'])
    def test_auto_queue_draft_and_free_budgets(self):
        s=self.record('Sumcoin Core v2.0.1 security release')
        engine.set_settings({'auto_draft':False})
        self.assertEqual(engine.auto_prepare_once(caller=lambda q:None)['status'],'disabled')
        engine.set_settings({'auto_draft':True})
        repeated='The release announcement describes a change to maintainers and other operators. It does not independently prove the implementation has been audited. Operators should review the source and any platform-specific upgrade instructions before acting. '
        body='## Overview\n\n'+repeated*4+'\n\n## Impact\n\n'+repeated*4
        def fake_caller(request):
            return {'choices':[{'message':{'content':json.dumps({'title':'Sumcoin Core v2.0.1 maintenance and security release','summary':'The latest Sumcoin Core update is covered through the official release listing, with scope and deployment claims awaiting independent editorial checks.', 'body':body,'verify':['Confirm tag is a final published release','Check user impact and supported platforms']})}}],
                   'usage':{'prompt_tokens':1200,'completion_tokens':1000}}
        def fake_fetch(api):return {'tag_name':'v2.0.1','name':'Sumcoin Core v2.0.1','body':'Security and maintenance release','published_at':s['published'],'draft':False,'prerelease':False}
        result=engine.auto_prepare_once(fetcher=fake_fetch,caller=fake_caller)
        self.assertEqual(result['status'],'prepared')
        self.assertEqual(engine.auto_prepare_once(fetcher=fake_fetch,caller=fake_caller)['status'],'no_eligible_story')
        draft=engine.get_draft(s['id'])
        self.assertTrue(draft['ai_generated'])
        self.assertIn('Publisher disclosure',draft['body'])
        usage=engine.ai_usage()
        self.assertEqual((usage['auto_used'],usage['daily_used'],usage['tokens_used']),(1,1,2200))
        self.assertIn('Sumcoin',draft['tags'])
        self.assertIn('Research &amp; Write',Path(__file__).resolve().parents[1].joinpath('dashboard.html').read_text())

if __name__=='__main__':unittest.main()
