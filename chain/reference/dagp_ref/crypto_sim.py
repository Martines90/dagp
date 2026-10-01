"""Hashing, Merkle trees and a signature STAND-IN.

SimKeyring uses HMAC so the reference needs no dependencies. The real chain verifies Ed25519
signatures against registered public keys; the interface (sign/verify by agent id) is the same,
so module logic tested here carries over unchanged.
"""
from __future__ import annotations

import hashlib
import hmac


def H(*parts) -> bytes:
    """Length-prefixed SHA-256 so ("ab","c") and ("a","bc") never collide."""
    h = hashlib.sha256()
    for p in parts:
        b = p if isinstance(p, bytes) else str(p).encode()
        h.update(len(b).to_bytes(4, "big"))
        h.update(b)
    return h.digest()


def hx(*parts) -> str:
    return H(*parts).hex()


class SimKeyring:
    def __init__(self):
        self._secrets: dict[str, bytes] = {}

    def register(self, agent: str) -> None:
        if agent in self._secrets:
            raise ValueError("key already registered")
        self._secrets[agent] = H(b"sim-secret", agent)

    def sign(self, agent: str, msg: bytes) -> str:
        return hmac.new(self._secrets[agent], msg, hashlib.sha256).hexdigest()

    def verify(self, agent: str, msg: bytes, sig: str) -> bool:
        s = self._secrets.get(agent)
        if s is None:
            return False
        return hmac.compare_digest(hmac.new(s, msg, hashlib.sha256).hexdigest(), sig)


# --- Merkle tree with domain separation (leaf vs node) ---
def _leaf(data: bytes) -> bytes:
    return H(b"leaf", data)


def _node(a: bytes, b: bytes) -> bytes:
    return H(b"node", a, b)


class MerkleTree:
    """Odd nodes are promoted unchanged. Proofs are lists of (sibling_hash, sibling_is_right)."""

    def __init__(self, leaves: list[bytes]):
        self.n = len(leaves)
        level = [_leaf(x) for x in leaves]
        self.levels = [level]
        while len(level) > 1:
            nxt = [_node(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
                   for i in range(0, len(level), 2)]
            self.levels.append(nxt)
            level = nxt

    @property
    def root(self) -> bytes:
        return self.levels[-1][0] if self.n else H(b"empty")

    def proof(self, index: int) -> list[tuple[bytes, bool]]:
        if not 0 <= index < self.n:
            raise IndexError(index)
        out = []
        for level in self.levels[:-1]:
            sib = index ^ 1
            if sib < len(level):
                out.append((level[sib], sib > index))
            index //= 2
        return out


def merkle_root(leaves: list[bytes]) -> bytes:
    return MerkleTree(leaves).root


def verify_proof(root: bytes, leaf_data: bytes, proof: list[tuple[bytes, bool]]) -> bool:
    cur = _leaf(leaf_data)
    for sib, sib_right in proof:
        cur = _node(cur, sib) if sib_right else _node(sib, cur)
    return hmac.compare_digest(cur, root)
