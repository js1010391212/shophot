"""Local project PostgreSQL backup; no arbitrary DSN, target or data output."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

import psycopg
from psycopg import sql

PG_BIN = Path('/usr/local/opt/postgresql@17/bin')
TIMEOUT = 300


class BackupError(Exception):
    """Only a fixed stage code may cross the command/report boundary."""


def private_directory(path):
    try:
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError
    except (OSError, ValueError):
        raise BackupError('private_directory_invalid') from None


def local_config(root):
    try:
        path = root/'.local'/'database.json'
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 8192:
            raise ValueError
        data = json.loads(path.read_text())
        if set(data) != {'engine','name','user','password','host','port'}:
            raise ValueError
        if (data['engine'] != 'postgresql' or data['host'] != '127.0.0.1' or str(data['port']) != '55432'
                or data['name'] != 'shophot' or data['user'] != 'shophot'):
            raise ValueError
        password = data['password']
        if not isinstance(password, str) or not password or any(ord(c) < 32 or ord(c) == 127 for c in password):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise BackupError('local_configuration_invalid') from None
    return {'host':'127.0.0.1','port':55432,'user':'shophot','password':password}


def tool_environment(config, database, readonly=False):
    return {'LANG':'C','LC_ALL':'C','PGHOST':config['host'],'PGPORT':str(config['port']),
            'PGUSER':config['user'],'PGPASSWORD':config['password'],'PGDATABASE':database,
            'PGCONNECT_TIMEOUT':'10','PGCLIENTENCODING':'UTF8',
            'PGOPTIONS':'-c statement_timeout=120000 -c lock_timeout=5000'+
                        (' -c default_transaction_read_only=on' if readonly else '')}


def connect_local(connect, config, database):
    return connect(**config, dbname=database, autocommit=True, connect_timeout=10,
                   options='-c statement_timeout=120000 -c lock_timeout=5000')


def readonly_snapshot(connection):
    connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    connection.execute("SET LOCAL TimeZone = 'UTC'")
    connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
    connection.execute('SET LOCAL extra_float_digits = 3')
    if int(connection.execute('SHOW server_version_num').fetchone()[0]) // 10000 != 17:
        raise BackupError('postgresql_version_unsupported')


def supported_scope(connection):
    unsupported = connection.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname NOT IN "
        "('public','pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_temp_' "
        "AND nspname !~ '^pg_toast_temp_') OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
        "AND c.relkind IN ('p','f','m','v')) OR EXISTS (SELECT 1 FROM pg_catalog.pg_largeobject_metadata)"
    ).fetchone()[0]
    if unsupported:
        raise BackupError('unsupported_database_scope')


def tables(connection):
    return [row[0] for row in connection.execute(
        "SELECT c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname COLLATE \"C\"")]


def fingerprints(connection, names, deadline, clock):
    result = {}
    for index, name in enumerate(names):
        digest, count = hashlib.sha256(), 0
        query = sql.SQL('SELECT to_jsonb(r)::text FROM ONLY {} AS r ORDER BY to_jsonb(r)::text COLLATE "C"').format(sql.Identifier('public',name))
        with connection.cursor(name=f'backup_hash_{index}') as cursor:
            cursor.execute(query)
            while True:
                if clock() > deadline:
                    raise BackupError('fingerprint_timeout')
                batch = cursor.fetchmany(256)
                if not batch:
                    break
                for (text,) in batch:
                    encoded = text.encode('utf-8')
                    digest.update(len(encoded).to_bytes(8,'big'));digest.update(encoded)
                    count += 1
        result[name] = (count,digest.hexdigest())
    return result


def run_tool(runner, command, *, config, database, readonly=False, **streams):
    try:
        done = runner(command, env=tool_environment(config,database,readonly), timeout=TIMEOUT,
                      stderr=subprocess.DEVNULL, check=False, **streams)
        if done.returncode:
            raise BackupError('tool_failed')
    except BackupError:
        raise
    except Exception:
        raise BackupError('tool_failed_or_timeout') from None


def reserve_archive(root, token):
    path = root/'.local'/'backups'/f'shophot-{token}.dump'
    try:
        fd = os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        return path,os.fdopen(fd,'w+b')
    except OSError:
        raise BackupError('archive_collision_or_invalid') from None


def remove_owned_archive(path, archive):
    # A replaced path is never unlinked on behalf of this run.
    info, owned = path.lstat(),os.fstat(archive.fileno())
    if stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==(owned.st_dev,owned.st_ino):
        path.unlink()
    else:
        raise BackupError('archive_cleanup_failed')


def perform_backup(project_root, *, connect=psycopg.connect, runner=subprocess.run, clock=time.monotonic,
                   token_factory=lambda: uuid.uuid4().hex):
    started=clock()
    report={'status':'failed','archive':None,'backup':'failed','verification':'not_run','cleanup':'not_created',
            'table_count':None,'row_count':None,'archive_sha256':None,
            'created_at':datetime.now(timezone.utc).isoformat(),'error':None}
    source=admin=target=archive=None
    path=None;created=False;complete=False;stage='configuration'
    root=Path(project_root).resolve()
    try:
        # psycopg/libpq also reads environment; fail rather than inherit redirection.
        if any(key.startswith('PG') for key in os.environ):
            raise BackupError('external_pg_environment_forbidden')
        private_directory(root/'.local')
        config=local_config(root)
        private_directory(root/'.local'/'backups')
        stage='archive_allocation'
        token=token_factory()
        if not re.fullmatch(r'[0-9a-f]{32}',token):raise BackupError('invalid_run_identity')
        database='shophot_restore_verify_'+token
        path,archive=reserve_archive(root,token)
        report['archive']=str(path.relative_to(root))
        stage='source_snapshot'
        source=connect_local(connect,config,'shophot')
        readonly_snapshot(source)
        supported_scope(source)
        names=tables(source)
        for name in names:
            source.execute(sql.SQL('LOCK TABLE ONLY {} IN ACCESS SHARE MODE').format(sql.Identifier('public',name)))
        snapshot=source.execute('SELECT pg_export_snapshot()').fetchone()[0]
        expected=fingerprints(source,names,started+TIMEOUT,clock)
        stage='dump'
        run_tool(runner,[str(PG_BIN/'pg_dump'),'--format=custom','--no-owner','--no-acl','--snapshot='+snapshot],
                 config=config,database='shophot',readonly=True,stdout=archive)
        archive.flush();os.fsync(archive.fileno())
        if archive.tell()==0:raise BackupError('empty_archive')
        complete=True;report['backup']='complete'
        source.execute('ROLLBACK');source.close();source=None
        archive.seek(0);digest=hashlib.sha256()
        for chunk in iter(lambda:archive.read(1024*1024),b''):digest.update(chunk)
        report['archive_sha256']=digest.hexdigest()
        report['table_count']=len(expected);report['row_count']=sum(row[0] for row in expected.values())
        stage='create_isolated_database'
        admin=connect_local(connect,config,'postgres')
        report['cleanup']='creation_unconfirmed'
        try:
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(database)))
        except psycopg.errors.DuplicateDatabase:
            report['cleanup']='not_created'
            raise
        created=True;report['cleanup']='pending'
        stage='restore'
        archive.seek(0)
        run_tool(runner,[str(PG_BIN/'pg_restore'),'--dbname='+database,'--exit-on-error','--single-transaction','--no-owner','--no-acl'],
                 config=config,database=database,stdin=archive,stdout=subprocess.DEVNULL)
        stage='compare'
        target=connect_local(connect,config,database)
        readonly_snapshot(target)
        supported_scope(target)
        actual=fingerprints(target,tables(target),clock()+TIMEOUT,clock)
        if actual != expected:raise BackupError('restored_data_mismatch')
        target.execute('ROLLBACK');target.close();target=None
        report['verification']='passed';report['status']='verified'
    except Exception:
        report['error']=stage
        if complete:report['verification']='failed'
    finally:
        for connection in (source,target):
            if connection is not None:
                try:connection.close()
                except Exception:pass
        if created:
            try:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
                report['cleanup']='removed'
            except Exception:
                report['cleanup']='failed';report['status']='failed';report['error']='cleanup'
        if admin is not None:
            try:admin.close()
            except Exception:pass
        if archive is not None:
            if not complete:
                try:remove_owned_archive(path,archive);report['archive']=None
                except Exception:report['error']='archive_cleanup'
            try:archive.close()
            except Exception:report['status']='failed';report['error']='archive_close'
        report['elapsed_seconds']=round(max(0,clock()-started),3)
    return report
