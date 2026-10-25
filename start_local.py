"""Interactive launcher: optional provider key read without echo or file writes."""
from getpass import getpass
import os
from pathlib import Path
import runpy
import yaml

root = Path(__file__).resolve().parent
config = yaml.safe_load((root/'config/ai.yaml').read_text(encoding='utf-8'))
provider = os.environ.get('AI_PROVIDER') or config['provider']
key_name = {'anthropic':'ANTHROPIC_API_KEY', 'openai':'OPENAI_API_KEY'}.get(provider)
if key_name and not os.environ.get(key_name):
    key = getpass('API ključ za nove povzetke (Enter = samo shranjeni povzetki): ')
    if key:
        os.environ[key_name] = key
    key = None
runpy.run_path(str(Path(__file__).resolve().parent/'server.py'), run_name='__main__')
