"""RSS helpers. Feed bodies and discovered URLs are untrusted data."""
import html
import ipaddress
import re
import socket
import time
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


def image_url(value, base):
    """Keep signed image queries intact; never accept scripts or local targets."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        url = urljoin(base, value.strip())
        canonical(url)
        p = urlsplit(url)
        if p.port not in (None, 80, 443) or p.hostname.lower().rstrip('.') == 'localhost' or p.hostname.lower().rstrip('.').endswith('.localhost'):
            return None
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                return None
        except ValueError:
            pass  # Named CDN hosts resolve in the browser.
        return url
    except (ValueError, TypeError):
        return None


def feed_image(entry, base):
    for candidate in entry.get('media_content', []):
        kind = candidate.get('type', '').lower()
        if candidate.get('medium', '').lower() == 'image' or kind.startswith('image/') or (not kind and candidate.get('medium', '') not in ('video', 'audio')):
            url = image_url(candidate.get('url'), base)
            if url:
                return url
    for candidate in entry.get('media_thumbnail', []):
        url = image_url(candidate.get('url'), base)
        if url:
            return url
    for candidate in entry.get('enclosures', []):
        if candidate.get('type', '').lower().startswith('image/'):
            url = image_url(candidate.get('href') or candidate.get('url'), base)
            if url:
                return url
    parser = ContentImage(base)
    values = [part.get('value', '') for part in entry.get('content', [])]
    values.append(entry.get('content_encoded', ''))
    for value in values:
        parser.feed(value)
        if parser.image:
            return parser.image
    return None


def is_thumbnail(url, width=None):
    if width is not None:
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*', str(width), re.I)
        if match and float(match.group(1)) < 400:
            return True
    path = urlsplit(url or '').path.lower()
    if re.search(r'/tmb/|/thumb|[-_]t\.(?:jpe?g|png|webp)$', path):
        return True
    sizes = re.search(r'[-_](\d+)x(\d+)(?=\.|/|$)', path)
    return bool(sizes and int(sizes.group(1)) < 400)


def feed_thumbnail(entry, url, base):
    if is_thumbnail(url):
        return True
    for key in ('media_content', 'media_thumbnail'):
        for candidate in entry.get(key, []):
            if image_url(candidate.get('url'), base) == url and is_thumbnail(url, candidate.get('width')):
                return True
    return False


class ContentImage(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.image = None

    def handle_starttag(self, tag, attrs):
        if tag != 'img' or self.image:
            return
        a = dict(attrs)
        for dimension in ('width', 'height'):
            match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*', a.get(dimension) or '', re.I)
            if match and float(match.group(1)) < 100:
                return
        self.image = image_url(a.get('src'), self.base)


class OpenGraph(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == 'meta' and (a.get('property') or a.get('name') or '').lower() == 'og:image' and a.get('content'):
            self.images.append(a['content'])


def og_image(url):
    """One streamed GET (plus redirects), only HTML head, no article extraction.

    Read at most 512 KiB and stop at </head> or <body>.
    """
    deadline = time.monotonic() + 5
    agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    with httpx.Client(timeout=5, headers={'User-Agent': agent}, trust_env=False) as client:
        for _ in range(6):
            public_url(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            with client.stream('GET', url, timeout=remaining) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                if 'html' not in response.headers.get('content-type', '').lower():
                    return None
                body = bytearray()
                end = None
                for chunk in response.iter_bytes(chunk_size=4096):
                    if time.monotonic() > deadline:
                        return None
                    body.extend(chunk[:524288 - len(body)])
                    # Search only the head. Do not parse body metadata.
                    end = re.search(br'</head\s*>|<body\b', body, re.IGNORECASE)
                    if end or len(body) >= 524288:
                        break
                head = bytes(body[:end.start()] if end else body)
                parser = OpenGraph()
                parser.feed(head.decode('utf-8', errors='replace'))
                for candidate in parser.images:
                    result = image_url(candidate, str(response.url))
                    if result:
                        return result
                return None
    return None
