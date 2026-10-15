import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from fireplanner.server import make_server


class APITest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=make_server(port=0,database=Path(self.tmp.name)/'test.db',workers=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self,method,path,data=None,cookie='',origin=None,extra_headers=None):
        conn=http.client.HTTPConnection(*self.server.server_address)
        headers={'Content-Type':'application/json','Cookie':cookie}
        if origin: headers['Origin']=origin
        if extra_headers: headers.update(extra_headers)
        conn.request(method,path,json.dumps(data) if data is not None else None,headers)
        response=conn.getresponse(); raw=response.read()
        result=raw.decode() if response.getheader('Content-Type','').startswith('text/csv') else json.loads(raw)
        cookie=response.getheader('Set-Cookie'); status=response.status; conn.close()
        return status,result,cookie

    def register(self,email):
        status,result,cookie=self.request('POST','/api/auth/register',dict(email=email,password='correct horse battery'))
        self.assertEqual(status,200)
        return result['user'],cookie

    def test_household_isolation_versions_and_job_access(self):
        a,ca=self.register('a@example.com'); b,cb=self.register('b@example.com')
        status,plan,_=self.request('POST','/api/plans',{'name':'A','plan':{'age':40}},ca)
        self.assertEqual(status,201); ident=plan['id']
        for route in [f'/api/plans/{ident}',f'/api/plans/{ident}/revisions',f'/api/plans/{ident}/export',f'/api/plans/{ident}/observations']:
            self.assertEqual(self.request('GET',route,cookie=cb)[0],404)
        self.assertEqual(self.request('PUT',f'/api/plans/{ident}',{'version':1,'plan':{'age':41}},ca)[0],200)
        self.assertEqual(self.request('PUT',f'/api/plans/{ident}',{'version':1,'plan':{}},ca)[0],409)
        revisions=self.request('GET',f'/api/plans/{ident}/revisions',cookie=ca)[1]['revisions']
        self.assertEqual([r['plan']['age'] for r in revisions],[40,41])
        _,result,_=self.request('POST',f'/api/plans/{ident}/run',{'kind':'project'},ca)
        job=result['job']['id']
        self.assertEqual(self.request('GET',f'/api/jobs/{job}',cookie=cb)[0],404)
        self.assertEqual(self.request('POST',f'/api/jobs/{job}/cancel',{},ca)[1]['job']['status'],'cancelled')

    def test_read_only_role_and_csrf(self):
        a,ca=self.register('owner@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{}},ca)
        with self.server.store.connect() as db:
            db.execute("UPDATE users SET role='viewer' WHERE id=?",(a['id'],))
        self.assertEqual(self.request('GET',f"/api/plans/{plan['id']}",cookie=ca)[0],200)
        self.assertEqual(self.request('PUT',f"/api/plans/{plan['id']}",{'version':1,'plan':{}},ca)[0],403)
        self.assertEqual(self.request('GET',f"/api/plans/{plan['id']}/export",cookie=ca)[0],403)
        self.assertEqual(self.request('GET',f"/api/plans/{plan['id']}/export?format=csv",cookie=ca)[0],200)
        self.assertEqual(self.request('DELETE',f"/api/plans/{plan['id']}",{},ca)[0],403)
        self.assertEqual(self.request('POST','/api/auth/logout',{},ca,origin='https://attacker.example')[0],403)
        self.assertIn('HttpOnly',ca); self.assertIn('SameSite=Strict',ca)

    def test_trusted_oidc_identity_maps_to_existing_owner(self):
        owner,_=self.register('owner@openfi.local')
        _,saved,_=self.request('POST','/api/plans',{'name':'Private plan','plan':{'age':42}},
                               cookie=self.request('POST','/api/auth/login',
                                   {'email':'owner@openfi.local','password':'correct horse battery'})[2])
        with patch.dict(os.environ,{'FIRE_OIDC_OWNER_EMAIL':'owner@openfi.local'}):
            status,reply,_=self.request('GET','/api/auth/me',extra_headers={'X-Forwarded-Email':'joe@example.test'})
            self.assertEqual(status,200)
            self.assertEqual(reply['user']['id'],owner['id'])
            status,plans,_=self.request('GET','/api/plans',extra_headers={'X-Forwarded-Email':'joe@example.test'})
            self.assertEqual(status,200)
            self.assertEqual(plans['plans'][0]['id'],saved['id'])
            status,reply,_=self.request('GET','/api/auth/me')
            self.assertIsNone(reply['user'])

    def test_editor_cannot_delete_plan_or_export_json(self):
        owner,cookie=self.register('delete-owner@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{}},cookie)
        with self.server.store.connect() as db:
            db.execute("UPDATE users SET role='editor' WHERE id=?",(owner['id'],))
        self.assertEqual(self.request('DELETE',f"/api/plans/{plan['id']}",{},cookie)[0],403)
        self.assertEqual(self.request('GET',f"/api/plans/{plan['id']}/export",cookie=cookie)[0],403)
        self.assertEqual(self.request('GET',f"/api/plans/{plan['id']}",cookie=cookie)[0],200)

    def test_invitation_requires_matching_email_and_preserves_plans(self):
        _,owner=self.register('owner2@example.com')
        _,member=self.register('member@example.com')
        _,outsider=self.register('outsider@example.com')
        _,reply,_=self.request('POST','/api/household/invites',{'email':'member@example.com','role':'editor'},owner)
        token=reply['invitation']['token']
        self.assertEqual(self.request('POST','/api/household/join',{'token':token},outsider)[0],404)
        self.assertEqual(self.request('POST','/api/household/join',{'token':token},member)[0],200)
        _,plan,_=self.request('POST','/api/plans',{'name':'Shared','plan':{}},member)
        self.assertEqual(self.request('GET',"/api/plans/"+plan['id'],cookie=owner)[0],200)
        self.assertEqual(self.request('POST','/api/household/invites',{'email':'x@example.com'},member)[0],403)

    def test_worker_durable_completion(self):
        import time
        from fireplanner.server import Worker
        _,cookie=self.register('worker@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{'horizon':2}},cookie)
        _,reply,_=self.request('POST',"/api/plans/"+plan['id']+'/run',{'kind':'project'},cookie)
        worker=Worker(self.server.store)
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                job=self.request('GET','/api/jobs/'+reply['job']['id'],cookie=cookie)[1]['job']
                if job['status'] in ('completed','failed'): break
                time.sleep(.05)
            self.assertEqual(job['status'],'completed')
            self.assertEqual(job['plan_version'],1)
            self.assertTrue(job['result']['annual'])
        finally:
            worker.stop.set(); worker.thread.join(5)

    def test_cancel_running_job_never_publishes_result(self):
        from unittest.mock import patch
        from fireplanner.server import Worker
        entered=threading.Event(); release=threading.Event()
        def blocked(plan,settings):
            entered.set()
            if not release.wait(5): raise RuntimeError('test timed out')
            return {'would_be':'discarded'}
        _,cookie=self.register('cancel@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{}},cookie)
        _,reply,_=self.request('POST',"/api/plans/"+plan['id']+'/run',{'kind':'simulate'},cookie)
        ident=reply['job']['id']
        with patch('fireplanner.engine.simulate',blocked):
            worker=Worker(self.server.store)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.request('POST','/api/jobs/'+ident+'/cancel',{},cookie)[1]['job']['status'],'cancelled')
            finally:
                worker.stop.set(); release.set(); worker.thread.join(5)
        job=self.request('GET','/api/jobs/'+ident,cookie=cookie)[1]['job']
        self.assertEqual(job['status'],'cancelled')
        self.assertIsNone(job['result'])

    def test_restart_exhaustion_and_private_database(self):
        import os
        from fireplanner.store import Store
        _,cookie=self.register('restart@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{}},cookie)
        _,reply,_=self.request('POST',"/api/plans/"+plan['id']+'/run',{'kind':'project'},cookie)
        ident=reply['job']['id']
        with self.server.store.connect() as db:
            db.execute("UPDATE jobs SET status='running',attempts=3 WHERE id=?",(ident,))
        Store(self.server.store.path)
        job=self.request('GET','/api/jobs/'+ident,cookie=cookie)[1]['job']
        self.assertEqual(job['status'],'failed')
        self.assertEqual(os.stat(self.server.store.path).st_mode & 0o777,0o600)
        self.assertEqual(self.request('POST','/api/auth/login',{'email':'restart@example.com','password':'x'*1025})[0],403)

    def test_logout_revokes_session(self):
        _,cookie=self.register('logout@example.com')
        self.assertEqual(self.request('POST','/api/auth/logout',{},cookie)[0],200)
        status,reply,_=self.request('GET','/api/auth/me',cookie=cookie)
        self.assertEqual((status,reply['user']),(200,None))
        self.assertEqual(self.request('GET','/api/plans',cookie=cookie)[0],401)

    def test_scenario_records_validate_name_and_plan(self):
        _,cookie=self.register('scenario-records@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{'horizon':2}},cookie)
        route=f"/api/plans/{plan['id']}/scenarios"
        for invalid in [
            {'name':'  ','plan':{'horizon':2}},
            {'name':'x'*101,'plan':{'horizon':2}},
            {'name':'bad','plan':[]},
            {'name':'bad','plan':{'horizon':0}},
            {'name':'bad','plan':{'horizon':2},'extra':True},
        ]:
            self.assertEqual(self.request('POST',route,invalid,cookie)[0],400)
        status,created,_=self.request('POST',route,{'name':'  Lower spending  ','plan':{'horizon':2}},cookie)
        self.assertEqual(status,200)
        self.assertEqual(created['scenarios'][0]['data'],{'name':'Lower spending','plan':{'horizon':2}})

    def test_purchase_fork_retains_baseline_and_isolates_sibling_changes(self):
        from copy import deepcopy
        _,cookie=self.register('forks@example.com')
        baseline=dict(age=35,horizon=5,valuation_date='2026-09-30',currency='USD',
                      accounts=[dict(balance=300000,return_rate=0)],streams=[],debts=[])
        _,saved,_=self.request('POST','/api/plans',{'name':'Baseline','plan':baseline},cookie)
        route=f"/api/plans/{saved['id']}/scenarios"
        fork=deepcopy(baseline)
        fork['future_purchases']=[dict(id='pool',name='Pool',amount=100000,month=24,annual_upkeep=0)]
        status,reply,_=self.request('POST',route,{'name':'Pool in two years','plan':fork,'baseline_plan':baseline},cookie)
        self.assertEqual(status,200)
        record=reply['scenarios'][0]['data']
        self.assertEqual(record['baseline_plan'],baseline)
        self.assertEqual(record['plan'],fork)
        changed=deepcopy(baseline);changed['accounts'][0]['balance']=900000
        self.assertEqual(self.request('PUT',f"/api/plans/{saved['id']}",{'version':1,'plan':changed},cookie)[0],200)
        records=self.request('GET',route,cookie=cookie)[1]['scenarios']
        self.assertEqual(records[0]['data'],record)
        bad=dict(baseline,currency='EUR')
        self.assertEqual(self.request('POST',route,{'name':'Mismatch','plan':fork,'baseline_plan':bad},cookie)[0],400)
        self.assertEqual(self.request('POST',route,{'name':'Invalid','plan':fork,'baseline_plan':{'horizon':0}},cookie)[0],400)

    def test_observation_records_validate_real_date_balance_and_note(self):
        _,cookie=self.register('observation-records@example.com')
        _,plan,_=self.request('POST','/api/plans',{'plan':{'horizon':2}},cookie)
        route=f"/api/plans/{plan['id']}/observations"
        invalid_rows=[
            {'date':'2025-02-29','balance':10},
            {'date':'2025-2-03','balance':10},
            {'date':'2025-01-01','balance':-0.01},
            {'date':'2025-01-01','balance':True},
            {'date':'2025-01-01','balance':'10'},
            {'date':'2025-01-01','balance':10,'note':'x'*241},
            {'date':'2025-01-01','balance':10,'unexpected':True},
        ]
        for invalid in invalid_rows:
            self.assertEqual(self.request('POST',route,invalid,cookie)[0],400)
        # JSON's non-finite tokens are rejected at the HTTP boundary as well.
        for non_finite in ('NaN','Infinity','-Infinity'):
            conn=http.client.HTTPConnection(*self.server.server_address)
            conn.request('POST',route,'{"date":"2024-02-29","balance":'+non_finite+'}',
                {'Content-Type':'application/json','Cookie':cookie})
            response=conn.getresponse(); response.read(); self.assertEqual(response.status,400); conn.close()
        status,created,_=self.request('POST',route,{'date':'2024-02-29','balance':0,'note':'Baseline'},cookie)
        self.assertEqual(status,200)
        observation=created['observations'][0]['data']
        self.assertEqual(observation,{'date':'2024-02-29','balance':0,'note':'Baseline'})


if __name__=='__main__': unittest.main()
