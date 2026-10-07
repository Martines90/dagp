"""Verify exported artifact hashes and replay simulation policies from recorded seeds."""
import argparse
import hashlib
import json
from pathlib import Path
from community import Community

def verify(directory, replay=False):
    raw=(directory/'report.json').read_bytes();report=json.loads(raw)
    manifest=json.loads((directory/'manifest.json').read_bytes())
    if replay and report.get('format') != 'dagp-community-simulation-v9':
        raise ValueError('Historical rules changed: v1 requires commit 6a87852; v2 requires f6bebf5. v3 requires 7140ed9; v4 requires 56ce3b9. v5 requires a38aea0. v6 requires adf6e63. v7 requires e035533. v8 requires 9d34c2c. Generate a fresh v9 scenario for current rules')
    if hashlib.sha256(raw).hexdigest()!=manifest['report_sha256']:raise ValueError('report hash mismatch')
    if len(manifest['runs'])!=len(report['runs']):raise ValueError('manifest run count mismatch')
    if 'insider_abuse_sha256' in manifest:
        raw_insider=(directory/'insider-abuse.json').read_bytes()
        if hashlib.sha256(raw_insider).hexdigest()!=manifest['insider_abuse_sha256']:
            raise ValueError('insider scenario hash mismatch')
        if replay:
            from insider_abuse import run as run_insider
            if json.loads(raw_insider)!=run_insider():
                raise ValueError('insider scenario replay mismatch')
    count=0
    for run,entry in zip(report['runs'],manifest['runs']):
        if (run['seed'],run['mode'])!=(entry['seed'],entry['mode']):raise ValueError('manifest run mismatch')
        raw_events=(directory/f"events-{run['seed']}-{run['mode']}.jsonl").read_bytes()
        digest=hashlib.sha256(raw_events).hexdigest()
        if digest!=run['events_sha256'] or digest!=entry['events_sha256']:raise ValueError('event file hash mismatch')
        prev='0'*64;last=None
        for index,line in enumerate(raw_events.splitlines()):
            event=json.loads(line);last=event['hash'];body={k:v for k,v in event.items() if k!='hash'}
            if event['index']!=index or event['prev']!=prev:raise ValueError('event link mismatch')
            expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if expected!=last:raise ValueError('event hash mismatch')
            prev=last;count+=1
        if last!=run['event_head'] or len(raw_events.splitlines())!=run['event_count']:raise ValueError('event head/count mismatch')
        if last!=entry['event_head']:raise ValueError('manifest event head mismatch')
        tr=run['treasury'];total=tr['free']+sum(tr['reserved'].values())+sum(tr['escrow'].values())+sum(tr['released'].values())
        if total!=100000 or total!=tr['conserved_total'] or tr['reserved']:raise ValueError('treasury invariant failed')
        if replay:
            reconstructed,stream=Community(run['population']-100,seed=run['seed'],mode=run['mode']).run()
            if json.loads(json.dumps(reconstructed))!=run or stream!=raw_events:raise ValueError('deterministic replay mismatch')
    receipt_path=directory/'anchor-receipt.json'
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_bytes())
        digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        if digest!=receipt['document_sha256']:raise ValueError('anchor document hash mismatch')
        if len(receipt['validator_app_hashes'])!=7 or len(set(receipt['validator_app_hashes']))!=1:raise ValueError('validator hashes disagree')
        if len(set(receipt['validator_block_ids']))!=1:raise ValueError('validator block IDs disagree')
        if receipt['replicated_document_reads']!=7:raise ValueError('replication mismatch')
    return count

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--replay',action='store_true');args=parser.parse_args()
    print(f'PASS: {verify(args.directory,args.replay)} hash-chained events verified'+(' and all runs replayed' if args.replay else ''))
