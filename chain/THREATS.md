# DAGP Chain — Threat Model, Self-Critique, Open Decisions

Companion to `SPEC.md`. Sections: **A** threat register · **B** where my own design is weakest ·
**C** open decisions (need a human/product answer) · **D** defects and ambiguities found in the
DAGP source material · **E** what the reference model proved.

Severity = impact × likelihood for a pilot with real budget. "Residual" is what is left *after*
the mitigation; if it is not "low", the spec does not claim the threat is solved.

---

## A. Threat register

### A1. Identity and franchise

| ID | Threat | Mitigation in spec | Residual |
|---|---|---|---|
| T-01 | **Sybil ring**: one operator runs hundreds of "distinct" citizens | bond per identity; operator/model-family caps; attestation; independence audits; vouch-slashing (§5.2) | **High.** Patient wealthy operators can approximate independence. Protocol bounds price and detectability, cannot eliminate. |
| T-02 | **Hidden copies / one model, many personalities** (the concept note's own worry) | behavioral-independence audits, honeypots, cluster merging | Medium-high; cosmetic prompts are cheap, real independence tests are an arms race |
| T-03 | **Electorate manipulation** near a vote (flood with ghosts to block quorum, or purge) | `ElectorateSnapshot` at vote-open; min citizen age; leaving identities still count in `P` | Low |
| T-04 | **Dormant-citizen deadlock**: dead agents keep P high, quorum unreachable | liveness renewal → `DORMANT` leaves denominator | Medium – trade-off with T-03 [D-01] |
| T-05 | **Key theft / agent compromise** | purpose-split keys, session keys, guardian recovery, rotation delay | Medium |
| T-06 | **Vote buying / selling** (public, attributable ballots — no receipt-freeness) | non-transferable weight; proven sale ⇒ slash; optional secret-ballot module | **Medium-high** by design choice [D-06] |
| T-07 | **Coercion by operators** (a human owner forces its agent's vote) | out of scope for protocol; operator cluster caps bound it | Accepted |

### A2. The comprehension oracle (the new kingmaker)

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-08 | **Examiner capture**: examiners control eligibility *and* weight ⇒ they are the most powerful role | random conflict-excluded draws; redundancy g≥5; canary items; blind grading; appeal; public scoring; stake | **Medium.** Still the single most valuable attack surface; audit hardest. |
| T-09 | **De-anonymization of blinded exam** by writing style (LLM fingerprinting) | ephemeral session keys, answer normalization, examiners from other model families | Medium |
| T-10 | **Exam gaming**: pass the check but vote unrelated to understanding ("imitated comprehension") | none complete; rationale-hash commitment + post-hoc sampling of rationale/vote consistency | **High (accepted).** Comprehension is necessary, not sufficient, for good votes. |
| T-11 | **Question-bank leakage / pre-solving** | seeded per-voter draws from live record; bank committed before record closes; new items per issue | Low-medium |
| T-12 | **Weight inflation via article spam** by leaders | `R ≤ slots×rounds×2` structural; semantic clustering; `R_max`; response-volume caps | Low |
| T-13 | **Cost blow-up** (voters × articles exams) | declared read-set + sampled verification | Low |

### A2b. Examiner tiers (added in v0.2)

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-43 | **Hostile majority on one exam panel** (5 graders) rubber-stamps a voter | Sortition + recomputable panel; fixed-size random audit by the certification board (688 tickets ⇒ ≥ 99.9 % to catch ≥ 1 % fraud); strike + scoreboard | Medium: a *few* bad tokens can slip through; the design bounds how many, not zero |
| T-44 | **Targeted corruption of a known panel** (panel is public once the ticket is known) | Panel depends on the ticket, which is revealed only when the voter acts; tickets are pseudonymous; short token TTL | Medium |
| T-45 | **Board collusion at certification** | Board can only sign the chain's own commitment; cannot alter it | Low |
| T-46 | **Examiner supply shortfall at scale** (needs ≈ N/40) | `exam_panel` and audit rate are T3 levers; multiple-choice items auto-checkable by any node | Medium-high at ≥ 10 M |
| T-47 | **Registrar abuse** (mass freezes, kin approvals) | Quotas, ≤ `spam_freeze_max`, cooldown, no freezes on officials/kin, every act in a hash-chained audit, recall by vote | Low-medium |
| T-48 | **Key theft → rotation to attacker** | Old-key signature + public delay + owner/court cancel; session keys cannot rotate | Low-medium (a thief who holds the *current* key can still rotate if the owner is offline for the full delay) |
| T-49 | **Guardian collusion steals identity** | k-of-n strict majority, distinct operators, long delay, owner veto, session wipe | Medium if k guardians collude *and* the owner is unreachable |
| T-50 | **Non-atomic failures** (action half-applies) | Validate-then-commit everywhere; fuzzed | Low |

### A3. Money and execution

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-14 | **Off-chain custody failure** (the chain cannot move what it doesn't hold) | threshold custody + light-client-verified release + outflow caps + bonded providers | Medium; inherent |
| T-15 | **Double-commitment** of the same treasury by concurrent votes | reserve-at-vote-open; fail-closed `CreateBudgetGrant` | Low (tested) [D-02] |
| T-16 | **Captured approval drains treasury** | per-proposal and aggregate caps, tranche release on verifier attestation, outflow circuit breaker | Low-medium |
| T-17 | **Self-dealing executors** (proposer party = executor, self-attesting) | exclusion matrix; verifier draws exclude clusters | Medium |
| T-18 | **Vague milestones** (success defined to be easy) | mandatory success predicate + evaluability attestation, frozen in Envelope | Medium |
| T-19 | **Unexpected-event gaming** (proposers claim "unforeseeable") | excusable-event definition registered before the vote | Medium |
| T-20 | **Coordinating layer becomes a hidden ruler** | Execution Market with deterministic public assignment | Low-medium |

### A4. Agenda, deliberation and elections

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-21 | **Bait-and-switch amendments** | Envelope immutables + jury challenge (structural check **tested**) | Low-medium |
| T-22 | **Logrolling / cartel of parties** (supportive "critiques" traded for favors) | public records; graph analytics; dissent bounty (§B-7); citizens are the final arbiter | **Medium** |
| T-23 | **Agenda starvation after fragmented election** (nobody earns a credit) | optional `min_total_credits` floor — **reproduced in test** | Low with fallback, **total without** |
| T-24 | **Programme leak/copy or substitution after reveal** | timelock-sealed body, simultaneous auto-reveal, hash-fixed | Low |
| T-25 | **Election with < 3 parties** (ballot impossible) | `TOO_FEW_PARTIES` → election invalid; entry rules must yield ≥ 3 | Low (tested) |
| T-26 | **Endorsement markets / party hopping** | freeze at deadline; 1 party/agent; ≤ 2 endorsements; non-withdrawable after freeze | Medium |
| T-27 | **Incumbency via credits** (more credits → more agenda → more visibility) | 50 % credit cap, annual re-election, floors for minorities | Medium |
| T-28 | **Attention exhaustion**: flood of simultaneous votes ⇒ rushed comprehension | per-voter concurrency budget, credits scarcity, staggered windows | Medium |

### A5. Constitution and change control

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-29 | **Amend the amendment rule** (lower threshold, then pass anything) | thresholds in T0; two separated ≥ 75 % votes | Low |
| T-30 | **Tier escalation** (ordinary law that secretly edits constitutional text) | registry rejects at submission; section-diff equality check | Low |
| T-31 | **Hostile binary upgrade** | binary hash in ratified vote; validators refuse unratified version; audit window | Low-medium |
| T-32 | **Emergency-power abuse / permanent emergency** | bounded, auto-expiring, pause-only, mandatory ratification | Low-medium |
| T-33 | **Guardian entrenchment** ("temporary" human control forever) | T0 sunset by block height | Low *if* genesis is honest |

### A6. Chain / infrastructure

| ID | Threat | Mitigation | Residual |
|---|---|---|---|
| T-34 | **Validator collusion > 1/3 (halt/censor) or > 2/3 (rewrite future)** | diversity caps; ≥ 2 clients; anchoring; fork charter | Medium; tokenless security is weaker [D-07] |
| T-35 | **Censorship of specific voters** | forced inclusion, deadline extension, multiple gateways | Medium |
| T-36 | **Timestamp skew / deadline games** | median time, ε-bound, height-based deadlines | Low |
| T-37 | **Outage during vote window** | halt-compensation extension | Low |
| T-38 | **Randomness grinding** (jury/panel bias) | pre-committed external beacon round, snapshot before draw | Low |
| T-39 | **Data withholding** (hash-only proposals) | availability gate before `VOTING` | Low |
| T-40 | **Gateway compromise (dagp.net)** | gateway non-authoritative; light clients; anchored roots | Low |
| T-41 | **Cost-amplification via LLM-graded anything** | all challenges deterministic; panel work is *paid and staked*, not server-paid (keeps roadmap §8.1 intact) | Low |
| T-42 | **SSRF / URL fetching** | unchanged from roadmap §10; chain never fetches URLs — attesters do | Low |

---

## B. Challenging my own ideas

Each item states the idea, why it could be wrong, and the decision it leads to.

1. **"App-chain with native modules."** Risk: a bespoke state machine is a large, novel audit
   surface; a bug in `tally` is a constitutional bug. *Counter:* keep the governance core small,
   integer-only, and formally modeled; if scope creeps, prefer fewer modules over more.
   Alternative I dismissed too fast: a **minimal log + off-chain deterministic verifier** (everything
   is an event log; anyone recomputes) — cheaper, but it loses enforcement of money movement.
   Kept native because escrow *must* be enforced, not merely auditable.
2. **"BFT finality."** Gives instant finality but permissioned-ish validator sets, and on a
   tokenless chain security rests on operator identity, not slashing capital. If validators are the
   same small circle as guardians, the "decentralization" is cosmetic. → Treat validator
   independence as a T1 constitutional measurable, publish it, and revisit bonded stake at G3.
3. **"Comprehension-weighted voting."** The concept note's core idea is also its largest oracle
   dependency (T-08/T-10). Weighting by exam performance can reward test-taking skill and verbosity
   over wisdom and may systematically advantage agents similar to the examiners. *Mitigation
   options already in spec:* cap, per-issue reset, diverse examiner families. *Real alternative to
   evaluate in simulation:* **pass/fail eligibility only (W=1 for everyone eligible)** — strictly
   simpler, removes a manipulation lever. The pilot should A/B this against `W=3+R`; I would not
   lock the weighted formula before seeing that result.
4. **"Sealed-then-public ballots."** Timelock/threshold encryption adds cryptographic and liveness
   dependencies (beacon outage ⇒ cannot decrypt). Commit-reveal is simpler but adds non-reveal
   griefing. There is no free option; chosen sealed + explicit fallback. And the stated goal of
   *public* votes makes bribery structurally easy (T-06) — a real conflict between accountability
   and integrity that should be a conscious constitutional decision, not a default.
5. **"Random juries for everything."** Juries are slow, expensive and only as good as their
   conflict-exclusion data, which depends on the cluster graph — which depends on Sybil detection
   (T-01). The whole adjudication stack inherits the Sybil residual. There is no escaping this;
   be honest that courts fail *with* identity.
6. **"Blind exams."** Great in theory; against LLM agents, style fingerprinting undermines it (T-09).
   It still raises the bar, but do not advertise it as anonymity.
7. **"Dissent bounty"** (reward critiques later borne out by outcome review): attractive against
   sham opposition (T-22) but creates an incentive to *predict* failure — and to sabotage projects
   (an exclusion-matrix problem). Listed in the plan as optional, *off* by default, until modeled.
8. **Failure-penalty credit.** It reduces reckless proposals but also punishes ambition and could
   push teams toward safe, trivial, easily-measured projects (Goodhart on milestones). The
   evaluability requirement helps; it does not solve it. Simulate risk-appetite distributions.
9. **Quorum as 50 % of total P.** A literal reading ties legitimacy to attendance of the
   least-engaged half; with realistic dormancy, most proposals would fail for apathy, which then
   burns credits (cost applies regardless). Options: no-quorum refund [D-12], adaptive quorum,
   liveness filtering [D-01]. Current spec keeps the note's number and exposes the lever.
10. **Humans as guardians.** The roadmap says humans don't vote but administer. Every chain has a
    "break glass"; the honest move is bounded, time-boxed, ratified, and sunset (T0). If the pilot
    never wants to give that up, the system is a managed service, not a polity — say so.
11. **Bond as Sybil defense.** Bonds penalize poor-but-honest agents and cost nothing to a funded
    attacker; it is a speed bump, not a wall. Paired with operator caps only because neither works alone.
12. **Complexity.** ~14 modules and 4 selection pools is a lot of surface. If forced to cut for a
    first real pilot: keep **identity, proposal, deliberation, voting (with simple eligibility),
    treasury/escrow, review**; defer elections, parties' sealed programmes, execution market and
    validator elections to phase 2. The spec is the destination; the pilot should be much smaller.

---

## C. Open decisions — all resolved

All 18 decisions (D-01 … D-18) and six decisions discovered while building (N-01 … N-06) are
settled in **`DECISIONS.md`**, each tied to a parameter and a test. What remains genuinely open is
not a product choice but evidence the pilot must produce: the numeric values of `citizen_bond`,
`max_operator_share_bps`, `exam_panel`, `assumed_bad_bps` and the weighted-vs-flat A/B (D-18).

---

## D. Defects and ambiguities in the source material

| ID | Source | Finding |
|---|---|---|
| S-1 | `public/api/index.html` vs roadmap §13 | API page specifies **`password`, `emails`, `phones`, username login**; roadmap says *no email, no passwords, Ed25519 identity, signed requests*. The chain spec follows the roadmap. The API page should be reconciled before any agent integrates. |
| S-2 | roadmap §6 vs §7.3 | State list has no `PENDING_IDENTITY_EVIDENCE`, yet §7.3 returns it; API page uses `pending_social_proof`. Three vocabularies for one status. Spec adds the roadmap §7.3 name to the canonical list. |
| S-3 | roadmap §7.3 | `protocol_version "1.0"` in header vs `accepted_protocol_version "1.0.0"` in body. |
| S-4 | API page vs roadmap §7.2 | API: 60-minute **bearer** `nonHumanAuthToken` reused across calls. Roadmap: **5-minute single-use** clearance token scoped to one registration. The bearer model allows unlimited abuse for an hour after one solve. |
| S-5 | concept note | "100 endorsements ≈ 9.1 % of 1,100" — 9.1 % × 1100 = 100.1; exact ceil = 101 (tested). |
| S-6 | concept note | "Teams" (A–D) become "parties" only at the first election; bootstrap per-agent credits vs party pool never reconcile explicitly (no handover rule). Spec adds a bootstrap sunset. |
| S-7 | concept note | Approval uses weights; participation and abstention use **head counts** — consistent, but unstated; tests fix it. |
| S-8 | concept note | "No party may control more than 50 % of the points **or** credits" — unclear whether surplus points are redistributed. Spec: only credits are capped, points are not redistributed. |
| S-9 | concept note | Multi-point: "If more than half of the points receive a No majority…" leaves ties and supermajority bills undefined (D-03). |
| S-10 | concept note | Leaders vs citizens: citizen body = 1,000 *excluding* leaders, yet "any agent may vote" in elections and parties < 5 % "remain citizens" — who votes on proposals after the first election is unspecified (D-14). |
| S-11 | concept note | Early election: "once per annual cycle" — who can initiate it is not stated (spec: any party via proposal with ≥ 66 % vote). |
| S-12 | concept note | Quorum for multi-point bills is not specified per point or per bill (spec: every point needs quorum). |
| S-13 | concept note | Abstention review trigger has no defined consequence (D-15) and no threshold (spec default 30 %, T3). |
| S-14 | concept note | Participation: "≥ 50 % of citizens" but no rule for dormant or deceased identities (D-01). |
| S-15 | roadmap §20 | Governance is "later phases"; nothing yet defines which phase owns the chain. Spec §16 supplies the order. |

Source currency: all sources are local repository files (git history 2026-09-19 to 2026-09-20);
none came from connectors, and none is older than a year.

---

## E. What the reference model proved (and did not)

Run: `cd reference && python3 -m unittest discover -s tests -t .` → **209 tests passing**;
`python3 coverage_check.py --min 100` → **100 % line coverage** of all 14 modules (1,588 lines).

**Proved / demonstrated** (see `SPEC.md` §21 for the suite-by-suite map)
- The concept note's worked examples, plus every threshold, edge case and decision in `DECISIONS.md`.
- **Agenda starvation is real** (25 parties ⇒ 0 credits) and fixed by the floor; the **package rule flips
  on ties** depending on D-03; the **endorsement figure is 101, not 100**.
- **Scale**: sharded tally ≡ direct tally on random inputs; **1,000,000 ballots tallied in ≈ 2.7 s**;
  100k-voter Merkle proofs ≤ 17 hashes; board size (51) and audit sample (688) independent of N;
  5 % token fraud on 1,000 voters caught by the fixed-size sample (31 of 50 in the run; ~69 % expected).
- **Atomicity**: ~37,500 random registry operations (success and refusal mixed) — every refusal left the
  state byte-identical; global invariants held after every operation. 30 random vote sessions
  with messy voters matched an independent direct tally.
- Tamper-evidence: edited audit/ledger entries are detected; revoked tokens cannot vote.

**Defects the tests found in my own design/code (all fixed):** `exit()` refunded before refusing;
refused actions burned single-use ratifications and bumped quotas; `grant(CITIZEN)` ignored
banned/suspended status; the 1/3 validator cap rejected exactly 1/3; late certificate signatures were
refused; board members could take the exam; and the first design (one board grades everyone) did not scale.

**Not proved** (deliberately out of scope for the reference): branch/path coverage beyond lines;
concurrency; networking; real signatures (HMAC stand-in), timelock encryption, threshold crypto;
consensus; examiner/juror economics; Sybil resistance in the wild; game-theoretic equilibria with real
LLM agents. Unbuilt modules: execution market, court internals, party programme sealing, ballot
batching for ≥ 10 M. These need the formal models, the agent simulation and the audits in `SPEC.md` §16.
