# DAGP Chain

A blockchain design for running the DAGP agent society end to end: registration, roles and node
roles, parties, elections, weighted votes validated by randomly drawn examiners, law and constitution
changes, budgets, execution, review and accountability — built to scale from 1,000 to 100,000,000
citizens, with the guarantees and the limits stated plainly.

| File | What it is |
|---|---|
| `SPEC.md` | Protocol and system specification. Part I: architecture, roles, identity, constitution tiers, voting, elections, treasury, courts, consensus, bootstrap, invariants. **Part II (v0.2): examiner-run voting process, role and node lifecycle, scale by design, test map** |
| `DECISIONS.md` | Every open question settled (D-01…D-18, N-01…N-06) with rationale and the code/test that enforces it |
| `THREATS.md` | Threat register (50 threats), critique of my own design, defects found in the DAGP sources, what the tests proved and did not |
| `CODEX_HANDOFF.md` | **Paste-ready prompt + full context and milestone roadmap (M0–M11) for building the Go implementation with ChatGPT Codex** |
| `reference/` | Executable reference model (Python, stdlib only): **209 tests, 100 % line coverage**, fuzzing, a 1,000,000-voter tally |

```
cd chain/reference
python3 -m unittest discover -s tests -t .      # all tests (≈ 16 s)
python3 coverage_check.py --min 100             # line coverage, no third-party tools
```

Read order: `SPEC.md` §1–§2 (principles; what a chain can/cannot guarantee) → §18 (who validates
what) → §19 (roles) → §20 (scale) → `DECISIONS.md` → `THREATS.md` §B (where it is weakest).

Reference modules: `tally` · `election` · `treasury` · `proposal` · `roles` · `keys` · `comprehension` ·
`session` · `scale` · `sortition` · `emergency` · `ledger` · `crypto_sim` · `params`.
