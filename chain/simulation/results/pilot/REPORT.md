# DAGP community simulation

Synthetic agents exercise the DAGP Python reference rules. This is a hybrid experiment, not AGI and not on-chain governance.

Admission inputs, bootstrap ratifications, briefs, answers, jury decisions and project attestations are modeled. Governance signatures use the reference HMAC stand-in. Only the result commitment uses real Ed25519 and CometBFT.

| Run | Population | Checks | Exams | Ballots | Treasury conserved |
|---|---:|---:|---:|---:|---:|
| 7 / WEIGHTED | 1100 | 130 | 10114 | 9253 | 100000 |
| 7 / FLAT | 1100 | 130 | 10114 | 9253 | 100000 |
| 19 / WEIGHTED | 1100 | 128 | 10157 | 9243 | 100000 |
| 19 / FLAT | 1100 | 128 | 10157 | 9243 | 100000 |
| 43 / WEIGHTED | 1100 | 126 | 10168 | 9274 | 100000 |
| 43 / FLAT | 1100 | 130 | 10168 | 9274 | 100000 |

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
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 887 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 262 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 901 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 892 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 904 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 881 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 913 / 1052 |

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
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 887 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 262 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 901 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 892 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 904 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 881 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 913 / 1052 |

## Seed 19 — WEIGHTED

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3023 | 9 |
| 1 | Stewards | 1792 | 5 |
| 1 | Researchers | 1185 | 3 |
| 1 | Commons | 342 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 2885 | 9 |
| 2 | Builders | 2475 | 7 |
| 2 | Commons | 883 | 2 |
| 2 | Stewards | 36 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 869 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 901 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 220 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 918 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 922 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 902 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 899 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 892 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 913 / 1052 |

## Seed 19 — FLAT

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3023 | 9 |
| 1 | Stewards | 1792 | 5 |
| 1 | Researchers | 1185 | 3 |
| 1 | Commons | 342 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 2885 | 9 |
| 2 | Builders | 2475 | 7 |
| 2 | Commons | 883 | 2 |
| 2 | Stewards | 36 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 869 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 901 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 220 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 918 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 922 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 902 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 899 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 892 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 913 / 1052 |

## Seed 43 — WEIGHTED

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3012 | 9 |
| 1 | Stewards | 1787 | 5 |
| 1 | Researchers | 1116 | 3 |
| 1 | Commons | 350 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Builders | 3416 | 10 |
| 2 | Researchers | 1781 | 5 |
| 2 | Commons | 1129 | 3 |
| 2 | Stewards | 30 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 909 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 897 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 213 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 902 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 883 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 939 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 899 / 1052 |
| Contested public model-training subsidy | Researchers | FAILED | REJECTED | 904 / 1052 |

## Seed 43 — FLAT

| Election | Party | Points | Credits |
|---|---|---:|---:|
| 1 | Builders | 3012 | 9 |
| 1 | Stewards | 1787 | 5 |
| 1 | Researchers | 1116 | 3 |
| 1 | Commons | 350 | 1 |
| 1 | Frontier | 0 | 0 |
| 2 | Researchers | 2863 | 9 |
| 2 | Builders | 2552 | 8 |
| 2 | Commons | 911 | 2 |
| 2 | Stewards | 30 | 0 |
| 2 | Frontier | 0 | 0 |

| Project | Party | Outcome | Project state | Ballots / electorate |
|---|---|---|---|---|
| Shared research library | Builders | PASSED | CLOSED_SUCCESS | 909 / 1052 |
| Unbounded speculative compute | Stewards | FAILED | REJECTED | 897 / 1052 |
| Optional archive migration | Researchers | NO_QUORUM | REJECTED | 213 / 1052 |
| Undefined collective mission | Commons | VOIDED | VOIDED | 902 / 1052 |
| Storage availability dispute | Builders | VOIDED | VOIDED | 883 / 1052 |
| Faulty compute procurement | Stewards | PASSED | CLOSED_FAILURE | 939 / 1052 |
| Examiner cartel incident | Researchers | PASSED | CLOSED_SUCCESS | 921 / 1052 |
| Silent certification board | Commons | PASSED | CLOSED_SUCCESS | 899 / 1052 |
| Contested public model-training subsidy | Researchers | PASSED | CLOSED_SUCCESS | 904 / 1052 |

## Paired comparison

[
  {
    "seed": 7,
    "outcome_differences": []
  },
  {
    "seed": 19,
    "outcome_differences": []
  },
  {
    "seed": 43,
    "outcome_differences": [
      {
        "issue": "project-8",
        "weighted": "FAILED",
        "flat": "PASSED"
      }
    ]
  }
]

Identical keyed behavioral draws are used in both modes. Later elections may differ because realized project outcomes affect party reputation. Stress distributions are chosen to exercise known failure paths; they do not estimate real AGI behavior or demonstrate that weighting improves decisions.
