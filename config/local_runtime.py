"""Local launcher lifecycle: per-real-directory OS lock and owned children only."""
import fcntl
import ipaddress
import os
from pathlib import Path
import select
import runpy
import socketserver
import signal
import socket
import stat
import subprocess
import sys
import time


class RuntimeErrorVisible(Exception):
    def __init__(self,message,code=1):
        super().__init__(message);self.code=code


class StopRequested(Exception):
    def __init__(self, signum):self.signum=signum


def acquire_lock(root):
    directory=root/'.local'
    directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeErrorVisible('项目运行目录无效；未启动服务。')
    fd=os.open(directory/'startup.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():
            raise RuntimeErrorVisible('项目启动锁无效；未启动服务。')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeErrorVisible('此项目已有启动进程；换端口也不能重复启动，请使用现有服务。') from None
        return fd
    except BaseException:
        os.close(fd);raise


def bind_target(value):
    if not isinstance(value,str) or len(value)>100:
        raise RuntimeErrorVisible('SHOPHOT_BIND 地址无效。')
    if value.isascii() and value.isdigit():host,port='127.0.0.1',value
    elif value.startswith('[') and ']:' in value:host,port=value[1:].split(']:',1)
    elif value.count(':')==1:host,port=value.split(':')
    else:raise RuntimeErrorVisible('SHOPHOT_BIND 地址无效，请使用 IP:端口（如 127.0.0.1:8000）。')
    if not port.isascii() or not port.isdigit() or len(port)>5 or not 1<=int(port)<=65535:
        raise RuntimeErrorVisible('SHOPHOT_BIND 端口须为 1–65535。')
    if host=='localhost':host='127.0.0.1'
    try:address=ipaddress.ip_address(host)
    except ValueError:raise RuntimeErrorVisible('SHOPHOT_BIND 地址无效，请填写明确 IP 或 localhost。') from None
    family=socket.AF_INET6 if address.version==6 else socket.AF_INET
    with socket.socket(family,socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:probe.bind((host,int(port)))
        except OSError:raise RuntimeErrorVisible('目标地址不可绑定或端口已被占用；未启动数据库、迁移或 worker。') from None
    return f'[{host}]:{port}' if address.version==6 else f'{host}:{port}'


def exit_status(code):
    return 128-code if code<0 else code


def group_metadata_alive(pgid):
    # Permission uncertainty is resolved only for this exact owned group.
    try:
        result=subprocess.run(['/bin/ps','-g',str(pgid),'-o','pid=,pgid=,uid=,stat='],
            capture_output=True,text=True,timeout=1,close_fds=True)
    except (OSError,subprocess.TimeoutExpired):return None
    if result.returncode not in (0,1) or result.stderr.strip() or len(result.stdout)>8192:return None
    rows=result.stdout.splitlines()
    if not rows:return False
    live=False
    for row in rows:
        parts=row.split()
        if len(parts)!=4 or not all(value.isdigit() for value in parts[:3]) or int(parts[1])!=pgid:return None
        if not parts[3].startswith(('Z','X')):
            if int(parts[2])!=os.getuid():return None
            live=True
    return live


def group_alive(pgid):
    try:os.killpg(pgid,0)
    except ProcessLookupError:return False
    except PermissionError:
        state=group_metadata_alive(pgid)
        return True if state is None else state
    return True


def stop_children(children):
    # Each group was created by our start_new_session Popen. Reap leaders while
    # retaining group IDs: a leader exiting does not prove descendants exited.
    groups={child.pid for child in children}
    for pgid in groups:
        try:os.killpg(pgid,signal.SIGTERM)
        except (ProcessLookupError,PermissionError):pass
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        for child in children:child.poll()
        groups={pgid for pgid in groups if group_alive(pgid)}
        if not groups:break
        time.sleep(.05)
    complete=True
    for pgid in groups:
        if group_alive(pgid):
            try:os.killpg(pgid,signal.SIGKILL)
            except ProcessLookupError:pass
            except PermissionError:
                if group_metadata_alive(pgid) is not False:
                    complete=False
                    print('本轮进程组无法完全核实清理；若仍有持锁进程，请维护者核对，勿删除锁文件。',file=sys.stderr)
    for child in children:
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            complete=False
            print('本轮子进程尚未退出，清理失败；请维护者核对，勿删除锁文件。',file=sys.stderr)
    return complete


def start_web(root,python,bind,lock,children,stop_check):
    read_fd,write_fd=os.pipe()
    try:
        child=subprocess.Popen([python,str(root/'config'/'local_runtime.py'),'--web-child',bind,str(write_fd)],
            cwd=root,start_new_session=True,pass_fds=(lock,write_fd))
        children.append(child)
        os.close(write_fd);write_fd=None
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            stop_check()
            if child.poll() is not None:
                raise RuntimeErrorVisible('网页启动失败；未启动 worker。',exit_status(child.returncode) or 1)
            ready,_,_=select.select([read_fd],[],[],.1)
            if ready:
                if os.read(read_fd,16)==b'ready' and child.poll() is None:return
                try:code=exit_status(child.wait(timeout=1))
                except subprocess.TimeoutExpired:code=1
                raise RuntimeErrorVisible('网页未就绪；未启动 worker。',code or 1)
        raise RuntimeErrorVisible('网页启动超时；未启动 worker。')
    finally:
        os.close(read_fd)
        if write_fd is not None:os.close(write_fd)


def web_child(root,bind,ready_fd):
    # TCPServer sends readiness only after this child successfully binds/listens.
    # Keep Django's original command/settings/WSGI lifecycle; no HTTP probe of a
    # potentially unrelated process can falsely trigger a worker.
    original=socketserver.TCPServer.server_activate
    port=int(bind.rsplit(':',1)[1])
    notified=False
    def activate(server):
        nonlocal notified
        original(server)
        if not notified and server.server_address[1]==port:
            os.write(ready_fd,b'ready');os.close(ready_fd);notified=True
    socketserver.TCPServer.server_activate=activate
    sys.path.insert(0,str(root))
    sys.argv=['manage.py','runserver',bind,'--noreload']
    runpy.run_path(str(root/'manage.py'),run_name='__main__')


def run(root):
    lock=None;children=[]
    handlers={};requested=None
    def interrupted(signum,frame):
        nonlocal requested
        requested=signum
    def stop_check():
        if requested is not None:raise StopRequested(requested)
    try:
        for signum in (signal.SIGINT,signal.SIGTERM):
            handlers[signum]=signal.signal(signum,interrupted)
        lock=acquire_lock(root)
        bind=bind_target(os.environ.get('SHOPHOT_BIND','127.0.0.1:8000'))
        stop_check()
        python=str(root/'.venv'/'bin'/'python')
        for command in ([python,str(root/'config'/'local_runtime.py'),'--prepare-child','bash',str(root/'scripts'/'start_postgres.sh')],
                        [python,'manage.py','migrate','--noinput'],
                        [python,'manage.py','check']):
            stop_check()
            child=subprocess.Popen(command,cwd=root,start_new_session=True,
                pass_fds=(lock,))
            children.append(child)
            while child.poll() is None:
                stop_check();time.sleep(.05)
            code=child.returncode
            if code:return exit_status(code)
            children.remove(child)
        stop_check()
        start_web(root,python,bind,lock,children,stop_check)
        stop_check()
        child=subprocess.Popen([python,'manage.py','collect_worker'],cwd=root,start_new_session=True,pass_fds=(lock,))
        children.append(child)
        while True:
            stop_check()
            for child in children:
                code=child.poll()
                if code is not None:return exit_status(code)
            time.sleep(.1)
    except StopRequested as stop:
        return 128+stop.signum
    except RuntimeErrorVisible as error:
        print(str(error),file=sys.stderr);return error.code
    except OSError:
        print('本机启动失败，请检查项目运行目录、解释器和脚本；本轮子进程将清理。',file=sys.stderr);return 1
    finally:
        # A second INT/TERM must not interrupt cleanup and leave a live owned child.
        for signum in handlers:signal.signal(signum,signal.SIG_IGN)
        complete=True
        try:complete=stop_children(children)
        finally:
            # Do not unlink or explicitly unlock: close releases our reference;
            # surviving children after an uncatchable SIGKILL retain their lock.
            if lock is not None:os.close(lock)
            for signum,handler in handlers.items():signal.signal(signum,handler)
        if not complete:return 1


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    if len(sys.argv)>2 and sys.argv[1]=='--prepare-child':
        # This finite wrapper retains the lock; helper/pg_ctl/daemon cannot.
        code=subprocess.run(sys.argv[2:],cwd=root,close_fds=True).returncode
        sys.exit(exit_status(code))
    elif len(sys.argv)==4 and sys.argv[1]=='--web-child':
        web_child(root,sys.argv[2],int(sys.argv[3]))
    else:
        sys.exit(run(root))
