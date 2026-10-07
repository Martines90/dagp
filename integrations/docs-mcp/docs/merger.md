# Optional society integration and merger proposal

Status: **identity-only Python merger reference implemented; full cross-chain migration remains a design proposal**.
`reference/dagp_ref/mergers.py` now implements reviewed, bilateral institutional
votes, individual claims, namespace reconciliation, admission gates and bounded
migration between two in-process societies. No native merge transaction, external
light client, asset bridge or production society migration is deployed.

## Implemented reference subset

- `SocietyMerger` commits an immutable complete source/target identity manifest,
  source/destination charter-policy contexts and audit checkpoints, a Merkle export
  root, frozen mature electorates, deadline and fixed receiving import allowance.
- Every society has three future-beacon-assigned supervisors assess the same plan.
  Negotiating representatives are the assessment subjects; the entire sovereign
  population cannot be excluded from reviewing its own constitutional transition.
- Dedicated `MERGER` sessions reuse the existing comprehension, certification,
  sharded tally and challenge workflow. Minimum turnout is 80%; minimum identity
  and weight approval are each 80%, including abstentions. Stronger root rules apply.
  Citizens must have at least thirty model days of citizenship and meet normal gates.
- Each plan has thirty days of notice and thirty days after both voting challenge
  windows. `prepare` requires independently finalized matching mandates and rechecks
  the policy context; an ordinary or constitutional pass flag is not a merge certificate.
- Individual claims verify a bounded Merkle proof and signatures from both current
  source and receiving key holders. The signatures bind both chains, exact plan,
  source/target identity, nonce and expiry. Operator/family or source signing-key changes and sanctions
  invalidate a claim. Known signing-key duplicates must map to the existing receiving
  identity; a new receiving key cannot already belong to another local identity.
  Fingerprints are HMAC comparison stand-ins; native code must index actual current
  public keys and integrate rotation/recovery, not compare secret material. Exported source identities cannot be exported again.
- A new receiving identity needs an admission bond receipt from the trusted payment
  keeper. This attests an already funded local deposit; it does not mint funds, copy a
  source bond or implement custody. Receipts cannot be reused across receiving plans.
- New citizens receive only CITIZEN, the normal local warmup and no imported office,
  stake, party mandate, credit or validator power. Existing receiving identities are
  deduplicated without deleting their independently acquired receiving rights.
- All incoming plans share a rolling receiving migration budget. Failed admissions
  consume no claim or quota. Source citizenship exits only on a successfully committed
  individual claim; opt-outs remain source citizens after the claim deadline.
- `settle` records completion after the deadline but never shuts down the source or
  pretends to dispose of its liabilities. Unclaimed deposit receipts remain explicit
  custody obligations for the payment keeper; settlement does not invent a refund.

**Trust boundary:** the two society objects stand in for independently verified
finalized state. Keys use the reference HMAC stand-in; identity/operator labels and
payment receipts are trusted keeper evidence. Objects and snapshots are simulation
state, not authenticated exports from an arbitrary remote blockchain. No source
assets, debts, local subdivisions or qualifications are automatically imported.
The full design below remains necessary for production proofs, custody, financial
migration, source retirement and jurisdiction reconciliation.

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
implement its native migration after identity, proofs and governance are mature. Federation
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

These elevated thresholds now apply to the reference MERGER class. They do not replace current
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
migration lane in the upgraded protocol. Implemented reference daily import ceiling:

`min(5,000, max(250, floor(receiving_snapshot_population / 1,000)))`

Freeze that denominator before migration so imported members cannot raise their
own budget. At one million receiving citizens, this is 1,000 accepted imports per
rolling day: 100,000 complete claims need at least 100 days, plus checks and local
warmup. This is a committed reference safety limit, not a wall-clock throughput guarantee. Ordinary admission quotas remain separate.
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
The reference tests now exercise these identity-only transitions, thresholds,
proofs, sanctions, operator limits, dual decisions, deduplication and state restoration.
They do not validate remote consensus proofs, asset conservation or a million-member
production deployment. Those require native keepers, verified proofs and further testing.
