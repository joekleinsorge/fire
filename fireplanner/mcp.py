"""Single-user stdio MCP bridge to the authenticated Open FI HTTP API.

Use locally with MCP clients or behind a private, account-restricted Secure MCP
Tunnel. This process has the authority of the local planner session. It never
opens a network listener and must not be shared as an anonymous public service.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote
from .client import authenticated_client
from .store import run_summary

INSTRUCTIONS = '''Use the planner as the source of truth. Read the saved plan and version before edits.
Persist every proposed scenario with its baseline, changed assumptions, rationale, and provenance.
Run saved plans or scenarios through run_plan/run_scenario, then use get_run until the job completes.
Report the saved plan/scenario/run IDs with numerical conclusions; never present queued or failed jobs as results.
Keep user-confirmed inputs separate from illustrative assumptions; unknowns must stay unknown.
Changing a plan return does not override account-specific returns. Change those rates explicitly when intended.
Every calculation here is logged with immutable inputs and stored results; old runs are read without recalculation.
'''

ID = {'type':'string','minLength':1,'description':'Saved identifier returned by this planner.'}
OBJECT = {'type':'object','additionalProperties':True}
PLAN = {'type':'object','additionalProperties':True,'properties':{
    'name':{'type':'string'},'age':{'type':'integer'},'horizon':{'type':'integer'},
    'retirement_age':{'type':'integer'},'return_rate':{'type':'number'},
    'withdrawal_rate':{'type':'number'},'valuation_date':{'type':'string'},
    'currency':{'type':'string'},'metadata':OBJECT,
    **{key:{'type':'array','items':OBJECT} for key in
       ('accounts','streams','debts','members','child_accounts','future_purchases')}}}


def tool(name, title, description, properties=None, required=(), read_only=True):
    return dict(name=name,title=title,description=description,
        inputSchema={'type':'object','properties':properties or {},'required':list(required),'additionalProperties':False},
        annotations={'readOnlyHint':read_only,'destructiveHint':False,'openWorldHint':False})


TOOLS = [
    tool('get_profile','Planner account','Identify the authenticated planner account and household.'),
    tool('get_capabilities','Calculation capabilities','Read supported calculations and model limitations.'),
    tool('list_plans','Saved plans','List saved plan IDs, names, and versions. Read the full plan before updating it.'),
    tool('get_plan','Read plan inputs','Read complete saved assumptions, holdings, notes, and metadata.',{'plan_id':ID},['plan_id']),
    tool('create_plan','Save a new plan','Persist a complete household plan and its first revision. Rates are decimals, money is real purchasing power. Requires explicit full-plan account, stream, and debt arrays.',
        {'name':{'type':'string'},'plan':PLAN},['name','plan'],False),
    tool('update_plan','Save plan changes','Apply a version-checked JSON Merge Patch. Objects merge; arrays replace in full; null deletes. Preserve unknown fields and record provenance in metadata. Returns the new saved revision.',
        {'plan_id':ID,'version':{'type':'integer'},'changes':OBJECT},['plan_id','version','changes'],False),
    tool('update_account_balances','Save sourced account balances','Save balances retrieved from the user’s Finances plugin or supplied documents. Match explicit existing planner account IDs, never guess name matches. Preserve returns, fees, access, and all unrelated records. Record source dates without automatically moving the whole plan valuation date; review mixed dates before modeling.',
        {'plan_id':ID,'version':{'type':'integer'},'source':{'type':'string'},'as_of':{'type':'string'},
         'balances':{'type':'array','items':{'type':'object','properties':{'account_id':ID,'balance':{'type':'number'},'source_account_id':{'type':'string'}},'required':['account_id','balance'],'additionalProperties':False}}},
        ['plan_id','version','source','as_of','balances'],False),
    tool('create_scenario','Save scenario assumptions','Save an immutable scenario from a saved baseline revision using a JSON Merge Patch. Record the rationale and which values are illustrative in metadata. Does not modify the baseline. Each alternative must be saved separately.',
        {'plan_id':ID,'name':{'type':'string'},'base_version':{'type':'integer'},'changes':OBJECT,'metadata':OBJECT},
        ['plan_id','name','base_version','changes','metadata'],False),
    tool('list_scenarios','Saved scenarios','List saved scenario IDs, assumptions, baseline snapshots, and metadata.',{'plan_id':ID},['plan_id']),
    tool('get_scenario','Read a saved scenario','Read an immutable saved scenario and its baseline.',{'plan_id':ID,'scenario_id':ID},['plan_id','scenario_id']),
    tool('run_plan','Log a plan calculation','Queue a real engine projection or seeded simulation of a saved plan revision. Always creates durable run history. Retrieve get_run until completed before reporting numbers.',
        {'plan_id':ID,'version':{'type':'integer'},'kind':{'type':'string','enum':['project','simulate']},'settings':OBJECT,'metadata':OBJECT},['plan_id','version','kind','metadata'],False),
    tool('run_scenario','Log a scenario calculation','Queue a real engine calculation of the exact saved scenario. Every invocation creates a separate durable run. Use get_run for status and results.',
        {'plan_id':ID,'scenario_id':ID,'kind':{'type':'string','enum':['project','simulate']},'settings':OBJECT,'metadata':OBJECT},['plan_id','scenario_id','kind','metadata'],False),
    tool('list_runs','Calculation history','List saved runs, results summaries, timestamps, scenario IDs, assumptions versions, and notes. Follow next_cursor to retrieve older runs.',
        {'plan_id':ID,'before':{'type':'string'}},['plan_id']),
    tool('get_run','Read logged results','Read a stored calculation without rerunning it. Summary is default; annual includes annual values or simulation percentile bands. Include inputs to inspect the exact assumptions used. Queued/failed jobs have no usable result.',
        {'run_id':ID,'detail':{'type':'string','enum':['summary','annual']},'include_inputs':{'type':'boolean'}},['run_id']),
]


def validate(value, schema):
    types={'object':dict,'array':list,'string':str,'integer':int,'number':(int,float),'boolean':bool}
    kind=schema.get('type')
    if kind and (not isinstance(value,types[kind]) or kind in ('integer','number') and isinstance(value,bool)):
        raise ValueError('Invalid argument type: expected '+kind)
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Unsupported argument value')
    if kind=='object':
        props=schema.get('properties',{})
        if any(k not in value for k in schema.get('required',[])):
            raise ValueError('Missing required tool argument')
        if schema.get('additionalProperties') is False and set(value)-set(props):
            raise ValueError('Unexpected tool argument')
        for key in props.keys() & value.keys():validate(value[key],props[key])
    if kind=='array':
        for item in value:validate(item,schema.get('items',{}))
    if kind=='string' and len(value)<schema.get('minLength',0):raise ValueError('Identifier cannot be empty')


def compact_job(job):
    return {key:value for key,value in job.items() if key not in ('snapshot','result')} | {'result':run_summary(job.get('result'))}


class Bridge:
    def __init__(self, url, session_file):
        self.url=url
        self.session_file=session_file

    def call(self, name, args):
        definition=next((t for t in TOOLS if t['name']==name),None)
        if not definition:raise ValueError('Unknown planner tool')
        validate(args,definition['inputSchema'])
        client=authenticated_client(self.url,self.session_file)
        plan_path='/api/plans/'+quote(args.get('plan_id',''),safe='')
        if name=='get_profile':return client.request('GET','/api/auth/me')
        if name=='get_capabilities':return client.request('GET','/api/capabilities')
        if name=='list_plans':return {'plans':[{k:p[k] for k in ('id','name','version')} for p in client.request('GET','/api/plans')['plans']]}
        if name=='get_plan':return client.request('GET',plan_path)
        if name=='create_plan':
            if not all(isinstance(args['plan'].get(k),list) for k in ('accounts','streams','debts')):
                raise ValueError('Provide explicit accounts, streams, and debts arrays; use [] when none are known')
            return client.request('POST','/api/plans',args)
        if name=='update_plan':return client.request('PATCH',plan_path,{k:args[k] for k in ('version','changes')})
        if name=='update_account_balances':
            from datetime import date
            if date.fromisoformat(args['as_of']).isoformat()!=args['as_of']:
                raise ValueError('as_of must be YYYY-MM-DD')
            if not args['source'].strip() or not args['balances']:
                raise ValueError('Provide a source and at least one balance')
            current=client.request('GET',plan_path)
            if current['version']!=args['version']:raise ValueError('Plan changed; reload before saving balances')
            accounts=current['plan'].get('accounts',[])
            by_id={account.get('id'):account for account in accounts}
            seen=set()
            for update in args['balances']:
                ident=update['account_id']
                if ident in seen or ident not in by_id:raise ValueError('Every balance must name one unique existing account ID')
                seen.add(ident);account=by_id[ident]
                account['balance']=update['balance']
                provenance={'provider':args['source'],'as_of':args['as_of']}
                if update.get('source_account_id'):provenance['source_account_id']=update['source_account_id']
                account['metadata']={**account.get('metadata',{}),'balance_source':provenance}
            return client.request('PATCH',plan_path,{'version':args['version'],'changes':{'accounts':accounts}})
        if name=='create_scenario':
            reply=client.request('POST',plan_path+'/scenarios',{k:args[k] for k in ('name','base_version','changes','metadata')})
            return {'scenario':reply['scenario']}
        if name=='list_scenarios':return client.request('GET',plan_path+'/scenarios')
        if name=='get_scenario':return client.request('GET',plan_path+'/scenarios/'+quote(args['scenario_id'],safe=''))
        if name in ('run_plan','run_scenario'):
            path=plan_path+('/scenarios/'+quote(args['scenario_id'],safe='') if name=='run_scenario' else '')+'/run'
            data={k:args[k] for k in ('kind','settings','metadata','version') if k in args}
            return {'job':compact_job(client.request('POST',path,data)['job'])}
        if name=='list_runs':return client.request('GET',plan_path+'/runs'+('?before='+quote(args['before'],safe='') if args.get('before') else ''))
        job=client.request('GET','/api/jobs/'+quote(args['run_id'],safe=''))['job']
        output=compact_job(job)
        snapshot=job['snapshot']
        output['provenance']={k:v for k,v in snapshot.items() if k not in ('plan','baseline_plan')}
        if args.get('include_inputs'):output['snapshot']=snapshot
        if args.get('detail')=='annual' and job['result']:
            output['annual']=job['result'].get('annual',job['result'].get('annual_bands',[]))
        return {'job':output}

    def dispatch(self, request):
        if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':
            return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid JSON-RPC request'}}
        if 'id' not in request:return None
        ident=request['id'];method=request.get('method');params=request.get('params') or {}
        if not isinstance(params,dict):return {'jsonrpc':'2.0','id':ident,'error':{'code':-32602,'message':'Params must be an object'}}
        if method=='initialize':
            supported=('2025-11-25','2025-06-18','2025-03-26','2024-11-05')
            version=params.get('protocolVersion')
            result={'protocolVersion':version if version in supported else supported[0],'capabilities':{'tools':{}},
                'serverInfo':{'name':'open-fi-planner','version':'1.0.0'},'instructions':INSTRUCTIONS}
        elif method=='ping':result={}
        elif method=='tools/list':result={'tools':TOOLS}
        elif method=='tools/call':
            try:
                content=self.call(params.get('name'),params.get('arguments',{}))
                result={'content':[{'type':'text','text':json.dumps(content,allow_nan=False)}],'structuredContent':content,'isError':False}
            except (ValueError,OSError,KeyError,TypeError) as exc:
                result={'content':[{'type':'text','text':str(exc)}],'isError':True}
        else:return {'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':ident,'result':result}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default=os.environ.get('OPENFI_URL','http://127.0.0.1:8080'))
    parser.add_argument('--session-file',type=Path,default=Path(os.environ.get('OPENFI_SESSION_FILE',Path.home()/'.config/openfi/session.json')))
    args=parser.parse_args();bridge=Bridge(args.url,args.session_file)
    while True:
        line=sys.stdin.buffer.readline(1048577)
        if not line:break
        if len(line)>1048576:
            response={'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Request exceeds 1 MiB'}}
        else:
            try:response=bridge.dispatch(json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite number'))))
            except (ValueError,UnicodeDecodeError):response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON'}}
        if response is not None:
            sys.stdout.write(json.dumps(response,allow_nan=False)+'\n');sys.stdout.flush()
        if len(line)>1048576:break


if __name__=='__main__':main()
