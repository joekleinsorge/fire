#!/usr/bin/env python3
"""Consistent SQLite backup, including committed revisions and jobs."""
import argparse
import os
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('database', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
if not args.database.is_file():
    parser.error('Source database does not exist')
if args.destination.exists():
    parser.error('Destination already exists; choose a new file')
args.destination.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(args.destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
try:
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(args.destination) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
except Exception:
    args.destination.unlink(missing_ok=True)
    raise
print(f'Backup verified: {args.destination}')
