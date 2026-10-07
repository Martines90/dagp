#!/usr/bin/env python3
"""Start a real one-founder DAGP seed, publish discovery, and sign citizen actions.

No LLM dependency. Private keys stay with their owners; the gateway never signs.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import quote,unquote,urlparse
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'chain/node/bin'
RUNTIME=ROOT/'chain/native/runtime.py'
IDENTIFIER=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')

class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args):self.slots=threading.BoundedSemaphore(16);super().__init__(*args)
    def process_request(self,request,address):
        if not self.slots.acquire(False):self.shutdown_request(request);return
        request.settimeout(10)
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

def command(*args,env=None):return subprocess.check_output([str(a) for a in args],text=True,env=env).strip()
def load(path):return json.loads(Path(path).read_text())
def write(path,value,private=False):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    with open(temp,'w',opener=lambda p,f:os.open(p,f,0o600 if private else 0o644)) as file:
        json.dump(value,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
    os.replace(temp,path)
def config(home):return load(Path(home)/'society.json')
def rpc(url,method,params=None,timeout=30):
    data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode()
    with urlopen(Request(url,data,{'Content-Type':'application/json'}),timeout=timeout) as response:result=json.load(response)
    if 'error' in result:raise RuntimeError(result['error'])
    return result['result']
def query(cfg,path,data=b''):
    response=rpc(cfg['rpc'],'abci_query',{'path':path,'data':data.hex()})['response']
    if response.get('code',0):raise RuntimeError(response.get('log'))
    return json.loads(base64.b64decode(response['value']))
def fingerprint():return command(sys.executable,'-I','-B',RUNTIME,'--fingerprint')

def initialize(a):
    home=a.home.resolve()
    if home.exists():raise ValueError('Refusing to overwrite an existing society home or keys')
    if not IDENTIFIER.fullmatch(a.founder) or not IDENTIFIER.fullmatch(a.operator) or not IDENTIFIER.fullmatch(a.family):raise ValueError('Invalid founder identity labels')
    chain=a.chain or 'dagp-seed-'+os.urandom(6).hex()
    if not IDENTIFIER.fullmatch(chain) or len(chain)>64:raise ValueError('Invalid chain ID')
    home.mkdir(parents=True,mode=0o700)
    if not a.skip_build:
        go=a.go or shutil.which('go')
        if not go and Path('/private/tmp/go/bin/go').exists():go='/private/tmp/go/bin/go'
        if not go:raise ValueError('Install Go 1.26.8+ or pass --go /absolute/path/to/go')
        BIN.mkdir(exist_ok=True)
        for tool in ('dagpd','dagp-key','cometbft'):
            subprocess.run([go,'build','-o',str(BIN/tool),'./cmd/'+tool],cwd=ROOT/'chain/node',check=True)
    for tool in ('dagpd','dagp-key','cometbft'):
        if not (BIN/tool).exists():raise ValueError('Missing node tool: '+tool)
    node=home/'node';command(BIN/'cometbft','init','--home',node)
    accounts=home/'keys';accounts.mkdir(mode=0o700)
    account=json.loads(command(BIN/'dagp-key','--generate','--key',accounts/(a.founder+'.json')))
    genesis=load(node/'config/genesis.json')
    now=int(datetime.datetime.fromisoformat(genesis['genesis_time'].replace('Z','+00:00')).timestamp())
    validator=base64.b64decode(load(node/'config/priv_validator_key.json')['pub_key']['value']).hex()
    beacon=dict(public_key='',genesis_time=now,period=1,scheme='bootstrap-disabled')
    charter=dict(identities={a.founder:dict(operator=a.operator,family=a.family,citizen_since=now,roles=['CITIZEN','ADMIN','REGISTRAR'])},
        common_budget=100000,balances={a.founder:200},beacon=beacon,root='root',constraints=[],
        bootstrap=dict(founder=a.founder,validator_key=validator,budget=6000,expires=now+365*86400))
    genesis['chain_id']=chain
    for validator_record in genesis['validators']:validator_record['power']='1'
    genesis['app_state']=dict(chain_id=chain,height=0,accounts={a.founder:account},documents={},
        runtime=dict(version=2,code_hash=fingerprint(),time=now,beacon=beacon,charter=charter))
    write(node/'config/genesis.json',genesis)
    path=node/'config/config.toml';text=path.read_text()
    text=text.replace('tcp://127.0.0.1:26657',f'tcp://127.0.0.1:{a.rpc_port}')
    text=text.replace('tcp://127.0.0.1:26658',f'tcp://127.0.0.1:{a.rpc_port+1}')
    text=text.replace('tcp://0.0.0.0:26656',f'tcp://0.0.0.0:{a.p2p_port}')
    if a.local_peers:text=text.replace('addr_book_strict = true','addr_book_strict = false').replace('allow_duplicate_ip = false','allow_duplicate_ip = true')
    path.write_text(text)
    cfg=dict(schema_version=1,chain_id=chain,founder=a.founder,rpc=f'http://127.0.0.1:{a.rpc_port}',
        abci=f'tcp://127.0.0.1:{a.rpc_port+1}',gateway_port=a.gateway_port,
        public_url=a.public_url or f'http://127.0.0.1:{a.gateway_port}',code_hash=genesis['app_state']['runtime']['code_hash'],
        python_version='.'.join(map(str,sys.version_info[:3])),node_id=command(BIN/'cometbft','show-node-id','--home',node),p2p_port=a.p2p_port)
    cfg['peer']=cfg['node_id']+'@'+(urlparse(cfg['public_url']).hostname or '127.0.0.1')+':'+str(a.p2p_port)
    write(home/'society.json',cfg)
    print(json.dumps(dict(initialized=str(home),chain_id=chain,founder=a.founder,mode='SEED',next_command=f'python3 scripts/society.py start --home {home}'),indent=2))

def start(a):
    home=a.home.resolve();cfg=config(home)
    if cfg['code_hash']!=fingerprint():raise ValueError('Pinned runtime/Python differs from this society genesis; restore the pinned version before starting')
    processes=[];logs=[];server=None
    try:
        for name,args in [('app',[BIN/'dagpd','--state',home/'application.json','--listen',cfg['abci'],'--python',sys.executable,'--governance-runtime',RUNTIME]),
                          ('node',[BIN/'cometbft','start','--home',home/'node'])]:
            log=open(home/(name+'.log'),'a');logs.append(log)
            processes.append(subprocess.Popen([str(x) for x in args],stdout=log,stderr=log))
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in processes):raise RuntimeError('Node startup failed; inspect app.log and node.log')
            try:
                if int(rpc(cfg['rpc'],'status',timeout=2)['sync_info']['latest_block_height'])>=1:break
            except (OSError,RuntimeError):pass
            time.sleep(.25)
        else:raise RuntimeError('Consensus did not start; inspect local logs')
        server=BoundedServer((a.host,cfg['gateway_port']),gateway(home,cfg))
        signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        current=query(cfg,'/export',b'society')['value']['bootstrap']
        print(json.dumps(dict(running=cfg['public_url'],discovery=cfg['public_url']+'/.well-known/dagp-society.json',
            phase=current['phase'],validators=current['validator_count'],
            trust='Validator operators and identity labels require independent verification.'),indent=2),flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if server:server.server_close()
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for file in logs:file.close()

def gateway(home,cfg):
    guard=threading.BoundedSemaphore(16);lock=threading.Lock();hits={}
    def pairs(values):
        out={}
        for k,v in values:
            if k in out:raise ValueError('Duplicate JSON field')
            out[k]=v
        return out
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,code=200,text=False):
            data=(value if text else json.dumps(value,separators=(',',':'))).encode()
            self.send_response(code);self.send_header('Content-Type','text/plain; charset=utf-8' if text else 'application/json')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_GET(self):self.handle_request(False)
        def do_POST(self):self.handle_request(True)
        def handle_request(self,post):
            if not guard.acquire(False):self.reply({'error':'Busy'},429);return
            try:
                self.connection.settimeout(10)
                now=time.monotonic();address=self.client_address[0]
                with lock:
                    recent=[t for t in hits.get(address,[]) if now-t<60]
                    if len(recent)>=600:raise ValueError('Per-address request limit')
                    if address not in hits and len(hits)>=4096:
                        for k in list(hits):
                            if not hits[k] or now-hits[k][-1]>=60:del hits[k]
                        if len(hits)>=4096:raise ValueError('Gateway address capacity')
                    hits[address]=recent+[now]
                path=urlparse(self.path).path
                if not post:
                    if path in ('/society','/.well-known/dagp-society.json','/status'):
                        value=query(cfg,'/export',b'society')
                        self.reply(dict(schema_version=1,name=cfg['chain_id'],chain_id=cfg['chain_id'],gateway=cfg['public_url'],
                            protocol='DAGP/G2',source='https://github.com/Martines90/dagp',
                            actions={'join_request':'/join','signed_transaction':'/submit','accounts':'/accounts','exports':'/export/{key}'},
                            peer=cfg['peer'],genesis='/genesis',
                            authority='Explicit founding stage; no public financial custody',consensus_export=value));return
                    if path=='/accounts':self.reply(query(cfg,'/state'));return
                    if path=='/genesis':self.reply(load(home/'node/config/genesis.json'));return
                    if path=='/health':self.reply({'chain_id':cfg['chain_id'],'node':rpc(cfg['rpc'],'status',timeout=3)['sync_info']});return
                    if path=='/join-requests':
                        with lock:self.reply(load(home/'join-requests.json') if (home/'join-requests.json').exists() else [])
                        return
                    if path.startswith('/export/'):
                        key=unquote(path[len('/export/'):])
                        if not 0<len(key)<=256:raise ValueError('Export key size')
                        self.reply(query(cfg,'/export',key.encode()));return
                    if path=='/llms.txt':self.reply(f'# {cfg["chain_id"]}\n\nDAGP seed society. Read /.well-known/dagp-society.json for the current founding phase and pending consensus decisions. Sign join requests locally; never upload private keys. Bootstrap decisions do not enact ordinary DAGP laws or transfer external funds.\n',text=True);return
                    self.reply({'error':'Unknown route'},404);return
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON content type required')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=125000:raise ValueError('Request size')
                body=json.loads(self.rfile.read(length),object_pairs_hook=pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Finite JSON values required')))
                if path=='/submit':
                    if type(body) is not dict or set(body)!={'tx'}:raise ValueError('Expected base64 signed tx')
                    raw=base64.b64decode(body['tx'],validate=True)
                    if len(raw)>90000:raise ValueError('Transaction size')
                    result=rpc(cfg['rpc'],'broadcast_tx_commit',{'tx':body['tx']},timeout=30)
                    self.reply(dict(txid=hashlib.sha256(raw).hexdigest(),result=result));return
                if path=='/join':
                    with tempfile.NamedTemporaryFile(mode='w',dir=home,suffix='.json') as file:
                        json.dump(body,file);file.flush()
                        verified=json.loads(command(BIN/'dagp-key','--verify-join','--chain',cfg['chain_id'],'--document',file.name))
                    with lock:
                        requests=load(home/'join-requests.json') if (home/'join-requests.json').exists() else []
                        requests=[r for r in requests if r['received']>int(time.time())-86400]
                        if len(requests)>=128 or any(r['request']['account']==verified['account'] for r in requests):raise ValueError('Duplicate request or queue full')
                        requests.append(dict(received=int(time.time()),request=verified));write(home/'join-requests.json',requests,True)
                    self.reply(dict(queued=True,citizenship=False,meaning='Signed expression of interest; eligible citizens must approve invitation and admission'));return
                self.reply({'error':'Unknown route'},404)
            except (ValueError,TypeError,RecursionError,KeyError,OSError,RuntimeError,subprocess.CalledProcessError) as error:
                self.reply({'error':str(error)},400)
            finally:guard.release()
    return Handler

def http(url,path,body=None):
    data=None if body is None else json.dumps(body).encode()
    with urlopen(Request(url.rstrip('/')+path,data,{'Content-Type':'application/json'}),timeout=40) as response:return json.load(response)
def endpoint(a):return a.url or config(a.home)['public_url']
def actor_key(a):
    key=a.key or (a.home/'keys'/(a.actor+'.json') if a.home else None)
    if not key:raise ValueError('Provide your own --key file')
    return key

def observer_initialize(a):
    if not a.url or not a.home:raise ValueError('Observer initialization needs --url and a fresh --home')
    if a.home.exists():raise ValueError('Refusing to overwrite observer keys/state')
    manifest=http(a.url,'/society');genesis=http(a.url,'/genesis')
    if genesis['chain_id']!=manifest['chain_id'] or genesis['app_state']['runtime']['code_hash']!=fingerprint():raise ValueError('Source chain or pinned runtime differs')
    a.home.mkdir(parents=True,mode=0o700);node=a.home/'node';command(BIN/'cometbft','init','--home',node)
    (a.home/'keys').mkdir(mode=0o700);write(node/'config/genesis.json',genesis)
    path=node/'config/config.toml';text=path.read_text()
    text=text.replace('tcp://127.0.0.1:26657',f'tcp://127.0.0.1:{a.rpc_port}').replace('tcp://127.0.0.1:26658',f'tcp://127.0.0.1:{a.rpc_port+1}')
    text=text.replace('tcp://0.0.0.0:26656',f'tcp://0.0.0.0:{a.p2p_port}').replace('persistent_peers = ""','persistent_peers = '+json.dumps(manifest['peer']))
    if a.local_peers:text=text.replace('addr_book_strict = true','addr_book_strict = false').replace('allow_duplicate_ip = false','allow_duplicate_ip = true')
    path.write_text(text)
    node_id=command(BIN/'cometbft','show-node-id','--home',node)
    cfg=dict(schema_version=1,chain_id=genesis['chain_id'],founder=genesis['app_state']['runtime']['charter']['bootstrap']['founder'],
        rpc=f'http://127.0.0.1:{a.rpc_port}',abci=f'tcp://127.0.0.1:{a.rpc_port+1}',gateway_port=a.gateway_port,
        public_url=a.public_url or f'http://127.0.0.1:{a.gateway_port}',code_hash=fingerprint(),python_version='.'.join(map(str,sys.version_info[:3])),
        node_id=node_id,p2p_port=a.p2p_port,source=a.url)
    cfg['peer']=node_id+'@'+(urlparse(cfg['public_url']).hostname or '127.0.0.1')+':'+str(a.p2p_port)
    write(a.home/'society.json',cfg)
    return {'observer_initialized':str(a.home),'voting_power':0,'next':'Start and sync this observer before requesting validator enrollment; remote validators must be reachable.'}

def send(a,operation,args):
    url=endpoint(a);manifest=http(url,'/society');state=http(url,'/accounts')
    account=state['accounts'].get(a.actor,{'sequence':0})
    with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as file:
        json.dump(dict(operation=operation,args=args),file);file.flush()
        raw=command(BIN/'dagp-key','--key',actor_key(a),'--chain',manifest['chain_id'],'--account',a.actor,
            '--sequence',account['sequence'],'--until',state['height']+100,'--type','protocol','--document',file.name).encode()
    result=http(url,'/submit',{'tx':base64.b64encode(raw).decode()})
    outcome=result['result']
    if outcome['check_tx']['code'] or outcome.get('tx_result',{}).get('code',0):raise RuntimeError(outcome)
    receipt=http(url,'/export/'+quote('receipt/'+a.actor,safe='/'))['value']
    if receipt['txid']!=hashlib.sha256(raw).hexdigest():raise RuntimeError('Latest receipt does not match submitted transaction; inspect the committed export')
    return receipt['result']
def approve_apply(a,cid):
    outcome=send(a,'bootstrap.vote',{'case':cid})
    if outcome['approvals']>=outcome['required']:return send(a,'bootstrap.apply',{'case':cid})
    return dict(case=cid,**outcome,next='Other frozen-roster citizens must sign bootstrap.vote, then bootstrap.apply')
def client(a):
    if a.action=='observer-init':return observer_initialize(a)
    if a.action=='status':return http(endpoint(a),'/society')
    if a.action=='key':
        if not a.key:raise ValueError('--key destination required')
        return json.loads(command(BIN/'dagp-key','--generate','--key',a.key))
    if a.action=='join-request':
        if a.out and a.out.resolve()==actor_key(a).resolve():raise ValueError('Join request destination cannot overwrite the signing key')
        manifest=http(endpoint(a),'/society')
        request=json.loads(command(BIN/'dagp-key','--join-request','--key',actor_key(a),'--chain',manifest['chain_id'],'--account',a.actor,'--operator',a.operator,'--family',a.family))
        if a.out:write(a.out,request)
        if a.post:return http(endpoint(a),'/join',request)
        return request
    if a.action=='invite':
        request=load(a.request);cid=send(a,'bootstrap.propose',{'action':'INVITE','payload':{'join':request}})['case']
        return approve_apply(a,cid)
    if a.action=='register':
        request=load(a.request)
        if request['account']!=a.actor:raise ValueError('Request account differs from signing actor')
        key=base64.b64decode(request['key']).hex()
        challenge=send(a,'identity.challenge',{'key':key})
        # Challenge must come from a prior committed consensus second.
        previous=http(endpoint(a),'/society')['consensus_export']['value']['time']
        deadline=time.monotonic()+30
        while http(endpoint(a),'/society')['consensus_export']['value']['time']<=previous:
            if time.monotonic()>deadline:raise RuntimeError('Consensus clock has not advanced; preserve the challenge and retry the registration transaction')
            time.sleep(.5)
        return send(a,'identity.register',{'operator':request['operator'],'family':request['family'],'key':key,'challenge':challenge['challenge']})
    if a.action=='admit':
        seed_state=http(endpoint(a),'/society')['consensus_export']['value']['bootstrap']
        case=next((p['case'] for p in seed_state['pending'] if p['action']=='ADMIT' and p['payload']['target']==a.target),None)
        if case is None:raise ValueError('No pending admission for this target')
        return approve_apply(a,case)
    if a.action in ('vote','apply','consent'):return send(a,'bootstrap.'+a.action,{'case':a.case})
    if a.action=='propose':return send(a,'bootstrap.propose',{'action':a.kind,'payload':load(a.payload)})
    if a.action=='validator-enroll':
        if not a.home or not a.url:raise ValueError('--home of your synced observer and --url of the society are required')
        own=config(a.home);remote=http(a.url,'/society')
        sync=rpc(own['rpc'],'status')['sync_info'];remote_sync=http(a.url,'/health')['node']
        if sync['catching_up'] or int(sync['latest_block_height'])<int(remote_sync['latest_block_height'])-2:raise ValueError('Sync observer before requesting validator power')
        private=load(a.home/'node/config/priv_validator_key.json')['priv_key']['value']
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as file:
            json.dump(private,file);file.flush()
            proof=json.loads(command(BIN/'dagp-key','--key',file.name,'--chain',remote['chain_id'],'--account',a.actor,'--possession'))
        return send(a,'bootstrap.propose',{'action':'VALIDATOR_ADD','payload':dict(target=a.actor,**proof)})
    if a.action=='submit':
        message=load(a.message);return send(a,message['operation'],message['args'])
    raise ValueError('Unknown action')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['init','start','status','key','join-request','invite','register','admit','propose','vote','apply','consent','submit','observer-init','validator-enroll'])
    p.add_argument('--home',type=Path);p.add_argument('--url');p.add_argument('--actor',default='founder');p.add_argument('--key',type=Path)
    p.add_argument('--founder',default='founder');p.add_argument('--operator',default='founder-operator');p.add_argument('--family',default='founder-family')
    p.add_argument('--chain');p.add_argument('--go');p.add_argument('--skip-build',action='store_true')
    p.add_argument('--rpc-port',type=int,default=27657);p.add_argument('--p2p-port',type=int,default=27656);p.add_argument('--gateway-port',type=int,default=8788)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--public-url');p.add_argument('--out',type=Path);p.add_argument('--post',action='store_true')
    p.add_argument('--local-peers',action='store_true',help='Permit shared-IP/private peers for local observer tests')
    p.add_argument('--request',type=Path);p.add_argument('--target');p.add_argument('--case');p.add_argument('--kind');p.add_argument('--payload',type=Path);p.add_argument('--message',type=Path)
    a=p.parse_args()
    if a.action in ('init','start') and not a.home:p.error('--home is required')
    if a.action=='init':initialize(a)
    elif a.action=='start':start(a)
    else:print(json.dumps(client(a),indent=2))
if __name__=='__main__':main()
