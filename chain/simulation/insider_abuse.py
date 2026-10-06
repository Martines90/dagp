#!/usr/bin/env python3
"""Deterministic coordinated-insider attack and containment story, no external services."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reference'))
from dagp_ref.admin import AdminCouncil
from dagp_ref.crypto_sim import SimKeyring
from dagp_ref.params import Params
from dagp_ref.roles import Actor,Role,RoleRegistry,Status
from dagp_ref.treasury import RuleViolation

MODULE=Actor('MODULE','insider-scenario')
def run():
    reg=RoleRegistry(Params(min_citizen_age=1));keys=SimKeyring();checks=[]
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    for n in range(1000):
        a=f'admin-{n}' if n<50 else f'citizen-{n}'
        reg.register(a,'operator-'+a,'family',10,0);reg.approve(MODULE,a,0)
        if n<50:
            keys.register(a)
            for role in (Role.ADMIN,Role.REGISTRAR,Role.SAFETY_COUNCIL):
                ref=f'grant:{a}:{role.value}'
                reg.register_ratification(MODULE,ref,f'GRANT:{role.value}',a)
                reg.grant(Actor('VOTE',ref),a,role,1)
    council=AdminCouncil('insider-scenario-chain',reg,keys)
    def case(member,target,height):
        evidence='e'*64
        return council.open(member,target,evidence,height,keys.sign(member,council.open_message(member,target,evidence,height)))
    def approve(member,c,height):
        return council.approve(member,c,height,keys.sign(member,council.approval_message(c)))
    hostile_case=case('admin-0','admin-40',100)
    for n in range(10):check(f'minority approval {n} cannot contain honest admin',not approve(f'admin-{n}',hostile_case,100))
    successes=denials=0
    for n in range(50):
        try:reg.suspend(Actor.agent(f'admin-{n//5}'),f'citizen-{50+n}',100,110,'COORDINATED_ABUSE');successes+=1
        except RuleViolation:denials+=1
    check('ten attackers restricted to twenty temporary sanctions',successes==20 and denials==30)
    check('registrar freezes cannot censor citizen votes',all(reg.can(f'citizen-{50+n}','VOTE',100)[0] for n in range(50)))
    check('honest administrator retains powers',reg.can('admin-40','REGISTRAR_ACT',100)[0])
    reg.tick(110)
    check('temporary victims automatically recover',all(reg.get(f'citizen-{50+n}').status is Status.ACTIVE for n in range(50)))
    for n in range(10):
        target=f'admin-{n}';c=case('admin-49',target,111)
        for supporter in range(10,35):approve(f'admin-{supporter}',c,111)
        check(f'hostile administrator {n} contained',not reg.can(target,'REGISTRAR_ACT',111)[0])
        check(f'hostile administrator {n} retains citizenship and appeal standing',reg.can(target,'VOTE',111)[0] and reg.can(target,'FILE_CASE',111)[0])
        issuer=f'admin-{35+n}';ref=f'court-dismiss:{target}'
        reg.register_ruling(MODULE,ref,'ADMIN_DISMISS',target,issuer)
        reg.dismiss_admin(Actor('COURT',ref),target,112)
        check(f'hostile administrator {n} dismissed after review',Role.ADMIN not in reg.get(target).roles)
    check('all ten lose authority beyond hold expiry',all(not reg.can(f'admin-{n}','REGISTRAR_ACT',500)[0] for n in range(10)))
    check('all fifty original citizens recover without permanent citizen bans',all(reg.get(f'citizen-{50+n}').status is Status.ACTIVE for n in range(50)))
    check('audit trail verifies',reg.verify_audit())
    return dict(format='dagp-insider-abuse-v1',citizens=1000,administrators=50,hostile_administrators=10,
                attempted_freezes=50,accepted_freezes=successes,refused_freezes=denials,
                peer_containment_threshold=council.threshold,contained_and_court_dismissed=10,
                permanent_citizenship_bans=0,checks=len(checks),passed_checks=checks,
                rule_hash=reg.p.snapshot_hash(),audit_head=reg.audit[-1]['hash'],
                limits='reference model, simulated signatures and trusted court evidence; not native G0 enforcement')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"PASS: {report['checks']} checks; {report['accepted_freezes']}/50 attacks accepted; ten officials contained and independently dismissed")
