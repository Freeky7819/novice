"""F1: RSS/Atom and optional image metadata -> JSON. No AI or body extraction."""
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
from feedlib import canonical, clean, read_feed, discover, feed_image, og_image, is_thumbnail, feed_thumbnail

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
    flags = 0 if word.isupper() else re.IGNORECASE
    return re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, flags) is not None


def topics_for(source, title, excerpt, config):
    topics = set(source.get('topics', []))
    topics.update(t for t, words in config.get('keywords', {}).items()
                  if any(matches(w, title + ' ' + excerpt) for w in words))
    return sorted(topics)


def image_due(item, now):
    if item['source_id'] == 'gnews-us' or (item.get('image') and not item.get('image_is_thumbnail', is_thumbnail(item['image']))):
        return False
    if item.get('image_attempts', 0) >= 2:
        return False
    tried = item.get('image_tried_at')
    if not tried:
        return True
    try:
        return now - datetime.fromisoformat(tried.replace('Z', '+00:00')) >= timedelta(hours=24)
    except (ValueError, TypeError):
        return False


def enrich_image(item, stamp):
    item['image_tried_at'] = stamp
    item['image_attempts'] = item.get('image_attempts', 0) + 1
    try:
        upgraded = og_image(item['url'])
        if upgraded:
            item['image'] = upgraded
            item['image_is_thumbnail'] = is_thumbnail(upgraded)
    except Exception:
        pass  # Keep the RSS thumbnail when OG fails.


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
                excerpt = clean(entry.get('summary', entry.get('description', ''))) if source.get('excerpt', True) else ''
                if any(matches(w, title + ' ' + excerpt) for w in config.get('exclude_keywords', [])):
                    continue
                date = entry.get('published_parsed') or entry.get('updated_parsed')
                published = datetime.fromtimestamp(calendar.timegm(date), timezone.utc) if date else now
                if published < now - timedelta(days=7) or published > now + timedelta(hours=6):
                    continue
                topics = topics_for(source, title, excerpt, config)
                publisher, publisher_domain = None, None
                if source['id'] == 'gnews-us':
                    media = entry.get('source', {})
                    publisher = clean(media.get('title', ''), 150) or None
                    try:
                        publisher_domain = urlsplit(canonical(media.get('href', ''))).hostname
                    except ValueError:
                        pass
                undated += int(not date)
                image = None if source['id'] == 'gnews-us' else feed_image(entry, url)
                items.append({'id': hashlib.sha1(url.encode()).hexdigest(), 'url': url, 'title': title,
                    'source_id': source['id'], 'published': published.isoformat().replace('+00:00', 'Z'),
                    'topics': topics, 'excerpt': excerpt,
                    'image': image, 'image_is_thumbnail': bool(image and feed_thumbnail(entry, image, url)),
                    'publisher': publisher, 'publisher_domain': publisher_domain})
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
    items = {i['id']: dict(i)
             for i in previous['items'] if i['source_id'] in enabled and i['published'] >= cutoff
             and not any(matches(w, i['title'] + ' ' + (i['excerpt'] if enabled[i['source_id']].get('excerpt', True) else '')) for w in config.get('exclude_keywords', []))}
    statuses = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for found, status in pool.map(lambda s: collect(s, now, config), enabled.values()):
            statuses.append(status)
            for item in found:
                old = items.get(item['id'])
                if old and item['published'] == now.isoformat().replace('+00:00', 'Z'):
                    item['published'] = old['published']
                if old and old.get('image') and (not item['image'] or
                        (item['image_is_thumbnail'] and not old.get('image_is_thumbnail', is_thumbnail(old['image'])))):
                    item['image'] = old.get('image')
                    item['image_is_thumbnail'] = old.get('image_is_thumbnail', is_thumbnail(old['image']))
                for key in ('image_tried_at', 'image_attempts'):
                    if old and key in old:
                        item[key] = old[key]
                items[item['id']] = item
    ordered = sorted(items.values(), key=lambda i: (i['published'], i['id']), reverse=True)[:500]
    # Backfill cached Google entries only from publisher/domain pairs confirmed
    # by <source> in this feed, never by guessing a domain from a title.
    publishers = {i['publisher']: i['publisher_domain'] for i in ordered
                  if i.get('publisher') and i.get('publisher_domain')}
    for item in ordered:
        source = enabled[item['source_id']]
        if not source.get('excerpt', True):
            item['excerpt'] = ''
        item['topics'] = sorted(set(topics_for(source, item['title'], item['excerpt'], config)) & allowed)
        item.setdefault('image', None)
        item.setdefault('image_is_thumbnail', is_thumbnail(item['image']))
        item.setdefault('publisher', None)
        item.setdefault('publisher_domain', None)
        if item['source_id'] == 'gnews-us':
            item['image'] = None
            item['image_is_thumbnail'] = False
            name = item['title'].rsplit(' - ', 1)[-1]
            if not item['publisher'] and name in publishers:
                item['publisher'], item['publisher_domain'] = name, publishers[name]
    needs_image = [i for i in ordered if image_due(i, now)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda item: enrich_image(item, stamp), needs_image))
    feed = {'generated_at': stamp, 'items': ordered}
    if previous.get('items') == ordered:
        feed['generated_at'] = previous.get('generated_at', stamp)
    save(data / 'feed.json', feed)
    save(data / 'config.json', {'topics': config['topics'], 'sources': [{k: s[k] for k in ('id', 'name', 'enabled')} for s in sources]})
    save(data / 'status.json', {'checked_at': stamp, 'sources': statuses})
    print(f'Novice: {len(ordered)} articles; {sum(s["ok"] for s in statuses)}/{len(statuses)} feeds OK')


if __name__ == '__main__':
    main()
