"""Random selection and the two numbers that make the design scale-independent.

1. draw(): deterministic sortition. Selected set = k smallest H(seed, id); any node can
   recompute it; nobody can grind it once the seed (a future external beacon round bound to a frozen
   candidate list BEFORE its unpredictable value is revealed) is fixed. Cost O(candidates) streaming, output O(k).
2. panel_size(): the board size needed so that a hostile majority has probability <= target
   given an assumed hostile fraction of the pool (20% hostile, 1e-6 -> 51 members). It depends on
   the ADVERSARY, not on the population: the same board protects a million citizens as well as a
   thousand. The board certifies and audits; it does not grade every voter (see session.py).
3. audit_sample_size(): how many items to spot-check so that a cheating rate >= f goes
   unnoticed with probability <= delta. Again independent of population size.
"""
from __future__ import annotations

import heapq
from typing import Iterable

from .crypto_sim import H
from .params import BPS


def score(seed: bytes, ident: str) -> int:
    return int.from_bytes(H(b"sortition", seed, ident)[:16], "big")


def draw(seed: bytes, candidates: Iterable[str], k: int,
         exclude: frozenset | set = frozenset()) -> list[str]:
    if k <= 0:
        raise ValueError("k must be positive")
    pool = ((score(seed, c), c) for c in candidates if c not in exclude)
    return [c for _, c in heapq.nsmallest(k, pool)]


def _tail_numerator(g: int, bad_bps: int) -> int:
    """sum_{i >= floor(g/2)+1}^{g} C(g,i) bad^i good^(g-i)  (denominator BPS**g)."""
    from math import comb
    good = BPS - bad_bps
    t = g // 2 + 1
    return sum(comb(g, i) * bad_bps ** i * good ** (g - i) for i in range(t, g + 1))


def panel_size(bad_bps: int, fail_den: int, min_size: int = 5, max_size: int = 301) -> int:
    """Smallest odd g in [min_size, max_size] with P(hostile majority) <= 1/fail_den.
    Binomial tail is a conservative bound for sampling without replacement."""
    if not 0 <= bad_bps < BPS // 2:
        raise ValueError("an honest majority of the pool is a hard precondition")
    g = min_size | 1
    while g <= max_size:
        if _tail_numerator(g, bad_bps) * fail_den <= BPS ** g:
            return g
        g += 2
    raise ValueError("no panel size in range reaches the target")


def threshold(g: int) -> int:
    """Signatures needed from a board of size g (strict majority)."""
    return g // 2 + 1


def audit_sample_size(fraud_bps: int, miss_den: int) -> int:
    """Smallest n with (1 - f)^n <= 1/miss_den, i.e. P(no cheater in n random samples) tiny."""
    if not 0 < fraud_bps <= BPS:
        raise ValueError("fraud_bps out of range")
    keep = BPS - fraud_bps
    if keep == 0:
        return 1
    n = 1
    while keep ** n * miss_den > BPS ** n:
        n += 1
    return n


def draw_independent(seed, candidates, k, registry, exclude=frozenset()):
    """Equal operator chances, one key per operator, at most ceil(k/2) per family."""
    from math import ceil
    ranked=sorted(set(candidates)-set(exclude),key=lambda a:(
        H('independent-operator',seed,registry.get(a).operator),H('independent-agent',seed,a)))
    selected=[];operators=set();families={}
    for a in ranked:
        identity=registry.get(a)
        if identity.operator in operators or families.get(identity.family,0)>=ceil(k/2):continue
        selected.append(a);operators.add(identity.operator)
        families[identity.family]=families.get(identity.family,0)+1
        if len(selected)==k:break
    return selected
