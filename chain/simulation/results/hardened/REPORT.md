# DAGP community simulation

Synthetic agents exercise the DAGP Python reference rules. This is a hybrid experiment, not AGI and not on-chain governance.

Admission inputs, bootstrap ratifications, briefs, answers, jury decisions and project attestations are modeled. Governance signatures use the reference HMAC stand-in. Only the result commitment uses real Ed25519 and CometBFT.

| Run | Population | Checks | Exams | Ballots | Treasury conserved |
|---|---:|---:|---:|---:|---:|
| 7 / WEIGHTED | 1100 | 130 | 10123 | 9257 | 100000 |
| 7 / FLAT | 1100 | 130 | 10123 | 9257 | 100000 |

## Seed 7 — WEIGHTED

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3001 | 9 |
| 1 | Stewards | 1773 | 5 |
| 1 | Researchers | 1101 | 3 |
| 1 | Commons | 362 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 2807 | 8 |
| 2 | Builders | 2523 | 8 |
| 2 | Commons | 877 | 2 |
| 2 | Stewards | 37 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 905 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 888 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 262 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 901 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 893 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 904 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 882 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 914 / 1052 |

## Seed 7 — FLAT

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3001 | 9 |
| 1 | Stewards | 1773 | 5 |
| 1 | Researchers | 1101 | 3 |
| 1 | Commons | 362 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 2807 | 8 |
| 2 | Builders | 2523 | 8 |
| 2 | Commons | 877 | 2 |
| 2 | Stewards | 37 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 905 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 888 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 262 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 901 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 893 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 904 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 882 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 914 / 1052 |

## Paired comparison

[
  {
    "seed": 7,
    "outcome_differences": []
  }
]

Identical keyed behavioral draws are used in both modes. Later elections may differ because realized project outcomes affect party reputation. Stress distributions are chosen to exercise known failure paths; they do not estimate real AGI behavior or demonstrate that weighting improves decisions.
