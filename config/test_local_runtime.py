"""Owned short-lived subprocesses and loopback listeners only: no PG or app DB."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import io
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase

RUNTIME=Path(__file__).with_name('local_runtime.py')
START=RUNTIME.parents[1]/'scripts'/'start.sh'


class LocalRuntimeTests(SimpleTestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project with spaces';self.root.mkdir()
        self.launchers=[];self.groups=set();self.listeners=[]
        self.addCleanup(self.clean)
        self.project(self.root)

    def project(self,root):
        (root/'config').mkdir();(root/'scripts').mkdir();(root/'.venv'/'bin').mkdir(parents=True)
        shutil.copyfile(RUNTIME,root/'config'/'local_runtime.py');shutil.copyfile(START,root/'scripts'/'start.sh')
        (root/'.venv'/'bin'/'python').symlink_to(sys.executable)
        (root/'scripts'/'start_postgres.sh').write_text('.venv/bin/python manage.py postgres\n')
        (root/'manage.py').write_text('''
import json, os, signal, socket, socketserver, subprocess, sys, time
from pathlib import Path
role=sys.argv[1]
if os.getenv('IGNORE_TERM_ROLE')==role:signal.signal(signal.SIGTERM,signal.SIG_IGN)
with Path('calls.jsonl').open('a') as file:
    file.write(json.dumps({'role':role,'pid':os.getpid()})+'\\n')
if os.getenv('HOLD_ROLE')==role:
    while not Path('release-helper').exists():time.sleep(.05)
if os.getenv('EXIT_EARLY_ROLE')==role:sys.exit(0)
if os.getenv('FAIL_ROLE')==role:sys.exit(7)
if role in ('postgres','migrate','check'):sys.exit(0)
if role=='collect_worker' and os.getenv('SPAWN_DESCENDANT'):
    child=subprocess.Popen([sys.executable,'-c',\"import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('descendant-ready').write_text(str(os.getpid()));time.sleep(8);Path('descendant-survived').write_text('alive');time.sleep(60)\"],close_fds=False)
    while not Path('descendant-ready').exists():time.sleep(.01)
if role=='runserver':
    if os.getenv('TAKE_PORT'):
        host,port=sys.argv[2].rsplit(':',1)
        competitor=socket.socket();competitor.bind((host,int(port)));competitor.listen()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):pass
    server=socketserver.TCPServer(tuple([sys.argv[2].rsplit(':',1)[0],int(sys.argv[2].rsplit(':',1)[1])]),Handler)
while True:time.sleep(.1)
''')

    def port(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));return probe.getsockname()[1]

    def calls(self,root=None):
        path=(root or self.root)/'calls.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        self.groups.update(row['pid'] for row in rows if row['role'] in ('collect_worker','runserver'))
        return rows

    def launch(self,root=None,bind=None,**env):
        root=root or self.root
        options=os.environ.copy();options.update(SHOPHOT_BIND=bind or '127.0.0.1:'+str(self.port()),**env)
        process=subprocess.Popen(['bash','scripts/start.sh'],cwd=root,env=options,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        self.launchers.append(process);return process

    def ready(self,process,root=None):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=self.calls(root)
            if any(row['role']=='collect_worker' for row in rows):return rows
            if process.poll() is not None: self.fail(process.communicate()[1].decode())
            time.sleep(.03)
        self.fail('isolated supervisor did not start worker')

    def gone(self,pid):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            try:os.kill(pid,0)
            except ProcessLookupError:return True
            time.sleep(.03)
        return False

    def clean(self):
        self.calls()
        for process in self.launchers:
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in self.launchers:
            try:process.communicate(timeout=7)
            except subprocess.TimeoutExpired:process.kill();process.communicate()
        for group in self.groups:
            try:os.killpg(group,signal.SIGTERM)
            except ProcessLookupError:pass
            except PermissionError:
                from .local_runtime import group_metadata_alive
                if group_metadata_alive(group) is not False:raise
        for listener in self.listeners:listener.close()

    def test_different_ports_same_root_start_only_one_migration_and_worker(self):
        first=self.launch();self.ready(first)
        second=self.launch();_,error=second.communicate(timeout=3)
        self.assertNotEqual(second.returncode,0);self.assertIn('已有启动进程',error.decode())
        rows=self.calls()
        self.assertEqual([row['role'] for row in rows].count('migrate'),1)
        self.assertEqual([row['role'] for row in rows].count('collect_worker'),1)
        self.assertIsNone(first.poll())

    def test_occupied_port_and_invalid_bind_reject_before_any_prep(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();self.listeners.append(listener)
        for bind in ('127.0.0.1:'+str(listener.getsockname()[1]),'not-an-ip:8000','127.0.0.1:0'):
            process=self.launch(bind=bind);_,error=process.communicate(timeout=3)
            self.assertNotEqual(process.returncode,0);self.assertTrue(error)
            self.assertEqual(self.calls(),[])

    def test_migration_check_and_web_failures_preserve_status_and_never_start_worker(self):
        for role in ('postgres','migrate','check','runserver'):
            with self.subTest(role=role):
                (self.root/'calls.jsonl').unlink(missing_ok=True)
                process=self.launch(FAIL_ROLE=role);process.communicate(timeout=4)
                self.assertEqual(process.returncode,7)
                roles=[row['role'] for row in self.calls()]
                self.assertNotIn('collect_worker',roles)
                if role=='migrate':self.assertNotIn('check',roles)
        (self.root/'calls.jsonl').unlink(missing_ok=True)
        process=self.launch(EXIT_EARLY_ROLE='runserver');process.communicate(timeout=4)
        self.assertNotEqual(process.returncode,0)
        self.assertNotIn('collect_worker',[row['role'] for row in self.calls()])

    def test_port_race_web_bind_failure_does_not_start_worker(self):
        process=self.launch(TAKE_PORT='1');process.communicate(timeout=4)
        self.assertNotEqual(process.returncode,0)
        self.assertNotIn('collect_worker',[row['role'] for row in self.calls()])

    def test_worker_exit_cleans_live_web_and_releases_lock(self):
        process=self.launch(FAIL_ROLE='collect_worker');process.communicate(timeout=4)
        self.assertEqual(process.returncode,7)
        web=next(row['pid'] for row in self.calls() if row['role']=='runserver')
        self.assertTrue(self.gone(web))
        next_process=self.launch();self.ready(next_process)

    def test_int_and_term_cleanup_owned_children_and_keep_lock_inode(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            (self.root/'calls.jsonl').unlink(missing_ok=True)
            process=self.launch();rows=self.ready(process)
            inode=(self.root/'.local'/'startup.lock').stat().st_ino
            process.send_signal(sig);_,error=process.communicate(timeout=7)
            self.assertEqual(process.returncode,128+sig,error.decode())
            for row in rows:
                if row['role'] in ('runserver','collect_worker'):self.assertTrue(self.gone(row['pid']))
            self.assertEqual((self.root/'.local'/'startup.lock').stat().st_ino,inode)

    def test_hard_kill_retains_live_child_lock_until_only_owned_children_exit(self):
        first=self.launch();rows=self.ready(first)
        owned=[row['pid'] for row in rows if row['role'] in ('runserver','collect_worker')]
        first.kill();first.wait(timeout=3)
        duplicate=self.launch();_,error=duplicate.communicate(timeout=3)
        self.assertNotEqual(duplicate.returncode,0);self.assertIn('已有启动进程',error.decode())
        for pid in owned:
            try:os.killpg(pid,signal.SIGTERM)
            except ProcessLookupError:pass
        # Reparented zombies can remain visible briefly but no longer retain FDs.
        for _ in range(100):
            process=self.launch()
            time.sleep(.05)
            if process.poll() is None:
                self.ready(process);break
            process.communicate(timeout=1);time.sleep(.03)
        else:self.fail('lock remained after owned children exited')

    def await_role(self,process,role):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=self.calls()
            if any(row['role']==role for row in rows):return rows
            if process.poll() is not None:self.fail(process.communicate()[1].decode())
            time.sleep(.03)
        self.fail('isolated helper phase not reached')

    def test_lock_and_int_term_cover_each_preparation_phase(self):
        for role in ('postgres','migrate','check'):
            for sig in (signal.SIGINT,signal.SIGTERM):
                with self.subTest(role=role,signal=sig):
                    (self.root/'calls.jsonl').unlink(missing_ok=True)
                    first=self.launch(HOLD_ROLE=role);rows=self.await_role(first,role)
                    duplicate=self.launch();_,error=duplicate.communicate(timeout=3)
                    self.assertNotEqual(duplicate.returncode,0);self.assertIn('已有启动进程',error.decode())
                    self.assertEqual(self.calls(),rows)
                    first.send_signal(sig);first.communicate(timeout=7)
                    self.assertEqual(first.returncode,128+sig)
                    self.assertNotIn('collect_worker',[row['role'] for row in self.calls()])

    def test_external_port_occupant_winning_after_precheck_is_not_killed(self):
        port=self.port();bind='127.0.0.1:'+str(port)
        first=self.launch(bind=bind,HOLD_ROLE='check');self.await_role(first,'check')
        listener=socket.socket();listener.bind(('127.0.0.1',port));listener.listen();self.listeners.append(listener)
        (self.root/'release-helper').write_text('go')
        first.communicate(timeout=4)
        self.assertNotEqual(first.returncode,0)
        self.assertNotIn('collect_worker',[row['role'] for row in self.calls()])
        self.assertEqual(listener.getsockname()[1],port)
        with socket.create_connection(('127.0.0.1',port),timeout=1):pass

    def test_cleanup_window_keeps_lock_and_reaps_term_ignoring_worker(self):
        first=self.launch(IGNORE_TERM_ROLE='collect_worker');rows=self.ready(first)
        first.send_signal(signal.SIGTERM);time.sleep(.15)
        self.assertIsNone(first.poll())
        duplicate=self.launch();_,error=duplicate.communicate(timeout=3)
        self.assertNotEqual(duplicate.returncode,0);self.assertIn('已有启动进程',error.decode())
        first.communicate(timeout=7);self.assertEqual(first.returncode,143)
        for row in rows:
            if row['role'] in ('runserver','collect_worker'):self.assertTrue(self.gone(row['pid']))
        (self.root/'calls.jsonl').unlink(missing_ok=True)
        again=self.launch();self.ready(again)

    def test_live_web_exit_cleans_worker_and_preserves_signal_result(self):
        first=self.launch();rows=self.ready(first)
        web=next(row['pid'] for row in rows if row['role']=='runserver')
        worker=next(row['pid'] for row in rows if row['role']=='collect_worker')
        os.kill(web,signal.SIGTERM);first.communicate(timeout=7)
        self.assertEqual(first.returncode,143);self.assertTrue(self.gone(worker))

    def test_dead_leader_term_ignoring_descendant_is_killed_before_lock_release(self):
        first=self.launch(SPAWN_DESCENDANT='1');rows=self.ready(first)
        marker=self.root/'descendant-ready'
        deadline=time.monotonic()+3
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(marker.exists())
        descendant=int(marker.read_text())
        worker=next(row['pid'] for row in rows if row['role']=='collect_worker')
        self.assertEqual(os.getpgid(descendant),worker)
        first.send_signal(signal.SIGTERM);time.sleep(.15)
        self.assertIsNone(first.poll())
        duplicate=self.launch();_,error=duplicate.communicate(timeout=3)
        self.assertNotEqual(duplicate.returncode,0);self.assertIn('已有启动进程',error.decode())
        first.communicate(timeout=8);self.assertEqual(first.returncode,143)
        self.assertTrue(self.gone(worker))
        # Orphan zombies may stay briefly visible to kill(0); they hold no lock.
        import fcntl
        with (self.root/'.local'/'startup.lock').open('r+') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        (self.root/'calls.jsonl').unlink(missing_ok=True)
        again=self.launch();self.ready(again)
        # Inspect this exact owned PID only: reparented zombies are not live.
        status=subprocess.run(['ps','-o','stat=','-p',str(descendant)],capture_output=True,text=True,timeout=2)
        self.assertTrue(not status.stdout.strip() or status.stdout.strip().startswith('Z'),status.stdout)

    def test_uncertain_permission_probe_is_not_treated_as_dead_group(self):
        from .local_runtime import group_alive,stop_children
        with patch('config.local_runtime.os.killpg',side_effect=PermissionError),patch('config.local_runtime.group_metadata_alive',return_value=None):
            self.assertTrue(group_alive(12345))
        child=Mock(pid=12345);child.poll.return_value=143;child.wait.return_value=143
        def send(pgid,signum):
            if signum in (0,signal.SIGKILL):raise PermissionError
        with patch('config.local_runtime.os.killpg',side_effect=send) as signals, \
             patch('config.local_runtime.time.monotonic',side_effect=[0,1,6]), \
             patch('config.local_runtime.time.sleep'), \
             patch('config.local_runtime.group_metadata_alive',return_value=None), \
             patch('config.local_runtime.sys.stderr',new_callable=io.StringIO) as errors:
            self.assertFalse(stop_children([child]))
        self.assertIn('无法完全核实清理',errors.getvalue())
        self.assertTrue(any(call.args[1]==signal.SIGKILL for call in signals.call_args_list))
        child.wait.assert_called_once()

    def test_preparation_hard_kill_keeps_lock_until_owned_stage_finishes(self):
        for role in ('postgres','migrate','check'):
            (self.root/'calls.jsonl').unlink(missing_ok=True)
            release=self.root/'release-helper';release.unlink(missing_ok=True)
            first=self.launch(HOLD_ROLE=role);rows=self.await_role(first,role)
            first.kill();first.wait(timeout=3)
            duplicate=self.launch();_,error=duplicate.communicate(timeout=3)
            self.assertNotEqual(duplicate.returncode,0);self.assertIn('已有启动进程',error.decode())
            self.assertEqual(self.calls(),rows)
            release.write_text('go')
            import fcntl
            deadline=time.monotonic()+3
            with (self.root/'.local'/'startup.lock').open('r+') as lock:
                while True:
                    try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:
                        if time.monotonic()>deadline:self.fail('finite preparation retained lock after completion')
                        time.sleep(.03)
            release.unlink()
        (self.root/'calls.jsonl').unlink(missing_ok=True)
        again=self.launch();self.ready(again)

    def test_pg_daemon_does_not_inherit_finite_wrapper_lock(self):
        (self.root/'scripts'/'start_postgres.sh').write_text('.venv/bin/python manage.py daemon-start\n')
        script=(self.root/'manage.py').read_text()
        script=script.replace("if role in ('postgres','migrate','check'):sys.exit(0)", "if role=='daemon-start':\n    subprocess.Popen([sys.executable,'-c',\"import os,time;from pathlib import Path;Path('daemon-pid').write_text(str(os.getpid()));time.sleep(60)\"],close_fds=False,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n    sys.exit(0)\nif role in ('postgres','migrate','check'):sys.exit(0)")
        (self.root/'manage.py').write_text(script)
        first=self.launch();self.ready(first)
        daemon=int((self.root/'daemon-pid').read_text());self.groups.add(daemon)
        first.send_signal(signal.SIGTERM);first.communicate(timeout=7)
        self.assertEqual(first.returncode,143)
        os.kill(daemon,0)  # Database-like daemon remains alive independently.
        import fcntl
        with (self.root/'.local'/'startup.lock').open('r+') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.killpg(daemon,signal.SIGTERM)

    def test_owned_group_metadata_distinguishes_zombies_and_unknown_live_owner(self):
        from .local_runtime import group_metadata_alive
        own=os.getuid()
        for output,expected in [(f'1 12345 {own} Z\n',False),(f'1 12345 {own} S\n',True),
                                (f'1 12345 {own+1} S\n',None),('1 99999 0 S\n',None)]:
            result=Mock(returncode=0,stdout=output,stderr='')
            with patch('config.local_runtime.subprocess.run',return_value=result) as lookup:
                self.assertIs(group_metadata_alive(12345),expected)
            self.assertEqual(lookup.call_args.args[0],['/bin/ps','-g','12345','-o','pid=,pgid=,uid=,stat='])

    def test_failed_metadata_query_remains_unknown_through_cleanup_chain(self):
        from .local_runtime import group_metadata_alive,group_alive,stop_children
        failed=Mock(returncode=1,stdout='',stderr='permission denied')
        with patch('config.local_runtime.subprocess.run',return_value=failed):
            self.assertIsNone(group_metadata_alive(12345))
            with patch('config.local_runtime.os.killpg',side_effect=PermissionError):
                self.assertTrue(group_alive(12345))
                child=Mock(pid=12345);child.poll.return_value=143;child.wait.return_value=143
                with patch('config.local_runtime.time.monotonic',side_effect=[0,1,6]), \
                     patch('config.local_runtime.time.sleep'), \
                     patch('config.local_runtime.sys.stderr',new_callable=io.StringIO) as errors:
                    self.assertFalse(stop_children([child]))
                self.assertIn('无法完全核实清理',errors.getvalue())
        with patch('config.local_runtime.subprocess.run',return_value=Mock(returncode=1,stdout='',stderr='')):
            self.assertFalse(group_metadata_alive(12345))

    def test_independent_real_directories_do_not_share_lock(self):
        other=Path(self.tmp.name)/'other';other.mkdir();self.project(other)
        first=self.launch();second=self.launch(root=other)
        self.ready(first);rows=self.ready(second,other)
        self.groups.update(row['pid'] for row in rows if row['role'] in ('runserver','collect_worker'))
        self.assertIsNone(first.poll());self.assertIsNone(second.poll())
