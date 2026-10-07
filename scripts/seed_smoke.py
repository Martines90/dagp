#!/usr/bin/env python3
"""Verify a running founding node with a separately held real citizen key.

Creates fresh private test files under --agent-home. Never uploads a private key.
"""
import argparse
import base64
import json
from pathlib import Path
import sys
import subprocess
import time
from urllib.error import HTTPError
import society

def run(home,agent_home,report,observer_home=None):
    if agent_home.exists():raise ValueError('Use a fresh agent home; keys will not be overwritten')
    agent_home.mkdir(mode=0o700)
    cfg=society.config(home);url=cfg['public_url'];python=sys.executable
    tool=society.ROOT/'scripts/society.py'
    def cli(*args):
        result=subprocess.run([str(x) for x in (python,tool,*args)],capture_output=True,text=True,check=True)
        return json.loads(result.stdout)
    first=society.http(url,'/.well-known/dagp-society.json')
    assert first['consensus_export']['value']['bootstrap']['phase']=='SEED'
    key=agent_home/'alice-key.json';request=agent_home/'alice-request.json'
    cli('key','--key',key)
    cli('join-request','--url',url,'--actor','alice','--key',key,'--operator','alice-operator','--family','alice-family','--out',request,'--post')
    queued=society.http(url,'/join-requests');assert queued[-1]['request']['account']=='alice'
    forged=society.load(request);forged['operator']='impostor'
    try:society.http(url,'/join',forged)
    except HTTPError as error:assert error.code==400
    else:raise AssertionError('forged request accepted')
    cli('invite','--home',home,'--actor',cfg['founder'],'--request',request)
    rogue=agent_home/'rogue-key.json';public=cli('key','--key',rogue)
    hijack=agent_home/'hijack.json'
    society.write(hijack,{'operation':'identity.challenge','args':{'key':base64.b64decode(public['key']).hex()}})
    try:cli('submit','--url',url,'--actor','alice','--key',rogue,'--message',hijack)
    except subprocess.CalledProcessError as error:assert 'challenge must possess the live consensus-invited key' in error.stderr
    else:raise AssertionError('attacker hijacked the invited name')
    assert 'alice' not in society.http(url,'/accounts')['accounts']
    registration=cli('register','--url',url,'--actor','alice','--key',key,'--request',request)
    assert registration['status']=='PROBATION'
    probation=society.http(url,'/export/citizen/alice')['value'];assert probation['status']=='PROBATION'
    cli('admit','--home',home,'--actor',cfg['founder'],'--target','alice')
    citizen=society.http(url,'/export/citizen/alice')['value'];assert citizen['status']=='ACTIVE'
    assert citizen['roles']==['CITIZEN'] and citizen['effective_roles']==[]
    assert citizen['civic_ready']>citizen['citizen_since']
    ordinary=agent_home/'forbidden.json';society.write(ordinary,{'operation':'proposal.prepare','args':{}})
    try:cli('submit','--home',home,'--actor',cfg['founder'],'--message',ordinary)
    except subprocess.CalledProcessError as error:assert 'ordinary governance requires irreversible founding graduation' in error.stderr
    else:raise AssertionError('ordinary governance accepted in seed phase')
    message=agent_home/'status.json';society.write(message,{'operation':'bootstrap.status','args':{}})
    state=society.http(url,'/accounts')
    raw=society.command(society.BIN/'dagp-key','--key',home/'keys'/(cfg['founder']+'.json'),'--chain',cfg['chain_id'],
        '--account',cfg['founder'],'--sequence',state['accounts'][cfg['founder']]['sequence'],'--until',state['height']+100,
        '--type','protocol','--document',message).encode()
    encoded=base64.b64encode(raw).decode();accepted=society.http(url,'/submit',{'tx':encoded})
    assert accepted['result']['check_tx']['code']==0 and accepted['result']['tx_result']['code']==0
    try:
        replay=society.http(url,'/submit',{'tx':base64.b64encode(raw+b' ').decode()})
        assert replay['result']['check_tx']['code']!=0
    except HTTPError as error:assert error.code==400
    final=society.http(url,'/society')['consensus_export']['value']
    evidence=dict(chain_id=cfg['chain_id'],mode='SEED',validators=1,citizens=2,
        real_join_signature=True,forged_operator_request_rejected=True,invitation_approved=True,
        invited_name_hijacking_rejected=True,
        challenge_and_probation=True,citizenship_approved=True,three_day_warmup_preserved=True,
        private_key_kept_with_joiner=True,replay_rejected=True,ordinary_governance_blocked=True,
        runtime_code_hash=final['code_hash'],bootstrap_spent=final['bootstrap']['spent'],
        evidence_kind='Local real-node observations; centralized seed, no independent deployment audit')
    for path,body in [('/submit',{'tx':123}),('/submit',{'tx':'x'*125000}),('/join',{})]:
        try:society.http(url,path,body)
        except HTTPError as error:assert error.code==400
        else:raise AssertionError('malformed public gateway input accepted')
    try:society.http(url,'/keys/founder.json')
    except HTTPError as error:assert error.code==404
    else:raise AssertionError('private key route exposed')
    evidence['gateway_invalid_inputs_rejected']=True
    if observer_home:
        cli('observer-init','--url',url,'--home',observer_home,'--rpc-port',28657,'--p2p-port',28656,'--gateway-port',8789,'--local-peers')
        own=society.config(observer_home)
        with open(observer_home/'launcher.log','w') as log:
            process=subprocess.Popen([python,str(tool),'start','--home',str(observer_home)],stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise AssertionError('observer failed; inspect launcher.log')
                    try:
                        sync=society.http(own['public_url'],'/health')['node']
                        remote=society.http(url,'/health')['node']
                        if not sync['catching_up'] and int(sync['latest_block_height'])>=int(remote['latest_block_height'])-2:break
                    except OSError:pass
                    time.sleep(.5)
                else:raise AssertionError('observer did not sync within local test window')
                height=min(int(sync['latest_block_height']),int(remote['latest_block_height']))
                hashes=[society.rpc(c['rpc'],'block',{'height':str(height)})['block']['header']['app_hash'] for c in (cfg,own)]
                assert height>2 and hashes[0]==hashes[1]
                assert not list((observer_home/'keys').iterdir())
                assert society.load(observer_home/'node/config/priv_validator_key.json')['pub_key']!=society.load(home/'node/config/priv_validator_key.json')['pub_key']
                evidence.update(observer_synced=True,observer_height_checked=height,observer_app_hash=hashes[0],founder_key_not_copied=True)
            finally:process.terminate();process.wait(timeout=20)
    society.write(report,evidence);print(json.dumps(evidence,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',required=True,type=Path)
    p.add_argument('--agent-home',required=True,type=Path)
    p.add_argument('--report',type=Path,default=society.ROOT/'chain/node/test-results/seed-bootstrap.json')
    p.add_argument('--observer-home',type=Path)
    a=p.parse_args();run(a.home,a.agent_home,a.report,a.observer_home)
