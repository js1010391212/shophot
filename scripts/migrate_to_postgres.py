#!/usr/bin/env python3
"""服务暂停后运行：保留 SQLite，导入并逐项验证项目数据。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from collections import Counter
from datetime import datetime
root=Path(__file__).resolve().parent.parent
local=root/'.local'
if not (local/'database.json').exists():
    raise SystemExit('先初始化 PostgreSQL')
local.mkdir(mode=0o700,exist_ok=True)
tag=datetime.now().strftime('%Y%m%d-%H%M%S')
source=local/f'migration-{tag}-sqlite.json'
target=local/f'migration-{tag}-postgres.json'
base=[sys.executable,str(root/'manage.py')]
arguments=['dumpdata','--natural-foreign','--natural-primary','--exclude','contenttypes','--exclude','auth.permission']
subprocess.run(base+arguments+['--output',str(source)],env=dict(os.environ,SHOPHOT_DB_ENGINE='sqlite'),check=True,cwd=root)
source.chmod(0o600)
subprocess.run(base+['migrate','--noinput'],env=dict(os.environ,SHOPHOT_DB_ENGINE='postgresql'),check=True,cwd=root)
# 不覆盖已含业务数据的 PostgreSQL；适用于本项目首次切换。
import psycopg
cfg=json.loads((local/'database.json').read_text())
with psycopg.connect(dbname=cfg['name'],user=cfg['user'],password=cfg['password'],host=cfg['host'],port=cfg['port']) as conn:
    if conn.execute('SELECT count(*) FROM market_product').fetchone()[0] or conn.execute('SELECT count(*) FROM auth_user').fetchone()[0] or conn.execute('SELECT count(*) FROM market_storediscovery').fetchone()[0]:
        raise SystemExit('目标数据库含数据，停止以防覆盖。')
subprocess.run(base+['loaddata',str(source)],env=dict(os.environ,SHOPHOT_DB_ENGINE='postgresql'),check=True,cwd=root)
subprocess.run(base+arguments+['--output',str(target)],env=dict(os.environ,SHOPHOT_DB_ENGINE='postgresql'),check=True,cwd=root)
target.chmod(0o600)
normalize=lambda p: sorted(json.loads(p.read_text()),key=lambda x:(x['model'],str(x.get('pk','')),json.dumps(x['fields'],sort_keys=True)))
if normalize(source)!=normalize(target):
    raise SystemExit('迁移数据校验不一致，请核查 .local 导出；SQLite 原库保留。')
print('逐项数据校验一致。记录数：',dict(Counter(row['model'] for row in normalize(source))))
