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

    def test_acronyms_are_case_sensitive_and_phrases_are_not(self):
        for acronym in ('AI', 'LLM', 'NVIDIA'):
            self.assertTrue(fetch.matches(acronym, 'New ' + acronym + ' research'))
            self.assertFalse(fetch.matches(acronym, acronym.lower()))
        for word in ('language model', 'machine learning', 'neural network', 'chatbot'):
            self.assertTrue(fetch.matches(word, word.upper()))
        self.assertFalse(fetch.matches('AI', 'RAILWAY'))

    @patch('fetch.read_feed')
    def test_google_publisher_and_disabled_excerpt(self, mocked):
        xml=b'<rss version="2.0"><channel><title>Test</title><item><title>News</title><link>https://news.google.com/item</link><description>Other headlines AI NVIDIA</description><source url="https://www.reuters.com">Reuters</source></item></channel></rss>'
        mocked.return_value=(feedparser.parse(xml),'https://news.google.com/rss')
        items,status=fetch.collect({'id':'gnews-us','url':'https://news.google.com/rss','topics':['us'],'excerpt':False},datetime.now(timezone.utc),{'keywords':{'ai':['AI','NVIDIA']}})
        self.assertTrue(status['ok'])
        self.assertEqual(items[0]['excerpt'],'')
        self.assertEqual(items[0]['topics'],['us'])
        self.assertEqual(items[0]['publisher'],'Reuters')
        self.assertEqual(items[0]['publisher_domain'],'www.reuters.com')
        self.assertIsNone(items[0]['image'])
        items,_=fetch.collect({'id':'another-source','url':'https://example.com/rss','topics':['us'],'excerpt':False},datetime.now(timezone.utc),{})
        self.assertEqual(items[0]['excerpt'],'')

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
            (root/'config/sources.yaml').write_text(yaml.safe_dump({'sources':[{'id':'test','name':'Test','url':'https://example.com/rss','enabled':True,'topics':['znanost']},{'id':'disabled','name':'Disabled','url':'https://example.com/off','enabled':False}]}))
            (root/'config/topics.yaml').write_text(yaml.safe_dump({'topics':[{'id':'znanost','label':'Science'}]}))
            item={'id':'test-item','url':'https://example.com/a','title':'Survives','source_id':'test','published':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'topics':['znanost'],'excerpt':'Test'}
            old={**item,'id':'old','published':(datetime.now(timezone.utc)-timedelta(days=10)).isoformat().replace('+00:00','Z')}
            disabled={**item,'id':'off','source_id':'disabled'}
            fetch.save(root/'data/feed.json',{'generated_at':'original','items':[item,old,disabled]})
            with patch('fetch.ROOT',root): fetch.main()
            result=json.loads((root/'data/feed.json').read_text())
            for key,value in item.items():
                self.assertEqual(result['items'][0][key],value)
            self.assertIsNone(result['items'][0]['image'])
            self.assertEqual(result['items'][0]['image_attempts'],1)
            self.assertIsNotNone(result['items'][0]['image_tried_at'])
            self.assertFalse(json.loads((root/'data/status.json').read_text())['sources'][0]['ok'])
            with patch('fetch.ROOT',root): fetch.main()
            # Migration attempts OG once, including when the result is null.
            self.assertEqual(mocks[0].call_count,1)


class ImageTests(unittest.TestCase):
    def test_thumbnail_size_and_url_detection(self):
        for url in ('https://example.com/tmb/a.jpg','https://example.com/thumbnail/a.jpg','https://example.com/a-t.jpg','https://example.com/a-150x150.jpg','https://example.com/a-300x200.webp'):
            self.assertTrue(feedlib.is_thumbnail(url),url)
        self.assertFalse(feedlib.is_thumbnail('https://example.com/a-1200x800.jpg'))
        self.assertTrue(feedlib.feed_thumbnail({'media_content':[{'url':'/image.jpg','width':'399'}]},'https://example.com/image.jpg','https://example.com/'))
        self.assertFalse(feedlib.feed_thumbnail({'media_thumbnail':[{'url':'/image.jpg','width':'400'}]},'https://example.com/image.jpg','https://example.com/'))

    @patch('fetch.og_image')
    def test_thumbnail_upgrade_and_failure_fallback(self, og):
        now=datetime.now(timezone.utc)
        item={'source_id':'test','url':'https://example.com/story','image':'https://example.com/tmb/a.jpg','image_is_thumbnail':True}
        self.assertTrue(fetch.image_due(item,now))
        og.return_value=None
        fetch.enrich_image(item,now.isoformat())
        self.assertEqual(item['image'],'https://example.com/tmb/a.jpg')
        self.assertTrue(item['image_is_thumbnail'])
        self.assertFalse(fetch.image_due(item,now))
        self.assertTrue(fetch.image_due(item,now+timedelta(hours=24)))
        og.return_value='https://example.com/large.jpg'
        fetch.enrich_image(item,(now+timedelta(hours=24)).isoformat())
        self.assertEqual(item['image'],'https://example.com/large.jpg')
        self.assertFalse(item['image_is_thumbnail'])
        self.assertFalse(fetch.image_due(item,now+timedelta(days=3)))

    @patch('fetch.og_image',side_effect=httpx.TimeoutException('timeout'))
    def test_thumbnail_survives_og_timeout(self, og):
        item={'url':'https://example.com/story','image':'https://example.com/tmb/a.jpg','image_is_thumbnail':True}
        fetch.enrich_image(item,datetime.now(timezone.utc).isoformat())
        self.assertEqual(item['image'],'https://example.com/tmb/a.jpg')
        self.assertEqual(item['image_attempts'],1)

    def test_content_encoded_first_safe_non_tiny_image(self):
        xml=b'<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Images</title><item><title>Article</title><link>https://example.com/article</link><content:encoded><![CDATA[<img src="/tracking.png" width="1" height="1"><img src="javascript:alert(1)"><img src="/small.jpg" height="99px"><img src="/hero.jpg" width="100" height="200"><img src="/later.jpg">]]></content:encoded></item></channel></rss>'
        entry=feedparser.parse(xml).entries[0]
        self.assertEqual(feed_image(entry,'https://example.com/article'),'https://example.com/hero.jpg')
        entry['media_thumbnail']=[{'url':'/rss.jpg'}]
        self.assertEqual(feed_image(entry,'https://example.com/article'),'https://example.com/rss.jpg')
        self.assertEqual(feed_image({'content':[{'value':'<img src="/unknown-size.jpg">'}]},'https://example.com/article'),'https://example.com/unknown-size.jpg')

    def test_one_retry_after_24_hours_and_no_google_requests(self):
        now=datetime.now(timezone.utc)
        item={'source_id':'test','image':None}
        self.assertTrue(fetch.image_due(item,now))
        item.update(image_attempts=1,image_tried_at=(now-timedelta(hours=23,minutes=59)).isoformat())
        self.assertFalse(fetch.image_due(item,now))
        item['image_tried_at']=(now-timedelta(hours=24)).isoformat()
        self.assertTrue(fetch.image_due(item,now))
        item['image_attempts']=2
        self.assertFalse(fetch.image_due(item,now+timedelta(days=3)))
        self.assertFalse(fetch.image_due({'source_id':'gnews-us','image':None},now))
        self.assertFalse(fetch.image_due({'source_id':'test','image':'https://example.com/img'},now))

    @patch('feedlib.public_url')
    def test_larger_og_head_and_browser_agent(self, public):
        head=b'<head>'+b' '*150000+b'<meta property="og:image" content="/large-head.jpg"></head>'
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=head)))
        with patch('feedlib.httpx.Client',return_value=client) as factory:
            self.assertEqual(og_image('https://example.com/'),'https://example.com/large-head.jpg')
            self.assertIn('Mozilla/5.0',factory.call_args.kwargs['headers']['User-Agent'])

    @patch('feedlib.public_url')
    def test_og_stops_at_512_kib(self, public):
        head=b'<head>'+b' '*524288+b'<meta property="og:image" content="/too-late.jpg"></head>'
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=head)))
        with patch('feedlib.httpx.Client',return_value=client):
            self.assertIsNone(og_image('https://example.com/'))

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
