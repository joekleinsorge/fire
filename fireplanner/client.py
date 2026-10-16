"""Local HTTP API client for people, scripts, and coding assistants (stdlib only)."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None  # Never forward credentials to a redirect destination.


class Client:
    def __init__(self, url='http://127.0.0.1:8080', token=None):
        self.url = url.rstrip('/')
        parsed = urlsplit(self.url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use an http(s) server URL without credentials, query, or fragment')
        if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Use HTTPS for servers outside loopback')
        self.token = token
        self.opener = build_opener(NoRedirect)

    def request(self, method, path, data=None):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None if data is None else json.dumps(data, allow_nan=False).encode()
        request = Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error).get('error', error.reason)
            except (ValueError, AttributeError):
                message = error.reason
            finally:
                error.close()
            raise ValueError(f'HTTP {error.code}: {message}') from None

    def wait(self, job_id, timeout=60, summary_only=False):
        deadline=time.monotonic()+timeout
        while True:
            job=self.request('GET','/api/jobs/'+job_id+('?summary=true' if summary_only else ''))['job']
            if job['status'] in ('completed','failed','cancelled'):
                return job
            if time.monotonic() >= deadline:
                return dict(job,timed_out=True)
            time.sleep(.3)


def authenticated_client(url, session_file):
    client=Client(url,os.environ.get('OPENFI_API_TOKEN'))
    if not client.token and Path(session_file).exists():
        session=json.loads(Path(session_file).read_text())
        if session.get('url') == client.url:
            client.token=session['token']
    return client


def read_json(path):
    return json.load(sys.stdin) if path == '-' else json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=os.environ.get('OPENFI_URL', 'http://127.0.0.1:8080'))
    parser.add_argument('--session-file', type=Path, default=Path(os.environ.get('OPENFI_SESSION_FILE',Path.home()/'.config/openfi/session.json')))
    commands = parser.add_subparsers(dest='command', required=True)
    login = commands.add_parser('login', help='Prompt for a password and store a private 24-hour session')
    identity=login.add_mutually_exclusive_group(required=True)
    identity.add_argument('--email')
    identity.add_argument('--credentials-file',type=Path,help='Existing private JSON file with email and password; credentials are never printed')
    commands.add_parser('logout', help='Revoke and remove the stored session')
    commands.add_parser('plans', help='List plan IDs, names, and versions')
    get = commands.add_parser('get', help='Read a complete saved plan envelope')
    get.add_argument('plan_id')
    patch = commands.add_parser('patch', help='Apply a versioned JSON merge patch: {version, changes}')
    patch.add_argument('plan_id'); patch.add_argument('file', help='JSON filename or - for stdin')
    create = commands.add_parser('create', help='Create a saved plan from plain plan JSON or an exported envelope')
    create.add_argument('file')
    project = commands.add_parser('project', help='Log a projection of a saved plan')
    project.add_argument('plan_id')
    project.add_argument('--wait',action='store_true')
    preview = commands.add_parser('preview', help='Temporary calculation without saved run history')
    preview.add_argument('plan_id')
    scenarios=commands.add_parser('scenarios',help='List saved scenario snapshots')
    scenarios.add_argument('plan_id')
    scenario=commands.add_parser('scenario',help='Save {name, base_version, changes, metadata} or a full scenario')
    scenario.add_argument('plan_id');scenario.add_argument('file')
    run=commands.add_parser('run',help='Log a projection or simulation with immutable inputs')
    run.add_argument('plan_id');run.add_argument('--scenario');run.add_argument('--version',type=int)
    run.add_argument('--kind',choices=('project','simulate'),default='project')
    run.add_argument('--settings',help='Settings JSON filename');run.add_argument('--metadata',help='Run notes/provenance JSON filename')
    run.add_argument('--wait',action='store_true');run.add_argument('--timeout',type=float,default=60)
    runs=commands.add_parser('runs',help='List saved calculation history')
    runs.add_argument('plan_id');runs.add_argument('--before',help='Pagination cursor from next_cursor')
    job=commands.add_parser('job',help='Read saved inputs, status, and results by run ID')
    job.add_argument('job_id');job.add_argument('--wait',action='store_true');job.add_argument('--timeout',type=float,default=60)
    args = parser.parse_args()
    if hasattr(args,'timeout') and not 0<args.timeout<=120:
        parser.error('timeout must be greater than 0 and at most 120 seconds')
    try:
        client = authenticated_client(args.url,args.session_file)
        if args.command == 'login':
            if args.credentials_file:
                credentials=json.loads(args.credentials_file.read_text())
                if not isinstance(credentials,dict) or not all(isinstance(credentials.get(k),str) for k in ('email','password')):
                    raise ValueError('Credentials file must contain email and password strings')
                login_data={key:credentials[key] for key in ('email','password')}
            else:
                login_data={'email':args.email,'password':getpass.getpass('Open FI password: ')}
            result = client.request('POST', '/api/auth/token', login_data)
            args.session_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(args.session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as output:
                json.dump({'url': client.url, 'token': result['access_token']}, output)
            result = {'signed_in': True, 'expires_in': result['expires_in']}
        elif args.command == 'logout':
            result = client.request('POST', '/api/auth/logout', {})
            if args.session_file.exists():
                session = json.loads(args.session_file.read_text())
                if session.get('url') == client.url:
                    args.session_file.unlink()
        elif args.command == 'plans':
            result = [{k: p[k] for k in ('id','name','version')} for p in client.request('GET', '/api/plans')['plans']]
        elif args.command == 'get':
            result = client.request('GET', '/api/plans/' + args.plan_id)
        elif args.command == 'patch':
            result = client.request('PATCH', '/api/plans/' + args.plan_id, read_json(args.file))
        elif args.command == 'create':
            document = read_json(args.file)
            result = client.request('POST', '/api/plans', document if 'plan' in document else {'name': document.get('name','My financial plan'), 'plan': document})
        elif args.command == 'scenarios':
            result=client.request('GET','/api/plans/'+args.plan_id+'/scenarios')
        elif args.command == 'scenario':
            document=read_json(args.file)
            result=client.request('POST','/api/plans/'+args.plan_id+'/scenarios',document)
        elif args.command in ('project','run'):
            path='/api/plans/'+args.plan_id
            if args.command=='run' and args.scenario:
                path+='/scenarios/'+args.scenario
            data={'kind':getattr(args,'kind','project')}
            for key in ('settings','metadata'):
                if getattr(args,key,None):data[key]=read_json(getattr(args,key))
            if getattr(args,'version',None) is not None:data['version']=args.version
            result=client.request('POST',path+'/run',data)['job']
            if args.wait:
                timeout=getattr(args,'timeout',60)
                if not 0<timeout<=120:raise ValueError('timeout must be from 0 to 120 seconds')
                result=client.wait(result['id'],timeout)
        elif args.command == 'runs':
            result=client.request('GET','/api/plans/'+args.plan_id+'/runs'+('?before='+args.before if args.before else ''))
        elif args.command == 'job':
            if not 0<args.timeout<=120:raise ValueError('timeout must be from 0 to 120 seconds')
            result=client.wait(args.job_id,args.timeout) if args.wait else client.request('GET','/api/jobs/'+args.job_id)['job']
        else:
            plan = client.request('GET', '/api/plans/' + args.plan_id)['plan']
            result = client.request('POST', '/api/project', {'plan': plan})
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
