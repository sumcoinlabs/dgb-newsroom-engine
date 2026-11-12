"""Exact grouping semantics and bounded candidate work; entirely offline."""
import unittest
from unittest.mock import patch
import editorial

class TestV063Grouping(unittest.TestCase):
    def test_matches_original_grouping(self):
        stamp='2026-11-12T20:00:00+00:00'
        titles=(
           'DigiByte Core v9.26.7 release','DigiByte Core v9.26.7 upgrade',
           'DigiByte Core v9.26.8 release','Bitcoin Core v9.26.7 release',
           'Bitcoin Core v9.26.7 upgrade','SEC seeks comment on crypto custody',
           'Crypto custody consultation from SEC','Ethereum upgrade affects clients',
           'Ethereum clients discuss network upgrade','Solana and Coinbase listing update',
           'Solana Coinbase adoption update','DigiByte security improvements',
           'DigiByte wallet security improvements',
        )
        rows=[{'id':str(i),'title':title,'source':'Reporter '+str(i%3),
               'kind':'release' if i%4==0 else 'news',
               'status':'new','manual':0,'url':'https://example.com/'+str(i),
               'published':stamp,'first_seen':stamp}
               for i,title in enumerate(titles*3)]
        ordered=sorted(rows,key=lambda r:(r.get('status')=='drafted',editorial.priority(r),r.get('published') or ''),reverse=True)
        expected=[]
        for item in ordered:
            e=dict(item); e['topic']=editorial.topic(e)
            e['priority']=editorial.priority(e)
            e['related_sources']=[];e['archived']=editorial.archive(e)
            if not editorial.relevant(e):e['off_topic']=True
            target=next((g for g in expected if editorial.similar(e,g)),None)
            if target is None:expected.append(e)
            else:target['related_sources'].append({'id':e['id'],'title':e['title'],'url':e['url'],'source':e['source']})
        actual=editorial.group_stories(rows)
        brief=lambda a:[(g['id'],tuple(r['id'] for r in g['related_sources'])) for g in a]
        self.assertEqual(brief(actual),brief(expected))

    def test_do_not_use_quadratic_similar_calls(self):
        stamp='2026-11-12T20:00:00+00:00'
        rows=[{'id':str(i),'title':'Bitcoin ecosystem change %d on Bitcoin network' % i,
               'source':'Bitcoin updates','kind':'news','status':'new','manual':0,
               'url':'https://example.com/'+str(i),'published':stamp,'first_seen':stamp}
              for i in range(350)]
        with patch.object(editorial,'similar',side_effect=AssertionError('quadratic slow path called')):
            groups=editorial.group_stories(rows)
        self.assertTrue(groups)

if __name__=='__main__':unittest.main()
