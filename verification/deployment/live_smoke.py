"""Live-container smoke with recording adapters; never sends external notifications."""
import asyncio,base64,json,subprocess,time,uuid
from pathlib import Path
import httpx
import websockets
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path('/private/tmp/uns-live-smoke')
ENV=dict(line.split('=',1) for line in (ROOT/'service.env').read_text().splitlines())
BASE='http://127.0.0.1:18080'
HEADERS={'Authorization':'Bearer '+ENV['UNS_API_KEY']}
CLIENT=httpx.Client(base_url=BASE,headers=HEADERS,timeout=15)
CHECKS=[]
IDS={}
RUN=uuid.uuid4().hex[:10]
AGENT=str(uuid.uuid4())
def check(name,condition,detail=None):
    if not condition:
        raise AssertionError(f'{name}: {detail}')
    CHECKS.append({'name':name,'passed':True})
    print('PASS',name,flush=True)
def call(method,path,expect=200,**kwargs):
    r=CLIENT.request(method,path,**kwargs)
    check(f'{method} {path.split("?")[0]} -> {expect}',r.status_code==expect,r.text[:500])
    return r.json() if 'json' in r.headers.get('content-type','') else r

def request(name,**changes):
    p={'notification_type':'smoke.safety','intent':'SAFETY','title':'UNS isolated smoke '+name,'message':'Recording-only smoke; no external delivery','source':'deployed-smoke','autonomy_context':{'agent_id':AGENT,'autonomy_mode':'LIVE'},'idempotency_key':RUN+'-'+name,'dedup_key':RUN+'-'+name}
    p.update(changes);return p

def inspect(identifier):
    r=CLIENT.get('/api/v1/runtime/notifications/'+identifier)
    r.raise_for_status();return r.json()
def wait_for(fn,seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=fn()
        if result:return result
        time.sleep(.2)
    raise TimeoutError('smoke predicate did not complete')
def ready():
    try:return CLIENT.get('/ready').json().get('status')=='ready'
    except Exception:return False

def send(name,**changes):
    response=call('POST','/api/v1/notifications',202,json=request(name,**changes))
    IDS[name]=response['notification_id'];return response

def records():
    p=ROOT/'data/recordings.jsonl'
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

def decode(result):
    check('MCP tool result is not an error',not result.isError,str(result.content)[:300])
    return result.structuredContent if result.structuredContent is not None else json.loads(next(c.text for c in result.content if c.type=='text'))

async def websockets_smoke():
    token=base64.urlsafe_b64encode(ENV['UNS_API_KEY'].encode()).decode().rstrip('=')
    async with websockets.connect('ws://127.0.0.1:18080/ws/agents/'+AGENT,subprotocols=['uns.v1','bearer.'+token],origin='http://localhost:5173') as ws:
        check('WebSocket authenticated connection',json.loads(await ws.recv())['type']=='connected')
        payload=request('websocket',notification_type='smoke.informational',intent='INFORMATIONAL',delivery_mode='BEST_EFFORT',require_ack=False)
        r=call('POST','/api/v1/notifications',202,json=payload)
        data=json.loads(await asyncio.wait_for(ws.recv(),5))
        check('WebSocket real network notification',data['type']=='notification' and data['notification']['notification_id']==r['notification_id'])
        check('WebSocket BEST_EFFORT reports delivery',r['status']=='DELIVERED',r)
        pending=send('websocket-ack')
        await ws.send(json.dumps({'type':'ack','notification_id':pending['notification_id']}))
        response=json.loads(await asyncio.wait_for(ws.recv(),5))
        check('WebSocket durable attributed ACK',response.get('ack_status')=='ACKED' and response.get('acked_by')=='smoke-operator',response)
        check('WebSocket ACK visible over HTTP',inspect(pending['notification_id'])['ack_status']=='ACKED')
    try:
        async with websockets.connect('ws://127.0.0.1:18080/ws/agents/'+AGENT):
            raise AssertionError('Unauthenticated websocket connected')
    except websockets.exceptions.InvalidStatus as exc:
        check('WebSocket rejects unauthenticated upgrade',exc.response.status_code in (401,403))

async def mcp_smoke():
    params=StdioServerParameters(command='docker',args=['exec','-i','uns-smoke-e759','python','/profile/mcp_profile.py'])
    async with stdio_client(params) as (read,write),ClientSession(read,write) as client:
        await client.initialize()
        names={t.name for t in (await client.list_tools()).tools}
        check('Live stdio MCP tool registry',len(names)==16 and 'send_signal' in names)
        status=decode(await client.call_tool('get_notification_status',{'notification_id':IDS['ack']}))
        check('MCP sees HTTP durable ACK',status['ack_status']=='ACKED',status)
        payload=request('mcp')
        preview=decode(await client.call_tool('simulate_signal',{'payload':payload}))
        check('MCP simulation is marked simulated',preview.get('simulated') is True,preview)
        delivered=decode(await client.call_tool('send_signal',{'payload':{**payload,'deliver':True,'operator_intent':'deliver','operator_confirmation_token':ENV['UNS_MCP_DELIVERY_CONFIRMATION_TOKEN']}}))
        check('MCP recording delivery',delivered['status']=='DELIVERED',delivered)
        repeat=call('POST','/api/v1/notifications',202,json=payload)
        check('HTTP/MCP cross-transport idempotency',repeat['notification_id']==delivered['notification_id'] and repeat['idempotent_replay'])
        ack=decode(await client.call_tool('ack_notification',{'payload':{'notification_id':delivered['notification_id']}}))
        check('MCP acknowledgment visible over HTTP',inspect(delivered['notification_id'])['ack_status']=='ACKED',ack)
        policy_args={'notification_type':'smoke.safety','intent':'SAFETY','autonomy_mode':'LIVE'}
        before_policy=decode(await client.call_tool('get_effective_policy',policy_args))
        check('MCP sees initial durable policy',before_policy['effective']['ack_timeout_minutes']==1)
        call('POST','/api/v1/policies/reload',json={'policy_dir':'/profile/policies-v2'})
        after_policy=decode(await client.call_tool('get_effective_policy',policy_args))
        check('Running MCP observes HTTP policy activation',after_policy['effective']['ack_timeout_minutes']==2)
        check('Accepted obligation keeps original deadline policy',inspect(IDS['timeout'])['notification']['ack_timeout_minutes']==1)


def main():
    wait_for(ready,20)
    check('Health public',httpx.get(BASE+'/health').status_code==200)
    for path in ('/ready','/metrics','/ui/audit','/api/v1/runtime/dead-letters'):
        check('Unauthenticated '+path+' rejected',httpx.get(BASE+path).status_code==401)
        check('Wrong credential '+path+' rejected',httpx.get(BASE+path,headers={'Authorization':'Bearer wrong'}).status_code==401)
    check('Readiness checks durable profile',call('GET','/ready')['status']=='ready')
    identity=call('GET','/__smoke__/identity')
    check('Running deployment revision/profile',identity['revision']==ENV['SMOKE_REVISION'] and identity['profile']=='recording-only-local-smoke')
    call('GET','/metrics')
    for path in ('/','/deliveries','/policy','/invariants','/audit'):
        r=call('GET',path);check('SPA served at '+path,'<div id="root"></div>' in r.text)
    before=len(records())
    preview=call('POST','/api/v1/notifications/simulate',json=request('preview'))
    check('HTTP simulation has no provider effect',preview['simulated'] and len(records())==before)
    check('Simulation has no durable notification',CLIENT.get('/api/v1/runtime/notifications/'+preview['notification_id']).status_code==404)
    call('POST','/api/v1/notifications',422,json=request('downgrade',delivery_mode='BEST_EFFORT'))
    call('POST','/api/v1/notifications',422,json=request('routing',metadata={'slack_channel':'forbidden'}))
    first=send('ack')
    check('Guaranteed recording delivery',first['status']=='DELIVERED' and 'SLACK' in first['channels_succeeded'])
    row=inspect(first['notification_id'])
    check('Policy revision and effective provenance retained',bool(row['notification']['metadata']['uns_resolution']['snapshot_revision']))
    check('Channel completion evidence retained',any(e['kind']=='CHANNEL_ATTEMPT_RESULT' for e in row['events']))
    repeat=send('ack')
    check('Same-content replay retains identity',repeat['notification_id']==first['notification_id'] and repeat['idempotent_replay'])
    call('POST','/api/v1/notifications',409,json=request('ack',message='Changed content'))
    duplicate=send('duplicate',dedup_key=RUN+'-ack')
    check('Semantic duplicate suppressed after delivery',duplicate['status']=='DEDUPLICATED')
    call('POST','/api/v1/notifications/'+first['notification_id']+'/ack',403,json={'acked_by':'imposter'})
    acknowledged=call('POST','/api/v1/notifications/'+first['notification_id']+'/ack',json={})
    check('ACK attributed to credential principal',acknowledged['acked_by']=='smoke-operator')
    audit=call('GET','/ui/audit?notification_id='+first['notification_id'])
    ack_events=[e for e in audit['items'] if e['event_type']=='ack.received']
    check('Audit ACK preserves actual LIVE context and agent',len(ack_events)==1 and ack_events[0]['autonomy_context']['autonomy_mode']=='LIVE' and ack_events[0]['autonomy_context']['agent_id']==AGENT)
    check('Audit timestamps have explicit UTC offset',all(e['event_time'].endswith(('Z','+00:00')) for e in audit['items']))
    filtered=call('GET','/ui/audit?notification_id='+first['notification_id']+'&autonomy_mode=PREVIEW')
    check('Audit mode filter excludes LIVE ACK',filtered['items']==[])
    repeated=call('POST','/api/v1/notifications/'+first['notification_id']+'/ack',json={})
    check('Repeated ACK retains original result',acknowledged==repeated)
    call('POST','/api/v1/notifications/'+first['notification_id']+'/dismiss',409,json={})
    dismissed=send('dismiss')
    check('Dismiss transition',call('POST','/api/v1/notifications/'+dismissed['notification_id']+'/dismiss',json={})['ack_status']=='DISMISSED')
    timeout=send('timeout')
    failure=send('failure',metadata={'smoke_fail':True})
    wait_for(lambda:inspect(failure['notification_id'])['status']=='FAILED',15)
    check('Worker exhausts recording failures',inspect(failure['notification_id'])['attempts']==3)
    check('Dead-letter inspection retains failed obligation',any(r['notification_id']==failure['notification_id'] for r in call('GET','/api/v1/runtime/dead-letters')))
    (ROOT/'data/allow-recovery').touch()
    call('POST','/api/v1/runtime/notifications/'+failure['notification_id']+'/replay')
    wait_for(lambda:inspect(failure['notification_id'])['status']=='DELIVERED')
    recovered=inspect(failure['notification_id'])
    check('Replay recovery preserves cumulative attempts',recovered['cycle']==2 and recovered['attempts']==4)
    call('POST','/api/v1/notifications/'+failure['notification_id']+'/ack',json={})
    for path in ('/ui/deliveries','/ui/audit','/ui/invariants','/ui/invariants/summary','/ui/deliveries/'+first['notification_id'],'/ui/policies/effective?notification_type=smoke.safety&intent=SAFETY&autonomy_mode=LIVE'):
        call('GET',path)
    summary=call('GET','/ui/invariants/summary')
    check('Summary timestamp has explicit UTC offset',summary['last_updated'].endswith('+00:00'))
    asyncio.run(websockets_smoke())
    asyncio.run(mcp_smoke())
    print('Waiting for real one-minute timeout worker...',flush=True)
    wait_for(lambda:inspect(timeout['notification_id'])['ack_status']=='TIMED_OUT',65)
    check('Real deadline timeout worker',inspect(timeout['notification_id'])['actor']=='uns-timeout-worker')
    call('POST','/api/v1/notifications/'+timeout['notification_id']+'/ack',409,json={})
    wait_for(lambda: all(not e['callback_pending'] for e in inspect(timeout['notification_id'])['events']),10)
    callbacks=[json.loads(line) for line in (ROOT/'data/callbacks.jsonl').read_text().splitlines()]
    check('Callback retries retain event identity',any(e['notification_id']==timeout['notification_id'] and e['attempt']==2 for e in callbacks))
    subprocess.run(['docker','stop','-t','10','uns-smoke-e759'],check=True,capture_output=True)
    seed="from runtime_profile import make_runtime; from uns.responses import SendNotificationRequest; import json,sys; r=make_runtime(); n=r.accept(SendNotificationRequest(**json.load(sys.stdin)),principal='smoke-operator'); print(n.notification_id); r.engine.dispose()"
    result=subprocess.run(['docker','run','--rm','-i','--env-file',str(ROOT/'service.env'),'--mount',f'type=bind,src={ROOT}/profile,dst=/profile,readonly','--mount',f'type=bind,src={ROOT}/data,dst=/data','uns:local-smoke','python','-c',seed],input=json.dumps(request('restart')),capture_output=True,text=True,check=True)
    pending=result.stdout.strip()
    subprocess.run(['docker','start','uns-smoke-e759'],check=True,capture_output=True)
    wait_for(ready,20)
    wait_for(lambda:inspect(pending)['status']=='DELIVERED')
    check('Pending work recovers after real service restart',inspect(pending)['attempts']==1)
    check('ACK survives service restart',inspect(first['notification_id'])['ack_status']=='ACKED')
    call('POST','/api/v1/notifications/'+pending+'/ack',json={})
    IDS['restart']=pending
    print('SMOKE COMPLETE',len(CHECKS),'checks',flush=True)

try:
    main()
except BaseException as exc:
    (ROOT/'results.json').write_text(json.dumps({'status':'failed','error':str(exc),'checks':CHECKS,'ids':IDS,'revision':ENV['SMOKE_REVISION']},indent=2)+'\n')
    raise
else:
    (ROOT/'results.json').write_text(json.dumps({'status':'passed','checks':CHECKS,'ids':IDS,'revision':ENV['SMOKE_REVISION'],'profile':'recording-only','real_external_delivery':False},indent=2)+'\n')
