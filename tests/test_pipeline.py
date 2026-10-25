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
import feedlib
from feedlib import canonical, clean, public_url, Discovery, feed_image, image_url, og_image


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
    @patch('fetch.og_image',return_value=None)
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
            self.assertEqual(result['items'],[{**item,'image':None}])
            self.assertFalse(json.loads((root/'data/status.json').read_text())['sources'][0]['ok'])
            with patch('fetch.ROOT',root): fetch.main()
            # Migration attempts OG once, including when the result is null.
            self.assertEqual(mocks[0].call_count,1)


class ImageTests(unittest.TestCase):
    def test_real_rss_media_fields(self):
        xml=b'<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Images</title><item><title>Article</title><link>https://example.com/article</link><media:content url="https://cdn.example/hero.jpg" type="image/jpeg"/><media:thumbnail url="https://cdn.example/thumb.jpg"/><enclosure url="https://cdn.example/enclosure.jpg" type="image/jpeg" length="1200"/></item></channel></rss>'
        entry=feedparser.parse(xml).entries[0]
        self.assertEqual(feed_image(entry,'https://example.com/rss'),'https://cdn.example/hero.jpg')

    def test_media_thumbnail_and_enclosure_priority(self):
        entry={'media_content':[{'type':'video/mp4','url':'https://cdn.example/video.mp4'},{'type':'image/jpeg','url':'/hero.jpg'}],
               'media_thumbnail':[{'url':'/thumb.jpg'}],
               'enclosures':[{'type':'image/png','href':'/enclosed.png'}]}
        self.assertEqual(feed_image(entry,'https://example.com/news/'), 'https://example.com/hero.jpg')
        del entry['media_content']
        self.assertEqual(feed_image(entry,'https://example.com/news/'), 'https://example.com/thumb.jpg')
        del entry['media_thumbnail']
        self.assertEqual(feed_image(entry,'https://example.com/news/'), 'https://example.com/enclosed.png')

    def test_image_urls_preserve_signed_queries_and_reject_unsafe_values(self):
        self.assertEqual(image_url('//cdn.example/a?sig=x%2Fy&token=z','https://example.com/'), 'https://cdn.example/a?sig=x%2Fy&token=z')
        for url in (None,'','javascript:alert(1)','data:image/png;base64,a','http://127.0.0.1/a','http://[::1]/a','http://localhost/a','https://user:pass@example.com/a'):
            self.assertIsNone(image_url(url,'https://example.com/'))

    @patch('feedlib.public_url')
    def test_og_reads_only_head_and_resolves_relative_image(self, public):
        reads=[]
        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                reads.append('head')
                yield b'<html><head><meta content="/cover.jpg?a=1&amp;b=2" property="og:image"></head>'.ljust(4096,b' ')
                reads.append('body')
                yield b'<body>Article text must not be downloaded</body>'
        def handler(request):
            self.assertEqual(request.method,'GET')
            return httpx.Response(200,headers={'content-type':'text/html'},stream=Stream())
        client=httpx.Client(transport=httpx.MockTransport(handler))
        with patch('feedlib.httpx.Client',return_value=client):
            self.assertEqual(og_image('https://example.com/story'), 'https://example.com/cover.jpg?a=1&b=2')
        self.assertEqual(reads,['head'])

    @patch('feedlib.public_url')
    def test_body_metadata_is_ignored(self, public):
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=b'<head></head><body><meta property="og:image" content="https://example.com/body.jpg">')))
        with patch('feedlib.httpx.Client',return_value=client):
            self.assertIsNone(og_image('https://example.com/story'))

    @patch('feedlib.public_url')
    def test_empty_head_is_optional(self, public):
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=b'')))
        with patch('feedlib.httpx.Client',return_value=client):
            self.assertIsNone(og_image('https://example.com/story'))


if __name__=='__main__':
    unittest.main()
