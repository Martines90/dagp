# Parties, pre-elections, campaigns and parliament

Current executable reference rules, 2026-10-06. This supersedes historical endorsement-count qualification and optional campaign reading. These state machines run in Python; native G0 keepers are not implemented.

## Party membership and internal sanctions

`PartyRegistry.form` requires at least ten distinct, eligible citizen founders, with every founder signing the same chain-bound formation record. A citizen has one current party affiliation. Joining and leaving are signed, nonce-protected operations. A second registry cannot reset affiliations on the same identity registry.

An internal BAN or SUSPEND requires signed approvals from at least half of the full party roster frozen when its case opened: five of ten, six of eleven. An opening complaint is not itself an approval. Outsiders, duplicate signatures, departed members and currently suspended members cannot contribute approvals. Later departures cannot shrink the denominator. Evidence is committed, cases expire, and suspension durations are bounded. Targets retain their public citizen voting rights, citizenship, identity and funds.

A ban removes membership and party privileges, and prevents rejoining that party. The citizen can join a different party when membership changes are allowed. A suspension leaves membership intact, temporarily removes party privileges, and expires automatically. Leaving/rejoining does not erase an unexpired suspension from that party. Internal sanctions cannot ban citizens from the society or remove their independent public offices.

Membership changes are frozen through the pre-election/campaign/election window. Local sanctions remain possible, but cannot rewrite already frozen candidate or member-case snapshots. Next-cycle qualification requires at least ten currently eligible, unsuspended members. One controller and replay-protected cycle IDs prevent duplicate enrollment.

## Pre-election support

Each eligible citizen submits one signed ballot containing a primary party (five points) and an optional, distinct secondary party (three points). They cannot place both choices on the same party, submit a third choice or vote twice. Ballots are sealed until close. Both party rosters and the eligible citizen electorate are frozen at opening.

Only actually cast, accepted support points enter the denominator. A party qualifies for the main election when:

`party_support_points * 10000 >= total_support_points * 500`

Exactly 5% qualifies. This is a share of cast support points, not 5% of registered citizens. The pre-election separately requires at least the configured citizen turnout (20% by default). Zero support, missing quorum or no qualifying parties cannot authorize a campaign. There is no remaining absolute 9.1%-population endorsement requirement on this path; historical `qualify_parties` helpers are retained only for legacy tests.

## Campaign and comprehension

Every pre-qualified party publishes a member-signed program and political vision, bound to the chain and pre-election commitment. The immutable campaign record commits to these texts, their authors/signatures, qualified roster, question bank, campaign window and membership conflicts. A cycle authorizes one campaign and one main election; repeated publication or election opening is refused.

Campaign comprehension covers both documents from **every** qualified party. The voter must declare the entire document set. Each document has an independent question set bound to its exact source hash. Question prompts, displayed options and answer commitments are included in the bank commitment; duplicate question IDs are refused. Every asked program/vision question must be answered correctly. Optional reading, partial declarations and a passing general-topic score cannot substitute for missing campaign sections. The existing topic exam, independent random graders, retries, signatures and fraud audits still apply. Candidate-party operators are excluded from grading and certification. Campaign question selection uses the voter, recorded attempt number, beacon and bank commitment; a voter-chosen secret cannot grind easier questions. Equal question content yields the same draws across paired weight modes.

The campaign closes before election voting opens, and neither programs nor the question bank can change afterward. This is an enforceable comprehension test, not proof that an agent read every sentence or understands every real-world consequence. Question relevance and semantic quality require independent review; the simulation uses scripted questions and synthetic behavior. Reference signatures remain HMAC stand-ins.

## Main election and monthly credits

The main-election default retains the existing ranked 4/2/1 ballot. When fewer than three parties qualify, the ballot has one slot per available party, preserving its highest-rank weights. A single-choice configuration is also supported. Campaign comprehension is required regardless of ballot mode. Distinct eligible choices are counted in points; malformed choices do not establish the minimum 20% citizen turnout.

A party enters parliament at at least 5% of the valid main-election points, using the same exact integer comparison. `ElectionResult.governing_parties` explicitly records the qualifying roster independently of credit balances. A party below the threshold receives zero governing credits. An election with no party over the threshold cannot install a new parliament or reset the credit basis.

The default credit allowance is `floor(percentage_share / 5)`, with no earlier 50%-share ceiling: 27% earns five credits, 73% earns fourteen, and 100% earns twenty. The share uses the full valid election-point denominator; excluded parties' points are not redistributed to inflate winners. Credit step and ceiling remain subject to the bounded parameter referendum path.

Monthly renewals preserve the parliament roster certified by the election. Changing parameters cannot admit an unelected party mid-cycle. Updated eligibility thresholds apply when a new election is tallied; the current parliament keeps its cycle eligibility. The current credit step applies at renewal, unused credits expire, debts survive, and repeated same-month elections cannot replenish spent credits. An outgoing party immediately loses its spending rights and unused allowance; pending refunds cannot restore governing power. Newcomers receive their first allowance at the next monthly reset, rather than minting a second current-month allowance.

Tests exercise founder consent, affiliation exclusivity, exact half-roster sanctions, expiry and suspension evasion, support weights and exact 5% boundaries, turnout, duplicate/malformed/replayed ballots, sealed records, all-party campaign checks, failed campaign answers, source/question tampering, duplicate campaign/election authorization, parliament exclusion, small candidate sets, sharded parity and frozen monthly eligibility. `simulation/results/party-campaign` exercises the same flow in two complete institutional cycles.
