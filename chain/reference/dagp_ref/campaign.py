"""Frozen, signed candidate programs/visions and mandatory campaign comprehension."""
from dataclasses import dataclass
from .crypto_sim import H,hx
from .comprehension import ExamPlan,PROPOSAL_ARTICLE
from .treasury import RuleViolation

def source_hash(text):return hx('campaign-section-v1',text)

def article_id(party,section):return 'campaign:'+hx('party',party)+':'+section

@dataclass(frozen=True)
class Program:
    party:str
    author:str
    program:str
    vision:str
    nonce:str
    signature:str=''
    def message(self,chain,pre_commitment):
        return H(b'campaign-program-v1',chain,pre_commitment,self.party,self.author,self.program,self.vision,self.nonce)

@dataclass(frozen=True)
class Campaign:
    chain:str
    issue:str
    programs:tuple
    bank_hash:str
    pre_commitment:str
    pre_qualified:tuple
    start_height:int
    end_height:int
    election_deadline:int
    member_operators:tuple

    @classmethod
    def publish(cls,pre,issue,programs,bank,start_height,end_height):
        from .parties import PreElection
        if (type(pre) is not PreElection or pre.result is None or not pre.result.valid
                or type(issue) is not str or not issue or bank.issue_id!=issue
                or type(start_height) is not int or type(end_height) is not int
                or start_height<pre.close_height or start_height<pre.parties._height
                or end_height-start_height<pre.p.campaign_min_blocks or end_height>=pre.locked_until
                or type(programs) is not tuple or any(type(p) is not Program for p in programs)):
            raise RuleViolation('finalized pre-election and campaign window required')
        candidates=pre.result.qualified
        if len(programs)!=len(candidates) or {p.party for p in programs}!=set(candidates):
            raise RuleViolation('one signed program and vision per qualified party required')
        programs=tuple(sorted(programs,key=lambda p:p.party))
        for p in programs:
            if (any(type(t) is not str or not 0<len(t)<=16384 for t in (p.program,p.vision))
                    or type(p.nonce) is not str or not 0<len(p.nonce)<=128):raise RuleViolation('bounded campaign text required')
            pre.parties._member(p.author,p.party,start_height)
            pre.parties._sig(p.author,p.message(pre.parties.chain,pre.result.commitment),p.signature)
        operators=tuple(sorted({pre.reg.get(a).operator for party,members in pre.members if party in candidates for a in members}))
        record=cls(pre.parties.chain,issue,programs,bank.record_hash(),pre.result.commitment,candidates,
                   start_height,end_height,pre.locked_until,operators)
        record.check(bank,candidates,pre.p)
        if pre.result.commitment in pre.parties._campaigns or any(entry[1]==issue for entry in pre.parties._campaigns.values()):
            raise RuleViolation("one campaign/election issue per pre-election cycle")
        pre.parties._campaigns[pre.result.commitment]=(record.digest(),issue,False)
        pre.parties._height=start_height
        return record
    @property
    def articles(self):return tuple(article_id(p.party,section) for p in self.programs for section in ('program','vision'))
    def digest(self):return hx('campaign-record-v1',self)
    def check(self,bank,qualified,params):
        if bank.issue_id!=self.issue or bank.record_hash()!=self.bank_hash or tuple(sorted(qualified))!=tuple(sorted(self.pre_qualified)):
            raise RuleViolation('campaign/election roster or record mismatch')
        for program in self.programs:
            for section in ('program','vision'):
                article=article_id(program.party,section)
                questions=[q for q in bank.questions.values() if q.article_id==article]
                if (bank.article_cluster.get(article)!=article or len(questions)<params.campaign_questions_per_document
                        or any(not q.prompt or not q.choices or q.source_hash!=source_hash(getattr(program,section)) for q in questions)):
                    raise RuleViolation('every program and vision needs committed questions bound to its exact text')
    def plan(self,bank,seed,declared,params):
        self.check(bank,self.pre_qualified,params)
        if type(declared) is not tuple or any(type(a) is not str for a in declared) or len(set(declared))!=len(declared) or set(declared)!=set(self.articles):
            raise RuleViolation('all candidate programs and visions must be declared read')
        seed=H(b'campaign-exam',seed,self.bank_hash)
        proposal=tuple(bank.draw(seed,PROPOSAL_ARTICLE,params.exam_items))
        if len(proposal)!=params.exam_items:raise RuleViolation('campaign bank lacks election questions')
        sampled=tuple((a,q) for a in self.articles for q in bank.draw(seed,a,params.campaign_questions_per_document))
        return ExamPlan(proposal,sampled,self.articles,True)
