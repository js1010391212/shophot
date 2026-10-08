#!/usr/bin/env python3
"""创建独立项目 PostgreSQL 集群；不修改系统数据库与登录启动项。"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import psycopg
from psycopg import sql

root = Path(__file__).resolve().parent.parent
local = root / '.local'
local.mkdir(mode=0o700, exist_ok=True)
local.chmod(0o700)
bin_dir = Path('/usr/local/opt/postgresql@17/bin')
if not (bin_dir / 'initdb').exists():
    raise SystemExit('请先安装 Homebrew postgresql@17')
config_path = local / 'database.json'
admin_path = local / 'database-admin.json'
if config_path.exists():
    raise SystemExit('项目数据库配置已存在；不会覆盖已有集群。')
if (local / 'postgres').exists():
    raise SystemExit('发现已有数据目录，请先核查；不会覆盖。')
password = secrets.token_urlsafe(32)
admin_password = secrets.token_urlsafe(32)
admin_path.write_text(json.dumps({'password': admin_password}))
admin_path.chmod(0o600)
pwfile = local / 'init-password'
pwfile.write_text(admin_password+'\n'); pwfile.chmod(0o600)
subprocess.run([str(bin_dir/'initdb'), '-D', str(local/'postgres'), '-U', 'shophot_admin',
                '--auth=scram-sha-256', '--pwfile='+str(pwfile), '--encoding=UTF8', '--locale=C'], check=True)
pwfile.unlink()
socket = local/'pgsocket';socket.mkdir(mode=0o700,exist_ok=True)
subprocess.run([str(bin_dir/'pg_ctl'), '-D', str(local/'postgres'), '-l', str(local/'postgres.log'),
                '-o', f'-h 127.0.0.1 -p 55432 -k {socket}', '-w', 'start'],check=True)
with psycopg.connect(host='127.0.0.1',port=55432,user='shophot_admin',password=admin_password,dbname='postgres',autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE ROLE shophot LOGIN CREATEDB PASSWORD {}').format(sql.Literal(password)))
    conn.execute('CREATE DATABASE shophot OWNER shophot')
config_path.write_text(json.dumps({'engine':'postgresql','name':'shophot','user':'shophot','password':password,'host':'127.0.0.1','port':'55432'},indent=2))
config_path.chmod(0o600)
print('独立 PostgreSQL 已启动，仅监听 127.0.0.1:55432；凭据保存在 .local，未输出。')
