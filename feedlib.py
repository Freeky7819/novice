"""RSS helpers. Feed bodies and discovered URLs are untrusted data."""
import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser
import httpx


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'br', 'div', 'li'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(value, limit=400):
    parser = Text()
    parser.feed(str(value))
    return re.sub(r'\s+', ' ', html.unescape(''.join(parser.parts))).strip()[:limit]


def canonical(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Neveljaven spletni naslov')
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', urlencode(query), ''))


def public_url(url):
    canonical(url)
    p = urlsplit(url)
    if p.port not in (None, 80, 443):
        raise ValueError('Dovoljena sta le spletna porta')
    addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Naslov ni javen')


def download(url):
    # Check each redirect, bound response size, and never log response bodies.
    with httpx.Client(timeout=25, headers={'User-Agent': 'Novice/1.0 RSS reader'}, trust_env=False) as client:
        for _ in range(6):
            public_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > 5_000_000:
                        raise ValueError('Odgovor je prevelik')
                return bytes(body), str(response.url)
    raise ValueError('Preveč preusmeritev')


def read_feed(url):
    body, final = download(url)
    parsed = feedparser.parse(body)
    if not parsed.version or not parsed.entries:
        raise ValueError('Ni veljaven RSS/Atom z vnosi')
    return parsed, final


class Discovery(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'link' and 'alternate' in a.get('rel', '').lower().split() and a.get('type', '').lower() in ('application/rss+xml', 'application/atom+xml'):
            if a.get('href'):
                self.links.append(a['href'])


def discover(url):
    body, final = download(url)
    parsed = feedparser.parse(body)
    if parsed.version and parsed.entries:
        return final, clean(parsed.feed.get('title', urlsplit(final).hostname), 100)
    parser = Discovery()
    parser.feed(body.decode('utf-8', errors='replace'))
    for href in parser.links[:12]:
        try:
            parsed, feed_url = read_feed(urljoin(final, href))
            return feed_url, clean(parsed.feed.get('title', urlsplit(feed_url).hostname), 100)
        except (httpx.HTTPError, ValueError, OSError):
            continue
    raise ValueError('Feeda nisem našel')
