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

    def records(self, user, ident, kind, data=None):
        if kind not in ('observations', 'scenarios'):
            raise ValueError('Unsupported record type')
        self.plan(user,ident)
        if data is not None:
            if not isinstance(data,dict):
                raise ValueError('Record must be an object')
            if kind == 'scenarios':
                if not {'name', 'plan'} <= set(data) or not set(data) <= {'name', 'plan', 'baseline_plan'}:
                    raise ValueError('Scenario must contain name and plan, with an optional baseline_plan')
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
                data=dict(name=name.strip(),plan=data['plan'], **({'baseline_plan':baseline} if baseline is not None else {}))
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
                db.execute('INSERT INTO records VALUES(?,?,?,?,?)', (secrets.token_hex(16),ident,kind,json.dumps(data,allow_nan=False),time.time()))
            rows = db.execute('SELECT id,data,created FROM records WHERE plan_id=? AND kind=? ORDER BY created', (ident,kind)).fetchall()
        return [dict(id=r['id'], data=json.loads(r['data']),created=r['created']) for r in rows]

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

    def enqueue(self, user, ident, data):
        self.writable(user)
        plan = self.plan(user,ident)
        kind = data.get('kind','project')
        if kind not in ('project','simulate'):
            raise ValueError('Unknown run kind')
        job_id = secrets.token_hex(16)
        with self.connect() as db:
            count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= 32:
                raise ValueError('Work queue is full; try later')
            payload = json.dumps(dict(plan=plan['plan'],plan_version=plan['version'],settings=data.get('settings',{})),allow_nan=False)
            db.execute('INSERT INTO jobs(id,household,plan_id,kind,payload,status,created) VALUES(?,?,?,?,?,?,?)',(job_id,user['household'],ident,kind,payload,'queued',time.time()))
        return self.job(user,job_id)

    def job(self, user, ident, cancel=False):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND household=?',(ident,user['household'])).fetchone()
            if not row:
                raise LookupError('Job not found')
            if cancel:
                self.writable(user)
                db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status IN ('queued','running')",(ident,))
                row = db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
        result = {k:row[k] for k in ('id','plan_id','kind','status','attempts','created','error')}
        result['plan_version'] = json.loads(row['payload']).get('plan_version')
        result['result'] = json.loads(row['result']) if row['result'] else None
        return result

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
