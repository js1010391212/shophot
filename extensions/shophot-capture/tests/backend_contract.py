"""Frozen real DOM evidence -> JS payload -> B1, with no database or server."""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]
REPOSITORY = EXTENSION.parents[1]
sys.path.insert(0, str(REPOSITORY))

from django.conf import settings
settings.configure(USE_TZ=True, SECRET_KEY='isolated-browser-contract-test', DATABASES={})

from market.browser_capture import parse_capture

node = shutil.which('node') or '/Users/qianpengfei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
program = '''
import fs from 'node:fs';
import {buildCapture} from './capture.mjs';
const records=JSON.parse(fs.readFileSync('./evidence/otto-readings.json','utf8'));
console.log(JSON.stringify(records.map(record=>({
  now:record.observed_at,
  payload:buildCapture(record.reading,new Date(record.observed_at),'f45b9333-1ac0-4d40-8363-bf699ab2a780')
}))));
'''
records = json.loads(subprocess.check_output([node, '--input-type=module', '-e', program], cwd=EXTENSION, text=True))
assert len(records) == 3
expected = [('S0R0I0F04SO6', '10.90'), ('S0R0I0F0C3SE', '10.90'), ('S08F10JEM769', '165.99')]
for record, (sku, price) in zip(records, expected, strict=True):
    payload = record['payload']
    result = parse_capture(json.dumps(payload, ensure_ascii=False).encode('utf8'), payload['url'],
                           now=datetime.fromisoformat(record['now']))
    assert result['sku_id'] == sku and result['price'] == price and result['currency'] == 'EUR'
    assert result['market_country'] is None
print('3 actual OTTO DOM readings accepted by B1 (frozen observation clock; no database access).')
