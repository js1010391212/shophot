#!/usr/bin/env python3
"""Explicit private config -> check -> isolated static -> fixed loopback WSGI."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description='Start the isolated personal web entry (no worker/migrations).')
    parser.add_argument('--config', required=True, help='Absolute private JSON runtime config path; never pass secrets here.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ['SHOPHOT_PERSONAL_CONFIG'] = args.config
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.personal_access'
    os.environ.pop('GUNICORN_CMD_ARGS', None)
    from django.core.exceptions import ImproperlyConfigured
    try:
        from config import personal_access  # Validate all inputs before commands, never print values.
    except ImproperlyConfigured as error:
        print(str(error), file=sys.stderr)
        return 2
    if any(importlib.util.find_spec(name) is None for name in ('gunicorn', 'whitenoise')):
        print('Missing personal WSGI/static dependencies; install the reviewed requirements-personal.txt first.', file=sys.stderr)
        return 2
    for command in ([sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
                    [sys.executable, 'manage.py', 'collectstatic', '--noinput']):
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode:
            return result.returncode
    os.chdir(root)
    os.execv(sys.executable, [sys.executable, '-m', 'gunicorn', '--config', 'scripts/personal_gunicorn.py',
                            'config.personal_wsgi:application'])


if __name__ == '__main__':
    sys.exit(main())
