"""F1: RSS/Atom -> public JSON. No AI, article scraping, or clustering."""
import calendar
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from feedlib import canonical, clean, read_feed, discover

ROOT = Path(__file__).resolve().parent


def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return default


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)


def matches(word, text):
    return re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.IGNORECASE) is not None


def error_message(error):
    if isinstance(error, httpx.HTTPStatusError):
        return f'HTTP {error.response.status_code}'
    if isinstance(error, httpx.TimeoutException):
        return 'Čas za odgovor je potekel'
    return type(error).__name__


def collect(source, now, config):
    items = []
    try:
        try:
            parsed, final_url = read_feed(source['url'])
        except Exception:
            host = urlsplit(source['url'])
            found_url, _ = discover(f'{host.scheme}://{host.netloc}/')
            parsed, final_url = read_feed(found_url)
        undated = 0
        for entry in parsed.entries:
            try:
                url = canonical(entry.get('link', ''))
                title = clean(entry.get('title', ''), 500)
                if not title:
                    continue
                excerpt = clean(entry.get('summary', entry.get('description', '')))
                if any(matches(w, title + ' ' + excerpt) for w in config.get('exclude_keywords', [])):
                    continue
                date = entry.get('published_parsed') or entry.get('updated_parsed')
                published = datetime.fromtimestamp(calendar.timegm(date), timezone.utc) if date else now
                if published < now - timedelta(days=7) or published > now + timedelta(hours=6):
                    continue
                topics = set(source.get('topics', []))
                topics.update(t for t, words in config.get('keywords', {}).items() if any(matches(w, title + ' ' + excerpt) for w in words))
                undated += int(not date)
                items.append({'id': hashlib.sha1(url.encode()).hexdigest(), 'url': url, 'title': title,
                    'source_id': source['id'], 'published': published.isoformat().replace('+00:00', 'Z'),
                    'topics': sorted(topics), 'excerpt': excerpt})
            except (ValueError, OverflowError, TypeError):
                continue
        status = {'id': source['id'], 'ok': True, 'count': len(items), 'feed_url': final_url}
        if undated:
            status['warning'] = f'{undated} vnosov brez datuma; uporabljen je prvi čas zaznave'
        return items, status
    except Exception as error:
        return [], {'id': source['id'], 'ok': False, 'warning': error_message(error)}


def main():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec='seconds').replace('+00:00', 'Z')
    sources = yaml.safe_load((ROOT / 'config/sources.yaml').read_text(encoding='utf-8'))['sources']
    config = yaml.safe_load((ROOT / 'config/topics.yaml').read_text(encoding='utf-8'))
    allowed = {t['id'] for t in config['topics']}
    enabled = {s['id']: s for s in sources if s.get('enabled', True)}
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    previous = load(data / 'feed.json', {'items': []})
    cutoff = (now - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
    items = {i['id']: {k: i[k] for k in ('id', 'url', 'title', 'source_id', 'published', 'topics', 'excerpt')}
             for i in previous['items'] if i['source_id'] in enabled and i['published'] >= cutoff
             and not any(matches(w, i['title'] + ' ' + i['excerpt']) for w in config.get('exclude_keywords', []))}
    statuses = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for found, status in pool.map(lambda s: collect(s, now, config), enabled.values()):
            statuses.append(status)
            for item in found:
                old = items.get(item['id'])
                if old and item['published'] == now.isoformat().replace('+00:00', 'Z'):
                    item['published'] = old['published']
                items[item['id']] = item
    ordered = sorted(items.values(), key=lambda i: (i['published'], i['id']), reverse=True)[:500]
    for item in ordered:
        item['topics'] = sorted(set(item['topics']) & allowed)
    feed = {'generated_at': stamp, 'items': ordered}
    if previous.get('items') == ordered:
        feed['generated_at'] = previous.get('generated_at', stamp)
    save(data / 'feed.json', feed)
    save(data / 'config.json', {'topics': config['topics'], 'sources': [{k: s[k] for k in ('id', 'name', 'enabled')} for s in sources]})
    save(data / 'status.json', {'checked_at': stamp, 'sources': statuses})
    print(f'Novice: {len(ordered)} articles; {sum(s["ok"] for s in statuses)}/{len(statuses)} feeds OK')


if __name__ == '__main__':
    main()
