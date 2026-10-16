import json
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_api
from fireplanner.server import Worker, make_server
from fireplanner.store import Store
from fireplanner.mcp import Bridge
from fireplanner.engine import VERSION


class DurableRunsTests(unittest.TestCase):
    setUp=test_api.APITest.setUp
    tearDown=test_api.APITest.tearDown
    request=test_api.APITest.request
    register=test_api.APITest.register

    def baseline(self,cookie):
        plan=dict(name='Baseline',age=40,retirement_age=41,horizon=2,valuation_date='2026-09-30',
            return_rate=0,withdrawal_rate=.04,accounts=[dict(id='cash',type='cash',balance=1000,return_rate=0,metadata={'keep':'source'})],
            streams=[dict(id='spending',kind='expense',amount=10,every_months=1)],debts=[],metadata={'notes':'Known inputs'})
        return self.request('POST','/api/plans',{'name':'Baseline','plan':plan},cookie)[1]

    def wait_job(self,ident,cookie):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            job=self.request('GET','/api/jobs/'+ident,cookie=cookie)[1]['job']
            if job['status'] in ('completed','failed','cancelled'):return job
            time.sleep(.03)
        self.fail('Worker did not finish the synthetic calculation')

    def test_scenario_snapshots_runs_and_results_survive_updates_and_restart(self):
        _,cookie=self.register('durable@example.test');saved=self.baseline(cookie);route='/api/plans/'+saved['id']
        status,reply,_=self.request('POST',route+'/scenarios',{'name':'Higher spending','base_version':1,
            'changes':{'streams':[dict(id='spending',kind='expense',amount=20,every_months=1)]},
            'metadata':{'rationale':'Synthetic expense stress test','status':'illustrative'}},cookie)
        self.assertEqual(status,200);scenario=reply['scenarios'][-1]
        self.assertEqual(scenario['data']['baseline_plan'],saved['plan'])
        self.assertEqual(scenario['data']['base_version'],1)
        self.assertEqual(self.request('GET',route,cookie=cookie)[1]['version'],1)
        _,reply,_=self.request('POST',route+'/scenarios/'+scenario['id']+'/run',{'kind':'project','metadata':{'origin':'ChatGPT'}},cookie)
        job_id=reply['job']['id'];worker=Worker(self.server.store)
        try:
            job=self.wait_job(job_id,cookie)
            self.assertEqual(job['status'],'completed')
            self.assertEqual(job['result']['annual'][0]['expenses'],240)
            self.assertEqual(job['result']['baseline_projection']['annual'][0]['expenses'],120)
            self.assertEqual(job['snapshot']['plan']['streams'][0]['amount'],20)
            self.assertEqual(job['snapshot']['scenario_metadata']['status'],'illustrative')
            self.assertEqual(job['snapshot']['metadata']['origin'],'ChatGPT')
            self.assertEqual(job['plan_version'],1)
            self.assertEqual(job['result']['metadata']['engine_version'],VERSION)
        finally:
            worker.stop.set();worker.thread.join(5)
        self.request('PATCH',route,{'version':1,'changes':{'age':42,'metadata':{'notes':'Newer inputs'}}},cookie)
        # A fresh server process sees the same snapshot and result, not a recalculation.
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.server=make_server(port=0,database=Path(self.tmp.name)/'test.db',workers=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        status,history,_=self.request('GET',route+'/runs',cookie=cookie)
        self.assertEqual(status,200);self.assertEqual(history['runs'][0]['id'],job_id)
        self.assertEqual(history['runs'][0]['result']['summary'],job['result']['summary'])
        self.assertNotIn('annual',history['runs'][0]['result'])
        self.assertEqual(self.request('GET','/api/jobs/'+job_id,cookie=cookie)[1]['job'],job)
        self.assertEqual(self.request('GET',route+'/scenarios/'+scenario['id'],cookie=cookie)[1]['scenario'],scenario)

    def test_history_permissions_pagination_failures_and_immutable_reruns(self):
        user,cookie=self.register('history@example.test');_,other=self.register('outside@example.test')
        saved=self.baseline(cookie);route='/api/plans/'+saved['id'];jobs=[]
        for kind in ('project','simulate','project'):
            _,reply,_=self.request('POST',route+'/run',{'kind':kind,'version':1,'settings':{'trials':0} if kind=='simulate' else {}},cookie)
            jobs.append(reply['job']['id'])
        self.request('POST','/api/jobs/'+jobs[2]+'/cancel',{},cookie)
        worker=Worker(self.server.store)
        try:
            self.assertEqual(self.wait_job(jobs[0],cookie)['status'],'completed')
            self.assertEqual(self.wait_job(jobs[1],cookie)['status'],'failed')
        finally:worker.stop.set();worker.thread.join(5)
        first=self.request('GET',route+'/runs?limit=2',cookie=cookie)[1]
        second=self.request('GET',route+'/runs?limit=2&before='+first['next_cursor'],cookie=cookie)[1]
        self.assertEqual([r['id'] for r in first['runs']+second['runs']],list(reversed(jobs)))
        self.assertIsNone(second['next_cursor'])
        for path in (route+'/runs','/api/jobs/'+jobs[0]):self.assertEqual(self.request('GET',path,cookie=other)[0],404)
        self.assertEqual(self.request('GET',route+'/runs?limit=0',cookie=cookie)[0],400)
        self.assertEqual(self.request('POST',route+'/run',{'version':0},cookie)[0],409)
        with self.server.store.connect() as db:db.execute("UPDATE users SET role='viewer' WHERE id=?",(user['id'],))
        self.assertEqual(self.request('GET',route+'/runs',cookie=cookie)[0],200)
        self.assertEqual(self.request('POST',route+'/run',{},cookie)[0],403)

    def test_scenarios_reject_stale_baselines_and_foreign_ids(self):
        _,cookie=self.register('scenario-auth@example.test');_,other=self.register('scenario-other@example.test')
        a=self.baseline(cookie);b=self.baseline(cookie);route='/api/plans/'+a['id']
        data={'name':'Test','base_version':1,'changes':{},'metadata':{'rationale':'Testing'}}
        scenario=self.request('POST',route+'/scenarios',data,cookie)[1]['scenarios'][-1]
        self.assertEqual(self.request('GET',route+'/scenarios/'+scenario['id'],cookie=other)[0],404)
        self.assertEqual(self.request('POST','/api/plans/'+b['id']+'/scenarios/'+scenario['id']+'/run',{},cookie)[0],404)
        self.request('PATCH',route,{'version':1,'changes':{'age':41}},cookie)
        self.assertEqual(self.request('POST',route+'/scenarios',data,cookie)[0],409)
        self.assertEqual(self.request('POST',route+'/scenarios',{'name':'False baseline','plan':a['plan'],'base_version':2,'baseline_plan':a['plan']},cookie)[0],400)
        self.assertEqual(len(self.request('GET',route+'/scenarios',cookie=cookie)[1]['scenarios']),1)

    def test_mcp_finances_balance_update_scenario_and_real_calculation(self):
        self.register('mcp@example.test')
        token=self.request('POST','/api/auth/token',{'email':'mcp@example.test','password':'correct horse battery'})[1]['access_token']
        url='http://%s:%d'%self.server.server_address
        session=Path(self.tmp.name)/'session.json';session.write_text(json.dumps({'url':url,'token':token}))
        bridge=Bridge(url,session)
        self.assertIn('Persist every proposed scenario',bridge.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}})['result']['instructions'])
        saved=bridge.call('create_plan',{'name':'MCP baseline','plan':{'age':40,'horizon':2,'retirement_age':41,'return_rate':0,'accounts':[dict(id='checking',type='cash',balance=1000,return_rate=0,metadata={'keep':'yes'})],'streams':[dict(kind='expense',amount=10)],'debts':[]}})
        ident=saved['id']
        updated=bridge.call('update_account_balances',{'plan_id':ident,'version':1,'source':'Finances','as_of':'2026-09-30','balances':[{'account_id':'checking','balance':1200,'source_account_id':'external-checking'}]})
        account=updated['plan']['accounts'][0]
        self.assertEqual(account['metadata']['keep'],'yes');self.assertEqual(account['return_rate'],0)
        self.assertEqual(account['metadata']['balance_source']['provider'],'Finances')
        self.assertEqual(account['balance'],1200)
        scenario=bridge.call('create_scenario',{'plan_id':ident,'name':'Lower spending','base_version':2,'changes':{'streams':[dict(kind='expense',amount=5)]},'metadata':{'rationale':'Synthetic case'}})['scenario']
        job=bridge.call('run_scenario',{'plan_id':ident,'scenario_id':scenario['id'],'kind':'project','metadata':{'origin':'ChatGPT'}})['job']
        worker=Worker(self.server.store)
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                read=bridge.call('get_run',{'run_id':job['id'],'include_inputs':True,'detail':'annual'})['job']
                if read['status'] in ('completed','failed'):break
                time.sleep(.03)
            self.assertEqual(read['status'],'completed')
            self.assertEqual(read['result']['summary']['ending_assets'],1080)
            self.assertEqual(read['annual'][0]['expenses'],60)
            self.assertEqual(read['snapshot']['baseline_plan']['accounts'][0]['balance'],1200)
            self.assertEqual(bridge.call('list_runs',{'plan_id':ident})['runs'][0]['id'],job['id'])
        finally:worker.stop.set();worker.thread.join(5)
        error=bridge.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'update_account_balances','arguments':{'plan_id':ident,'version':1,'source':'Finances','as_of':'2026-09-30','balances':[{'account_id':'guess','balance':0}]}}})
        self.assertTrue(error['result']['isError'])
        self.assertEqual(bridge.call('get_plan',{'plan_id':ident})['version'],2)

    def test_stdio_protocol_does_not_log_credentials_and_reads_real_history(self):
        self.register('stdio@example.test')
        token=self.request('POST','/api/auth/token',{'email':'stdio@example.test','password':'correct horse battery'})[1]['access_token']
        session=Path(self.tmp.name)/'session.json';session.write_text(json.dumps({'url':'http://%s:%d'%self.server.server_address,'token':token}))
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'list_plans','arguments':{}}}]
        run=subprocess.run([sys.executable,'-m','fireplanner.mcp','--url','http://%s:%d'%self.server.server_address,'--session-file',str(session)],input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0);self.assertEqual(run.stderr,'');self.assertNotIn(token,run.stdout)
        responses=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual([r['id'] for r in responses],[1,2,3])
        self.assertTrue(any(t['name']=='run_scenario' for t in responses[1]['result']['tools']))
        self.assertEqual(responses[2]['result']['structuredContent'],{'plans':[]})
