"""Queue endpoint performance regression tests; no network, publishing or AI calls."""
import unittest
from unittest.mock import patch
import editorial
import engine

class DummyDB:
    def execute(self, sql):
        if 'SELECT story_id,content FROM drafts' in sql:
            return []
        raise AssertionError('Unexpected query: '+sql)
    def close(self):
        pass

class TestV062Queue(unittest.TestCase):
    def test_queue_source_is_bounded(self):
        with patch.object(engine,'story_list',return_value=[]) as read, patch.object(engine,'get_db',return_value=DummyDB()):
            self.assertEqual(engine.grouped_queue(),[])
            read.assert_called_once_with(400)

    def test_same_topic_duplicates_still_group(self):
        rows=[
          {'id':'a','source':'DigiByte releases','kind':'release','title':'DigiByte Core v9.26.7 release','published':'2026-11-12T00:00:00+00:00','first_seen':'2026-11-12T00:00:00+00:00','status':'new','manual':0,'url':'https://github.com/a'},
          {'id':'b','source':'DigiByte activity','kind':'release','title':'DigiByte Core v9.26.7 upgrade','published':'2026-11-12T00:00:00+00:00','first_seen':'2026-11-12T00:00:00+00:00','status':'new','manual':0,'url':'https://github.com/b'},
          {'id':'c','source':'Bitcoin Core releases','kind':'release','title':'Bitcoin Core v9.26.7 upgrade','published':'2026-11-12T00:00:00+00:00','first_seen':'2026-11-12T00:00:00+00:00','status':'new','manual':0,'url':'https://github.com/c'},
        ]
        out=editorial.group_stories(rows)
        self.assertEqual(len(out),2)
        digi=[x for x in out if x['topic']=='DigiByte'][0]
        self.assertEqual(len(digi['related_sources']),1)
        self.assertEqual(len([x for x in out if x['topic']=='Bitcoin']),1)

if __name__=='__main__': unittest.main()
