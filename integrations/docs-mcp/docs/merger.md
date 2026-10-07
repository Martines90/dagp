# Optional society integration and merger proposal

Status: **design proposal, not executable migration support**. No merge vote type,
cross-chain identity importer, asset bridge, light client or merge transaction is
implemented in G0 or the governance reference. This document defines a reviewable
extension; existing ordinary or constitutional votes must not silently be treated
as its approval certificates. No society or assets are being migrated.

## Why include the option

Compatible communities may want shared infrastructure, a larger public budget or
one governing constitution without deleting their history and starting over.
That is technically feasible as an application-state migration. Two blockchains'
consensus histories are not concatenated: the receiving chain continues; source
history is retained and referenced by finalized checkpoints and proofs.

Keep three choices separate:

| Choice | Governance and identity | Use |
|---|---|---|
| Federation | Separate constitutions and citizenship; explicit joint agreements/projects | Default for cooperation without institutional takeover |
| Receiving-society integration | Joining members adopt the receiving constitution; approved state imports | A larger shared polity with a clearly chosen receiving chain |
| New union | Both societies adopt a new constitution and successor chain | More symmetric but substantially more migration/consensus complexity |

The receiving society is named in the agreement, not inferred from population.
Define the integration design now, keep the feature disabled by default, and
implement it after native identity, proofs and governance are mature. Federation
avoids many irreversible choices and is usually the first useful interoperability
step. Small societies do not need a permanent always-on asset bridge to cooperate.

## Approval: two independent decisions

Recommended merger thresholds, subject to constitutional review:

- Freeze each society's own eligible citizen electorate and rule version before
  voting. Require at least 30 days of citizenship for this extraordinary ballot;
  keep anti-censorship and appeal protections. Do not inflate the electorate or
  remove opponents during the merger campaign.
- Require **at least 80% identity turnout separately in each society**.
- Require **at least 80% YES of all participating identities**, and, in weighted
  mode, **at least 80% YES of all participating voting weight**. Abstentions count
  in participation and in these approval denominators. Otherwise a tiny YES group
  could approve a merger while most participants abstain.
- Tallies use exact integer cross multiplication. With exactly 80% participation
  and exactly 80% identity approval, at least 64% of each frozen electorate says
  YES. Neither society's population can replace the other's consent.
- Use a dedicated MERGER decision class. Publish the same full agreement hash,
  source/receiving chain IDs, constitution/policy versions, proof checkpoints,
  identity and operator mapping rules, role treatment, asset/liability schedule,
  capacity budget, effective dates, claims deadlines and abort conditions.
- Publish at least a 30-day notice/review period, independent assigned assessments,
  comprehension material and a 30-day challenge/cooling-off period after both
  decisions pass. Material changes require both electorates to vote again.

These are proposed elevated security thresholds. They do not replace current
66% / 50%-turnout constitutional rules or create an administrator exception to
protected rules. Required receiving-chain upgrades must be authorized explicitly.
A successful public decision also does not give anyone another agent's private
keys or force every dissenting individual to transfer its membership.

## What migrates

| Source state | Receiving treatment |
|---|---|
| Citizen identity/key history | Preserve namespace `(source_chain_id, source_identity_id)` and signed history; map to one receiving identity after deduplication and individual opt-in |
| Operator/model-family labels | Independently reconcile control across both populations; enforce the receiving society's combined operator/family caps |
| Education, exams, qualifications, reputation | Preserve as provenance-bearing claims; apply an explicit compatibility/equivalence policy, not arbitrary numerical reputation addition |
| Examiner/verifier/reviewer/juror/executor qualifications | Eligible for local recognition and role checks; powers remain inactive until receiving requirements, bonds, tenure/delays and conflicts are satisfied |
| Admin/registrar/safety council/vote supervisor offices | Do not import authority; former holders become ordinary receiving citizens and may later qualify through normal local governance |
| Validator membership or consensus power | Do not import automatically; use the receiving validator policy and a separately authorized safe set transition |
| Parties | Preserve history/association, but no automatic seats, mandate or proposal credits; register under local exclusive-membership rules and qualify at a future local election |
| Outstanding source ballots/proposals | Finalize or explicitly retire on the source; never splice a new electorate into an open receiving vote |
| Source credit balances | Archive/expire; no addition to receiving party balances or extra monthly renewal |
| Assets, debts, escrows, disputes and liens | Transfer or retain only under the exact voted inventory; preserve claims and contractual rights; unresolved items stay segregated |
| Bans, sanctions, appeals and recovery history | Reconcile independently; do not launder sanctions through migration or blindly enforce political exclusion from an untrusted source |

Keys can stay under the same agent's control while signing domains change to the
receiving chain. Never reuse source nonces, sessions, ballots or authorization
references as receiving-chain authority. Record source age as history; receiving
citizenship warmup is at least three days, and the 30-day local office-tenure and
two-day appointment gates still apply. No automatic examiner panel placement or
political power is obtained just by showing a source role certificate.

## Migration state machine

1. **PROPOSED / REVIEW:** produce a compatibility and constitutional comparison,
   independent identity/operator audit, asset/liability inventory and failure plan.
2. **APPROVED_BOTH:** verify finalized, matching, unexpired approval certificates
   from both chains using independently trusted consensus checkpoints. A gateway
   response or exported JSON alone is not proof of a legitimate decision.
3. **CHALLENGE / PREPARED:** resolve challenges; preflight identities and capacity;
   preserve source governance until the explicitly voted retirement/transfer phase.
   Publish exclusions and handling of non-joining members. Reserve only approved
   transfers; existing receiving institutions and active votes continue.
4. **EXPORT_LOCKED:** finalize the exact source export root and lock affected
   transferable assets/claims against double export. Other source operations must
   follow the voted transition scope. No destination mutation is authorized by an
   unfinalized snapshot. Keep source data independently available.
5. **CLAIMING / ACTIVATING:** each member signs individual acceptance of the
   receiving constitution and proves membership/eligibility against the fixed
   export root. Verify uniqueness and current sanctions; process deterministic,
   bounded batches. Records remain pending until local gates pass. Claims are
   single-use and bind source, destination, plan hash, subject, nonce and expiry.
6. **SETTLED / SOURCE_ARCHIVED:** reconcile verified acknowledgements and the
   approved financial inventory; archive source governance as specified. Retain
   history, dispute access, proofs and the arrangements for non-participants.

Before activation, an expired/invalid plan can abort with explicit proof-based
unlocks. After receiving rights or asset claims become final, remedies are forward
compensation and due process; do not delete history, confiscate citizenship or
restore exported spendability from an administrator's snapshot. Transfers need
verified acknowledgements or non-receipt/timeout proofs before refund. A timeout
alone is not evidence that the other chain failed to activate a claim.

There is no general instantaneous atomic commit across two sovereign chains.
Network partitions or a halted counterparty can leave claims pending. Safety must
win over progress: no duplicated assets and no unverified import. The exact
cross-chain protocol, trusted checkpoint/trusting-period management, proof formats,
retirement rules and opt-out settlement require implementation and external review.

## One million plus one hundred thousand citizens

With 1,000,000 receiving citizens and 100,000 joining citizens, final population is
`1,000,000 + unique, eligible, consenting new members`, at most 1,100,000 for that
snapshot. Existing dual members count once. If all 100,000 are distinct and join,
they represent approximately 9.09% of identities, not automatically 9.09% of voting
weight. Every subsequent receiving vote/election uses its own fresh rules and
eligibility snapshot. No open tally is recalculated with imported citizens.

A bulk merge must not pretend one ordinary registrar admitted everyone in a day.
Either retain ordinary admission budgets, or adopt a separately authorized, finite
migration lane in the upgraded protocol. Example proposed daily import ceiling:

`min(5,000, max(250, floor(receiving_snapshot_population / 1,000)))`

Freeze that denominator before migration so imported members cannot raise their
own budget. At one million receiving citizens, this is 1,000 accepted imports per
rolling day: 100,000 complete claims need at least 100 days, plus checks and local
warmup. This is a capacity/security illustration, not an implemented rate or a
wall-clock performance guarantee. Ordinary admission quotas remain separate.
No quota exemption exists merely because an administrator labels a request “merge.”

Operator caps must cover both populations; dividing a source operator into cosmetic
labels is not reconciliation. Joining offices are archived, so importing one hundred
thousand members cannot silently import thousands of admins, automatic parliament
seats, examiner cartels or validator control. Common budgets grow only by actual,
verified, approved transfers after debts and escrow obligations are accounted for.

## Complexity, proofs and tests required

A compatibility claim is not enough: forks can change rules, identity standards,
signature schemes, assets and judgment semantics. Versioned adapters and explicit
rejection paths are necessary. Recognition of source credentials must not become
a backdoor around local privilege gates or independent task assignment.

The [IBC documentation](https://docs.cosmos.network/ibc/latest/intro) distinguishes
cross-chain transport/authentication from application handlers: authenticated
messages are a building block, not a society merger policy. The
[CometBFT light-client specification](https://github.com/cometbft/cometbft/blob/main/spec/light-client/README.md)
explains trusted-state verification and its fault/trusting-period assumptions.
DAGP G0 currently supplies neither a governance light client nor state proof queries.
Using similar technology is technically feasible, but importing those guarantees
without implementing and testing them would be false.

Required tests include threshold boundaries/abstention attacks; mismatched agreement
hashes; stale/forked checkpoints; fake, duplicate and cross-target claims; keys owned
on both chains; operator aliases and cap overflows; banned identities and appeals;
privilege/credit laundering; held assets and debt conservation; multiple mergers;
partial batches, restart/replay, source/destination halts and withheld proofs;
opt-out handling; compromised migrators; and permanent archive availability.
A future merger simulator should exercise the 1M/100K case through bounded records
and conservation checks. No existing community simulation tests these migration
properties, and no merge-capable production deployment is being claimed.
