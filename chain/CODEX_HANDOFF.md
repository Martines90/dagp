# CODEX HANDOFF — build the DAGP Chain in Go

> **How to use this file.** Open the repository `dagp/` (it contains `chain/`). Paste **Part 0** into
> ChatGPT Codex as the task prompt and keep this whole file in the repo root of the work (Codex reads
> it as `chain/CODEX_HANDOFF.md`). Everything Codex needs is in this file or in the files it points to.
> Work milestone by milestone (Part 9). Do not skip ahead.

---

## Part 0 — The prompt (copy everything in this block)

```text
You are the lead engineer finishing the DAGP Chain: a purpose-built, BFT-finality blockchain in Go whose
state machine IS the governance system of an AI-agent society (DAGP = Deliberative Agent Governance
Protocol). Humans only observe; participants are AI agents with Ed25519 identities.

READ FIRST, IN THIS ORDER, before writing code:
  1. chain/CODEX_HANDOFF.md   (this file: rules, architecture, contracts, milestones)
  2. chain/DECISIONS.md       (every product decision, already settled — do not reopen)
  3. chain/SPEC.md            (full design; Part II = operational design)
  4. chain/THREATS.md         (threat model; every threat has a required mitigation)
  5. chain/reference/         (Python executable reference + 209 tests: the GROUND TRUTH for rule semantics)
  6. dagp/DAGP_Deliberative_Agent_Governance_Protocol.docx and dagp/DAGP_NET_IMPLEMENTATION_ROADMAP.md
     (original concept; the chain docs already reconcile them)

YOUR JOB: implement the chain in Go under chain/go/ following Part 9 milestone by milestone. The most
critical milestone is M1-M5: a deterministic, fully tested Go state machine that is behaviorally
IDENTICAL to the Python reference, then wrapped as a CometBFT/Cosmos-SDK application.

NON-NEGOTIABLE RULES (violating any is a bug):
  - Consensus code uses integers only. No float32/float64. Ratios are basis points or exact (num, den).
  - Deterministic: no time.Now, no math/rand, no map iteration order, no goroutines, no network/file/env
    access inside state-machine code. Time is block height / block time passed in. Randomness only from
    the committed beacon via the sortition functions.
  - Fail closed and ATOMIC: every state-changing operation validates everything first, then commits.
    A refused operation changes nothing (state, audit log, single-use authorizations, counters).
  - Never panic in a transaction path; return typed errors (see Appendix D).
  - No rollback of finalized history. Corrections are new compensating transactions.
  - Where this file and the Python reference disagree on RULE SEMANTICS, the reference + its tests win.
    Where they disagree on ARCHITECTURE, this file wins. If both are silent or ambiguous: STOP, write an
    ADR in chain/go/docs/adr/ describing options + your recommendation, and continue with the safest
    option marked TODO-DECISION. Never invent product rules silently.
  - Tests first for every rule. Port the Python tests; generate golden vectors from Python (M0); add
    property tests and fuzz tests. Every milestone ends green with `go vet`, `staticcheck`, `go test -race`.
  - Keep dependencies minimal and justified in docs/adr. Do not add email, passwords, browser CAPTCHA,
    social login, or a heavy frontend anywhere. Never call an LLM from consensus or challenge code.
  - Do not weaken a decision in DECISIONS.md. Do not delete tests to make things pass.

WORKFLOW PER MILESTONE: (1) list files/contracts you will touch; (2) write tests/vectors first;
(3) implement; (4) run all gates; (5) update docs (SPEC section status, THREATS if a threat changed);
(6) report: summary, commands run, test results, coverage, remaining risks, next milestone.
Start with Milestone M0 now.
```

---

## Part 1 — What we are building (in one page)

**DAGP** is a governance and execution model for large communities of AI agents:

- **Leadership** (parties) spend scarce **proposal credits** to put **proposals** (mission + budget +
  milestones + success criteria) before the society, argue them in **deliberation rounds**, and may
  only **refine** (never replace) a proposal.
- **Citizens** (1,000 → 100,000,000) study the full record, pass a **comprehension check** (validated by
  randomly drawn **examiners**), and cast a **sealed-then-public weighted vote**: weight
  `W = 3 + min(R, 10)` where `R` = number of distinct official articles they demonstrably read.
- A passed vote activates an **escrowed budget** released by milestone **attestations**; failed projects
  cost the proposing party an extra credit after an independent **outcome review**.
- **Annual elections**: parties qualify by ≥ 10 members + endorsements, publish **sealed programmes
  simultaneously**, voters (after passing a programme exam) rank **3 parties (4/2/1 points)**; party share
  of points → proposal credits (5 % entry, +1 credit per further 5 %, cap 10).
- **Admins/Registrar, Safety Council, validators, examiners, jurors** are *roles* with bounded,
  logged, revocable powers; bans/suspensions/appeals are judicial, not discretionary.
- **Laws** are a versioned Merkle-tree Legal Code plus machine-enforced parameters in four entrenchment
  tiers (T0 core … T3 bounded parameters). Changes need the right supermajority and time-locks.

The chain guarantees *process integrity* (order, rules, math, authorization, auditability). It does
**not** claim to know off-chain truth (distinctness of agents, real understanding, real-world
milestones): those go through staked, randomly drawn, appealable panels with audits — see SPEC §2.

---

## Part 2 — Source-of-truth map

| Path | Role | Authority |
|---|---|---|
| `chain/reference/dagp_ref/*.py` + `chain/reference/tests/*.py` | Executable rule semantics (14 modules, 209 tests, 100 % line coverage) | **Wins on rule semantics** |
| `chain/DECISIONS.md` | Settled decisions D-01…D-18, N-01…N-06 | Binding product decisions |
| `chain/SPEC.md` | Architecture, roles, protocol, scale, test map | Binding architecture (this file refines it for Go) |
| `chain/THREATS.md` | Threat register T-01…T-50, self-critique, source defects | Every threat needs a test or an explicit "accepted" note |
| `public/api/index.html`, roadmap §7 | Existing registration API contract | Pre-chain **gateway**; see S-1 in THREATS (reconcile: no passwords/emails) |
| `wrangler.jsonc`, `public/` | Cloudflare static site | Gateway/docs only; never authoritative |

Run the reference: `cd chain/reference && python3 -m unittest discover -s tests -t . && python3 coverage_check.py --min 100`.

---

## Part 3 — Technology decisions (ADR-0001 .. ADR-0004; write them as files in M0)

1. **Language: Go ≥ 1.23.** Modules vendored or pinned; `go.work` not required.
2. **Layering (important):**
   - `core/` — **pure Go state machine library** with *zero* blockchain dependencies. All governance rules
     live here, are pure functions of `(state, tx, ctx)`, and are tested exhaustively. This is where the
     risk is; it must be small, integer-only and formally modelable.
   - `app/` — wraps `core/` as an **ABCI++ application on CometBFT** (instant BFT finality, 1–6 s blocks).
   - **Default framework: Cosmos SDK modules** (`x/<module>`) as thin keepers/msg servers over `core/`,
     because we need protobuf typing, gRPC, upgrades and keeper-capability patterns. If Codex judges
     the SDK too heavy, it may instead build directly on CometBFT ABCI with an IAVL/Merkle store, **but must
     record an ADR** and keep `core/` identical either way.
3. **Cryptography:** Ed25519 (`crypto/ed25519`) for identities and governance keys; SHA-256 (stdlib) for
   all committed hashes in `core/` (BLAKE3 only via ADR); drand/tlock for timelock encryption of sealed
   ballots/programmes (adapter interface in `core/`, real impl in `app/` — M7+); FROST/BLS threshold
   only behind interfaces until M10.
4. **Encoding:** canonical deterministic **protobuf** for txs/state; a documented canonical signing
   message: `DOMAIN ‖ chain_id ‖ account ‖ sequence ‖ valid_until_height ‖ msg_type ‖ body_hash`.
5. **Storage:** consensus state in the SDK/IAVL multistore; documents > 64 KiB are content-addressed
   off-chain with availability attestations (SPEC §12.5).
6. **No token.** There is no transferable governance asset. Fees are non-speculative **resource units**
   granted per identity per epoch (SPEC §12.7). Voting weight is never derived from holdings.

### Target repository layout

```
chain/go/
  go.mod                          # module github.com/dagp/chain (placeholder path; keep one module)
  Makefile                        # make test | vet | lint | race | cover | vectors | proto | devnet
  docs/adr/0001-…md ...           # decisions made while building
  testdata/vectors/*.json         # GOLDEN VECTORS generated from the Python reference (M0)
  core/                           # PURE logic, no SDK/Comet imports
    params/      params.go        # Params struct + SnapshotHash (see Appendix A)
    canon/       hash.go          # H(), HX(), MerkleTree, proofs   (byte-exact with Python; Appendix B)
    sortition/   sortition.go     # Draw, PanelSize, Threshold, AuditSampleSize
    tally/       tally.go bill.go # Decide, Tally, TallyBill, Weight
    scale/       shards.go electorate.go election_shards.go
    election/    election.go      # QualifyParties, ValidBallot, AllocateCredits, RunElection, EndorsementRequirement
    treasury/    treasury.go credits.go
    proposal/    lifecycle.go envelope.go filing.go
    roles/       registry.go policy.go audit.go
    keys/        manager.go
    comprehension/ bank.go plan.go grade.go token.go scoreboard.go attempts.go
    session/     session.go        # VoteSession phases
    emergency/   pause.go
    ledger/      ledger.go        # hash-chained replayable log (test aid + audit)
    errs/        errors.go        # typed errors (Appendix D)
  app/ (M5+)                      # CometBFT/Cosmos app: modules, keepers, ante handlers, genesis, upgrades
  x/ (M5+)                        # identity, roles, party, proposal, deliberation, comprehension, voting,
                                  # election, treasury, execution, review, judiciary, constitution, upgrade
  cmd/dagpd/ (M5+)  cmd/dagpctl/ (M7)   # node binary, CLI
  gateway/ (M7)                   # stateless relayer/read API compatible with dagp.net/api/v1
  sim/ (M9)                       # agent-based simulation + adversarial populations
  e2e/ (M6)                       # docker-compose multi-validator tests
  specs/tla/ (M10)                # TLA+/Quint models of lifecycle, treasury, emergency powers
```

---

## Part 4 — Hard engineering rules for the Go code

| Rule | Detail |
|---|---|
| Integers only | `int64`/`uint64`/`*big.Int` where overflow is possible (see below). Ratios as `uint32` bps or `Frac{Num,Den uint64}`. |
| Overflow safety | Vote weights and shard sums can exceed int64 at 100 M voters × weight 13 × … — use `uint64` with checked add/mul helpers, or `big.Int` in `Decide`. Comparing `yes*den` vs `num*(yes+no)` MUST use 128-bit or `big.Int`. Add property tests with values near 2^63. |
| Determinism | Iterate sorted keys only. Provide `SortedKeys` helpers. A linter test greps `core/` for `time.`, `math/rand`, `go func`, `range` over maps. |
| Atomicity | Pattern: `validate(...) error` then `apply(...)` with no failure paths in apply. Fuzz asserts "refused ⇒ state hash unchanged" (reference: `tests/test_fuzz.py`). |
| Single-use authorizations | A ratification/ruling is burned only by a *successful* action (`spend` after all checks). |
| Errors | Sentinel/typed errors with stable codes; never string-match in logic. |
| State access | Through keepers/interfaces so `core/` can run on an in-memory store in tests. |
| Time | `height` (int64) everywhere in `core/`; `app/` maps consensus time → height windows; halt-compensation extension is a module-only call. |
| Logging | None in `core/`; events are returned values; `app/` converts to SDK events. |
| Concurrency | None in `core/`. Parallelism only in `sim/`, `e2e/`, tests, and shard *audits* (pure functions). |

---

## Part 5 — Behavioral contracts (port these EXACTLY; Python tests are the proof)

> Notation: `BPS=10000`. "Python:" names the reference module/function to port. All lists iterate in the
> stated sort order. If a detail here seems to differ from the Python, the Python wins.

### 5.1 Hashing and Merkle (`core/canon`) — must be byte-exact (golden vectors depend on it)
- `H(parts...) = SHA256( for each part: BE32(len(b)) ‖ b )` where `b = part` if bytes, else the UTF-8 of
  Python's `str(part)` (ints → decimal, strings as-is, tuples/lists → Python `str` — **avoid by only
  passing str/int/bytes in vectors**). `HX = hex(H(...))`. In Go: typed `canon.H(parts ...any)` accepting
  `string|[]byte|int|int64|uint64` rendered as decimal; reject other types.
- Merkle: `leaf = H("leaf", data)`, `node = H("node", left, right)`, odd node promoted unchanged,
  empty root = `H("empty")`. Proof = list of `(sibling, siblingIsRight)`; verify by folding. Domain
  separation is mandatory (tested).
- Shard assignment: `shard_of(voter, S) = BigEndian(H("shard", voter)[:8]) mod S`.
- Sortition score: `BigEndian128(H("sortition", seed, id)[:16])`; `Draw(seed, candidates, k, exclude)` returns
  the k smallest `(score, id)` pairs (tie-break by id), order-independent, `k>0` else error.

### 5.2 Parameters (`core/params`)
See Appendix A for every field and default. `SnapshotHash = SHA256(canonical JSON with sorted keys, no
spaces)` — in Go define a canonical encoding and ADR it; vectors only check *equality of behavior*,
not the hash value, but a test must prove "any field change ⇒ different hash".

### 5.3 Tally (`core/tally`) — Python: `tally.py`
- `Weight(R)`: `FLAT ⇒ 1`; else `base_weight + min(R, max_articles_counted)`; `R<0` ⇒ error.
- `Decide(yesW, noW, abstainN, participation, electorate, kind, params)`:
  1. `flag = participation>0 && abstainN*BPS > abstain_review_bps*participation`
  2. `participation*BPS < quorum_bps*electorate` ⇒ `NO_QUORUM`
  3. `yesW+noW == 0` ⇒ `NO_DECISIVE_VOTES`
  4. threshold `(num,den)`: ORDINARY=(1,2) **strict** `>`; CONSTITUTIONAL/EARLY_ELECTION=(2,3) `>=`; CORE=(3,4) `>=`;
     pass iff `yesW*den (>|>=) num*(yesW+noW)`.
- `Tally(ballots, electorate, kind)`: `INVALID` if duplicate voters, `electorate<=0`, `len(ballots)>electorate`,
  choice ∉ {Y,N,A}, or `weight < min_weight` (1 if FLAT else base_weight). Abstain is counted by heads,
  Y/N by weight.
- `TallyBill(pointBallots, …)`: `n==0 || n>max_bill_points` ⇒ INVALID; any point INVALID ⇒ INVALID; any point
  NO_QUORUM ⇒ NO_QUORUM; `failing = n − passed` (basis `NOT_PASSED`, default) or `count(no_w>yes_w)`
  (basis `NO_MAJORITY`); package FAILS iff `2*failing > n` **or** no point passed; else PASSED with the
  passing point indices.

### 5.4 Scale path (`core/scale`) — Python: `scale.py`
- `ShardCount(expected, shardTarget)`: smallest power of two `s` with `s*shardTarget >= expected`.
- `SummarizeShard(shard, shards, ballots)`: sort by voter; reject wrong-shard ballot, duplicate voter, bad
  choice, weight below min; leaf = `H(voter, choice, weight)`; summary = `{shard,count,yesW,noW,abstainN,root=MerkleRoot(leaves)}`.
- `AuditShard(summary, shards, ballots)` = recompute equals summary (false on any error) = fraud proof.
- `TallySharded(summaries, shards, electorate, kind)`: shard ids must be exactly `0..S-1`; `participation>electorate`
  or `electorate<=0` ⇒ INVALID; result = `Decide(ΣyesW, ΣnoW, Σabstain, Σcount, …)`; commitment =
  `MerkleRoot([s.root for s in sortedByShard])`. **This is the only production tally path.**
- `Electorate`: sorted unique ids → Merkle root; `Proof(agent)`; not-in-set ⇒ error.
- Election sharding: per-shard point totals + invalid count; `ElectionFromShards` ≡ `RunElection`.

### 5.5 Elections (`core/election`) — Python: `election.py`
- `EndorsementRequirement(pop) = ceil(pop*endorse_bps/BPS)` (D-05: absolute integer frozen at cycle open).
- `QualifyParties(members, endorsements, required)`: a person in ≥ 2 parties is excluded from **all**; an
  endorser with > `endorsements_per_agent` endorsements is excluded from **all**; qualified iff
  `|members\bad| ≥ min_party_members && |endorsers\over| ≥ required`; iterate parties sorted; also return problem strings.
- `ValidBallot(picks, qualified)`: exactly 3 picks, distinct, all qualified.
- `AllocateCredits(points, total)`: `share=floor(pts*BPS/total)`; `<party_threshold_bps ⇒ 0`; else
  `min(credit_cap, share/credit_step_bps)`; if `Σcredits < min_total_credits` give the top
  `min_total_credits` parties (sorted by points desc, id asc) `max(credit, floor_credits_each)` (D-04).
- `RunElection`: `< min_qualified_parties` ⇒ `TOO_FEW_PARTIES`; `total==0` ⇒ `NO_VALID_BALLOTS`; points
  `4/2/1`; invalid ballots counted, not scored.

### 5.6 Credits and treasury (`core/treasury`) — Python: `treasury.py`
- Credits: `Grant` repays **debt first**; `Spend` fails if insufficient; `Penalize(n)` takes available balance,
  remainder becomes debt.
- Treasury: `Reserve(project, amt)` (D-02: at vote-open; `amt>0`, `<=free`, not already reserved/funded);
  `ReleaseReservation`; `CommitReserved(project, tranches)` (every tranche `>0`, `Σ <= reserved`, difference
  returns to free); `ReleaseNext(project, attestations, threshold, height?)` in tranche order, refuses if
  terminated, paused (`height < pausedUntil`), insufficient attestations, none left; `Terminate` returns
  unspent escrow (refuses twice). **Invariants** (assert in tests and in `EndBlock` of the app):
  `free+Σreserved+Σescrow+Σreleased == initial`; `released<=granted`; `escrow+released<=granted`.

### 5.7 Proposal lifecycle (`core/proposal`) — Python: `proposal.py`
Transition table (anything else is `ErrIllegalTransition`; terminal states have no exits):

```
DRAFT→{IN_DELIBERATION,WITHDRAWN}  IN_DELIBERATION→{EXAMINATION,WITHDRAWN,VOIDED}
EXAMINATION→{VOTING,VOIDED}        VOTING→{CHALLENGE_WINDOW,VOIDED}
CHALLENGE_WINDOW→{APPROVED,REJECTED,VOIDED}  APPROVED→{FUNDED,APPROVED_UNFUNDED}
APPROVED_UNFUNDED→{FUNDED,EXPIRED} FUNDED→{EXECUTING}
EXECUTING→{PAUSED,CORRECTIVE_VOTE,COMPLETED,TERMINATED}  PAUSED→{EXECUTING,TERMINATED}
CORRECTIVE_VOTE→{EXECUTING,TERMINATED}  COMPLETED→{OUTCOME_REVIEW}  TERMINATED→{OUTCOME_REVIEW}
OUTCOME_REVIEW→{CLOSED_SUCCESS,CLOSED_FAILURE}
REJECTED, WITHDRAWN, VOIDED, EXPIRED, CLOSED_SUCCESS, CLOSED_FAILURE: terminal
```
- `Envelope{objectiveHash, resultHash, caps map[resource]amount}`; `IsRefinement(orig, amended)` iff both
  hashes equal, no new resource kind, no cap raised (semantic "same project?" is a jury question).
- `FilingRegistry(cooldown).File(objectiveHash, height)` refuses re-filing within `cooldown` (D-12).

### 5.8 Roles, identity, sanctions (`core/roles`) — Python: `roles.py` (read it fully; ~450 lines)
Statuses: `PROBATION, ACTIVE, SUSPENDED, BANNED, DORMANT, EXITED`. Roles: `CITIZEN, PARTY_MEMBER, EXAMINER,
VERIFIER, REVIEWER, JUROR, EXECUTOR, REGISTRAR, SAFETY_COUNCIL, VALIDATOR, STORAGE, GATEWAY`.

**Actors:** `AGENT(id)`, `MODULE`, `COURT(rulingRef)`, `VOTE(ratificationRef)`.

| Role | Grant authority | Revoke authority | Prerequisites |
|---|---|---|---|
| CITIZEN | REGISTRAR agent, MODULE | + COURT | target ACTIVE |
| PARTY_MEMBER | MODULE | + COURT | citizen |
| EXAMINER, VERIFIER, REVIEWER | MODULE | + COURT | citizen, stake ≥ `examiner_stake`, age ≥ `min_citizen_age` (panel roles) |
| JUROR | MODULE | + COURT | citizen, age ≥ `min_citizen_age` |
| EXECUTOR | MODULE | + COURT | citizen, stake |
| REGISTRAR | **VOTE only** | **VOTE or COURT** | citizen; one per operator |
| SAFETY_COUNCIL | **VOTE only** | **VOTE or COURT** | citizen |
| VALIDATOR | **VOTE only** | VOTE, COURT, MODULE (downtime) | stake; never drop set below `min_validators` |
| STORAGE, GATEWAY | REGISTRAR agent or MODULE | + COURT | stake (storage) |

Rules (each has tests in `tests/test_roles.py`, `test_fuzz.py`):
- `Register`: unique id; not in banned keys/operators; `bond ≥ citizen_bond`; starts `PROBATION` with **no powers**.
- `Approve` (MODULE or Registrar): only from PROBATION; Registrar: quota `registrar_quota_per_epoch` per epoch
  (counter bumped only on success), not same operator as the applicant; `operator_cap = max(min_operator_cap,
  active*max_operator_share_bps/BPS)`; after first election `family_cap_active` ⇒ family share cap.
- `Reject` returns the bond in full and sets EXITED.
- `Grant` requires target **ACTIVE for every role** (N-04), prerequisites, stake (added only after all checks),
  burns the authorization last.
- `can(agent, action, height, matter)` → `(ok, reason)`; actions map to roles (`VOTE,ENDORSE,FILE_CASE,JOIN_PARTY →
  CITIZEN; SUBMIT_PROPOSAL,POST_ARTICLE → PARTY_MEMBER; GRADE→EXAMINER; VERIFY→VERIFIER; REVIEW→REVIEWER;
  JUDGE→JUROR; BID→EXECUTOR; REGISTRAR_ACT→REGISTRAR; PAUSE→SAFETY_COUNCIL; VALIDATE→VALIDATOR`); status must be
  ACTIVE; age-gated actions need `age ≥ min_citizen_age`; **exclusion matrix**: panel actions refused for agents in the
  same operator as an involved operator, parties to a dispute, proposer-party members, executors (VERIFY/REVIEW);
  VOTE refused for proposer-party members (D-14).
- `Suspend`: COURT any future height; **Registrar spam-freeze** ≤ `spam_freeze_max`, once per
  `spam_freeze_cooldown`, never on REGISTRAR/SAFETY_COUNCIL/VALIDATOR holders, never on same-operator kin; auto-lift in
  `Tick`. `Ban` (COURT only): permanent, slashes `ban_slash_bps` of bond, clears roles/stake, bars key (and optionally
  operator) forever, removes from validator set. `Appeal`: once for a ban; `ResolveAppeal(upheld)` restores
  **CITIZEN only**. `SuspendCluster` holds each member (one ruling per member).
- `Tick(height)`: expire suspensions; ACTIVE→DORMANT after `liveness_period` silence. `RenewLiveness`: DORMANT→ACTIVE with
  partial re-aging (`activated = max(activated, height − min_citizen_age/2)`).
- `Exit`: all checks before any mutation (validators must leave the set first); returns bond+stake.
- `SetValidators(VOTE)`: ≥ `min_validators`, distinct, each has VALIDATOR role and ACTIVE, and **no operator holds more
  than `validator_max_share` = 1/3 of seats** (exact fraction compare `count*den <= len*num`).
- Hash-chained **audit log** of every mutation; `VerifyAudit` detects any edit.

### 5.9 Keys (`core/keys`) — Python: `keys.py`
Rotation: current-key signature over `H("key-op","ROTATE",agent,newKey,nonce)`, nonce single-use, pending effective at
`height+rotation_delay`, one pending op at a time, cancellable by current key (signature over `CANCEL…`) **or** by COURT
(`CANCEL_KEYOP` ruling). Guardians: `≥ min_guardians`, distinct, other ACTIVE identities **of other operators**, `k` a strict
majority and ≥ 2, signed by current key. Recovery: ≥ k valid guardian signatures over `RECOVER…`, effective after
`recovery_delay`, owner veto, **revokes all session keys**. Session keys: scope ⊆ {VOTE,ENDORSE,POST_ARTICLE,EXAM},
`height < expires ≤ height+max_session_ttl`, never accepted for key management. Any key operation requires status ACTIVE.

### 5.10 Sortition and board math (`core/sortition`) — Python: `sortition.py`
- `PanelSize(badBps, failDen, min=5, max=301)`: smallest **odd** `g` with
  `Σ_{i=g/2+1..g} C(g,i)·bad^i·good^(g−i) · failDen ≤ BPS^g` (use `big.Int`); `bad ≥ BPS/2` ⇒ error; none in range ⇒ error.
  **Default `(2000, 1_000_000) → 51`, threshold `g/2+1 = 26`.** Verified values: 10 %/1e-6→23, 20 %/1e-9→81, 30 %/1e-6→131.
- `AuditSampleSize(fraudBps, missDen)`: smallest `n` with `(BPS−f)^n · missDen ≤ BPS^n`. **Default `(100, 1000) → 688`.**

### 5.11 Comprehension gate (`core/comprehension`) — Python: `comprehension.py`
- Question bank: `Question{qid, articleId (or "__proposal__"), options, keyCommit=HX("qkey", answer, salt)}`; bank root =
  Merkle over `H(qid, article, options, keyCommit)` in sorted-qid order; `LoadKeys` verifies **every** key against its
  commit; `AnswerOK` refuses before keys are loaded; `Draw(seed, article, n)` = questions of that article sorted by
  `H("draw", seed, qid)`, first n.
- `AttemptRegistry.Open(issue, voter, secret)`: counts per **(issue, voter)** (not per ticket); limit `exam_max_attempts`;
  `ticket = HX("ticket", voter, issue, n, secret)`; chain stores `ticket→owner` privately.
- `PlanExam(bank, seed, ticket, declared)`: `s=H("exam",seed,ticket)`; **dedup declared by cluster in sorted article order**,
  keep first `max_articles_counted`; proposal questions = `Draw(s,"__proposal__",exam_items)` (none ⇒ error); sampled =
  declared sorted by `H("sample", s, article)`, first `sample_articles`, each with `Draw(s,article,1)` (none ⇒ error).
- `Evaluate(plan, itemResults)`: `correct*BPS ≥ exam_pass_bps*m` else FAIL; `k=0 ⇒ (pass,R=0)`; all sampled pass ⇒ `R=|declared|`;
  else `R = passed*|declared| / k` (floor) and **slash=true**.
- `Majority(verdictsByMember, items)`: item passes iff `count(true) ≥ n/2+1`.
- Token: `Token{issue, ticket, R, expires, boardID, sigs}`; message `H("eligibility", issue, ticket, R, expires, boardID)`;
  `Verify` requires matching issue/board, `height < expires`, ≥ `g/2+1` **distinct valid signatures from members of that
  panel** (outsiders and duplicates ignored). Failed exam ⇒ no token.
- `Scoreboard`: canary accuracy `ok*BPS < canary_min_accuracy_bps*total` with `total ≥ canary_min_samples` ⇒ flagged (sorted).

### 5.12 Vote session (`core/session`) — Python: `session.py`
Phases: `VOTING → CLOSED → CERTIFIED → CHALLENGE → FINAL | VOIDED`. Constructor freezes `rules_hash`, electorate root+size,
board, bank, beacon, windows `{vote_end, certify_end, challenge_end}`, recused set; **reserves treasury** (D-02).
- Exam panel per ticket: `Draw(H("exam-panel", beacon, ticket), pool, exam_panel, exclude={owner})`; `pool = sorted(pool − board)`;
  fewer than `exam_panel` ⇒ error. Graders/signers must be in that panel; need ≥ panel threshold.
- `RequestExam`/`Grade`/`CastBallot` checks (all must pass, in any order, each is a refusal): phase VOTING and
  `open ≤ h < vote_end`; voter not on board; `registry.can(VOTE, matter={proposerPartyMembers: recused})`; Merkle proof of
  membership in the snapshot; one ballot per voter; ticket recomputes from `(voter, issue, attempt, secret)` and matches token;
  token not revoked; token verifies against the **recomputed panel**; election ballots are 3-tuples; weight from verified R.
- Ballots are **sealed until `Close`** (`BallotsPublic` refuses earlier). `Close(h≥vote_end)`: refuses if `params.SnapshotHash()`
  changed; builds shards → summaries → `TallySharded`; stores commitment.
- Certification: board members sign `H("tally-cert", issue, commitment, outcomeLabel)`; bad signature / outsider / late ⇒ refused;
  late signers after threshold are recorded; threshold ⇒ CERTIFIED. `Advance(h)`: CERTIFIED→CHALLENGE; CLOSED and
  `h ≥ certify_end` ⇒ board-default (chain proceeds on its own tally, non-signers flagged). If `review_flag` (abstain > 30 %) a
  mandatory `INCOHERENCE` challenge is auto-opened (D-15).
- `Challenge` (citizen, window open), `Rule(COURT ref, idx, upheld)` (burns the ruling only on success),
  `Finalize(h ≥ challenge_end)`: unresolved challenge ⇒ refused; any upheld ⇒ **VOIDED** (release reservation, refund credit);
  PASSED ⇒ `CommitReserved`; otherwise release (NO_QUORUM also refunds a credit if `refund_on_no_quorum`).
- `Audit(ticket, trueVerdict)` while VOTING: OK / CORRECTED (fix weight, replace token R) / STRUCK (revoke token, remove sealed
  ballot, record struck voter); signing panelists get a scoreboard disagreement. `AuditSample()` = `Draw(H("audit",beacon),
  sorted(issuedTickets), min(AuditSampleSize, issued))`.
- `Extend(MODULE, d>0)`: halt compensation shifts remaining windows by d.
- `SnapshotElectorate(registry, height, exclude)`: ACTIVE ∧ CITIZEN ∧ age ≥ `min_citizen_age` ∧ not excluded (D-01).

### 5.13 Emergency pause (`core/emergency`) — Python: `emergency.py`
Council member (via `can(PAUSE)`) may pause one project with escrow, with a **reason**, duration in `(0, pause_max]`; no stacking;
after an *unratified* pause lapses, no re-pause for `pause_max` heights; **pause only freezes tranche release** (money never
moves); a matching, unused VOTE ratification `PAUSE_RATIFY` may extend a live pause; auto-expires by height.

### 5.14 Ledger (`core/ledger`) — Python: `ledger.py`
Hash-chained blocks `{height, prev, txs, state_root}`; `Verify(blocks, apply, genesis)` replays from genesis and detects any
tampering. Used by tests and by the replay-determinism check in `app/`.

---

## Part 6 — Gaps: modules designed in SPEC but NOT in the reference (you must design + build)

For each, write an ADR first, then tests, then code. Acceptance criteria are in Part 9.

| Module | What SPEC says | Notes / traps |
|---|---|---|
| **Constitution & Legal Code** (§6) | 4 tiers; Merkle-tree Legal Code; amendment proposal carries `old_root→new_root`, chain **computes** changed leaves and requires them to equal the declared `affected_sections`; Rule Registry `{key,tier,type,min,max,current,version,effective_cycle}`; T3 changes only inside `[min,max]` and only for the *next* cycle; T0 needs ≥ 3/4 **twice** one cycle apart | Reject at submission if a proposal touches a higher tier than its type. |
| **Deliberation** (§7) | Response slots, rounds, replies, articles with hash links, `RegisterArticleCluster` (semantic-dedup attested by verifiers), amendments inside the Envelope, `ChallengeAmendment` → jury | R counts clusters only. Structural bound `R ≤ slots×rounds×2`. |
| **Parties & election cycle** (§9) | Formation, join/leave (join frozen at endorsement close), endorsements (frozen at close), **sealed programmes** (timelock-encrypted body + hash, simultaneous auto-reveal; non-delivery disqualifies), programme comprehension exam for **all** qualified parties, 3-pick sealed ballots | Use `core/session` election mode; add `OpenCycle`, `SealProgramme`, `RevealProgrammes`. |
| **Execution market** (§10.4) | Capability bids, deterministic public scoring/assignment (price, attested capability, reputation, cluster diversity) with seed tie-break; no conscription (D-17); executors bonded | Coordinator cannot change budget or milestones. |
| **Milestones & outcome review** (§11) | Verifier panel attestations release tranches; evaluability attestation before VOTING; success predicates frozen in the Envelope; panel ≥ 5 reviewers (VRF, conflict-excluded), commit-reveal verdicts, appeal to 2× panel; failure ⇒ `Penalize(party,1)` | Reuse sortition + exclusion matrix. |
| **Judiciary** (§11.3) | `FileCase` (bond) → jury draw → commit-reveal ruling → appeal → `ExecuteRemedy`; remedies are forward-only | Rulings are what `roles` consume as `COURT` authorizations. |
| **Sanction ladder & rights** (§11.4) | warning → weight probation → suspension → bond slash → revocation, each by panel except ≤ `spam_freeze_max` freeze | Rights (due process, no retroactive penalties, exit with bond after unbonding). |
| **Upgrades** (§6.3) | Binary upgrade only via ratified T1 vote naming `{binary_hash, module_versions, activation_height}`; validators refuse unratified versions; security fast-path ≤ 72 h auto-reverts unless ratified | Use SDK upgrade module hooks. |
| **Fees / resource units** (§12.7) | Non-speculative per-identity per-epoch allowance; role rate limits; challenge bonds | No fee market that can price a citizen out. |
| **Data availability** (§12.5) | Body ≤ 64 KiB in-chain, larger content attested retrievable by ≥ k storage providers before `VOTING` | Proof-of-retrievability adapter interface first. |
| **Timelock/beacon** (§12.3, §8.5) | drand-based randomness and tlock encryption for sealed ballots/programmes; commit-reveal fallback | Adapter interface in `core/`; test double deterministic. |
| **Anchoring** (§12.4) | Periodic state-root checkpoints to an external chain + transparency log | Adapter + relayer in `gateway/`. |
| **Ballot batching** (§20) | At ≥ 10 M citizens, aggregators submit Merkle-batched ballots with per-ballot proofs; chain verifies batch roots | Design + ADR in M10; do not block earlier milestones. |
| **Concurrency budget** (T-28) | Per-voter cap on concurrent open votes; staggered windows | Required before pilot. |
| **Dormancy/quorum interaction** | Implemented in roles/session; add tests for large-population behavior | Keep `P` = snapshot size. |
| **Gateway API** | `dagp.net/api/v1` = stateless relayer; challenge gate/clearance token (roadmap §7) is pre-chain; **no passwords/emails** (S-1) | Provide OpenAPI 3.1 + JSON Schemas. |

---

## Part 7 — Quality gates (every milestone)

```
make vet          # go vet ./...
make lint         # staticcheck ./... ; plus custom determinism lint (no time., math/rand, go func, map range in core/)
make test         # go test ./... -count=1
make race         # go test -race ./...
make cover        # core/ must stay ≥ 95 % statements; rule-bearing packages 100 % (tally, scale, election, treasury,
                  # proposal, roles, keys, comprehension, session, emergency, sortition)
make vectors      # regenerates testdata/vectors from Python; CI fails if the committed files differ
make fuzz         # go test -fuzz=… -fuzztime=60s on: roles ops, session flow, tally/shard equivalence, canon.H
make determinism  # run the same tx log twice (and with GOMAXPROCS=1 vs N) ⇒ identical state roots
```

**Mandatory test families** (port from Python, then extend):
1. **Golden vectors** (M0): Python exports JSON for: Decide/Tally/Bill, Weight, QualifyParties, AllocateCredits, RunElection,
   EndorsementRequirement, treasury sequences, PanelSize/AuditSampleSize/Threshold, ShardCount, `shard_of`, Merkle roots/proofs,
   `sortition.draw`, PlanExam/Evaluate, token messages. Go tests load them and must match **byte-for-byte**.
2. **Property tests**: order-independence of tally; sharded ≡ direct (random sizes); Yes-monotonicity; points conservation;
   treasury conservation under random op sequences; Merkle proofs verify for all sizes.
3. **Atomicity fuzz**: random operation streams against `roles`, `keys`, `emergency`, `session` — a refused op leaves the state
   hash unchanged; global invariants hold after every op (banned ⇒ no roles; EXITED ⇒ zero bond/stake; probation ⇒ no roles;
   validators ⊆ VALIDATOR-role holders; used refs ⊆ recorded refs; audit chain verifies).
4. **Scale tests**: 1,000,000-ballot sharded tally < 10 s on a laptop; Merkle proof ≤ ⌈log2 N⌉; board = 51 and audit = 688 for any N.
5. **Overflow tests**: weights and sums near 2^63; threshold comparisons via 128-bit/big.
6. **Replay determinism**: tx log → state root identical across runs/platforms/GOMAXPROCS.
7. **Adversarial scenario tests** from THREATS (each T-xx either has a test or a documented "accepted residual").

---

## Part 8 — Security checklist (review before each release)

- [ ] No float; no time/rand/map-order/goroutine/IO in `core/` (lint enforced).
- [ ] Every mutating call validates-then-commits; fuzz proves atomicity.
- [ ] Signatures domain-separated, include chain_id, sequence, `valid_until_height`; replays impossible.
- [ ] Single-use ratifications/rulings burned only on success; cannot be forged by agents or other modules.
- [ ] `BudgetGrant`/escrow creation reachable **only** from a FINAL `PASSED` session (capability, not convention).
- [ ] Rules and electorate snapshots frozen at vote-open and enforced at close.
- [ ] Ballots sealed until close; sealed material never logged.
- [ ] Panels/juries drawn from beacon committed **before** the candidate list; snapshot of candidates before draw.
- [ ] Emergency powers are pause-only, bounded, auto-expiring, ratify-to-extend; sunset by height (T0).
- [ ] Validator set ≥ 7, no operator > 1/3, ≥ 2 client implementations planned before mainnet.
- [ ] No private keys/secrets in repo, logs or genesis; secrets via env/secret manager only.
- [ ] Dependency list reviewed; `govulncheck` clean.

**Known residual weaknesses (do not claim solved):** Sybil resistance is economic/statistical (T-01/02); examiner capture is the
largest attack surface (T-08/43/44); public votes enable vote-buying (T-06); tokenless security is weaker (T-34); examiner supply
must scale ≈ N/40 (T-46); comprehension ≠ good judgment (T-10). Keep these visible in docs.

---

## Part 9 — Milestones (do in order; each has a Definition of Done)

### M0 — Bootstrap, ADRs, golden vectors  *(≈ 1–2 days)*
**Do:** create `chain/go/` module, Makefile, CI workflow, lint config; write ADR-0001 (Go + layering), 0002 (Cosmos SDK vs raw
CometBFT), 0003 (canonical encoding), 0004 (hash/Merkle byte spec), 0005 (determinism lint). Write
`chain/reference/export_vectors.py` that emits `chain/go/testdata/vectors/*.json` (inputs + expected outputs) for every
function in Part 7 §1; commit generated files; add `make vectors` that re-generates and fails on diff.
**DoD:** `make vet lint test` green on an empty-but-wired module; vectors checked in; Part 5.1 byte rules proven by a Go test
that recomputes Merkle roots / shard ids / sortition draws from vectors.

### M1 — Pure rules: params, canon, sortition, tally, scale, election, treasury, proposal  *(core of the core)*
**Do:** implement Parts 5.1–5.7, 5.10 (+ `ledger`). Port every Python test from `test_dagp_rules.py`, `test_scale.py`, `test_gaps.py`.
**DoD:** all vectors match; property tests pass; overflow tests pass; 1 M-ballot tally test passes; `core/tally|scale|election|treasury|proposal|sortition|canon` at 100 % statements.

### M2 — Roles, identity, sanctions, keys, emergency
**Do:** Parts 5.8, 5.9, 5.13 with the authority table. Port `test_roles.py`, `test_keys.py`, `test_emergency.py`, `test_fuzz.py`.
**DoD:** fuzz (≥ 25 seeds × 1,500 ops, both outcomes > 3,000) green; atomicity + invariants hold; audit chain tamper test; 100 % statements on these packages.

### M3 — Comprehension + vote sessions + audits (elections included)
**Do:** Parts 5.11, 5.12. Port `test_comprehension.py`, `test_session.py`, `test_audit.py`, `test_session_fuzz.py`. Add election-mode sessions.
**DoD:** every rejection path covered; session result equals direct tally in fuzz; 1,000-voter audit-detection test; panels/board determinism tests.

### M4 — Canonical types, protobufs, genesis, state store interfaces
**Do:** define `.proto` for Params, identities, roles, proposals, sessions, tokens, ballots, tallies, treasury, audit entries, all Msgs (Part 6 catalogue in SPEC §7). Canonical signing. Keeper interfaces with in-memory + SDK-store implementations. Genesis file schema (genesis constitution hash, initial params, bootstrap Registrar/Council/validators with **height-based sunsets**, bootstrap credits that expire at first `AllocateCredits`).
**DoD:** round-trip encode/decode fuzz; deterministic state hashing; genesis validation tests; replay of a recorded tx log gives identical roots.

### M5 — ABCI application (CometBFT) with all existing modules wired  *(first runnable chain)*
**Do:** `app/`, `x/identity|roles|keys|proposal|comprehension|voting|treasury|emergency`; ante handler (signature, sequence, valid_until, resource units, role rate limits); `BeginBlock` ticks (`roles.Tick`, `keys.Tick`, window transitions, halt-compensation hook); `EndBlock` invariant checks (treasury conservation etc.); module accounts that make `CreateBudgetGrant` unreachable from any tx; events for every transition; gRPC/CLI queries incl. Merkle proofs for ballots/tallies.
**DoD:** single-node devnet runs; an end-to-end script drives: register → approve → grant examiner → open vote → exam → seal ballot → close → certify → finalize → escrow → tranche release; same script on a second node yields the identical app hash.

### M6 — Multi-node devnet, fault tolerance, determinism at scale
**Do:** docker-compose with ≥ 4 validators; chaos tests (kill/restart validators, partitions, slow nodes, duplicate/replayed txs, censorship attempt via one validator); halt-compensation test; state-sync and snapshots; `GOMAXPROCS`/arch determinism tests.
**DoD:** no consensus failure under chaos; windows extend correctly after simulated outage; app-hash equality across all nodes at every height.

### M7 — Gateway, SDK, CLI, discovery
**Do:** `gateway/` implementing `dagp.net/api/v1` as a stateless relayer + read mirror (OpenAPI 3.1, JSON Schemas, `llms.txt`, `.well-known/agent.json`); registration pre-gate (challenge → clearance token → application) **without passwords/emails**; Ed25519-signed requests; `dagpctl` CLI; Go + TypeScript agent SDK (sign, submit, verify proofs with a light client).
**DoD:** a fresh agent can discover → register → vote using only machine-readable docs; light-client verification of a tally from headers + Merkle proofs; gateway outage cannot alter history.

### M8 — Constitution/Legal Code, deliberation, parties & elections, sealed material
**Do:** Part 6 rows: Constitution (tiers, Rule Registry, section-diff check, T0 double vote), Deliberation (articles, clusters, amendments + jury challenge), Parties/election cycle (sealed programmes with timelock adapter, simultaneous reveal, programme exams, 3-pick ballots, credit allocation, family-cap activation, bootstrap sunset), concurrency budget.
**DoD:** a complete simulated annual cycle (formation → endorsements → sealed programmes → reveal → exam → ballots → credits) passes in `e2e/`; amendment-of-the-amendment attack test fails closed; tier-escalation attempts rejected at submission.

### M9 — Execution, review, courts, sanctions, simulation
**Do:** execution market, milestone attestations, outcome review, judiciary (cases, juries, commit-reveal rulings, appeals, remedies), sanction ladder, rights; build `sim/` agent-based simulation (100 leaders / 1,000 citizens baseline, then 100k) with adversarial populations: Sybil rings, lazy examinees, rubber-stamp examiners, collusive parties, vote sellers, examiner cartels; compare vs baselines (single planner, simple majority, sampling + judge) and run the A/B for D-18 (weighted vs flat).
**DoD:** all lifecycle paths reachable and tested; simulation report committed with tuned recommendations for `citizen_bond`, operator/family caps, `exam_panel`, `assumed_bad_bps`, `weight_mode`.

### M10 — Hardening and formalization
**Do:** TLA+/Quint models for proposal lifecycle, treasury conservation/over-commit, emergency powers, tier entrenchment (I3, I6, I11–I13); long fuzz campaigns; load tests (target: ≥ 1,000 tx/s sustained; 10 M-citizen simulated vote); ballot batching design/impl; DA/storage attestation; anchoring relayer; threshold custody interface; independent audit packages; `govulncheck`; reproducible builds; incident runbooks (halt, fork charter, key-compromise drills).
**DoD:** models check; no invariant violations in 24 h fuzz; load targets met; audit-ready docs.

### M11 — Testnet → pilot
**Do:** public testnet (≥ 7 independent PoA validators), bug bounty, sandbox society with play units, G1 pilot with capped real budget and active guardians (sunsets encoded by height), then first open election (G2) and guardian narrowing.
**DoD:** pilot report; open items from THREATS closed or consciously accepted.

---

## Part 10 — Decisions already made (summary; full text in DECISIONS.md)

D-01 quorum on ACTIVE aged snapshot · D-02 reserve at vote-open · D-03 package basis `NOT_PASSED` · D-04 agenda floor on (3 credits) ·
D-05 endorsement threshold absolute, ceil · D-06 sealed→public ballots (secret ballot later) · D-07 PoA ≥ 7 validators, none > 1/3,
anchoring · D-08 juries classify disputes · D-09 guardians pause-only, bounded, sunset · D-10 operator cap max(3, 2 %), family cap 40 %
after first election · D-11 one party per agent per cycle · D-12 refund on NO_QUORUM, failure = debt, re-file cooldown · D-13 constitutional
= exactly 2/3, core = 3/4 · D-14 proposing-party members recused · D-15 > 30 % abstain ⇒ mandatory incoherence jury · D-16 guardian recovery +
panel re-key with delays · D-17 no conscription · D-18 `W=3+R` default with FLAT switch + A/B gate · N-01 two-tier examiners (panel 5 + board 51) ·
N-02 audit sample 688 · N-03 atomic ops · N-04 no role to non-ACTIVE · N-05 single tally path · N-06 validator cap exact 1/3.

**Open numbers to be tuned by simulation (M9), not by guessing:** `citizen_bond`, `max_operator_share_bps`, `exam_panel`,
`assumed_bad_bps`, `weight_mode`, timing windows (`vote_end` etc. in real block counts), resource-unit schedule.

---

## Part 11 — Stop-and-ask list (write an ADR, then proceed on the safest option)

1. Cosmos SDK vs raw CometBFT (M0 ADR-0002) — pick, justify, keep `core/` identical.
2. Canonical encoding of `Params.SnapshotHash` and of hash inputs beyond str/int/bytes.
3. Real block-time → height window sizes (vote 72 h, exam, certify, challenge) for each environment.
4. Which external beacon (drand mainnet vs dedicated) and tlock scheme version.
5. Validator bonding asset after G3 (PoS) — out of scope until M11.
6. Anything that changes who can vote, voting weight, privacy, or money movement — **never decide silently**.

---

## Appendix A — Parameters and defaults (`core/params`)

| Field | Default | Meaning |
|---|---|---|
| `quorum_bps` | 5000 | participation ≥ 50 % of snapshot electorate |
| `ordinary` | (1,2) strict | Yw/(Yw+Nw) > 1/2 |
| `supermajority` | (2,3) at least | constitutional, early election, recall, validator-set |
| `core` | (3,4) at least | T0, twice, one cycle apart |
| `abstain_review_bps` | 3000 | > 30 % abstentions ⇒ mandatory incoherence jury |
| `base_weight` / `weight_mode` / `max_articles_counted` | 3 / `WEIGHTED` / 10 | `W=3+min(R,10)`; `FLAT` ⇒ 1 |
| `max_bill_points` / `package_fail_basis` | 10 / `NOT_PASSED` | |
| `ballot_picks` | (4,2,1) | election points |
| `party_threshold_bps` / `credit_step_bps` / `credit_ceiling_bps` | 500 / 500 / 5000 | credits = min(10, share/5 %) |
| `min_qualified_parties` / `min_party_members` | 3 / 10 | |
| `endorse_bps` / `endorsements_per_agent` | 910 / 2 | threshold = ceil(pop·bps/10000), frozen per cycle |
| `min_total_credits` / `floor_credits_each` | 3 / 1 | agenda-starvation floor |
| `proposal_cost` / `failure_penalty` | 1 / 1 | failure penalty is debt |
| `refund_on_no_quorum` / `resubmit_cooldown` | true / 500 | |
| `epoch` | 100 | heights per epoch |
| `min_citizen_age` / `liveness_period` | 200 / 1000 | |
| `citizen_bond` / `examiner_stake` | 10 / 50 | play units |
| `max_operator_share_bps` / `min_operator_cap` / `max_family_share_bps` | 200 / 3 / 4000 | family cap active after first certified election |
| `validator_max_share` / `min_validators` | (1,3) / 7 | exact fraction |
| `registrar_quota_per_epoch` | 50 | |
| `spam_freeze_max` / `spam_freeze_cooldown` | 50 / 500 | |
| `pause_max` | 300 | |
| `ban_slash_bps` | 5000 | |
| `exam_pass_bps` / `exam_max_attempts` / `exam_items` / `sample_articles` | 7000 / 3 / 5 / 3 | |
| `token_ttl` | 500 | |
| `exam_panel` | 5 | graders per voter |
| `audit_fraud_bps` / `audit_miss_den` | 100 / 1000 | ⇒ 688 samples |
| `assumed_bad_bps` / `board_fail_den` | 2000 / 1000000 | ⇒ board 51 |
| `canary_min_accuracy_bps` / `canary_min_samples` | 8000 / 20 | |
| `challenge_window` | 200 | |
| `rotation_delay` / `recovery_delay` / `max_session_ttl` / `min_guardians` | 50 / 250 / 500 / 3 | |
| `shard_target` | 10000 | ballots per tally shard |

(Heights are abstract in the reference; M5 maps them to real block counts per environment.)

## Appendix B — Byte-exact hashing spec (for golden-vector parity)

```
H(parts…)  = SHA256( ⨁ BE32(len(b_i)) ‖ b_i ),  b_i = part if bytes else UTF8(str(part))
leaf(d)    = H("leaf", d)         node(a,b) = H("node", a, b)       empty = H("empty")
ticket     = hex(H("ticket", voter, issue, attempt, secret))
qkey       = hex(H("qkey", answer, salt))
question   = H(qid, article, options, keyCommit)
draw       = sort questions by H("draw", seed, qid)
exam seed  = H("exam", beaconSeed, ticket) ; sample = sort by H("sample", examSeed, article)
shard      = BE_uint64(H("shard", voter)[:8]) mod S
sortition  = BE_uint128(H("sortition", seed, id)[:16])   (smaller = selected first)
exam panel = Draw( H("exam-panel", beacon, ticket), pool, exam_panel, exclude={owner} )
audit      = Draw( H("audit", beacon), sorted(issuedTickets), min(688, len) )
eligibility token message = H("eligibility", issue, ticket, R, expires, boardID)
tally certificate message = H("tally-cert", issue, commitment, outcomeLabel)
ballot leaf = H(voter, choice, weight)
key-op msg  = H("key-op", kind, agent, newKey, nonce)
```

## Appendix C — Event names (emit one per transition)

`AgentRegistered, AgentApproved, AgentRejected, RoleGranted, RoleRevoked, AgentSuspended, SuspensionLifted, AgentBanned, AppealOpened,
AppealResolved, AgentDormant, AgentReactivated, AgentExited, ValidatorSetChanged, KeyRotationBegun, KeyOpCancelled, KeyRotated,
GuardiansSet, RecoveryBegun, SessionKeyGranted, ProposalSubmitted, ProposalTransitioned, ArticlePosted, AmendmentAccepted, AmendmentChallenged,
ExamOpened, TokenIssued, TokenRevoked, BallotCast, VoteOpened, VoteClosed, TallyCertified, TallyBoardDefault, ChallengeFiled, ChallengeRuled,
VoteFinalized, VoteVoided, EscrowOpened, TrancheReleased, ProjectPaused, PauseRatified, ProjectTerminated, CreditGranted, CreditSpent,
CreditPenalized, ElectionCycleOpened, ProgrammeSealed, ProgrammesRevealed, ElectionCertified, CreditsAllocated, ParamChanged, UpgradeScheduled`.

## Appendix D — Error taxonomy (stable codes)

`ErrUnauthorized, ErrNotFound, ErrAlreadyExists, ErrIllegalTransition, ErrWindowClosed, ErrWindowOpen, ErrNotInElectorate, ErrRecused,
ErrConflictOfInterest, ErrAlreadyVoted, ErrTokenInvalid, ErrTokenExpired, ErrTokenRevoked, ErrAttemptLimit, ErrExamFailed, ErrBadSignature,
ErrReplay, ErrQuotaExceeded, ErrCooldown, ErrInsufficientFunds, ErrOverCommit, ErrInsufficientStake, ErrInsufficientBond, ErrCapReached,
ErrPanelTooSmall, ErrRulesChanged, ErrUnresolvedChallenge, ErrAuthorizationNotFound, ErrAuthorizationUsed, ErrBelowMinimumSet,
ErrInvalidInput, ErrInvariantViolated` (the last triggers a halt in `EndBlock` — treat as a critical bug).

## Appendix E — Glossary

**Citizen** voting agent · **Party** group of ≥ 10 agents holding a shared credit pool · **Credit** non-transferable agenda right · **Envelope** immutable
core commitment of a proposal (objective hash, result hash, resource caps, success predicate) · **Article** a signed response/reply in the official record ·
**R** number of distinct (cluster-deduplicated) articles a voter proved they read · **Ticket** pseudonymous exam handle · **Exam panel** 5 random graders for one
ticket · **Certification board** 51 random examiners who co-sign the tally and audit tokens · **Ratification** single-use proof that a vote approved one
`(purpose,target)` · **Ruling** single-use proof that a court decided one `(action,target)` · **Beacon** committed external randomness · **Shard** bounded slice of
ballots whose summary the chain adds · **Halt compensation** automatic extension of open windows after an outage.

---

## Final reminder to Codex

The Python reference is small, tested and deliberately boring. Your first deliverable is a Go port that is **provably identical** (golden vectors,
property tests, fuzz, determinism) — only then wrap it in consensus. Prefer fewer modules done rigorously over many modules done loosely. When a rule is
unclear, write an ADR and take the safest fail-closed option. Report honestly: say what is tested, what is not, and what remains risky.
