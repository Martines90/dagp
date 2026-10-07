"""Bounded parameter updates and UTC calendar-month proposal-credit renewal."""
from dataclasses import replace
from datetime import datetime,timezone
from .params import Params
from .treasury import RuleViolation
from .tally import Kind,Outcome
from .session import ELECTION,Phase
from .election import allocate_credits

MUTABLE={'quorum_bps','credit_step_bps','credit_ceiling_bps','party_threshold_bps',
         'max_bill_points','weight_mode','max_articles_counted','bill_mode'}

def validate_changes(params,changes):
    if type(changes) is not tuple or not changes or len(changes)>len(MUTABLE):raise RuleViolation('typed parameter changes required')
    if any(type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not str or pair[0] not in MUTABLE for pair in changes):
        raise RuleViolation('unknown or protected parameter')
    if len({k for k,_ in changes})!=len(changes):raise RuleViolation('duplicate parameter update')
    for key,value in changes:
        if key in ('weight_mode','bill_mode'):
            if value not in (('WEIGHTED','FLAT') if key=='weight_mode' else ('INDEPENDENT','PACKAGE')):
                raise RuleViolation('unknown parameter value')
        elif type(value) is not int or value<0:raise RuleViolation('integer parameter value required')
    if any(k=='max_articles_counted' and v>100 for k,v in changes):raise RuleViolation('weight cap exceeds bound')
    try:return replace(params,**dict(changes))
    except ValueError as error:raise RuleViolation(str(error)) from error

def month_at(seconds):
    if type(seconds) is not int or not 0<=seconds<=253402300799:raise RuleViolation('committed UTC timestamp required')
    date=datetime.fromtimestamp(seconds,timezone.utc)
    return date.year,date.month

def next_month(month):
    year,m=month
    if year==9999 and m==12:raise RuleViolation('month outside supported range')
    return (year+1,1) if m==12 else (year,m+1)

class ParameterGovernance:
    def __init__(self,registry):self.registry=registry;self.active=registry.p;self.pending=None;self.used=set();self.time=0
    def schedule(self,session,timestamp):
        month=month_at(timestamp)
        if timestamp<self.time or self.pending is not None:raise RuleViolation('backdated or conflicting update')
        if (session.registry is not self.registry or session.phase is not Phase.FINAL or session.outcome is not Outcome.PASSED
                or session.kind is not Kind.PARAMETER or not session.approved_record_hash
                or session.rules_hash!=self.active.snapshot_hash() or session.issue in self.used):
            raise RuleViolation('finalized matching parameter referendum required')
        session._check_review_effects()
        candidate=validate_changes(self.active,session.parameter_changes)
        activation=next_month(month)
        self.pending=(activation,candidate,session.issue);self.used.add(session.issue);self.time=timestamp
        return activation
    def tick(self,timestamp):
        month=month_at(timestamp)
        if timestamp<self.time:raise RuleViolation('backdated governance clock')
        self.time=timestamp
        if self.pending is not None and month>=self.pending[0]:
            _,candidate,_=self.pending
            self.active=candidate;self.registry.p=candidate;self.pending=None
        return self.active

class MonthlyCredits:
    def __init__(self,ledger,registry):
        self.ledger,self.registry=ledger,registry;self.points=None;self.total=0;self.governing=();self.used=set();self.time=0
    def record_election(self,session,timestamp):
        month_at(timestamp)
        if (timestamp<self.time or session.registry is not self.registry or session.kind!=ELECTION
                or session.phase is not Phase.FINAL or session.outcome is not Outcome.PASSED
                or not session.result.valid or session.issue in self.used):
            raise RuleViolation('new finalized election required')
        points=dict(session.result.points);total=session.result.total_points
        if total<=0 or any(type(n) is not int or n<0 for n in points.values()) or sum(points.values())!=total:
            raise RuleViolation('invalid election totals')
        governing=tuple(sorted(q for q,n in points.items() if n*10000>=total*session.p.party_threshold_bps))
        if tuple(session.result.governing_parties)!=governing:raise RuleViolation("invalid frozen parliament roster")
        self.governing=governing
        self.ledger.eligible_parties=frozenset(governing)
        for party in self.ledger.balance:
            if party not in self.ledger.eligible_parties:self.ledger.balance[party]=0
        self.points,self.total=points,total;self.used.add(session.issue);self.time=timestamp
        # Subsequent elections replace the NEXT month's basis, never mint another current allowance.
        if self.ledger.month is None:return self.tick(timestamp)
        return False
    def tick(self,timestamp):
        month=month_at(timestamp)
        if timestamp<self.time:raise RuleViolation('backdated credit clock')
        if self.points is None:raise RuleViolation('election basis required')
        if self.ledger.month is not None and month<self.ledger.month:raise RuleViolation('month reversal')
        if self.ledger.month==month:self.time=timestamp;return False
        allowances=allocate_credits(self.points,self.total,replace(self.registry.p,party_threshold_bps=0))
        allowances={party:amount if party in self.governing else 0 for party,amount in allowances.items()}
        # Replace unused balances, preserve debt. Skipped months never accumulate credits.
        self.ledger.balance={};self.ledger.month=month
        for party,amount in allowances.items():self.ledger.grant(party,amount)
        self.time=timestamp
        return True
