# DAGP community simulation

Synthetic agents exercise the DAGP Python reference rules. This is a hybrid experiment, not AGI and not on-chain governance.

Admission inputs, bootstrap ratifications, briefs, answers, jury decisions and project attestations are modeled. Governance signatures use the reference HMAC stand-in. Only the result commitment uses real Ed25519 and CometBFT.

| Run | Population | Checks | Exams | Ballots | Treasury conserved |
|---|---:|---:|---:|---:|---:|
| 7 / WEIGHTED | 10100 | 130 | 98307 | 89414 | 100000 |
| 7 / FLAT | 10100 | 130 | 98307 | 89414 | 100000 |

## Seed 7 — WEIGHTED

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 29054 | 9 |
| 1 | Stewards | 16761 | 5 |
| 1 | Researchers | 10758 | 3 |
| 1 | Commons | 3522 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 27044 | 9 |
| 2 | Builders | 24042 | 8 |
| 2 | Commons | 8520 | 2 |
| 2 | Stewards | 272 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 8761 / 10236 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 8744 / 10236 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 2239 / 10236 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 8760 / 10236 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 8749 / 10236 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 8708 / 10236 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 8805 / 10236 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 8729 / 10236 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 8776 / 10236 |

## Seed 7 — FLAT

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 29054 | 9 |
| 1 | Stewards | 16761 | 5 |
| 1 | Researchers | 10758 | 3 |
| 1 | Commons | 3522 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 27044 | 9 |
| 2 | Builders | 24042 | 8 |
| 2 | Commons | 8520 | 2 |
| 2 | Stewards | 272 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 8761 / 10236 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 8744 / 10236 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 2239 / 10236 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 8760 / 10236 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 8749 / 10236 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 8708 / 10236 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 8805 / 10236 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 8729 / 10236 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 8776 / 10236 |

## Paired comparison

[
  {
    "seed": 7,
    "outcome_differences": []
  }
]

Identical keyed behavioral draws are used in both modes. Later elections may differ because realized project outcomes affect party reputation. Stress distributions are chosen to exercise known failure paths; they do not estimate real AGI behavior or demonstrate that weighting improves decisions.
