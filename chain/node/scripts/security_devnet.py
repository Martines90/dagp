#!/usr/bin/env python3
"""Execute native G1 protections on seven isolated validators (stdlib only).

Creates private keys under --home and refuses to overwrite it. Observations are
local RPC evidence, not independently verified light-client proofs.
"""
import argparse
import base64
import datetime
import json
import pathlib
import subprocess
import signal
import time
import devnet as net


def query(path):
    response = net.rpc(0, 'abci_query', {'path': path})['response']
    if response.get('code', 0):
        raise RuntimeError(response)
    return json.loads(base64.b64decode(response['value']))


def initialize(home):
    net.HOME = home
    net.initialize()
    genesis = json.loads((home/'node0/config/genesis.json').read_text())
    stamp = datetime.datetime.fromisoformat(genesis['genesis_time'].replace('Z', '+00:00'))
    now = int(stamp.timestamp())
    identities, accounts = {}, {}
    for j in range(100):
        name = f'agent{j:03d}'
        accounts[name] = json.loads(net.command(net.BIN/'dagp-key', '--generate', '--key', home/f'{name}.json'))
        identities[name] = dict(operator=f'op{j:03d}', citizen_since=now-40*86400)
        if j < 50:
            identities[name]['admin_since'] = now-3*86400
    genesis['chain_id'] = 'dagp-local-g1-security'
    genesis['app_state'] = dict(chain_id=genesis['chain_id'], height=0,
        accounts=accounts, documents={}, governance=dict(version=1, time=now,
        identities=identities, freezes=[], complaints=[], cases={}, rosters={}, rotations={}))
    for j in range(7):
        (home/f'node{j}/config/genesis.json').write_text(json.dumps(genesis, indent=2))


def run(home):
    net.HOME = home
    processes, logs = [], []
    last_height = 0
    try:
        for j in range(7):
            log = open(home/f'app{j}.log', 'a'); logs.append(log)
            processes.append(subprocess.Popen([str(net.BIN/'dagpd'), '--state',
                str(home/f'node{j}/data/application.json'), '--listen',
                f'tcp://127.0.0.1:{26658+j*10}'], stdout=log, stderr=log))
        time.sleep(1)
        for j in range(7):
            log = open(home/f'node{j}.log', 'a'); logs.append(log)
            processes.append(subprocess.Popen([str(net.BIN/'cometbft'), 'start',
                '--home', str(home/f'node{j}')], stdout=log, stderr=log))
        for _ in range(60):
            try:
                if all(int(net.rpc(j, 'status')['sync_info']['latest_block_height']) >= 2 for j in range(7)):
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Consensus did not start; inspect logs')

        def send(actor, kind, body, accepted=True):
            nonlocal last_height
            state = query('/state')
            path = home/'message.json'; path.write_text(json.dumps(body))
            raw = net.command(net.BIN/'dagp-key', '--key', home/f'{actor}.json',
                '--chain', state['chain_id'], '--account', actor,
                '--sequence', state['accounts'][actor]['sequence'], '--until',
                int(net.rpc(0, 'status')['sync_info']['latest_block_height'])+100,
                '--type', kind, '--document', path)
            method = 'broadcast_tx_commit' if accepted else 'broadcast_tx_sync'
            result = net.rpc(0, method, {'tx': base64.b64encode(raw.encode()).decode()})
            if accepted:
                assert result['check_tx']['code'] == 0 and result['tx_result']['code'] == 0, result
                last_height = int(result['height'])
                # A lagging peer may temporarily admit the old sequence to its
                # mempool. Wait for its committed account sequence before asserting
                # admission rejection; proposal execution always rechecks it.
                for _ in range(100):
                    peer = net.rpc(1, 'abci_query', {'path': '/state'})['response']
                    peer_state = json.loads(base64.b64decode(peer['value']))
                    if peer_state['accounts'][actor]['sequence'] > state['accounts'][actor]['sequence']:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError('Peer failed to commit the transaction')
                replay = net.rpc(1, 'broadcast_tx_sync', {'tx': base64.b64encode((raw+' ').encode()).decode()})
                assert replay['code'] != 0, 'replay accepted'
            else:
                assert result['code'] != 0, result
            return raw

        evidence = '0'*63+'1'
        for target in ('agent090', 'agent091'):
            send('agent000', 'freeze_identity', dict(target=target, evidence=evidence))
        send('agent000', 'freeze_identity', dict(target='agent092', evidence=evidence), False)
        send('agent001', 'freeze_identity', dict(target='agent092', evidence=evidence))
        send('agent002', 'freeze_identity', dict(target='agent093', evidence=evidence), False)
        send('agent010', 'open_containment', dict(target='agent000', evidence=evidence))
        cases = query('/governance')['cases']; assert len(cases) == 1
        case = next(iter(cases)); assert len(query('/governance')['rosters'][cases[case]['roster']]) == 50
        for j in range(10):
            send(f'agent{j:03d}', 'open_containment', dict(target=f'agent{30+j:03d}', evidence=evidence))
        assert len(query('/governance')['cases']) == 11, 'minority exhausted complaint capacity'
        for j in range(1, 11):
            send(f'agent{j:03d}', 'approve_containment', dict(case=case))
        assert query('/governance')['identities']['agent000'].get('held_until', 0) == 0
        send('agent001', 'approve_containment', dict(case=case), False)
        for j in range(11, 26):
            send(f'agent{j:03d}', 'approve_containment', dict(case=case))
        g = query('/governance'); assert g['identities']['agent000']['held_until'] > g['time']
        send('agent000', 'open_containment', dict(target='agent030', evidence=evidence), False)
        send('agent030', 'grant_admin', dict(target='agent050'), False)
        for _ in range(30):
            try:
                blocks = [net.rpc(j, 'block', {'height': str(last_height+1)}) for j in range(7)]
                roots = [b['block']['header']['app_hash'] for b in blocks]
                assert len(set(roots)) == 1
                break
            except (OSError, RuntimeError):
                time.sleep(1)
        else:
            raise RuntimeError('Validator state did not converge')
        # Same-height queries compare actual committed governance, not just app hashes.
        for j in range(7):
            snapshot = json.loads((home/f'node{j}/data/application.json').read_text())
            assert snapshot['governance']['cases'][case]['applied']
            assert snapshot['accounts']['agent000']['sequence'] == 3
        report = dict(format='dagp-native-security-devnet-v1', validators=7,
            citizens=100, administrators=50, transaction_height=last_height,
            header_height=last_height+1, app_hashes=roots, case=case,
            quorum_approvals=25, minority_approvals_tested=10,
            minority_complaint_capacity_tested=True,
            freeze_cap=3, replay_rejected=True, native_execution=True,
            assurance='Local RPC and committed snapshot observations; no independent light-client proof')
        (home/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=pathlib.Path, required=True)
    args = parser.parse_args()
    # Fresh genesis is required: never implicitly upgrade the G0 devnet.
    if args.home.exists():
        parser.error('home already exists; choose a new directory')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    initialize(args.home.resolve())
    run(args.home.resolve())
