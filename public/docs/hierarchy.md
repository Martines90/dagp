# Nested societies and parent authority

Status: **optional Python governance reference implemented; not native blockchain governance**.
The implementation is `reference/dagp_ref/societies.py`; institutional votes use
existing comprehension, certification, challenge and sharded tally machinery.
Root governance remains available without constructing a `SocietyTree`.

## Purpose and limits

A society can contain regions, cities, institutions or other nested jurisdictions.
Names do not define powers: membership, parent, charter and approved decisions do.
Root citizenship is shared; a member of a child is also a member of every ancestor.
The root keeps its identity namespace, constitution and common treasury. Creating
another level does not create another copy of a citizen, money or parliamentary power.

Hierarchy is useful for local decisions at large population sizes. It adds process
costs and is optional for small communities. The current conservative reference
requires review at **every ancestor**, both before voting and before implementation.
This follows the requested rule that higher authorities always approve. It can be a
throughput bottleneck. Future delegated budgets or automatically checked policy
lanes need explicitly approved extensions; no silent exemption is implemented.

Default depth is eight levels including the root; a constructor may use a stricter
limit, up to an absolute sixteen-level bound. The reference forbids cycles by only
adding new children beneath existing jurisdictions. Membership changes, boundary
moves, dissolution and federation are separate future decision workflows; there is
no arbitrary administrator command to move a population or reparent a unit.

## Formation: both populations consent

1. Each founder signs the exact chain, parent, child, membership and charter plan.
   At least ten distinct, eligible parent citizens are required under default rules.
2. The pending child cannot vote, appoint officials or operate its local registry.
3. Every ancestor assigns three independent, eligible vote supervisors from a
   pool committed before a future beacon. Founder operators and their parties are
   excluded. All assigned supervisors sign a compatibility assessment of the exact
   request. A shortage blocks approval; founders cannot choose substitute officials.
4. Separate dedicated `FORMATION` ballots cover the **full parent electorate** and
   the **founding cohort**. Both require at least 50% participation and 66% approval
   by participating identities **and** voting weight. Abstentions are included in
   both approval denominators. Stronger root thresholds still apply.
5. Ballots require existing comprehension checks, independent certification and
   challenge handling. Certification members remain in the structural electorate
   denominator although they cannot vote on what they certify.
6. There is at least seven model days of notice before voting and seven days of
   cooling off after both challenge windows. The same immutable plan must pass on
   both sides, remain unexpired and retain ancestor pre-approval before activation.

These are extraordinary formation rules, not a change to the ordinary root
constitutional tally. A failed or expired pending formation remains inert; retry
uses a new proposal identifier. No official can activate it with a pass flag.

## Same governance structure, scoped powers

`ScopedRegistry` supplies local identities and roles to the existing `PartyRegistry`,
`PreElection`, campaign, `ProposalReview`, `VoteSession` and monthly-credit modules.
Operators must use a separate domain, party registry and credit ledger per scope.
Party exclusivity applies **within each jurisdiction**. Local parties earn local
mandates and credits through local elections; they gain no root seats or credits.
This optional extension must be explicitly adopted by a native constitution before
production use; creating a Python object is not a constitutional upgrade transaction.

- Root citizenship/status gates every local action. A root ban or loss of civic
  standing cannot be evaded through a child. Root operator/family labels and
  citizenship activation age remain authoritative.
- Local party membership, suspensions and offices live in local state. A jurisdiction
  ban blocks its descendants but cannot remove root citizenship. Root offices are not automatically local offices.
- Root-recognized examiner/verifier/reviewer/juror/executor qualifications may be
  used locally; root qualification revocation removes their local effectiveness.
  Local offices still require normal ratifications, tenure, stake where applicable,
  activation delays and conflict checks.
- Sensitive-office appointment events and administrative protection events share
  root rolling budgets across scopes. Creating ten jurisdictions does not provide
  ten independent allowances for the same officials.
- Every scope uses the root protocol parameters. Local referendums cannot change
  root credit, quorum, identity or constitutional constants. Local charter constraints
  may add obligations but cannot replace a different ancestor constraint value.

## Mandatory approval path for proposals and budgets

A trusted keeper records a request binding scope, issue, exact content hash,
beneficiaries, budget, ancestry/rule snapshot, expiry and stage. This keeper must
identify the actual affected parties, not accept an agent-selected conflict list.
All assigned ancestor reviewers sign their own chain/scope-bound assessments.

Before local discussion or voting starts, `activate_preapproval`:

- requires every ancestor's complete assigned review;
- reserves the whole approved budget ceiling from the common treasury;
- installs the permission for that exact issue, version and amount.

Local `ProposalReview` construction and amendments require this permission before
spending a credit. An amendment needs fresh ancestor approval of its exact content;
its budget cannot increase. Replacement releases a reduced reservation's difference.
Once a vote is open, its parent permission cannot be replaced to alter its meaning.
Local election sessions similarly need prior approval of the committed campaign.

A direct local `VoteSession` cannot bypass these gates. It has no direct common-
treasury spending authority. Approval is rechecked while casting, closing and
finalizing; expired permissions and changed ancestor rules stop execution.

After a local proposal passes, a separate `FINAL` request binds its actual tally
commitment and approved amount. Every ancestor reviews it again. `finalize_local`
recomputes the accepted ballots, requires the exact passing-clause tranche schedule,
and only then converts the reservation to milestone escrow. Rejected clauses receive
no allocation; unused ceiling returns to the common budget. An expired unimplemented
permission releases its reservation. Funded milestone conditions are retained for the
existing authenticated execution/payment adapter; raw Treasury methods are keeper
internals, not an agent payment API.

## Higher law always takes precedence

The structural check rejects unequal values for inherited, named charter constraints.
Rule contexts commit ancestor charters, membership and **recorded governing decisions**.
The root keeper calls `record_root_decision` for reviewed finalized root laws; local
finalization records local laws. A new ancestor law invalidates descendant permits
and makes previously recorded descendant laws inactive pending compatibility review
(`law_is_current`). Root law and parameter adapters must record these changes atomically
in a native implementation; omitting an approved root law is not a supported integration.

Hashes cannot prove that two natural-language laws are logically compatible. Signed,
randomly assigned supervisors perform that semantic assessment. Their evidence is
public and subject to existing constitutional/judicial review. The model does not
provide a theorem prover, automatic legal interpretation or a complete appellate
court. Root identity/operator truth, keeper authorization, court inputs, consensus
time and future-beacon bytes remain reference trust assumptions.

## Implemented API and validation

- `SocietyTree.propose_child`, `formation_mandates`, `activate_child`: formation.
- `request`, `approve`, `activate_preapproval`, `require_preapproval`: parent gates.
- `view`: isolated local registry; cannot open a pending child.
- `finalize_local`, `expire`, `record_root_decision`, `law_is_current`: execution and
  ancestor-policy precedence.
- `InstitutionalMandate`: engine-registered, single-session structural capability;
  finalized certificates recompute ballots rather than accepting an imported result flag.

Run `PYTHONPATH=chain/reference python3 -m unittest tests.test_societies -v`.
Tests cover child/grandchild formation, founder consent, conflicting charters,
pending authority, local/root sanctions, revoked qualifications, unchanged root
thresholds, exact version/budget gates, amendments, real reviewed local votes,
partial bill funding, final ancestor reviews, malformed and replayed merger claims,
operator limits, shared migration quotas and deterministic checkpoint restoration.
They are model tests, not evidence of native million-citizen network throughput.
