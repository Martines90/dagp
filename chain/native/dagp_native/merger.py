"""Identity-only bilateral merger covenants backed by verified peer export proofs.

A source citizen exits on the source chain before importing citizenship. No
source funds, offices, party membership or credits cross the proof boundary.
"""
import json
from dagp_ref.crypto_sim import hx,MerkleTree,verify_proof
from dagp_ref.roles import Actor,Role,Status
from dagp_ref.session import snapshot_electorate
from dagp_ref.societies import InstitutionalMandate,digest
from dagp_ref.tally import Kind
from dagp_ref.treasury import RuleViolation


def wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def row_bytes(row):return wire(row).encode()
def name(source,agent):return 'm.'+hx('native-import-identity',source,agent)[:48]

class Covenant:
    def __init__(self,world,manifest):
        self.world=world;self.manifest=manifest;self.payload=hx('native-merger-covenant-v1',wire(manifest))
        self.context=world.tree.context(world.tree.root);self.rules=world.registry.p.snapshot_hash();self.laws=tuple(sorted((key,law[0]) for key,law in world.tree._laws.items() if key[0]==world.tree.root))
        self._mandates={};self.claimed={};self.claim_indices={};self.peer_approved=False;self.daily=[]
        electorate=snapshot_electorate(world.registry,world.now)
        issue='merger:'+manifest['id']+':'+world.chain
        self.mandate=InstitutionalMandate(self,issue,Kind.MERGER,world.registry,electorate,
            self.payload,world.now,30*86400,manifest['expires'],self.payload,())
        # Political representatives are recused from certification, not voters.
        parties=world.parties
        self.mandate.subjects=tuple(sorted(parties._party))
        if not self.mandate.subjects:raise RuleViolation('elected society and political representatives required')
        self._mandates[issue]=self.mandate
    def check_context(self,context):
        if context!=self.payload or self.context!=self.world.tree.context(self.world.tree.root) or self.rules!=self.world.registry.p.snapshot_hash() or self.laws!=tuple(sorted((key,law[0]) for key,law in self.world.tree._laws.items() if key[0]==self.world.tree.root)):raise RuleViolation('merger law or policy context changed')
    def approved(self):
        self.mandate.certificate(self.world.now)
        if self.world.now<self.mandate.session.w.challenge_end+30*86400:raise RuleViolation('merger cooling-off period')
        return True
    def claim_tree(self):
        return MerkleTree([row_bytes((index,self.claim_indices.get(index))) for index in range(self.manifest['size'])])
    def summary(self):
        try:approved=self.approved()
        except RuleViolation:approved=False
        return {'chain':self.world.chain,'payload':self.payload,'manifest':self.manifest,'approved':approved,
                'expires':self.manifest['expires'],'time':self.world.now,'claimed_root':self.claim_tree().root.hex(),'claim_count':len(self.claimed)}


def peer(world,verified,key,chain):
    if verified.get('peer_chain')!=chain or verified.get('peer_key')!=key:
        raise RuleViolation('verified peer export domain required')
    value=json.loads(verified['peer_value'])
    if value.get('chain')!=chain:raise RuleViolation('peer export chain mismatch')
    return value


def operate(w,actor,op,a,verified,fields,number,bounded):
    n=w.now
    w.populations=getattr(w,'populations',{})
    w.mergers=getattr(w,'mergers',{})
    w.exported_identities=getattr(w,'exported_identities',{})
    if op=='merger.snapshot':
        fields(a,('id',));ident=bounded(a['id'])
        if not w.registry.can(actor,'VOTE',n)[0] or ident in w.populations:raise RuleViolation('unique citizen-requested population snapshot')
        ids=[x for x in sorted(w.registry.ids) if w.registry.can(x,'VOTE',n)[0] and w.registry.age(x,n)>=30*86400]
        rows=tuple((x,w.public_keys[x],w.registry.get(x).operator,w.registry.get(x).family,w.registry.get(x).activated) for x in ids)
        tree=MerkleTree([row_bytes(row) for row in rows]);w.populations[ident]=(rows,tree)
        return {'snapshot':ident,'root':tree.root.hex(),'size':len(rows)}
    if op=='merger.propose':
        fields(a,('manifest','peer'))
        m=fields(a['manifest'],('id','source','destination','snapshot','root','size','expires','policy'))
        bounded(m['id']);number(m['size'],1,1024);number(m['expires'],n+70*86400)
        if m['source']==m['destination'] or w.chain not in (m['source'],m['destination']) or m['policy']!='identity-only-citizen-warmup-v1' or m['id'] in w.mergers:raise RuleViolation('unique bilateral identity-only manifest')
        if not w.registry.can(actor,'VOTE',n)[0] or w.monthly.points is None:raise RuleViolation('established elected society required')
        if w.chain==m['source']:
            rows,tree=w.populations[m['snapshot']]
            if tree.root.hex()!=m['root'] or len(rows)!=m['size']:raise RuleViolation('source population snapshot mismatch')
            # Prove a real elected receiving society before asking citizens to unite.
            view=peer(w,verified,'society',m['destination'])
            if not view.get('elected'):raise RuleViolation('receiving society is not established')
        else:
            view=peer(w,verified,'population/'+m['snapshot'],m['source'])
            if view.get('root')!=m['root'] or view.get('size')!=m['size']:raise RuleViolation('verified source population mismatch')
        covenant=Covenant(w,dict(m));w.mergers[m['id']]=covenant
        w.freeze('certification',covenant.mandate.issue,covenant.mandate.subjects)
        return {'payload':covenant.payload,'issue':covenant.mandate.issue}
    if op=='merger.vote_open':
        fields(a,('id','bank','windows'));c=w.mergers[a['id']];m=c.mandate
        w.open_session(m.issue,w.registry,a['bank'],a['windows'],Kind.MERGER,mandate=m)
        return {'opened':True}
    if op=='merger.confirm':
        fields(a,('id','peer'));c=w.mergers[a['id']];c.approved()
        other=c.manifest['destination'] if w.chain==c.manifest['source'] else c.manifest['source']
        view=peer(w,verified,'merger/'+a['id'],other)
        if view.get('payload')!=c.payload or not view.get('approved') or view.get('manifest')!=c.manifest:raise RuleViolation('matching live bilateral approvals required')
        c.peer_approved=True;return {'prepared':True}
    if op=='merger.lock':
        fields(a,('id','destination_key','proof','nonce'))
        c=w.mergers[a['id']];c.approved();m=c.manifest
        if w.chain!=m['source'] or not c.peer_approved or n>=m['expires'] or actor in w.exported_identities:raise RuleViolation('prepared source opt-in required')
        rows,tree=w.populations[m['snapshot']];index=next((i for i,r in enumerate(rows) if r[0]==actor),None)
        if index is None:raise RuleViolation('outside frozen source population')
        row=rows[index];i=w.registry.get(actor)
        if i.status is not Status.ACTIVE or row[1]!=w.public_keys[actor] or row[2:4]!=(i.operator,i.family) or not verified.get('new_key'):raise RuleViolation('current source identity and receiving-key proof required')
        bounded(a['nonce'])
        for scope in w.scoped.values():
            p=scope['parties'];party=p._party.pop(actor,None)
            if party is not None:p._members[party].discard(actor)
        refund=w.registry.exit(actor,n);w.wallets[actor]=w.wallets.get(actor,0)+refund
        record={'chain':w.chain,'source':actor,'payload':c.payload,'destination':m['destination'],'destination_key':a['destination_key'],
                'row':list(row),'index':index,'proof':[[h.hex(),right] for h,right in tree.proof(index)],'expires':m['expires'],'nonce':a['nonce']}
        w.exported_identities[actor]=record
        return {'export':'identity/'+actor,'bond_refunded':refund}
    if op=='merger.claim':
        fields(a,('id','source','key','peer'));c=w.mergers[a['id']];c.approved();m=c.manifest
        if w.chain!=m['destination'] or not c.peer_approved or n>=m['expires']:raise RuleViolation('prepared receiving covenant required')
        view=peer(w,verified,'identity/'+a['source'],m['source'])
        if view.get('payload')!=c.payload or view.get('destination')!=w.chain or view.get('destination_key')!=a['key'] or view.get('expires')!=m['expires']:raise RuleViolation('source exit receipt belongs to another receiving claim')
        row=view['row'];proof=[(bytes.fromhex(h),right) for h,right in view['proof']]
        if row[0]!=a['source'] or len(proof)>64 or not verify_proof(bytes.fromhex(m['root']),row_bytes(row),proof):raise RuleViolation('source cohort inclusion proof')
        existing=next((x for x,key in w.public_keys.items() if key==a['key']),None)
        expected=existing if existing is not None else name(m['source'],a['source'])
        if actor!=expected or (m['source'],a['source']) in c.claimed:raise RuleViolation('receiving identity namespace or replay')
        events=[t for t in c.daily if t>n-86400]
        total_events=[t for merge in w.mergers.values() for t in merge.daily if t>n-86400]
        mature=sum(w.registry.can(x,'VOTE',n)[0] for x in w.registry.ids)
        cap=min(5000,max(250,mature//1000))
        if len(total_events)>=cap:raise RuleViolation('aggregate receiving merger daily cap')
        if existing is not None and existing in w.registry.ids:
            identity=w.registry.get(existing)
            if identity.status is not Status.ACTIVE or not w.registry.can(existing,'VOTE',n)[0] or (identity.operator,identity.family)!=tuple(row[2:4]):raise RuleViolation('existing identity cannot be revived or relabeled by merger')
        else:
            if existing is not None:raise RuleViolation('pending/banned receiving key cannot bypass admission')
            w.debit(actor,w.params.citizen_bond)
            w.registry.register(actor,row[2],row[3],w.params.citizen_bond,n)
            w.registry.approve(Actor('MODULE','verified-merger-import'),actor,n)
            identity=w.registry.get(actor);identity.roles={Role.CITIZEN};identity.stake=0;identity.role_ready={}
            w.public_keys[actor]=a['key']
        c.claimed[m['source'],a['source']]=actor;c.claim_indices[view['index']]=actor;c.daily=events+[n]
        return {'citizen':actor,'warmup_until':identity.activated+3*86400}
    if op=='merger.restore':
        fields(a,('id','peer','status_proof'))
        c=w.mergers[a['id']];m=c.manifest;record=w.exported_identities[actor]
        if w.chain!=m['source'] or record['payload']!=c.payload:raise RuleViolation('source export restoration domain')
        view=peer(w,verified,'merger/'+a['id'],m['destination'])
        if view.get('payload')!=c.payload or view.get('time',0)<m['expires'] or n<m['expires']:raise RuleViolation('receiving deadline must be irreversibly closed')
        proof=[(bytes.fromhex(h),right) for h,right in a['status_proof']]
        if len(proof)>64 or not verify_proof(bytes.fromhex(view['claimed_root']),row_bytes((record['index'],None)),proof):raise RuleViolation('prove source export remained unclaimed')
        i=w.registry.get(actor)
        if i.status is not Status.EXITED:raise RuleViolation('export is not exited')
        w.debit(actor,w.params.citizen_bond);i.bond=w.params.citizen_bond;i.status=Status.ACTIVE;i.roles={Role.CITIZEN};i.activated=n;i.stake=0;i.role_ready={}
        del w.exported_identities[actor];w.registry._log(n,Actor.agent(actor),'MERGER_UNCLAIMED_RESTORED',m['id']);return {'restored':True,'warmup_until':n+3*86400}
    raise RuleViolation('unknown native merger operation')


def exports(w):
    values={'society':{'chain':w.chain,'elected':w.monthly.points is not None}}
    for actor,receipt in getattr(w,'transaction_receipts',{}).items():values['receipt/'+actor]={'chain':w.chain,**receipt}
    for ident,(rows,tree) in getattr(w,'populations',{}).items():
        values['population/'+ident]={'chain':w.chain,'root':tree.root.hex(),'size':len(rows)}
    for ident,c in getattr(w,'mergers',{}).items():values['merger/'+ident]=c.summary()
    for agent,record in getattr(w,'exported_identities',{}).items():values['identity/'+agent]=record
    return values
