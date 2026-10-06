# Governed constants, monthly credits and independent clauses

Current reference rules, updated 2026-10-06. This document supersedes earlier 50% quorum, package-gating and automatic credit-floor defaults in the historical specification. These are executable Python reference rules, not native G0 blockchain transitions.

## Credits and time

The default allowance is `min(10, floor(election_share / 5%))`, with a 5% eligibility threshold. Election share means the share of valid ranked election **points**, from the existing 4/2/1 ballot; it does not mean the number of citizens who mentioned a party. A 27% share yields five proposal-start credits. The automatic fragmentation fallback is disabled: parties below 5% receive zero.

`MonthlyCredits` accepts only finalized, successful elections from its role registry. First certification initializes the current UTC month. Each later calendar month replaces unused balances using the latest finalized election basis and current parameters. A second election in the same month changes the next allowance basis and cannot mint extra credits now. Repeated renewal is a no-op; skipped months cannot accumulate allowances. Failure debt survives and is repaid before new credits become spendable. A review spends its credit at filing. No-quorum/void refunds return only to the month charged; an expired credit cannot inflate a new month's allowance.

The caller supplies monotonically increasing committed UTC timestamps. The reference does not authenticate consensus timestamps itself; native keepers must derive them from committed block time and run governance activation before monthly renewal. No local wall clock determines a tally. The existing simulation uses an explicit January–March 2026 calendar.

## Parameter referendums and turnout

Every citizen ballot session, including elections, has a minimum 20% headcount quorum against its frozen eligible electorate. Recused proposers, certification-board members and ineligible/dormant identities are excluded when that electorate is frozen; it is not the count of all identities ever registered. Weighted yes power cannot compensate for inadequate participation. Invalid election ballots do not establish quorum. Abstentions count toward turnout but not decisive yes/no power.

`Kind.PARAMETER` requires **at least 66.00% of decisive voting power**, compared with exact integers, and the same headcount quorum. This is distinct from the existing constitutional two-thirds threshold. A typed parameter proposal must have an approved, signed review, be atomic and unfunded, and finish certification and challenges successfully. `ParameterGovernance` queues one update, rejects replay/stale rules/conflicts, and activates it at the next UTC month boundary. Open sessions keep their original parameter snapshot.

The bounded allowlist covers quorum, credit step/ceiling, party eligibility threshold, clause limit, weight mode, verified article cap, and bill mode. The 20% turnout floor, 66% authorization threshold and administrative security protections cannot be weakened through this path. Setting 4% per credit does not also change the separate 5% eligibility threshold. Changing that threshold needs an explicit approved parameter entry.

## Point-by-point votes and budgets

`BillPoint` binds a stable ID, text, optional budget, exact acceptance milestones, and optional prerequisite clause IDs into the reviewed record and voting certificate. The owner may refine text during review with fresh independent supervisor approvals; IDs stay fixed and per-clause budget ceilings cannot rise. Clauses must partition the overall budget and milestones exactly. Dependencies must be known and acyclic.

One identity submits one sealed vector containing Y, N, A or a skipped entry (`None`) for each clause, using its authenticated exam token and frozen membership proof. Each clause independently needs 20% participation and its applicable approval threshold. Skipping a clause does not count as turnout on it. Ordinary approval needs strictly more than 50% of decisive power; 51% passes and a tie fails.

All approved clauses produce `PASSED`; some produce `PARTIAL`; none activate if no clause passes. A rejected prerequisite also prevents its dependent from taking effect, even if that dependent won its own tally. No majority-of-clauses gate exists in default `INDEPENDENT` mode. The older `PACKAGE` behavior remains available only as an explicit configuration choice and is governable through the referendum path.

At finalization only effective approved clauses activate. Only their tranches enter escrow; rejected/under-quorum/dependency-blocked funding returns to the common treasury. Approved unfunded clauses can take effect without reserving money for rejected funded clauses. An upheld or unresolved timed-out challenge voids the whole session and releases its reservation. Existing milestone verification/payment protections still apply. Raw clause outcomes and effective clauses remain separately available so dependencies do not obscure voters' decisions.

Tests cover exact 20% and 66% boundaries, malformed vectors, duplicate identities, independent minority-of-clauses success, skips, dependency cycles/closure, partial funding, unfunded effects, challenge rollback, protected constants, immutable open sessions, monthly replay/backdating, election replays, same-month remint attempts, debt and expired refunds. Semantic coherence of clause text, operator identities, HMAC reference signatures and trusted court/consensus inputs remain assumptions requiring production mechanisms and independent review.
