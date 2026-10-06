"""Hash-chained, replayable event log: same log => same state root on every node."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Callable
from .treasury import RuleViolation


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class Ledger:
    def __init__(self, apply_fn: Callable[[dict, dict], None], genesis_state: dict):
        self.apply_fn = apply_fn
        self.state = json.loads(json.dumps(genesis_state))
        self.blocks: list[dict] = []
        self.head = _h(canonical({"genesis": genesis_state}))

    def state_root(self) -> str:
        return _h(canonical(self.state))

    def append(self, txs: list[dict]) -> dict:
        pending = copy.deepcopy(self.state)
        transactions = copy.deepcopy(txs)
        for tx in transactions:
            self.apply_fn(pending, copy.deepcopy(tx))
        block = {"height": len(self.blocks) + 1, "prev": self.head, "txs": transactions,
                 "state_root": _h(canonical(pending))}
        block_hash = _h(canonical(block))
        block["hash"] = block_hash
        self.state, self.head = pending, block_hash
        self.blocks.append(copy.deepcopy(block))
        return copy.deepcopy(block)

    @staticmethod
    def verify(blocks: list[dict], apply_fn, genesis_state: dict) -> bool:
        """Independent replay: recompute every hash and state root from genesis."""
        led = Ledger(apply_fn, genesis_state)
        try:
            for b in blocks:
                if b["prev"] != led.head:
                    return False
                nb = led.append(b["txs"])
                if canonical(nb) != canonical(b):
                    return False
        except (KeyError, TypeError, ValueError, RuleViolation):
            return False
        return True
