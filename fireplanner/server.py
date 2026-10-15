"""Dependency-free loopback HTTP server and bounded durable worker."""
import argparse
import csv
import io
import ipaddress
import json
import mimetypes
import os
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .store import Store


class Worker:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.wait(.15):
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE jobs SET status='running',attempts=attempts+1 WHERE id=?",(row['id'],))
            if not row:
                continue
            try:
                from . import engine
                payload = json.loads(row['payload'])
                result = engine.project(payload['plan']) if row['kind']=='project' else engine.simulate(payload['plan'],payload['settings'])
                encoded = json.dumps(result,allow_nan=False)
                with self.store.connect() as db:
                    db.execute("UPDATE jobs SET status='completed',result=?,error=NULL WHERE id=? AND status='running'",(encoded,row['id']))
            except Exception as exc:
                # Validation failures are terminal; unexpected errors retry twice.
                status = 'failed' if isinstance(exc,(ValueError,TypeError,KeyError)) or row['attempts'] >= 2 else 'queued'
                with self.store.connect() as db:
                    db.execute("UPDATE jobs SET status=?,error=? WHERE id=? AND status='running'",(status,str(exc)[:500],row['id']))


def make_server(host='127.0.0.1', port=8080, database='data/planner.sqlite3', static=None, workers=True):
    owner_email = os.environ.get('FIRE_OIDC_OWNER_EMAIL', '').strip().lower()
    if owner_email:
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError as exc:
            raise ValueError('FIRE_OIDC_OWNER_EMAIL requires a loopback bind address') from exc
        if not loopback:
            raise ValueError('FIRE_OIDC_OWNER_EMAIL requires a loopback bind address')
    store = Store(database)
    root = Path(static or Path(__file__).resolve().parent.parent/'web').resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'FirePlanner/1'

        def log_message(self, *args):
            pass  # Do not retain URLs, user identifiers, or financial inputs in logs.

        def send(self, status, value, content_type='application/json', cookie=None):
            body = json.dumps(value,allow_nan=False).encode() if content_type=='application/json' else value
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
            if cookie:
                self.send_header('Set-Cookie',cookie)
            self.end_headers()
            self.wfile.write(body)

        def token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie',''))
                return cookie['session'].value if 'session' in cookie else ''
            except Exception:
                return ''

        def dispatch(self):
            configured_owner_email = os.environ.get('FIRE_OIDC_OWNER_EMAIL', '').strip().lower()
            path = urlsplit(self.path).path
            parts = path.strip('/').split('/')
            data = {}
            if self.command in ('POST','PUT','DELETE'):
                origin = self.headers.get('Origin')
                host_header = self.headers.get('Host','')
                if origin and origin not in ('http://'+host_header,'https://'+host_header):
                    raise PermissionError('Cross-origin mutation rejected')
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    raise PermissionError('Cross-site mutation rejected')
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                size = int(self.headers.get('Content-Length','0'))
                if size < 0 or size > 1048576:
                    raise ValueError('Request exceeds 1 MiB')
                data = json.loads(self.rfile.read(size) or b'{}',parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite number')))
                if not isinstance(data,dict):
                    raise ValueError('Request must be an object')
            if path == '/api/health' and self.command=='GET':
                return self.send(200,{'status':'ok'})
            if path == '/api/quick' and self.command=='POST':
                from .engine import quick
                return self.send(200,quick(data.get('plan',data)))
            if path == '/api/project' and self.command=='POST':
                if set(data) != {'plan'} or not isinstance(data['plan'],dict):
                    raise ValueError('Request must contain only a plan object')
                from .engine import project
                return self.send(200,project(data['plan']))
            if path == '/api/analyze' and self.command=='POST':
                from .planning import analyze
                return self.send(200,analyze(data))
            if path == '/api/capabilities' and self.command=='GET':
                from .planning import capabilities
                return self.send(200,capabilities())
            if path in ('/api/auth/register','/api/auth/login') and self.command=='POST':
                method = store.register if path.endswith('register') else store.login
                user = method(str(data.get('email','')),str(data.get('password','')))
                token = store.session(user)
                return self.send(200,{'user':user},cookie='session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
            if not path.startswith('/api/'):
                if self.command != 'GET':
                    raise LookupError('Not found')
                candidate = (root/path.lstrip('/')).resolve() if path != '/' else root/'index.html'
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    raise LookupError('Not found')
                return self.send(200,candidate.read_bytes(),mimetypes.guess_type(str(candidate))[0] or 'application/octet-stream')
            user = store.user(self.token())
            if not user:
                asserted_email = self.headers.get('X-Forwarded-Email', '').strip().lower()
                if asserted_email and configured_owner_email and asserted_email == configured_owner_email:
                    with store.connect() as db:
                        row = db.execute(
                            'SELECT id,email,household,role FROM users WHERE email=? AND role=?',
                            (configured_owner_email, 'owner')).fetchone()
                    user = dict(row) if row else None
            if path == '/api/auth/me' and self.command=='GET':
                # This public endpoint lets the browser choose local login or OIDC.
                return self.send(200,{'user':user or None,'oidc':bool(configured_owner_email)})
            if path == '/api/auth/oidc' and self.command=='GET':
                if not user:
                    return self.send(401,{'error':'Sign in required'})
                return self.send(200,{'user':user,'oidc':bool(configured_owner_email)})
            if not user:
                return self.send(401,{'error':'Sign in required'})
            if path == '/api/household/members' and self.command=='GET':
                return self.send(200,{'members':store.members(user)})
            if path == '/api/household/invites' and self.command=='POST':
                return self.send(201,{'invitation':store.invite(user,data)})
            if path == '/api/household/join' and self.command=='POST':
                return self.send(200,{'user':store.redeem(user,data)})
            if path == '/api/auth/logout' and self.command=='POST':
                store.logout(self.token())
                return self.send(200,{'ok':True},cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if parts == ['api','plans']:
                if self.command=='GET':
                    return self.send(200,{'plans':store.plans(user)})
                if self.command=='POST':
                    return self.send(201,store.save(user,data))
            if len(parts)>=3 and parts[:2]==['api','plans']:
                ident=parts[2]
                if len(parts)==3:
                    if self.command=='GET':
                        return self.send(200,store.plan(user,ident))
                    if self.command=='PUT':
                        return self.send(200,store.save(user,data,ident))
                    if self.command=='DELETE':
                        return self.send(200,{'deleted':store.delete_plan(user,ident)})
                if len(parts)==4:
                    action=parts[3]
                    if action=='fork' and self.command=='POST':
                        return self.send(201,store.fork(user,ident,data))
                    if action=='compare' and self.command=='POST':
                        if set(data) != {'other_id'} or not isinstance(data['other_id'],str) or not data['other_id']:
                            raise ValueError('Request must contain only a non-empty other_id')
                        left=store.plan(user,ident)
                        right=store.plan(user,data['other_id'])
                        from .engine import project
                        left_projection=project(left['plan'])
                        right_projection=project(right['plan'])
                        left_by_age={row.get('age'):row for row in left_projection.get('annual',[]) if isinstance(row.get('age'),(int,float))}
                        right_by_age={row.get('age'):row for row in right_projection.get('annual',[]) if isinstance(row.get('age'),(int,float))}
                        overlap=sorted(left_by_age.keys() & right_by_age.keys())
                        annual=[]
                        for age in overlap:
                            lrow,rrow=left_by_age[age],right_by_age[age]
                            difference={'age':age}
                            for field in ('balance','net_worth','unfunded'):
                                if field in lrow and field in rrow:
                                    difference[field]=rrow[field]-lrow[field]
                            annual.append(difference)
                        return self.send(200,{'left':{'id':left['id'],'name':left['name'],'projection':left_projection},
                            'right':{'id':right['id'],'name':right['name'],'projection':right_projection},
                            'comparison':{'basis':'age','annual':annual}})
                    if action=='run' and self.command=='POST':
                        return self.send(202,{'job':store.enqueue(user,ident,data)})
                    if action in ('scenarios','observations','revisions'):
                        if action=='revisions' and self.command=='GET':
                            store.plan(user,ident)
                            with store.connect() as db:
                                rows=db.execute('SELECT version,plan,created FROM revisions WHERE plan_id=? ORDER BY version',(ident,)).fetchall()
                            return self.send(200,{'revisions':[dict(version=r['version'],plan=json.loads(r['plan']),created=r['created']) for r in rows]})
                        if action!='revisions' and self.command in ('GET','POST'):
                            return self.send(200,{action:store.records(user,ident,action,data if self.command=='POST' else None)})
                    if action=='export' and self.command=='GET':
                        plan=store.plan(user,ident)
                        export_format=parse_qs(urlsplit(self.path).query).get('format',['json'])[0]
                        if export_format not in ('json','csv'):
                            raise ValueError('format must be json or csv')
                        if export_format=='csv':
                            from .engine import project
                            projection=project(plan['plan'])
                            out=io.StringIO(); writer=csv.writer(out)
                            writer.writerow(['plan_id',plan['id']]); writer.writerow(['plan_version',plan['version']])
                            for key,value in projection.get('metadata',{}).items():
                                writer.writerow([key,json.dumps(value)])
                            rows=projection['annual']
                            fields=list(rows[0]) if rows else ['year','balance','unfunded']
                            writer.writerow(fields)
                            for row in rows:
                                writer.writerow([row.get(key,'') for key in fields])
                            return self.send(200,out.getvalue().encode(),'text/csv; charset=utf-8')
                        store.owner(user)
                        return self.send(200,plan)
                if len(parts)==5 and parts[3] in ('observations','scenarios') and self.command=='DELETE':
                    return self.send(200,{'deleted':store.delete_record(user,ident,parts[3],parts[4])})
            if len(parts) in (3,4) and parts[:2]==['api','jobs']:
                if self.command=='GET' and len(parts)==3:
                    return self.send(200,{'job':store.job(user,parts[2])})
                if self.command=='POST' and len(parts)==4 and parts[3]=='cancel':
                    return self.send(200,{'job':store.job(user,parts[2],True)})
            raise LookupError('Not found')

        def handle_request(self):
            try:
                self.dispatch()
            except (ValueError,TypeError,json.JSONDecodeError) as exc:
                self.send(400,{'error':str(exc)})
            except PermissionError as exc:
                self.send(403,{'error':str(exc)})
            except LookupError as exc:
                self.send(404,{'error':str(exc)})
            except (FileExistsError,sqlite3.IntegrityError) as exc:
                self.send(409,{'error':'Account already exists' if isinstance(exc,sqlite3.IntegrityError) else str(exc)})
            except Exception:
                self.send(500,{'error':'Internal server error'})

        do_GET=handle_request
        do_POST=handle_request
        do_PUT=handle_request
        do_DELETE=handle_request

    server=ThreadingHTTPServer((host,port),Handler)
    server.store=store
    server.worker=Worker(store) if workers else None
    return server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default=os.environ.get('FIRE_HOST','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('FIRE_PORT','8080')))
    parser.add_argument('--database',default=os.environ.get('FIRE_DB','data/planner.sqlite3'))
    args=parser.parse_args()
    server=make_server(args.host,args.port,args.database)
    print('FirePlanner listening at http://%s:%d' % server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.worker.stop.set()
        server.server_close()


if __name__=='__main__':
    main()
