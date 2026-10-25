"""Local-only HTTP app. No credentials, configuration, or private cache served."""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import re
from urllib.parse import unquote, urlsplit

from on_demand import ROOT, SummaryError, SummaryService

PUBLIC = {'/', '/index.html', '/app.js', '/style.css', '/sw.js', '/manifest.json',
          '/data/feed.json', '/data/config.json', '/data/status.json'}


def handler_for(service):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(service.root), **kwargs)

        def log_message(self, *args):
            pass  # Never log request bodies, prompts, provider errors, or keys.

        def allowed_host(self):
            port = self.server.server_port
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def reply(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def public_path(self):
            path = unquote(urlsplit(self.path).path)
            return path in PUBLIC or re.fullmatch(r'/icons/[a-zA-Z0-9_-]+\.(?:png|svg)', path)

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {'error': 'host_not_allowed'})
            if not self.public_path():
                return self.reply(404, {'error': 'not_found'})
            if urlsplit(self.path).path == '/':
                self.path = '/index.html'
            super().do_GET()

        def do_HEAD(self):
            if not self.allowed_host() or not self.public_path():
                return self.reply(404, {'error': 'not_found'})
            if urlsplit(self.path).path == '/':
                self.path = '/index.html'
            super().do_HEAD()

        def do_POST(self):
            origin = self.headers.get('Origin')
            expected = 'http://' + self.headers.get('Host', '')
            if not self.allowed_host() or (origin and origin != expected) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.reply(403, {'error': 'origin_not_allowed'})
            if self.path != '/api/summary':
                return self.reply(404, {'error': 'not_found'})
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                return self.reply(415, {'error': 'json_required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) != {'id'} or not isinstance(data['id'], str) or not re.fullmatch(r'[0-9a-f]{40}', data['id']):
                    raise ValueError()
            except (ValueError, TypeError):
                return self.reply(400, {'error': 'invalid_request'})
            try:
                self.reply(200, service.get(data['id']))
            except SummaryError as error:
                self.reply(error.status, {'error': error.code, 'message': error.message})
            except Exception:
                self.reply(503, {'error': 'unavailable', 'message': 'Povzemanje trenutno ni na voljo. Poskusi pozneje.'})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    service = SummaryService()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(service))
    print(f'Novice: http://127.0.0.1:{args.port}/ (lokalno, AI samo ob kliku)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
