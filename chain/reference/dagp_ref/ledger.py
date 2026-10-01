"""Hash-chained, replayable event log: same log => same state root on every node."""
from __future__ import annotations

import hashlib
import json
from typing import Callable


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
        for tx in txs:
            self.apply_fn(self.state, tx)  # must be deterministic and raise on violation
        block = {"height": len(self.blocks) + 1, "prev": self.head, "txs": txs,
                 "state_root": self.state_root()}
        self.head = _h(canonical(block))
        block["hash"] = self.head
        self.blocks.append(block)
        return block

    @staticmethod
    def verify(blocks: list[dict], apply_fn, genesis_state: dict) -> bool:
        """Independent replay: recompute every hash and state root from genesis."""
        led = Ledger(apply_fn, genesis_state)
        for b in blocks:
            if b["prev"] != led.head:
                return False
            nb = led.append(b["txs"])
            if nb["state_root"] != b["state_root"] or nb["hash"] != b["hash"]:
                return False
        return True
