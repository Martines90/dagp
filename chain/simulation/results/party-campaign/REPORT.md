# DAGP community simulation

Synthetic agents exercise the DAGP Python reference rules. This is a hybrid experiment, not AGI and not on-chain governance.

Admission inputs, bootstrap ratifications, briefs, answers, jury decisions and project attestations are modeled. Governance signatures use the reference HMAC stand-in. Only the result commitment uses real Ed25519 and CometBFT.

| Run | Population | Checks | Exams | Ballots | Treasury conserved |
|---|---:|---:|---:|---:|---:|
| 7 / WEIGHTED | 1100 | 167 | 13680 | 10526 | 100000 |
| 7 / FLAT | 1100 | 167 | 13680 | 10526 | 100000 |

## Seed 7 — WEIGHTED

| Election | Party | Points | Credits | Parliament |
|---|---|---:|---:|---|
| 1 | Builders | 2262 | 9 | YES |
| 1 | Stewards | 1329 | 5 | YES |
| 1 | Researchers | 810 | 3 | YES |
| 1 | Commons | 275 | 1 | YES |
| 1 | Frontier | 0 | 0 | NO |
| 2 | Builders | 2486 | 13 | YES |
| 2 | Researchers | 1422 | 7 | YES |
| 2 | Commons | 627 | 3 | YES |
| 2 | Stewards | 29 | 0 | NO |
| 2 | Frontier | 0 | 0 | NO |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 906 / 1054 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 890 / 1055 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 157 / 1054 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 904 / 1054 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 895 / 1054 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 908 / 1055 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 922 / 1054 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 883 / 1054 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 916 / 1054 |
| Five-clause public infrastructure | Builders | PARTIAL | CLOSED_SUCCESS | 923 / 1054 |

## Seed 7 — FLAT

| Election | Party | Points | Credits | Parliament |
|---|---|---:|---:|---|
| 1 | Builders | 2262 | 9 | YES |
| 1 | Stewards | 1329 | 5 | YES |
| 1 | Researchers | 810 | 3 | YES |
| 1 | Commons | 275 | 1 | YES |
| 1 | Frontier | 0 | 0 | NO |
| 2 | Builders | 2486 | 13 | YES |
| 2 | Researchers | 1422 | 7 | YES |
| 2 | Commons | 627 | 3 | YES |
| 2 | Stewards | 29 | 0 | NO |
| 2 | Frontier | 0 | 0 | NO |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 906 / 1054 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 890 / 1055 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 157 / 1054 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 904 / 1054 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 895 / 1054 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 908 / 1055 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 922 / 1054 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 883 / 1054 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 916 / 1054 |
| Five-clause public infrastructure | Builders | PARTIAL | CLOSED_SUCCESS | 923 / 1054 |

## Paired comparison

[
  {
    "seed": 7,
    "outcome_differences": []
  }
]

Identical keyed behavioral draws are used in both modes. Later elections may differ because realized project outcomes affect party reputation. Stress distributions are chosen to exercise known failure paths; they do not estimate real AGI behavior or demonstrate that weighting improves decisions.
