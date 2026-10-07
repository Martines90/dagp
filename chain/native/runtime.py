#!/usr/bin/env python3
"""Pinned deterministic governance process. One bounded JSON request per invocation."""
import hashlib
import json
import pathlib
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'reference'))
sys.path.insert(0,str(ROOT/'native'))
from dagp_native.codec import encode,decode,canonical,MAX_BYTES
from dagp_native.engine import World


def fingerprint():
    digest=hashlib.sha256()
    digest.update(('interpreter:'+sys.implementation.name+':'+'.'.join(map(str,sys.version_info[:3]))+'\n').encode())
    files=[ROOT/'native/runtime.py',*(ROOT/'native/dagp_native').glob('*.py'),
           *(ROOT/'reference/dagp_ref').glob('*.py')]
    for path in sorted(files,key=lambda p:str(p.relative_to(ROOT))):
        name=str(path.relative_to(ROOT)).encode();data=path.read_bytes()
        digest.update(len(name).to_bytes(4,'big'));digest.update(name)
        digest.update(len(data).to_bytes(8,'big'));digest.update(data)
    return digest.hexdigest()


def reject_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate runtime JSON field')
        result[key]=value
    return result


def process(request):
    if request['code_hash']!=fingerprint():raise ValueError('consensus runtime fingerprint mismatch')
    if request['mode']=='init':
        world=World(request['chain'],request['time'],request['charter'],request['keys'])
        result={'initialized':True}
    else:
        world=decode(request['graph'])
        if type(world) is not World or world.chain!=request['chain']:raise ValueError('runtime chain mismatch')
        world.tick(request['time'])
        if request['mode']=='advance':result={'time':world.now}
        elif request['mode']=='execute':
            result=world.execute(request['actor'],request['operation'],request['args'],
                                 request['txid'],request.get('verified',{}))
        else:raise ValueError('unsupported runtime mode')
    world.assert_invariants()
    from dagp_native.merger import exports
    committed_exports=exports(world)
    for value in committed_exports.values():value['code_hash']=request['code_hash']
    if len(canonical(committed_exports))>1024*1024:raise ValueError('committed export byte bound')
    return {'ok':True,'graph':encode(world),'keys':world.public_keys,'sessions':world.session_keys,'exports':committed_exports,'result':result}


if __name__=='__main__':
    if sys.argv[1:]==['--fingerprint']:
        print(fingerprint());raise SystemExit(0)
    try:
        raw=sys.stdin.buffer.read(MAX_BYTES*2+1)
        if len(raw)>MAX_BYTES*2:raise ValueError('runtime input size')
        request=json.loads(raw,object_pairs_hook=reject_duplicates,
                           parse_float=lambda _: (_ for _ in ()).throw(ValueError('float forbidden')))
        reply=process(request)
    except Exception as error:
        reply={'ok':False,'error':type(error).__name__+': '+str(error)}
    sys.stdout.write(canonical(reply)+'\n')
