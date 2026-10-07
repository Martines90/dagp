"""Optional nested polities and institutional mandates for the Python reference.

MODULE, registry identities, consensus time and assignment beacons are trusted
keeper inputs. This is not a native keeper or a cross-chain finality verifier.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from .crypto_sim import H, hx
from .ledger import canonical
from .roles import Actor, Role, RoleRegistry, SENSITIVE_OFFICES
from .scale import Electorate
from .session import Phase, snapshot_electorate
from .tally import Kind, Outcome
from .treasury import RuleViolation, Treasury, _integer

M = Actor('MODULE', 'societies')
OFFICES = {Role.ADMIN, Role.REGISTRAR, Role.SAFETY_COUNCIL, Role.VOTE_SUPERVISOR,
           Role.VALIDATOR, Role.PARTY_MEMBER}
QUALIFICATIONS={Role.EXAMINER,Role.VERIFIER,Role.REVIEWER,Role.JUROR,Role.EXECUTOR}


def text(value, limit=256):
    if type(value) is not str or not 0 < len(value) <= limit:
        raise RuleViolation('bounded nonempty identifier required')
    return value


def digest(value):
    return hx(canonical(value))


def keeper(actor):
    if type(actor) is not Actor or actor.kind != 'MODULE':
        raise RuleViolation('trusted keeper capability required')


def rules(items):
    if (type(items) is not tuple or any(type(p) is not tuple or len(p) != 2 for p in items)
            or len(items) > 128):
        raise RuleViolation('typed charter constraints required')
    for key, value in items:
        text(key,128); text(value,4096)
    if tuple(sorted(items)) != items or len(dict(items)) != len(items):
        raise RuleViolation('unique sorted charter constraints required')
    return items


@dataclass(frozen=True)
class Society:
    ident: str
    parent: str | None
    members: tuple  # root uses live global citizenship, other scopes use admitted membership
    charter: tuple


@dataclass(frozen=True)
class ParentRequest:
    ident: str
    scope: str
    issue: str
    payload: str
    budget: int
    context: str
    subjects: tuple
    opened: int
    expires: int
    stage: str = 'PRE'
    decision: str = ''


class InstitutionalMandate:
    """Engine-created, single-session structural ballot capability, not an approval flag."""
    def __init__(self, engine, issue, kind, registry, electorate, payload, opened, notice,
                 expires, context, subjects=()):
        self.engine,self.issue,self.kind,self.registry = engine,issue,kind,registry
        self.electorate,self.payload,self.opened,self.notice = electorate,payload,opened,notice
        self.expires,self.context,self.session = expires,context,None
        self.subjects=subjects

    def validate_open(self, issue, kind, registry, payload, root, size, height, windows,
                      effects, point_ids, parameter_changes, params):
        if (self.engine._mandates.get(self.issue) is not self or self.session is not None
                or (issue,kind,registry,payload,root,size) !=
                   (self.issue,self.kind,self.registry,self.payload,self.electorate.root,self.electorate.size)
                or height < self.opened+self.notice or windows.challenge_end > self.expires
                or point_ids or parameter_changes or effects is not None
                or params.snapshot_hash()!=registry.p.snapshot_hash()):
            raise RuleViolation('matching unused, matured institutional mandate required')
        self.engine.check_context(self.context)

    def bind(self, session):
        if self.session is not None:raise RuleViolation('institutional mandate already consumed')
        self.session=session

    def check(self, session):
        if (session is None or self.engine._mandates.get(self.issue) is not self or self.session is not session
                or session.approved_record_hash != self.payload or session.registry is not self.registry
                or session.kind is not self.kind or session.root != self.electorate.root
                or session.size != self.electorate.size
                or session.p.snapshot_hash()!=self.registry.p.snapshot_hash()
                or session.rules_hash!=session.p.snapshot_hash() or session.effects.ceiling
                or session.effects.treasury is not None or session.effects.credits is not None
                or session.point_ids or session.parameter_changes):
            raise RuleViolation('institutional decision context changed')
        self.engine.check_context(self.context)

    def certificate(self, height):
        self.check(self.session)
        if (self.session.phase is not Phase.FINAL or self.session.outcome is not Outcome.PASSED
                or height < self.session.w.challenge_end or height > self.expires):
            raise RuleViolation('finalized, unexpired institutional approval required')
        # Recompute from accepted ballots; do not trust an externally supplied pass flag.
        from .tally import Ballot,tally
        result=tally([Ballot(a,c,w) for a,(c,w) in self.session._sealed.items()],
                     self.electorate.size,self.kind,self.session.p)
        if result != self.session.result or result.outcome is not Outcome.PASSED:
            raise RuleViolation('institutional certificate tally mismatch')
        return digest((self.issue,self.payload,self.electorate.root.hex(),self.session.commitment.hex()))


class ScopedRegistry(RoleRegistry):
    """Local political/party state with root standing checked on every action.

Identity copies isolate local sanctions/offices; only the root registry may change
root citizenship. Root qualified workers may serve locally, but offices do not flow down.
"""
    def __init__(self, tree, scope):
        if scope not in tree._applied or scope in tree._views:
            raise RuleViolation('unique activated local registry required')
        super().__init__(tree.reg.p)
        self.tree,self.scope=tree,scope
        for agent in tree.nodes[scope].members:
            identity=copy.deepcopy(tree.reg.get(agent))
            identity.roles-=OFFICES
            identity.role_ready={};self.ids[agent]=identity
        self.p=tree.reg.p
        self._sessions={}

    @property
    def p(self):
        return self.tree.reg.p if hasattr(self,'tree') else self._p

    @p.setter
    def p(self,value):
        if hasattr(self,'tree') and value != self.tree.reg.p:
            raise RuleViolation('local scope cannot override root protocol parameters')
        self._p=value

    def grant(self,actor,agent,role,height,stake=0):
        if role in QUALIFICATIONS and role not in self.tree.reg.effective_roles(agent,height):
            raise RuleViolation('root-recognized professional qualification required')
        if role not in SENSITIVE_OFFICES:return super().grant(actor,agent,role,height,stake)
        root=self.tree.reg
        self.appointment_events=root.appointment_events
        self.appointment_height=max(self.appointment_height,root.appointment_height)
        super().grant(actor,agent,role,height,stake)
        root.appointment_events=self.appointment_events
        root.appointment_height=self.appointment_height

    def get(self,agent):
        identity=super().get(agent);root=self.tree.reg.get(agent)
        identity.operator,identity.family,identity.activated=root.operator,root.family,root.activated
        return identity

    def _guard_check(self,actor,height,category,ban=False):
        self.protection_events=self.tree.reg.protection_events
        self.protection_height=max(self.protection_height,self.tree.reg.protection_height)
        return super()._guard_check(actor,height,category,ban)

    def _guard_commit(self,event):
        super()._guard_commit(event)
        self.tree.reg.protection_events=self.protection_events
        self.tree.reg.protection_height=self.protection_height

    def _log(self,height,actor,action,target,detail=''):
        super()._log(height,actor,action,target,detail)
        self.tree.reg._log(height,actor,'SCOPE:'+action,self.scope+':'+target,detail)

    def effective_roles(self,agent,height):
        if (agent not in self.ids or not self.tree.is_member(self.scope,agent)
                or not self.tree.reg.can(agent,'VOTE',height)[0]):return set()
        for authority in self.tree.ancestry(self.scope)[:-1]:
            if authority!=self.tree.root and not self.tree.view(authority).can(agent,'VOTE',height)[0]:
                return set()
        self.get(agent)
        roles=super().effective_roles(agent,height)
        for authority in self.tree.ancestry(self.scope)[:-1]:
            if height<self.tree.view(authority).admin_holds.get(agent,0):
                roles-=SENSITIVE_OFFICES|QUALIFICATIONS
        return roles-(QUALIFICATIONS-self.tree.reg.effective_roles(agent,height))

    def validate_draft(self,issue,draft,height):
        if draft.parameter_changes:raise RuleViolation('local votes cannot change global protocol parameters')
        self.tree.require_preapproval(self.scope,issue,draft.digest(),height,draft.budget)

    def validate_session(self,issue,payload,height,effects,campaign,institutional,params=None):
        if params is not None and params.snapshot_hash()!=self.p.snapshot_hash():
            raise RuleViolation('local voting rules must match root protocol')
        if institutional is not None:return
        if issue in self._sessions:raise RuleViolation('one scoped session per issue')
        if campaign is not None:payload=campaign.digest()
        req=self.tree.require_preapproval(self.scope,issue,payload,height)
        if effects is not None and (effects.treasury is not None or effects.ceiling):
            raise RuleViolation('local votes use parent-reserved budgets, not direct treasury authority')
        if not req:raise RuleViolation('parent approval required')

    def check_session(self,session,height=None):
        if session.institutional is not None:return
        payload=session.campaign.digest() if session.campaign is not None else session.approved_record_hash
        self.tree.require_preapproval(self.scope,session.issue,payload,
                                      max(self.tree._height,session.open_height) if height is None else height)
        if session.p.snapshot_hash()!=self.p.snapshot_hash():raise RuleViolation('root voting rules changed')
        if session.registry is not self or session.effects.treasury is not None or session.effects.ceiling:
            raise RuleViolation('scoped vote authority changed')


class SocietyTree:
    def __init__(self,chain,root,registry,keyring,treasury,charter=(),max_depth=8):
        text(chain,64);text(root,128);rules(charter)
        if type(treasury) is not Treasury or type(max_depth) is not int or not 1<=max_depth<=16:
            raise RuleViolation('bounded hierarchy and common treasury required')
        if getattr(registry,'society_tree',None) is not None:raise RuleViolation('one polity tree per identity registry')
        self.chain,self.root,self.reg,self.kr,self.treasury = chain,root,registry,keyring,treasury
        self.nodes={root:Society(root,None,(),charter)};self.max_depth=max_depth
        self._views={root:registry};self._requests={};self._approvals={};self._active={}
        self._mandates={};self._formations={};self._applied=set();self._laws={};self._height=0
        registry.society_tree=self

    def _time(self,height):
        _integer(height)
        if height<max(self._height,self.reg.protection_height,self.reg.appointment_height):
            raise RuleViolation('backdated polity clock')

    def ancestry(self,scope):
        if scope not in self.nodes:raise RuleViolation('unknown jurisdiction')
        out=[]
        while scope is not None:
            out.append(scope);scope=self.nodes[scope].parent
        return tuple(reversed(out))

    def is_member(self,scope,agent):
        return agent in self.reg.ids and all(q==self.root or agent in self.nodes[q].members
                                            for q in self.ancestry(scope))

    def inherited_rules(self,scope):
        result={}
        for q in self.ancestry(scope):
            for key,value in self.nodes[q].charter:
                if key in result and result[key]!=value:raise RuleViolation('incompatible local charter; jurisdiction frozen')
                result[key]=value
        return tuple(sorted(result.items()))

    def context(self,scope):
        return digest((self.chain,scope,self.reg.p.snapshot_hash(),
                       [(q,self.nodes[q].charter,self.nodes[q].members) for q in self.ancestry(scope)],
                       [(q,tuple(sorted((issue,law[0]) for (jurisdiction,issue),law in self._laws.items()
                                       if jurisdiction==q))) for q in self.ancestry(scope)[:-1]]))

    def check_context(self,context):
        if not any(context==self.context(q) for q in self.nodes):
            raise RuleViolation('ancestor rules or membership changed; fresh approval required')

    def view(self,scope):
        if scope in self._formations and scope not in self._applied:
            raise RuleViolation("subsociety not activated by both populations")
        self.inherited_rules(scope)
        if scope not in self._views:self._views[scope]=ScopedRegistry(self,scope)
        return self._views[scope]

    def request(self,actor,scope,issue,payload,budget,subjects,height,expires,stage='PRE'):
        keeper(actor)
        self._time(height);text(issue);text(payload,64);_integer(budget)
        if scope in self._formations and scope not in self._applied and issue!='formation:'+scope:
            raise RuleViolation('pending subgroup only permits its formation request')
        if scope==self.root or type(expires) is not int or expires<=height or stage not in ('PRE','FINAL'):
            raise RuleViolation('parent jurisdiction, stage and expiry required')
        if type(subjects) is not tuple or not subjects or len(set(subjects))!=len(subjects):
            raise RuleViolation('distinct proposal beneficiaries required')
        for a in subjects:
            if not self.is_member(scope,a):raise RuleViolation('beneficiary outside jurisdiction')
        decision=''
        if stage=='FINAL':
            view=self._views.get(scope);session=getattr(view,'_sessions',{}).get(issue)
            if session is None or session.approved_record_hash!=payload:
                raise RuleViolation('final parent review binds an existing local decision')
            amount,_,_=self._local_effects(session)
            if budget!=amount:raise RuleViolation('final budget must match passing clauses')
            decision=session.commitment.hex()
        context=self.context(scope)
        ident=digest((scope,issue,payload,budget,context,height,expires,stage,decision))
        if ident in self._requests:raise RuleViolation('parent request replay')
        # One outstanding version per issue; no parallel approval shopping.
        if any(r.scope==scope and r.issue==issue and r.stage==stage and r.expires>=height
               and r.ident not in self._applied for r in self._requests.values()):
            raise RuleViolation('outstanding parent request must expire or settle first')
        self._requests[ident]=ParentRequest(ident,scope,issue,payload,budget,context,subjects,height,expires,stage,decision)
        self._approvals[ident]={};self._height=height
        self.reg._log(height,M,'PARENT_REQUEST',scope,ident)
        return ident

    def _request(self,request):
        if type(request) is not str or request not in self._requests:
            raise RuleViolation('known parent request required')
        return self._requests[request]

    def review_message(self,request,note,authority=None):
        r=self._request(request)
        authority=authority or self.nodes[r.scope].parent
        return H('parent-review-v1',self.chain,r.ident,r.stage,r.context,authority,note)

    def approve(self,request,reviewer,note,height,signature,authority=None):
        self._time(height);text(note,4096)
        r=self._request(request);self.check_context(r.context)
        authority=authority or self.nodes[r.scope].parent
        if authority not in self.ancestry(r.scope)[:-1]:raise RuleViolation('ancestor authority required')
        key=(authority,reviewer)
        if height>r.expires or request in self._applied or key in self._approvals[request]:
            raise RuleViolation('expired, settled or duplicate parent review')
        parent=self.view(authority)
        service=getattr(parent,'assignments',None)
        if service is None:raise RuleViolation('assigned parent review required')
        result=service._results.get(('hierarchy_review',r.ident))
        if result is None or reviewer not in result.members:raise RuleViolation('reviewer not assigned by parent')
        service.require(service.chain,'hierarchy_review',r.ident,result.members,height,r.subjects)
        if not parent.can(reviewer,'SUPERVISE_VOTE',height)[0]:raise RuleViolation('parent supervisory authority required')
        if type(signature) is not str or not self.kr.verify(reviewer,self.review_message(request,note,authority),signature):
            raise RuleViolation('invalid parent review signature')
        self._approvals[request][key]=(note,height,signature);self._height=height
        self.reg._log(height,Actor.agent(reviewer),'PARENT_REVIEW',r.scope,r.ident)

    def _approved(self,request,height):
        r=self._request(request);self.check_context(r.context)
        if height>r.expires:raise RuleViolation('parent permission expired')
        for authority in self.ancestry(r.scope)[:-1]:
            parent=self.view(authority);service=getattr(parent,'assignments',None)
            if service is None:raise RuleViolation('ancestor assignment missing')
            result=service._results.get(('hierarchy_review',r.ident))
            if result is None:raise RuleViolation('ancestor review not assigned')
            service.require(service.chain,'hierarchy_review',r.ident,result.members,height,r.subjects)
            if any((authority,a) not in self._approvals[request] for a in result.members):
                raise RuleViolation('all assigned ancestor reviews required')
        return r

    def activate_preapproval(self,request,height):
        self._time(height);r=self._approved(request,height)
        if r.stage!='PRE' or request in self._applied:raise RuleViolation('unused preapproval required')
        previous=self._active.get((r.scope,r.issue))
        if previous is not None:
            old=self._requests[previous]
            view=self._views.get(r.scope)
            if (view is not None and r.issue in getattr(view,'_sessions',{})) or (r.scope,r.issue) in self._laws:
                raise RuleViolation('opened votes and enacted decisions cannot be silently revised')
            if r.budget>old.budget:raise RuleViolation('revision cannot increase the approved budget')
            if old.budget and 'scope:'+previous not in self.treasury.reserved:
                raise RuleViolation('previous parent reserve unavailable')
            if old.budget:self.treasury.release_reservation('scope:'+previous)
        if r.budget:self.treasury.reserve('scope:'+request,r.budget)
        self._active[r.scope,r.issue]=request;self._applied.add(request);self._height=height
        self.reg._log(height,M,'PARENT_PREAPPROVED',r.scope,request)

    def require_preapproval(self,scope,issue,payload,height,budget=None):
        self._time(height);self.inherited_rules(scope)
        request=self._active.get((scope,issue))
        if request is None:raise RuleViolation('parent preapproval required before local activity')
        r=self._approved(request,height)
        if r.payload!=payload or (budget is not None and r.budget!=budget):
            raise RuleViolation('parent permission does not cover this exact version/budget')
        return r

    def _local_effects(self,session):
        from .tally import Ballot,tally,tally_bill,BillResult
        if session.phase is not Phase.FINAL or session.outcome not in (Outcome.PASSED,Outcome.PARTIAL):
            raise RuleViolation('passed finalized local decision required')
        session._check_review_effects()
        if session.point_ids:
            columns=[[Ballot(a,choices[i],w) for a,(choices,w) in session._sealed.items() if choices[i] is not None]
                     for i in range(len(session.point_ids))]
            expected=tally_bill(columns,session.size,session.kind,session.p)
            passing=set(expected.passing_points);indexes={q:i for i,q in enumerate(session.point_ids)}
            while True:
                retained={i for i in passing if all(indexes[q] in passing for q in session.point_dependencies[i])}
                if retained==passing:break
                passing=retained
            outcome=Outcome.PASSED if len(passing)==len(session.point_ids) else Outcome.PARTIAL if passing else expected.outcome
            expected=BillResult(outcome,expected.point_outcomes,tuple(sorted(passing)),expected.review_flag)
            tranches=tuple(n for i in sorted(passing) for n in session.effects.point_tranches[i])
            milestones=tuple(m for i in sorted(passing) for m in session.effects.point_milestones[i])
        else:
            if session.kind=='ELECTION':raise RuleViolation('elections cannot enact local laws or budgets')
            expected=tally([Ballot(a,c,w) for a,(c,w) in session._sealed.items()],session.size,session.kind,session.p)
            tranches=tuple(session.effects.tranches);milestones=session.effects.milestones
        if session.result!=expected or expected.outcome not in (Outcome.PASSED,Outcome.PARTIAL):
            raise RuleViolation('local decision tally mismatch')
        return sum(tranches),tranches,milestones

    def finalize_local(self,request,session,tranches,height):
        self._time(height);r=self._approved(request,height)
        original=self.require_preapproval(r.scope,r.issue,r.payload,height)
        if (r.stage!='FINAL' or request in self._applied or (r.scope,r.issue) in self._laws
                or session.registry is not self.view(r.scope) or session.issue!=r.issue
                or session.approved_record_hash!=r.payload
                or self.view(r.scope)._sessions.get(session.issue) is not session
                or r.decision!=session.commitment.hex() or r.budget>original.budget):
            raise RuleViolation('matching local decision and final parent approval required')
        amount,expected,milestones=self._local_effects(session)
        if type(tranches) is not tuple or tranches!=expected or amount!=r.budget:
            raise RuleViolation('exact approved passing-clause tranche schedule required')
        project='scope:'+original.ident
        if original.budget:
            if amount:
                self.treasury.commit_reserved(project,list(tranches))
                self.treasury.milestone_conditions[project]=milestones
            else:self.treasury.release_reservation(project)
        self._laws[r.scope,r.issue]=(r.payload,r.context,project,session.effective_points)
        self._applied.add(request);self._height=height
        self.reg._log(height,M,'LOCAL_DECISION_ENACTED',r.scope,request)
        return project

    def record_root_decision(self,actor,session,height):
        keeper(actor);self._time(height)
        if (session.registry is not self.reg or session.kind in (Kind.FORMATION,Kind.MERGER,'ELECTION')
                or not session.approved_record_hash or (self.root,session.issue) in self._laws):
            raise RuleViolation('new reviewed root law decision required')
        self._local_effects(session)
        self._laws[self.root,session.issue]=(session.approved_record_hash,self.context(self.root),
                                           session.effects.project,session.effective_points)
        self._height=height
        self.reg._log(height,actor,'ROOT_LAW_RECORDED',session.issue,session.approved_record_hash)

    def law_is_current(self,scope,issue):
        law=self._laws.get((scope,issue))
        return bool(law) and law[1]==self.context(scope)

    def expire(self,scope,issue,height):
        self._time(height);request=self._active.get((scope,issue))
        if request is None or height<=self._requests[request].expires:raise RuleViolation('expired permission required')
        project='scope:'+request
        if project in self.treasury.reserved:self.treasury.release_reservation(project)
        del self._active[scope,issue];self._height=height
        self.reg._log(height,M,'PARENT_PERMISSION_EXPIRED',scope,request)

    def propose_child(self,parent,child,members,charter,nonce,height,expires,signatures):
        self._time(height);text(child,128);text(nonce);rules(charter)
        if child in self.nodes or child in self._formations or len(self.ancestry(parent))>=self.max_depth:
            raise RuleViolation('unique child within bounded hierarchy required')
        if type(members) is not tuple or any(type(a) is not str for a in members) or len(members)<self.reg.p.min_party_members or tuple(sorted(set(members)))!=members:
            raise RuleViolation('sorted distinct consenting subgroup required')
        if set(signatures)!=set(members):raise RuleViolation('each founding member must consent')
        if type(expires) is not int or expires<=height+14*self.reg.p.protection_day_blocks:
            raise RuleViolation('adequate formation review, vote and challenge lifetime required')
        inherited=dict(self.inherited_rules(parent))
        if any(k in inherited and inherited[k]!=v for k,v in charter):raise RuleViolation('child contradicts ancestor law')
        electorate=snapshot_electorate(self.view(parent),height)
        for a in members:
            if a not in electorate.ids or not self.is_member(parent,a):raise RuleViolation('founder is not an eligible parent citizen')
        payload=digest((self.chain,parent,child,members,charter,nonce))
        message=H('subsociety-opt-in-v1',self.chain,payload)
        if any(type(signatures[a]) is not str or not self.kr.verify(a,message,signatures[a]) for a in members):
            raise RuleViolation('invalid subgroup consent signature')
        # Pending node supplies a scope for parent review; it has no active governance view yet.
        self.nodes[child]=Society(child,parent,members,charter)
        self._formations[child]=(payload,height,expires,None,None)
        request=self.request(M,child,'formation:'+child,payload,0,members,height,expires)
        return request

    def formation_message(self,parent,child,members,charter,nonce):
        return H('subsociety-opt-in-v1',self.chain,digest((self.chain,parent,child,members,charter,nonce)))

    def formation_mandates(self,child,height):
        self._time(height)
        if type(child) is not str or child not in self._formations:raise RuleViolation('known child formation required')
        payload,opened,expires,left,right=self._formations[child]
        if left is not None:raise RuleViolation('formation mandates already created')
        self.require_preapproval(child,'formation:'+child,payload,height,0)
        node=self.nodes[child];registry=self.view(node.parent)
        parent_el=snapshot_electorate(registry,opened)
        cohort=Electorate(node.members);context=self.context(child)
        notice=7*self.reg.p.protection_day_blocks
        if expires<=opened+notice:raise RuleViolation('formation notice and vote windows required')
        mandates=[]
        for side,el in (('parent',parent_el),('child',cohort)):
            issue='formation:'+child+':'+side
            mandate=InstitutionalMandate(self,issue,Kind.FORMATION,registry,el,payload,opened,notice,expires,context,node.members)
            self._mandates[issue]=mandate;mandates.append(mandate)
        self._formations[child]=(payload,opened,expires,*mandates);self._height=height
        return tuple(mandates)

    def activate_child(self,child,height):
        self._time(height)
        if type(child) is not str or child not in self._formations:raise RuleViolation('known child formation required')
        payload,opened,expires,left,right=self._formations[child]
        if left is None or child in self._applied:raise RuleViolation('paired formation decisions required')
        left.certificate(height);right.certificate(height)
        cooldown=max(left.session.w.challenge_end,right.session.w.challenge_end)+7*self.reg.p.protection_day_blocks
        if height<cooldown:raise RuleViolation('formation cooling-off period incomplete')
        self.require_preapproval(child,'formation:'+child,payload,height,0)
        self._applied.add(child);self._height=height
        self.reg._log(height,M,'SUBSOCIETY_ACTIVATED',child,payload)
        return self.view(child)
