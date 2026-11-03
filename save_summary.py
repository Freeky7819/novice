"""Validate repository_dispatch before changing any file; never print its body."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import yaml
from fetch import save, matches
from summarize import unique_object, validate, read_cache

ROOT = Path(__file__).resolve().parent
FIELDS = {'id', 'neutral', 'mine', 'topics', 'basis', 'model', 'created_at'}
BASES = {'article', 'public_part', 'excerpt', 'title'}


def validate_payload(payload, root=ROOT):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError('Invalid payload shape')
    id = payload['id']
    if not isinstance(id, str) or not re.fullmatch('[0-9a-f]{40}', id):
        raise ValueError('Invalid id')
    feed = json.loads((root/'data/feed.json').read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    item = next((i for i in feed['items'] if i['id'] == id), None)
    if item is None:
        raise ValueError('Unknown id')
    sources = yaml.safe_load((root/'config/sources.yaml').read_text(encoding='utf-8'))['sources']
    source = next((s for s in sources if s['id'] == item['source_id'] and s.get('enabled', True)), None)
    topics = yaml.safe_load((root/'config/topics.yaml').read_text(encoding='utf-8'))
    if not source or any(matches(w, item['title']+' '+item['excerpt']) for w in topics.get('exclude_keywords', [])):
        raise ValueError('Excluded article')
    result = validate(json.dumps({k: payload[k] for k in ('neutral', 'mine', 'topics')}, ensure_ascii=False), [t['id'] for t in topics['topics']])
    if not isinstance(payload['basis'], str) or payload['basis'] not in BASES:
        raise ValueError('Invalid basis')
    ai = yaml.safe_load((root/'config/ai.yaml').read_text(encoding='utf-8'))
    if payload['model'] != ai['models']['anthropic']:
        raise ValueError('Unexpected model')
    stamp = payload['created_at']
    if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', stamp):
        raise ValueError('Invalid timestamp')
    when = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if when > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Future timestamp')
    return id, {'status': 'ok', 'attempted_at': stamp, 'provider': 'anthropic',
                'model': payload['model'], 'basis': payload['basis'], 'result': result}


def apply_event(event, root=ROOT):
    if not isinstance(event, dict) or event.get('action') != 'povzetek':
        raise ValueError('Unexpected event')
    id, entry = validate_payload(event.get('client_payload'), root)
    path = root/'data/summaries.json'
    cache = read_cache(path)  # A corrupt cache must not be silently replaced.
    if cache.get(id, {}).get('status') == 'ok':
        # Idempotent replay; preserve the first valid result for this article.
        allowed = [t['id'] for t in yaml.safe_load((root/'config/topics.yaml').read_text(encoding='utf-8'))['topics']]
        validate(json.dumps(cache[id]['result'], ensure_ascii=False), allowed)
    else:
        cache[id] = entry
        save(path, cache)
    return id


def main():
    try:
        event_path = Path(os.environ['GITHUB_EVENT_PATH'])
        if event_path.stat().st_size > 1_000_000:
            raise ValueError('Event too large')
        event = json.loads(event_path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        id = apply_event(event)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write('article_id='+id+'\n')
        print('Povzetek preverjen.')
    except Exception:
        raise SystemExit('Neveljaven dogodek ali nedosegljivi podatki; brez shranjevanja.') from None


if __name__ == '__main__':
    main()
