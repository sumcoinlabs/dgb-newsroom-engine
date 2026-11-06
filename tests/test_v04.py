import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import editorial, engine, ai_writer

RSS=b'''<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Zcash blockchain security upgrade launches</title><link>https://decrypt.co/2099/zcash-security-upgrade</link><description>Reported upgrade details</description><pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'''
ATOM=b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Sumcoin Core v0.21.0 security release</title><link rel="alternate" href="https://github.com/sumcoinlabs/sumcoin/releases/tag/v0.21.0" />
<published>2026-11-06T12:00:00Z</published><summary>Important security update</summary></entry></feed>'''

class TestVersion04(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=(engine.STATE,engine.DBFILE,engine.SOURCES)
  engine.STATE=Path(self.temp.name);engine.DBFILE=engine.STATE/'stories.sqlite3';engine.SOURCES=engine.STATE/'sources.json'
  engine.SOURCES.write_text(json.dumps([
    {'name':'Sumcoin releases','url':'https://github.com/sumcoinlabs/sumcoin/releases.atom','kind':'release'},
    {'name':'Decrypt headlines','url':'https://decrypt.co/feed','kind':'news'}]))
  engine.get_db().close()
 def tearDown(self):
  engine.STATE,engine.DBFILE,engine.SOURCES=self.old;self.temp.cleanup()
 def test_classification_ignores_publisher_brand(self):
  src={'kind':'news','source':'Bitcoin Magazine headlines','title':'Thailand SEC complaint against exchange'}
  self.assertEqual(editorial.topic(src),'Crypto')
  self.assertFalse(editorial.relevant(src))
  src['title']='OpenAI Found 948 Linux Security Flaws'
  self.assertFalse(editorial.relevant(src))
  src['title']='Bitcoin Core receives major security update'
  self.assertEqual(editorial.topic(src),'Bitcoin')
  self.assertTrue(editorial.relevant(src))
 def test_archive_and_fresh_prioritization(self):
  now=dt.datetime.now(dt.timezone.utc)
  item={'kind':'release','status':'new','title':'Sumcoin Core v0.21.0 security upgrade','source':'Sumcoin releases','published':now.isoformat(),'manual':0}
  self.assertGreaterEqual(editorial.priority(item),76)
  self.assertTrue(editorial.auto_eligible(item))
  item['published']=(now-dt.timedelta(days=40)).isoformat()
  self.assertTrue(editorial.archive(item));self.assertFalse(editorial.auto_eligible(item))
  item['title']='docs: update readme security notice';item['published']=now.isoformat()
  self.assertFalse(editorial.auto_eligible(item))
 def test_news_and_atom_and_bad_hosts(self):
  r=list(editorial.rss_entries(RSS,{'name':'Decrypt headlines','url':'https://decrypt.co/feed','kind':'news'}))
  self.assertEqual(len(r),1);self.assertEqual(r[0]['kind'],'news')
  a=list(engine.atom_entries(ATOM,'Sumcoin releases','release'))
  self.assertEqual(len(a),1)
  self.assertEqual(list(editorial.rss_entries(RSS.replace(b'https://decrypt.co/2099/',b'https://evil.com/2099/'),{'name':'Decrypt','url':'https://decrypt.co/feed'})),[])
  with self.assertRaises(ValueError):list(editorial.rss_entries(RSS.replace(b'<rss',b'<!DOCTYPE html><rss'),{'name':'Decrypt','url':'https://decrypt.co/feed'}))
 def test_source_health_scan_and_database_preservation(self):
  results=engine.scan_once(fetcher=lambda url:ATOM if url.endswith('releases.atom') else RSS)
  self.assertEqual(results['new'],2)
  with engine.get_db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM stories').fetchone()[0],2)
   health=list(c.execute('SELECT status,count FROM source_health ORDER BY name'))
   self.assertEqual([(h['status'],h['count']) for h in health],[('ok',1),('ok',1)])
  results=engine.scan_once(fetcher=lambda url:ATOM if url.endswith('releases.atom') else (_ for _ in ()).throw(ValueError('feed unavailable')))
  self.assertEqual(results['new'],0);self.assertEqual(len(results['errors']),1)
  with engine.get_db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM stories').fetchone()[0],2)
   self.assertEqual(c.execute("SELECT status FROM source_health WHERE name='Decrypt headlines'").fetchone()[0],'error')
 def test_non_destructive_draft_review_and_disclosure_not_forced(self):
  engine.scan_once(fetcher=lambda url:ATOM if url.endswith('releases.atom') else RSS)
  story=[s for s in engine.story_list() if s['kind']=='release'][0]
  draft=engine.draft_for(story['id'])
  self.assertIn('VERIFY BEFORE PUBLISHING',draft['body'])
  self.assertFalse(any('Disclose publisher' in s for s in engine.preview_article(story['id'])['warnings']))
  self.assertNotIn('disclose that the publisher',ai_writer.SYSTEM)
  groups=engine.grouped_queue()
  self.assertTrue(any(g['id']==story['id'] for g in groups))
 def test_dashboard_has_research_queue_and_health(self):
  txt=(Path(__file__).resolve().parents[1]/'dashboard.html').read_text()
  for name in ('reviewcards','sourcepill','healthycount','search','autodraft','topic','storyart','preflight'):
   self.assertIn('id="'+name+'"',txt)
 def test_source_list_validation_accepts_expanded_config(self):
  engine.SOURCES=(Path(__file__).resolve().parents[1]/'sources.json')
  s=engine.load_sources()
  self.assertGreaterEqual(len(s),30)
  self.assertEqual(len(s),len(set(row['url'] for row in s)))

if __name__=='__main__':unittest.main()
