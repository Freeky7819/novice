"""Read only public article text. Never retain HTML/text in files or logs."""
import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from feedlib import public_url

AGENT = 'Novice/2.1 (personal news reader)'
MAX_HTML = 1_000_000
MAX_TEXT = 12_000


def limited_get(client, url, deadline, limit):
    public_url(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    with client.stream('GET', url, timeout=min(15, remaining)) as response:
        if response.is_redirect:
            return response.status_code, dict(response.headers), b''
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=4096):
            if time.monotonic() > deadline:
                raise TimeoutError()
            body.extend(chunk)
            if len(body) > limit:
                raise ValueError('Response too large')
        return response.status_code, dict(response.headers), bytes(body)


def robots_allowed(client, url, deadline):
    p = urlsplit(url)
    robots_url = f'{p.scheme}://{p.netloc}/robots.txt'
    for _ in range(3):
        status, headers, body = limited_get(client, robots_url, deadline, 65536)
        if 300 <= status < 400 and headers.get('location'):
            robots_url = urljoin(robots_url, headers['location'])
            continue
        if status in (404, 410):
            return True
        if status != 200 or 'html' in headers.get('content-type', '').lower():
            return False
        parser = RobotFileParser()
        parser.parse(body.decode('utf-8', errors='replace').splitlines())
        # Do not accelerate past a site's crawl-delay in a short request.
        delay = parser.crawl_delay('Novice')
        return parser.can_fetch('Novice', url) and not delay and not parser.request_rate('Novice')
    return False


def read_article(item):
    """Return (bounded text, basis). Network/robots/paywall failure uses excerpt."""
    fallback = ('', 'excerpt' if item.get('excerpt') else 'title')
    url = item['url']
    deadline = time.monotonic() + 20
    try:
        with httpx.Client(headers={'User-Agent': AGENT}, timeout=15,
                          follow_redirects=False, trust_env=False) as client:
            for _ in range(4):
                public_url(url)
                if not robots_allowed(client, url, deadline):
                    return fallback
                status, headers, body = limited_get(client, url, deadline, MAX_HTML)
                if 300 <= status < 400 and headers.get('location'):
                    url = urljoin(url, headers['location'])
                    continue
                if status != 200 or 'html' not in headers.get('content-type', '').lower():
                    return fallback
                # Treat explicit paywall metadata as public-part only. No bypass.
                paywall = bool(re.search(br'"isAccessibleForFree"\s*:\s*(?:false|"false")', body, re.I))
                text = trafilatura.extract(body, url=url, include_comments=False,
                        include_tables=False, include_links=False, favor_precision=True,
                        max_tree_size=50000) or ''
                text = text.strip()
                if not text:
                    return fallback
                basis = 'public_part' if paywall or len(text) < 800 else 'article'
                return text[:MAX_TEXT], basis
    except Exception:
        return fallback
    return fallback
