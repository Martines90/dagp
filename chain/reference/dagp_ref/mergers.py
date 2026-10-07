"""Bilateral, identity-only merger reference with in-process finality trust.

No asset transfers, external proof verifier or native migrations are provided.
Source/destination objects stand in for independently verified native checkpoints.
"""
from dataclasses import dataclass
from .crypto_sim import H, MerkleTree, verify_proof
from .societies import InstitutionalMandate, digest, text, keeper
from .scale import Electorate
from .session import snapshot_electorate
from .roles import Status, Role, Actor
from .tally import Kind
from .treasury import RuleViolation, _integer


@dataclass(frozen=True)
class MergePlan:
    ident: str
    source: str
    destination: str
    manifest: tuple  # (source identity, target identity, reconciled operator, family, source age, frozen source key fingerprint)
    export_root: bytes
    opened: int
    expires: int
    daily_limit: int
    source_context: str
    destination_context: str
    source_checkpoint: str
    destination_checkpoint: str


class SocietyMerger:
    def __init__(self,source,destination,ident,mapping,height,expires,assets=()):
        text(ident,96);_integer(height);_integer(expires)
        if source is destination or source.chain==destination.chain or assets:
            raise RuleViolation('distinct societies and identity-only migration required; assets unsupported')
        source._time(height);destination._time(height)
        self.source,self.destination=source,destination
        if not hasattr(source,'_merge_plans'):source._merge_plans={};source._exported={}
        if not hasattr(destination,'_merge_plans'):destination._merge_plans={};destination._exported={}
        if ident in source._merge_plans or ident in destination._merge_plans:raise RuleViolation('merger identifier reused')
        day=source.reg.p.protection_day_blocks
        if destination.reg.p.protection_day_blocks!=day or expires<=height+60*day:
            raise RuleViolation('compatible committed-time conversion and review/challenge windows required')
        electorate=snapshot_electorate(source.reg,height)
        citizens=tuple(a for a in electorate.ids if source.reg.age(a,height)>=30*day)
        dest_el=snapshot_electorate(destination.reg,height)
        dest_ids=tuple(a for a in dest_el.ids if destination.reg.age(a,height)>=30*day)
        if not citizens or not dest_ids or type(mapping) is not tuple or len(mapping)!=len(citizens):
            raise RuleViolation('complete mature source mapping and receiving electorate required')
        if any(type(pair) is not tuple or len(pair)!=2 or any(type(v) is not str for v in pair) for pair in mapping):raise RuleViolation('typed identity mapping required')
        mappings=dict(mapping)
        if tuple(sorted(mappings))!=citizens or len(mappings)!=len(mapping):raise RuleViolation('exact unique source mapping required')
        if len(set(mappings.values()))!=len(mappings):raise RuleViolation('many-to-one aliases require prior identity adjudication')
        destination_keys={}
        for target in destination.reg.ids:
            if target in destination.kr._secrets:
                key=self.key_fingerprint(destination.kr,target)
                destination_keys.setdefault(key,[]).append(target)
        manifest=[];source_keys=set()
        for a in citizens:
            target=text(mappings[a]);i=source.reg.get(a)
            source_key=self.key_fingerprint(source.kr,a)
            if source_key in source_keys:raise RuleViolation('source signing-key aliases require identity adjudication')
            source_keys.add(source_key)
            duplicates=destination_keys.get(source_key,[])
            if duplicates and duplicates!=[target]:raise RuleViolation('known receiving signing key must deduplicate to its existing identity')
            if target in destination.reg.ids:
                other=destination.reg.get(target)
                if other.operator!=i.operator or other.family!=i.family:
                    raise RuleViolation('existing identity/operator reconciliation mismatch')
            elif target != 'merge:'+digest((source.chain,a)):
                raise RuleViolation('new identity requires collision-resistant source namespace')
            manifest.append((a,target,i.operator,i.family,i.activated,source_key))
        manifest=tuple(manifest)
        self._tree=MerkleTree([H(*record) for record in manifest])
        self._index={record[0]:n for n,record in enumerate(manifest)}
        limit=min(5000,max(250,len(dest_ids)//1000))
        self.plan=MergePlan(ident,source.chain,destination.chain,manifest,self._tree.root,height,expires,limit,
                            source.context(source.root),destination.context(destination.root),
                            source.reg.audit[-1]['hash'] if source.reg.audit else '',
                            destination.reg.audit[-1]['hash'] if destination.reg.audit else '')
        self.payload=digest(self.plan.__dict__ | {'export_root':self.plan.export_root.hex()})
        self.state='REVIEW';self._height=height;self._claimed={};self._events=[];self._approvals={};self._mandates={};self._pair=None;self._deposits={}
        source._merge_plans[ident]=self;destination._merge_plans[ident]=self
        self._assessment={}
        for tree in (source,destination):
            task='merger:'+ident
            self._assessment[tree.chain]=(task,(citizens[0],) if tree is source else (dest_ids[0],))
        self._electorates={source.chain:Electorate(citizens),destination.chain:Electorate(dest_ids)}

    @staticmethod
    def key_fingerprint(keyring,agent):
        # Comparison stand-in only; native implementations index actual public keys.
        if agent not in keyring._secrets:raise RuleViolation('known identity signing key required')
        return keyring.sign(agent,H('reference-key-fingerprint-v1'))

    def _time(self,height):
        _integer(height)
        if height<self._height or height>self.plan.expires:raise RuleViolation('backdated or expired merger')
        self.source._time(height);self.destination._time(height)

    def check_context(self,context):
        if self.source._merge_plans.get(self.plan.ident) is not self or self.destination._merge_plans.get(self.plan.ident) is not self:
            raise RuleViolation('unknown merger keeper context')
        if digest(self.plan.__dict__ | {'export_root':self.plan.export_root.hex()}) != self.payload:
            raise RuleViolation('merger inventory changed')
        self.source.check_context(self.plan.source_context);self.destination.check_context(self.plan.destination_context)
        if context!=self.payload:raise RuleViolation('wrong merger context')

    def assessment_message(self,chain,note):
        return H('merger-assessment-v1',chain,self.payload,note)

    def assess(self,tree,reviewer,note,height,signature):
        self._time(height);self.check_context(self.payload);text(note,4096)
        if self.state!='REVIEW' or tree not in (self.source,self.destination):raise RuleViolation('active bilateral review required')
        service=getattr(tree.reg,'assignments',None);task,subjects=self._assessment[tree.chain]
        result=service._results.get(('hierarchy_review',task)) if service else None
        if result is None or reviewer not in result.members:raise RuleViolation('independent assigned merger assessor required')
        service.require(tree.chain,'hierarchy_review',task,result.members,height,subjects)
        key=tree.chain,reviewer
        if key in self._approvals or type(signature) is not str or not tree.kr.verify(reviewer,self.assessment_message(tree.chain,note),signature):
            raise RuleViolation('duplicate or unsigned merger assessment')
        self._approvals[key]=(note,height,signature);self._height=height
        tree.reg._log(height,Actor.agent(reviewer),'MERGER_ASSESSMENT',self.plan.ident,self.payload)

    def mandates(self,height):
        self._time(height);self.check_context(self.payload)
        if self._pair is not None:raise RuleViolation('one pair of merger mandates per plan')
        out=[]
        for tree in (self.source,self.destination):
            task,subjects=self._assessment[tree.chain];service=getattr(tree.reg,'assignments',None)
            result=service._results.get(('hierarchy_review',task)) if service else None
            if result is None or any((tree.chain,a) not in self._approvals for a in result.members):
                raise RuleViolation('both societies require all assigned assessments')
            service.require(tree.chain,'hierarchy_review',task,result.members,height,subjects)
            issue='merger:'+self.plan.ident+':'+tree.chain
            mandate=InstitutionalMandate(self,issue,Kind.MERGER,tree.reg,self._electorates[tree.chain],self.payload,
                                          self.plan.opened,30*tree.reg.p.protection_day_blocks,self.plan.expires,self.payload,subjects)
            out.append(mandate)
        self._pair=tuple(out);self._mandates={m.issue:m for m in out}
        self._height=height
        return self._pair

    def prepare(self,actor,height):
        keeper(actor);self._time(height);self.check_context(self.payload)
        if self.state!='REVIEW' or self._pair is None:raise RuleViolation('unprepared reviewed merger required')
        for mandate in self._pair:mandate.certificate(height)
        end=max(m.session.w.challenge_end for m in self._pair)+30*self.source.reg.p.protection_day_blocks
        if height<end:raise RuleViolation('bilateral post-vote challenge period incomplete')
        self.state='CLAIMING';self._height=height
        self.source._height=height;self.destination._height=height
        for tree in (self.source,self.destination):tree.reg._log(height,Actor('MODULE','mergers'),'MERGER_PREPARED',self.plan.ident,self.payload)

    def proof(self,agent):return self._tree.proof(self._index[agent])

    def record_admission_bond(self,actor,agent,receipt,amount,height):
        """Trusted payment keeper attests an already funded receiving admission bond.
        Not a payment API or a transfer of source money; native custody must verify it.
        """
        keeper(actor);self._time(height);self.check_context(self.payload);text(receipt,128)
        if agent not in self._index or agent in self._deposits or self.state!='CLAIMING':
            raise RuleViolation('unique pending source admission required')
        target=self.plan.manifest[self._index[agent]][1]
        if target in self.destination.reg.ids or type(amount) is not int or amount!=self.destination.reg.p.citizen_bond:
            raise RuleViolation('new identity and exact receiving admission deposit required')
        if not hasattr(self.destination,'_bond_receipts'):self.destination._bond_receipts=set()
        if receipt in self.destination._bond_receipts:raise RuleViolation('bond receipt already reserved')
        self.destination._bond_receipts.add(receipt);self._deposits[agent]=(receipt,amount)
        self._height=height;self.destination._height=height
        self.destination.reg._log(height,actor,'MERGER_BOND_RESERVED',self.plan.ident,receipt)

    def claim_message(self,agent,nonce,expires):
        return H('merger-claim-v1',self.plan.source,self.plan.destination,self.payload,agent,
                 self.plan.manifest[self._index[agent]][1],nonce,expires)

    def claim(self,agent,nonce,expires,proof,source_signature,destination_signature,height):
        self._time(height);self.check_context(self.payload);text(nonce,128)
        if self.state!='CLAIMING' or agent not in self._index or agent in self._claimed:
            raise RuleViolation('live single-use source claim required')
        if type(expires) is not int or not height<=expires<=self.plan.expires:raise RuleViolation('claim expired or outside plan lifetime')
        record=self.plan.manifest[self._index[agent]];a,target,operator,family,activated,source_key=record
        if type(proof) is not list or len(proof)>64 or any(type(p) is not tuple or len(p)!=2 or type(p[0]) is not bytes or len(p[0])!=32 or type(p[1]) is not bool for p in proof):
            raise RuleViolation('bounded typed export proof required')
        if not verify_proof(self.plan.export_root,H(*record),proof):raise RuleViolation('invalid export membership proof')
        i=self.source.reg.get(a)
        if (a in self.source._exported or i.status is not Status.ACTIVE or
                (i.operator,i.family,i.activated)!=(operator,family,activated)
                or self.key_fingerprint(self.source.kr,a)!=source_key
                or not self.source.reg.can(a,'VOTE',height)[0]):
            raise RuleViolation('source identity changed, sanctioned or already exported')
        message=self.claim_message(a,nonce,expires)
        if (type(source_signature) is not str or type(destination_signature) is not str
                or not self.source.kr.verify(a,message,source_signature)
                or not self.destination.kr.verify(target,message,destination_signature)):
            raise RuleViolation('source and receiving key holders must individually consent')
        day=self.destination.reg.p.protection_day_blocks
        recent=[h for h in self._events if height-day<h]
        # Aggregate across all receiving mergers; splitting plans cannot multiply the lane.
        combined=sum(height-day<h for merge in self.destination._merge_plans.values()
                     if merge.destination is self.destination for h in merge._events)
        if combined>=self.plan.daily_limit:raise RuleViolation('shared rolling migration budget exhausted')
        reg=self.destination.reg
        receiving_key=self.key_fingerprint(self.destination.kr,target)
        if any(other!=target and other in self.destination.kr._secrets
               and self.key_fingerprint(self.destination.kr,other)==receiving_key for other in reg.ids):
            raise RuleViolation('receiving key already controls another identity')
        if target in reg.ids:
            other=reg.get(target)
            if (other.status is not Status.ACTIVE or other.operator!=operator or other.family!=family
                    or not reg.can(target,'VOTE',height)[0]):raise RuleViolation('receiving duplicate identity is not compatible and active')
        else:
            if a not in self._deposits:raise RuleViolation('verified receiving admission bond required')
            # Stage all registry writes first: a refused admission consumes no claim or quota.
            staged=__import__('copy').copy(reg)
            staged.ids=dict(reg.ids);staged.audit=list(reg.audit)
            staged.register(target,operator,family,self._deposits[a][1],height)
            staged.approve(Actor('MODULE','merger-import'),target,height)
            identity=staged.get(target)
            identity.roles={Role.CITIZEN};identity.stake=0;identity.role_ready={}
            # Never replace registry objects held by sessions/assignments; commit only admission fields.
            reg.ids[target]=identity
            for entry in staged.audit[len(reg.audit):]:reg.audit.append(entry)
        # No source funds, party offices, local scopes, credits or voting sessions are copied.
        self.source._exported[a]=(self.plan.ident,target)
        i.status=Status.EXITED
        self._claimed[a]=target;self._events=recent+[height];self._height=height
        self.source._height=height;self.destination._height=height
        self.source.reg._log(height,Actor.agent(a),'MERGER_EXIT',self.plan.ident,target)
        reg._log(height,Actor.agent(target),'MERGER_IDENTITY_IMPORTED',self.plan.ident,digest(record))
        return target

    def settle(self,actor,height):
        keeper(actor);_integer(height)
        if height<self._height or self.state!='CLAIMING' or height<=self.plan.expires:
            raise RuleViolation('claim period must close before settlement')
        self.state='SETTLED';self._height=height
        # Opt-outs remain source citizens; source is not shut down or silently archived.
        self.source.reg._log(height,actor,'MERGER_SETTLED',self.plan.ident,str(len(self._claimed)))

    def snapshot(self):
        return dict(plan=self.plan,payload=self.payload,state=self.state,claimed=dict(self._claimed),
                    unclaimed=tuple(a for a in self._index if a not in self._claimed),
                    unclaimed_bond_receipts={a:receipt for a,receipt in self._deposits.items() if a not in self._claimed})
