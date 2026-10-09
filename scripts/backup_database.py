#!/usr/bin/env python3
"""No DSN/path/target arguments: this project source and fresh isolated verify DB only."""
import argparse
import json
from pathlib import Path
import sys


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'This tool accepts no connection, archive or restore-target arguments.\n')


def main():
    parser=PrivateArgumentParser(description='Back up this local project DB and verify in a fresh disposable DB.')
    parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from config.database_backup import perform_backup
    report=perform_backup(root)
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status']=='verified' and report['cleanup']=='removed' else 1


if __name__=='__main__':sys.exit(main())
