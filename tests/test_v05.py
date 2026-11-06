import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ai_writer, editorial, engine, traffic_report

class TestVersion05(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.prev=(engine.STATE,engine.DBFILE,engine.SOURCES)
  engine.STATE=Path(self.tmp.name);engine.DBFILE=engine.STATE/'stories.sqlite3';engine.SOURCES=engine.STATE/'sources.json'
  engine.SOURCES.write_text(json.dumps([{'name':'Sumcoin releases','url':'https://github.com/sumcoinlabs/sumcoin/releases.atom','kind':'release'}]))
  engine.get_db().close()
 def tearDown(self):
  engine.STATE,engine.DBFILE,engine.SOURCES=self.prev;self.tmp.cleanup()
 def test_clean_article_keeps_private_checks(self):
  para=('The maintained client addresses an issue described in the primary release announcement. '
        'This account makes no claim that the release has received an independent security audit. '
        'Operators should compare the listed code changes against the applicable deployment environment. ')
  input={'title':'Sumcoin Core security and reliability release','summary':'The developers describe improvements in the latest Sumcoin Core version, though an independent review of implementation is still needed.',
         'body':'## What changed\n\n'+para*4+'\n\n## What it means\n\n'+para*4,
         'verify':['Confirm release status and version','Check official deployment instructions']}
  evidence={'source':'Sumcoin releases','original_url':'https://github.com/sumcoinlabs/sumcoin/releases/tag/v0.21.0','newsroom_topic':'Sumcoin'}
  out=ai_writer.validate_ai_article(input,evidence)
  self.assertTrue(out['body'].endswith('](https://github.com/sumcoinlabs/sumcoin/releases/tag/v0.21.0)'))
  self.assertNotIn('Human checks still required',out['body'])
  self.assertEqual(out['verification'],input['verify'])
  input['body']=input['body']+'\n\n**EDITORIAL WORKING DRAFT**'
  with self.assertRaisesRegex(ai_writer.ResearchError,'editorial instructions'):
   ai_writer.validate_ai_article(input,evidence)
 def test_legacy_ai_draft_notes_not_embedded(self):
  d={'ai_generated':True,'body':'**EDITORIAL WORKING DRAFT — VERIFY BEFORE PUBLISHING.**\n\n## Story\n\nFactual reporting body.\n\n## Source and verification\n\nOriginal source: [Sumcoin](https://github.com/sumcoinlabs/sumcoin/releases/tag/v1)\n\n**Human checks still required:**\n\n- Check release tag\n- Confirm details\n\nThis is an AI-assisted draft.'}
  result=engine.normalized_draft(d)
  self.assertIn('Factual reporting body',result['body'])
  self.assertNotIn('EDITORIAL WORKING DRAFT',result['body'])
  self.assertEqual(result['verification'],['Check release tag','Confirm details'])
  self.assertEqual(d['body'].startswith('**EDITORIAL WORKING DRAFT'),True)
  self.assertTrue(result['review_required'])
 def test_no_auto_beta(self):
  now=dt.datetime.now(dt.timezone.utc).isoformat()
  base={'title':'Sumcoin Core v0.21.0 security release','kind':'release','source':'Sumcoin releases','published':now,'status':'new','manual':0}
  self.assertTrue(editorial.auto_eligible(base))
  self.assertFalse(editorial.auto_eligible(dict(base,title='Solana Agave v4.5.0-beta.0 testnet release')))
  self.assertFalse(editorial.auto_eligible(dict(base,title='Sumcoin Core v0.21.0-rc1 preview')))
 def test_failed_request_reserves_budget(self):
  now=dt.datetime.now(dt.timezone.utc).isoformat();sid='b'*32
  with engine.get_db() as c:
   c.execute('INSERT INTO stories (id,source,kind,title,url,summary,published,first_seen) VALUES (?,?,?,?,?,?,?,?)',
             (sid,'Sumcoin releases','release','Sumcoin Core v0.21.0 security release','https://github.com/sumcoinlabs/sumcoin/releases/tag/v0.21.0','Security update',now,now))
  with self.assertRaisesRegex(ai_writer.ResearchError,'simulated'):
   engine.research_story(sid,fetcher=lambda url:{},caller=lambda data:(_ for _ in ()).throw(ai_writer.ResearchError('simulated outage')))
  u=engine.ai_usage(sid)
  self.assertEqual(u['tokens_used'],0)
  self.assertEqual(u['tokens_committed'],10000)
  self.assertEqual(u['unverified_attempts'],1)
  self.assertFalse(u['billing_guarantee'])
 def test_analytics_aggregator_anonymizes(self):
  today=dt.datetime.now(dt.timezone.utc).date()
  day=today.strftime('%d/%b/%Y')
  lines=[
   '203.0.113.2 - - ['+day+':14:03:00 +0000] "GET /news/test-news.html HTTP/1.1" 200 2200 "-" "Mozilla/5.0"',
   '203.0.113.4 - - ['+day+':14:04:00 +0000] "GET /news/test-news.html?utm=x HTTP/1.1" 200 200 "-" "Mozilla/5.0"',
   '203.0.113.5 - - ['+day+':14:05:00 +0000] "GET /news/test-news.html HTTP/1.1" 200 200 "-" "Googlebot"',
   '203.0.113.5 - - ['+day+':14:05:00 +0000] "GET /news/test-news.html HTTP/1.1" 404 200 "-" "Mozilla/5.0"',
   '203.0.113.5 - - ['+day+':14:05:00 +0000] "GET /faucet/ HTTP/1.1" 200 200 "-" "Mozilla/5.0"',
  ]
  stats=traffic_report.counts_for_lines(lines,today,30)
  self.assertEqual(stats['/news/test-news.html'],2)
  path=engine.STATE/'access.log';path.write_text('\n'.join(lines))
  agg=traffic_report.report([path]);self.assertEqual(agg['views'],2)
  self.assertNotIn('203.0.113.',json.dumps(agg))
  self.assertNotIn('Mozilla',json.dumps(agg))
  self.assertEqual(engine.analytics_report()['configured'],False)
  (engine.STATE/'traffic-aggregate.json').write_text(json.dumps(agg))
  self.assertEqual(engine.analytics_report()['views'],2)
 def test_dashboard_contains_private_checklist_and_real_analytics(self):
  page=(Path(__file__).resolve().parents[1]/'dashboard.html').read_text()
  for term in ('Private fact-check checklist','/api/analytics','/api/publications','tokens_committed','Article traffic'):
   self.assertIn(term,page)
  self.assertTrue(engine.published_inventory.__doc__)

if __name__=='__main__':unittest.main()
