"""Mock-only backup boundary tests, no business DB or PostgreSQL process."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import sys
import psycopg

from django.test import SimpleTestCase
from .database_backup import perform_backup, fingerprints, BackupError, local_config

TOKEN='a'*32
PASSWORD='synthetic-password-never-log'


class Result:
    def __init__(self,rows):self.rows=rows
    def __iter__(self):return iter(self.rows)
    def fetchone(self):return self.rows[0]


class Cursor:
    def __init__(self,connection):self.connection=connection;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query):
        text=query.as_string();self.connection.queries.append(text)
        self.rows=sorted([(row,) for row in self.connection.data],key=lambda r:r[0].encode())
    def fetchmany(self,size):
        rows,self.rows=self.rows[:size],self.rows[size:];return rows


class Connection:
    def __init__(self,data=None,create_error=False,drop_error=False,unsupported=False):
        self.data=data or ['{"id": 1, "value": "synthetic"}','{"id": 2, "value": null}']
        self.create_error=create_error;self.drop_error=drop_error;self.unsupported=unsupported
        self.queries=[];self.closed=False
    def cursor(self,**kwargs):return Cursor(self)
    def execute(self,query):
        text=query if isinstance(query,str) else query.as_string();self.queries.append(text)
        if text.startswith('CREATE DATABASE') and self.create_error:
            if self.create_error=='unknown':raise RuntimeError(PASSWORD)
            raise psycopg.errors.DuplicateDatabase('controlled duplicate')
        if text.startswith('DROP DATABASE') and self.drop_error:raise RuntimeError(PASSWORD)
        if text=='SHOW server_version_num':return Result([(170011,)])
        if text=='SELECT pg_export_snapshot()':return Result([('synthetic-snapshot',)])
        if text.startswith('SELECT EXISTS'):return Result([(self.unsupported,)])
        if text.startswith('SELECT c.relname'):return Result([('controlled_table',)])
        return Result([])
    def close(self):self.closed=True


class DatabaseBackupTests(SimpleTestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.local=self.root/'.local';self.local.mkdir(mode=0o700)
        self.config=dict(engine='postgresql',name='shophot',user='shophot',password=PASSWORD,host='127.0.0.1',port='55432')
        self.file=self.local/'database.json';self.file.write_text(json.dumps(self.config));self.file.chmod(0o600)
        self.source=Connection();self.admin=Connection();self.target=Connection()
        self.connections=[];self.commands=[]
    def connect(self,**kwargs):
        self.connections.append(kwargs)
        return self.source if kwargs['dbname']=='shophot' else self.admin if kwargs['dbname']=='postgres' else self.target
    def runner(self,command,**kwargs):
        self.commands.append((command,kwargs))
        if command[0].endswith('pg_dump'):
            self.assertFalse(self.source.closed)
            kwargs['stdout'].write(b'PGDMP-controlled-custom-fixture')
        else:self.assertTrue(kwargs['stdin'].read().startswith(b'PGDMP'))
        return SimpleNamespace(returncode=0)
    def run_backup(self,**changes):
        with patch.dict(os.environ,{},clear=True):
            return perform_backup(self.root,connect=changes.get('connect',self.connect),runner=changes.get('runner',self.runner),
                                  token_factory=lambda:TOKEN,clock=changes.get('clock',lambda:0))
    def test_success_snapshot_readonly_tools_private_archive_and_owned_cleanup(self):
        report=self.run_backup()
        self.assertEqual(report['status'],'verified');self.assertEqual(report['cleanup'],'removed')
        self.assertEqual((report['table_count'],report['row_count']),(1,2))
        archive=self.root/report['archive'];self.assertEqual(archive.stat().st_mode & 0o777,0o600)
        self.assertEqual(archive.parent.stat().st_mode & 0o777,0o700)
        self.assertIn('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY',self.source.queries)
        self.assertIn("SET LOCAL TimeZone = 'UTC'",self.source.queries)
        self.assertIn("SET LOCAL DateStyle = 'ISO, YMD'",self.source.queries)
        self.assertTrue(any('COLLATE "C"' in query for query in self.source.queries))
        dump,restore=self.commands
        self.assertIn('--snapshot=synthetic-snapshot',dump[0]);self.assertIn('--format=custom',dump[0])
        for flag in ('--single-transaction','--exit-on-error','--no-owner','--no-acl'):self.assertIn(flag,restore[0])
        self.assertNotIn('--create',restore[0])
        self.assertEqual(len([q for q in self.admin.queries if q.startswith('DROP DATABASE')]),1)
        self.assertTrue(all(PASSWORD not in arg for command,_ in self.commands for arg in command))
        self.assertNotIn(PASSWORD,json.dumps(report))
        for _,kwargs in self.commands:
            self.assertIs(kwargs['stderr'],subprocess.DEVNULL)
            self.assertNotIn('PGSERVICE',kwargs['env']);self.assertEqual(kwargs['env']['PGHOST'],'127.0.0.1')
            self.assertEqual(kwargs['timeout'],300)
    def test_invalid_or_overspecified_local_config_never_connects(self):
        for changes in ({'host':'db.example.test'},{'name':'other'},{'user':'admin'},{'port':'5432'},
                        {'engine':'sqlite'},{'options':'-c bad=true'}):
            self.file.write_text(json.dumps({**self.config,**changes}))
            report=self.run_backup();self.assertEqual(report['status'],'failed');self.assertEqual(self.connections,[])
            self.assertNotIn(PASSWORD,json.dumps(report))
    def test_open_config_and_symlink_paths_rejected_without_overwrite(self):
        self.file.chmod(0o644);self.assertEqual(self.run_backup()['status'],'failed')
        self.file.chmod(0o600)
        external=self.root/'external';external.mkdir()
        (self.local/'backups').symlink_to(external,target_is_directory=True)
        self.assertEqual(self.run_backup()['status'],'failed');self.assertEqual(list(external.iterdir()),[])
        self.assertEqual(self.connections,[])
    def test_archive_collision_and_symlink_are_never_overwritten(self):
        folder=self.local/'backups';folder.mkdir(mode=0o700)
        archive=folder/f'shophot-{TOKEN}.dump';archive.write_bytes(b'keep-existing')
        self.assertEqual(self.run_backup()['status'],'failed');self.assertEqual(archive.read_bytes(),b'keep-existing')
        archive.unlink();external=self.root/'outside';external.write_bytes(b'keep-outside');archive.symlink_to(external)
        self.assertEqual(self.run_backup()['status'],'failed');self.assertEqual(external.read_bytes(),b'keep-outside')
        self.assertEqual(self.connections,[])
    def test_external_libpq_environment_forbidden_before_connect(self):
        with patch.dict(os.environ,{'PGSERVICE':'redirect'},clear=True):
            report=perform_backup(self.root,connect=self.connect,runner=self.runner)
        self.assertEqual(report['status'],'failed');self.assertEqual(self.connections,[])
    def test_failed_or_timed_out_dump_removes_partial_archive_suppresses_stderr(self):
        for timeout in (False,True):
            def runner(command,**kwargs):
                kwargs['stdout'].write(b'partial')
                if timeout:raise subprocess.TimeoutExpired(command,300,stderr=PASSWORD)
                return SimpleNamespace(returncode=1)
            report=self.run_backup(runner=runner)
            self.assertEqual(report['backup'],'failed');self.assertIsNone(report['archive'])
            self.assertEqual(list((self.local/'backups').iterdir()),[])
            self.assertNotIn(PASSWORD,json.dumps(report));self.assertEqual(self.admin.queries,[])
    def test_create_collision_does_not_grant_cleanup_ownership(self):
        self.admin.create_error=True
        report=self.run_backup()
        self.assertEqual(report['backup'],'complete');self.assertEqual(report['verification'],'failed')
        self.assertEqual(report['cleanup'],'not_created')
        self.assertTrue((self.root/report['archive']).exists())
        self.assertFalse(any(q.startswith('DROP DATABASE') for q in self.admin.queries))
    def test_unconfirmed_create_never_drops_and_reports_possible_residual(self):
        self.admin.create_error='unknown'
        report=self.run_backup()
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['cleanup'],'creation_unconfirmed')
        self.assertEqual(report['verification'],'failed')
        self.assertFalse(any(q.startswith('DROP DATABASE') for q in self.admin.queries))
        self.assertTrue((self.root/report['archive']).exists())

    def test_restore_failure_preserves_complete_archive_and_cleans_only_created_database(self):
        def runner(command,**kwargs):
            if command[0].endswith('pg_restore'):raise RuntimeError(PASSWORD)
            return self.runner(command,**kwargs)
        report=self.run_backup(runner=runner)
        self.assertEqual(report['backup'],'complete');self.assertEqual(report['verification'],'failed')
        self.assertEqual(report['cleanup'],'removed');self.assertTrue((self.root/report['archive']).exists())
        drops=[q for q in self.admin.queries if q.startswith('DROP DATABASE')]
        self.assertEqual(drops,['DROP DATABASE "shophot_restore_verify_'+TOKEN+'"'])
        self.assertNotIn(PASSWORD,json.dumps(report))
    def test_changed_row_or_table_fails_verification_and_keeps_archive(self):
        self.target.data=['{"id": 1, "value": "changed"}']
        report=self.run_backup();self.assertEqual(report['status'],'failed')
        self.assertEqual(report['verification'],'failed');self.assertEqual(report['cleanup'],'removed')
        self.assertTrue((self.root/report['archive']).exists())
    def test_cleanup_failure_is_not_reported_as_accepted_backup(self):
        self.admin.drop_error=True
        report=self.run_backup();self.assertEqual(report['status'],'failed')
        self.assertEqual(report['cleanup'],'failed');self.assertEqual(report['error'],'cleanup')
        self.assertTrue((self.root/report['archive']).exists())
    def test_unsupported_scope_and_fingerprint_timeout_do_not_create_restore_db(self):
        self.source.unsupported=True
        report=self.run_backup();self.assertEqual(report['status'],'failed');self.assertEqual(self.admin.queries,[])
        self.source.unsupported=False
        times=iter([0,301,301]);report=self.run_backup(clock=lambda:next(times))
        self.assertEqual(report['status'],'failed');self.assertEqual(self.admin.queries,[])
    def test_sorted_fingerprint_ignores_order_and_retains_duplicates_and_changes(self):
        rows=['{"id":2}','{"id":1}','{"id":1}']
        first=fingerprints(Connection(rows),['table'],100,lambda:0)
        second=fingerprints(Connection(list(reversed(rows))),['table'],100,lambda:0)
        self.assertEqual(first,second);self.assertEqual(first['table'][0],3)
        self.assertNotEqual(first,fingerprints(Connection(rows[:-1]),['table'],100,lambda:0))
    def test_command_rejects_arbitrary_dsn_without_echoing_secret(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'scripts/backup_database.py','--dsn=postgres://'+PASSWORD],
                              cwd=root,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertNotIn(PASSWORD,result.stderr+result.stdout)
