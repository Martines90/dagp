"""Shared builders: a small society, a question bank, and a helper that runs one voter end to end."""
from dagp_ref.comprehension import (PROPOSAL_ARTICLE, AttemptRegistry, Board, Question, QuestionBank,
                                    Submission, commit_key, grade_item_verdicts)
from dagp_ref.crypto_sim import SimKeyring, hx
from dagp_ref.params import Params
from dagp_ref.roles import Actor, Role, RoleRegistry
from dagp_ref.sortition import draw, panel_size
from dagp_ref.session import Effects, VoteSession, Windows, snapshot_electorate
from dagp_ref.tally import Kind

MODULE = Actor("MODULE", "test")
P = Params(quorum_bps=5000,credit_ceiling_bps=5000,min_citizen_age=10, exam_items=3, sample_articles=2, challenge_window=20, exam_panel=3)
ARTICLES = ("a1", "a2", "a3", "a4")
CLUSTERS = {"a1": "c1", "a2": "c2", "a3": "c3", "a4": "c3"}   # a3/a4 are near-duplicates


def build_bank(issue="prop1", n_proposal=6):
    qs, keys = [], {}

    def mk(qid, art):
        ans = int(hx("ans", qid)[:4], 16) % 4
        salt = f"s-{qid}"
        qs.append(Question(qid, art, 4, commit_key(ans, salt)))
        keys[qid] = (ans, salt)

    for i in range(n_proposal):
        mk(f"{issue}-p{i}", PROPOSAL_ARTICLE)
    for a in ARTICLES:
        for j in range(2):
            mk(f"{issue}-{a}-{j}", a)
    bank = QuestionBank(issue, qs, CLUSTERS)
    bank.load_keys(keys)
    return bank, keys


class Society:
    def __init__(self, n=30, n_ex=14, p=P):
        self.p, self.kr, self.reg = p, SimKeyring(), RoleRegistry(p)
        self.citizens = [f"c{i}" for i in range(n)]
        self.examiners = [f"e{i}" for i in range(n_ex)]
        for a in self.citizens + self.examiners:
            self.reg.register(a, f"op-{a}", f"fam{sum(map(ord, a)) % 4}", p.citizen_bond, 0)
            self.kr.register(a)
            self.reg.approve(MODULE, a, 0)
        for e in self.examiners:
            self.reg.grant(MODULE, e, Role.EXAMINER, 20, stake=p.examiner_stake)
        self.attempts = AttemptRegistry(p)

    def session(self, issue="prop1", kind=Kind.ORDINARY, height=50, recused=frozenset(),
                effects=None, board_size=5, vote_len=100, certify_len=20, chal_len=20, **kw):
        beacon = hx("beacon", issue).encode()
        members = tuple(draw(beacon, self.examiners, board_size))
        board = Board(f"board-{issue}", members, issue)
        el = snapshot_electorate(self.reg, height, set(recused) | set(members))
        bank, keys = build_bank(issue)
        if kind=="ELECTION" and kw.get('qualified_parties'):
            from dagp_ref.campaign import Campaign,Program,article_id,source_hash
            parties=kw['qualified_parties'];questions=list(bank.questions.values());clusters=dict(bank.article_cluster)
            for party in parties:
                for section in ('program','vision'):
                    article=article_id(party,section);clusters[article]=article
                    for j in range(self.p.campaign_questions_per_document):
                        qid=article+str(j);salt='campaign-salt-'+qid;keys[qid]=(0,salt)
                        questions.append(Question(qid,article,4,commit_key(0,salt),'Identify the '+section+' of '+party,
                            ('Committed statement','Unrelated statement','Bypass review','Unlimited budget'),
                            source_hash(('Programme ' if section=='program' else 'Vision ')+party)))
            bank=QuestionBank(issue,questions,clusters);bank.load_keys(keys)
            # Isolated session fixture; complete party/pre-election integration has dedicated tests.
            kw['campaign']=Campaign('test',issue,tuple(Program(p,'c0','Programme '+p,'Vision '+p,'fixture') for p in sorted(parties)),
                bank.record_hash(),hx('fixture-pre-election',issue),tuple(sorted(parties)),height-10,height-1,
                height+vote_len+certify_len+chal_len+self.p.challenge_resolution_grace,())
            from dagp_ref.parties import PartyRegistry
            pr=getattr(self.reg,'party_registry',None)
            if pr is None:pr=PartyRegistry('test',self.reg,self.kr)
            pr._campaigns[kw['campaign'].pre_commitment]=(kw['campaign'].digest(),issue,False)  # trusted fixture bootstrap
        w = Windows(height + vote_len, height + vote_len + certify_len,
                    height + vote_len + certify_len + chal_len)
        s = VoteSession(issue, kind, self.p, self.reg, self.kr, el.root, el.size, board, bank,
                        self.attempts, beacon, height, w, recused=frozenset(recused),
                        effects=effects, pool=self.examiners, **kw)
        s.electorate, s.keys = el, keys
        return s

    def answers(self, s, plan, ok_prop=True, ok_art=True):
        ans = []
        for q in plan.proposal_qs:
            a = s.keys[q.qid][0]
            ans.append((q.qid, a if ok_prop else (a + 1) % 4))
        for _, q in plan.sampled:
            a = s.keys[q.qid][0]
            ans.append((q.qid, a if ok_art else (a + 1) % 4))
        return tuple(ans)

    def get_token(self, s, voter, declared=("a1", "a2"), height=55, ok_prop=True, ok_art=True,
                  secret="sec", hostile=0):
        if s.campaign:declared=s.campaign.articles
        att = s.request_exam(voter, secret, height)
        plan = s.plan(att, declared)
        sub = Submission(att.ticket, declared, self.answers(s, plan, ok_prop, ok_art))
        panel = s.panel_for(att.ticket)
        verdicts = {}
        for i, m in enumerate(panel.members):
            v = grade_item_verdicts(s.bank, plan, sub)
            if i < hostile:                                   # first `hostile` panelists rubber-stamp
                v = {k: True for k in v}
            verdicts[m] = v
        tok, slashed = s.grade(att, sub, verdicts, list(panel.members), height)
        return att, tok, slashed

    def vote(self, s, voter, choice, declared=("a1", "a2"), height=55, secret="sec"):
        att, tok, _ = self.get_token(s, voter, declared, height, secret=secret)
        s.cast_ballot(voter, choice, tok, secret, att.n, s.electorate.proof(voter), height)
        return tok

    def run_to_final(self, s, close_h=None, sign=True):
        close_h = close_h or s.w.vote_end
        s.close(close_h)
        if sign:
            for m in s.board.members:
                s.certify(m, self.kr.sign(m, s.certificate_message()), close_h)
        s.advance(close_h)
        return s.finalize(s.w.challenge_end)
