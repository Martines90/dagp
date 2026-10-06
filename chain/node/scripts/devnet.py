#!/usr/bin/env python3
"""Create and run seven local G0 validators; never overwrites existing keys."""
import argparse, base64, hashlib, json, pathlib, signal, subprocess, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN, HOME = ROOT/'bin', ROOT/'.devnet'
def command(*args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()
def rpc(i, method, params=None):
    data=json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params or {})).encode()
    req=urllib.request.Request(f'http://127.0.0.1:{26657+i*10}', data, {'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=3) as response: result=json.load(response)
    if 'error' in result: raise RuntimeError(result['error'])
    return result['result']
def initialize():
    if HOME.exists(): raise SystemExit('Devnet exists; reuse with start or smoke. Keys will not be overwritten.')
    command(BIN/'cometbft','testnet','--home',ROOT/'.devnet-tool','--v','7','--o',HOME,'--populate-persistent-peers=false')
    account=json.loads(command(BIN/'dagp-key','--generate','--key',HOME/'agent-key.json'))
    nodes=[HOME/f'node{i}' for i in range(7)]
    ids=[command(BIN/'cometbft','show-node-id','--home',n) for n in nodes]
    genesis=json.loads((nodes[0]/'config/genesis.json').read_text())
    genesis['chain_id']='dagp-local-g0'
    genesis['app_state']=dict(chain_id=genesis['chain_id'],height=0,accounts={'agent':account},documents={})
    for i,n in enumerate(nodes):
        (n/'config/genesis.json').write_text(json.dumps(genesis,indent=2))
        path=n/'config/config.toml'; text=path.read_text()
        for port in (26657,26658): text=text.replace(f'tcp://127.0.0.1:{port}',f'tcp://127.0.0.1:{port+i*10}')
        text=text.replace('tcp://0.0.0.0:26656',f'tcp://127.0.0.1:{26656+i*10}')
        peers=','.join(f'{ids[j]}@127.0.0.1:{26656+j*10}' for j in range(7) if j!=i)
        text=text.replace('persistent_peers = ""',f'persistent_peers = "{peers}"')
        text=text.replace('addr_book_strict = true','addr_book_strict = false').replace('allow_duplicate_ip = false','allow_duplicate_ip = true')
        path.write_text(text)
    print('Initialized seven local validators and one document-publishing account.')
def smoke():
    for _ in range(60):
        try:
            if all(int(rpc(i,'status')['sync_info']['latest_block_height'])>=2 for i in range(7)): break
        except (OSError,RuntimeError): pass
        time.sleep(1)
    else: raise RuntimeError('No consensus; inspect .devnet logs')
    state=json.loads(base64.b64decode(rpc(0,'abci_query',{'path':'/state'})['response']['value']))
    seq=state['accounts']['agent']['sequence']; doc=HOME/'smoke.txt';doc.write_text(f'DAGP smoke sequence {seq}')
    height=int(rpc(0,'status')['sync_info']['latest_block_height'])
    tx=command(BIN/'dagp-key','--key',HOME/'agent-key.json','--document',doc,'--sequence',seq,'--until',height+100)
    encoded=base64.b64encode(tx.encode()).decode()
    result=rpc(0,'broadcast_tx_commit',{'tx':encoded})
    assert result['check_tx']['code']==0 and result['tx_result']['code']==0,result
    height=int(result['height'])
    for _ in range(30):
        try:
            roots=[rpc(i,'block',{'height':str(height+1)})['block']['header']['app_hash'] for i in range(7)]
            assert len(set(roots))==1,roots
            break
        except (OSError,RuntimeError): time.sleep(1)
    else: raise RuntimeError('Validators failed to agree')
    # Different wire bytes bypass the mempool byte-hash cache; the account sequence must reject it.
    replay=base64.b64encode((tx+' ').encode()).decode()
    assert rpc(1,'broadcast_tx_sync',{'tx':replay})['code']!=0,'replay accepted'
    cid=hashlib.sha256(doc.read_bytes()).hexdigest()
    for i in range(7):
        r=rpc(i,'abci_query',{'path':'/document','data':cid.encode().hex()})['response']
        assert base64.b64decode(r['value'])==doc.read_bytes()
    print(f'PASS: seven validators agree; document committed at height {height}; replay refused.')
def anchor(document, receipt):
    for _ in range(60):
        try:
            if all(int(rpc(i,'status')['sync_info']['latest_block_height'])>=2 for i in range(7)): break
        except (OSError,RuntimeError): pass
        time.sleep(1)
    else: raise RuntimeError('No consensus; inspect .devnet logs')
    data=document.read_bytes()
    if not 0<len(data)<=65536: raise ValueError('Anchor document must fit within 64 KiB')
    cid=hashlib.sha256(data).hexdigest()
    state=json.loads(base64.b64decode(rpc(0,'abci_query',{'path':'/state'})['response']['value']))
    height=int(rpc(0,'status')['sync_info']['latest_block_height'])
    tx=command(BIN/'dagp-key','--key',HOME/'agent-key.json','--document',document,
        '--sequence',state['accounts']['agent']['sequence'],'--until',height+100)
    result=rpc(0,'broadcast_tx_commit',{'tx':base64.b64encode(tx.encode()).decode()})
    if result['check_tx']['code']!=0 or result['tx_result']['code']!=0: raise RuntimeError(result)
    height=int(result['height'])
    for _ in range(30):
        try:
            blocks=[rpc(i,'block',{'height':str(height+1)}) for i in range(7)]
            roots=[b['block']['header']['app_hash'] for b in blocks]
            if len(set(roots))!=1: raise AssertionError('Validator application hashes disagree')
            break
        except (OSError,RuntimeError): time.sleep(1)
    else: raise RuntimeError('Anchor was not replicated')
    for i in range(7):
        r=rpc(i,'abci_query',{'path':'/document','data':cid.encode().hex()})['response']
        if base64.b64decode(r['value'])!=data: raise AssertionError('Anchor document mismatch')
    evidence=dict(format='dagp-g0-anchor-receipt-v1',chain_id='dagp-local-g0',
        document_sha256=cid,transaction_hash=result['hash'],transaction_height=height,
        app_hash_header_height=height+1,validator_app_hashes=roots,
        validator_block_ids=[b['block_id']['hash'] for b in blocks],
        replicated_document_reads=7,
        governance_execution='off-chain reference; only this manifest is published on G0',
        assurance='Local RPC observations, not an independently verified light-client proof')
    receipt.write_text(json.dumps(evidence,indent=2))
    print(f'PASS: manifest {cid} anchored at height {height}; all seven validators agree; receipt {receipt}')

def faults(processes, logs):
    """Crash-only campaign: 2/7 offline progress, 3/7 halt, restored quorum recovery."""
    smoke()
    def height():
        return int(rpc(0,'status')['sync_info']['latest_block_height'])
    def stop(i):
        p=processes[7+i];p.terminate();p.wait(timeout=15)
    def progress(baseline, timeout=45):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if height()>baseline:return height()
            time.sleep(1)
        raise RuntimeError('Consensus failed to progress with sufficient voting power')
    stop(5);stop(6)
    progress(height())
    print('PASS: consensus progresses with two of seven validators offline',flush=True)
    stop(4)
    # Drain a potentially already committed block before checking loss-of-quorum halt.
    time.sleep(5);baseline=height();time.sleep(8)
    if height()!=baseline:raise RuntimeError('Chain advanced without two-thirds voting power')
    print('PASS: chain halts with three of seven validators offline',flush=True)
    for i in (4,5,6):
        log=open(HOME/f'node{i}.log','a');logs.append(log)
        p=subprocess.Popen([str(BIN/'cometbft'),'start','--home',str(HOME/f'node{i}')],stdout=log,stderr=log)
        processes.append(p)
    progress(baseline,90)
    smoke()
    print('PASS: restored validators resume consensus and agree on committed state',flush=True)

def start(test, document=None, receipt=None, fault_test=False):
    if not HOME.exists(): raise SystemExit('Run init first')
    processes=[]; logs=[]
    def stopped(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stopped)
    try:
        for i in range(7):
            log=open(HOME/f'app{i}.log','a');logs.append(log)
            processes.append(subprocess.Popen([str(BIN/'dagpd'),'--state',str(HOME/f'node{i}/data/application.json'),'--listen',f'tcp://127.0.0.1:{26658+i*10}'],stdout=log,stderr=log))
        time.sleep(1)
        for i in range(7):
            log=open(HOME/f'node{i}.log','a');logs.append(log)
            processes.append(subprocess.Popen([str(BIN/'cometbft'),'start','--home',str(HOME/f'node{i}')],stdout=log,stderr=log))
        if fault_test: faults(processes,logs)
        elif document is not None: anchor(document,receipt)
        elif test: smoke()
        else:
            print('Devnet running; RPC ports 26657, 26667, … 26717. Ctrl-C stops it.',flush=True)
            while True:
                if any(p.poll() is not None for p in processes): raise RuntimeError('Node exited; inspect logs')
                time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        for p in reversed(processes):
            if p.poll() is None: p.terminate()
        for p in processes:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill();p.wait()
        for log in logs: log.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['init','start','smoke','anchor','faults'])
    parser.add_argument('--document',type=pathlib.Path)
    parser.add_argument('--receipt',type=pathlib.Path)
    args=parser.parse_args()
    if args.action=='anchor' and (args.document is None or args.receipt is None): parser.error('anchor requires --document and --receipt')
    if args.action=='init': initialize()
    else: start(args.action=='smoke',args.document if args.action=='anchor' else None,args.receipt,args.action=='faults')
