"""SQLite persistence for the local prototype; production deployment targets PostgreSQL."""
import contextlib
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import time
from pathlib import Path


def merge_inputs(target, changes, depth=0):
    if depth > 50:
        raise ValueError('Changes are nested too deeply')
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in changes.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = merge_inputs(result.get(key), value, depth+1)
        else:
            result[key] = value
    return result


def run_summary(result):
    if result is None:
        return None
    keys = ('target','fi_age','earliest_fi_age','years_to_target','summary','outcomes',
            'ending_assets','completed','status','metadata','essential_spending_funded',
            'desired_lifestyle_funded','portfolio_survives')
    return {key: result[key] for key in keys if key in result}


class Store:
    def __init__(self, path):
        self.path = str(path)
        parent=Path(self.path).parent
        parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Create private database storage before SQLite can apply a permissive umask.
        descriptor=os.open(self.path,os.O_CREAT | os.O_RDWR,0o600)
        os.close(descriptor)
        os.chmod(self.path,0o600)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,household TEXT NOT NULL,role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY,household TEXT NOT NULL,email TEXT NOT NULL,role TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,household TEXT NOT NULL,name TEXT NOT NULL,version INTEGER NOT NULL,plan TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(plan_id TEXT NOT NULL,version INTEGER NOT NULL,plan TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(plan_id,version));
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,household TEXT NOT NULL,plan_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,result TEXT,error TEXT,attempts INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS job_summaries(run_id TEXT PRIMARY KEY,data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);
            CREATE INDEX IF NOT EXISTS jobs_history ON jobs(plan_id,household,created DESC,id DESC);
            CREATE INDEX IF NOT EXISTS jobs_latest ON jobs(plan_id,household,json_extract(payload,'$.scenario_id'),kind,created DESC,id DESC) WHERE status='completed';
            ''')
            # A process restart returns interrupted work to the durable queue.
            db.execute("UPDATE jobs SET status='failed',error='Interrupted after maximum attempts' WHERE status='running' AND attempts>=3")
            db.execute("UPDATE jobs SET status='queued' WHERE status='running' AND attempts<3")

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def password(value, salt=None):
        salt = salt or secrets.token_hex(16)
        return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 310000).hex()

    def register(self, email, password):
        email = email.strip().lower()
        if '@' not in email or len(email) > 254 or len(password) < 12 or len(password) > 1024:
            raise ValueError('Use a valid email and a password of 12–1024 characters')
        user = dict(id=secrets.token_hex(16), email=email, household=secrets.token_hex(16), role='owner')
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user['id'], email, self.password(password), user['household'], user['role']))
        return user

    def login(self, email, password):
        if len(password) > 1024:
            raise PermissionError('Invalid email or password')
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        # Perform the same expensive hash for unknown users.
        stored = row['password'] if row else '00' * 16 + ':' + '00' * 32
        if not hmac.compare_digest(self.password(password, stored.split(':')[0]), stored) or not row:
            raise PermissionError('Invalid email or password')
        return {k: row[k] for k in ('id', 'email', 'household', 'role')}

    def session(self, user):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time()+86400))
        return token

    def user(self, token):
        with self.connect() as db:
            row = db.execute('SELECT u.id,u.email,u.household,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))

    @staticmethod
    def writable(user):
        if user['role'] not in ('owner', 'editor'):
            raise PermissionError('Household is read-only for this account')

    @staticmethod
    def owner(user):
        if user['role'] != 'owner':
            raise PermissionError('Only household owners can perform this action')

    def plans(self, user):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM plans WHERE household=? ORDER BY rowid DESC', (user['household'],)).fetchall()
        return [self.decode_plan(r) for r in rows]

    @staticmethod
    def decode_plan(row):
        return dict(id=row['id'], name=row['name'], version=row['version'], plan=json.loads(row['plan']))

    def plan(self, user, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM plans WHERE id=? AND household=?', (ident, user['household'])).fetchone()
        if not row:
            raise LookupError('Plan not found')
        return self.decode_plan(row)

    def save(self, user, data, ident=None):
        self.writable(user)
        plan = data.get('plan', {})
        if not isinstance(plan, dict):
            raise ValueError('plan must be an object')
        if 'metadata' in plan and not isinstance(plan['metadata'], dict):
            raise ValueError('metadata must be an object')
        from .engine import project
        project(plan)  # Validate the full account/stream contract before persistence.
        name = str(data.get('name', 'My retirement plan')).strip()[:200] or 'My retirement plan'
        encoded = json.dumps(plan, allow_nan=False)
        with self.connect() as db:
            if ident:
                row = db.execute('SELECT version FROM plans WHERE id=? AND household=?', (ident,user['household'])).fetchone()
                if not row:
                    raise LookupError('Plan not found')
                if data.get('version') != row['version']:
                    raise FileExistsError('Plan changed; reload before saving')
                version = row['version']+1
                updated = db.execute('UPDATE plans SET name=?,version=?,plan=? WHERE id=? AND household=? AND version=?', (name,version,encoded,ident,user['household'],version-1))
                if updated.rowcount != 1:
                    raise FileExistsError('Plan changed; reload before saving')
            else:
                ident,version = secrets.token_hex(16),1
                db.execute('INSERT INTO plans VALUES(?,?,?,?,?)', (ident,user['household'],name,version,encoded))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)', (ident,version,encoded,time.time()))
        return self.plan(user,ident)

    def patch_plan(self, user, ident, data):
        """Versioned JSON Merge Patch of plan inputs, preserving unrelated fields."""
        self.writable(user)
        if set(data) != {'version', 'changes'} or not isinstance(data['changes'], dict):
            raise ValueError('PATCH requires version and a changes object')
        if type(data['version']) is not int:
            raise ValueError('version must be an integer')
        current = self.plan(user, ident)
        if current['version'] != data['version']:
            raise FileExistsError('Plan changed; reload before saving')

        plan = merge_inputs(current['plan'], data['changes'])
        return self.save(user, {'version': data['version'], 'name': plan.get('name', current['name']), 'plan': plan}, ident)

    def fork(self, user, ident, data):
        self.writable(user)
        if set(data) != {'name','plan'}:
            raise ValueError('Fork requires only name and plan')
        if not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>200:
            raise ValueError('name must be a non-empty string of at most 200 characters')
        if not isinstance(data['plan'],dict):
            raise ValueError('plan must be an object')
        self.plan(user,ident)  # Enforce that the parent belongs to this household.
        return self.save(user,{'name':data['name'],'plan':data['plan']})

    def delete_plan(self, user, ident):
        self.owner(user)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id FROM plans WHERE id=? AND household=?',
                (ident,user['household'])).fetchone()
            if not row:
                raise LookupError('Plan not found')
            # Stop queued and active work before removing it. A worker that already
            # claimed a row cannot publish after the job row has been deleted.
            db.execute("UPDATE jobs SET status='cancelled' WHERE plan_id=? AND household=? AND status IN ('queued','running')",
                (ident,user['household']))
            db.execute('DELETE FROM jobs WHERE plan_id=? AND household=?',(ident,user['household']))
            db.execute('DELETE FROM revisions WHERE plan_id=?',(ident,))
            db.execute('DELETE FROM records WHERE plan_id=?',(ident,))
            deleted=db.execute('DELETE FROM plans WHERE id=? AND household=?',(ident,user['household']))
            if deleted.rowcount != 1:
                raise LookupError('Plan not found')
        return True

    def records(self, user, ident, kind, data=None, return_created=False):
        if kind not in ('observations', 'scenarios'):
            raise ValueError('Unsupported record type')
        parent = self.plan(user,ident)
        if data is not None:
            if not isinstance(data,dict):
                raise ValueError('Record must be an object')
            if kind == 'scenarios':
                if 'changes' in data:
                    if not {'name','base_version','changes'} <= set(data) or not set(data) <= {'name','base_version','changes','metadata'}:
                        raise ValueError('Scenario changes require name, base_version, changes, and optional metadata')
                    if type(data['base_version']) is not int or data['base_version'] != parent['version']:
                        raise FileExistsError('Plan changed; reload before creating the scenario')
                    if not isinstance(data['changes'], dict):
                        raise ValueError('Scenario changes must be an object')
                    data = dict(name=data['name'],plan=merge_inputs(parent['plan'],data['changes']),
                        baseline_plan=parent['plan'],base_version=parent['version'],metadata=data.get('metadata',{}))
                if not {'name', 'plan'} <= set(data) or not set(data) <= {'name', 'plan', 'baseline_plan', 'base_version', 'metadata'}:
                    raise ValueError('Scenario must contain name and plan, with optional baseline_plan, base_version, and metadata')
                if 'metadata' in data and not isinstance(data['metadata'],dict):
                    raise ValueError('Scenario metadata must be an object')
                if 'base_version' in data:
                    version = data['base_version']
                    if type(version) is not int or version < 1:
                        raise ValueError('base_version must be a positive integer')
                    with self.connect() as db:
                        revision = db.execute('SELECT plan FROM revisions WHERE plan_id=? AND version=?',(ident,version)).fetchone()
                    if not revision or data.get('baseline_plan') != json.loads(revision['plan']):
                        raise ValueError('baseline_plan must match the specified saved revision')
                name=data['name']
                if not isinstance(name,str) or not name.strip() or len(name.strip())>100:
                    raise ValueError('Scenario name must be 1–100 characters')
                if not isinstance(data['plan'],dict):
                    raise ValueError('Scenario plan must be an object')
                from .engine import project
                project(data['plan'])
                baseline = data.get('baseline_plan')
                if 'baseline_plan' in data:
                    if not isinstance(baseline, dict):
                        raise ValueError('Scenario baseline_plan must be an object')
                    project(baseline)
                    if (baseline.get('currency', 'USD') != data['plan'].get('currency', 'USD')
                            or baseline.get('valuation_date') != data['plan'].get('valuation_date')):
                        raise ValueError('Scenario and baseline must share currency and valuation date')
                data=dict(name=name.strip(),plan=data['plan'], **({'baseline_plan':baseline} if baseline is not None else {}),
                    **({key:data[key] for key in ('base_version','metadata') if key in data}))
            else:
                allowed={'date','balance','note'}
                if not {'date','balance'} <= set(data) or not set(data) <= allowed:
                    raise ValueError('Observation must contain date and balance, with an optional note')
                from datetime import date
                date_value=data['date']
                try:
                    parsed=date.fromisoformat(date_value) if isinstance(date_value,str) else None
                except ValueError:
                    parsed=None
                if parsed is None or parsed.isoformat()!=date_value:
                    raise ValueError('Observation date must be a real YYYY-MM-DD date')
                balance=data['balance']
                if isinstance(balance,bool) or not isinstance(balance,(int,float)) or not math.isfinite(balance) or balance<0:
                    raise ValueError('Observation balance must be a finite non-negative number')
                note=data.get('note','')
                if not isinstance(note,str) or len(note)>240:
                    raise ValueError('Observation note must be text of at most 240 characters')
                data=dict(date=date_value,balance=balance,note=note)
        with self.connect() as db:
            if data is not None:
                self.writable(user)
                record_id=secrets.token_hex(16)
                db.execute('INSERT INTO records VALUES(?,?,?,?,?)', (record_id,ident,kind,json.dumps(data,allow_nan=False),time.time()))
            rows = db.execute('SELECT id,data,created FROM records WHERE plan_id=? AND kind=? ORDER BY created', (ident,kind)).fetchall()
        records=[dict(id=r['id'], data=json.loads(r['data']),created=r['created']) for r in rows]
        if return_created and data is not None:
            return {'scenarios':records,'scenario':next(record for record in records if record['id']==record_id)}
        return records

    def delete_record(self, user, ident, kind, record_id):
        if kind not in ('observations','scenarios'):
            raise ValueError('Unsupported record type')
        self.writable(user)
        self.plan(user,ident)
        with self.connect() as db:
            deleted=db.execute('DELETE FROM records WHERE id=? AND plan_id=? AND kind=?',
                (record_id,ident,kind))
        if deleted.rowcount != 1:
            raise LookupError('Record not found')
        return True

    def scenario(self, user, ident, scenario_id):
        self.plan(user,ident)
        with self.connect() as db:
            row=db.execute("SELECT id,data,created FROM records WHERE id=? AND plan_id=? AND kind='scenarios'",(scenario_id,ident)).fetchone()
        if not row:
            raise LookupError('Scenario not found')
        return dict(id=row['id'],data=json.loads(row['data']),created=row['created'])

    def enqueue(self, user, ident, data, scenario_id=None):
        self.writable(user)
        plan = self.plan(user,ident)
        if not set(data) <= {'kind','settings','metadata','version'}:
            raise ValueError('Run accepts kind, settings, metadata, and optional version')
        if not isinstance(data.get('settings',{}),dict) or not isinstance(data.get('metadata',{}),dict):
            raise ValueError('Run settings and metadata must be objects')
        if 'version' in data and (type(data['version']) is not int or data['version'] != plan['version']):
            raise FileExistsError('Plan changed; reload before running')
        scenario = self.scenario(user,ident,scenario_id)['data'] if scenario_id else None
        if scenario and scenario.get('metadata',{}).get('status') == 'needs_inputs':
            raise ValueError('This scenario needs confirmed purchase or household inputs before it can be calculated')
        kind = data.get('kind','project')
        if kind not in ('project','simulate'):
            raise ValueError('Unknown run kind')
        job_id = secrets.token_hex(16)
        with self.connect() as db:
            count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= 32:
                raise ValueError('Work queue is full; try later')
            from .engine import VERSION
            payload = json.dumps(dict(plan=scenario['plan'] if scenario else plan['plan'],
                plan_version=scenario.get('base_version') if scenario else plan['version'],
                plan_name=plan['name'],scenario_id=scenario_id,scenario_name=scenario['name'] if scenario else None,
                baseline_plan=scenario.get('baseline_plan') if scenario else None,
                scenario_metadata=scenario.get('metadata',{}) if scenario else {},
                settings=data.get('settings',{}),metadata=data.get('metadata',{}),
                requested_by=user['id'],submitted_engine_version=VERSION),allow_nan=False)
            db.execute('INSERT INTO jobs(id,household,plan_id,kind,payload,status,created) VALUES(?,?,?,?,?,?,?)',(job_id,user['household'],ident,kind,payload,'queued',time.time()))
        return self.job(user,job_id)

    def job(self, user, ident, cancel=False, summary_only=False):
        with self.connect() as db:
            columns='id,plan_id,kind,status,attempts,created,error,payload' if summary_only else '*'
            row = db.execute(f'SELECT {columns} FROM jobs WHERE id=? AND household=?',(ident,user['household'])).fetchone()
            if not row:
                raise LookupError('Job not found')
            if cancel:
                self.writable(user)
                db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status IN ('queued','running')",(ident,))
                row = db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
        result = {k:row[k] for k in ('id','plan_id','kind','status','attempts','created','error')}
        snapshot = json.loads(row['payload'])
        result['plan_version'] = snapshot.get('plan_version')
        result['snapshot'] = snapshot
        result['scenario_id'] = snapshot.get('scenario_id')
        result['scenario_name'] = snapshot.get('scenario_name')
        result['name'] = snapshot.get('scenario_name') or snapshot.get('plan_name') or 'Plan calculation'
        if summary_only:
            with self.connect() as db:
                result['result']=self.cached_run_summary(db,ident,row['plan_id'])['result'] if row['status']=='completed' else None
        else:
            result['result'] = json.loads(row['result']) if row['result'] else None
        return result

    def runs(self, user, ident, limit=50, before=None):
        self.plan(user,ident)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be an integer from 1 to 100')
        with self.connect() as db:
            params=[ident,user['household']]
            where='plan_id=? AND household=?'
            if before:
                cursor=db.execute('SELECT created,id FROM jobs WHERE id=? AND plan_id=? AND household=?',(before,ident,user['household'])).fetchone()
                if not cursor:
                    raise LookupError('Run cursor not found')
                where+=' AND (created<? OR (created=? AND id<?))'
                params.extend((cursor['created'],cursor['created'],cursor['id']))
            rows=db.execute(f'SELECT id FROM jobs WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*params,limit+1)).fetchall()
            runs=[self.cached_run_summary(db,row['id'],ident) for row in rows[:limit]]
        return dict(runs=runs,next_cursor=rows[limit-1]['id'] if len(rows)>limit else None)

    def latest_runs(self, user, ident):
        """One completed summary per scenario and calculation kind, across history."""
        self.plan(user,ident)
        with self.connect() as db:
            rows=db.execute("""WITH ranked AS (
                SELECT id,ROW_NUMBER() OVER (
                    PARTITION BY json_extract(payload,'$.scenario_id'),kind
                    ORDER BY created DESC,id DESC) AS position
                FROM jobs WHERE plan_id=? AND household=? AND status='completed'
                ) SELECT id FROM ranked WHERE position=1""",(ident,user['household'])).fetchall()
            runs=[self.cached_run_summary(db,row['id'],ident) for row in rows]
        runs.sort(key=lambda row:(row['created'],row['id']),reverse=True)
        return dict(runs=runs)

    def cached_run_summary(self, db, run_id, plan_id):
        """Completed runs are immutable; keep their small list representation."""
        cached=db.execute('SELECT data FROM job_summaries WHERE run_id=?',(run_id,)).fetchone()
        if cached:
            return json.loads(cached['data'])
        row=db.execute('SELECT * FROM jobs WHERE id=? AND plan_id=?',(run_id,plan_id)).fetchone()
        if not row:
            raise LookupError('Run not found')
        summary=self._summarize_runs([row],plan_id)[0]
        if row['status']=='completed':
            db.execute('INSERT OR IGNORE INTO job_summaries VALUES(?,?)',(run_id,json.dumps(summary,allow_nan=False)))
        return summary

    def _summarize_runs(self, rows, ident):
        runs=[]
        for row in rows:
            snapshot=json.loads(row['payload'])
            result=json.loads(row['result']) if row['result'] else None
            runs.append(dict(id=row['id'],plan_id=ident,kind=row['kind'],status=row['status'],created=row['created'],
                error=row['error'],plan_version=snapshot.get('plan_version'),scenario_id=snapshot.get('scenario_id'),
                name=snapshot.get('scenario_name') or snapshot.get('plan_name') or 'Plan calculation',
                settings=snapshot.get('settings',{}),metadata=snapshot.get('metadata',{}),
                scenario_metadata=snapshot.get('scenario_metadata',{}),result=run_summary(result)))
        return runs

    def members(self, user):
        with self.connect() as db:
            rows=db.execute('SELECT id,email,role FROM users WHERE household=? ORDER BY email',(user['household'],)).fetchall()
        return [dict(row) for row in rows]

    def invite(self,user,data):
        if user['role']!='owner':
            raise PermissionError('Only household owners can invite members')
        email=str(data.get('email','')).strip().lower()
        role=data.get('role','viewer')
        if '@' not in email or role not in ('editor','viewer'):
            raise ValueError('Provide email and editor or viewer role')
        token=secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO invites VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['household'],email,role,time.time()+86400))
        return dict(token=token,email=email,role=role,expires_in=86400)

    def redeem(self,user,data):
        token=hashlib.sha256(str(data.get('token','')).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            invite=db.execute('SELECT * FROM invites WHERE token=? AND email=? AND expires>?',(token,user['email'],time.time())).fetchone()
            if not invite:
                raise LookupError('Invitation not found or expired')
            if db.execute('SELECT count(*) FROM plans WHERE household=?',(user['household'],)).fetchone()[0]:
                raise ValueError('Cannot join a household while your current household owns plans')
            if db.execute('SELECT count(*) FROM users WHERE household=?',(user['household'],)).fetchone()[0]>1:
                raise ValueError('Cannot leave a shared household through invitation redemption')
            db.execute('UPDATE users SET household=?,role=? WHERE id=?',(invite['household'],invite['role'],user['id']))
            db.execute('DELETE FROM invites WHERE token=?',(token,))
        return dict(id=user['id'],email=user['email'],household=invite['household'],role=invite['role'])
