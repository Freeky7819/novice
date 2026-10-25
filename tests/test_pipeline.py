from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import feedparser
import httpx
import yaml
import fetch
from feedlib import canonical, clean, public_url, Discovery


class FeedTests(unittest.TestCase):
    def test_html_and_scripts_are_stripped(self):
        self.assertEqual(clean('<p>Hello</p><script>alert(1)</script><b>world &amp; everyone</b>'), 'Hello world & everyone')
        self.assertEqual(len(clean('x'*1000)),400)

    def test_links_and_tracking(self):
        self.assertEqual(canonical('https://example.com/a?utm_source=foo&x=1#fragment'), 'https://example.com/a?x=1')
        for url in ('javascript:alert(1)', 'file:///secret', 'https://user:pass@example.com'):
            with self.assertRaises(ValueError):
                canonical(url)

    def test_private_targets_rejected(self):
        for url in ('http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/', 'http://10.0.0.1/'):
            with self.assertRaises(ValueError):
                public_url(url)

    def test_keyword_boundaries(self):
        self.assertFalse(fetch.matches('AI', 'chair daily'))
        self.assertTrue(fetch.matches('AI', 'An AI model'))

    def test_autodiscovery_link_parser(self):
        parser=Discovery()
        parser.feed('<link rel="alternate" type="application/atom+xml" href="/atom.xml"><link rel="stylesheet" href="bad.css">')
        self.assertEqual(parser.links,['/atom.xml'])

    @patch('fetch.discover',side_effect=ValueError('broken'))
    @patch('fetch.read_feed',side_effect=ValueError('broken'))
    def test_broken_feed_is_isolated(self, mocked, discovery):
        items,status=fetch.collect({'id':'broken','url':'https://example.com'},datetime.now(timezone.utc),{})
        self.assertEqual(items,[])
        self.assertFalse(status['ok'])
        discovery.assert_called_once_with('https://example.com/')

    @patch('fetch.read_feed')
    def test_normalization_exclusions_and_dates(self, mocked):
        xml=b'<rss version="2.0"><channel><title>Test</title><item><title>New battery research</title><link>https://example.com/a?utm_source=x</link><description>&lt;p&gt;fusion energy&lt;/p&gt;</description></item><item><title>Sponsored AI</title><link>https://example.com/ad</link></item><item><title>Old story</title><link>https://example.com/old</link><pubDate>Mon, 01 Jan 2001 00:00:00 GMT</pubDate></item><item><title>Unsafe URL</title><link>javascript:alert(1)</link></item></channel></rss>'
        mocked.return_value=(feedparser.parse(xml),'https://example.com/rss')
        items,status=fetch.collect({'id':'test','url':'https://example.com/rss','topics':['znanost']},datetime.now(timezone.utc),{'keywords':{'energija':['battery']},'exclude_keywords':['sponsored']})
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['topics'],['energija','znanost'])
        self.assertEqual(items[0]['url'],'https://example.com/a')
        self.assertEqual(items[0]['id'],hashlib.sha1(b'https://example.com/a').hexdigest())

    def test_save_unchanged_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.json'
            fetch.save(path,{'value':1})
            before=path.stat().st_mtime_ns
            fetch.save(path,{'value':1})
            self.assertEqual(before,path.stat().st_mtime_ns)

    @patch('fetch.read_feed',side_effect=ValueError('broken'))
    @patch('fetch.discover',side_effect=ValueError('broken'))
    def test_previous_data_survives_failure_and_disabled_sources_are_removed(self,*mocks):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir();(root/'config').mkdir()
            (root/'config/sources.yaml').write_text(yaml.safe_dump({'sources':[{'id':'test','name':'Test','url':'https://example.com/rss','enabled':True},{'id':'disabled','name':'Disabled','url':'https://example.com/off','enabled':False}]}))
            (root/'config/topics.yaml').write_text(yaml.safe_dump({'topics':[{'id':'znanost','label':'Science'}]}))
            item={'id':'test-item','url':'https://example.com/a','title':'Survives','source_id':'test','published':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'topics':['znanost'],'excerpt':'Test'}
            old={**item,'id':'old','published':(datetime.now(timezone.utc)-timedelta(days=10)).isoformat().replace('+00:00','Z')}
            disabled={**item,'id':'off','source_id':'disabled'}
            fetch.save(root/'data/feed.json',{'generated_at':'original','items':[item,old,disabled]})
            with patch('fetch.ROOT',root): fetch.main()
            result=json.loads((root/'data/feed.json').read_text())
            self.assertEqual(result['items'],[item])
            self.assertFalse(json.loads((root/'data/status.json').read_text())['sources'][0]['ok'])


if __name__=='__main__':
    unittest.main()
