from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import unittest
import yaml
from fetch import save, load, public_config
from save_summary import validate_payload, apply_event
import test_summaries as batch
from prepare_worker import generated, ROOT


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = batch.SummaryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.id = 'a'*40
        save(self.root/'data/feed.json', {'items': [batch.article(self.id)]})
        save(self.root/'data/summaries.json', {})
        self.payload = {'id': self.id, **deepcopy(batch.VALID), 'basis': 'article',
                        'model': 'fake-haiku', 'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}

    def test_valid_event_saves_only_summary_and_replay_is_idempotent(self):
        feed = (self.root/'data/feed.json').read_bytes()
        self.assertEqual(apply_event({'action': 'povzetek', 'client_payload': self.payload}, self.root), self.id)
        cache = (self.root/'data/summaries.json').read_bytes()
        entry = load(self.root/'data/summaries.json', {})[self.id]
        self.assertEqual(entry['basis'], 'article')
        self.assertEqual(entry['result'], batch.VALID)
        apply_event({'action': 'povzetek', 'client_payload': self.payload}, self.root)
        self.assertEqual((self.root/'data/summaries.json').read_bytes(), cache)
        self.assertEqual((self.root/'data/feed.json').read_bytes(), feed)

    def test_invalid_payloads_do_not_modify_any_data(self):
        original = (self.root/'data/summaries.json').read_bytes()
        changes = [{'id': 'b'*40}, {'id': '../bad'}, {'url': 'https://evil.example'},
                   {'neutral': '<script>alert(1)</script>'}, {'mine': 'x'*601}, {'mine': ''},
                   {'neutral': 42}, {'topics': ['invented']}, {'topics': 'ai'}, {'topics': [None]},
                   {'basis': 'invented'}, {'basis': []}, {'model': 'other-model'},
                   {'created_at': 'yesterday'}, {'created_at': '2026-10-25T12:00:00'},
                   {'created_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat().replace('+00:00', 'Z')}]
        invalid = [None, [], {}, {k:v for k,v in self.payload.items() if k!='basis'}]
        invalid.extend({**self.payload, **change} for change in changes)
        for payload in invalid:
            with self.subTest(payload=repr(payload)[:60]):
                with self.assertRaises((ValueError, TypeError)):
                    apply_event({'action': 'povzetek', 'client_payload': payload}, self.root)
                self.assertEqual((self.root/'data/summaries.json').read_bytes(), original)

    def test_disabled_excluded_and_wrong_event_rejected(self):
        for item in [batch.article(self.id, source_id='disabled'), batch.article(self.id, title='sponsored offer')]:
            save(self.root/'data/feed.json', {'items': [item]})
            with self.assertRaises(ValueError): validate_payload(self.payload, self.root)
        with self.assertRaises(ValueError): apply_event({'action': 'other', 'client_payload': self.payload}, self.root)

    def test_corrupt_existing_cache_is_not_reset(self):
        path = self.root/'data/summaries.json'
        path.write_text('{bad')
        with self.assertRaises(ValueError): apply_event({'action': 'povzetek', 'client_payload': self.payload}, self.root)
        self.assertEqual(path.read_text(), '{bad')

    def test_worker_bundle_matches_python_prompt_yaml_and_style(self):
        self.assertTrue((ROOT/'worker/generated.js').read_text(encoding='utf-8') == generated(), 'Worker export must match config and Python instructions')

    def test_public_config_exports_only_explicit_source_domains_and_api(self):
        config = public_config([{'id':'test', 'name':'Test', 'url':'https://www.example.com/feed', 'enabled':True}],
                               {'topics':[{'id':'znanost'}]}, {'api_url':'https://test-only.workers.dev'})
        self.assertEqual(config['sources'][0]['domains'], ['example.com','www.example.com'])
        self.assertEqual(config['summary_api'], 'https://test-only.workers.dev')

    def test_all_pages_workflows_queue_and_dispatch_does_not_interpolate_payload_into_shell(self):
        for file in ('pages.yml','fetch.yml','shrani-povzetek.yml'):
            workflow = yaml.safe_load((ROOT/'.github/workflows'/file).read_text(encoding='utf-8'))
            self.assertEqual(workflow['concurrency'], {'group':'pages', 'queue':'max', 'cancel-in-progress':False})
        text = (ROOT/'.github/workflows/shrani-povzetek.yml').read_text(encoding='utf-8')
        self.assertNotIn('${{ github.event.client_payload', text)
        self.assertIn('git add -- data/summaries.json', text)
        self.assertIn('run: python save_summary.py', text)


if __name__ == '__main__':
    unittest.main()
