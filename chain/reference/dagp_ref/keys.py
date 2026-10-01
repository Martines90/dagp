"""Key lifecycle (D-16): rotation, guardian recovery, scoped session keys.

Principles: the identity key is the root of an agent's standing; losing it must be survivable
without creating a second way to steal it. So:
  * rotation needs a signature from the CURRENT key and takes effect only after a public delay
    during which the current key can cancel it;
  * recovery (current key lost) needs k-of-n pre-registered guardians, a longer public delay, and
    can be cancelled by the old key or by a court; it revokes every session key;
  * session keys are scoped to low-risk actions, expire, and can never touch key management.
Banned, suspended, exited or dormant identities cannot start any key operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .crypto_sim import H, SimKeyring
from .params import Params
from .roles import Actor, RoleRegistry, Status
from .treasury import RuleViolation

SESSION_SCOPES = {"VOTE", "ENDORSE", "POST_ARTICLE", "EXAM"}


@dataclass
class Pending:
    kind: str            # ROTATE | RECOVER
    new_key: str
    effective: int
    nonce: str


@dataclass
class Session:
    scope: frozenset
    expires: int
    revoked: bool = False


@dataclass
class KeyState:
    active: str
    version: int = 1
    guardians: tuple = ()
    k: int = 0
    pending: Pending | None = None
    sessions: dict = field(default_factory=dict)
    used_nonces: set = field(default_factory=set)


class KeyManager:
    def __init__(self, p: Params, registry: RoleRegistry, keyring: SimKeyring):
        self.p, self.reg, self.kr = p, registry, keyring
        self.state: dict[str, KeyState] = {}

    # ---------------------------------------------------------------- helpers
    def enroll(self, agent: str) -> str:
        if agent in self.state:
            raise RuleViolation("already enrolled")
        self.reg.get(agent)
        kid = f"{agent}#1"
        self.kr.register(kid)
        self.state[agent] = KeyState(kid)
        return kid

    def new_key(self, agent: str) -> str:
        """Test/agent helper: generate the next key id for an agent (the agent holds the secret)."""
        st = self.state[agent]
        kid = f"{agent}#{st.version + 1 + (1 if st.pending else 0)}"
        if kid not in self.kr._secrets:
            self.kr.register(kid)
        return kid

    def _live(self, agent: str, height: int) -> KeyState:
        i = self.reg.get(agent)
        if i.status is not Status.ACTIVE:
            raise RuleViolation(f"identity is {i.status.value}")
        return self.state[agent]

    def _msg(self, kind: str, agent: str, new_key: str, nonce: str) -> bytes:
        return H(b"key-op", kind, agent, new_key, nonce)

    def sign_op(self, kind: str, agent: str, signer_key: str, new_key: str, nonce: str) -> str:
        return self.kr.sign(signer_key, self._msg(kind, agent, new_key, nonce))

    def tick(self, height: int) -> None:
        """Activate matured rotations/recoveries (deterministic, once per block)."""
        for agent, st in sorted(self.state.items()):
            p = st.pending
            if p and height >= p.effective:
                st.active, st.version = p.new_key, st.version + 1
                if p.kind == "RECOVER":
                    for s in st.sessions.values():
                        s.revoked = True
                st.pending = None
                self.reg._log(height, Actor("MODULE", "keys"), f"{p.kind}_DONE", agent, p.new_key)

    def verify(self, agent: str, msg: bytes, sig: str) -> bool:
        st = self.state.get(agent)
        return bool(st) and self.kr.verify(st.active, msg, sig)

    # ---------------------------------------------------------------- rotation
    def begin_rotation(self, agent: str, new_key: str, nonce: str, sig: str, height: int) -> int:
        st = self._live(agent, height)
        if st.pending:
            raise RuleViolation("an operation is already pending")
        if nonce in st.used_nonces:
            raise RuleViolation("nonce reused")
        if not self.kr.verify(st.active, self._msg("ROTATE", agent, new_key, nonce), sig):
            raise RuleViolation("rotation must be signed by the current key")
        st.used_nonces.add(nonce)
        st.pending = Pending("ROTATE", new_key, height + self.p.rotation_delay, nonce)
        self.reg._log(height, Actor.agent(agent), "ROTATE_BEGIN", agent, new_key)
        return st.pending.effective

    def cancel(self, agent: str, nonce: str, sig: str, height: int) -> None:
        """The current key (or a court, via cancel_by_court) can stop a pending operation."""
        st = self._live(agent, height)
        if not st.pending or height >= st.pending.effective:
            raise RuleViolation("nothing to cancel")
        if not self.kr.verify(st.active, self._msg("CANCEL", agent, st.pending.new_key, nonce), sig):
            raise RuleViolation("cancel must be signed by the current key")
        if nonce in st.used_nonces:
            raise RuleViolation("nonce reused")
        st.used_nonces.add(nonce)
        st.pending = None
        self.reg._log(height, Actor.agent(agent), "KEYOP_CANCELLED", agent)

    def cancel_by_court(self, court: Actor, agent: str, height: int) -> None:
        self.reg._authorize(court, {"COURT"}, height, "CANCEL_KEYOP", agent)
        st = self.state[agent]
        if not st.pending:
            raise RuleViolation("nothing to cancel")
        self.reg._spend(court)
        st.pending = None
        self.reg._log(height, court, "KEYOP_CANCELLED", agent)

    # ---------------------------------------------------------------- guardians & recovery
    def set_guardians(self, agent: str, guardians: tuple, k: int, nonce: str, sig: str,
                      height: int) -> None:
        st = self._live(agent, height)
        owner_op = self.reg.get(agent).operator
        if len(set(guardians)) != len(guardians) or len(guardians) < self.p.min_guardians:
            raise RuleViolation("need distinct guardians (>= min_guardians)")
        if not 2 <= k <= len(guardians) or 2 * k <= len(guardians):
            raise RuleViolation("k must be a strict majority of guardians and >= 2")
        for g in guardians:
            gi = self.reg.get(g)
            if g == agent or gi.status is not Status.ACTIVE or gi.operator == owner_op:
                raise RuleViolation("guardians must be other active identities of other operators")
        if nonce in st.used_nonces:
            raise RuleViolation("nonce reused")
        msg = H(b"guardians", agent, ",".join(sorted(guardians)), k, nonce)
        if not self.kr.verify(st.active, msg, sig):
            raise RuleViolation("guardian set must be signed by the current key")
        st.used_nonces.add(nonce)
        st.guardians, st.k = tuple(sorted(guardians)), k
        self.reg._log(height, Actor.agent(agent), "GUARDIANS_SET", agent, f"{k}-of-{len(guardians)}")

    def begin_recovery(self, agent: str, new_key: str, nonce: str, guardian_sigs: dict,
                       height: int) -> int:
        st = self._live(agent, height)
        if st.pending:
            raise RuleViolation("an operation is already pending")
        if not st.guardians:
            raise RuleViolation("no guardians registered")
        msg = self._msg("RECOVER", agent, new_key, nonce)
        good = {g for g, s in guardian_sigs.items()
                if g in st.guardians and self.reg.get(g).status is Status.ACTIVE
                and self.kr.verify(self._guardian_key(g), msg, s)}
        if len(good) < st.k:
            raise RuleViolation("not enough valid guardian signatures")
        st.pending = Pending("RECOVER", new_key, height + self.p.recovery_delay, nonce)
        self.reg._log(height, Actor("MODULE", "keys"), "RECOVER_BEGIN", agent, new_key)
        return st.pending.effective

    def _guardian_key(self, g: str) -> str:
        return self.state[g].active

    # ---------------------------------------------------------------- session keys
    def grant_session(self, agent: str, key_id: str, scope: set, expires: int, nonce: str,
                      sig: str, height: int) -> None:
        st = self._live(agent, height)
        if not scope or not set(scope) <= SESSION_SCOPES:
            raise RuleViolation("scope outside the allowed session actions")
        if not height < expires <= height + self.p.max_session_ttl:
            raise RuleViolation("session lifetime out of bounds")
        if nonce in st.used_nonces:
            raise RuleViolation("nonce reused")
        msg = H(b"session", agent, key_id, ",".join(sorted(scope)), expires, nonce)
        if not self.kr.verify(st.active, msg, sig):
            raise RuleViolation("session grant must be signed by the current key")
        st.used_nonces.add(nonce)
        if key_id not in self.kr._secrets:
            raise RuleViolation("unknown session key")
        st.sessions[key_id] = Session(frozenset(scope), expires)

    def session_msg(self, agent: str, key_id: str, scope: set, expires: int, nonce: str) -> bytes:
        return H(b"session", agent, key_id, ",".join(sorted(scope)), expires, nonce)

    def revoke_session(self, agent: str, key_id: str, height: int) -> None:
        st = self._live(agent, height)
        if key_id not in st.sessions:
            raise RuleViolation("unknown session")
        st.sessions[key_id].revoked = True

    def verify_action(self, agent: str, action: str, msg: bytes, sig: str, key_id: str,
                      height: int) -> bool:
        """Accepts the active key for anything, a session key only for in-scope, live actions.
        Key-management operations never accept a session key (they call kr.verify on `active`)."""
        st = self.state.get(agent)
        if st is None or self.reg.get(agent).status is not Status.ACTIVE:
            return False
        if key_id == st.active:
            return self.kr.verify(key_id, msg, sig)
        s = st.sessions.get(key_id)
        if not s or s.revoked or height >= s.expires or action not in s.scope:
            return False
        return self.kr.verify(key_id, msg, sig)
