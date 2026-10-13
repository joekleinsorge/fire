"""Create a new private database and import a household source (offline only)."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fireplanner.household import import_household, draft_scenarios
from fireplanner.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--email', default='owner@openfi.local')
    args = parser.parse_args()
    if args.database.exists() or args.credentials.exists():
        parser.error('Refusing to overwrite an existing database or credentials file')
    plan = import_household(json.loads(args.source.read_text()))
    os.umask(0o077)
    args.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.credentials.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    password = secrets.token_urlsafe(32)
    # Exclusive creation protects both paths against accidental concurrent imports.
    with args.database.open('xb'):
        pass
    with args.credentials.open('x') as output:
        json.dump(dict(email=args.email, password=password), output)
        output.write('\n')
    store = Store(args.database)
    user = store.register(args.email, password)
    saved = store.save(user, dict(name=plan['name'], plan=plan))
    for scenario in draft_scenarios(plan):
        store.records(user, saved['id'], 'scenarios', scenario)
    export = args.database.with_suffix('.plan.json')
    with export.open('x') as output:
        json.dump(plan, output, indent=2)
        output.write('\n')
    with store.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    print('Created private database, credentials, importable plan, and three draft scenarios. No personal data printed.')


if __name__ == '__main__':
    main()
