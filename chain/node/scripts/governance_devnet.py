#!/usr/bin/env python3
"""Run authenticated G2 party/pre-election actions on seven fresh local validators.

The generator beacon key is a public test fixture, not a production randomness
service. Long governance phases are covered by consensus-time unit stories.
"""
import argparse
import base64
import datetime
import json
import pathlib
import signal
import subprocess
import sys
import time
import devnet as net

RUNTIME=net.ROOT.parent/'native/runtime.py'
BEACON_KEY='97f1d3a73197d7942695638c4fa9ac0fc3688c4f9774b905a14e3a3f171bac586c55e83ff97a1aeffb3af00adb22c6bb'

def query(index=0,path='/state'):
    result=net.rpc(index,'abci_query',{'path':path})['response']
    if result.get('code',0):raise RuntimeError(result)
    return json.loads(base64.b64decode(result['value']))

def initialize(home):
    net.HOME=home;net.initialize()
    genesis=json.loads((home/'node0/config/genesis.json').read_text())
    now=int(datetime.datetime.fromisoformat(genesis['genesis_time'].replace('Z','+00:00')).timestamp())
    accounts={};identities={}
    for index in range(100):
        actor=f'agent{index:03d}'
        accounts[actor]=json.loads(net.command(net.BIN/'dagp-key','--generate','--key',home/f'{actor}.json'))
        identities[actor]=dict(operator=f'op{index}',family=f'family{index%5}',citizen_since=now-40*86400,
            roles=['CITIZEN','EXAMINER','REGISTRAR','VERIFIER','JUROR','VOTE_SUPERVISOR']+(['ADMIN'] if index<50 else []))
    beacon=dict(public_key=BEACON_KEY,genesis_time=now,period=1,scheme='pedersen-bls-unchained')
    charter=dict(identities=identities,common_budget=100000,balances={a:200 for a in accounts},beacon=beacon,root='root',constraints=[])
    fingerprint=net.command(sys.executable,'-I','-B',RUNTIME,'--fingerprint')
    genesis['chain_id']='dagp-local-g2-governance'
    genesis['app_state']=dict(chain_id=genesis['chain_id'],height=0,accounts=accounts,documents={},
        runtime=dict(version=2,code_hash=fingerprint,time=now,beacon=beacon,charter=charter))
    for index in range(7):(home/f'node{index}/config/genesis.json').write_text(json.dumps(genesis,indent=2))

def run(home,report):
    net.HOME=home;processes=[];logs=[];last_height=0
    try:
        for index in range(7):
            log=open(home/f'app{index}.log','a');logs.append(log)
            processes.append(subprocess.Popen([str(net.BIN/'dagpd'),'--state',str(home/f'node{index}/data/application.json'),
                '--listen',f'tcp://127.0.0.1:{26658+index*10}','--python',sys.executable,'--governance-runtime',str(RUNTIME)],stdout=log,stderr=log))
        time.sleep(1)
        for index in range(7):
            log=open(home/f'node{index}.log','a');logs.append(log)
            processes.append(subprocess.Popen([str(net.BIN/'cometbft'),'start','--home',str(home/f'node{index}')],stdout=log,stderr=log))
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                if all(int(net.rpc(i,'status')['sync_info']['latest_block_height'])>=2 for i in range(7)):break
            except (OSError,RuntimeError):pass
            time.sleep(1)
        else:raise RuntimeError('G2 consensus did not start; inspect fresh network logs')
        def send(actor,operation,args,accepted=True):
            nonlocal last_height
            state=query();path=home/'message.json';path.write_text(json.dumps(dict(operation=operation,args=args)))
            raw=net.command(net.BIN/'dagp-key','--key',home/f'{actor}.json','--chain',state['chain_id'],'--account',actor,
                '--sequence',state['accounts'][actor]['sequence'],'--until',int(net.rpc(0,'status')['sync_info']['latest_block_height'])+100,
                '--type','protocol','--document',path)
            result=net.rpc(0,'broadcast_tx_commit' if accepted else 'broadcast_tx_sync',{'tx':base64.b64encode(raw.encode()).decode()},timeout=30)
            if accepted:
                if result['check_tx']['code'] or result['tx_result']['code']:raise RuntimeError(result)
                last_height=int(result['height'])
            elif result['code']==0:raise RuntimeError('unauthorized action admitted')
            return raw
        last_raw=None
        for party,start in [('alpha',0),('beta',10)]:
            members=[f'agent{i:03d}' for i in range(start,start+10)]
            for actor in members:last_raw=send(actor,'party.consent',dict(party=party,members=members,nonce='formation',scope='root'))
        stamp=net.rpc(0,'block')['block']['header']['time']
        now=int(datetime.datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp())
        send('agent000','pre.open',dict(cycle='cycle',close=now+86400,deadline=now+80*86400,scope='root'))
        for i in range(20):last_raw=send(f'agent{i:03d}','pre.vote',dict(cycle='cycle',picks=['alpha','beta']))
        send('agent000','treasury.release_next',dict(project='attacker'),False)
        send('agent000','role.grant',dict(target='agent099',role='ADMIN'),False)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:
                roots=[net.rpc(i,'block',{'height':str(last_height+1)})['block']['header']['app_hash'] for i in range(7)]
                if len(set(roots))==1:break
            except (OSError,RuntimeError):pass
            time.sleep(1)
        else:raise RuntimeError('seven validator roots did not converge')
        replay=net.rpc(1,'broadcast_tx_sync',{'tx':base64.b64encode((last_raw+' ').encode()).decode()})
        if replay['code']==0:raise RuntimeError('replay admitted')
        evidence=dict(protocol='G2',validators=7,citizens=100,admins=50,parties=2,founder_consents=20,pre_election_ballots=20,
            last_transaction_height=last_height,header_height=last_height+1,app_hashes=roots,all_hashes_match=len(set(roots))==1,
            replay_rejected=True,raw_treasury_release_rejected=True,raw_role_grant_rejected=True,
            runtime_code_hash=query(path='/runtime')['code_hash'],evidence_kind='local RPC observations; not an independent deployment audit')
        report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps(evidence,indent=2))
    finally:
        for process in processes:
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in processes:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',required=True,type=pathlib.Path)
    parser.add_argument('--report',type=pathlib.Path,default=net.ROOT/'test-results/g2-governance.json')
    args=parser.parse_args();initialize(args.home.resolve());run(args.home.resolve(),args.report.resolve())
