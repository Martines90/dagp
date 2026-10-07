# Reviewed proposals and common-budget allocation

A proposal has one immutable goal/result commitment and a versioned implementation
record. Other parties can publish signed comments and reply to existing comments;
the owner can answer and submit refinements during the review window. Comments
commit to the version and record they discuss. Full signatures and thread links are
retained, as are old versions and amendment evidence.

## Roles and approval

`VOTE_SUPERVISOR` is granted by public ratification, requires citizenship and minimum
age, and is disabled by administrative containment. The supervisor pool is fixed
when review begins. Members must belong to distinct operators, and proposing-party
operators cannot supervise their own proposal. Default approval requires **two
independent supervisors**. An ordinary admin account cannot substitute for this role. Registrars cannot
freeze supervisors to obstruct a review; judicial authority is required.

Code rejects a different goal/result, an added resource, higher caps, higher budget,
malformed milestones or a budget above the explicit `treasury` cap. Goal and result
text must match their hash commitments. Every amended version discards prior
approvals; supervisor signatures bind the complete record, version, chain, issue,
rules and assessment note. Before locking, current authority and operator independence
are rechecked. Body changes can still change the real meaning of a proposal: the
supervisor must assess that meaning and decline to sign inappropriate changes.
This is accountable semantic review, not an automated proof of equivalence.

The owner signs the final lock. The full review window must end, and at least five
blocks must have passed since the last amendment. Comments/edits close when the
record locks. Opening a vote from the locked record is single-use and computes the
eligible electorate with proposing-party and board recusals. Caller-supplied budgets,
credit ledgers and electorate overrides are refused. A changed rule snapshot also
requires a new review rather than silently changing the approval standard.

A different goal/result or larger budget requires a new proposal, new filing credit,
discussion, examination and vote. Once voting begins, no mid-vote amendment can
change the document or financial effects. Tally certificates bind the reviewed
record and effects; changing reviewed tranche amounts makes execution fail closed.
Existing challenge/court finalization remains available after the ballot closes.
Native governance must verify court and role ratification evidence, rather than
accepting the reference harness's trusted `MODULE`, `VOTE` or `COURT` objects.

## Budget and milestones

Each milestone has a unique label, positive amount and explicit acceptance condition.
Amounts sum exactly to the requested budget. A zero-budget law/policy uses no tranches.
The factory uses the approved amount and milestones directly; it does not trust a
separate caller-supplied effect. With a credit ledger configured, filing spends the
party's proposal credit once. No-quorum finalization refunds that same charge once.
A failure to obtain review approval is not a passed or refunded vote.

At vote-open the treasury **reserves** the amount, preventing concurrent votes from
promising the same money. At successful finalization, after the challenge phase,
the reservation becomes project escrow; reviewed milestone acceptance records are
stored beside the tranches. This allocates from the common budget but is not an
immediate unrestricted payout. Failed, voided and no-quorum votes unwind reservations
according to the existing credit/refund rules. Insufficient common funds fail before
opening/reserving; the proposal's filing credit is a separate cost.

Actual tranche release must verify milestone evidence and independent approvals,
respect pauses and prevent duplicate release. `payments.py` defines the authenticated
reference payment protocol. Legacy simulation `Treasury.release_next` accepts trusted
numeric attestations; it must not be exposed as a native transaction endpoint. Merely
storing an acceptance description or hash does not prove delivery. A production port
must connect escrow conditions to authenticated verifier approvals and dispute windows.

## Bounded discussion

The reference limits text length, 32 milestones, 20 versions, 200 comments, 20 comments
per agent, and each party's share of comment slots. These bounds prevent one author
from consuming the entire discussion and keep replay bounded. Production storage and
fee policy must preserve evidence availability without turning bounds into censorship.
Party membership and supervisor eligibility come from authenticated frozen snapshots
in native code; client-supplied membership labels are not authority.

## Validation and integration

`tests/test_review.py` exercises discussions, owner replies, supervisor quorum,
invalidated signatures, colluding operators, material changes, thread spam, notice
periods, locked effects, zero-budget law votes, exact milestone funding, credit
refunds, exhausted treasury and duplicate opening/payment. The community simulation
now uses this controller for all nine proposal stories, rather than treating review
as a scripted eligibility check. The debate and semantic judgments remain synthetic.

Current community exports use v4 rules under `simulation/results/review-budget/`.
Historical v3 replay requires commit `7140ed9`; earlier artifacts remain unchanged.
These changes enforce reference behavior; G0 still anchors signed result commitments
rather than executing governance transitions.

Validation: **306 governance tests**, including **23 review/budget regressions**, and
**six simulator tests** pass. The paired 1,100-identity community runs complete
**242 checks** and **20,490 events**. Exports retain the original and approved record,
supervisor signatures, signed comments, amendments and milestone conditions.
