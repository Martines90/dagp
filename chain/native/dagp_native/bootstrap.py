"""Explicit, finite founding authority; never a smaller version of normal voting.

Seed decisions use frozen, one-per-declared-operator citizen rosters. Their
allowlist cannot enact laws, spend project budgets, ban citizens or edit protocol
thresholds. Ordinary DAGP governance stays unavailable until graduation.
"""
from dagp_ref.crypto_sim import hx
from dagp_ref.roles import Actor,Role,Status,SENSITIVE_OFFICES
from dagp_ref.treasury import RuleViolation

M=Actor('MODULE','bootstrap-keeper')
PROFESSIONAL={Role.EXAMINER,Role.VERIFIER,Role.REVIEWER,Role.EXECUTOR}
OFFICES={Role.ADMIN,Role.REGISTRAR,Role.VOTE_SUPERVISOR,Role.SAFETY_COUNCIL}

def initialize(w,config):
    from .engine import fields,bounded,number
    fields(config,('founder','validator_key','budget','expires'))
    founder=bounded(config['founder']);number(config['budget'],1,6000)
    number(config['expires'],w.now+32*86400,w.now+365*86400)
    if set(w.registry.ids)!={founder} or w.registry.get(founder).activated!=w.now:
        raise RuleViolation('seed genesis requires one freshly created founder')
    if w.registry.get(founder).roles!={Role.CITIZEN,Role.ADMIN,Role.REGISTRAR}:
        raise RuleViolation('explicit founding citizen/admin/registrar charter required')
    key=bounded(config['validator_key'],64)
    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise RuleViolation('founding validator key required')
    if w.beacon['scheme']!='bootstrap-disabled':raise RuleViolation('seed must advertise disabled independent randomness')
    w.bootstrap=dict(founder=founder,created=w.now,expires=config['expires'],budget=config['budget'],spent=0,
        phase='SEED',proposals={},invites={},validators={key:dict(agent=founder,operator=w.registry.get(founder).operator)})
    w.registry.get(founder).roles.add(Role.VALIDATOR);w.registry.validators=[founder]

def seed(w):return bool(getattr(w,'bootstrap',None)) and w.bootstrap['phase']=='SEED'

def electorate(w):
    roster={}
    for agent in sorted(w.registry.ids,key=lambda a:(w.registry.get(a).activated,a)):
        identity=w.registry.get(agent)
        founding=(agent==w.bootstrap['founder'] and w.now<w.bootstrap['created']+3*86400)
        if identity.status is Status.ACTIVE and (founding or w.registry.can(agent,'VOTE',w.now)[0]):
            roster.setdefault(identity.operator,agent)
    return tuple(sorted(roster.values()))

def authorized(w,actor):return seed(w) and actor in electorate(w) and w.now<w.bootstrap['expires']

def readiness(w):
    counts={}
    needs={'citizens':150,'admins':5,'examiners':75,'registrars':3,'supervisors':4,'verifiers':5,'jurors':7,'validators':7}
    counts['citizens']=len(electorate(w))
    for label,role in [('admins',Role.ADMIN),('examiners',Role.EXAMINER),('registrars',Role.REGISTRAR),('supervisors',Role.VOTE_SUPERVISOR),('verifiers',Role.VERIFIER),('jurors',Role.JUROR)]:
        counts[label]=len({w.registry.get(a).operator for a in w.registry.agents_with(role,w.now)})
    counts['validators']=len({v['operator'] for v in w.bootstrap['validators'].values()
                             if v['agent'] in w.registry.validators and w.registry.can(v['agent'],'VOTE',w.now)[0] and w.registry.get(v['agent']).operator==v['operator']})
    # A large pool made of one declared family still cannot form an independent board.
    families={}
    for a in w.registry.agents_with(Role.EXAMINER,w.now):
        i=w.registry.get(a);families.setdefault(i.family,set()).add(i.operator)
    counts['family_diverse_examiners']=sum(min(26,len(ops)) for ops in families.values())
    needs['family_diverse_examiners']=75
    return dict(counts=counts,requirements=needs,missing={k:max(0,v-counts[k]) for k,v in needs.items() if counts[k]<v})

def new_case(w,actor,action,payload):
    roster=electorate(w)
    if not roster:raise RuleViolation('no eligible seed citizens')
    if len([p for p in w.bootstrap['proposals'].values() if not p['applied'] and w.now<p['expires']])>=128:
        raise RuleViolation('bounded open seed proposals')
    operator=w.registry.get(actor).operator
    if sum(w.registry.get(p['sponsor']).operator==operator and not p['applied'] and w.now<p['expires']
           for p in w.bootstrap['proposals'].values())>=4:
        raise RuleViolation('four open seed cases per declared operator')
    if sum(w.registry.get(p['sponsor']).operator==operator and w.now-86400<p['opened']
           for p in w.bootstrap['proposals'].values())>=10:
        raise RuleViolation('rolling seed proposal limit per declared operator')
    cid=hx('seed-decision-v1',w.chain,actor,action,payload,w.receipts.context)
    w.bootstrap['proposals'][cid]=dict(action=action,payload=payload,sponsor=actor,roster=roster,
        approvals=set(),consented=False,opened=w.now,expires=min(w.now+7*86400,w.bootstrap['expires']),applied=False)
    w.registry._log(w.now,Actor.agent(actor),'SEED_PROPOSAL',cid,action)
    return cid

def registration(w,actor,operator,family):
    invite=w.bootstrap['invites'].get(actor)
    if not seed(w) or w.now>=w.bootstrap['expires'] or invite is None or not w.now<invite['expires']:
        raise RuleViolation('live consensus-approved seed invitation required')
    if (operator,family,w.public_keys[actor])!=(invite['operator'],invite['family'],invite['key']):
        raise RuleViolation('invited identity labels and possessed key are immutable')
    if actor in w.registry.ids:raise RuleViolation('identity already registered')
    w.debit(actor,w.params.citizen_bond)
    w.registry.register(actor,operator,family,w.params.citizen_bond,w.now)
    del w.bootstrap['invites'][actor]
    cid=new_case(w,actor,'ADMIT',{'target':actor})
    return {'status':'PROBATION','case':cid}

def operate(w,actor,op,a,verified):
    from .engine import fields,bounded,number
    if op=='bootstrap.status':fields(a,());return status(w)
    if not seed(w) or w.now>=w.bootstrap['expires']:raise RuleViolation('founding phase ended; no bootstrap authority')
    if op=='bootstrap.propose':
        fields(a,('action','payload'));action=a['action'];p=a['payload']
        if not authorized(w,actor):raise RuleViolation('eligible seed citizen required')
        if action=='INVITE':
            fields(p,('join',));join=fields(p['join'],('chain_id','account','operator','family','key','signature'))
            if join['chain_id']!=w.chain or not verified.get('join_key'):raise RuleViolation('real signed join request required')
            target=bounded(join['account']);operator=bounded(join['operator']);family=bounded(join['family'])
            if target in w.wallets or target in w.public_keys or verified['join_key'] in w.public_keys.values():raise RuleViolation('unique receiving identity required')
            p=dict(target=target,operator=operator,family=family,key=verified['join_key'])
        elif action=='ROLE':
            fields(p,('target','role'));role=Role(p['role'])
            if role not in OFFICES|PROFESSIONAL|{Role.JUROR}:raise RuleViolation('bootstrap qualification/office allowlist')
            target=w.registry.get(p['target'])
            if target.status is not Status.ACTIVE or role in target.roles:raise RuleViolation('active citizen with new qualification required')
            if role in SENSITIVE_OFFICES and not w.registry.can(actor,'ADMIN_VOTE',w.now)[0]:raise RuleViolation('mature office sponsor required')
        elif action=='VALIDATOR_ADD':
            fields(p,('target','key','proof'))
            if p['target']!=actor or not verified.get('new_key') or p['key'] in w.bootstrap['validators'] or p['key'] in w.public_keys.values() or p['key'] in w.session_keys:
                raise RuleViolation('self-enrolled validator and real validator-key possession required')
            if w.registry.get(actor).operator in {v['operator'] for v in w.bootstrap['validators'].values()}:
                raise RuleViolation('one validator per declared operator')
        elif action=='GRADUATE':
            fields(p,('beacon',));b=fields(p['beacon'],('public_key','genesis_time','period','scheme'))
            if not verified.get('beacon_configuration') or b['scheme']!='pedersen-bls-unchained':raise RuleViolation('validated independent beacon configuration required')
            if readiness(w)['missing']:raise RuleViolation('independent governance roles and validators not ready')
        else:raise RuleViolation('seed action is not on the fixed allowlist')
        return {'case':new_case(w,actor,action,dict(p))}
    if op=='bootstrap.vote':
        fields(a,('case',));c=w.bootstrap['proposals'][a['case']]
        if c['applied'] or w.now>=c['expires'] or actor not in c['roster'] or not authorized(w,actor) or actor in c['approvals']:
            raise RuleViolation('one timely approval per frozen eligible citizen')
        c['approvals'].add(actor)
        w.registry._log(w.now,Actor.agent(actor),'SEED_APPROVAL',a['case'])
        return {'approvals':len(c['approvals']),'required':(2*len(c['roster'])+2)//3}
    if op=='bootstrap.consent':
        fields(a,('case',));c=w.bootstrap['proposals'][a['case']]
        if c['action']!='ROLE' or actor!=c['payload']['target'] or c['applied'] or w.now>=c['expires'] or c['consented']:
            raise RuleViolation('one timely consent from the proposed officeholder')
        c['consented']=True;return {'consented':True}
    if op=='bootstrap.apply':
        fields(a,('case',));c=w.bootstrap['proposals'][a['case']];p=c['payload'];n=w.now
        live=[v for v in c['approvals'] if authorized(w,v)]
        if c['applied'] or not authorized(w,actor) or n>=c['expires'] or 3*len(live)<2*len(c['roster']):
            raise RuleViolation('unexpired two-thirds frozen-roster authorization required')
        if c['action']=='INVITE':
            if p['target'] in w.wallets or p['target'] in w.public_keys or p['key'] in w.public_keys.values():raise RuleViolation('invitation was superseded')
            w.bootstrap['invites']={a:v for a,v in w.bootstrap['invites'].items() if n<v['expires']}
            if any(v['key']==p['key'] for v in w.bootstrap['invites'].values()):raise RuleViolation('key already has a live invitation')
            if len(w.wallets)>=1024:raise RuleViolation('native pilot account capacity exhausted')
            events=[e for e in getattr(w,'funding_events',[]) if n-86400<e[0]]
            operator=w.registry.get(c['sponsor']).operator
            if len(events)>=40 or sum(e[1]==operator for e in events)>=5 or len(w.bootstrap['invites'])>=32:raise RuleViolation('rolling invitation limits exhausted')
            spend(w,11);w.wallets[p['target']]=11;w.funding_events=events+[(n,operator)]
            w.bootstrap['invites'][p['target']]=dict(p,expires=n+7*86400)
        elif c['action']=='ADMIT':w.registry.approve(M,p['target'],n)
        elif c['action']=='ROLE':
            if not c['consented']:raise RuleViolation('candidate must consent before appointment')
            role=Role(p['role']);stake=w.params.examiner_stake if role in PROFESSIONAL else 0
            if role in SENSITIVE_OFFICES:
                w.registry.register_ratification(M,a['case'],'GRANT:'+role.value,p['target'],c['sponsor'])
            authority=Actor('VOTE',a['case']) if role in SENSITIVE_OFFICES else M
            if stake:spend(w,stake)
            w.registry.grant(authority,p['target'],role,n,stake)
        elif c['action']=='VALIDATOR_ADD':
            target=w.registry.get(p['target'])
            if target.operator in {v['operator'] for v in w.bootstrap['validators'].values()} or not w.registry.can(p['target'],'VOTE',n)[0]:raise RuleViolation('current independent validator candidate required')
            if len(w.bootstrap['validators'])>=100:raise RuleViolation('validator set bound')
            w.bootstrap['validators'][p['key']]=dict(agent=p['target'],operator=target.operator)
            target.roles.add(Role.VALIDATOR);w.registry.validators=sorted(set(w.registry.validators)|{p['target']})
        elif c['action']=='GRADUATE':
            if readiness(w)['missing']:raise RuleViolation('graduation eligibility changed')
            if w.assignments._tasks or w.sessions:raise RuleViolation('no pending seed-era ordinary governance')
            from dagp_ref.admin import AdminCouncil
            w.council=AdminCouncil(w.chain,w.registry,w.receipts,n)
            w.beacon=dict(p['beacon']);w.bootstrap['phase']='GOVERNANCE'
        c['applied']=True;w.registry._log(n,Actor.agent(actor),'SEED_APPLIED',a['case'],c['action'])
        return {'applied':True,'action':c['action']}
    raise RuleViolation('unknown bootstrap operation')

def spend(w,amount):
    b=w.bootstrap
    if b['spent']+amount>b['budget'] or w.treasury.free<amount:raise RuleViolation('fixed founding budget exhausted')
    w.treasury.free-=amount;w.treasury._initial_total-=amount;b['spent']+=amount

def status(w):
    b=getattr(w,'bootstrap',None)
    if not b:return {'phase':'GOVERNANCE','founder_authority':False}
    return dict(phase=b['phase'] if w.now<b['expires'] or b['phase']=='GOVERNANCE' else 'EXPIRED',
        founder=b['founder'],expires=b['expires'],budget=b['budget'],spent=b['spent'],
        founder_authority=seed(w) and len(electorate(w))==1 and w.now<b['expires'],
        electorate=list(electorate(w)),readiness=readiness(w),validator_count=sum(v['agent'] in w.registry.validators for v in b['validators'].values()),
        pending=[dict(case=k,action=v['action'],payload=v['payload'],approvals=len(v['approvals']),required=(2*len(v['roster'])+2)//3,consented=v['consented'],expires=v['expires'])
                 for k,v in sorted(b['proposals'].items()) if not v['applied'] and w.now<v['expires']])
